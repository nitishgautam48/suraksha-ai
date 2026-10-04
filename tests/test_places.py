"""State / city dropdowns: one list of states shared by the server and the web app."""

import json
import re
from pathlib import Path
from typing import get_args

from backend.utils.india import PLACES, IndianState

ROOT = Path(__file__).resolve().parent.parent


def test_all_36_states_and_uts_with_cities():
    assert len(PLACES) == 36
    assert list(PLACES) == list(get_args(IndianState))
    for state, cities in PLACES.items():
        assert cities and len(cities) == len(set(cities)), state


def test_frontend_list_matches_server():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    india = json.loads(re.search(r"const INDIA=(\{.*?\});", html).group(1))
    assert {k: tuple(v.split("|")) for k, v in india.items()} == PLACES


def test_state_names_translated_to_hindi():
    hi = json.loads((ROOT / "frontend/i18n/hi.json").read_text(encoding="utf-8"))
    assert all(state in hi for state in PLACES)


def test_profile_saves_state_and_city(client, auth):
    h, _ = auth
    r = client.patch("/auth/me", json={"state": "Madhya Pradesh", "city": "Indore"}, headers=h)
    assert r.status_code == 200, r.text
    assert (r.json()["state"], r.json()["city"]) == ("Madhya Pradesh", "Indore")
    me = client.get("/auth/me", headers=h).json()
    assert me["state"] == "Madhya Pradesh"


def test_unknown_state_is_rejected(client, auth):
    h, _ = auth
    assert client.patch("/auth/me", json={"state": "Atlantis"}, headers=h).status_code == 422
