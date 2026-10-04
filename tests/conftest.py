"""Test setup: SQLite database, fakeredis, LLM disabled (rule-engine path)."""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="suraksha-test-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_tmp}/test.db",
    UPLOAD_DIR=f"{_tmp}/uploads",
    KNOWLEDGE_UPLOAD_DIR=f"{_tmp}/knowledge",
    RATE_LIMIT_ENABLED="false",
    LLM_ENABLED="false",
    VOICE_ENABLED="false",
    REDIS_URL="redis://127.0.0.1:1/0",
    OLLAMA_BASE_URL="http://127.0.0.1:1",
    CHROMA_HOST="127.0.0.1",
    CHROMA_PORT="1",
    LOG_JSON="false",
    SECRET_KEY="test-secret-key-0123456789abcdef0123456789",
)

import fakeredis  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.utils import cache  # noqa: E402

cache._client = fakeredis.FakeRedis(decode_responses=True)

from backend.database.base import Base  # noqa: E402
from backend.database.session import engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.seed.seed import seed_courses  # noqa: E402

Base.metadata.create_all(engine)
seed_courses()


OUTBOX: list[dict] = []


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
    """Capture outgoing email instead of talking to SMTP / Celery."""
    from backend.services import email_service

    OUTBOX.clear()
    monkeypatch.setattr(
        email_service,
        "send_email",
        lambda to, subject, text, html_body=None: OUTBOX.append({"to": to, "subject": subject, "text": text}),
    )
    cache._client.flushall()  # reset email / OTP cooldowns between tests
    return OUTBOX


SMS_OUTBOX: list[dict] = []


@pytest.fixture(autouse=True)
def sms_outbox(monkeypatch):
    """Capture outgoing SMS instead of calling a gateway / Celery."""
    from backend.services import sms_service

    SMS_OUTBOX.clear()
    monkeypatch.setattr(
        sms_service,
        "send_sms",
        lambda to, text, purpose, variables=None: SMS_OUTBOX.append({"to": to, "text": text, "purpose": purpose}),
    )
    return SMS_OUTBOX


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _register(client, email, password="Passw0rd!x", name="Test User"):
    r = client.post("/auth/register", json={"name": name, "email": email, "password": password, "consent": True})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def auth(client):
    import uuid

    data = _register(client, f"user-{uuid.uuid4().hex[:8]}@example.com")
    return {"Authorization": f"Bearer {data['access_token']}"}, data


@pytest.fixture
def register(client):
    return lambda email, **kw: _register(client, email, **kw)
