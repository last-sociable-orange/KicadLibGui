"""GUI smoke test: construct the real window, search, save, browse, close."""

from __future__ import annotations

import time
import tkinter as tk

import pytest
from conftest import make_payload, tk_available

from kicad_core.parser import parse_digikey_response
from services.database_service import DatabaseService


def pump(app, seconds: float = 0.4) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.root.update()
        time.sleep(0.01)


@pytest.mark.skipif(not tk_available(), reason="no display available")
def test_gui_flow(workdir, monkeypatch):
    config_dir = workdir / "config"
    config_dir.mkdir()
    log_dir = workdir / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("KICAD_LIB_GEN_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("KICAD_LIB_GEN_LOG_DIR", str(log_dir))

    db_path = workdir / "components.db"
    service = DatabaseService(db_path)
    service.open_or_create(create=True)
    existing = parse_digikey_response(make_payload("EXISTING-1"))
    existing.with_mapping("Symbol:EXISTING", "Footprint:EXISTING")
    service.upsert(existing)

    from gui.app import App

    app = App(portable=False, database_path=str(db_path))
    try:
        pump(app, 0.8)
        assert app.database is not None
        assert app.db_info is not None
        assert app.db_info.count == 1

        products = [
            parse_digikey_response(make_payload("LM324N")),
            parse_digikey_response(make_payload("LM324NP", status="Obsolete")),
        ]
        app.window.search_var.set("LM324N")
        app.window._search_succeeded(products)
        pump(app, 0.3)
        assert app.window.results_table.products == products
        assert app.window.detail.product is not None
        assert app.window.detail.product.mpn == "LM324N"
        assert app.window.detail.in_database is False

        # The inline banner must be visible above the tabs, and must not leave
        # a gap behind when dismissed.
        app.window.clear_banner()
        pump(app, 0.2)
        tabs_y = app.window.tabs_bar.winfo_rooty()
        app.window.show_banner("A test warning", "", "warning")
        pump(app, 0.2)
        assert app.window.banner.winfo_ismapped()
        assert app.window.banner.winfo_height() > 0
        assert app.window.banner.winfo_rooty() < app.window.tabs_bar.winfo_rooty()
        app.window.clear_banner()
        pump(app, 0.2)
        assert not app.window.banner.winfo_ismapped()
        assert app.window.tabs_bar.winfo_rooty() == tabs_y

        app.window.detail.symbol_var.set("Symbol:IC_LM324N")
        app.window.detail.footprint_var.set("Footprint:IC_LM324N")
        monkeypatch.setattr("gui.main_window.messagebox.askyesno", lambda *a, **k: True)
        app.window.save_detail()
        pump(app, 0.5)
        assert app.database.count() == 2
        stored = app.database.find_by_mpn("LM324N")
        assert stored is not None
        assert stored.base.kicad_symbol_library == "Symbol:IC_LM324N"
        assert app.window.detail.in_database is True

        app.window._select_tab("database")
        pump(app, 0.3)
        tab = app.window.database_tab
        assert tab.records
        tab.tree.selection_set("0")
        tab._on_select()
        pump(app, 0.2)
        assert tab.current is not None
        assert tab.editor.winfo_ismapped()
        assert tab.symbol_var.get()

        assert app.runner.busy is False
    finally:
        app.close()
    assert not app.runner.busy


@pytest.mark.skipif(not tk_available(), reason="no display available")
def test_gui_empty_state(workdir, monkeypatch):
    config_dir = workdir / "config-empty"
    config_dir.mkdir()
    monkeypatch.setenv("KICAD_LIB_GEN_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("KICAD_LIB_GEN_LOG_DIR", str(workdir / "logs-empty"))

    from gui.app import App

    app = App(portable=False)
    try:
        pump(app, 0.5)
        assert app.database is None
        assert app.window.db_info is None
        app.window.search_var.set("LM324N")
        app.window.perform_search()
        pump(app, 0.2)
        dialogs = [child for child in app.root.winfo_children()
                   if isinstance(child, tk.Toplevel)]
        assert dialogs, "sign-in dialog should open without a token"
        assert not app.runner.busy
    finally:
        app.close()
