"""Browser end-to-end test of the web app against a running stack (not collected by pytest).

    pip install playwright && python -m playwright install chromium
    python tests/e2e/ui_flow.py            # BASE_URL=http://localhost:3000 MAILPIT_URL=http://localhost:8025

Flow: phone sign-up with privacy consent (OTP read from Mailpit, SMS_PROVIDER=email_bridge) -> dashboard ->
message scan with confidence + report-to-1930 sheet -> trusted contact -> Get Help -> voice navigation ->
family readiness -> safety habits (drill, shield, score) -> link checker -> quiz check -> alerts -> Hindi interface. Fails on any JS error.
"""

import json
import os
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:3000")
MAILPIT = os.environ.get("MAILPIT_URL", "http://localhost:8025")
SHOTS = os.environ.get("SCREENSHOT_DIR", "e2e-screenshots")
PHONE = "98201" + str(int(time.time()))[-5:]


def mailpit_otp(phone: str) -> str:
    for _ in range(30):
        msgs = json.load(urllib.request.urlopen(f"{MAILPIT}/api/v1/messages"))["messages"]  # noqa: S310
        for m in msgs:
            if phone in m["Subject"] and "otp" in m["Subject"]:
                body = json.load(urllib.request.urlopen(f"{MAILPIT}/api/v1/message/{m['ID']}"))["Text"]  # noqa: S310
                return re.search(r"\b(\d{6})\b", body).group(1)
        time.sleep(1)
    raise SystemExit("OTP SMS not found in Mailpit")


def check_icons(pg, scope: str) -> None:
    """Every icon in scope must render as a glyph (a missing icon shows its name as wide text)."""
    bad = pg.evaluate(
        """s => [...document.querySelectorAll(s + ' i')].filter(i => i.offsetWidth > parseFloat(getComputedStyle(i).fontSize) * 1.5)
              .map(i => i.textContent)""",
        scope,
    )
    assert not bad, f"icons not in the font subset: {bad}"


