import json
import os
from dataclasses import fields
from uuid import UUID, uuid4

import pytest

from vireceipt.eval.io import Prediction


@pytest.fixture
def repository():
    pytest.importorskip("pg8000.dbapi")
    from vireceipt.database import DatabaseConfig, connection, init_database
    from vireceipt.request_store import RequestStore

    url = os.environ.get("VIRECEIPT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VIRECEIPT_TEST_DATABASE_URL for PostgreSQL integration tests")
    config = DatabaseConfig.from_url(url)
    assert config.database == "vireceipt_test"
    init_database(config)
    ids = []
    try:
        yield RequestStore(config), ids
    finally:
        with connection(config) as conn:
            for job_id in ids:
                conn.cursor().execute(
                    "DELETE FROM vireceipt_requests WHERE job_id = %s::uuid", (job_id,)
                )


def test_save_snapshot_get_and_duplicate_receipt_ids(repository, receipt):
    store, ids = repository
    original = json.loads(json.dumps(receipt))
    for raw in (receipt, "invalid model JSON\x00\u2028", None):
        ids.append(
            store.save(
                Prediction(
                    "r0001",
                    raw,
                    decision="review",
                    extra={
                        "schema_valid": isinstance(raw, dict),
                        "grounding_checked": False,
                        "verification_issues": [{"code": "synthetic", "severity": "warning"}],
                    },
                ),
                "image/png",
                b"synthetic image",
            )
        )
    assert len(set(ids)) == 3 and all(str(UUID(value)) == value for value in ids)
    receipt["total"] = 1
    job = store.get(ids[0])
    assert job.receipt_id == "r0001" and job.prediction["receipt"] == original
    assert job.image_mime == "image/png" and job.image == b"synthetic image"
    assert job.status == "review" and job.revision == 0 and job.correction is None
    assert job.prediction["schema_valid"] is True
    assert job.prediction["grounding_checked"] is False
    assert job.prediction["verification_issues"] == [{"code": "synthetic", "severity": "warning"}]
    assert "synthetic image" not in repr(job) and "seller" not in repr(job)
    assert store.get(ids[1]).prediction["receipt"] == "invalid model JSON\x00\u2028"
    assert store.get(ids[2]).prediction["receipt"] is None
    assert store.get(str(uuid4())) is None


def test_list_is_bounded_metadata_only_and_supports_paging(repository, receipt):
    from vireceipt.database import connection
    from vireceipt.request_store import RequestSummary

    store, ids = repository
    for record_id in ("r0001", "r0002", "r0003"):
        ids.append(
            store.save(Prediction(record_id, None, decision="review"), "image/jpeg", b"image")
        )
    with connection(store.config) as conn:
        conn.cursor().execute(
            "UPDATE vireceipt_requests SET created_at = "
            "(SELECT max(created_at) + INTERVAL '1 second' FROM vireceipt_requests) "
            "WHERE job_id IN (%s::uuid, %s::uuid, %s::uuid)",
            tuple(ids),
        )
    expected = sorted(ids, reverse=True)
    page = store.list_requests(limit=2, offset=0, status="review")
    assert [row.job_id for row in page] == expected[:2]
    assert page[0].created_at == page[1].created_at
    assert store.list_requests(limit=1, offset=2)[0].job_id == expected[2]
    with connection(store.config) as conn:
        conn.cursor().execute(
            "UPDATE vireceipt_requests SET status = 'corrected', correction = %s::json, "
            "revision = revision + 1, updated_at = CURRENT_TIMESTAMP "
            "WHERE job_id = %s::uuid",
            (json.dumps(receipt), ids[0]),
        )
    job = store.get(ids[0])
    assert job.correction == receipt and job.status == "corrected" and job.revision == 1
    assert job.prediction["receipt"] is None
    corrected = store.list_requests(status="corrected")
    assert ids[0] in {row.job_id for row in corrected}
    assert all(row.status == "corrected" for row in corrected)
    assert ids[0] not in {row.job_id for row in store.list_requests(status="review")}
    assert {f.name for f in fields(RequestSummary)} == {
        "job_id",
        "receipt_id",
        "status",
        "revision",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize("scenario", ["id", "decision", "mime", "image", "reserved", "nonfinite"])
def test_invalid_save_never_opens_database(monkeypatch, scenario):
    from vireceipt.database import DatabaseConfig
    from vireceipt.request_store import RequestStore

    def forbidden(*args, **kwargs):
        raise AssertionError("Validation must run before connecting")

    monkeypatch.setattr("vireceipt.request_store.connection", forbidden)
    prediction, mime, image = Prediction("r0001", None, decision="review"), "image/png", b"image"
    if scenario == "id":
        prediction = Prediction("bad", None, decision="review")
    elif scenario == "decision":
        prediction = Prediction("r0001", None, decision="accept")
    elif scenario == "mime":
        mime = "text/plain"
    elif scenario == "image":
        image = b""
    elif scenario == "reserved":
        prediction = Prediction("r0001", None, decision="review", extra={"id": "r9999"})
    else:
        prediction = Prediction("r0001", float("nan"), decision="review")
    with pytest.raises(ValueError):
        RequestStore(DatabaseConfig.from_url("postgresql://test@localhost/vireceipt_test")).save(
            prediction, mime, image
        )


def test_invalid_queries_never_open_database(monkeypatch):
    from vireceipt.database import DatabaseConfig
    from vireceipt.request_store import RequestStore

    def forbidden(*args, **kwargs):
        raise AssertionError("Validation must run before connecting")

    monkeypatch.setattr("vireceipt.request_store.connection", forbidden)
    store = RequestStore(DatabaseConfig.from_url("postgresql://test@localhost/vireceipt_test"))
    for kwargs in (
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"offset": -1},
        {"status": "accept"},
    ):
        with pytest.raises(ValueError):
            store.list_requests(**kwargs)
    with pytest.raises(ValueError):
        store.get("not-a-uuid")
