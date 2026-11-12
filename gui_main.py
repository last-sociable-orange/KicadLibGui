"""KiCad LibGen GUI entry point.

Flags:
  --version     print the version and exit
  --self-test   import the modules and run an offline database/token/CSV check
  --smoke-test  construct the window under a display and close after 2 s (CI)
  --portable    keep settings, token and logs beside the executable
  --db PATH     open this database at startup
  --log-level   override the configured log level
"""

from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import version

logger = logging.getLogger(__name__)


def _emit(message: str) -> None:
    """Print when stdout exists (PyInstaller ``--windowed`` sets it to None)."""
    stream = sys.stdout
    if stream is not None:
        try:
            print(message, file=stream, flush=True)
        except Exception:
            pass


def _make_temp_dir(prefix: str) -> Path:
    """Create a writable temp directory, falling back to the CWD.

    ``tempfile.mkdtemp`` creates mode-0700 directories; on some locked-down
    Windows setups that ACL can make the directory unwritable by a sandboxed
    or service account (including CI runners).  A normal ``mkdir`` inherits
    the parent ACL and works there.
    """
    import uuid

    for parent in (None, os.getcwd()):
        base = Path(parent) if parent else Path(tempfile.gettempdir())
        path = base / f"{prefix}{uuid.uuid4().hex[:10]}"
        try:
            path.mkdir(parents=False, exist_ok=False)
            probe = path / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return path
        except OSError as exc:
            logger.debug("Temp dir %r unusable: %s", path, exc)
    raise RuntimeError("No writable temporary directory is available.")


def _cleanup_temp_dir(path: Path) -> None:
    import shutil

    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:  # pragma: no cover
        pass


