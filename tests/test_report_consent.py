"""Consent before processing, the privacy notice, the report-to-1930 flow and impact metrics."""

import uuid

import pytest

from backend import i18n


def test_content_endpoints_require_consent(client):
    email = f"noconsent-{uuid.uuid4().hex[:6]}@example.com"
    r = client.post("/auth/register", json={"name": "No Consent", "email": email, "password": "Passw0rd!x"})
    assert r.status_code == 201
    assert r.json()["user"]["consent_version"] is None
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}

    blocked = client.post("/analyze/message", headers=h, json={"message_text": "hello"})
    assert blocked.status_code == 428
    assert blocked.json()["detail"]["code"] == "consent_required"
    assert client.post("/chat", headers=h, json={"message": "hi"}).status_code == 428
    assert client.get("/contacts", headers=h).status_code == 428
    # own data stays reachable without consent
    assert client.get("/me/export", headers=h).status_code == 200

    ok = client.post("/me/consent", headers=h)
    assert ok.status_code == 200 and ok.json()["consent_version"]
    assert client.post("/analyze/message", headers=h, json={"message_text": "hello"}).status_code == 200


def test_stale_consent_version_rejected(client, auth):
    h, _ = auth
    assert client.post("/me/consent", headers=h, params={"version": "1999-01"}).status_code == 409


@pytest.mark.parametrize("lang", list(i18n.LANGUAGES))
def test_privacy_notice_in_every_language(client, lang):
    r = client.get("/privacy", params={"language": lang})
    assert r.status_code == 200
    body = r.json()
    assert body["version"] and len(body["points"]) == 9 and body["consent_label"]
    assert "{" not in "".join(body["points"])  # retention days filled in
    if lang != "en":
        assert body["points"][1] != client.get("/privacy").json()["points"][1]


def test_report_flow_builds_summary_and_marks_reported(client, auth):
    h, _ = auth
    msg = (
        "Congratulations! Guaranteed 10% daily returns. Join now, pay Rs 999 to win@ybl or call 9876543210. "
        "Visit http://bit.ly/rich-fast . Share OTP 123456 to activate"
    )
    a = client.post("/analyze/message", headers=h, json={"message_text": msg, "language": "hi"}).json()
    assert a["risk_level"] in ("high", "critical")

    rep = client.get(f"/analyze/history/{a['analysis_id']}/report", headers=h, params={"language": "hi"})
    assert rep.status_code == 200, rep.text
    body = rep.json()
    assert body["summary_language"] == "en"
    assert "win@ybl" in body["identifiers"]["upi_ids"]
    assert any("9876543210" in p for p in body["identifiers"]["phones"])
    assert body["identifiers"]["links"]
    assert "123456" not in body["summary"] and "••••" in body["summary"]
    keys = [s["key"] for s in body["steps"]]
    assert keys[0] == "report_step_1930" and "report_step_portal" in keys and "report_step_sebi" in keys
    assert body["steps"][0]["tel"] == "tel:1930"
    assert body["title"] == i18n.t("report_title", "hi")

    first = client.post(f"/analyze/history/{a['analysis_id']}/reported", headers=h).json()["reported_at"]
    again = client.post(f"/analyze/history/{a['analysis_id']}/reported", headers=h).json()["reported_at"]
    assert first and first[:26] == again[:26]  # idempotent, XP granted once (SQLite drops the tz)


def test_report_is_private_to_owner(client, auth, register):
    h, _ = auth
    a = client.post("/analyze/message", headers=h, json={"message_text": "Share your OTP now"}).json()
    other = register(f"other-{uuid.uuid4().hex[:6]}@example.com")
    oh = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/analyze/history/{a['analysis_id']}/report", headers=oh).status_code == 404


def test_impact_metrics_are_admin_only_and_anonymous(client, auth, register):
    h, _ = auth
    assert client.get("/admin/impact", headers=h).status_code == 403

    from backend.database.session import SessionLocal
    from backend.models import User

    email = f"admin-{uuid.uuid4().hex[:6]}@example.com"
    data = register(email)
    with SessionLocal() as db:
        db.get(User, uuid.UUID(data["user"]["id"])).role = "admin"
        db.commit()
    ah = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.get("/admin/impact", headers=ah)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"checks_total", "high_risk_flagged", "reports_started", "family_alerts", "users_by_language"} <= set(body)
    assert "@" not in str(body)
