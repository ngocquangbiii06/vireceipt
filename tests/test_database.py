import json
import os
import ssl
from uuid import uuid4

import pytest


@pytest.mark.parametrize(
    "url",
    [
        "http://user@localhost/db",
        "postgresql://localhost/db",
        "postgresql://user@localhost/",
        "postgresql://user@localhost:0/db",
        "postgresql://user@localhost:bad/db",
        "postgresql://user@localhost/db?sslmode=disable",
    ],
)
def test_config_rejects_bad_urls_without_leaking_credentials(url):
    from vireceipt.database import DatabaseConfig

    with pytest.raises(ValueError) as caught:
        DatabaseConfig.from_url(url)
    assert url not in str(caught.value)


def test_config_decodes_credentials_and_requires_remote_tls():
    from vireceipt.database import DatabaseConfig

    config = DatabaseConfig.from_url("postgresql://demo:p%40ss@localhost:55432/vireceipt_test")
    assert config.password == "p@ss" and "p@ss" not in repr(config)
    assert "demo" not in repr(config)
    assert config.ssl_context() is False
    remote = DatabaseConfig.from_url("postgresql://demo:secret@db.example.com/vireceipt")
    assert remote.ssl_context().check_hostname
    assert "secret" not in repr(remote)


def test_config_rejects_unescaped_whitespace():
    from vireceipt.database import DatabaseConfig

    with pytest.raises(ValueError):
        DatabaseConfig.from_url("postgresql://demo@db server/vireceipt_test")


@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("host", ["localhost", "db.example.com"])
def test_connection_commits_or_rolls_back_and_always_closes(monkeypatch, failed, host):
    pg = pytest.importorskip("pg8000.dbapi")
    from vireceipt.database import DatabaseConfig, connection

    calls = []

    class FakeConnection:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

        def close(self):
            calls.append("close")

    settings = {}

    def fake_connect(**kwargs):
        settings.update(kwargs)
        return FakeConnection()

    monkeypatch.setattr(pg, "connect", fake_connect)
    config = DatabaseConfig.from_url(f"postgresql://demo@{host}/vireceipt_test")
    if failed:
        with pytest.raises(RuntimeError), connection(config):
            raise RuntimeError("synthetic transaction error")
    else:
        with connection(config):
            pass
    assert calls == (["rollback", "close"] if failed else ["commit", "close"])
    if host == "localhost":
        assert settings["ssl_context"] is False
    else:
        assert settings["ssl_context"].check_hostname
        assert settings["ssl_context"].verify_mode == ssl.CERT_REQUIRED


def test_migration_is_idempotent_and_preserves_json_on_real_postgres(receipt):
    pg = pytest.importorskip("pg8000.dbapi")
    from vireceipt.database import DatabaseConfig, connection, init_database

    url = os.environ.get("VIRECEIPT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VIRECEIPT_TEST_DATABASE_URL for the dedicated PostgreSQL test database")
    config = DatabaseConfig.from_url(url)
    assert config.database == "vireceipt_test", "Use only the dedicated test database"
    init_database(config)
    job_id, prediction = str(uuid4()), {"id": "r0001", "receipt": "raw\x00line\u2028text"}
    try:
        with connection(config) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vireceipt_requests "
                "(job_id, receipt_id, image_mime, image, prediction) "
                "VALUES (%s, %s, %s, %s, %s::json)",
                (job_id, "r0001", "image/png", b"synthetic image", json.dumps(prediction)),
            )
        init_database(config)
        with connection(config) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT prediction::text, status, revision FROM vireceipt_requests "
                "WHERE job_id = %s::uuid",
                (job_id,),
            )
            saved, status, revision = cursor.fetchone()
            assert json.loads(saved) == prediction and status == "review" and revision == 0
        with connection(config) as conn:
            conn.cursor().execute(
                "UPDATE vireceipt_requests SET image = %s WHERE job_id = %s::uuid",
                (b"x" * (10 * 1024 * 1024), job_id),
            )
        for column, value in [
            ("receipt_id", "bad"),
            ("image_mime", "text/plain"),
            ("revision", -1),
            ("status", "pending"),
            ("status", "corrected"),
            ("image", b""),
            ("image", b"x" * (10 * 1024 * 1024 + 1)),
        ]:
            with pytest.raises(pg.DatabaseError) as caught, connection(config) as conn:
                conn.cursor().execute(
                    f"UPDATE vireceipt_requests SET {column} = %s WHERE job_id = %s::uuid",
                    (value, job_id),
                )
            assert caught.value.args[0]["C"] == "23514"  # PostgreSQL CHECK violation.
        with connection(config) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE vireceipt_requests SET correction = %s::json, status = 'corrected', "
                "revision = revision + 1, updated_at = CURRENT_TIMESTAMP WHERE job_id = %s::uuid",
                (json.dumps(receipt), job_id),
            )
            cursor.execute(
                "SELECT correction::text, status, revision FROM vireceipt_requests "
                "WHERE job_id = %s::uuid",
                (job_id,),
            )
            correction, status, revision = cursor.fetchone()
            assert json.loads(correction) == receipt and status == "corrected" and revision == 1
    finally:
        with connection(config) as conn:
            conn.cursor().execute(
                "DELETE FROM vireceipt_requests WHERE job_id = %s::uuid", (job_id,)
            )
