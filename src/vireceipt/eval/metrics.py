"""Field, line-item, receipt-level, abstention and operations metrics.

Outcome of one scalar field, comparing gold G with prediction P:
- correct:      G == P after the field's normalisation (both null counts as correct)
- wrong:        both present, different
- missed:       G present, P null
- hallucinated: G null, P present  (the model invented a value the receipt does not show)

A receipt whose prediction is null or does not match the schema counts as "invalid": every
present gold field is missed and every gold item is unmatched.
"""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from vireceipt.eval.io import GoldRecord, Prediction
from vireceipt.normalize import digits_only, norm_loose, norm_text, similarity
from vireceipt.schema import is_valid_receipt

NAME_SIM_THRESHOLD = 0.8
COVERAGES = (1.0, 0.9, 0.8, 0.7, 0.5)


def _text_key(v: str) -> str:
    return norm_loose(v)


def _digits_key(v: str) -> str:
    return digits_only(v)


def _exact_key(v: Any) -> Any:
    return v


# field path -> normalisation applied before comparing
SCALAR_FIELDS: dict[str, Callable[[Any], Any]] = {
    "seller.name": _text_key,
    "seller.address": _text_key,
    "seller.phone": _digits_key,
    "seller.tax_code": _digits_key,
    "issued_at.date": _exact_key,
    "issued_at.time": _exact_key,
    "subtotal": _exact_key,
    "discount": _exact_key,
    "vat": _exact_key,
    "total": _exact_key,
    "payment_method": _exact_key,
}
TEXT_FIELDS = ("seller.name", "seller.address")


def get_path(obj: dict[str, Any], path: str) -> Any:
    """Read a dotted path such as 'seller.name' from a receipt."""
    for part in path.split("."):
        obj = obj[part]
    return obj


def compare_field(path: str, gold: Any, pred: Any) -> str:
    """Return 'correct', 'wrong', 'missed' or 'hallucinated' for one scalar field."""
    if gold is None:
        return "correct" if pred is None else "hallucinated"
    if pred is None:
        return "missed"
    key = SCALAR_FIELDS[path]
    return "correct" if key(gold) == key(pred) else "wrong"


def _item_match_score(gold: dict[str, Any], pred: dict[str, Any]) -> float | None:
    if gold["amount"] is not None and gold["amount"] != pred["amount"]:
        return None
    score = similarity(gold["name"], pred["name"])
    return score if score >= NAME_SIM_THRESHOLD else None


def match_items(gold_items: list[dict], pred_items: list[dict]) -> int:
    """Greedy one-to-one matching; returns the number of matched (true positive) items.

    A pair matches when the names are at least NAME_SIM_THRESHOLD similar and, if the gold
    amount is known, the amounts are equal.
    """
    candidates = []
    for gi, g in enumerate(gold_items):
        for pi, p in enumerate(pred_items):
            score = _item_match_score(g, p)
            if score is not None:
                candidates.append((score, gi, pi))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    used_g, used_p = set(), set()
    for _, gi, pi in candidates:
        if gi not in used_g and pi not in used_p:
            used_g.add(gi)
            used_p.add(pi)
    return len(used_g)


@dataclass
class ReceiptResult:
    id: str
    valid: bool
    fields: dict[str, str]
    strict_text: dict[str, bool]  # text fields equal without casefolding / punctuation removal
    items_tp: int
    items_gold: int
    items_pred: int
    quality: tuple[str, ...]
    confidence: float | None = None
    decision: str | None = None
    latency_ms: float | None = None
    cost_usd: float | None = None

    @property
    def all_correct(self) -> bool:
        items_ok = self.items_tp == self.items_gold == self.items_pred
        return self.valid and items_ok and all(o == "correct" for o in self.fields.values())


def score_receipt(gold: GoldRecord, pred: Prediction | None) -> ReceiptResult:
    """Score one receipt. `pred` is None when the predictions file has no line for it."""
    g = gold.receipt
    p = pred.receipt if pred is not None else None
    valid = p is not None and is_valid_receipt(p)
    fields, strict = {}, {}
    for path in SCALAR_FIELDS:
        gv = get_path(g, path)
        pv = get_path(p, path) if valid else None
        fields[path] = compare_field(path, gv, pv)
        if path in TEXT_FIELDS:
            strict[path] = (gv is None and pv is None) or (
                gv is not None and pv is not None and norm_text(gv) == norm_text(pv)
            )
    pred_items = p["items"] if valid else []
    return ReceiptResult(
        id=gold.id,
        valid=valid,
        fields=fields,
        strict_text=strict,
        items_tp=match_items(g["items"], pred_items),
        items_gold=len(g["items"]),
        items_pred=len(pred_items),
        quality=gold.quality,
        confidence=pred.confidence if pred else None,
        decision=pred.decision if pred else None,
        latency_ms=pred.latency_ms if pred else None,
        cost_usd=pred.cost_usd if pred else None,
    )


