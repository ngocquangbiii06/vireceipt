import traceback
from datetime import date
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from vireceipt.api import create_app
from vireceipt.extraction import ExtractionResult

TODAY = date(2026, 10, 23)
URL = "/v1/extract?receipt_id=r0001"
HEADERS = {"Content-Type": "image/png; charset=binary"}


def test_unconfigured_api_stays_stateless_without_database_initialization(monkeypatch, api_png):
    def forbidden(config):
        raise AssertionError("Stateless API must not initialize a database")

    monkeypatch.setattr("vireceipt.api.init_database", forbidden)
    with TestClient(create_app(lambda image: ExtractionResult(None), today=TODAY)) as client:
        response = client.post(URL, content=api_png, headers=HEADERS)
    assert response.status_code == 200 and "job_id" not in response.json()


@pytest.mark.parametrize("mode", ["injected", "environment"])
def test_api_persists_bytes_and_prediction_with_unique_jobs(
    api_repository, api_png, receipt, monkeypatch, mode
):
    store, ids, url = api_repository
    kwargs = {"store": store}
    if mode == "environment":
        monkeypatch.setenv("VIRECEIPT_DATABASE_URL", url)
        kwargs = {}
    app = create_app(lambda image: ExtractionResult(receipt), today=TODAY, **kwargs)
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post(URL, content=api_png, headers=HEADERS)
            body = response.json()
            ids.append(body["job_id"])
            assert response.status_code == 200
            job = store.get(ids[-1])
            assert job.image == api_png and job.image_mime == "image/png"
            assert job.prediction == {key: value for key, value in body.items() if key != "job_id"}
            assert job.prediction["receipt"] == receipt and job.status == "review"
    assert ids[0] != ids[1]


@pytest.mark.parametrize("failed", [False, True])
def test_invalid_output_and_backend_error_are_saved(api_repository, api_png, failed):
    store, ids, _ = api_repository

    def backend(image):
        if failed:
            raise RuntimeError("PRIVATE_BACKEND_ERROR")
        return ExtractionResult("broken JSON\x00\u2028")

    with TestClient(create_app(backend, today=TODAY, store=store)) as client:
        response = client.post(URL, content=api_png, headers=HEADERS)
    ids.append(response.json()["job_id"])
    assert response.status_code == (502 if failed else 200)
    job = store.get(ids[-1])
    assert job.prediction["receipt"] == (None if failed else "broken JSON\x00\u2028")
    assert job.prediction["schema_valid"] is False and job.prediction["decision"] == "review"
    assert "PRIVATE_BACKEND_ERROR" not in response.text


def test_storage_failure_is_sanitized_and_invalid_upload_never_saves(api_png, receipt):
    calls = []

    def save(*args):
        calls.append(args)
        raise RuntimeError("PRIVATE_DATABASE_CREDENTIALS")

    app = create_app(
        lambda image: ExtractionResult(receipt), today=TODAY, store=SimpleNamespace(save=save)
    )
    with TestClient(app) as client:
        assert client.post(URL, content=b"bad", headers=HEADERS).status_code == 422
        assert calls == []
        response = client.post(URL, content=api_png, headers=HEADERS)
    assert response.status_code == 503 and response.json() == {"detail": "storage_unavailable"}
    assert "PRIVATE_DATABASE_CREDENTIALS" not in response.text and len(calls) == 1


@pytest.mark.parametrize("failure", ["url", "connection"])
def test_storage_initialization_fails_without_echoing_secrets(monkeypatch, failure):
    monkeypatch.setenv(
        "VIRECEIPT_DATABASE_URL", "postgresql://user:PRIVATE_PASSWORD@localhost/vireceipt_test"
    )
    if failure == "url":
        monkeypatch.setenv("VIRECEIPT_DATABASE_URL", "PRIVATE_INVALID_URL")
    else:

        def unavailable(config):
            raise RuntimeError("PRIVATE_DATABASE_CREDENTIALS")

        monkeypatch.setattr("vireceipt.api.init_database", unavailable)
    with pytest.raises(RuntimeError, match="PostgreSQL storage initialization failed") as error:
        create_app(lambda image: ExtractionResult(None), today=TODAY)
    assert "PRIVATE_" not in "".join(traceback.format_exception(error.value))
