"""Habit tracker rebuilt around real actions: Safety Score, Daily Scam Drill, Safety Shield,
daily goals and the weekly challenge."""

from backend.services import safety_service


def _habits(client, h):
    r = client.get("/habits", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_drill_bank_is_well_formed():
    bank = safety_service.drill_bank()
    assert len(bank) >= 30
    labels = [d["label"] for d in bank.values()]
    assert labels.count("scam") >= 15 and labels.count("genuine") >= 10
    assert all(d["tip"] and d["text"] and d["label"] in ("scam", "genuine") for d in bank.values())


def test_overview_has_score_drill_shield_goals(client, auth):
    h, _ = auth
    body = _habits(client, h)
    s = body["safety_score"]
    assert 300 <= s["score"] <= 900 and s["band"] and len(s["parts"]) == 6 and s["boosters"]
    items = body["drill"]["items"]
    assert len(items) == 3 and not body["drill"]["done"]
    labels = {safety_service.drill_bank()[i["id"]]["label"] for i in items}
    assert labels == {"scam", "genuine"}
    assert all("label" not in i or i["label"] is None for i in items)  # answers stay hidden until answered
    assert len(body["shield"]) == len(safety_service.SHIELD)
    assert [g["key"] for g in body["daily"]["goals"]] == ["drill", "learn", "check"]
    assert len(body["daily"]["goals"][0]["week"]) == 7
    assert body["weekly_challenge"]["title"] and not body["weekly_challenge"]["done"]
    assert any("Scam Drill" in n for n in body["nudges"])


def test_drill_flow_awards_xp_streak_and_raises_score(client, auth):
    h, _ = auth
    before = _habits(client, h)
    ids = [i["id"] for i in before["drill"]["items"]]
    bank = safety_service.drill_bank()

    first = client.post("/habits/drill/answer", headers=h, json={"item_id": ids[0], "answer": bank[ids[0]]["label"]}).json()
    assert first["correct"] and first["xp_awarded"] == 10 and first["tip"] and first["remaining"] == 2
    again = client.post("/habits/drill/answer", headers=h, json={"item_id": ids[0], "answer": "genuine"}).json()
    assert again["correct"] and again["xp_awarded"] == 0  # first answer counts, no double XP

    wrong = "genuine" if bank[ids[1]]["label"] == "scam" else "scam"
    second = client.post("/habits/drill/answer", headers=h, json={"item_id": ids[1], "answer": wrong}).json()
    assert not second["correct"] and second["xp_awarded"] == 0
    third = client.post("/habits/drill/answer", headers=h, json={"item_id": ids[2], "answer": bank[ids[2]]["label"]}).json()
    assert third["done"] and third["xp_awarded"] == 10 + 25  # correct + finished-the-drill bonus

    after = _habits(client, h)
    assert after["drill"]["done"] and after["drill"]["correct_today"] == 2 and after["drill"]["streak_days"] == 1
    assert all(i["answered"] and i["label"] for i in after["drill"]["items"])
    assert after["daily"]["goals"][0]["done"] and after["daily"]["goals"][0]["week"][-1]
    assert after["safety_score"]["score"] > before["safety_score"]["score"]
    titles = [x["title"] for x in client.get("/gamification", headers=h).json()["recent_xp"]]
    assert "Finished today's Scam Drill" in titles


def test_drill_rejects_items_not_in_today(client, auth):
    h, _ = auth
    today = {i["id"] for i in _habits(client, h)["drill"]["items"]}
    other = next(i for i in safety_service.drill_bank() if i not in today)
    assert client.post("/habits/drill/answer", headers=h, json={"item_id": other, "answer": "scam"}).status_code == 404
    assert client.post("/habits/drill/answer", headers=h, json={"item_id": "d01", "answer": "maybe"}).status_code == 422


def test_shield_steps(client, auth):
    h, _ = auth
    before = _habits(client, h)["safety_score"]["score"]
    assert client.put("/habits/shield/sec_whatsapp_2step", headers=h, json={"completed": True}).status_code == 200
    assert client.put("/habits/shield/sec_trusted_contact", headers=h, json={"completed": True}).status_code == 400
    assert client.put("/habits/shield/not_a_step", headers=h, json={"completed": True}).status_code == 404
    body = _habits(client, h)
    step = next(s for s in body["shield"] if s["key"] == "sec_whatsapp_2step")
    assert step["done"] and body["safety_score"]["score"] > before
    # shield steps must not count toward the emergency-fund checklist / badge
    assert body["emergency_fund_progress"] == 0
    badges = {a["key"]: a["state"] for a in client.get("/gamification", headers=h).json()["achievements"]}
    assert badges["emergency_ready"] == "locked" and badges["fully_shielded"] == "locked"


def test_trusted_contact_step_is_automatic(client, auth):
    h, _ = auth
    r = client.post("/contacts", headers=h, json={"name": "Asha Verma", "relationship": "daughter", "phone": "98201 55120"})
    assert r.status_code == 201, r.text
    step = next(s for s in _habits(client, h)["shield"] if s["key"] == "sec_trusted_contact")
    assert step["done"] and step["auto"]


def test_weekly_challenge_once_per_week(client, auth):
    h, _ = auth
    assert "+40 XP" in client.post("/habits/weekly-challenge", headers=h).json()["detail"]
    assert "Already" in client.post("/habits/weekly-challenge", headers=h).json()["detail"]
    assert _habits(client, h)["weekly_challenge"]["done"]


def test_opening_flashcards_is_not_practice(client, auth):
    """The app pre-loads flash cards; only actually flipping them counts toward today's Learn goal."""
    h, _ = auth
    course = client.get("/learning/courses", headers=h).json()[0]["id"]
    assert client.get(f"/learning/courses/{course}/flashcards", headers=h).status_code == 200
    learn = next(g for g in _habits(client, h)["daily"]["goals"] if g["key"] == "learn")
    assert not learn["done"]
    r = client.post(f"/learning/courses/{course}/flashcards/practised", headers=h)
    assert r.status_code == 200 and "XP" in r.json()["detail"]
    learn = next(g for g in _habits(client, h)["daily"]["goals"] if g["key"] == "learn")
    assert learn["done"]
