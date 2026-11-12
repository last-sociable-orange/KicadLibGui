"""DigiKey ProductSearch client shared by the CLI and the GUI.

Compared with upstream this module adds a request timeout, typed errors
for the status codes the GUI maps to friendly messages, and an injectable
``requests`` session for tests.  The call signature remains compatible:
``digikey_search(keywords, token_file=".token", limit=10, offset=0)``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import re
import sys
from typing import Any

import requests

import digikey_auth
from kicad_core.errors import (
    AuthError,
    AuthRequired,
    NetworkError,
    ParseError,
    RateLimitError,
    SearchError,
    ServerError,
)

logger = logging.getLogger(__name__)

PRODUCT_SEARCH_URL = "https://api.digikey.com/products/v4/search/keyword"
DEFAULT_TIMEOUT = 30


def _retry_after_seconds(response: requests.Response) -> int:
    raw = ""
    try:
        raw = str(response.headers.get("Retry-After", "") or "")
    except AttributeError:  # pragma: no cover - unusual mock
        raw = ""
    try:
        return max(1, int(float(raw)))
    except (TypeError, ValueError):
        return 60


def _raise_for_status(response: requests.Response) -> None:
    status = response.status_code
    if status == 200:
        return
    detail = ""
    try:
        detail = (response.text or "")[:500]
    except Exception:  # pragma: no cover - defensive
        detail = ""
    if status == 401:
        raise AuthRequired("DigiKey session expired. Sign in again.", details=detail)
    if status == 403:
        raise SearchError(
            "This DigiKey app is not authorized for ProductSearch. "
            "Check the app's API scopes.",
            details=detail,
        )
    if status == 429:
        seconds = _retry_after_seconds(response)
        raise RateLimitError(
            f"DigiKey rate limit reached. Wait {seconds} seconds and retry.",
            details=detail,
            retry_after=seconds,
        )
    if 500 <= status < 600:
        raise ServerError(
            "DigiKey is temporarily unavailable. Retry in a moment.",
            details=detail,
        )
    raise SearchError(
        f"DigiKey returned HTTP {status}.", details=detail
    )


def digikey_search(
    keywords: str,
    token_file: str = ".token",
    limit: int = 10,
    offset: int = 0,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Search DigiKey and return the decoded JSON payload.

    Raises :class:`AuthRequired`, :class:`AuthError`, :class:`RateLimitError`,
    :class:`NetworkError`, :class:`ParseError` or :class:`SearchError`.
    """
    keywords = (keywords or "").strip()
    if not keywords:
        raise SearchError("Enter a part number or keyword to search for.")
    if limit < 1:
        raise SearchError("The result limit must be at least 1.")

    token = digikey_auth.ensure_token(token_file, timeout=timeout)
    client_id = str(token.get("client_id", ""))
    access_token = str(token.get("access_token", ""))

    payload = {"Keywords": keywords, "Limit": int(limit), "Offset": int(offset)}
    headers = {
        "Accept": "application/json",
        "X-DIGIKEY-Client-Id": client_id,
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    http = session or requests
    try:
        logger.debug("Sending DigiKey ProductSearch request (limit=%s, offset=%s)", limit, offset)
        response = http.post(
            PRODUCT_SEARCH_URL, headers=headers, json=payload, timeout=timeout
        )
    except requests.Timeout as exc:
        raise NetworkError(
            "DigiKey did not answer in time. Check your network and retry.",
            details=str(exc),
        ) from exc
    except requests.RequestException as exc:
        raise NetworkError(details=str(exc)) from exc

    _raise_for_status(response)
    try:
        decoded = response.json()
    except ValueError as exc:
        raise ParseError(
            "DigiKey returned an unexpected response.",
            details=f"Invalid JSON: {exc}",
        ) from exc
    if not isinstance(decoded, dict):
        raise ParseError("DigiKey returned an unexpected response.")
    return decoded


def _summary(payload: dict[str, Any], keywords: str, limit: int, offset: int) -> dict[str, Any]:
    """Compact, agent-friendly JSON summary (kept from upstream CLI)."""
    products_summary = []
    for product_raw in payload.get("Products", []) or []:
        if not isinstance(product_raw, dict):
            continue
        distro_numbers = []
        distro_prices = []
        for variation in product_raw.get("ProductVariations", []) or []:
            if not isinstance(variation, dict):
                continue
            distro_numbers.append(variation.get("DigiKeyProductNumber", ""))
            pricing = variation.get("StandardPricing", []) or []
            if pricing:
                first = pricing[0]
                distro_prices.append(
                    f"{first.get('UnitPrice', '')}@{first.get('BreakQuantity', '')}"
                )
            else:
                distro_prices.append("-")

        raw_params = (product_raw.get("Parameters", []) or [])[:32]
        params_list = []
        package_val = ""
        value_val = product_raw.get("ManufacturerProductNumber", "") or ""
        for param in raw_params:
            if not isinstance(param, dict):
                continue
            p_name = param.get("ParameterText", "")
            p_val = param.get("ValueText", "")
            if param.get("ParameterType") != "String":
                p_val = re.sub(r"\s", "", p_val)
            params_list.append({"param": p_name, "value": p_val})
            if p_name == "Package / Case":
                package_val = p_val
            if param.get("ParameterId") in (2085, 1, 2087, 2049):
                value_val = (
                    p_val.replace("Ohms", "").upper() if "Ohms" in p_val else p_val
                )

        category = product_raw.get("Category", {}) or {}
        main_category = category.get("Name", "")
        cat_path = [""]
        child_cats = category.get("ChildCategories", []) or []
        while child_cats:
            first_category = child_cats[0] if isinstance(child_cats[0], dict) else {}
            cat_path.append(first_category.get("Name", ""))
            child_cats = first_category.get("ChildCategories", []) or []
        product_id = (
            main_category
            + "/".join(cat_path)
            + "/"
            + (product_raw.get("ManufacturerProductNumber", "") or "")
        )

        ds_url = product_raw.get("DatasheetUrl") or ""
        if ds_url and not ds_url.startswith("http"):
            ds_url = "https:" + ds_url

        products_summary.append(
            {
                "main_category": main_category,
                "id": product_id,
                "description": (product_raw.get("Description", {}) or {}).get(
                    "ProductDescription", ""
                ),
                "keywords": (product_raw.get("Description", {}) or {}).get(
                    "DetailedDescription", ""
                ),
                "value": value_val,
                "manufacturer": (product_raw.get("Manufacturer", {}) or {}).get(
                    "Name", ""
                ),
                "manufacturer_product_number": product_raw.get(
                    "ManufacturerProductNumber", ""
                ),
                "package": package_val,
                "kicad_symbol_library": "",
                "kicad_footprint_library": "",
                "part_status": (product_raw.get("ProductStatus", {}) or {}).get(
                    "Status", ""
                ),
                "qty_available": str(product_raw.get("QuantityAvailable", 0)),
                "distributor": "Digikey",
                "distributor_product_number": "/".join(distro_numbers),
                "unit_price": "/".join(distro_prices),
                "product_url": product_raw.get("ProductUrl") or "",
                "datasheet_url": ds_url,
                "parameters": params_list,
            }
        )
    return {
        "keywords": keywords,
        "limit": limit,
        "offset": offset,
        "total_products": len(products_summary),
        "products": products_summary,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Perform a DigiKey product search")
    parser.add_argument("keywords", type=str, help="Search keywords")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")
    parser.add_argument("--offset", type=int, default=0, help="Index offset for pagination")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="HTTP timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Output a JSON summary to stdout")
    args = parser.parse_args(argv)
    try:
        results = digikey_search(
            args.keywords,
            limit=args.limit,
            offset=args.offset,
            timeout=args.timeout,
        )
    except (AuthRequired, AuthError, SearchError) as exc:
        print(f"Search failed: {exc}", file=sys.stderr)
        if exc.details:
            print(f"  {exc.details}", file=sys.stderr)
        return 1
    if args.json:
        json.dump(
            _summary(results, args.keywords, args.limit, args.offset),
            sys.stdout,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0
    timestamp = datetime.datetime.now().strftime("%m-%d_%H-%M-%S")
    filename = f"response_{timestamp}_{args.keywords.replace(' ', '_')}.json"
    with open(filename, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
    print(f"Saved {len(results.get('Products', []) or [])} products to {filename}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
