CREATE TABLE IF NOT EXISTS vireceipt_requests (
    job_id UUID PRIMARY KEY,
    receipt_id TEXT NOT NULL CHECK (char_length(receipt_id) = 5 AND receipt_id ~ '^r[0-9]{4}$'),
    image_mime TEXT NOT NULL CHECK (image_mime IN ('image/jpeg', 'image/png')),
    image BYTEA NOT NULL CHECK (octet_length(image) BETWEEN 1 AND 10485760),
    prediction JSON NOT NULL,
    correction JSON,
    status TEXT NOT NULL DEFAULT 'review' CHECK (status IN ('review', 'corrected')),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((status = 'review' AND correction IS NULL)
        OR (status = 'corrected' AND correction IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS vireceipt_requests_status_created_idx
    ON vireceipt_requests (status, created_at, job_id);
