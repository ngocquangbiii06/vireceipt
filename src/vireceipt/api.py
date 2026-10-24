"""Local HTTP extraction with optional durable PostgreSQL snapshots."""

import asyncio
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from vireceipt.api_images import MAX_BYTES, UploadError, validate_image
from vireceipt.database import DatabaseConfig, init_database
from vireceipt.extraction import Extractor, extract_images
from vireceipt.request_store import RequestStore


def create_app(
    extractor: Extractor | None = None,
    *,
    today: date | None = None,
    store: RequestStore | None = None,
) -> FastAPI:
    """Select the backend explicitly; persist only with a store or configured database URL."""
    if extractor is None:
        choice = os.environ.get("VIRECEIPT_API_BACKEND", "")
        if choice == "vlm":
            from vireceipt.extractors.chat_vlm import extract
        elif choice == "ocr-llm":
            from vireceipt.extractors.ocr_llm import extract
        else:
            raise ValueError("Set VIRECEIPT_API_BACKEND to vlm or ocr-llm")
        extractor = extract
    database_url = os.environ.get("VIRECEIPT_DATABASE_URL")
    if store is None and database_url is not None:
        try:
            config = DatabaseConfig.from_url(database_url)
            init_database(config)
            store = RequestStore(config)
        except Exception:
            raise RuntimeError("PostgreSQL storage initialization failed") from None
    app = FastAPI(title="ViReceipt local API", version="0.1.0")
    backend_lock = asyncio.Lock()

    def process(payload: bytes, content_type: str, record_id: str) -> JSONResponse:
        suffix = validate_image(payload, content_type)
        with tempfile.TemporaryDirectory(prefix="vireceipt-api-") as directory:
            image = Path(directory) / ("receipt" + suffix)
            image.write_bytes(payload)
            (prediction,) = extract_images({record_id: image}, extractor, today=today)
        row = vars(prediction).copy()
        row.update(row.pop("extra"))
        if store is not None:
            try:
                mime = "image/png" if suffix == ".png" else "image/jpeg"
                row["job_id"] = store.save(prediction, mime, payload)
            except Exception:
                raise HTTPException(503, "storage_unavailable") from None
        return JSONResponse(row, status_code=502 if "error" in row else 200)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/v1/extract",
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    mime: {"schema": {"type": "string", "format": "binary"}}
                    for mime in ("image/jpeg", "image/png")
                },
            }
        },
    )
    async def extract(
        request: Request,
        receipt_id: Annotated[str, Query(min_length=5, max_length=5, pattern=r"^r[0-9]{4}$")],
    ) -> JSONResponse:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                raise HTTPException(400, "invalid_content_length") from None
            if size < 0:
                raise HTTPException(400, "invalid_content_length")
            if size > MAX_BYTES:
                raise HTTPException(413, "image_too_large")
        payload = bytearray()
        async for chunk in request.stream():
            if len(payload) + len(chunk) > MAX_BYTES:
                raise HTTPException(413, "image_too_large")
            payload.extend(chunk)
        try:
            async with backend_lock:
                return await run_in_threadpool(
                    process, bytes(payload), request.headers.get("content-type", ""), receipt_id
                )
        except UploadError as error:
            raise HTTPException(error.status_code, error.code) from None
        except OSError:
            raise HTTPException(503, "temporary_storage_unavailable") from None

    return app
