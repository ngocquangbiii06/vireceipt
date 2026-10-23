"""Load the receipt JSON Schema and validate receipts against it."""

import json
from functools import cache
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_VERSION = "1.0"


@cache
def load_schema() -> dict[str, Any]:
    """Return the receipt JSON Schema shipped with the package."""
    text = files("vireceipt").joinpath("schemas/receipt.schema.json").read_text(encoding="utf-8")
    return json.loads(text)


@cache
def _validator() -> Draft202012Validator:
    schema = load_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_receipt(receipt: Any) -> list[str]:
    """Return schema errors for `receipt` as readable strings; an empty list means valid."""
    errors = sorted(_validator().iter_errors(receipt), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def is_valid_receipt(receipt: Any) -> bool:
    """Return True when `receipt` matches the schema."""
    return not validate_receipt(receipt)
