"""CLI regression tests with a mocked DigiKey client (no network)."""

from __future__ import annotations

from conftest import make_payload

import kicad_cip
from kicad_core.database import ProductDb


def test_cli_batch_inserts_and_logs(workdir, monkeypatch):
    csv_path = workdir / "parts.csv"
    csv_path.write_text(
        "manufacturer_product_number,kicad_symbol_library,kicad_footprint_library\n"
        "TEST-1,Symbol:IC_TEST,Footprint:IC_TEST\n",
        encoding="utf-8-sig",
    )
    db_path = workdir / "components.db"

    def fake_search(mpn, **kwargs):
        return {"Products": [make_payload(mpn)]}

    monkeypatch.setattr(kicad_cip.digikey_search, "digikey_search", fake_search)
    code = kicad_cip.main(["-b", str(csv_path), "-o", str(db_path)])
    assert code == 0
    with ProductDb(db_path, create=False) as db:
        assert db.count() == 1
        stored = db.find_by_mpn("TEST-1")
        assert stored.base.kicad_symbol_library == "Symbol:IC_TEST"
        assert stored.base.kicad_footprint_library == "Footprint:IC_TEST"
    logs = list(workdir.glob("parts-*.log"))
    assert logs
    assert "==> inserted" in logs[0].read_text(encoding="utf-8")


def test_cli_batch_continues_after_error(workdir, monkeypatch):
    csv_path = workdir / "parts.csv"
    csv_path.write_text(
        "manufacturer_product_number,kicad_symbol_library,kicad_footprint_library\n"
        "BAD,S,F\nGOOD,S,F\n",
        encoding="utf-8-sig",
    )
    db_path = workdir / "components.db"

    def fake_search(mpn, **kwargs):
        if mpn == "BAD":
            raise RuntimeError("boom")
        return {"Products": [make_payload(mpn)]}

    monkeypatch.setattr(kicad_cip.digikey_search, "digikey_search", fake_search)
    code = kicad_cip.main(["-b", str(csv_path), "-o", str(db_path)])
    assert code == 1
    with ProductDb(db_path, create=False) as db:
        assert db.count() == 1


def test_cli_rejects_bad_csv(workdir, monkeypatch):
    csv_path = workdir / "parts.csv"
    csv_path.write_text("A,B\n", encoding="utf-8")
    db_path = workdir / "components.db"
    code = kicad_cip.main(["-b", str(csv_path), "-o", str(db_path)])
    assert code == 1
    with ProductDb(db_path, create=False) as db:
        assert db.count() == 0
