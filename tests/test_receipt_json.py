import json

import pytest


@pytest.mark.parametrize(
    "text,expected",
    [
        (' {"total": 1} ', {"total": 1}),
        ('```json\n{"total":1}\n```', {"total": 1}),
        ('```\n{"total":1}\n```', {"total": 1}),
        ("null", None),
        ("[]", []),
        ("not JSON", "not JSON"),
        ('Here is the receipt: {"total":1}', 'Here is the receipt: {"total":1}'),
        ('```json\n{"total":1}\n```\nExplanation', '```json\n{"total":1}\n```\nExplanation'),
        ("NaN", "NaN"),
        ("Infinity", "Infinity"),
        ('{"total":NaN}', '{"total":NaN}'),
    ],
)
def test_parser_preserves_invalid_outputs_instead_of_repairing_them(text, expected):
    from vireceipt.extractors.receipt_json import parse_receipt

    assert parse_receipt(text) == expected


def test_prompt_supplies_complete_current_output_schema():
    from vireceipt.extractors.receipt_json import build_prompt
    from vireceipt.schema import load_schema

    schema = json.loads(build_prompt().split("JSON Schema:\n", 1)[1])
    assert schema == load_schema()
    assert set(schema["required"]) == {
        "schema_version",
        "seller",
        "issued_at",
        "items",
        "subtotal",
        "discount",
        "vat",
        "total",
        "currency",
        "payment_method",
    }
