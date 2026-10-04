import io

from PIL import Image


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "x-request-id" in r.headers


def test_register_login_and_duplicate(client, register):
    register("dup@example.com")
    r = client.post("/auth/register", json={"name": "X", "email": "DUP@example.com", "password": "Passw0rd!x"})
    assert r.status_code == 409
    r = client.post("/auth/login", json={"email": "dup@example.com", "password": "wrong-pass1"})
    assert r.status_code == 401
    r = client.post("/auth/login", json={"email": "dup@example.com", "password": "Passw0rd!x"})
    assert r.status_code == 200 and r.json()["token_type"] == "bearer"


def test_weak_password_rejected(client):
    r = client.post("/auth/register", json={"name": "X", "email": "weak@example.com", "password": "password"})
    assert r.status_code == 422


def test_xss_stripped_from_name(client, register):
    data = register("xss@example.com", name="<script>alert(1)</script>Asha")
    assert data["user"]["name"] == "Asha"


def test_auth_required(client):
    assert client.get("/dashboard").status_code == 401
    assert client.get("/dashboard", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_refresh_and_logout_revokes(client, register):
    data = register("logout@example.com")
    h = {"Authorization": f"Bearer {data['access_token']}"}
    r = client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert r.status_code == 200
    # the used refresh token is revoked
    assert client.post("/auth/refresh", json={"refresh_token": data["refresh_token"]}).status_code == 401
    assert client.post("/auth/logout", headers=h).status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 401


def test_message_analyzer(client, auth):
    h, _ = auth
    r = client.post(
        "/analyze/message",
        headers=h,
        json={"message_text": "Guaranteed 10% monthly returns, SEBI approved. Join now, only 2 slots left! http://bit.ly/x"},
    )
    body = r.json()
    assert r.status_code == 200
    assert body["risk_level"] in ("high", "critical")
    labels = {f["label"] for f in body["warning_flags"]}
    assert "Guaranteed returns" in labels
    assert body["disclaimer"]
    alerts = client.get("/alerts", headers=h).json()
    assert alerts["unread_count"] >= 1


def test_social_analyzer(client, auth):
    h, _ = auth
    r = client.post(
        "/analyze/social", headers=h, json={"text": "Multibagger to the moon 🚀🚀 Don't miss out!", "platform": "instagram"}
    )
    assert r.status_code == 200
    assert any(s["risky"] for s in r.json()["segments"])


def test_scan_text(client, auth):
    h, _ = auth
    r = client.post("/scan/text", headers=h, json={"text": "Share your UPI PIN to receive the refund"})
    assert r.status_code == 200
    assert "phishing" in r.json()["categories"]


def test_upload_validation(client, auth):
    h, _ = auth
    r = client.post("/scan/image", headers=h, files={"file": ("x.png", b"<script>alert(1)</script>", "image/png")})
    assert r.status_code == 415
    r = client.post("/scan/image", headers=h, files={"file": ("x.exe", b"MZ\x90\x00", "application/octet-stream")})
    assert r.status_code == 415
    r = client.post("/scan/pdf", headers=h, files={"file": ("x.pdf", b"%PDF-1.4 garbage", "application/pdf")})
    assert r.status_code == 400


def test_image_upload_accepted(client, auth, monkeypatch):
    from backend.ocr import tesseract
    from backend.ocr.tesseract import OCRResult

    monkeypatch.setattr(
        "backend.services.scan_service.ocr_image",
        lambda data, language=None: OCRResult("Guaranteed returns! Share OTP now", 1, "tesseract", "eng"),
    )
    assert tesseract  # imported for monkeypatch target resolution
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), "white").save(buf, "PNG")
    h, _ = auth
    r = client.post("/scan/image", headers=h, files={"file": ("s.png", buf.getvalue(), "image/png")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_id"] and body["ocr"]["method"] == "tesseract"
    assert body["risk_level"] in ("high", "critical")


def test_chat_refuses_advice(client, auth):
    h, _ = auth
    r = client.post("/chat", headers=h, json={"message": "Which stock should I buy today?"})
    assert r.status_code == 200 and r.json()["blocked"] is True
    r = client.post("/chat", headers=h, json={"message": "How do I spot a phishing link?"})
    assert r.status_code == 200 and r.json()["blocked"] is False
    assert len(client.get("/chat/history", headers=h).json()) == 2


def test_learning_flow_and_progress(client, auth):
    h, _ = auth
    courses = client.get("/learning/courses", headers=h).json()
    assert len(courses) == 4
    cid = courses[0]["id"]
    detail = client.get(f"/learning/courses/{cid}", headers=h).json()
    for lesson in detail["lessons"]:
        assert client.post(f"/learning/lessons/{lesson['id']}/complete", headers=h).status_code == 200
    quiz = client.get(f"/learning/courses/{cid}/assessment", headers=h).json()["questions"]
    assert all("correct_index" not in q for q in quiz)
    r = client.post(f"/learning/courses/{cid}/assessment/submit", headers=h, json={"answers": {q["id"]: 1 for q in quiz}})
    assert r.status_code == 200
    progress = client.get("/progress", headers=h).json()
    assert progress["learning_streak_days"] == 1
    assert progress["courses"][0]["completion"] == 100.0


def test_habits(client, auth):
    h, _ = auth
    assert client.put("/habits/checklist/set_target", headers=h, json={"completed": True}).status_code == 200
    assert client.put("/habits/checklist/not_a_key", headers=h, json={"completed": True}).status_code == 404
    assert client.post("/habits/savings-checkin", headers=h, json={"saved": True}).status_code == 200
    body = client.get("/habits", headers=h).json()
    assert body["emergency_fund_progress"] > 0
    assert body["savings_discipline"] == 100.0
    assert body["nudges"]


def test_dashboard(client, auth):
    h, _ = auth
    client.post("/analyze/message", headers=h, json={"message_text": "Share OTP to claim your prize"})
    d = client.get("/dashboard", headers=h).json()
    assert 0 <= d["safety_score"]["score"] <= 100
    assert d["scam_detection_history"]["total_scans"] == 1
    assert len(d["awareness_trend"]) == 8


def test_rbac(client, auth, register):
    h, _ = auth
    assert client.get("/admin/audit-logs", headers=h).status_code == 403
    r = client.post("/learning/generate", headers=h, json={"topic": "upi_frauds", "kind": "lesson", "save_to_course": True})
    assert r.status_code == 403


def test_admin_can_read_audit_logs(client, register):
    from backend.database.session import SessionLocal
    from backend.models import User

    data = register("admin-test@example.com")
    with SessionLocal() as db:
        u = db.get(User, __import__("uuid").UUID(data["user"]["id"]))
        u.role = "admin"
        db.commit()
    token = client.post("/auth/login", json={"email": "admin-test@example.com", "password": "Passw0rd!x"}).json()["access_token"]
    r = client.get("/admin/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert any(row["action"] == "auth.login" for row in r.json())


def test_export_and_delete_account(client, register):
    data = register("delete-me@example.com")
    h = {"Authorization": f"Bearer {data['access_token']}"}
    assert client.get("/me/export", headers=h).status_code == 200
    assert client.delete("/auth/me", headers=h).status_code == 200
    assert client.post("/auth/login", json={"email": "delete-me@example.com", "password": "Passw0rd!x"}).status_code == 401


def test_metrics_endpoint(client, auth, monkeypatch):
    from backend.config import settings

    h, _ = auth
    client.post("/analyze/message", headers=h, json={"message_text": "Share your OTP now"})
    body = client.get("/metrics").text
    assert 'suraksha_http_requests_total{method="POST",route="/analyze/message",status="200"}' in body
    assert "suraksha_analyses_total" in body
    monkeypatch.setattr(settings, "METRICS_TOKEN", "s3cret")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_emergency_fund_goal_and_trackers(client, auth):
    h, _ = auth
    t = {x["key"]: x for x in client.get("/habits", headers=h).json()["trackers"]}
    assert t["emergency_fund"]["sub"].endswith("steps") and len(t) == 4
    ef = client.put("/habits/emergency-fund", headers=h, json={"target": 50000, "saved": 31000}).json()
    assert ef == {"target": 50000, "saved": 31000, "pct": 62.0}
    t = {x["key"]: x for x in client.get("/habits", headers=h).json()["trackers"]}
    assert t["emergency_fund"]["value"] == 62.0 and t["emergency_fund"]["sub"] == "₹31,000 of ₹50,000"
    assert client.put("/habits/emergency-fund", headers=h, json={"saved": -5}).status_code == 422
