import re

import pytest

from backend.utils.phone import InvalidPhone, normalize_phone


@pytest.mark.parametrize(
    "raw", ["9820144120", "98201 44120", "+91 98201-44120", "09820144120", "919820144120", "0091 9820144120"]
)
def test_normalize_indian_numbers(raw):
    assert normalize_phone(raw) == "+919820144120"


@pytest.mark.parametrize("raw", ["12345", "5820144120", "+91 1234567890", "abc", "+0123"])
def test_invalid_numbers(raw):
    with pytest.raises(InvalidPhone):
        normalize_phone(raw)


def _code(sms):
    return re.search(r"\b(\d{6})\b", sms[-1]["text"]).group(1)


def test_phone_signup_then_login(client, sms_outbox):
    r = client.post("/auth/phone/request-otp", json={"phone": "98201 44121", "language": "hi"})
    assert r.status_code == 202 and "4121" in r.json()["detail"] and "98201" not in r.json()["detail"]
    assert sms_outbox[-1]["to"] == "+919820144121" and "Suraksha AI" in sms_outbox[-1]["text"]
    assert "कोड" in sms_outbox[-1]["text"]  # Hindi template
    r = client.post(
        "/auth/phone/verify",
        json={
            "phone": "9820144121",
            "code": _code(sms_outbox),
            "name": "Rajendra",
            "city": "Pune",
            "state": "Maharashtra",
            "user_type": "senior_citizen",
            "language": "mr",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_new_user"] is True
    assert body["user"]["phone"] == "+919820144121" and body["user"]["phone_verified"]
    assert (
        body["user"]["email"] is None
        and body["user"]["city"] == "Pune"
        and body["user"]["state"] == "Maharashtra"
        and body["user"]["language"] == "mr"
    )

    from backend.utils import cache

    cache._client.flushall()  # skip the resend cooldown
    client.post("/auth/phone/request-otp", json={"phone": "+919820144121"})
    r = client.post("/auth/phone/verify", json={"phone": "+919820144121", "code": _code(sms_outbox)})
    assert r.status_code == 200 and r.json()["is_new_user"] is False and r.json()["user"]["name"] == "Rajendra"


def test_wrong_codes_lock_out(client, sms_outbox):
    client.post("/auth/phone/request-otp", json={"phone": "9820144122"})
    good = _code(sms_outbox)
    bad = "000000" if good != "000000" else "111111"
    for left in (4, 3, 2, 1):
        r = client.post("/auth/phone/verify", json={"phone": "9820144122", "code": bad})
        assert r.status_code == 400 and f"{left} attempt" in r.json()["detail"]
    r = client.post("/auth/phone/verify", json={"phone": "9820144122", "code": bad})
    assert "Too many" in r.json()["detail"]
    # even the right code no longer works
    assert client.post("/auth/phone/verify", json={"phone": "9820144122", "code": good}).status_code == 400


def test_resend_cooldown(client, sms_outbox):
    assert client.post("/auth/phone/request-otp", json={"phone": "9820144123"}).status_code == 202
    assert client.post("/auth/phone/request-otp", json={"phone": "9820144123"}).status_code == 429
    assert len(sms_outbox) == 1


def test_invalid_phone_rejected(client):
    assert client.post("/auth/phone/request-otp", json={"phone": "1234567890"}).status_code == 422


def test_otp_fails_closed_without_redis(client, monkeypatch):
    from backend.services import otp_service

    class Down:
        def ping(self):
            raise ConnectionError("redis down")

    monkeypatch.setattr(otp_service, "get_redis", lambda: Down())
    assert client.post("/auth/phone/request-otp", json={"phone": "9820144124"}).status_code == 503


def test_link_phone_and_conflict(client, register, sms_outbox, outbox):
    a = register("linker@example.com")
    h = {"Authorization": f"Bearer {a['access_token']}"}
    assert client.post("/auth/phone/link/request", headers=h, json={"phone": "9820144125"}).status_code == 202
    r = client.post("/auth/phone/link/confirm", headers=h, json={"phone": "9820144125", "code": _code(sms_outbox)})
    assert r.status_code == 200 and r.json()["phone"] == "+919820144125"
    # the linked number now logs into the same account
    from backend.utils import cache

    cache._client.flushall()
    client.post("/auth/phone/request-otp", json={"phone": "9820144125"})
    r = client.post("/auth/phone/verify", json={"phone": "9820144125", "code": _code(sms_outbox)})
    assert r.json()["user"]["email"] == "linker@example.com" and r.json()["is_new_user"] is False

    b = register("other-linker@example.com")
    hb = {"Authorization": f"Bearer {b['access_token']}"}
    cache._client.flushall()
    client.post("/auth/phone/link/request", headers=hb, json={"phone": "9820144125"})
    r = client.post("/auth/phone/link/confirm", headers=hb, json={"phone": "9820144125", "code": _code(sms_outbox)})
    assert r.status_code == 409


def test_phone_user_adds_email(client, sms_outbox, outbox):
    client.post("/auth/phone/request-otp", json={"phone": "9820144126"})
    tok = client.post("/auth/phone/verify", json={"phone": "9820144126", "code": _code(sms_outbox)}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.patch("/auth/me", headers=h, json={"email": "Phone.User@example.com", "user_type": "student"})
    assert r.status_code == 200 and r.json()["email"] == "phone.user@example.com" and not r.json()["email_verified"]
    assert outbox and outbox[-1]["to"] == "phone.user@example.com"


def test_sms_providers_dispatch(monkeypatch):
    from backend.config import settings
    from backend.services import sms_service

    calls = []

    class Resp:
        def raise_for_status(self):
            pass

    monkeypatch.setattr(sms_service.httpx, "post", lambda url, **kw: calls.append((url, kw)) or Resp())
    monkeypatch.setattr(settings, "SMS_PROVIDER", "webhook")
    monkeypatch.setattr(settings, "SMS_WEBHOOK_URL", "https://gw.example/send")
    sms_service.send_sms_now("+919820144120", "hi", "otp_login", {"otp": "123456"})
    assert calls[-1][0] == "https://gw.example/send" and calls[-1][1]["json"]["otp"] == "123456"
    monkeypatch.setattr(settings, "SMS_PROVIDER", "fast2sms")
    sms_service.send_sms_now("+919820144120", "hi", "otp_login", {"otp": "123456"})
    assert calls[-1][1]["json"] == {"route": "otp", "variables_values": "123456", "numbers": "9820144120"}
    monkeypatch.setattr(settings, "SMS_PROVIDER", "nope")
    with pytest.raises(sms_service.SMSError):
        sms_service.send_sms_now("+919820144120", "hi", "otp_login")
