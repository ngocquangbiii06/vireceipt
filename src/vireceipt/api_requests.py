"""Local review reads over persisted extraction jobs."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from vireceipt.request_store import RequestStore, StoredRequest

_HEADERS = {"Cache-Control": "no-store"}


def requests_router(store: RequestStore | None) -> APIRouter:
    """Build bounded metadata/detail/image routes without rerunning the extractor."""
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

    return router
