import copy
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def gold_path() -> Path:
    return FIXTURES / "gold.jsonl"


@pytest.fixture
def pred_path() -> Path:
    return FIXTURES / "pred.jsonl"


@pytest.fixture
def receipt(gold_path: Path) -> dict:
    """A valid receipt (deep copy, safe to mutate)."""
    first = json.loads(gold_path.read_text(encoding="utf-8").splitlines()[0])
    return copy.deepcopy(first["receipt"])
