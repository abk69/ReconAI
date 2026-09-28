"""Public response hygiene, request ids, and operational log safety."""

from __future__ import annotations

import logging
import re
from collections.abc import Generator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.request_context import REQUEST_ID_HEADER
from app.db.models import Document
from app.db.session import get_db
from app.domain.enums import DocumentType
from app.embeddings.gemini import GeminiEmbeddingProvider
from app.llm.gemini import GeminiProvider
from app.llm.schemas import GeminiExtractionOutput
from app.main import app, create_app
from app.services.document_service import DocumentService
from app.storage.local import LocalFileStorage

PDF_BYTES = b"%PDF-1.4 hygiene"
API_KEY_SENTINEL = "TEST_API_KEY_SENTINEL"
DB_SENTINEL = "TEST_DATABASE_PASSWORD_SENTINEL"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _http_logs_stay_enabled() -> None:
    """Alembic's fileConfig disables loggers already created in this process."""
    http_logger = logging.getLogger("app.http")
    http_logger.disabled = False
    http_logger.propagate = True


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_document_post_and_get_omit_storage_path(
    client: TestClient,
    db_session: Session,
    storage_root: Path,
) -> None:
    created = client.post(
        "/documents",
        files={"file": ("hygiene.pdf", PDF_BYTES, "application/pdf")},
        data={"document_type": "PO"},
    )
    assert created.status_code == 201
    body = created.json()
    assert "storage_path" not in body
    assert body["status"] == "VALIDATED"

    fetched = client.get(f"/documents/{body['id']}")
    assert fetched.status_code == 200
    assert "storage_path" not in fetched.json()

    listed = client.get("/documents")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert "storage_path" not in listed.text

    row = db_session.get(Document, UUID(body["id"]))
    assert row is not None
    assert row.storage_path
    storage = LocalFileStorage(storage_root)
    assert storage.read(stored_filename=row.stored_filename) == PDF_BYTES
    assert storage.exists(stored_filename=row.storage_path)


def test_internal_upload_still_stores_the_file(db_session: Session, storage_root: Path) -> None:
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, is_duplicate = service.upload(
        filename="internal.pdf",
        content_type="application/pdf",
        data=PDF_BYTES,
        document_type=DocumentType.PO,
    )
    assert is_duplicate is False
    assert (storage_root / row.stored_filename).read_bytes() == PDF_BYTES


def test_generated_request_id_is_returned(client: TestClient) -> None:
    response = client.get("/health")
    request_id = response.headers[REQUEST_ID_HEADER]
    assert _UUID_RE.fullmatch(request_id)
    assert response.json() == {"status": "ok", "service": "reconai"}


def test_supplied_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: "req-123.ABC"})
    assert response.headers[REQUEST_ID_HEADER] == "req-123.ABC"


@pytest.mark.parametrize(
    "raw",
    [
        "bad id",
        "a" * 129,
        "../secret",
        "line\nbreak",
        f"postgresql://user:{DB_SENTINEL}@localhost/db",
    ],
)
def test_unsafe_request_id_is_replaced(client: TestClient, raw: str) -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: raw})
    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id != raw
    assert raw not in request_id
    assert API_KEY_SENTINEL not in request_id
    assert DB_SENTINEL not in request_id
    assert _UUID_RE.fullmatch(request_id)


def test_health_and_readiness_include_request_id(client: TestClient) -> None:
    health = client.get("/health")
    ready = client.get("/ready")
    assert health.status_code == 200
    assert ready.status_code == 200
    assert health.json() == {"status": "ok", "service": "reconai"}
    assert ready.json() == {"status": "ready"}
    assert _UUID_RE.fullmatch(health.headers[REQUEST_ID_HEADER])
    assert _UUID_RE.fullmatch(ready.headers[REQUEST_ID_HEADER])


def test_request_id_is_written_to_the_access_log(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.http"):
        response = client.get("/health", headers={REQUEST_ID_HEADER: "req-log-1"})
    assert response.headers[REQUEST_ID_HEADER] == "req-log-1"
    matches = [
        record.getMessage()
        for record in caplog.records
        if "request method=" in record.getMessage()
    ]
    assert matches
    message = matches[-1]
    assert "method=GET" in message
    assert "path=/health" in message
    assert "status=200" in message
    assert "request_id=req-log-1" in message


def test_sensitive_headers_and_query_are_not_logged(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="app.http"):
        response = client.get(
            f"/health?api_key={API_KEY_SENTINEL}",
            headers={
                "Authorization": f"Bearer {API_KEY_SENTINEL}",
                "Cookie": f"session={DB_SENTINEL}",
            },
        )
    assert response.status_code == 200
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "path=/health" in logged
    assert "?" not in logged
    assert API_KEY_SENTINEL not in logged
    assert DB_SENTINEL not in logged
    assert "Authorization" not in logged
    assert "Cookie" not in logged


def test_unexpected_exception_is_a_safe_response(caplog: pytest.LogCaptureFixture) -> None:
    application = create_app()

    @application.get("/__boom")
    def _boom() -> None:
        raise RuntimeError(
            f"{API_KEY_SENTINEL} {DB_SENTINEL} C:/secret/reconai.pdf postgresql://user:secret@db/app"
        )

    with caplog.at_level(logging.ERROR, logger="app.http"):
        response = TestClient(application, raise_server_exceptions=False).get(
            "/__boom",
            headers={REQUEST_ID_HEADER: "err-req-9"},
        )

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == "err-req-9"
    assert response.json() == {
        "detail": "Internal server error",
        "request_id": "err-req-9",
    }
    body = response.text
    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert API_KEY_SENTINEL not in body
    assert DB_SENTINEL not in body
    assert "C:/secret" not in body
    assert "postgresql://" not in body
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "application_error request_id=err-req-9" in logged
    assert API_KEY_SENTINEL not in logged
    assert DB_SENTINEL not in logged
    assert "C:/secret" not in logged
    assert "postgresql://" not in logged
    assert "Traceback" not in logged


def test_business_not_found_keeps_its_status(client: TestClient) -> None:
    response = client.get(f"/documents/{uuid4()}")
    assert response.status_code == 404
    assert isinstance(response.json()["detail"], str)
    assert "request_id" not in response.json()


def test_provider_failure_logs_category_only(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(
        _env_file=None,
        gemini_api_key="synthetic-not-used",
        llm_max_retries=0,
    )

    class _BoomModels:
        @staticmethod
        def generate_content(**_kwargs: object) -> None:
            raise TimeoutError(f"timeout {API_KEY_SENTINEL} prompt secret text")

        @staticmethod
        def embed_content(**_kwargs: object) -> None:
            raise TimeoutError(f"timeout {DB_SENTINEL} document text")

    class _BoomClient:
        models = _BoomModels()

    provider = GeminiProvider(settings)
    provider._client = _BoomClient()
    with (
        caplog.at_level(logging.WARNING, logger="app.http"),
        pytest.raises(Exception, match="Gemini timed out"),
    ):
        provider.generate_structured(
            system_instruction="do not log this prompt",
            user_content="do not log this document",
            response_model=GeminiExtractionOutput,
        )
    embedder = GeminiEmbeddingProvider(settings)
    embedder._client = _BoomClient()
    with (
        caplog.at_level(logging.WARNING, logger="app.http"),
        pytest.raises(Exception, match="Gemini timed out"),
    ):
        embedder.embed_text("vendor invoice text that must stay out of logs")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "provider_failure category=TIMEOUT" in logged
    assert API_KEY_SENTINEL not in logged
    assert DB_SENTINEL not in logged
    assert "do not log this prompt" not in logged
    assert "vendor invoice text" not in logged
