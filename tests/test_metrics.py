import pytest

from vireceipt.eval.io import DataError, Prediction, load_gold, load_predictions
from vireceipt.eval.metrics import compare_field, match_items, score_all, summarize


@pytest.fixture
def summary(gold_path, pred_path):
    return summarize(score_all(load_gold(gold_path), load_predictions(pred_path))).to_dict()


def test_compare_field_outcomes():
    assert compare_field("total", None, None) == "correct"
    assert compare_field("total", None, 5000) == "hallucinated"
    assert compare_field("total", 5000, None) == "missed"
    assert compare_field("total", 5000, 6000) == "wrong"
    assert compare_field("seller.name", "Cửa hàng A", "CỬA HÀNG A.") == "correct"
    assert compare_field("seller.phone", "028 3812 3456", "028.3812.3456") == "correct"


def test_match_items_is_one_to_one_and_needs_equal_amounts():
    gold = [{"name": "Trà đá", "amount": 5000}, {"name": "Trà đá", "amount": 5000}]
    assert match_items(gold, [{"name": "Trà đá", "amount": 5000}]) == 1
    assert match_items(gold[:1], [{"name": "Trà đá", "amount": 6000}]) == 0
    assert match_items(gold[:1], [{"name": "Bánh bao", "amount": 5000}]) == 0


def test_receipt_level(summary):
    assert summary["n"] == 3
    assert summary["valid_json"] == 2  # r0003 failed extraction
    assert summary["all_correct"] == 1  # only r0001


def test_field_counts(summary):
    total = summary["fields"]["total"]
    assert (total["correct"], total["wrong"], total["missed"]) == (1, 1, 1)
    vat = summary["fields"]["vat"]
    assert (vat["correct"], vat["hallucinated"]) == (2, 1)
    name = summary["fields"]["seller.name"]
    assert name["correct"] == 2  # r0001 differs only in case; r0003 is missed
    assert name["strict_accuracy"] == pytest.approx(1 / 3)
    assert summary["hallucinated_total"] == 1


def test_items_order_and_small_typos_do_not_matter(summary):
    items = summary["items"]
    assert (items["matched"], items["gold"], items["predicted"]) == (3, 3, 3)
    assert items["f1"] == pytest.approx(1.0)


def test_by_quality_slices(summary):
    assert summary["by_quality"]["good"] == {"n": 1, "all_correct": 1, "rate": 1.0}
    assert summary["by_quality"]["skewed"]["all_correct"] == 0


def test_abstention(summary):
    curve = {row["coverage"]: row for row in summary["abstention"]["coverage_curve"]}
    assert (curve[1.0]["n"], curve[1.0]["all_correct"]) == (3, 1)
    assert (curve[0.5]["n"], curve[0.5]["all_correct"]) == (2, 1)
    d = summary["abstention"]["decisions"]
    assert d["accepted"] == 1
    assert d["accepted_accuracy"] == 1.0
    assert (d["wrong_receipts"], d["wrong_sent_to_review"]) == (2, 2)


def test_operations(summary):
    op = summary["operations"]
    assert (op["latency_ms_p50"], op["latency_ms_p95"], op["latency_n"]) == (800, 1500, 2)
    assert op["cost_usd_mean"] == pytest.approx(0.0005)


def test_missing_prediction_counts_as_invalid(gold_path):
    gold = load_gold(gold_path)
    s = summarize(score_all(gold, [])).to_dict()
    assert s["valid_json"] == 0 and s["all_correct"] == 0
    assert "coverage_curve" not in s["abstention"]


def test_prediction_for_unknown_id_is_an_error(gold_path):
    with pytest.raises(ValueError, match="not in the labels"):
        score_all(load_gold(gold_path), [Prediction(id="nope", receipt=None)])


def test_gold_file_errors_name_the_line(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "a", "store_id": "s", "receipt": {}}\n', encoding="utf-8")
    with pytest.raises(DataError, match=r"bad.jsonl:1: receipt does not match schema"):
        load_gold(bad)


def test_prediction_confidence_must_be_a_probability(tmp_path):
    bad = tmp_path / "pred.jsonl"
    bad.write_text('{"id": "a", "receipt": null, "confidence": "high"}\n', encoding="utf-8")
    with pytest.raises(DataError, match="confidence"):
        load_predictions(bad)
