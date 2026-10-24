"""Optional PostgreSQL configuration, transactions and schema initialization."""

import ipaddress
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class DatabaseConfig:
    """Validated server-owned connection settings; credentials never appear in repr."""

    host: str
    user: str = field(repr=False)
    database: str
    port: int = 5432
    password: str | None = field(default=None, repr=False)

    @classmethod
    def from_url(cls, url: str) -> "DatabaseConfig":
        """Parse a PostgreSQL URL without echoing credentials in validation errors."""
        try:
            if any(character.isspace() for character in url):
                raise ValueError
            parsed = urlsplit(url)
            host, user = parsed.hostname, unquote(parsed.username or "")
            port = parsed.port if parsed.port is not None else 5432
            database = unquote(parsed.path.removeprefix("/"))
            password = unquote(parsed.password) if parsed.password is not None else None
            if (
                parsed.scheme != "postgresql"
                or not host
                or not user
                or not database
                or "/" in database
                or parsed.query
                or parsed.fragment
                or not 1 <= port <= 65535
                or any("\x00" in value for value in (host, user, database, password or ""))
            ):
                raise ValueError
        except ValueError:
            raise ValueError("Invalid PostgreSQL connection URL") from None
        return cls(host, user, database, port, password)

    def ssl_context(self) -> ssl.SSLContext | bool:
        """Permit plain loopback connections; require certificate-verified TLS remotely."""
        try:
            local = ipaddress.ip_address(self.host).is_loopback
        except ValueError:
            local = self.host.casefold() == "localhost"
        return False if local else ssl.create_default_context()


@contextmanager
def connection(config: DatabaseConfig) -> Iterator[Any]:
    """Open one transaction, commit or roll back, and always close the connection."""
    import pg8000.dbapi

    conn = pg8000.dbapi.connect(
        user=config.user,
        host=config.host,
        database=config.database,
        port=config.port,
        password=config.password,
        ssl_context=config.ssl_context(),
        timeout=10,
        application_name="vireceipt",
    )
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database(config: DatabaseConfig) -> None:
    """Apply the initial idempotent DDL without resetting existing request data."""
    sql = files("vireceipt").joinpath("sql/001_requests.sql").read_text(encoding="utf-8")
    with connection(config) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
        finally:
            cursor.close()