@contextmanager
def _temp_directory(prefix: str):
    path = _make_temp_dir(prefix)
    try:
        yield str(path)
    finally:
        _cleanup_temp_dir(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="KiCadLibGen",
        description=f"{version.APP_NAME} - {version.APP_SUBTITLE}",
    )
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    parser.add_argument("--self-test", action="store_true",
                        help="run offline import/database/token checks and exit")
    parser.add_argument("--smoke-test", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--startup-test", action="store_true",
                        help=argparse.SUPPRESS)
    parser.add_argument("--portable", action="store_true",
                        help="use a data folder beside the executable")
    parser.add_argument("--db", type=str, default=None,
                        help="database to open at startup")
    parser.add_argument("--log-level", type=str, default=None,
                        choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser


def self_test() -> int:
    """Offline checks suitable for CI and PyInstaller smoke tests."""
    started = time.time()
    try:
        import colors  # noqa: F401  (CLI module must be importable)
        import digikey_auth
        import digikey_search  # noqa: F401
        import gui.app
        import gui.main_window  # noqa: F401
        import kicad_core
        from services.batch_service import validate_csv
        from services.database_service import DatabaseService

        with _temp_directory("kicad-libgen-selftest-") as temp:
            root = Path(temp)
            database_path = root / "components.db"
            service = DatabaseService(database_path)
            info = service.open_or_create(create=True)
            if info.count != 0:
                raise AssertionError("new database should be empty")

            product = kicad_core.ProductInfo(
                base=kicad_core.ProductInfoBase(
                    id="Test/Part/TEST-1",
                    description="Self-test part",
                    keywords="self test",
                    value="TEST-1",
                    manufacturer="Acme",
                    manufacturer_product_number="TEST-1",
                    package="0603",
                    part_status="Active",
                    qty_available="42",
                    distributor="Digikey",
                    distributor_product_number="TEST-1-ND",
                    unit_price="0.10@1",
                    product_url="https://example.invalid/product",
                    datasheet_url="https://example.invalid/datasheet.pdf",
                )
            )
            product.params[0] = {"param": "Resistance", "value": "10k"}
            product.with_mapping("Symbol:?", "Footprint:?")
            first = service.upsert(product)
            if first.action != "inserted":
                raise AssertionError(f"first upsert was {first.action}")
            second = service.upsert(product)
            if second.action != "updated":
                raise AssertionError(f"second upsert was {second.action}")
            if service.count() != 1:
                raise AssertionError("upsert duplicated a record")
            stored = service.find_by_mpn("TEST-1")
            if stored is None or stored.base.kicad_symbol_library != "Symbol:TEST-1":
                raise AssertionError("mapping placeholder was not resolved")
            if stored.base.kicad_footprint_library != "Footprint:TEST-1":
                raise AssertionError("footprint placeholder was not resolved")

            csv_path = root / "parts.csv"
            csv_path.write_text(
                "manufacturer_product_number,kicad_symbol_library,kicad_footprint_library\n"
                "TEST-1,Symbol:TEST-1,Footprint:TEST-1\n",
                encoding="utf-8-sig",
            )
            validation = validate_csv(csv_path)
            if not validation.valid or validation.total != 1:
                raise AssertionError("CSV validation failed")

            token_path = root / "token.json"
            now = int(time.time())
            digikey_auth.save_token(token_path, {
                "client_id": "self-test",
                "client_secret": "self-test",
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_by": now + 3600,
                "refresh_token_expires_by": now + 86400,
            })
            token = digikey_auth.load_token(token_path)
            if not digikey_auth.token_status(token).access_valid:
                raise AssertionError("token round-trip failed")

            payload = {
                "Products": [{
                    "ManufacturerProductNumber": "TEST-2",
                    "Manufacturer": {"Name": "Acme"},
                    "Description": {"ProductDescription": "Demo", "DetailedDescription": "Demo"},
                    "ProductStatus": {"Status": "Active"},
                    "QuantityAvailable": 7,
                    "ProductVariations": [{
                        "DigiKeyProductNumber": "TEST-2-ND",
                        "StandardPricing": [{"BreakQuantity": 1, "UnitPrice": 0.5}],
                    }],
                    "Parameters": [{
                        "ParameterId": 1, "ParameterText": "Resistance",
                        "ValueText": "10kOhms", "ParameterType": "String",
                    }],
                    "Category": {"Name": "Resistors", "ChildCategories": []},
                    "ProductUrl": "https://example.invalid/p",
                    "DatasheetUrl": "//example.invalid/d.pdf",
                }]
            }
            parsed = kicad_core.parse_digikey_response(payload["Products"][0])
            if parsed.mpn != "TEST-2" or parsed.base.value != "10K":
                raise AssertionError("parser self-test failed")
    except BaseException as exc:
        logger.exception("Self-test failed")
        _emit(f"SELF-TEST FAILED: {exc}")
        return 1

    elapsed = time.time() - started
    _emit(f"SELF-TEST OK ({elapsed:.2f}s)")
    return 0


def smoke_test() -> int:
    """Construct the real window, pump the loop for 2 s, then close."""
    return _gui_lifetime_test(2000)


def startup_test() -> int:
    """Construct and close the window quickly, for cold-start measurement."""
    return _gui_lifetime_test(250)


def _gui_lifetime_test(milliseconds: int) -> int:
    from gui.app import App

    with _temp_directory("kicad-libgen-smoke-") as temp:
        os.environ["KICAD_LIB_GEN_CONFIG_DIR"] = temp
        os.environ["KICAD_LIB_GEN_LOG_DIR"] = str(Path(temp) / "logs")
        try:
            app = App(portable=False)
        except Exception as exc:  # pragma: no cover - display failures
            _emit(f"GUI-TEST FAILED: {exc}")
            logger.exception("GUI test could not construct the window")
            return 1
        app.root.after(milliseconds, app.close)
        try:
            app.run()
        except Exception as exc:  # pragma: no cover
            _emit(f"GUI-TEST FAILED: {exc}")
            logger.exception("GUI test failed")
            return 1
    _emit("GUI-TEST OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.version:
        _emit(f"{version.APP_NAME} {version.__version__}")
        return 0
    if args.self_test:
        return self_test()
    if args.smoke_test:
        return smoke_test()
    if args.startup_test:
        return startup_test()

    from gui.app import App

    try:
        app = App(portable=args.portable or None, database_path=args.db)
    except Exception as exc:  # pragma: no cover - startup failures
        logger.exception("Could not start the GUI")
        _emit(f"Could not start {version.APP_NAME}: {exc}")
        try:
            from tkinter import messagebox

            messagebox.showerror(
                version.APP_NAME,
                f"Could not start {version.APP_NAME}:\n\n{exc}",
            )
        except Exception:
            pass
        return 1
    if args.log_level:
        logging.getLogger().setLevel(args.log_level)
    return app.run()


if __name__ == "__main__":  # pragma: no cover - executable entry point
    multiprocessing.freeze_support()
    raise SystemExit(main())
