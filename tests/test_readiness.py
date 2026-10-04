"""Nominee & family-readiness checklist."""

from backend import i18n


def test_checklist_starts_empty_and_lists_all_items(client, auth):
    h, _ = auth
    r = client.get("/family/readiness", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 11 and body["score_pct"] == 0
    assert {"bank_account", "demat", "mutual_fund", "insurance", "will"} <= {i["key"] for i in body["items"]}
    assert "not legal or financial advice" in body["disclaimer"]
    assert len(body["next_steps"]) == 3


def test_updating_items_raises_score_and_never_stores_numbers(client, auth):
    h, _ = auth
    for key in ("bank_account", "insurance"):
        r = client.put(
            f"/family/readiness/{key}",
            headers=h,
            json={"nominee": "yes", "family_informed": True, "documents_location": "almirah, a/c no 123456789012"},
        )
        assert r.status_code == 200, r.text
    # mark everything else as not applicable -> two complete items = 100%
    for item in r.json()["items"]:
        if item["key"] not in ("bank_account", "insurance"):
            client.put(f"/family/readiness/{item['key']}", headers=h, json={"applicable": False})
    body = client.get("/family/readiness", headers=h).json()
    assert body["score_pct"] == 100
    bank = next(i for i in body["items"] if i["key"] == "bank_account")
    assert bank["done"] and "123456789012" not in bank["documents_location"]

    summary = client.get("/family/readiness/summary", headers=h)
    assert summary.status_code == 200 and "almirah" in summary.text and "123456789012" not in summary.text


def test_unknown_item_and_localized_titles(client, auth):
    h, _ = auth
    assert client.put("/family/readiness/crypto_wallet", headers=h, json={"nominee": "yes"}).status_code == 404
    hi = client.get("/family/readiness", headers=h, params={"language": "ta"}).json()
    assert hi["title"] == i18n.t("readiness_title", "ta") and hi["items"][0]["title"] != "Bank savings accounts"


def test_readiness_text_passes_advice_guardrail():
    from backend.ai.guardrails import output_violates_policy

    for code in i18n.LANGUAGES:
        for key in ("readiness_intro", "readiness_disclaimer", "rd_demat_tip", "rd_mutual_fund_tip", "rd_will_tip"):
            assert not output_violates_policy(i18n.t(key, code)), f"{code}:{key}"
