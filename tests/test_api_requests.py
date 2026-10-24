import json
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from vireceipt.api import create_app
from vireceipt.extraction import ExtractionResult

TODAY = date(2026, 10, 23)
ROOT = "/v1/requests"


@pytest.mark.parametrize("output", ["valid", "raw", "null", "extra_fields"])
def test_post_then_read_detail_and_original_image(api_repository, api_png, receipt, output):
    store, ids, _ = api_repository
    raw = {
        "valid": receipt,
        "raw": "bad JSON\x00\u2028",
        "null": None,
        "extra_fields": {"_sale_note": "keep", "nested": {"_sa_details": [1, 2]}},
    }[output]
    calls = []

    def backend(image):
        calls.append(image)
        return ExtractionResult(raw)

    with TestClient(create_app(backend, today=TODAY, store=store)) as client:
        body = client.post(
            "/v1/extract?receipt_id=r0001", content=api_png, headers={"Content-Type": "image/png"}
        ).json()
        ids.append(body["job_id"])
        path = ROOT + "/" + ids[0]
        detail = client.get(path)
        job = detail.json()
        assert detail.status_code == 200 and detail.headers["cache-control"] == "no-store"
        assert job["prediction"] == {key: value for key, value in body.items() if key != "job_id"}
        assert job["receipt_id"] == "r0001" and job["status"] == "review" and job["revision"] == 0
        assert job["correction"] is None and "image" not in job
        assert job["created_at"] and job["updated_at"]
        image = client.get(path + "/image")
        assert image.status_code == 200 and image.content == api_png
        assert image.headers["content-type"] == "image/png"
        assert image.headers["cache-control"] == "no-store" and len(calls) == 1
        for suffix in ("", "/image"):
            assert client.get(ROOT + "/" + str(uuid4()) + suffix).status_code == 404


def test_queue_pages_only_metadata_and_filters_status(api_repository, api_png, receipt):
    from vireceipt.database import connection

    store, ids, _ = api_repository
    with TestClient(
        create_app(lambda image: ExtractionResult(receipt), today=TODAY, store=store)
    ) as client:
        for _ in range(3):
            ids.append(
                client.post(
                    "/v1/extract?receipt_id=r0001",
                    content=api_png,
                    headers={"Content-Type": "image/png"},
                ).json()["job_id"]
            )
        page = client.get(ROOT, params={"limit": 1, "offset": 1}).json()
        assert page["limit"] == 1 and page["offset"] == 1
        assert [item["job_id"] for item in page["items"]] == [ids[1]]
        assert set(page["items"][0]) == {
            "job_id",
            "receipt_id",
            "status",
            "revision",
            "created_at",
            "updated_at",
        }
        with connection(store.config) as conn:
            conn.cursor().execute(
                "UPDATE vireceipt_requests SET status = 'corrected', correction = %s::json "
                "WHERE job_id = %s::uuid",
                (json.dumps(receipt), ids[0]),
            )
        corrected = client.get(ROOT, params={"status": "corrected"})
        assert ids[0] in {item["job_id"] for item in corrected.json()["items"]}
        assert all(item["status"] == "corrected" for item in corrected.json()["items"])
        assert corrected.headers["cache-control"] == "no-store"
        review = client.get(ROOT, params={"status": "review"}).json()["items"]
        assert ids[0] not in {item["job_id"] for item in review}


def test_detail_preserves_reserved_looking_keys_in_metadata_and_correction(api_repository, api_png):
    from vireceipt.database import connection
    from vireceipt.eval.io import Prediction

    store, ids, _ = api_repository
    ids.append(
        store.save(
            Prediction("r0001", None, decision="review", extra={"_sa_metadata": {"_sale": 1}}),
            "image/png",
            api_png,
        )
    )
    correction = {"_sale_total": 123, "receipt": {"_sa_details": "preserve"}}
    with connection(store.config) as conn:
        conn.cursor().execute(
            "UPDATE vireceipt_requests SET status = 'corrected', correction = %s::json "
            "WHERE job_id = %s::uuid",
            (json.dumps(correction), ids[0]),
        )
    with TestClient(create_app(lambda image: ExtractionResult(None), store=store)) as client:
        body = client.get(ROOT + "/" + ids[0]).json()
    assert body["prediction"]["_sa_metadata"] == {"_sale": 1}
    assert body["correction"] == correction


@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize(
    "suffix",
    ["", "/00000000-0000-0000-0000-000000000001", "/00000000-0000-0000-0000-000000000001/image"],
)
def test_storage_unavailable_routes_are_sanitized(configured, suffix):
    def unavailable(*args, **kwargs):
        raise RuntimeError("PRIVATE_STORAGE_EXCEPTION")

    store = SimpleNamespace(get=unavailable, list_requests=unavailable) if configured else None
    with TestClient(create_app(lambda image: ExtractionResult(None), store=store)) as client:
        response = client.get(ROOT + suffix)
    expected = "storage_unavailable" if configured else "storage_not_configured"
    assert response.status_code == 503 and response.json() == {"detail": expected}
    assert "PRIVATE_STORAGE_EXCEPTION" not in response.text


@pytest.mark.parametrize(
    "path",
    ["?limit=0", "?limit=101", "?offset=-1", "?status=accepted", "/bad-uuid", "/bad-uuid/image"],
)
def test_invalid_request_queries_are_rejected_before_storage(path):
    with TestClient(create_app(lambda image: ExtractionResult(None))) as client:
        assert client.get(ROOT + path).status_code == 422
