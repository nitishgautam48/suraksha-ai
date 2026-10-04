import pytest


@pytest.fixture
def user_h(client, register):
    data = register(f"fam-{__import__('uuid').uuid4().hex[:6]}@example.com", name="Rajendra Patil")
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_contacts_crud_and_primary(client, user_h, sms_outbox):
    r = client.post("/contacts", headers=user_h, json={"name": "Rahul Kulkarni", "relationship": "son", "phone": "98201 44120"})
    assert r.status_code == 201 and r.json()["is_primary"] is True and r.json()["phone"] == "+919820144120"
    assert sms_outbox[-1]["purpose"] == "contact_added" and "Rajendra Patil" in sms_outbox[-1]["text"]
    rahul = r.json()["id"]
    anita = client.post(
        "/contacts",
        headers=user_h,
        json={"name": "Anita", "relationship": "daughter", "phone": "9930018842", "email": "anita@example.com"},
    ).json()
    assert anita["is_primary"] is False
    assert client.post("/contacts", headers=user_h, json={"name": "Dup", "phone": "+91 98201 44120"}).status_code == 409
    client.patch(f"/contacts/{anita['id']}", headers=user_h, json={"is_primary": True})
    contacts = client.get("/contacts", headers=user_h).json()
    assert [c["name"] for c in contacts if c["is_primary"]] == ["Anita"]
    client.delete(f"/contacts/{anita['id']}", headers=user_h)
    contacts = client.get("/contacts", headers=user_h).json()
    assert len(contacts) == 1 and contacts[0]["id"] == rahul and contacts[0]["is_primary"]


def test_max_contacts(client, user_h):
    for i in range(5):
        assert (
            client.post(
                "/contacts", headers=user_h, json={"name": f"C{i}", "phone": f"98200000{i}0", "notify_contact": False}
            ).status_code
            == 201
        )
    assert client.post("/contacts", headers=user_h, json={"name": "C6", "phone": "9820000099"}).status_code == 400


def test_help_alert_flow(client, user_h, sms_outbox, outbox):
    assert client.post("/help/alert", headers=user_h, json={}).status_code == 400  # no contacts yet
    client.post(
        "/contacts",
        headers=user_h,
        json={
            "name": "Rahul",
            "relationship": "son",
            "phone": "9820144120",
            "email": "rahul@example.com",
            "notify_contact": False,
        },
    )
    r = client.post(
        "/help/alert",
        headers=user_h,
        json={"note": "Someone on video call says I am arrested", "location": {"lat": 18.5204, "lon": 73.8567}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["call"]["tel"] == "tel:+919820144120" and body["helplines"][0]["number"] == "1930"
    sms = sms_outbox[-1]
    assert sms["purpose"] == "help_alert" and "maps.google.com/?q=18.52040,73.85670" in sms["text"] and "1930" in sms["text"]
    assert outbox[-1]["to"] == "rahul@example.com"
    alerts = client.get("/alerts", headers=user_h).json()["items"]
    assert alerts[0]["alert_type"] == "family_alert"
    assert len(client.get("/help/history", headers=user_h).json()) == 1
    client.post("/help/alert", headers=user_h, json={})
    client.post("/help/alert", headers=user_h, json={})
    assert client.post("/help/alert", headers=user_h, json={}).status_code == 429  # 3 per 10 minutes


def test_auto_alert_on_critical_scan_when_opted_in(client, user_h, sms_outbox):
    from backend.utils import cache

    client.post("/contacts", headers=user_h, json={"name": "Rahul", "phone": "9820144120", "notify_contact": False})
    scam = "URGENT: share your OTP now to claim guaranteed 5% daily returns, only 2 slots left, pay fee to claim prize"
    client.post("/analyze/message", headers=user_h, json={"message_text": scam})
    assert not [s for s in sms_outbox if s["purpose"] == "auto_alert"]  # not opted in
    from backend.database.session import SessionLocal
    from backend.models import User
    from backend.services import preferences

    me = client.get("/auth/me", headers=user_h).json()
    with SessionLocal() as db:
        u = db.get(User, __import__("uuid").UUID(me["id"]))
        preferences.update(u, {"auto_alert_family": True})
        db.commit()
    cache._client.flushall()
    r = client.post("/analyze/message", headers=user_h, json={"message_text": scam})
    assert r.json()["risk_level"] == "critical"
    auto = [s for s in sms_outbox if s["purpose"] == "auto_alert"]
    assert len(auto) == 1 and scam[:20] not in auto[0]["text"]  # message content never shared
    client.post("/analyze/message", headers=user_h, json={"message_text": scam})
    assert len([s for s in sms_outbox if s["purpose"] == "auto_alert"]) == 1  # 6-hour throttle
