"""Batch CSV validation and import-engine tests."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from conftest import make_payload

from kicad_core.errors import RateLimitError, SearchError
from kicad_core.parser import parse_digikey_response
from services.batch_service import (
    BatchOptions,
    BatchRunner,
    validate_csv,
)
from services.database_service import DatabaseService

HEADER = "manufacturer_product_number,kicad_symbol_library,kicad_footprint_library\n"


def csv_file(workdir, body: str, name: str = "parts.csv", encoding: str = "utf-8-sig"):
    path = workdir / name
    path.write_text(HEADER + body, encoding=encoding, newline="")
    return path


def product(mpn="TEST-1", symbol="Symbol:NEW", footprint="Footprint:NEW"):
    item = parse_digikey_response(make_payload(mpn))
    item.with_mapping(symbol, footprint)
    return item


def database(workdir):
    service = DatabaseService(workdir / "components.db")
    service.open_or_create(create=True)
    return service


class FakeSearch:
    def __init__(self, results=None, error=None, on_call=None):
        self.results = results or {}
        self.error = error
        self.calls: list[str] = []
        self.on_call = on_call

    def search(self, mpn, limit=25):
        self.calls.append(mpn)
        if self.on_call:
            self.on_call(mpn)
        if self.error is not None:
            if isinstance(self.error, list):
                result = self.error.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result
            raise self.error
        return self.results.get(mpn, [])


def runner_for(database_service, search, workdir, **option_kwargs):
    options = BatchOptions(delay_ms=0, **option_kwargs)
    return BatchRunner(search, database_service, options, log_dir=workdir)


# -- validation --------------------------------------------------------------


def test_validate_valid_csv(workdir):
    path = csv_file(workdir, "A,Symbol:A,Footprint:A\nB,Symbol:B,Footprint:B\n")
    result = validate_csv(path)
    assert result.valid
    assert result.total == 2
    assert result.rows[0].line == 2
    assert result.header == (
        "manufacturer_product_number",
        "kicad_symbol_library",
        "kicad_footprint_library",
    )


def test_validate_accepts_bom_and_crlf(workdir):
    path = workdir / "crlf.csv"
    path.write_bytes((HEADER + "A,Symbol:A,Footprint:A\r\n").encode("utf-8-sig"))
    result = validate_csv(path)
    assert result.valid
    assert result.rows[0].mpn == "A"


def test_validate_skips_blank_lines_and_quoted_commas(workdir):
    body = '\nA,Symbol:A,"Footprint:A,B"\n   \nB,Symbol:B,Footprint:B\n'
    result = validate_csv(csv_file(workdir, body))
    assert result.valid
    assert result.total == 2
    assert result.rows[0].footprint == "Footprint:A,B"


def test_validate_bad_header(workdir):
    path = workdir / "bad.csv"
    path.write_text("part,symbol,footprint\nA,B,C\n", encoding="utf-8")
    result = validate_csv(path)
    assert result.errors
    assert not result.valid


def test_validate_wrong_column_count(workdir):
    result = validate_csv(csv_file(workdir, "A,OnlyTwo\n"))
    assert result.errors
    assert "Expected 3 fields" in result.errors[0].message


def test_validate_missing_mapping(workdir):
    result = validate_csv(csv_file(workdir, "A,,\n"))
    assert result.errors
    assert any("symbol" in issue.message.lower() for issue in result.errors)
    assert any("footprint" in issue.message.lower() for issue in result.errors)


def test_validate_empty_file(workdir):
    path = workdir / "empty.csv"
    path.write_text("", encoding="utf-8")
    result = validate_csv(path)
    assert result.errors
    assert not result.valid


def test_validate_duplicate_warning(workdir):
    result = validate_csv(csv_file(workdir, "A,S,F\nA,S2,F2\n"))
    assert result.valid
    assert result.warnings
    assert "Duplicate" in result.warnings[0].message


# -- runner ------------------------------------------------------------------


def test_runner_inserts_and_writes_log(workdir):
    db = database(workdir)
    path = csv_file(workdir, "TEST-1,Symbol:NEW,Footprint:NEW\n")
    search = FakeSearch({"TEST-1": [product()]})
    summary = runner_for(db, search, workdir).run(validate_csv(path))
    assert summary.count("inserted") == 1
    assert summary.count("errors") == 0
    assert db.count() == 1
    stored = db.find_by_mpn("TEST-1")
    assert stored.base.kicad_symbol_library == "Symbol:NEW"
    assert summary.log_path is not None
    content = Path(summary.log_path).read_text(encoding="utf-8")
    assert "TEST-1:" in content
    assert "==> inserted" in content


def test_runner_no_result_and_multi_result(workdir):
    db = database(workdir)
    path = csv_file(workdir, "NONE,S,F\nMANY,S,F\n")
    search = FakeSearch({
        "NONE": [],
        "MANY": [product("MANY-1"), product("MANY-2")],
    })
    summary = runner_for(db, search, workdir).run(validate_csv(path))
    assert summary.count("skipped_no_result") == 1
    assert summary.count("skipped_multi_results") == 1
    assert db.count() == 0


def test_runner_skips_duplicate(workdir):
    db = database(workdir)
    db.upsert(product("TEST-1", "Symbol:OLD", "Footprint:OLD"))
    path = csv_file(workdir, "TEST-1,Symbol:NEW,Footprint:NEW\n")
    search = FakeSearch({"TEST-1": [product()]})
    summary = runner_for(db, search, workdir, skip_duplicates=True).run(validate_csv(path))
    assert summary.count("skipped_duplicates") == 1
    assert db.find_by_mpn("TEST-1").base.kicad_symbol_library == "Symbol:OLD"


def test_runner_overwrites_duplicate(workdir):
    db = database(workdir)
    db.upsert(product("TEST-1", "Symbol:OLD", "Footprint:OLD"))
    path = csv_file(workdir, "TEST-1,Symbol:NEW,Footprint:NEW\n")
    search = FakeSearch({"TEST-1": [product()]})
    summary = runner_for(
        db, search, workdir, skip_duplicates=False, overwrite_existing=True
    ).run(validate_csv(path))
    assert summary.count("updated") == 1
    assert db.find_by_mpn("TEST-1").base.kicad_symbol_library == "Symbol:NEW"


def test_runner_cancel_before_start(workdir):
    db = database(workdir)
    path = csv_file(workdir, "A,S,F\nB,S,F\n")
    event = threading.Event()
    event.set()
    search = FakeSearch({"A": [product("A")], "B": [product("B")]})
    runner = BatchRunner(
        search, db, BatchOptions(delay_ms=0), cancel_event=event, log_dir=workdir
    )
    summary = runner.run(validate_csv(path))
    assert summary.count("cancelled") == 2
    assert summary.count("inserted") == 0
    assert search.calls == []


def test_runner_cancel_after_in_flight_request(workdir):
    db = database(workdir)
    path = csv_file(workdir, "A,S,F\nB,S,F\n")
    event = threading.Event()

    def cancel_on_first(mpn):
        event.set()

    search = FakeSearch({"A": [product("A")], "B": [product("B")]}, on_call=cancel_on_first)
    runner = BatchRunner(
        search, db, BatchOptions(delay_ms=0), cancel_event=event, log_dir=workdir
    )
    summary = runner.run(validate_csv(path))
    assert summary.count("cancelled") == 2
    assert summary.count("inserted") == 0
    assert len(search.calls) == 1


def test_runner_error_row_does_not_stop_batch(workdir):
    db = database(workdir)
    path = csv_file(workdir, "A,S,F\nB,S,F\n")

    class BrokenSearch:
        def __init__(self):
            self.calls = []

        def search(self, mpn, limit=25):
            self.calls.append(mpn)
            if mpn == "A":
                raise SearchError("boom")
            return [product("B")]

    search = BrokenSearch()
    runner = BatchRunner(search, db, BatchOptions(delay_ms=0), log_dir=workdir)
    summary = runner.run(validate_csv(path))
    assert summary.count("errors") == 1
    assert summary.count("inserted") == 1
    assert db.count() == 1


def test_runner_retries_rate_limit(workdir):
    db = database(workdir)
    path = csv_file(workdir, "A,S,F\n")
    search = FakeSearch(error=[
        RateLimitError("slow", retry_after=1),
        RateLimitError("slow", retry_after=1),
        [product("A")],
    ])
    delays: list[float] = []
    runner = BatchRunner(
        search, db, BatchOptions(delay_ms=0, max_retries=3),
        log_dir=workdir, wait=lambda seconds: delays.append(seconds) or False,
    )
    summary = runner.run(validate_csv(path))
    assert summary.count("inserted") == 1
    assert delays == [2, 4]


def test_runner_aborts_after_repeated_rate_limit(workdir):
    db = database(workdir)
    path = csv_file(workdir, "A,S,F\nB,S,F\n")
    search = FakeSearch(error=RateLimitError("slow", retry_after=1))
    runner = BatchRunner(
        search, db, BatchOptions(delay_ms=0, max_retries=1),
        log_dir=workdir, wait=lambda seconds: False,
    )
    summary = runner.run(validate_csv(path))
    assert summary.aborted
    assert summary.count("errors") == 1
    assert summary.count("cancelled") == 1
    assert db.count() == 0


def test_runner_cancelled_while_waiting_rate_limit(workdir):
    db = database(workdir)
    path = csv_file(workdir, "A,S,F\n")
    search = FakeSearch(error=RateLimitError("slow", retry_after=1))
    runner = BatchRunner(
        search, db, BatchOptions(delay_ms=0, max_retries=3),
        log_dir=workdir, wait=lambda seconds: True,
    )
    summary = runner.run(validate_csv(path))
    assert summary.count("cancelled") == 1
    assert summary.aborted


def test_runner_requires_valid_csv(workdir):
    db = database(workdir)
    path = workdir / "bad.csv"
    path.write_text("bad,header\nA,B,C\n", encoding="utf-8")
    runner = runner_for(db, FakeSearch(), workdir)
    with pytest.raises(Exception):
        runner.run(validate_csv(path))
