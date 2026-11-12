"""Defensive parsing of DigiKey ProductSearch responses.

The original upstream parser indexed every key directly.  A changed or
partial API response then raised ``KeyError`` and aborted a whole batch.
This port keeps the same output fields and transformations but tolerates
missing/``None`` values.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .models import ProductInfo

_VALUE_PARAMETER_IDS = frozenset({2085, 1, 2087, 2049})


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _nested(mapping: Any, *keys: str) -> Any:
    """Walk nested mappings, returning ``None`` as soon as a key is absent."""
    current: Any = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def parse_categories(
    flattened_categories: list[str], nested_categories: list[Any]
) -> list[str]:
    """Flatten DigiKey's first-child category chain (upstream behaviour)."""
    if len(nested_categories) == 0:
        return flattened_categories
    first = _mapping(nested_categories[0])
    flattened_categories.append(_text(first.get("Name")))
    return parse_categories(flattened_categories, _sequence(first.get("ChildCategories")))


def _price_list(raw_product: Mapping[str, Any]) -> tuple[str, str]:
    numbers: list[str] = []
    prices: list[str] = []
    for variation in _sequence(raw_product.get("ProductVariations")):
        variation = _mapping(variation)
        numbers.append(_text(variation.get("DigiKeyProductNumber")))
        pricing = _sequence(variation.get("StandardPricing"))
        if pricing:
            first = _mapping(pricing[0])
            prices.append(
                f"{_text(first.get('UnitPrice'))}@{_text(first.get('BreakQuantity'))}"
            )
        else:
            prices.append("-@-")
    return "/".join(numbers), "/".join(prices)


def parse_digikey_response(response: Any) -> ProductInfo:
    """Convert one raw ProductSearch product into a :class:`ProductInfo`."""
    raw = _mapping(response)
    product = ProductInfo()

    base = product.base
    mpn = _text(raw.get("ManufacturerProductNumber"))
    base.manufacturer_product_number = mpn
    base.value = mpn
    base.distributor = "Digikey"

    distributor_number, unit_price = _price_list(raw)
    base.distributor_product_number = distributor_number
    base.unit_price = unit_price

    package = ""
    parameters = _sequence(raw.get("Parameters"))[:32]
    for index, parameter in enumerate(parameters):
        parameter = _mapping(parameter)
        name = _text(parameter.get("ParameterText"))
        value = _text(parameter.get("ValueText"))
        if _text(parameter.get("ParameterType")) != "String":
            value = re.sub(r"\s", "", value)
        product.params[index] = {"param": name or "-", "value": value or "-"}

        if name == "Package / Case":
            package = value
        if parameter.get("ParameterId") in _VALUE_PARAMETER_IDS:
            if "Ohms" in value:
                base.value = value.removesuffix("Ohms").upper()
            else:
                base.value = value
    base.package = package

    category = _mapping(raw.get("Category"))
    base.main_category = _text(category.get("Name"))
    category_path = "/".join(
        parse_categories([""], _sequence(category.get("ChildCategories")))
    )
    base.id = f"{base.main_category}{category_path}/{mpn}"

    base.description = _text(_nested(raw, "Description", "ProductDescription"))
    base.keywords = _text(_nested(raw, "Description", "DetailedDescription"))
    base.manufacturer = _text(_nested(raw, "Manufacturer", "Name"))
    base.part_status = _text(_nested(raw, "ProductStatus", "Status"))

    qty = raw.get("QuantityAvailable")
    base.qty_available = "0" if qty is None else _text(qty)

    base.product_url = _text(raw.get("ProductUrl"))
    datasheet = _text(raw.get("DatasheetUrl"))
    if datasheet and not datasheet.startswith("http"):
        datasheet = "https:" + datasheet
    base.datasheet_url = datasheet

    base.kicad_symbol_library = ""
    base.kicad_footprint_library = ""
    product.normalise_params()
    return product


def parse_products(payload: Any) -> list[ProductInfo]:
    """Parse a ProductSearch payload into products.

    Raises :class:`ValueError` when the payload has no product list; the
    search service maps that to a user-facing ``ParseError``.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("response is not a JSON object")
    products = payload.get("Products")
    if products is None:
        raise ValueError("response has no 'Products' list")
    if not isinstance(products, (list, tuple)):
        raise ValueError("'Products' is not a list")
    return [parse_digikey_response(item) for item in products]
