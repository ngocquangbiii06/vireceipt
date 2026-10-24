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


def _body(receipt):
    return dict(
        receipt=receipt, expected_revision=0, store_id="shop-1", source="own", quality=["good"]
    )


def test_http_correction_keeps_original_and_rejects_stale_revision(
    api_repository, api_png, receipt
):
    store, ids, _ = api_repository
    calls = []

    def backend(image):
        calls.append(image)
        return ExtractionResult(None)

    with TestClient(create_app(backend, today=TODAY, store=store)) as client:
        prediction = client.post(
            "/v1/extract?receipt_id=r0001", content=api_png, headers={"Content-Type": "image/png"}
        ).json()
        ids.append(prediction["job_id"])
        path = "/v1/requests/" + ids[0]
        receipt["total"], receipt["issued_at"]["date"] = 123, "2026-11-12"
        body = _body(receipt) | {"notes": "A\x00\u2028B"}
        response = client.put(path + "/correction", json=body)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        saved = response.json()
        assert saved["job_id"] == ids[0] and saved["revision"] == 1
        assert saved["verification"]["schema_valid"] is True
        assert {"total", "date_future"} <= {
            issue["code"] for issue in saved["verification"]["issues"]
        }
        job = client.get(path).json()
        assert job["correction"] == {
            key: value for key, value in body.items() if key != "expected_revision"
        }
        assert job["status"] == "corrected" and job["revision"] == 1
        assert job["prediction"] == {
            key: value for key, value in prediction.items() if key != "job_id"
        }
        assert client.get(path + "/image").content == api_png
        body["notes"] = "stale overwrite"
        stale = client.put(path + "/correction", json=body)
        assert stale.status_code == 409 and stale.json() == {"detail": "revision_conflict"}
        assert client.get(path).json()["correction"]["notes"] == "A\x00\u2028B"
        body["expected_revision"] = 1
        assert client.put(path + "/correction", json=body).json()["revision"] == 2
        assert len(calls) == 1


@pytest.mark.parametrize(
    "scenario", ["bool", "negative", "overflow", "unknown", "source", "quality", "schema", "uuid"]
)
def test_invalid_http_correction_cannot_modify_job(api_repository, api_png, receipt, scenario):
    from vireceipt.eval.io import Prediction

    store, ids, _ = api_repository
    ids.append(store.save(Prediction("r0001", None, decision="review"), "image/png", api_png))
    body = _body(receipt)
    record_id = ids[0]
    if scenario in {"bool", "negative", "overflow"}:
        body["expected_revision"] = {"bool": True, "negative": -1, "overflow": 2147483647}[scenario]
    elif scenario == "uuid":
        record_id = "invalid-uuid"
    else:
        body.update(
            {
                "unknown": {"unexpected": 1},
                "source": {"source": "other"},
                "quality": {"quality": ["unknown"]},
                "schema": {"receipt": {}},
            }[scenario]
        )
    with TestClient(
        create_app(lambda image: ExtractionResult(None), store=store, today=TODAY)
    ) as client:
        assert client.put(f"/v1/requests/{record_id}/correction", json=body).status_code == 422
    job = store.get(ids[0])
    assert job.revision == 0 and job.correction is None and job.status == "review"


@pytest.mark.parametrize("configured", [False, True])
def test_unavailable_correction_storage_is_sanitized(configured, receipt):
    def unavailable(*args, **kwargs):
        raise RuntimeError("PRIVATE_DATABASE_ERROR")

    store = SimpleNamespace(correct=unavailable) if configured else None
    with TestClient(create_app(lambda image: ExtractionResult(None), store=store)) as client:
        response = client.put(f"/v1/requests/{uuid4()}/correction", json=_body(receipt))
    assert response.status_code == 503
    assert response.json() == {
        "detail": "storage_unavailable" if configured else "storage_not_configured"
    }
    assert "PRIVATE_DATABASE_ERROR" not in response.text


def test_missing_correction_job_returns_404(api_repository, receipt):
    store, _, _ = api_repository
    with TestClient(
        create_app(lambda image: ExtractionResult(None), store=store, today=TODAY)
    ) as client:
        response = client.put(f"/v1/requests/{uuid4()}/correction", json=_body(receipt))
    assert response.status_code == 404 and response.json() == {"detail": "request_not_found"}


@pytest.mark.parametrize(
    "field,value",
    [
        pytest.param("expected_revision", float("nan"), id="nan"),
        pytest.param("store_id", float("inf"), id="infinity"),
        pytest.param("expected_revision", "\ud800", id="surrogate"),
    ],
)
def test_invalid_json_values_return_sanitized_422_instead_of_500(receipt, field, value):
    body = _body(receipt) | {field: value}
    with TestClient(
        create_app(lambda image: ExtractionResult(None)), raise_server_exceptions=False
    ) as client:
        response = client.put(
            f"/v1/requests/{uuid4()}/correction",
            content=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )
    assert response.status_code == 422 and response.json() == {"detail": "invalid_request"}
    assert response.headers["cache-control"] == "no-store"
