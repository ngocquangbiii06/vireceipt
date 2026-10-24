"""Local review reads and optimistic corrections over persisted extraction jobs."""

from datetime import date
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from vireceipt.request_store import RequestNotFound, RequestStore, RevisionConflict, StoredRequest

_HEADERS = {"Cache-Control": "no-store"}


class CorrectionBody(BaseModel):
    """Explicit review values and the revision the reviewer actually read."""

    model_config = ConfigDict(extra="forbid", strict=True)

    receipt: dict[str, Any]
    expected_revision: int = Field(ge=0, le=2147483646)
    store_id: str
    source: Literal["own", "mcocr"]
    quality: list[str]
    notes: str = ""


def requests_router(store: RequestStore | None, *, today: date | None = None) -> APIRouter:
    """Build review routes without rerunning the extractor or replacing model snapshots."""
    router = APIRouter(prefix="/v1/requests")

    def get_job(job_id: UUID) -> StoredRequest:
        if store is None:
            raise HTTPException(503, "storage_not_configured")
        try:
            job = store.get(str(job_id))
        except Exception:
            raise HTTPException(503, "storage_unavailable") from None
        if job is None:
            raise HTTPException(404, "request_not_found")
        return job

    @router.get("")
    def list_requests(
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
        status: Literal["review", "corrected"] | None = None,
    ) -> JSONResponse:
        if store is None:
            raise HTTPException(503, "storage_not_configured")
        try:
            items = store.list_requests(limit=limit, offset=offset, status=status)
        except Exception:
            raise HTTPException(503, "storage_unavailable") from None
        return JSONResponse(
            jsonable_encoder({"items": items, "limit": limit, "offset": offset}), headers=_HEADERS
        )

    @router.get("/{job_id}")
    def detail(job_id: UUID) -> JSONResponse:
        row = vars(get_job(job_id)).copy()
        row.pop("image")
        return JSONResponse(jsonable_encoder(row, sqlalchemy_safe=False), headers=_HEADERS)

    @router.get("/{job_id}/image")
    def image(job_id: UUID) -> Response:
        job = get_job(job_id)
        return Response(job.image, media_type=job.image_mime, headers=_HEADERS)

    @router.put("/{job_id}/correction")
    def correct(job_id: UUID, body: CorrectionBody) -> JSONResponse:
        if store is None:
            raise HTTPException(503, "storage_not_configured", headers=_HEADERS)
        try:
            revision, report = store.correct(str(job_id), **body.model_dump(), today=today)
        except RequestNotFound:
            raise HTTPException(404, "request_not_found", headers=_HEADERS) from None
        except RevisionConflict:
            raise HTTPException(409, "revision_conflict", headers=_HEADERS) from None
        except ValueError:
            raise HTTPException(422, "invalid_correction", headers=_HEADERS) from None
        except Exception:
            raise HTTPException(503, "storage_unavailable", headers=_HEADERS) from None
        return JSONResponse(
            jsonable_encoder({"job_id": str(job_id), "revision": revision, "verification": report}),
            headers=_HEADERS,
        )

    return router
