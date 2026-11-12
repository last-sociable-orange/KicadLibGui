# KiCad CIP command line tool
# Usage:
#   kicad_cip --keywords/-k part_number [--output/-o db_name]
#   kicad_cip --batch/-b parts.csv   [--output/-o db_name]
#
# Workflow:
#   search DigiKey -> pick one product -> enter KiCad symbol/footprint ->
#   insert the row into the SQLite database.
#
# Database schema (authoritative; see kicad_core/database.py):
#   table "components", key ManufacturerProductNumber
#   ID, Description, Keywords, Value, Manufacturer, ManufacturerProductNumber,
#   Package, KicadSymbolLibrary, KicadFootprintLibrary, PartStatus,
#   QtyAvailable, Distributor, DistributorProductNumber, UnitPrice,
#   ProductUrl, DatasheetUrl, Param01, Value01 ... Param32, Value32.
#   The older comment in upstream's source was stale: this is what the
#   executed CREATE TABLE actually creates (80 columns, no UNIQUE index).
#
# The GUI and the CLI share kicad_core, so both write identical rows.

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from datetime import datetime
from typing import Any

import colors
import digikey_search
from kicad_core import ProductDb, ProductInfo, parse_digikey_response
from kicad_core.errors import AppError
from kicad_core.parser import parse_categories  # noqa: F401 - upstream re-export

logger = logging.getLogger(__name__)

try:  # The GUI build excludes prompt_toolkit; the CLI installs it.
    from prompt_toolkit import prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.formatted_text import ANSI
except ImportError:  # pragma: no cover - CLI dependency missing
    prompt = None
    WordCompleter = None  # type: ignore[assignment]
    ANSI = None  # type: ignore[assignment]

__version__ = "1.0.0"


def _require_prompt_toolkit() -> None:
    if prompt is None:
        raise SystemExit(
            "prompt_toolkit is required for the interactive CLI. "
            "Install it with: pip install prompt-toolkit"
        )


def select_product_prompt(products: list[ProductInfo]) -> ProductInfo:
    """Select one product from a list (interactive CLI)."""
    _require_prompt_toolkit()
    colors.print_info(f"Total {len(products)} products found:")
    if len(products) == 0:
        return ProductInfo()

    for index, product in enumerate(products):
        print(
            colors.print_product_item(
                index + 1,
                product.base.manufacturer_product_number,
                product.base.manufacturer,
                product.base.description,
                product.base.qty_available,
                product.base.part_status,
            )
        )
    while True:
        try:
            product_index = int(
                prompt(ANSI(colors.question("Choose one product, 0 to exit: ")), default="1")
            )
            if product_index == 0:
                sys.exit(0)
            if product_index < 1 or product_index > len(products):
                colors.print_error("Invalid selection, please retry...")
                continue
            product = products[product_index - 1]
            break
        except (ValueError, IndexError):
            colors.print_error("Invalid selection, please retry...")
    print(
        colors.print_selected(
            product.base.manufacturer_product_number,
            product.base.manufacturer,
            product.base.description,
        )
    )
    return product


def input_product_info_prompt(
    product: ProductInfo,
    symbol_completer: Any,
    footprint_completer: Any,
) -> ProductInfo:
    """Prompt for the KiCad mapping; ``?`` is replaced with the MPN."""
    _require_prompt_toolkit()
    try:
        if product.base.manufacturer_product_number == "":
            colors.print_warning("No product found in DigiKey")
            if prompt(ANSI(colors.question("Enter manually? [y|n]: ")), default="n") in ("y", "Y"):
                product.base.id = prompt(ANSI(colors.question("Enter Product ID: ")))
                product.base.description = prompt(
                    ANSI(colors.question("Enter Product Description: "))
                )
                product.base.keywords = prompt(
                    ANSI(colors.question("Enter Product keywords: "))
                )
                product.base.manufacturer = prompt(
                    ANSI(colors.question("Enter Product Manufacturer: "))
                )
                product.base.manufacturer_product_number = prompt(
                    ANSI(colors.question("Enter Product Manufacturer Product Number: "))
                )
                product.base.value = product.base.manufacturer_product_number
            else:
                return product

        symbol_input = prompt(
            ANSI(colors.question("Enter Kicad symbol library name: ")),
            default=product.base.kicad_symbol_library,
            completer=symbol_completer,
            complete_while_typing=True,
        )
        product.base.kicad_symbol_library = re.sub(
            r"\?", f"{product.base.manufacturer_product_number}", symbol_input
        )
        footprint_input = prompt(
            ANSI(colors.question("Enter Kicad footprint library name: ")),
            default=product.base.kicad_footprint_library,
            completer=footprint_completer,
            complete_while_typing=True,
        )
        product.base.kicad_footprint_library = re.sub(
            r"\?", f"{product.base.manufacturer_product_number}", footprint_input
        )
        return product
    except KeyboardInterrupt:
        colors.print_error("Keyboard interrupt, exit")
        sys.exit(1)


