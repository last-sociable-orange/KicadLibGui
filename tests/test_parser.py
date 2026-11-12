"""Parser tests: fixtures, missing fields, truncation, value overrides."""

from __future__ import annotations

from conftest import make_payload

from kicad_core.models import PARAM_COUNT
from kicad_core.parser import parse_categories, parse_digikey_response, parse_products


def test_full_fixture(full_response):
    product = parse_digikey_response(full_response)
    base = product.base
    assert base.manufacturer_product_number == "LM324N"
    assert base.manufacturer == "Texas Instruments"
    assert base.description == "IC OPAMP GP 4 CIRCUIT 14DIP"
    assert base.keywords == "General Purpose Amplifier 4 Circuit 14-PDIP"
    assert base.part_status == "Active"
    assert base.qty_available == "2500"
    assert base.package == '14-DIP (0.300", 7.62mm)'
    assert base.value == "LM324N"
    assert base.distributor == "Digikey"
    assert base.distributor_product_number == "LM324N-ND"
    assert base.unit_price == "0.45@1"
    assert base.datasheet_url == "https://www.ti.com/lit/ds/symlink/lm324.pdf"
    assert base.product_url == "https://www.digikey.com/en/products/detail/lm324n"
    assert base.id == (
        "Integrated Circuits (ICs)/Linear/Amplifiers/Instrumentation/LM324N"
    )
    assert product.params[0] == {
        "param": "Package / Case",
        "value": '14-DIP (0.300", 7.62mm)',
    }
    assert product.parameter_count() == 4


def test_missing_quantity_defaults_to_zero():
    payload = make_payload("NOQTY", qty=None)
    product = parse_digikey_response(payload)
    assert product.base.qty_available == "0"


def test_missing_optional_fields_do_not_raise():
    product = parse_digikey_response({"ManufacturerProductNumber": "MIN"})
    assert product.mpn == "MIN"
    assert product.base.manufacturer == ""
    assert product.base.description == ""
    assert product.base.qty_available == "0"
    assert product.base.package == ""
    assert len(product.params) == PARAM_COUNT
    assert product.params[0] == {"param": "-", "value": "-"}


def test_more_than_32_parameters_are_truncated():
    params = [
        {"ParameterId": index, "ParameterText": f"P{index}",
         "ValueText": f"V{index}", "ParameterType": "String"}
        for index in range(40)
    ]
    product = parse_digikey_response(make_payload(params=params))
    assert len(product.params) == PARAM_COUNT
    assert product.params[-1] == {"param": "P31", "value": "V31"}


def test_resistor_value_override():
    params = [{
        "ParameterId": 2085,
        "ParameterText": "Resistance",
        "ValueText": "10 kOhms",
        "ParameterType": "String",
    }]
    product = parse_digikey_response(make_payload("R1", params=params))
    assert product.base.value == "10 K"


def test_parameter_whitespace_stripped_for_non_strings():
    params = [{
        "ParameterId": 99,
        "ParameterText": "Power",
        "ValueText": "1 / 4 W",
        "ParameterType": "Numeric",
    }]
    product = parse_digikey_response(make_payload("R2", params=params))
    assert product.params[0]["value"] == "1/4W"


def test_datasheet_url_normalisation():
    product = parse_digikey_response(make_payload("D1", datasheet="//example.invalid/d.pdf"))
    assert product.base.datasheet_url == "https://example.invalid/d.pdf"
    product = parse_digikey_response(make_payload("D2", datasheet=None))
    assert product.base.datasheet_url == ""


def test_none_urls_become_empty():
    product = parse_digikey_response(make_payload("N1", datasheet=None, product_url=None))
    assert product.base.product_url == ""
    assert product.base.datasheet_url == ""


def test_parse_categories_recursive():
    nested = [{"Name": "A", "ChildCategories": [{"Name": "B", "ChildCategories": []}]}]
    assert parse_categories([""], nested) == ["", "A", "B"]


def test_parse_products_rejects_non_payloads():
    assert len(parse_products({"Products": []})) == 0
    for bad in ({}, {"Products": "nope"}, [], None):
        try:
            parse_products(bad)
        except ValueError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"expected ValueError for {bad!r}")
