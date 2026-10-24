from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from uuid import uuid4

import pytest

from vireceipt.eval.io import Prediction
from vireceipt.request_store import RequestStore

TODAY = date(2026, 10, 23)
META = {"store_id": " shop-1 ", "source": "own", "quality": ["good"], "today": TODAY}


def test_correction_preserves_snapshot_and_reports_printed_errors(api_repository, receipt):
    from vireceipt.request_store import RequestNotFound, RevisionConflict

    store, ids, _ = api_repository
    ids.append(store.save(Prediction("r0001", None, decision="review"), "image/png", b"image"))
    before = store.get(ids[0])
    receipt["total"] = 123
    revision, report = store.correct(ids[0], 0, receipt, notes="A\x00\u2028B", **META)
    job = store.get(ids[0])
    assert revision == job.revision == 1 and job.status == "corrected"
    assert job.prediction == before.prediction and job.image == before.image
    assert job.created_at == before.created_at and job.updated_at >= before.updated_at
    assert job.correction == {
        "receipt": receipt,
        "store_id": "shop-1",
        "source": "own",
        "quality": ["good"],
        "notes": "A\x00\u2028B",
    }
    assert report.schema_valid and "total" in {issue.code for issue in report.issues}
    assert report.grounding.checked is False
    receipt["total"] = 456
    assert store.get(ids[0]).correction["receipt"]["total"] == 123
    with pytest.raises(RevisionConflict):
        store.correct(ids[0], 0, receipt, **META)
    assert store.get(ids[0]).correction["receipt"]["total"] == 123
    receipt["subtotal"] = receipt["total"] = None
    for item in receipt["items"]:
        item["quantity"] = item["unit_price"] = item["amount"] = None
    revision, report = store.correct(ids[0], 1, receipt, **META)
    assert revision == 2 and report.schema_valid
    assert not {"line_amount", "items_sum", "total"} & {issue.code for issue in report.issues}
    with pytest.raises(RequestNotFound):
        store.correct(str(uuid4()), 0, receipt, **META)


def test_two_concurrent_reviewers_cannot_overwrite_each_other(api_repository, receipt):
    from vireceipt.request_store import RevisionConflict

    store, ids, _ = api_repository
    ids.append(store.save(Prediction("r0001", None, decision="review"), "image/png", b"image"))
    ready = Barrier(2)

    def attempt(notes):
        ready.wait(timeout=5)
        try:
            store.correct(ids[0], 0, receipt, notes=notes, **META)
            return notes
        except RevisionConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["reviewer-A", "reviewer-B"]))
    winners = [result for result in results if result is not None]
    assert len(winners) == 1
    job = store.get(ids[0])
    assert job.revision == 1 and job.correction["notes"] == winners[0]


@pytest.mark.parametrize(
    "scenario", ["revision", "bool", "overflow", "schema", "store", "source", "quality", "notes"]
)
def test_invalid_correction_never_connects(monkeypatch, receipt, scenario):
    from vireceipt.database import DatabaseConfig

    def forbidden(*args, **kwargs):
        raise AssertionError("Validate correction before database connection")

    monkeypatch.setattr("vireceipt.request_store.connection", forbidden)
    revision, metadata = 0, META.copy()
    if scenario in {"revision", "bool", "overflow"}:
        revision = {"revision": -1, "bool": True, "overflow": 2147483647}[scenario]
    elif scenario == "schema":
        receipt = {"total": float("nan")}
    else:
        metadata.update(
            {
                "store": {"store_id": " "},
                "source": {"source": "unknown"},
                "quality": {"quality": []},
                "notes": {"notes": "\ud800"},
            }[scenario]
        )
    store = RequestStore(DatabaseConfig.from_url("postgresql://test@localhost/vireceipt_test"))
    with pytest.raises(ValueError):
        store.correct(str(uuid4()), revision, receipt, **metadata)