def main() -> int:
    os.makedirs(SHOTS, exist_ok=True)
    with sync_playwright() as p:
        kwargs = {"executable_path": os.environ["CHROMIUM_PATH"]} if os.environ.get("CHROMIUM_PATH") else {}
        browser = p.chromium.launch(**kwargs)
        pg = browser.new_page(viewport={"width": 1366, "height": 900})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: m.type == "error" and errors.append(m.text))

        pg.goto(BASE, wait_until="networkidle")
        pg.click("button:has-text('Watch Demo')")  # narrated product story (captions-only without a voice)
        pg.wait_for_selector("[data-testid=story-slide]:has-text('Paste or upload the message')")
        check_icons(pg, "[data-testid=story-player]")
        for _ in range(7):
            pg.click("[data-testid=story-next]")
        pg.wait_for_selector("[data-testid=story-end]")
        hrefs = pg.eval_on_selector_all("[data-testid=story-end] a", "els => els.map(e => e.href)")
        assert len(hrefs) == 4 and all(h.startswith("https://") for h in hrefs), hrefs
        pg.screenshot(path=f"{SHOTS}/0-demo-story-end.png")
        pg.click("[data-testid=story-player] button[aria-label=Close]")
        print("PASS landing demo story + official links")
        foot = "[data-testid=footer-links]"
        pg.click(f"{foot} >> text=Privacy Policy")
        pg.wait_for_selector("[data-testid=consent-sheet]")
        pg.click("[data-testid=consent-sheet] button[aria-label=Close]")
        pg.click(f"{foot} >> text=Safety lessons")
        pg.wait_for_selector("[data-testid=story-slide]")
        pg.click("[data-testid=story-player] button[aria-label=Close]")
        hrefs = pg.eval_on_selector_all(f"{foot} a", "els => els.map(e => e.getAttribute('href'))")
        assert "tel:1930" in hrefs and "https://cybercrime.gov.in" in hrefs, hrefs
        print("PASS footer links")
        pg.click("text=Get started")
        pg.fill("input[placeholder='Priya Sharma']", "Kamala Iyer")
        pg.select_option("select >> nth=0", "English")
        assert pg.locator("[data-testid=su-city]").count() == 0  # city list appears after a state is chosen
        pg.select_option("[data-testid=su-state]", "Tamil Nadu")
        pg.select_option("[data-testid=su-city]", "__other")
        pg.fill("[data-testid=su-city-other]", "Kumbakonam")  # a town not in the list
        pg.select_option("[data-testid=su-city]", "Chennai")
        assert pg.locator("[data-testid=su-city-other]").count() == 0
        pg.click("text=Senior Citizen")
        pg.fill("input[placeholder='98765 43210']", PHONE)
        pg.click("button:has-text('Send OTP')")
        pg.wait_for_selector("text=Please accept the privacy notice")  # consent is required
        pg.click("[data-testid=consent-toggle]")
        pg.click("button:has-text('Send OTP')")
        pg.wait_for_selector("text=Enter the 6-digit OTP")
        pg.fill("input[maxlength='6']", mailpit_otp("+91" + PHONE))
        pg.click("button:has-text('Verify & create account')")
        pg.wait_for_selector("text=/(Namaste|नमस्ते), Kamala/", timeout=20000)
        assert "Chennai" in pg.locator("header, aside").first.inner_text() or "Chennai" in pg.content()
        pg.screenshot(path=f"{SHOTS}/1-dashboard.png")
        print("PASS sign-up + dashboard")

        pg.click("aside >> text=Message Scanner")
        pg.click("button:has-text('Scan message')")
        if os.environ.get("SLOW_AI"):  # with a slow model, the rules result must appear first
            t0 = time.time()
            pg.wait_for_selector("text=AI is double-checking this result", timeout=3000)
            print(f"PASS instant rules result in {time.time() - t0:.1f}s while the AI runs")
            pg.screenshot(path=f"{SHOTS}/2a-quick.png", full_page=True)
        pg.wait_for_selector("text=/\\d+\\/100/", timeout=30000)
        pg.wait_for_selector("text=/Confidence: (high|medium|low)/")
        assert "1930" in pg.locator("[data-trust]").first.inner_text()
        og = pg.locator("[data-og]").first
        assert "SEBI" in og.inner_text() and og.locator("a").first.get_attribute("href").startswith("https://")
        pg.screenshot(path=f"{SHOTS}/2-message.png", full_page=True)
        print("PASS message scan + confidence + what the regulators say")

        pg.click("[data-testid=report-btn]")
        pg.wait_for_selector("[data-testid=report-summary]:has-text('wealthking@ybl')", timeout=15000)
        assert pg.get_attribute("[data-testid=report-sheet] a:has-text('1930')", "href") == "tel:1930"
        pg.screenshot(path=f"{SHOTS}/3-report.png")
        pg.click("button:has-text('I have reported it')")
        pg.wait_for_selector("text=Thank you for reporting")
        print("PASS report-to-1930 sheet")

        pg.click("aside >> text=Elderly Protection")
        pg.click("button:has-text('Add')")
        pg.fill("input[placeholder='Name (e.g. Rahul Kulkarni)']", "Rahul Iyer")
        pg.fill("input[placeholder='Relationship (e.g. Son)']", "Son")
        pg.fill("input[placeholder='Mobile number']", "9820144120")
        pg.click("text=Save contact")
        pg.wait_for_selector("text=Rahul Iyer")
        pg.click("button:has-text('Get Help')")
        pg.wait_for_selector("text=Help is on the way", timeout=20000)
        assert pg.get_attribute("a:has-text('Call Rahul')", "href") == "tel:+919820144120"
        print("PASS trusted contact + Get Help")

        pg.click("[data-toggle=voiceNav]")
        pg.wait_for_selector("[data-testid=voice-fab]")
        intent = pg.evaluate(
            """async () => { const fd = new FormData(); fd.append('text', 'इस संदेश की जाँच करो');
            const r = await fetch('/api/voice/command', {method: 'POST', body: fd,
              headers: {Authorization: 'Bearer ' + localStorage.getItem('sk_access')}}); return (await r.json()).intent; }"""
        )
        assert intent == "scan", intent
        print("PASS voice navigation button + command:", intent)

        pg.click("aside >> text=Family Readiness")
        pg.wait_for_selector("[data-ready-item=bank_account]")
        pg.click("[data-ready-item=bank_account] >> button:has-text('Added')")
        pg.wait_for_function("document.querySelector('[data-testid=ready-score]').innerText !== '0'")
        pg.screenshot(path=f"{SHOTS}/4-readiness.png", full_page=True)
        print("PASS family readiness:", pg.inner_text("[data-testid=ready-score]") + "%")

        pg.click("aside >> text=Safety Habits")
        pg.wait_for_selector("text=/Level \\d · /")
        pg.wait_for_selector("[data-testid=safety-score-value]:not(:has-text('…'))")
        before = int(pg.inner_text("[data-testid=safety-score-value]"))
        for _ in range(3):  # daily scam drill: answer, read the explanation, next
            pg.click("[data-testid=drill-scam]")
            pg.wait_for_selector("[data-testid=drill-result]")
            pg.click("[data-testid=drill-next]")
        pg.wait_for_selector("[data-testid=drill-done]")
        pg.locator("[data-testid=shield-btn]").first.click()
        pg.wait_for_function(f"+document.querySelector('[data-testid=safety-score-value]').innerText > {before}")
        pg.screenshot(path=f"{SHOTS}/5-safety-habits.png", full_page=True)
        print("PASS safety habits: drill + shield, score", before, "->", pg.inner_text("[data-testid=safety-score-value]"))

        pg.click("aside >> text=Link Checker")
        pg.fill("[data-testid=link-input]", "http://127.0.0.1/admin")  # private address: never fetched (SSRF guard)
        pg.click("[data-testid=link-check]")
        pg.wait_for_selector("[data-testid=link-verdict]", timeout=30000)
        assert "private network" in pg.inner_text("main")  # not opened, and the user is told why
        assert pg.locator("[data-testid=link-checks]").count() == 1
        print("PASS link checker refuses private addresses and explains why")

        pg.click("aside >> text=Learning Center")
        pg.wait_for_selector("text=/Question 1 of/")
        pg.locator("text=/^B$/").first.click()
        pg.click("button:has-text('Check answer')")
        pg.wait_for_selector("text=/Correct|Not quite/")
        print("PASS quiz check")
        check_icons(pg, "main")
        pg.click("[data-story=collect]")
        pg.wait_for_selector("[data-testid=story-slide]:has-text('You are selling something online')")
        pg.wait_for_selector("[data-testid=story-slide]:has-text('A request pops up')", timeout=15000)  # plays on its own
        pg.screenshot(path=f"{SHOTS}/7a-story.png")
        pg.click("[data-testid=story-play]")  # pause
        pg.wait_for_selector("[data-testid=story-play]:has-text('Play')")
        pg.click("[data-testid=story-player] button[aria-label=Close]")
        assert pg.locator("a[href='https://rbikehtahai.rbi.org.in/']").count() == 1
        print("PASS story lesson plays, pauses + official videos listed")

        pg.click("aside >> text=Safety Alerts")
        pg.wait_for_selector("text=/family has been alerted/i", timeout=10000)
        pg.screenshot(path=f"{SHOTS}/5-alerts.png", full_page=True)
        print("PASS alerts")

        pg.click("[data-nav=settings]")
        pg.click("button:has-text('हिन्दी · Hindi')")
        pg.wait_for_selector("[data-nav=settings]:has-text('सेटिंग्स')", timeout=10000)
        pg.click("[data-nav=ready]")
        pg.wait_for_selector("text=परिवार की तैयारी")
        pg.screenshot(path=f"{SHOTS}/6-hindi.png")
        pg.click("[data-nav=settings]")
        pg.click("button:has-text('English')")
        pg.wait_for_selector("[data-nav=settings]:has-text('Settings')", timeout=10000)
        print("PASS Hindi interface + back to English")
        browser.close()
    if errors:
        print("JS errors:", errors)
        return 1
    print("ALL UI CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
