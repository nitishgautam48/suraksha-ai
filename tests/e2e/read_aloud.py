"""Browser check of the Voice Assistant read-aloud (not collected by pytest; needs a running stack).

    python tests/e2e/read_aloud.py     # BASE_URL=http://localhost:3000 API_URL=http://localhost:8000

1. Device with Hindi + English voices: a Hindi reply is read by the Hindi voice, in sentence-sized
   chunks, without markdown symbols; Listen/Stop toggles.
2. Device with no Hindi voice: the server voice (POST /voice/tts) is played instead.
"""

import json
import os
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE_URL", "http://localhost:3000")
API = os.environ.get("API_URL", "http://localhost:8000")
REPLY = (
    "**यह धोखाधड़ी है।** 🚨\n- गारंटीड रिटर्न का वादा\n- OTP माँगना\n"
    + "किसी को भी अपना OTP, PIN या पासवर्ड न बताएं, चाहे वह खुद को बैंक, पुलिस, SEBI या किसी सरकारी विभाग का अधिकारी बताए। "
    + "पैसे चले गए हों तो तुरंत 1930 पर कॉल करें और https://cybercrime.gov.in/Webform पर शिकायत करें।"
)
FAKE_SPEECH = """(withHindi) => {
  window.__spoken = [];
  const voices = [{name:'Google US English', lang:'en-US', localService:false},
                  {name:'Microsoft Heera - English (India)', lang:'en-IN', localService:true}];
  if (withHindi) voices.push({name:'Google हिन्दी', lang:'hi-IN', localService:false});
  let queue = [], timer = null;
  const next = () => { const u = queue.shift(); if (!u) { timer = null; return; }
    window.__spoken.push({text: u.text, voice: u.voice && u.voice.name, lang: u.lang});
    timer = setTimeout(() => { u.onend && u.onend(); next(); }, 150); };
  const fake = {getVoices: () => voices, speak(u) { queue.push(u); if (!timer) next(); },
    cancel() { queue = []; clearTimeout(timer); timer = null; }, resume() {}, pause() {}, onvoiceschanged: null};
  Object.defineProperty(window, 'speechSynthesis', {value: fake, configurable: true, writable: true});
  window.SpeechSynthesisUtterance = function (t) { this.text = t; };
}"""


def register():
    body = {
        "name": "Voice Tester",
        "email": f"voice{int(time.time() * 1000)}@example.com",
        "password": "Passw0rd!x",
        "consent": True,
    }
    req = urllib.request.Request(f"{API}/auth/register", json.dumps(body).encode(), {"Content-Type": "application/json"})
    t = json.load(urllib.request.urlopen(req))  # noqa: S310
    return t.get("access_token") or t["tokens"]["access_token"], t.get("refresh_token") or t["tokens"]["refresh_token"]


def run(p, with_hindi: bool) -> None:
    kwargs = {"executable_path": os.environ["CHROMIUM_PATH"]} if os.environ.get("CHROMIUM_PATH") else {}
    b = p.chromium.launch(**kwargs)
    pg = b.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.add_init_script(f"({FAKE_SPEECH})({str(with_hindi).lower()})")
    tts_calls = []
    pg.route("**/chat", lambda r: r.fulfill(json={"response": REPLY, "chat_id": "x", "sources": []}))

    def tts(route):
        if route.request.method == "GET":  # availability check
            return route.fulfill(json={"available": True, "languages": ["en", "hi"]})
        tts_calls.append(route.request.post_data_json)
        # 0.2 s of silence as a valid WAV
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(8000), w.writeframes(b"\0\0" * 1600)
        route.fulfill(body=buf.getvalue(), headers={"content-type": "audio/wav"})

    pg.route("**/voice/tts", tts)
    acc, ref = register()
    pg.goto(BASE, wait_until="networkidle")
    pg.evaluate(f"localStorage.setItem('sk_access','{acc}');localStorage.setItem('sk_refresh','{ref}')")
    pg.goto(BASE, wait_until="networkidle")
    pg.click("aside >> text=Voice Assistant")
    pg.fill("input[placeholder^='Type, or tap']", "Kya yeh scam hai?")
    pg.click("button[aria-label=Send]")
    pg.wait_for_selector("text=Speaking… tap to stop")
    if with_hindi:
        pg.wait_for_selector("text=Speaking… tap to stop", state="detached", timeout=20000)  # whole reply read
        spoken = pg.evaluate("window.__spoken")
        assert all(s["voice"] == "Google हिन्दी" for s in spoken), spoken
        joined = " ".join(s["text"] for s in spoken)
        assert "**" not in joined and "🚨" not in joined and "https://" not in joined and "cybercrime.gov.in" in joined, joined
        assert max(len(s["text"]) for s in spoken) <= 181, [len(s["text"]) for s in spoken]
        assert not tts_calls
        pg.wait_for_selector("[data-testid=v-listen]:has-text('Listen')")
        pg.click("[data-testid=v-listen]")
        pg.wait_for_selector("[data-testid=v-listen]:has-text('Stop')")
        pg.click("[data-testid=v-listen]")
        pg.wait_for_selector("[data-testid=v-listen]:has-text('Listen')")
        print(f"PASS Hindi voice: {len(spoken)} chunks, clean text, Listen/Stop toggles")
    else:
        pg.wait_for_function("1", timeout=1000)
        pg.wait_for_selector("text=Speaking… tap to stop", state="detached", timeout=15000)
        assert tts_calls and tts_calls[0]["language"] == "hi" and "**" not in tts_calls[0]["text"], tts_calls
        print("PASS no Hindi voice on device: server voice played")
    assert not errors, errors
    b.close()


def main() -> int:
    with sync_playwright() as p:
        run(p, with_hindi=True)
        run(p, with_hindi=False)
    print("ALL READ-ALOUD CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
