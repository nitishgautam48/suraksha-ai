"""Quality gate: the rule engine must keep catching scams without flagging genuine messages.

Thresholds sit a little below today's measured results so that genuine regressions fail CI while
small dataset additions don't. Update them deliberately when the dataset grows.
"""

import json

import pytest

from backend.ai.eval import evaluate as ev
from backend.config import settings


@pytest.fixture(scope="module", params=["tune", "holdout"])
def scored(request):
    return request.param, ev.score_rows(ev.load(split=request.param))


def test_warning_level_quality(scored):
    split, rows = scored
    m = ev.metrics_at(rows, settings.RISK_MEDIUM_THRESHOLD)
    assert m["precision"] >= 0.95, (split, m, ev.errors(rows, settings.RISK_MEDIUM_THRESHOLD))
    assert m["recall"] >= 0.90, (split, m, ev.errors(rows, settings.RISK_MEDIUM_THRESHOLD))


def test_no_legit_message_reaches_high(scored):
    split, rows = scored
    assert ev.metrics_at(rows, settings.RISK_HIGH_THRESHOLD)["fp"] == 0, split


def test_every_category_detected():
    rows = ev.score_rows(ev.load(split="all"))
    for cat, ratio in ev.category_recall(rows, settings.RISK_MEDIUM_THRESHOLD).items():
        hit, total = map(int, ratio.split("/"))
        assert hit / total >= 0.8, (cat, ratio)


def test_dataset_well_formed():
    rows = ev.load(split="all")
    assert len(rows) >= 120
    assert {r["label"] for r in rows} == {"scam", "legit"}
    assert {r["split"] for r in rows} == {"tune", "holdout"}
    assert all(r["text"].strip() for r in rows)
    assert len({r["text"] for r in rows}) == len(rows), "duplicate examples"


def test_feedback_flow_and_export(client, register):
    from backend.database.session import SessionLocal
    from backend.models import User

    user = register("fb-user@example.com")
    h = {"Authorization": f"Bearer {user['access_token']}"}
    benign = client.post("/analyze/message", headers=h, json={"message_text": "Lunch at 1pm tomorrow?"}).json()
    scam = client.post("/analyze/message", headers=h, json={"message_text": "Pay Rs 999 fee to claim your prize"}).json()
    # user says the benign-looking one was actually a scam (false negative) and shares the text
    r = client.post(
        f"/analyze/history/{benign['analysis_id']}/feedback",
        headers=h,
        json={"verdict": "scam", "comment": "<b>it was</b> a scam", "share_text": True},
    )
    assert r.status_code == 200 and r.json()["comment"] == "it was a scam"
    client.post(f"/analyze/history/{scam['analysis_id']}/feedback", headers=h, json={"verdict": "scam"})
    # updating feedback replaces it rather than duplicating
    client.post(f"/analyze/history/{benign['analysis_id']}/feedback", headers=h, json={"verdict": "scam", "share_text": True})

    other = {"Authorization": "Bearer " + register("fb-other@example.com")["access_token"]}
    assert (
        client.post(f"/analyze/history/{benign['analysis_id']}/feedback", headers=other, json={"verdict": "not_scam"}).status_code
        == 404
    )
    assert client.get("/admin/feedback", headers=h).status_code == 403

    admin = register("fb-admin@example.com")
    with SessionLocal() as db:
        db.get(User, __import__("uuid").UUID(admin["user"]["id"])).role = "admin"
        db.commit()
    tok = client.post("/auth/login", json={"email": "fb-admin@example.com", "password": "Passw0rd!x"}).json()["access_token"]
    ah = {"Authorization": f"Bearer {tok}"}
    rows = client.get("/admin/feedback?disagreements_only=true", headers=ah).json()
    assert [r["analysis_id"] for r in rows] == [benign["analysis_id"]] and rows[0]["disagrees"] is True
    export = client.get("/admin/feedback/export", headers=ah)
    lines = [json.loads(line) for line in export.text.splitlines()]
    assert len(lines) == 1 and lines[0]["label"] == "scam" and "Lunch" in lines[0]["text"]
