"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def pytest_configure(config) -> None:
    """Hydrate Tcl/Tk before GUI tests.

    The development workspace is OneDrive-hosted; Windows can leave the Tcl
    library files as dehydrated placeholders, which makes Tk fail with
    "Can't find a usable init.tcl" on an otherwise valid install.  Reading
    the files once at session start is harmless on a normal machine and makes
    the GUI tests deterministic here.
    """
    if sys.platform != "win32":
        return
    tcl_root = Path(sys.base_prefix) / "tcl"
    if not tcl_root.exists():
        return
    for version_dir, env_name in (("tcl8.6", "TCL_LIBRARY"), ("tk8.6", "TK_LIBRARY")):
        directory = tcl_root / version_dir
        if directory.exists():
            os.environ.setdefault(env_name, str(directory))
    try:
        for path in tcl_root.rglob("*"):
            if path.is_file():
                try:
                    path.read_bytes()
                except OSError:
                    pass
    except OSError:
        pass


def tk_available(attempts: int = 3) -> bool:
    """Return True when a Tk root can be created (retry transient Tcl I/O)."""
    try:
        import tkinter as tk
    except ImportError:  # pragma: no cover - Python without Tk
        return False
    for attempt in range(attempts):
        try:
            root = tk.Tk()
            root.withdraw()
            root.update_idletasks()
            root.destroy()
            return True
        except tk.TclError:
            if attempt + 1 < attempts:
                time.sleep(0.2)
    return False


@pytest.fixture
def workdir():
    """A writable temp directory inside the repo (sandbox-friendly)."""
    base = Path(__file__).resolve().parent / ".tmp"
    base.mkdir(exist_ok=True)
    path = base / uuid.uuid4().hex
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def full_response() -> dict:
    with (FIXTURES / "digikey_product_full.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def make_payload(
    mpn: str = "TEST-1",
    *,
    qty: int | None = 42,
    params: list[dict] | None = None,
    status: str = "Active",
    manufacturer: str = "Acme",
    datasheet: str | None = "https://example.invalid/d.pdf",
    product_url: str | None = "https://example.invalid/p",
) -> dict:
    payload = {
        "ManufacturerProductNumber": mpn,
        "Manufacturer": {"Name": manufacturer},
        "Description": {
            "ProductDescription": f"{mpn} description",
            "DetailedDescription": f"{mpn} detailed",
        },
        "ProductStatus": {"Status": status},
        "ProductVariations": [{
            "DigiKeyProductNumber": f"{mpn}-ND",
            "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 0.5}],
        }],
        "Parameters": params if params is not None else [
            {"ParameterId": 1, "ParameterText": "Package / Case",
             "ValueText": "0603", "ParameterType": "String"},
        ],
        "Category": {"Name": "Test", "ChildCategories": []},
        "ProductUrl": product_url,
        "DatasheetUrl": datasheet,
    }
    if qty is not None:
        payload["QuantityAvailable"] = qty
    return payload