def score_all(gold: list[GoldRecord], preds: list[Prediction]) -> list[ReceiptResult]:
    """Score every gold receipt. Predictions for ids that are not in the gold file are an error."""
    by_id = {p.id: p for p in preds}
    unknown = set(by_id) - {g.id for g in gold}
    if unknown:
        raise ValueError(f"predictions for ids not in the labels: {sorted(unknown)[:5]}")
    return [score_receipt(g, by_id.get(g.id)) for g in gold]


def _rate(num: int, den: int) -> float | None:
    return num / den if den else None


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    k = max(0, math.ceil(q * len(ordered)) - 1)
    return ordered[k]


def _f1(p: float | None, r: float | None) -> float | None:
    if p is None or r is None or p + r == 0:
        return None
    return 2 * p * r / (p + r)


def abstention_summary(results: list[ReceiptResult]) -> dict[str, Any]:
    """Accuracy among the most confident receipts, and accept/review outcomes if decided."""
    n = len(results)
    out: dict[str, Any] = {}
    if n and all(r.confidence is not None for r in results):
        ranked = sorted(results, key=lambda r: -r.confidence)  # stable for ties
        curve = []
        for c in COVERAGES:
            k = max(1, int(c * n + 0.5))  # round half up
            correct = sum(r.all_correct for r in ranked[:k])
            curve.append({"coverage": c, "n": k, "all_correct": correct, "rate": correct / k})
        out["coverage_curve"] = curve
    if n and all(r.decision is not None for r in results):
        accepted = [r for r in results if r.decision == "accept"]
        wrong = [r for r in results if not r.all_correct]
        caught = sum(r.decision == "review" for r in wrong)
        out["decisions"] = {
            "accepted": len(accepted),
            "auto_accept_rate": len(accepted) / n,
            "accepted_all_correct": sum(r.all_correct for r in accepted),
            "accepted_accuracy": _rate(sum(r.all_correct for r in accepted), len(accepted)),
            "wrong_receipts": len(wrong),
            "wrong_sent_to_review": caught,
            "error_catch_rate": _rate(caught, len(wrong)),
        }
    return out


def _by_quality(results: Iterable[ReceiptResult]) -> dict[str, dict[str, Any]]:
    slices: dict[str, list[ReceiptResult]] = {}
    for r in results:
        for tag in r.quality:
            slices.setdefault(tag, []).append(r)
    return {
        tag: {
            "n": len(rs),
            "all_correct": sum(r.all_correct for r in rs),
            "rate": sum(r.all_correct for r in rs) / len(rs),
        }
        for tag, rs in sorted(slices.items())
    }


@dataclass
class Summary:
    n: int
    valid: int
    all_correct: int
    fields: dict[str, dict[str, Any]]
    items: dict[str, Any]
    by_quality: dict[str, dict[str, Any]]
    abstention: dict[str, Any]
    operations: dict[str, Any]
    hallucinated_total: int = field(default=0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "valid_json": self.valid,
            "valid_json_rate": _rate(self.valid, self.n),
            "all_correct": self.all_correct,
            "all_correct_rate": _rate(self.all_correct, self.n),
            "hallucinated_total": self.hallucinated_total,
            "fields": self.fields,
            "items": self.items,
            "by_quality": self.by_quality,
            "abstention": self.abstention,
            "operations": self.operations,
        }


def summarize(results: list[ReceiptResult]) -> Summary:
    """Aggregate per-receipt results into the numbers that go into a report."""
    n = len(results)
    fields = {}
    for path in SCALAR_FIELDS:
        outcomes = [r.fields[path] for r in results]
        counts = {k: outcomes.count(k) for k in ("correct", "wrong", "missed", "hallucinated")}
        entry: dict[str, Any] = {**counts, "accuracy": _rate(counts["correct"], n)}
        if path in TEXT_FIELDS:
            entry["strict_accuracy"] = _rate(sum(r.strict_text[path] for r in results), n)
        fields[path] = entry

    tp = sum(r.items_tp for r in results)
    n_gold = sum(r.items_gold for r in results)
    n_pred = sum(r.items_pred for r in results)
    precision, recall = _rate(tp, n_pred), _rate(tp, n_gold)
    items = {
        "matched": tp,
        "gold": n_gold,
        "predicted": n_pred,
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }

    latencies = [r.latency_ms for r in results if r.latency_ms is not None]
    costs = [r.cost_usd for r in results if r.cost_usd is not None]
    operations = {
        "latency_ms_p50": _percentile(latencies, 0.5) if latencies else None,
        "latency_ms_p95": _percentile(latencies, 0.95) if latencies else None,
        "latency_n": len(latencies),
        "cost_usd_mean": sum(costs) / len(costs) if costs else None,
        "cost_n": len(costs),
    }

    return Summary(
        n=n,
        valid=sum(r.valid for r in results),
        all_correct=sum(r.all_correct for r in results),
        fields=fields,
        items=items,
        by_quality=_by_quality(results),
        abstention=abstention_summary(results),
        operations=operations,
        hallucinated_total=sum(f["hallucinated"] for f in fields.values()),
    )