def write_batch_log(log_entries: list[dict[str, str]], input_filename: str,
                    log_dir: str | None = None) -> str:
    """Write ``<mpn>: <record> ==> <status>`` lines, upstream format."""
    timestamp = datetime.now().strftime("%y-%m-%d-%H-%M-%S")
    base_name = os.path.splitext(os.path.basename(input_filename))[0]
    directory = log_dir or os.path.dirname(os.path.abspath(input_filename)) or "."
    log_filename = os.path.join(directory, f"{base_name}-{timestamp}.log")
    with open(log_filename, "w", encoding="utf-8") as log_file:
        log_file.writelines(f"{entry['mpn']}: {entry['record']} ==> {entry['status']}\n" for entry in log_entries)
    return log_filename


def _read_batch_csv(path: str) -> list[dict[str, str]]:
    """Read the upstream CSV format, tolerating a BOM and blank lines."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.reader(handle) if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise ValueError("CSV file must contain a header line and at least one data row")
    if len(rows[0]) != 3:
        raise ValueError(
            "CSV file must have a header line and 3 fields: "
            "<product_number>, <symbol_library>, <footprint_library>"
        )
    entries: list[dict[str, str]] = []
    for line_number, row in enumerate(rows[1:], start=2):
        if len(row) != 3:
            raise ValueError(
                f"CSV line {line_number} must have exactly 3 fields "
                "(product_number, symbol_library, footprint_library)"
            )
        entries.append({"product": row[0].strip(), "symbol": row[1].strip(),
                        "footprint": row[2].strip()})
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kicad_cip",
        description="Search DigiKey and add parts to a KiCad database library.",
    )
    input_group = parser.add_argument_group("Inputs")
    input_mutex = input_group.add_mutually_exclusive_group(required=True)
    input_mutex.add_argument(
        "--keywords", "-k", type=str,
        help="product keywords, normally the manufacturer part number",
    )
    input_mutex.add_argument(
        "--batch", "-b", type=str,
        help="CSV file with one part per line (3 columns, header required)",
    )
    parser.add_argument(
        "--output", "-o", type=str, default="components.db",
        help="Output database file (default: components.db)",
    )
    parser.add_argument(
        "--timeout", type=float, default=30,
        help="HTTP timeout in seconds (default: 30)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    colors.print_header("═" * 60)
    colors.print_header(" KiCad Component Information Provider (CIP)")
    colors.print_header("═" * 60)
    print()

    try:
        db = ProductDb(db_name=args.output)
    except AppError as exc:
        colors.print_error(str(exc))
        return 1
    colors.print_info(f"Using database: {colors.highlight(args.output)}")
    print()

    batch_log: list[dict[str, str]] = []
    is_batch_mode = args.batch is not None
    keywords_list: list[dict[str, str]] = []
    try:
        if args.keywords is not None:
            keywords_list.append({"product": args.keywords, "symbol": "", "footprint": ""})
        else:
            keywords_list = _read_batch_csv(args.batch)
    except (OSError, ValueError) as exc:
        colors.print_error(str(exc))
        db.close()
        return 1

    colors.print_subheader("Processing parts...")
    print()
    exit_code = 0
    for keyword in keywords_list:
        mpn = keyword["product"]
        log_entry = {"mpn": mpn, "record": "", "status": ""}
        batch_mode = bool(keyword["symbol"] and keyword["footprint"])
        if not is_batch_mode:
            print()
            colors.print_info(f"Searching for: {colors.highlight(mpn)}")

        try:
            logger.info("Searching keyword: %s", mpn)
            results = digikey_search.digikey_search(mpn, timeout=args.timeout)
            products = [
                parse_digikey_response(result)
                for result in (results.get("Products") or [])
            ]

            if batch_mode:
                if len(products) == 0:
                    log_entry["status"] = "skipped-no-result"
                    batch_log.append(log_entry)
                    colors.print_warning(
                        f"Searching '{colors.highlight(mpn)}' returned no results. Skipping."
                    )
                    continue
                if len(products) > 1:
                    log_entry["status"] = "skipped-multi-results"
                    batch_log.append(log_entry)
                    colors.print_warning(
                        f"Searching '{colors.highlight(mpn)}' returned "
                        f"{len(products)} results. Skipping."
                    )
                    continue
                product = products[0]
            else:
                product = select_product_prompt(products)

            insert_op = True
            if db.query_record(product) is not None:
                if batch_mode:
                    log_entry["status"] = "skipped-duplicate"
                    batch_log.append(log_entry)
                    colors.print_warning(
                        f"'{colors.highlight(mpn)}' already exists in database. Skipping."
                    )
                    continue
                if prompt(ANSI(colors.question("Product exist, overwrite? [y|n]: ")), default="n") in ("n", "N"):
                    insert_op = False

            if not insert_op:
                continue

            if batch_mode:
                product.base.kicad_symbol_library = keyword["symbol"]
                product.base.kicad_footprint_library = keyword["footprint"]
            else:
                symbol_list = db.query_symbols()
                footprint_list = db.query_footprints()
                symbols = ["Standard:", "Symbol:?"] + [item[1] for item in symbol_list]
                footprints = ["Standard:", "Footprint:?"] + [item[1] for item in footprint_list]
                symbol_completer = WordCompleter(symbols, ignore_case=True)
                footprint_completer = WordCompleter(footprints, ignore_case=True)
                product.base.kicad_symbol_library = keyword["symbol"]
                product.base.kicad_footprint_library = keyword["footprint"]
                product = input_product_info_prompt(
                    product, symbol_completer, footprint_completer
                )

            if product.base.manufacturer_product_number != "":
                outcome = db.upsert(product)
                logger.info(
                    "inserted one record: %s", product.base.manufacturer_product_number
                )
                verb = "Inserted" if outcome.action == "inserted" else "Updated"
                colors.print_success(
                    f"{verb} '{colors.highlight(product.base.manufacturer_product_number)}' "
                    "in database."
                )
                if batch_mode:
                    log_entry["record"] = str(outcome.values)
                    log_entry["status"] = outcome.action
                    batch_log.append(log_entry)

        except AppError as exc:
            logger.error("Search failed for %s: %s", mpn, exc)
            if batch_mode:
                log_entry["status"] = "error"
                log_entry["record"] = str(exc)
                batch_log.append(log_entry)
                colors.print_error(f"'{mpn}': {exc}. Continuing.")
                continue
            colors.print_error(str(exc))
            exit_code = 1
        except Exception as exc:  # pragma: no cover - unexpected CLI failure
            logger.exception("Unexpected error for %s", mpn)
            if batch_mode:
                log_entry["status"] = "error"
                log_entry["record"] = str(exc)
                batch_log.append(log_entry)
                colors.print_error(f"'{mpn}': {exc}. Continuing.")
                continue
            colors.print_error(f"Unexpected error: {exc}")
            exit_code = 1

    if is_batch_mode and batch_log:
        log_file_path = write_batch_log(batch_log, args.batch)
        colors.print_success(f"Batch log written to: {colors.highlight(log_file_path)}")
        print()
        colors.print_header("─" * 40)
        colors.print_subheader("Batch Processing Summary")
        colors.print_header("─" * 40)
        inserted = sum(1 for entry in batch_log if entry["status"] in ("inserted", "updated"))
        no_result = sum(1 for entry in batch_log if entry["status"] == "skipped-no-result")
        multi_results = sum(1 for entry in batch_log if entry["status"] == "skipped-multi-results")
        duplicates = sum(1 for entry in batch_log if entry["status"] == "skipped-duplicate")
        errors = sum(1 for entry in batch_log if entry["status"] == "error")
        print(f"  Successfully inserted/updated: {inserted}")
        print(f"  Skipped (no results):          {no_result}")
        print(f"  Skipped (multi results):       {multi_results}")
        print(f"  Skipped (duplicates):          {duplicates}")
        print(f"  Errors:                        {errors}")
        print(f"  Total processed:               {len(batch_log)}")
        if errors:
            exit_code = 1

    print()
    if exit_code == 0:
        colors.print_success("Done!")
    else:
        colors.print_error("Finished with errors.")
    db.close()
    return exit_code


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
