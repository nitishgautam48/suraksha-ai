import re
import uuid
from datetime import UTC, datetime, timedelta

SCAM = "URGENT share your OTP now to claim guaranteed 5% daily returns, only 2 slots left"


def _h(data):
    return {"Authorization": f"Bearer {data['access_token']}"}


def test_preferences_defaults_and_update(client, register):
    h = _h(register(f"pref-{uuid.uuid4().hex[:6]}@example.com"))
    p = client.get("/me/preferences", headers=h).json()
    assert p["elder_mode"] is False and p["theme"] == "system" and p["auto_alert_family"] is False
    p = client.patch("/me/preferences", headers=h, json={"elder_mode": True, "theme": "contrast"}).json()
    assert p["elder_mode"] and p["text_scale"] == 1.2 and p["tts_autoplay"] and p["auto_alert_family"]
    assert client.patch("/me/preferences", headers=h, json={"text_scale": 3}).status_code == 422
    p = client.patch("/me/preferences", headers=h, json={"auto_alert_family": False}).json()
    assert p["elder_mode"] and p["auto_alert_family"] is False  # explicit choice wins


def test_senior_signup_turns_on_elder_mode(client, sms_outbox):
    client.post("/auth/phone/request-otp", json={"phone": "9820144130"})
    code = re.search(r"\b(\d{6})\b", sms_outbox[-1]["text"]).group(1)
    tok = client.post("/auth/phone/verify", json={"phone": "9820144130", "code": code, "user_type": "senior_citizen"}).json()
    assert client.get("/me/preferences", headers=_h(tok)).json()["elder_mode"] is True


def test_simple_verdict_and_elder_effects(client, register, sms_outbox):
    h = _h(register(f"elder-{uuid.uuid4().hex[:6]}@example.com", name="Kamala"))
    r = client.post("/analyze/message", headers=h, json={"message_text": SCAM}).json()
    v = r["simple_verdict"]
    assert v["level"] == "critical" and v["headline"].startswith("STOP") and v["call"]["tel"] == "tel:1930"
    assert v["elder_mode"] is False and len(r["safe_practices"]) > 3

    client.post("/contacts", headers=h, json={"name": "Rahul", "phone": "9820144120", "notify_contact": False})
    client.patch("/me/preferences", headers=h, json={"elder_mode": True})
    client.patch("/auth/me", headers=h, json={"language": "hi"})
    r = client.post("/analyze/message", headers=h, json={"message_text": SCAM}).json()
    v = r["simple_verdict"]
    assert v["elder_mode"] and v["call"]["tel"] == "tel:+919820144120" and "Rahul" in v["call"]["label"]
    assert "धोखाधड़ी" in v["headline"]  # Hindi
    assert len(r["safe_practices"]) <= 3
    assert any(s["purpose"] == "auto_alert" for s in sms_outbox)  # elder mode => family alerted

    benign = client.post("/scan/text", headers=h, json={"text": "Dinner at 8?"}).json()["simple_verdict"]
    assert benign["level"] == "low" and benign["call"] is None


def test_auto_delete_scans_after_24h(client, register):
    from backend.database.session import SessionLocal
    from backend.models import ScamAnalysis
    from backend.services.maintenance_service import purge_expired_scans

    keep_h = _h(register(f"keep-{uuid.uuid4().hex[:6]}@example.com"))
    del_h = _h(register(f"del-{uuid.uuid4().hex[:6]}@example.com"))
    client.patch("/me/preferences", headers=del_h, json={"auto_delete_scans": True})
    ids = [
        client.post("/analyze/message", headers=hh, json={"message_text": SCAM}).json()["analysis_id"] for hh in (keep_h, del_h)
    ]
    with SessionLocal() as db:
        for a in db.query(ScamAnalysis).filter(ScamAnalysis.id.in_([uuid.UUID(i) for i in ids])):
            a.created_at = datetime.now(UTC) - timedelta(hours=25)
        db.commit()
        purge_expired_scans(db)
        remaining = {str(a.id) for a in db.query(ScamAnalysis).filter(ScamAnalysis.id.in_([uuid.UUID(i) for i in ids]))}
    assert remaining == {ids[0]}


def test_weekly_report_and_nudges_respect_preferences(client, register, outbox):
    from backend.database.session import SessionLocal
    from backend.services.maintenance_service import send_daily_nudges, send_weekly_reports

    on = register(f"weekly-{uuid.uuid4().hex[:6]}@example.com")
    off = register(f"noweekly-{uuid.uuid4().hex[:6]}@example.com")
    client.patch("/me/preferences", headers=_h(off), json={"weekly_report": False, "notify_learning": False})
    outbox.clear()
    with SessionLocal() as db:
        send_weekly_reports(db)
        send_daily_nudges(db)
    recipients = {m["to"] for m in outbox}
    assert on["user"]["email"] in recipients and off["user"]["email"] not in recipients
    assert "safety score" in next(m for m in outbox if m["to"] == on["user"]["email"])["text"]
    assert client.get("/alerts", headers=_h(off)).json()["total"] == 0
    assert any(a["alert_type"] == "habit_nudge" for a in client.get("/alerts", headers=_h(on)).json()["items"])
