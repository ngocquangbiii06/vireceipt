import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def isolate_api_database(monkeypatch):
    """Never let API tests implicitly connect to a user's configured database."""
    monkeypatch.delenv("VIRECEIPT_DATABASE_URL", raising=False)


@pytest.fixture
def api_repository():
    import os

    pytest.importorskip("pg8000.dbapi")
    from vireceipt.database import DatabaseConfig, connection, init_database
    from vireceipt.request_store import RequestStore

    url = os.environ.get("VIRECEIPT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set VIRECEIPT_TEST_DATABASE_URL for PostgreSQL integration tests")
    config = DatabaseConfig.from_url(url)
    assert config.database == "vireceipt_test"
    init_database(config)
    ids = []
    try:
        yield RequestStore(config), ids, url
    finally:
        with connection(config) as conn:
            for job_id in ids:
                conn.cursor().execute(
                    "DELETE FROM vireceipt_requests WHERE job_id = %s::uuid", (job_id,)
                )


@pytest.fixture
def api_png():
    import io

    Image = pytest.importorskip("PIL.Image")
    stream = io.BytesIO()
    Image.new("RGB", (2, 3), "blue").save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture
def gold_path() -> Path:
    return FIXTURES / "gold.jsonl"


@pytest.fixture
def pred_path() -> Path:
    return FIXTURES / "pred.jsonl"


@pytest.fixture
def receipt(gold_path: Path) -> dict:
    """A valid receipt (deep copy, safe to mutate)."""
    first = json.loads(gold_path.read_text(encoding="utf-8").splitlines()[0])
    return copy.deepcopy(first["receipt"])


@pytest.fixture
def chat_server():
    """Real loopback HTTP server; requests never leave the test process's computer."""
    state = SimpleNamespace(requests=[], replies=[])

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state.requests.append((self.path, dict(self.headers), body))
            status, response, headers = state.replies[0]
            if len(state.replies) > 1:
                state.replies.pop(0)
            payload = response if isinstance(response, bytes) else json.dumps(response).encode()
            if status is None:
                self.wfile.write(payload)
                return
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

        def do_GET(self):
            state.requests.append((self.path, dict(self.headers), None))
            self.send_error(500)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
        )
        thread.start()
        state.url = f"http://127.0.0.1:{server.server_port}/v1"
        try:
            yield state
        finally:
            server.shutdown()
            thread.join(timeout=2)
