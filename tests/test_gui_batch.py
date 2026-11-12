"""GUI batch-dialog integration test (worker + progress + log)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from conftest import make_payload, tk_available

from kicad_core.parser import parse_digikey_response
from services.database_service import DatabaseService


def pump(app, seconds: float = 0.4) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.01)


class FakeSearch:
    def search(self, mpn, limit=25):
        return [parse_digikey_response(make_payload(mpn))]


@pytest.mark.skipif(not tk_available(), reason="no display available")
def test_batch_dialog_runs_and_writes_log(workdir, monkeypatch):
    config_dir = workdir / "config"
    config_dir.mkdir()
    monkeypatch.setenv("KICAD_LIB_GEN_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("KICAD_LIB_GEN_LOG_DIR", str(workdir / "logs"))

    db_path = workdir / "components.db"
    service = DatabaseService(db_path)
    service.open_or_create(create=True)

    csv_path = workdir / "batch.csv"
    csv_path.write_text(
        "manufacturer_product_number,kicad_symbol_library,kicad_footprint_library\n"
        "BATCH-1,Symbol:BATCH,Footprint:BATCH\n",
        encoding="utf-8-sig",
    )

    from gui.app import App
    from gui.dialogs.batch_dialog import BatchDialog

    app = App(portable=False, database_path=str(db_path))
    dialog = None
    try:
        pump(app, 0.8)
        app.search_service = FakeSearch()
        dialog = BatchDialog(app.root, app)
        dialog.load_file(str(csv_path))
        assert dialog._validation is not None and dialog._validation.valid
        dialog.delay_var.set("0")
        dialog._start()
        deadline = time.time() + 10
        while time.time() < deadline and dialog._running:
            app.root.update()
            time.sleep(0.02)
        assert not dialog._running
        assert dialog._summary is not None
        assert dialog._summary.count("inserted") == 1
        assert service.count() == 1
        assert dialog._summary.log_path is not None
        log_path = Path(dialog._summary.log_path)
        assert log_path.exists()
        assert "==> inserted" in log_path.read_text(encoding="utf-8")
        assert app.runner.busy is False
    finally:
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()
        app.close()
