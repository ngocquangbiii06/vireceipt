"""PostgreSQL snapshots of extracted requests, independent of dataset labels."""

import json
import re
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from vireceipt.database import DatabaseConfig, connection
from vireceipt.eval.io import Prediction
from vireceipt.request_corrections import prepare_correction
from vireceipt.verify import Verification

_SUMMARY = "job_id::text, receipt_id, status, revision, created_at, updated_at"


class RequestNotFound(LookupError):
    """No persisted request has this UUID."""


class RevisionConflict(ValueError):
    """Another correction was saved since this reviewer read the job."""


@dataclass(frozen=True)
class RequestSummary:
    """Small queue entry without image or receipt data."""

    job_id: str
    receipt_id: str
    status: str
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class StoredRequest(RequestSummary):
    """One immutable model snapshot and its current review state."""

    image_mime: str
    image: bytes = field(repr=False)
    prediction: dict[str, Any] = field(repr=False)
    correction: Any = field(repr=False)


class RequestStore:
    """Open a separate transaction per operation; never replace an existing job."""

    def __init__(self, config: DatabaseConfig) -> None:
        self.config = config

    def save(self, prediction: Prediction, image_mime: str, image: bytes) -> str:
        """Persist a strict JSON snapshot and return a new UUID, even for repeated receipt IDs."""
        if (
            not isinstance(prediction.id, str)
            or not re.fullmatch(r"r[0-9]{4}", prediction.id)
            or prediction.decision != "review"
            or image_mime not in ("image/jpeg", "image/png")
            or not isinstance(image, bytes)
            or not 1 <= len(image) <= 10 * 1024 * 1024
        ):
            raise ValueError("Invalid request snapshot")
        row = vars(prediction).copy()
        extra = row.pop("extra")
        if (
            not isinstance(extra, dict)
            or set(extra) & row.keys()
            or any(not isinstance(key, str) for key in extra)
        ):
            raise ValueError("Invalid prediction metadata")
        row.update(extra)
        try:
            payload = json.dumps(row, ensure_ascii=False, allow_nan=False)
            payload.encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError) as error:
            raise ValueError("Prediction must be strict UTF-8 JSON") from error
        job_id = str(uuid4())
        with connection(self.config) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO vireceipt_requests "
                "(job_id, receipt_id, image_mime, image, prediction) "
                "VALUES (%s, %s, %s, %s, %s::json)",
                (job_id, prediction.id, image_mime, image, payload),
            )
        return job_id

    def get(self, job_id: str) -> StoredRequest | None:
        """Retrieve one job and its image, or None if the UUID is absent."""
        canonical = str(UUID(job_id))
        with connection(self.config) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                f"SELECT {_SUMMARY}, image_mime, image, prediction::text, correction::text "
                "FROM vireceipt_requests WHERE job_id = %s::uuid",
                (canonical,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return StoredRequest(
            *row[:6],
            row[6],
            bytes(row[7]),
            json.loads(row[8]),
            None if row[9] is None else json.loads(row[9]),
        )

    def correct(
        self,
        job_id: str,
        expected_revision: int,
        receipt: Any,
        *,
        store_id: str,
        source: str,
        quality: list[str],
        notes: str = "",
        today: date | None = None,
    ) -> tuple[int, Verification]:
        """Save a candidate correction only if the reviewer's revision is still current."""
        canonical = str(UUID(job_id))
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or not 0 <= expected_revision <= 2147483646
        ):
            raise ValueError("Invalid expected revision")
        payload, report = prepare_correction(
            receipt, store_id=store_id, source=source, quality=quality, notes=notes, today=today
        )
        with connection(self.config) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                "UPDATE vireceipt_requests SET correction = %s::json, status = 'corrected', "
                "revision = revision + 1, updated_at = CURRENT_TIMESTAMP "
                "WHERE job_id = %s::uuid AND revision = %s RETURNING revision",
                (payload, canonical, expected_revision),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "SELECT 1 FROM vireceipt_requests WHERE job_id = %s::uuid", (canonical,)
                )
                if cursor.fetchone() is None:
                    raise RequestNotFound("Request not found")
                raise RevisionConflict("Revision conflict")
        return row[0], report

    def list_requests(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[RequestSummary]:
        """Return bounded metadata pages, newest first, optionally filtered by review state."""
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or status not in (None, "review", "corrected")
        ):
            raise ValueError("Invalid request page")
        where = " WHERE status = %s" if status is not None else ""
        params = (status, limit, offset) if status is not None else (limit, offset)
        with connection(self.config) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                f"SELECT {_SUMMARY} FROM vireceipt_requests"
                + where
                + " ORDER BY created_at DESC, job_id DESC LIMIT %s OFFSET %s",
                params,
            )
            rows = cursor.fetchall()
        return [RequestSummary(*row) for row in rows]
