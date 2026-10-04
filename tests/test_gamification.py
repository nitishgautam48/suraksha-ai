import uuid

import pytest

from backend.services.gamification_service import level_for


def _h(data):
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.mark.parametrize(
    "xp,level,name",
    [
        (0, 1, "Beginner"),
        (99, 1, "Beginner"),
        (100, 2, "Learner"),
        (2340, 6, "Guardian"),
        (9000, 10, "Suraksha Hero"),
        (50000, 10, "Suraksha Hero"),
    ],
)
def test_levels(xp, level, name):
    info = level_for(xp)
    assert info["level"] == level and info["level_name"] == name


def test_design_example_level_6():
    info = level_for(2340)
    assert info["label"] == "Level 6 · Guardian" and info["xp_to_next"] == 660 and info["progress_pct"] == 34.0


def test_xp_is_idempotent_and_badges_claimable(client, register):
    h = _h(register(f"xp-{uuid.uuid4().hex[:6]}@example.com"))
    course = client.get("/learning/courses", headers=h).json()[0]
    lesson = client.get(f"/learning/courses/{course['id']}", headers=h).json()["lessons"][0]
    first = client.post(f"/learning/lessons/{lesson['id']}/complete", headers=h).json()
    assert first["xp_awarded"] == 50 + 25  # lesson + daily learning
    again = client.post(f"/learning/lessons/{lesson['id']}/complete", headers=h).json()
    assert again["xp_awarded"] == 0  # no double pay

    q = client.get(f"/learning/courses/{course['id']}/assessment", headers=h).json()["questions"][0]
    wrong = client.post(f"/learning/questions/{q['id']}/check", headers=h, json={"answer": 3}).json()
    right_idx = wrong["correct_index"]
    if right_idx == 3:
        assert wrong["correct"] and wrong["xp_awarded"] == 20
    else:
        assert not wrong["correct"] and wrong["xp_awarded"] == 0
        right = client.post(f"/learning/questions/{q['id']}/check", headers=h, json={"answer": right_idx}).json()
        assert right["correct"] and right["xp_awarded"] == 20
    assert client.post(f"/learning/questions/{q['id']}/check", headers=h, json={"answer": right_idx}).json()["xp_awarded"] == 0

    client.post("/analyze/message", headers=h, json={"message_text": "Share OTP now to claim prize"})
    g = client.get("/gamification", headers=h).json()
    assert g["xp"] == 75 + 20 + 10
    badges = {a["key"]: a for a in g["achievements"]}
    assert badges["first_check"]["state"] == "claim" and badges["scam_spotter"]["state"] == "locked"
    assert badges["scam_spotter"]["progress"] == 1 and badges["scam_spotter"]["target"] == 10
    claimed = client.post("/gamification/achievements/first_check/claim", headers=h).json()
    assert claimed["xp_awarded"] == 20 and claimed["xp"] == 125
    assert client.post("/gamification/achievements/first_check/claim", headers=h).status_code == 409
    assert client.post("/gamification/achievements/scam_spotter/claim", headers=h).status_code == 400
    alerts = client.get("/alerts", headers=h).json()["items"]
    assert any(a["alert_type"] == "achievement" for a in alerts)


def test_scan_xp_daily_cap(client, register):
    h = _h(register(f"cap-{uuid.uuid4().hex[:6]}@example.com"))
    for i in range(7):
        client.post("/analyze/message", headers=h, json={"message_text": f"hello {i}"})
    assert client.get("/gamification", headers=h).json()["xp"] == 5 * 10 + 20 * 0  # capped at 5 scans/day


def test_quiz_submit_xp_and_quiz_ace(client, register):
    h = _h(register(f"ace-{uuid.uuid4().hex[:6]}@example.com"))
    course = client.get("/learning/courses", headers=h).json()[1]
    qs = client.get(f"/learning/courses/{course['id']}/assessment", headers=h).json()["questions"]
    answers = {}
    for q in qs:  # discover the right answers via practice mode (first try awards XP)
        answers[q["id"]] = client.post(f"/learning/questions/{q['id']}/check", headers=h, json={"answer": 0}).json()[
            "correct_index"
        ]
    before = client.get("/gamification", headers=h).json()["xp"]
    r = client.post(f"/learning/courses/{course['id']}/assessment/submit", headers=h, json={"answers": answers}).json()
    unpaid = sum(1 for idx in answers.values() if idx != 0)  # practice paid only the ones answered right (0)
    assert r["percent"] == 100.0 and r["xp_awarded"] == unpaid * 20 + 100  # no double pay + pass bonus
    g = client.get("/gamification", headers=h).json()
    assert g["xp"] == before + r["xp_awarded"]
    assert {a["key"]: a["state"] for a in g["achievements"]}["quiz_ace"] == "claim"


def test_heatmap_and_activity_feed(client, register):
    h = _h(register(f"heat-{uuid.uuid4().hex[:6]}@example.com"))
    client.post("/analyze/message", headers=h, json={"message_text": "Guaranteed 5% daily returns"})
    client.put("/habits/checklist/set_target", headers=h, json={"completed": True})
    hm = client.get("/activity/heatmap", headers=h).json()
    assert len(hm["days"]) == 98 and hm["active_days"] == 1
    today = next(d for d in hm["days"] if d["count"])
    assert today["level"] >= 1
    feed = client.get("/activity/recent", headers=h).json()
    titles = [f["title"] for f in feed]
    assert any("Emergency-fund step" in t for t in titles) and any("Scanned a" in t for t in titles)
    d = client.get("/dashboard", headers=h).json()
    assert d["level"]["label"].startswith("Level 1") and d["recent_activity"]
