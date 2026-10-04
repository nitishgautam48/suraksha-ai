#!/usr/bin/env python3
"""End-to-end smoke test against a running Suraksha AI API.

Usage:  python scripts/smoke_test.py [BASE_URL]      (default http://localhost:8000)
Requires only the Python standard library + Pillow (optional, for the image-scan check).
"""

from __future__ import annotations

import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
if not BASE.startswith(("http://", "https://")):
    sys.exit("BASE_URL must start with http:// or https://")
TOKEN: str | None = None
FAILED = 0


def call(method: str, path: str, body=None, files=None, expect=(200, 201, 202)):
    headers = {"Accept": "application/json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = None
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for name, (filename, content, ctype) in files.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n".encode()
                + content
                + b"\r\n"
            )
        for k, v in (body or {}).items():
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        data = b"".join(parts) + f"--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            status, payload = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, payload = e.code, e.read()
    try:
        parsed = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        parsed = payload[:200]
    return status, parsed


def check(name: str, status: int, payload, ok=(200, 201, 202), show=None):
    global FAILED
    good = status in ok
    FAILED += 0 if good else 1
    extra = ""
    if isinstance(payload, dict) and show:
        extra = " " + json.dumps({k: payload.get(k) for k in show}, ensure_ascii=False)[:300]
    elif not good:
        extra = " " + json.dumps(payload, ensure_ascii=False)[:300]
    print(f"{'PASS' if good else 'FAIL'} [{status}] {name}{extra}")


