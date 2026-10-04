import re
import time

import pytest

from backend.config import settings

PW = "Passw0rd!x"


def _token(mail) -> str:
    m = re.search(r"token=([\w\-%]+)", mail["text"])
    assert m, mail["text"]
    return m.group(1)


def _login(client, email, password=PW):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_register_sends_verification_and_confirm(client, register, outbox):
    data = register("verify@example.com")
    assert data["user"]["email_verified"] is False
    assert len(outbox) == 1 and outbox[0]["to"] == "verify@example.com"
    assert "/verify-email?token=" in outbox[0]["text"]
    r = client.post("/auth/verify-email/confirm", json={"token": _token(outbox[0])})
    assert r.status_code == 200 and r.json()["email_verified"] is True
    # single use
    assert client.post("/auth/verify-email/confirm", json={"token": _token(outbox[0])}).status_code == 400


def test_resend_is_enumeration_safe_and_rate_limited(client, register, outbox):
    register("resend@example.com")
    outbox.clear()
    a = client.post("/auth/verify-email/request", json={"email": "resend@example.com"})
    b = client.post("/auth/verify-email/request", json={"email": "ghost@example.com"})
    assert a.status_code == b.status_code == 202 and a.json() == b.json()
    assert outbox == []  # within the 60s cooldown after registration


def test_forgot_and_reset_password_signs_out_everywhere(client, register, outbox):
    data = register("reset@example.com")
    old = {"Authorization": f"Bearer {data['access_token']}"}
    outbox.clear()
    r = client.post("/auth/password/forgot", json={"email": "reset@example.com"})
    ghost = client.post("/auth/password/forgot", json={"email": "nobody-here@example.com"})
    assert r.status_code == ghost.status_code == 202 and r.json() == ghost.json()
    assert len(outbox) == 1 and "/reset-password?token=" in outbox[0]["text"]
    token = _token(outbox[0])

    time.sleep(1.1)  # tokens are second-granular; make the old session strictly older
    assert client.post("/auth/password/reset", json={"token": token, "new_password": "weak"}).status_code == 422
    r = client.post("/auth/password/reset", json={"token": token, "new_password": "N3wPassword!"})
    assert r.status_code == 200
    assert any("password was changed" in m["subject"] for m in outbox)
    assert client.get("/auth/me", headers=old).status_code == 401  # old access token rejected
    assert client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]}).status_code == 401
    assert _login(client, "reset@example.com").status_code == 401
    new = _login(client, "reset@example.com", "N3wPassword!")
    assert new.status_code == 200 and new.json()["user"]["email_verified"] is True
    # reset tokens are single use
    assert client.post("/auth/password/reset", json={"token": token, "new_password": "Another1Pass"}).status_code == 400


def test_new_reset_request_invalidates_previous_link(client, register, outbox, monkeypatch):
    from backend.services import auth_service

    monkeypatch.setattr(auth_service, "_cooldown_ok", lambda *a: True)
    register("twice@example.com")
    outbox.clear()
    client.post("/auth/password/forgot", json={"email": "twice@example.com"})
    client.post("/auth/password/forgot", json={"email": "twice@example.com"})
    first, second = _token(outbox[0]), _token(outbox[1])
    assert client.post("/auth/password/reset", json={"token": first, "new_password": "N3wPassword!"}).status_code == 400
    assert client.post("/auth/password/reset", json={"token": second, "new_password": "N3wPassword!"}).status_code == 200


def test_expired_reset_token_rejected(client, register, outbox):
    from datetime import UTC, datetime, timedelta

    from backend.database.session import SessionLocal
    from backend.models import AuthToken

    register("expired@example.com")
    outbox.clear()
    client.post("/auth/password/forgot", json={"email": "expired@example.com"})
    with SessionLocal() as db:
        for t in db.query(AuthToken).filter(AuthToken.purpose == "reset_password").all():
            t.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    r = client.post("/auth/password/reset", json={"token": _token(outbox[0]), "new_password": "N3wPassword!"})
    assert r.status_code == 400


def test_change_password(client, register, outbox):
    data = register("change@example.com")
    h = {"Authorization": f"Bearer {data['access_token']}"}
    bad = client.post("/auth/password/change", headers=h, json={"current_password": "wrong", "new_password": "N3wPassword!"})
    assert bad.status_code == 400
    time.sleep(1.1)
    r = client.post("/auth/password/change", headers=h, json={"current_password": PW, "new_password": "N3wPassword!"})
    assert r.status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401  # old session ended
    fresh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/auth/me", headers=fresh).status_code == 200


def test_require_email_verification(client, register, outbox, monkeypatch):
    monkeypatch.setattr(settings, "REQUIRE_EMAIL_VERIFICATION", True)
    register("strict@example.com")
    r = _login(client, "strict@example.com")
    assert r.status_code == 403 and "not verified" in r.json()["detail"]
    client.post("/auth/verify-email/confirm", json={"token": _token(outbox[0])})
    assert _login(client, "strict@example.com").status_code == 200


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_email_templates_render(lang):
    from backend.services.email_service import render

    subject, text, html = render("reset_password", lang, "http://x/reset-password?token=abc", name="<b>Asha</b>")
    assert subject and "token=abc" in text
    assert "<b>Asha</b>" not in html and "&lt;b&gt;Asha" in html  # names are escaped in HTML email


def test_google_signup_and_link(client, register, monkeypatch):
    from backend.services import auth_service

    monkeypatch.setattr(
        auth_service,
        "verify_google_token",
        lambda token: {"sub": "g-123", "email": "g.user@example.com", "name": "G User", "email_verified": True},
    )
    r = client.post("/auth/google", json={"id_token": "x" * 30})
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email_verified"] is True and r.json()["user"]["auth_provider"] == "google"
    # second login reuses the same account
    assert client.post("/auth/google", json={"id_token": "x" * 30}).json()["user"]["id"] == r.json()["user"]["id"]
    # an existing password account with the same email gets linked and marked verified
    register("linked.google@example.com")
    monkeypatch.setattr(
        auth_service,
        "verify_google_token",
        lambda token: {"sub": "g-456", "email": "linked.google@example.com", "email_verified": True},
    )
    r = client.post("/auth/google", json={"id_token": "y" * 30})
    assert r.status_code == 200 and r.json()["user"]["email_verified"] is True