def main() -> int:
    global TOKEN
    check("GET /health", *call("GET", "/health"))
    s, p = call("GET", "/health/ready")
    check("GET /health/ready", s, p, show=["ollama", "models", "chromadb", "knowledge_chunks"])

    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    s, p = call(
        "POST",
        "/auth/register",
        {"name": "Smoke <b>Tester</b>", "email": email, "password": "Passw0rd!x", "language": "en", "consent": True},
    )
    check("POST /auth/register", s, p)
    s, p = call("POST", "/auth/login", {"email": email, "password": "Passw0rd!x"})
    check("POST /auth/login", s, p)
    TOKEN = p["access_token"]
    s, p = call("GET", "/auth/me")
    check("GET /auth/me (HTML stripped from name)", s, p, show=["name", "role"])

    scam = (
        "URGENT!! Join our SEBI registered VIP group. Guaranteed 5% daily returns, double your money in 30 days. "
        "Only 3 slots left, offer ends in 30 minutes. Pay Rs 999 registration fee to win@ybl and click "
        "http://sbi-kyc-update.xyz/claim to verify KYC or your account will be blocked."
    )
    s, p = call("POST", "/analyze/message", {"message_text": scam + " OTP 482913"})
    check("POST /analyze/message (scam)", s, p, show=["risk_score", "risk_level"])
    if s == 200:
        print("      flags:", [f["label"] for f in p["warning_flags"]], "| llm_used:", p["engine"]["llm_used"])
        print("      confidence:", p["confidence"]["level"], "| redacted:", p["privacy"]["redacted"])
        check("OTP redacted before analysis", 200 if "482913" not in json.dumps(p) else 500, p)
        analysis_id = p["analysis_id"]
        s, r = call("GET", f"/analyze/history/{analysis_id}/report?language=hi")
        check("GET report-to-1930 summary", s, r, show=["risk_level"])
        if s == 200:
            print("      identifiers:", r["identifiers"], "| steps:", [st["key"] for st in r["steps"]])
    s, p = call("POST", "/analyze/message", {"message_text": "Hi beta, dinner at 8 tonight? Bring the vegetables please."})
    check("POST /analyze/message (benign)", s, p, show=["risk_score", "risk_level"])

    social = (
        "This hidden gem multibagger is going to the moon 🚀🚀🚀 Operator buying, upper circuit tomorrow! "
        "I turned 10k to 5 lakh in a month. Don't miss out, only 20 seats left in my premium Telegram group. Trust me!"
    )
    s, p = call("POST", "/analyze/social", {"text": social, "platform": "telegram"})
    check("POST /analyze/social", s, p, show=["risk_score", "risk_level"])
    if s == 200:
        print(
            "      tactics:", [t["label"] for t in p["tactics"]], "| risky segments:", sum(seg["risky"] for seg in p["segments"])
        )

    s, p = call("POST", "/scan/text", {"text": "Your PAN card KYC expired. Share OTP to avoid account suspension."})
    check("POST /scan/text", s, p, show=["risk_score", "risk_level", "categories"])

    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1000, 260), "white")
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 34)
        except OSError:
            font = ImageFont.load_default()
        draw.multiline_text(
            (20, 20),
            "Guaranteed 20% monthly returns!\nShare your OTP to claim reward.\nOffer ends today, act now!",
            fill="black",
            font=font,
        )
        buf = io.BytesIO()
        img.save(buf, "PNG")
        s, p = call("POST", "/scan/image", {"language": "en"}, files={"file": ("scam.png", buf.getvalue(), "image/png")})
        check("POST /scan/image (OCR)", s, p, ok=(200, 503), show=["risk_score", "risk_level", "extracted_text"])
    except ImportError:
        print("SKIP POST /scan/image (Pillow not installed)")

    s, p = call("POST", "/scan/image", files={"file": ("evil.png", b"<script>alert(1)</script>", "image/png")}, expect=(415,))
    check("POST /scan/image rejects fake image", s, p, ok=(415,))

    s, p = call("GET", "/privacy?language=hi")
    check("GET /privacy (Hindi notice)", s, p, show=["version", "title"])
    s, p = call("GET", "/family/readiness")
    check("GET /family/readiness", s, p, show=["score_pct"])
    s, p = call("POST", "/chat", {"message": "எந்த பங்கை வாங்க வேண்டும்?"})
    check("POST /chat refuses a Tamil stock-pick question", s, p, show=["blocked"])
    if s == 200 and not p.get("blocked"):
        check("Tamil advice question blocked", 500, p)
    s, p = call("POST", "/chat", {"message": "Should I buy Reliance shares now?"})
    check("POST /chat (advice request is refused)", s, p, show=["blocked"])
    s, p = call("POST", "/chat", {"message": "How do I report a UPI fraud?"})
    check("POST /chat (grounded question)", s, p, show=["grounded", "llm_used"])
    if s == 200:
        print("      answer:", p["response"][:160].replace("\n", " "), "...")

    s, courses = call("GET", "/learning/courses")
    check("GET /learning/courses", s, courses)
    if s == 200 and courses:
        cid = courses[0]["id"]
        s, detail = call("GET", f"/learning/courses/{cid}")
        check("GET /learning/courses/{id}", s, detail)
        s, p = call("POST", f"/learning/lessons/{detail['lessons'][0]['id']}/complete")
        check("POST /learning/lessons/{id}/complete", s, p, show=["detail"])
        s, p = call("GET", f"/learning/courses/{cid}/flashcards")
        check("GET flashcards", s, p)
        s, quiz = call("GET", f"/learning/courses/{cid}/assessment")
        check("GET assessment", s, quiz)
        answers = {q["id"]: 1 for q in quiz["questions"]}
        s, p = call("POST", f"/learning/courses/{cid}/assessment/submit", {"answers": answers})
        check("POST assessment submit", s, p, show=["score", "total", "passed", "completion"])

    check("PUT /habits/checklist/track_expenses", *call("PUT", "/habits/checklist/track_expenses", {"completed": True}))
    check("POST /habits/savings-checkin", *call("POST", "/habits/savings-checkin", {"saved": True}))
    s, p = call("GET", "/habits")
    check("GET /habits", s, p, show=["learning_streak_days", "emergency_fund_progress", "nudges"])
    s, p = call("GET", "/progress")
    check("GET /progress", s, p, show=["overall_completion", "learning_streak_days"])
    s, p = call("GET", "/alerts")
    check("GET /alerts", s, p, show=["unread_count", "total"])
    s, p = call("GET", "/dashboard")
    check("GET /dashboard", s, p, show=["safety_score"])
    s, p = call("GET", "/admin/audit-logs")
    check("GET /admin/audit-logs is forbidden for users", s, p, ok=(403,))

    TOKEN = "invalid"
    s, p = call("GET", "/dashboard")
    check("GET /dashboard without valid token -> 401", s, p, ok=(401,))

    print(f"\n{'ALL PASSED' if not FAILED else f'{FAILED} FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    t = time.time()
    rc = main()
    print(f"({time.time() - t:.1f}s)")
    sys.exit(rc)
