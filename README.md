# Suraksha AI — Investor Protection Platform

AI-powered platform (FastAPI backend + web app) that protects Indian investors from **scams, financial misinformation, phishing,
fake investment schemes and risky financial behaviour**. Every model runs locally (Ollama, Tesseract,
Whisper, Coqui TTS), so **no paid APIs are needed**.

> **Compliance by design.** Suraksha AI never predicts prices, gives buy/sell/hold calls, recommends
> securities or brokers, or generates trading signals. It only detects scams, explains manipulation,
> teaches financial literacy and encourages safe behaviour. This is enforced in three layers, in all
> 12 supported languages: system prompts, an input guardrail that politely refuses advice-seeking
> questions and price predictions before the LLM is called, and an output guardrail that removes
> advice-like sentences from model output.
>
> **Privacy by design.** OTPs, PINs, card, Aadhaar, PAN and account numbers are masked before any
> analysis or storage; screenshots are deleted as soon as their text is read; all AI runs on your own
> server; users accept a plain-language privacy notice before any of their content is processed.

---

## Quick start

```bash
cp .env.example .env          # optional - every setting has a working default
docker compose up -d          # builds the API image and starts the whole stack
docker compose logs -f ollama-init   # watch the one-time model download (~11 GB)
```

* **Web app: http://localhost:3000**. Sign up with a phone number; in development the OTP SMS
  lands in Mailpit (http://localhost:8025).
* Swagger UI: http://localhost:8000/docs  ·  ReDoc: http://localhost:8000/redoc
* Readiness (DB, Redis, Ollama models, ChromaDB, indexed chunks): http://localhost:8000/health/ready
* End-to-end check: `python3 scripts/smoke_test.py http://localhost:8000`
* Emails (verification, password reset) and development SMS (OTP, family alerts) land in the bundled
  Mailpit inbox: http://localhost:8025
* Optional: `docker compose --profile monitoring up -d` (Grafana on http://localhost:3001) and
  `docker compose --profile https up -d` (Caddy with automatic HTTPS) and
  `docker compose --profile offsite up -d` (off-machine backup copies). See [Operations](#operations).
* Copying `.env.example` also bootstraps an admin account (`admin@example.com` / `ChangeMe123`).
  Change both values before you deploy.

The API is usable **immediately**. Until the Ollama models finish downloading, analysis runs on the
deterministic rule engine (`engine.llm_used: false`) and chat returns safe offline guidance. Once the
`nomic-embed-text` model is available, the Celery worker indexes the knowledge base into ChromaDB
automatically (it checks every 10 minutes and on worker start).

### Hardware

| Machine | Works? | Notes |
|---|---|---|
| 16 GB RAM + 8 GB NVIDIA GPU (RTX 4060 / 3060 Ti / 4060 Ti 8 GB) | **Yes, recommended minimum** | Use the GPU override (below). Answers in roughly 2–10 s |
| 16 GB RAM, no GPU | Yes, slowly | LLM answers take 30–90 s; set `WEB_CONCURRENCY=1`, or `INSTALL_VOICE=false` if RAM runs out |
| 32 GB RAM and/or 12 GB+ GPU | Comfortably | Can raise `OLLAMA_NUM_PARALLEL` / `OLLAMA_MAX_LOADED_MODELS` to 2 |

Disk: about 25 GB (images ~8 GB with voice, models ~11 GB, and Docker build cache).

**Running on 16 GB RAM + an 8 GB GPU (e.g. RTX 4060)**

1. Start with the GPU override so Ollama runs on the graphics card:
   `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d`
   * Linux: install the NVIDIA driver and the NVIDIA Container Toolkit.
   * Windows: Docker Desktop with the WSL 2 backend and a current NVIDIA Game Ready / Studio driver
     (no CUDA install needed inside WSL).
   * Check that Docker sees the GPU: `docker compose exec ollama nvidia-smi` should list the card,
     and after the first analysis `docker compose exec ollama ollama ps` should show `100% GPU`.
2. Windows only: WSL 2 gives Docker **half of your RAM (8 GB) by default**, which is too little.
   Create `%UserProfile%\.wslconfig` with:
   ```ini
   [wsl2]
   memory=12GB
   swap=8GB
   ```
   then run `wsl --shutdown` and restart Docker Desktop.
3. In `.env`, set `WEB_CONCURRENCY=1`. Each API process loads its own Whisper + Coqui voice models
   (about 2.5 GB of RAM) the first time voice is used, and one process is plenty for one user.

What the defaults already do for an 8 GB card: one LLM plus the small `nomic-embed-text` embedding
model (~0.5 GB) in VRAM at a time (`OLLAMA_MAX_LOADED_MODELS=2`), one request at a time, flash
attention and an 8-bit KV cache.

* `llama3.1:8b` (scam analysis, chat, voice) needs ~4.9 GB + ~1 GB cache and fits fully on the GPU.
* `gemma2:9b` (lessons, quizzes, translations, nudges) needs ~5.4 GB + cache. That is close to the
  8 GB limit, so Ollama may keep a few layers on the CPU, making lesson generation a little slower.
* When you switch between scanning/chat and AI lessons, Ollama unloads one LLM and loads the other.
  The first request after a switch waits an extra 3–10 s.
* Whisper, Coqui and Tesseract run on the CPU, so the GPU stays free for the LLMs.

**Single-model option:** to skip the swap and the extra 5.4 GB download, set
`OLLAMA_SECONDARY_MODEL=llama3.1:8b` and remove `gemma2:9b` from `OLLAMA_PULL_MODELS`. Everything gets
faster; lessons and Indian-language translations may read slightly less naturally.

Expected RAM use with this setup: about 6–8 GB for the containers once voice has been used, plus
Windows and a browser. Stop the optional `monitoring` profile if memory is tight.

### Services

| Service | Image | Purpose |
|---|---|---|
| `postgres` | postgres:16-alpine | Primary database |
| `redis` | redis:7-alpine | Cache, rate-limit storage, token revocation, Celery broker |
| `ollama` | ollama/ollama | Local LLM runtime (port 11434) |
| `ollama-init` | ollama/ollama | One-shot pull of `nomic-embed-text`, `llama3.1:8b`, `gemma2:9b` |
| `chromadb` | chromadb/chroma | Vector database for RAG |
| `backend` | built from `backend/Dockerfile` | FastAPI app: runs migrations, seeds, then serves on :8000 |
| `worker` | same image | Celery worker + beat (async scans, emails, RAG ingestion, daily nudges) |
| `mailpit` | axllent/mailpit | Local SMTP catcher; web inbox on 127.0.0.1:8025 |
| `frontend` | built from `frontend/Dockerfile` (nginx) | Web app on :3000, proxies `/api/` to the backend on the same origin |
| `db-backup` | postgres:16-alpine | Daily `pg_dump` + archive of uploads/knowledge into `./backups` |
| `prometheus`, `grafana` | profile `monitoring` | Metrics, alert rules and a provisioned dashboard |
| `caddy` | profile `https` | Reverse proxy with automatic Let's Encrypt certificates |
| `backup-offsite` | profile `offsite` (rclone) | Copies `./backups` to S3 / B2 / Drive / SFTP hourly |

---

## Architecture

```
   web app (nginx :3000, same-origin /api proxy)
                 │
            ┌────▼─────── FastAPI (backend) ─────────────┐
            │ security middleware: request-id, audit log, │
            │ security headers, CORS, rate limit (Redis)  │
            │ JWT / Google OAuth / phone OTP  ·  RBAC      │
            ├─────────────────────────────────────────────┤
            │ routers → services                           │
            │  scan/analyze ─► OCR (Tesseract, PyMuPDF)     │
            │               ─► clean text ─► rule engine    │
            │               ─► Ollama llama3.1 (JSON) ─► fuse│
            │  chat/voice   ─► guardrail ─► RAG (Chroma +   │
            │                  nomic-embed) ─► Ollama ─► guardrail
            │  voice        ─► Whisper STT … Coqui TTS      │
            │  learning     ─► gemma2 (+RAG) generation     │
            └───────┬───────────────┬───────────────┬──────┘
                PostgreSQL        Redis ◄── Celery worker/beat
```

### Scam-detection pipeline (Modules 1–3)

`OCR → content cleaning → rule-based risk detection → LLM analysis → score fusion`

1. **OCR**: Tesseract (`eng+hin+guj+mar`) with screenshot preprocessing (upscaling, dark-mode
   inversion, autocontrast). For PDFs, embedded text is used where present and scanned pages are
   rasterised and OCR'd.
2. **Cleaning**: Unicode normalisation, removal of zero-width characters and WhatsApp timestamps.
3. **Rule engine** (`backend/ai/patterns.py`): 22 explainable detectors in English, Hinglish and
   Hindi. They cover guaranteed returns, unrealistic profits, Ponzi referral income, fake advisers,
   pump language, impersonation, "digital arrest", OTP/PIN requests, phishing, lottery bait,
   advance-fee demands, task-job scams, "sent by mistake" refund tricks, payment deadlines, secrecy
   requests, urgency, FOMO, fear, emotional manipulation, fake success stories, payment requests and
   missing disclosures. Link analysis checks look-alike bank domains, shorteners, raw IPs, punycode
   and risky TLDs. Negation handling and "awareness context" damping stop genuine warnings such as
   "never share your OTP" or a cyber-safety tip from being flagged.
4. **LLM** (`llama3.1:8b`, JSON mode): returns a calibrated score, categories, reasons and an
   explanation in the user's language. Results are cached in Redis.
5. **Fusion**: `final = max(rules, (1-w)·rules + w·llm)` with `w = RISK_LLM_WEIGHT` (0.6), so a strong
   rule hit is never diluted. Levels: `low` < 25 ≤ `medium` < 50 ≤ `high` < 75 ≤ `critical`
   (configurable with `RISK_*_THRESHOLD`).

High or critical results and dangerous links create **SafetyAlerts** automatically.

Risk categories: Ponzi Scheme, Guaranteed Returns, Fake Advisor, Pump and Dump, Impersonation,
Phishing, Urgency Manipulation, Social Engineering.

### Detection quality and calibration

`backend/ai/eval/dataset.jsonl` holds 132 labelled messages: 76 scams across all categories and 56
legitimate messages. The legitimate set deliberately includes hard negatives, such as genuine bank OTP
SMS, debit alerts and awareness posts that quote scam phrases. A third of the examples are a
**holdout** split that was set aside before tuning and is only used for reporting.

Rule engine alone (no LLM), at the default thresholds:

| Split | Warning (≥ medium) precision / recall | Scam (≥ high) precision / recall |
|---|---|---|
| tune (97) | 1.00 / 1.00 | 1.00 / 0.73 |
| holdout (35) | 1.00 / 1.00 | 1.00 / 0.55 |

**Caveat:** every example was written by hand, so these numbers show the engine generalises within
that style, not how it will do on real-world traffic. The gap between tune and holdout at the "high"
level shows where more tuning would only overfit. With Ollama running, the LLM layer raises scores
further.

To grow the dataset with real data:

1. Users mark results right or wrong with `POST /analyze/history/{id}/feedback`. Sharing the message
   excerpt requires `share_text: true`, which is explicit consent.
2. Admins review likely false positives and negatives with `GET /admin/feedback?disagreements_only=true`.
3. `GET /admin/feedback/export` downloads consented examples in the dataset format.
4. `python scripts/evaluate_risk.py --dataset feedback.jsonl --split all --calibrate` reports
   precision and recall, misses per category, and a suggested `RISK_MEDIUM_THRESHOLD`. Add `--llm` to
   score with the full hybrid engine.

`tests/test_risk_quality.py` is a CI quality gate: precision must stay ≥ 0.95, recall ≥ 0.90, and no
legitimate message may reach "high".

### RAG

Pipeline: `documents (PDF / Markdown / text / HTML) → loaders → markdown-aware chunking (900 chars,
150 overlap) → nomic-embed-text → ChromaDB`. At query time, the top-k chunks above a relevance
threshold are injected as numbered context, and the model must cite them as `[1]`, `[2]`. PDF chunks
keep their **page number**, so sources come back as, for example, "RBI booklet, page 2".

Every indexed document is tracked in the `knowledge_documents` table with its status, chunk count,
page count and any error. Re-indexing a document replaces its old chunks, so edits never leave stale
passages behind. There are three origins:

* **bundled:** `backend/rag/knowledge/*.md` are seven short summaries written for this project. They
  are a starting point, not the official text.
* **upload:** an admin uploads official documents with
  `POST /admin/knowledge/documents` (multipart: `file`, `title`, `source`, `url`, `topic`). Scanned
  PDF pages are OCR'd.
* **fetched:** list official PDF or page URLs in `backend/rag/sources.json` (format in
  `sources.example.json`), then call `POST /admin/knowledge/fetch` or run
  `python scripts/ingest_knowledge.py --fetch`. The fetcher accepts HTTPS only, refuses private or
  internal addresses (SSRF protection), re-checks every redirect, and caps size at `KNOWLEDGE_MAX_MB`.

**Recommended next step:** replace the bundled summaries with the regulators' own current documents.
For example, upload SEBI investor-awareness booklets, the RBI "BE(A)WARE" fraud booklet, NCFE
financial-literacy material and I4C cyber-hygiene guides. Admins can list, re-index or delete
documents under `/admin/knowledge/documents`.

---

## API

All endpoints except `/health*`, `/languages` and the public `/auth/*` calls (register, login, google,
phone OTP, refresh, password reset) need
`Authorization: Bearer <access_token>`.

| Method | Path | Module | Description |
|---|---|---|---|
| POST | `/auth/register` | Auth | Email + password sign-up, returns tokens |
| POST | `/auth/login` | Auth | Login, returns access + refresh tokens |
| POST | `/auth/google` | Auth | Google ID-token login (OAuth / OIDC) |
| POST | `/auth/phone/request-otp` · `/auth/phone/verify` | Auth | Phone + SMS OTP sign-up / login (no password) |
| POST | `/auth/phone/link/request` · `/auth/phone/link/confirm` | Auth | Add and verify a phone on an existing account |
| POST | `/auth/refresh` | Auth | Rotate tokens (old refresh token revoked) |
| POST | `/auth/logout` | Auth | Revoke tokens |
| POST | `/auth/verify-email/request` · `/auth/verify-email/confirm` | Auth | Send / confirm the email-verification link |
| POST | `/auth/password/forgot` · `/auth/password/reset` | Auth | Emailed single-use reset link → new password (signs out all sessions) |
| POST | `/auth/password/change` | Auth | Change password while logged in (other sessions signed out) |
| GET/PATCH/DELETE | `/auth/me` | Auth | Profile (name, language, city, user type, add email), account deletion |
| GET/PATCH | `/me/preferences` | Prefs | Elder mode, theme, text size, voice, notifications, privacy |
| GET | `/languages` | i18n | The 12 languages with OCR / speech-to-text / server-voice support flags |
| POST | `/scan/image` | 1 | Screenshot/photo → OCR → analysis (`async=true` queues it on Celery) |
| POST | `/scan/pdf` | 1 | PDF → text/OCR → analysis |
| POST | `/scan/text` | 1 | Any pasted text |
| POST | `/analyze/message` | 2 | WhatsApp message analyzer |
| POST | `/analyze/message-image` | 2 | Chat screenshot → OCR in memory (never stored) → message analysis |
| POST | `/analyze/link` | 3 | Link Checker: open an Instagram / YouTube / Telegram / X / web link, fact-check its claims, reasoned verdict |
| POST | `/analyze/social` | 3 | Paste a caption / transcript instead: highlighted manipulation tactics |
| GET | `/analyze/history[/{id}]` | 1–3 | Your past analyses |
| POST | `/analyze/history/{id}/feedback` | 1–3 | "Was this right?", the labelled data used for calibration |
| GET | `/analyze/history/{id}/report` | Report | Complaint summary (English, for the police portal) + steps for 1930, cybercrime.gov.in, Chakshu, bank, SEBI SCORES |
| POST | `/analyze/history/{id}/reported` | Report | Mark that the user started reporting (impact metric, XP) |
| POST | `/chat` | RAG | Grounded safety assistant |
| GET | `/chat/history` | RAG | Conversation history |
| POST | `/voice/chat` | 5 | Audio → Whisper → Ollama → Coqui TTS |
| GET | `/dashboard` | Dash | Safety score, scan history, learning, alerts, awareness trend |
| GET | `/progress` | 6 | Learning progress and streaks |
| GET | `/alerts` | Dash | Safety alerts (`/alerts/{id}/read`, `/alerts/read-all`) |
| GET | `/learning/courses[/{id}]` | 6 | Courses and lessons |
| POST | `/learning/lessons/{id}/complete` | 6 | Mark a lesson complete (`GET` lesson takes `?language=` for a translated copy) |
| POST | `/learning/questions/{id}/check` | 6 | Check one quiz answer instantly (practice mode, XP on first correct) |
| GET | `/learning/courses/{id}/flashcards` | 6 | Flash cards |
| POST | `/learning/courses/{id}/flashcards/practised` | 6 | The user flipped cards today (learning streak, XP once a day) |
| GET/POST | `/learning/courses/{id}/assessment[/submit]` | 6 | Quiz (answers hidden) and grading |
| POST | `/learning/generate` | 6 | gemma2 lesson / flash cards / quiz / simplification grounded by RAG |
| GET | `/habits` | 4 | Safety Score (300-900), today's goals, Scam Drill, Safety Shield, weekly challenge, streaks, emergency fund, nudges |
| GET | `/habits/drill` | 4 | Today's 3 drill messages |
| POST | `/habits/drill/answer` | 4 | Answer `scam` / `genuine`; explanation, highlighted words, XP |
| PUT | `/habits/shield/{key}` | 4 | Mark a Safety Shield step done |
| POST | `/habits/weekly-challenge` | 4 | Complete this week's challenge (+40 XP) |
| PUT | `/habits/checklist/{key}` | 4 | Tick an emergency-fund checklist item |
| POST | `/habits/savings-checkin` | 4 | Weekly yes/no savings check-in (no amounts) |
| PUT | `/habits/emergency-fund` | 4 | Emergency-fund goal + saved so far (the user's own numbers, never advice) |
| GET/POST/PATCH/DELETE | `/contacts[/{id}]` | Family | Up to 5 trusted contacts, one primary |
| POST | `/help/alert` · GET `/help/history` | Family | "Get Help": SMS trusted contacts (+ optional location) and show 1930 / 112 |
| GET · PUT | `/family/readiness[/{item}]` · GET `/family/readiness/summary` | Family | Nominee & family-readiness checklist (no numbers or amounts stored) and a shareable summary |
| POST | `/voice/command` | Voice | Voice navigation: phrase (text or audio) in any of the 12 languages → app command |
| GET | `/gamification` | Rewards | XP, level, achievements (locked / unlocked / claimed) |
| POST | `/gamification/achievements/{key}/claim` | Rewards | Claim an unlocked badge for its XP |
| GET | `/activity/heatmap` · `/activity/recent` | Rewards | 14-week activity heatmap and recent XP events |
| GET | `/tasks/{task_id}` | — | Poll an async scan |
| GET | `/me/export` | — | Download your data as JSON |
| GET | `/privacy` · POST `/me/consent` | Privacy | Plain-language privacy notice (12 languages) and consent; content endpoints return 428 until accepted |
| GET/PATCH | `/admin/users…`, `/admin/audit-logs` | Admin | RBAC-protected administration |
| POST | `/admin/knowledge/ingest` | Admin | Re-index every knowledge document |
| GET/POST/DELETE | `/admin/knowledge/documents[/{id}[/reingest]]` | Admin | List, upload, re-index or remove documents |
| POST | `/admin/knowledge/fetch` | Admin | Download and index official documents (one URL, or `sources.json`) |
| GET | `/admin/feedback[/export]` | Admin | Review user feedback, export the labelled JSONL |
| GET | `/admin/impact` | Admin | Anonymous impact numbers: checks by risk level, reports started, family alerts, quiz scores, users by language |
| GET | `/metrics` | Ops | Prometheus metrics (optionally behind `METRICS_TOKEN`; blocked by Caddy) |

### Examples

```bash
API=http://localhost:8000
TOKEN=$(curl -s -X POST $API/auth/register -H 'Content-Type: application/json' \
  -d '{"name":"Asha","email":"asha@example.com","password":"Passw0rd!x","language":"hi"}' | jq -r .access_token)

# Module 2 - WhatsApp message
curl -s -X POST $API/analyze/message -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message_text":"Guaranteed 5% daily returns! Only 3 slots left. Pay Rs 999 to win@ybl"}' | jq

# Module 1 - screenshot
curl -s -X POST $API/scan/image -H "Authorization: Bearer $TOKEN" -F file=@whatsapp.png -F language=en | jq

# Module 3 - YouTube transcript
curl -s -X POST $API/analyze/social -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"platform":"youtube","text":"This multibagger will go to the moon 🚀🚀 I turned 10k into 5 lakh!"}' | jq '.segments'

# Module 5 - voice (Hindi)
curl -s -X POST $API/voice/chat -H "Authorization: Bearer $TOKEN" -F audio=@question.wav -F language=hi \
  | jq -r .audio_base64 | base64 -d > answer.wav
```

Sample `/analyze/message` response (abridged):

```json
{
  "risk_score": 98,
  "risk_level": "critical",
  "warning_flags": [
    {"key": "guaranteed_returns", "label": "Guaranteed returns", "category": "guaranteed_returns",
     "reason": "Promises guaranteed or risk-free returns...", "evidence": ["Guaranteed 5% daily returns"]}
  ],
  "explanation": "This looks like a scam...",
  "safe_practices": ["Treat any promise of guaranteed or fixed high returns as a red flag.", "..."],
  "highlights": [{"start": 0, "end": 27, "text": "Guaranteed 5% daily returns", "label": "Guaranteed returns"}],
  "engine": {"rule_score": 98, "llm_score": 95, "llm_used": true, "model": "llama3.1:8b"},
  "disclaimer": "Suraksha AI provides scam-awareness and financial-literacy information only..."
}
```

---

## Modules

* **Link Checker (3):** `POST /analyze/link` takes a link to an Instagram reel or post, a YouTube
  video or short, a Telegram channel or post, an X post, a WhatsApp chat or group invite, or any web
  page. The server opens it (`backend/ai/link_fetcher.py`) and reads the title, author, caption or
  description, the spoken words (YouTube subtitles, or a local Whisper transcript of short videos in
  the voice build) and the page text. It never logs in: when a platform hides a post behind a login,
  the result says so and suggests pasting the caption or a screenshot. Every request is SSRF-guarded:
  http(s) on ports 80/443 only, private / loopback / link-local addresses refused at every redirect,
  12 s timeout, 2 MB cap. Deterministic fact checks (`backend/ai/link_checks.py`) then test the claims:
  promised returns are compounded to a yearly figure ("3% daily" is about 48 lakh % a year), "turned
  10k into 5 lakh in 2 weeks" stories are checked the same way, SEBI-registration claims without an
  INA / INH number fail, trading calls without registration are flagged, payment to a personal UPI ID
  fails (a SEBI `@valid` handle passes), private WhatsApp / Telegram funnels and celebrity
  endorsements are flagged, and shortened links are followed to their real destination. The local LLM
  gets these checks as facts and returns a verdict, the claims it found with an assessment (false,
  misleading, unverifiable, plausible), red flags with quoted evidence, genuine signals and next steps.
  As everywhere, the AI can raise the rules score but never lower it, and advice sentences are removed.
  `yt-dlp` (metadata and subtitles, no download) is used for YouTube, Instagram and X when available.
  The caption / transcript analyzer is still available as "Paste text instead".
* **Message scanner without copy-paste (2):** one-tap *Paste & scan* (clipboard), pasting or dropping
  a screenshot straight into the box, *Screenshot* upload (`POST /analyze/message-image`: OCR in
  memory, the image is never stored), and *Speak it* (browser speech recognition). A pasted link is
  sent to the Link Checker automatically.
* **Safety Habits (4):** the habit tracker is built around what the user actually does, not
  self-ticked boxes (`backend/services/safety_service.py`):
  * **Suraksha Safety Score, 300 to 900** (read like a credit score): Safety Shield 30%, scam-spotting
    skill 20% (30-day drill accuracy, scaled by practice), daily consistency 15%, scam awareness 15%,
    checks before trusting 10% (scans in the last 30 days) and family & money readiness 10%
    (trusted contact, Family Readiness, emergency fund). Bands: At risk, Building up, Good,
    Excellent. A weekly history shows "+24 since last week", and "Raise your score" lists the actions
    worth the most points.
  * **Daily Scam Drill:** three real-style Indian messages a day (`backend/seed/drills.json`, 36
    scams and genuine bank / government messages), always at least one scam and one genuine.
    Answer *Scam* or *Genuine* and see why, with the suspicious words highlighted by the rules
    engine. 10 XP per correct answer, +25 for finishing; drill streak and 30-day accuracy.
  * **Safety Shield:** ten one-time protection steps with how-to and official links: OTP pledge,
    WhatsApp two-step verification, UPI daily limit, Sanchar Saathi number check, Aadhaar biometric
    lock, transaction alerts, email 2-step verification, removing screen-sharing apps, saving 1930,
    and a trusted contact (detected automatically).
  * **Today's goals:** Scam Drill, learn for 2 minutes, check before you trust, with a 7-day view,
    all tracked automatically. Opening the app no longer counts as practising flash cards; only
    flipping one does (`POST /learning/courses/{id}/flashcards/practised`).
  * **Weekly challenge** (+40 XP): one real-world action, e.g. teach a parent that banks never ask
    for OTPs, or report a spam call on Chakshu.
  * New badges: Sharp Eye (30 correct drill answers), Drill Streak (7 days), Fully Shielded.
  * Still included: emergency-fund checklist and goal, weekly savings check-ins, learning streak and
    rule-based nudges (optional gemma2 nudge with `?ai_nudge=true`, passed through the guardrail).
* **Senior tools only for seniors:** the Senior-mode switch and the "Elderly Protection" page are
  shown to users who signed up as senior citizens. Everyone else sees **Family Safety** (trusted
  contacts, Get Help, scam warnings) to protect their parents and grandparents, and can turn on
  *Larger text* in Settings.
* **Voice (5):** Whisper (`WHISPER_MODEL`, default `base`) transcribes all 12 languages. Coqui VITS
  speaks English replies and XTTS-v2 speaks Hindi; other languages need a voice in
  `TTS_CUSTOM_MODELS`, otherwise replies come back as text with `tts_note` explaining why (see
  [12 Indian languages](#12-indian-languages)). XTTS-v2 is
  released under the Coqui Public Model License (non-commercial). The image sets
  `COQUI_TOS_AGREED=1`, so review that licence before any commercial use.
* **Read aloud (web app):** replies are spoken by the device's own voice, chosen by script (Devanagari
  → Hindi voice, otherwise Indian English; Google / Microsoft Natural voices preferred), in
  sentence-sized chunks so long answers are not cut off, with markdown, emoji and full URLs removed.
  If the device has no voice for the language (e.g. Windows without a Hindi voice), the app uses the
  server's Coqui voice (`GET /voice/tts` reports availability, `POST /voice/tts` returns WAV).
  `tests/e2e/read_aloud.py` checks both paths in a browser.
* **Learning centre (6):** four seeded courses (Scam Detection, UPI Frauds, Cyber Safety, Financial
  Literacy) with 12 lessons, flash cards and assessments. Completion is 80% lessons and 20% for a
  passed quiz (≥ 60%). Progress lives in `learning_progress` and `quiz_attempts`. Educators
  (`educator` role) can save AI-generated content into courses.
  The web app adds three **story lessons** (narrated slide stories: fake trading apps, UPI
  collect-request fraud, deepfake finfluencers) and a product walkthrough behind **Watch Demo**.
  They run offline, with captions always shown and narration from the browser's built-in voice
  (Hindi needs a Hindi voice installed, e.g. Windows Settings → Time & language → Speech). Each
  story ends with links to official sources: RBI Kehta Hai, SEBI investor education, Cyber Dost
  (I4C) and cybercrime.gov.in.
* **Dashboard:** safety score = 30% learning + 25% quiz performance + 20% habits + 25% vigilance
  (recent scans and alerts read), plus scan history by level, recent alerts and an 8-week awareness
  trend.

---

## Phone login, family protection, elder mode, rewards and languages

### Phone + OTP login

* `POST /auth/phone/request-otp` → `POST /auth/phone/verify` signs a user in, or creates the account
  on first use (optional `name`, `language`, `city`, `user_type`). Numbers are normalised to E.164 (`DEFAULT_COUNTRY_CODE=91`).
  Email becomes optional; phone-only users can add an email later via `PATCH /auth/me`.
* OTPs are 6 digits, valid 5 minutes, stored in Redis only as an HMAC (keyed by `SECRET_KEY`), burned
  after 5 wrong attempts, with a 60 s resend cooldown and at most 5 per number per hour. If Redis is
  down, OTP login **fails closed** (503) rather than skipping checks. Requesting a code behaves the
  same whether or not the number already has an account.
* `SMS_PROVIDER` picks the gateway: `console` (log), `email_bridge` (development: each SMS appears in
  Mailpit as mail to `<number>@sms.suraksha.local`, the compose default), `webhook` (POST JSON to any
  gateway, including a self-hosted Android SMS gateway, which costs nothing), `twilio`, `msg91` or
  `fast2sms`. SMS is sent by the Celery worker with retries. **Commercial SMS to Indian numbers needs
  DLT registration** (entity, sender ID and approved templates) with your provider.

### Trusted contacts and "alert family"

* Up to 5 contacts with a relationship and one primary. Adding a contact sends them a courtesy SMS so
  they know who listed them.
* `POST /help/alert` (the app's **Get Help** button) texts every contact, optionally with a Google
  Maps link if the user shares location, and always returns the official helplines (1930 cyber
  crime, 112 emergency) plus a "call your primary contact" link. Limit: 3 alerts per 10 minutes.
* **Automatic alerts:** when a scan comes back *critical* (or *high* in elder mode), contacts get an
  SMS naming the risk category and asking them to call, at most once every 6 hours. This is on by default in elder mode and opt-in
  otherwise (`auto_alert_family` preference). The SMS never includes the scanned message itself.
* All alerts are logged in `help_requests` (`GET /help/history`).

### Elder mode and preferences

`/me/preferences` stores theme, text size, voice navigation, TTS autoplay, notification and privacy
switches. Turning on `elder_mode` also turns on large text and spoken answers unless the user chose
otherwise. Picking user type `senior_citizen` at sign-up switches it on. In elder mode:

* scan responses carry a `simple_verdict` (one short sentence, a single action and who to call),
  which the web app shows in big print with a "Call <contact>" button;
* chat answers are shorter and simpler;
* high-risk results also alert family automatically (above).

`auto_delete_scans` purges a user's analyses and uploads after 24 hours (hourly Celery job), and
`weekly_report` sends a short weekly summary.

### XP, levels and achievements

Learning and safe behaviour earn XP: lesson 50, passed quiz 100, first correct answer 20, daily
learning 25, flash cards 15, emergency-fund step 30, savings week 20, trusted contact 50, verified
email/phone 50, scans 10 (max 5 a day), chat 5 (max 3 a day), feedback 5. Each award is recorded
once in `xp_events` (unique per user, action and reference), so replaying a request cannot farm XP.
Ten levels run from *Beginner* (0) to *Suraksha Hero* (9,000). Thirteen achievements (First Check,
Scam Spotter, Week Warrior, Family Shield, Quiz Ace and so on) unlock automatically and are claimed for bonus
XP. The dashboard includes the level and recent activity.

### Languages

* **Web app interface: Hindi and English.** Every screen, button, message, detector reason, quiz and
  lesson title is translated (`frontend/i18n/hi.json`, about 800 strings).
* **API and AI: 12 languages.** English, Hindi, Gujarati, Marathi, Tamil, Bengali, Telugu, Kannada,
  Malayalam, Punjabi, Odia and Assamese (`GET /languages`): answers, guardrails, privacy notice,
  report steps, readiness tips, voice commands and SMS. Adding another interface language means
  adding one `frontend/i18n/<code>.json` and the language to `LANGS` in `index.html`.

* **AI replies:** the analysis explanation, chat and lessons are generated in the user's language.
  Lesson translations are produced once by gemma2 and cached in `lesson_translations`.
  `OLLAMA_LANGUAGE_MODELS` can route a language to a different local model.
* **Fixed strings** (refusals, verdicts, OTP and alert SMS, level names) live in
  `backend/i18n/strings/<code>.json`. English and Hindi are reviewed; **the other ten are drafts
  that need review by native speakers** before launch, and are marked so in each file.
* **OCR:** the image ships Tesseract data for all 12 scripts. Each scan loads English + Hindi + the
  user's script.
* **Speech-to-text:** Whisper handles all of them; Odia has no Whisper language code, so it
  auto-detects (`small` or larger is recommended for Indic languages).
* **Text-to-speech:** English and Hindi are built in. For the others, add a Coqui-compatible voice
  (for example AI4Bharat Indic-TTS) with `TTS_CUSTOM_MODELS`; otherwise the reply comes back as
  text with a `tts_note`, and the web app uses the device's own speech synthesis.
* Emails (verification, reset) are in English or Hindi; other languages get English for now.

---

## Trust, privacy and safety

### Guardrails in every language

`backend/ai/guardrails.py` combines precise English / Hinglish / Hindi patterns with a multilingual
lexicon (`backend/ai/guardrail_lexicon.py`) of product, buy/sell, "which / best / should" and
price-movement words in all 12 scripts. "कौन सा शेयर खरीदूं?", "எந்த பங்கை வாங்க வேண்டும்?" or
"Nifty kal upar jayega?" are refused before the LLM runs; "they say this share will double tomorrow,
is it a fraud?" is still answered, because scam-checking and verification context is exempt. Model
output is checked sentence by sentence: advice-like sentences are removed (or the whole answer is
replaced by the refusal), while safety guidance such as "never buy on WhatsApp tips" is kept.
`tests/test_guardrails_multilingual.py` covers every language. The word lists need review by native
speakers.

### What the regulators say (official guidance on results)

Every risky result carries up to three short statements from Indian authorities, each linked to the
official source: SEBI (no guaranteed returns, registered advisers only, SEBI-name impersonation,
"@valid" UPI handles), RBI (BUDS Act / Sachet, forex Alert List, "banks never ask for OTP",
customer liability for unauthorised transactions), NPCI (no PIN to receive money), I4C (no "digital
arrest") and DoT (Chakshu). They are picked deterministically from the rule signals in
`backend/ai/official_guidance.py`, never generated. The same statements are given to the LLM as the
*only* regulations it may cite, so explanations can say "SEBI says..." without inventing rules,
circular numbers or dates. The chat assistant gets them through the knowledge base
(`09_official_guidance_quick_reference.md`). The statements are paraphrases, written in English and
Hindi (other languages are drafts); the linked official pages are authoritative, so review the file
when regulators update their guidance.

### Sensitive numbers and retention

`backend/utils/redact.py` masks OTPs, UPI PINs, CVVs, card numbers (Luhn-checked), Aadhaar, PAN,
bank account numbers and passwords with `••••` right after text cleaning, so they never reach the
rule engine, the LLM, the database, logs or responses. Phone numbers, UPI IDs and links are kept,
because they identify the scammer and are needed for a report. Each result says what was hidden
(`privacy.redacted`). Chat questions, feedback comments and Get Help notes are redacted the same way.

* Screenshots and PDFs are deleted as soon as their text is read (`uploaded_files.deleted_at`).
* An hourly job deletes any leftover upload after 24 hours and analyses after
  `ANALYSIS_RETENTION_DAYS` (default 180). Users can choose 24-hour deletion in Settings.

### How sure are we?

Every scan, message and social analysis returns `confidence`: a level (high / medium / low), the
reasons in the user's language (AI unavailable, rules and AI disagree, very short text, score near a
boundary, little text read from an image, language with few rule phrases), a plain warning that the
result can be wrong, and where to verify (1930, cybercrime.gov.in, SEBI's intermediary list). The
web app shows this on every result, including offline checks (always "low").

### Consent and privacy notice

`GET /privacy?language=hi` returns the notice in any of the 12 languages. Sign-up requires ticking
it (`consent: true`); existing users see it once (`POST /me/consent`). Until then, scan, analyze,
chat, voice and family endpoints return **428** `consent_required`, so no personal content is
processed without authorization. Bump `CONSENT_VERSION` when the notice changes to ask everyone
again.

### Report this scam

Medium-or-higher results have a **Report this scam** button. It shows the official steps (call 1930
within the first hours if money was lost, cybercrime.gov.in, Sanchar Saathi Chakshu, the bank,
SEBI SCORES for adviser frauds) and a ready-to-paste English complaint summary with the scammer's
phone numbers, UPI IDs and links (the user's own numbers stay masked). Suraksha AI never files a
complaint itself.

### Family readiness (nominees)

A checklist for 11 kinds of holdings (bank, FD, demat, mutual funds, insurance, EPF/PPF, NPS, post
office, locker, property papers, will): is a nominee recorded, does the family know where the papers
are. No account numbers, amounts or nominee details are stored, and notes are redacted. The tips
are awareness only, with a clear "not legal or financial advice" notice and a pointer to RBI's UDGAM
portal for forgotten deposits. **Share with family** produces a plain-text summary for WhatsApp/SMS.

### Voice navigation

With **Voice Navigation** on (Senior Safety screen), each screen is read aloud in the user's
language and a floating **Say a command** button listens for commands such as "संदेश जाँचो",
"मदद", "पढ़कर सुनाओ" or "check message". Browser speech recognition is used where available;
otherwise a 4-second recording is transcribed by Whisper. Commands are understood in all 12
languages (`backend/voice/commands.py`). "Help" opens Get Help and asks the user to press it; it
never sends an alert on its own.

---

## Web app (`frontend/`)

The design prototype is now a working app served by nginx on http://localhost:3000. It talks to the
API through `/api` on the same origin, so no CORS setup is needed, and refreshes tokens
automatically. Every screen is wired: phone/OTP, email and Google sign-in, password reset and email
verification links, dashboard, scan (text, screenshot, PDF), WhatsApp and social analyzers, chat,
voice, learning with quizzes, habits, trusted contacts and Get Help, rewards, alerts, settings and
elder mode.

* React, ReactDOM and all fonts (Poppins, Noto Sans Devanagari, Material Symbols) are vendored
  under `frontend/vendor/`, so the page makes **no third-party requests**. nginx sets a strict CSP
  and blocks `/api/metrics`.
* **Low bandwidth:** a first visit transfers about **410 KB** (it was about 6 MB). The icon font is
  cut to the ~140 icons the app uses (5.3 MB → 154 KB, `scripts/subset_icons.py`), nginx gzips all
  text, and the Hindi dictionary (28 KB compressed) loads only when Hindi is chosen. To add icons,
  download the full font (`material-symbols` npm package, `material-symbols-rounded.woff2`) and
  re-run the script.
* **Translation runtime** (`frontend/i18n.js`): translates the rendered page in place from
  `i18n/<code>.json`, keeps it translated as React re-renders, and never touches inputs, user
  messages, AI answers or complaint summaries (`translate="no"`).
* `frontend/docker-entrypoint.d/40-suraksha-config.sh` writes `config.js` at container start
  (`GOOGLE_CLIENT_ID`, API base).
* With the `https` profile, Caddy serves the web app on `DOMAIN` and the API under `/api`.

---

## Accounts: email verification and password reset

* On registration a verification link is emailed to `{FRONTEND_URL}/verify-email?token=…`. Your
  frontend posts the token to `/auth/verify-email/confirm`. Set `REQUIRE_EMAIL_VERIFICATION=true` to
  block password logins until the email is verified. Google accounts count as verified.
* `POST /auth/password/forgot` always answers the same way, so it cannot be used to discover which
  emails have accounts. Reset links are **single-use**, expire after 60 minutes, are stored only as
  SHA-256 hashes, and any older link stops working when a new one is requested. Each user can receive
  at most one email per minute.
* A reset or change sets `users.tokens_valid_after`, which rejects **every existing access and
  refresh token** ("sign out everywhere"). A "your password was changed" email follows.
* Emails are sent by the Celery worker with retries, in English or Hindi based on the user's
  language; other languages get English for now. Delivery goes to Mailpit by default; set
  `SMTP_*` for a real provider (any SMTP service, e.g. Gmail with an app password, Zoho, Brevo or
  Amazon SES), and set `FRONTEND_URL` to your public domain so links point at it.

---

## Operations

### Monitoring (`--profile monitoring`)

* `/metrics` exposes Prometheus metrics in multi-process mode across uvicorn workers: request rate
  and latency per route, analyses by source and risk level, Ollama call outcomes and latency, RAG
  hit rate, email, auth and guardrail-block counters.
* Prometheus (`127.0.0.1:9090`) loads alert rules from `deploy/prometheus/alerts.yml`: API down, 5xx
  above 5%, Ollama failing above 20%, p95 analysis latency above 60 s, and RAG rarely grounding.
  Hook up Alertmanager to receive notifications.
* Grafana (`127.0.0.1:3001`, user `admin`, password `GRAFANA_ADMIN_PASSWORD`) comes with the
  "Suraksha AI - Overview" dashboard already provisioned.
* Limitation: metrics from the Celery worker process (async scans, ingestion) are not scraped yet.

### Backups

`db-backup` waits `BACKUP_INITIAL_DELAY_SECONDS` (15 minutes), then every 24 hours writes a verified
`pg_dump` and tarballs of the `uploads` and `knowledge` volumes to `./backups`. It keeps 7 days.
ChromaDB is not backed up because it is rebuilt from the documents (`POST /admin/knowledge/ingest`).

**Off-machine copies (`--profile offsite`).** `backup-offsite` runs `rclone copy` of `./backups` to
`BACKUP_REMOTE` every hour (`OFFSITE_INTERVAL_SECONDS`) and deletes remote copies older than
`BACKUP_REMOTE_RETENTION_DAYS` (30). The remote is configured entirely with `RCLONE_CONFIG_*`
variables in `.env`, so any rclone backend works: S3, Backblaze B2, Cloudflare R2, Google Drive,
SFTP and so on (see `.env.example`). Test it once with
`docker compose --profile offsite run --rm backup-offsite --once`.

```bash
docker compose run --rm db-backup sh /scripts/backup.sh --once           # backup now
docker compose stop backend worker
docker compose run --rm db-backup sh /scripts/restore_db.sh /backups/suraksha-db-<timestamp>.dump
docker compose start backend worker
```

### HTTPS (`--profile https`)

Point your domain's DNS at the server, then set `DOMAIN`, `ACME_EMAIL`, `API_BIND=127.0.0.1` and
`FORWARDED_ALLOW_IPS=*` in `.env` and run `docker compose --profile https up -d`. Caddy obtains and
renews Let's Encrypt certificates, redirects HTTP to HTTPS, adds HSTS, and hides `/metrics`. With
`DOMAIN=localhost` it uses its own local CA, which is useful for testing.

### CI (`.github/workflows`)

* `ci.yml` runs on every push and PR: ruff lint and format, 254 tests including the detection quality
  gate, a risk-evaluation report artifact, migrations upgrade → downgrade → upgrade → drift check on
  PostgreSQL 16, and a Docker build. It then brings up the stack and runs the smoke test, a Mailpit
  delivery check, a backup/restore round trip, and a Playwright browser test of the web app
  (`tests/e2e/ui_flow.py`: OTP sign-up with consent via Mailpit, scan with confidence, report sheet,
  trusted contact + Get Help, voice navigation, family readiness, level, quiz, alerts, Hindi
  interface). A screenshot is uploaded as an artifact. A dependency audit (`pip-audit`) runs as advisory.
* `voice-image.yml` builds the full voice image (PyTorch, Whisper, Coqui) weekly, on demand, and when
  its dependencies change. It checks the imports and runs a real Whisper transcription.
* Dependabot keeps pip, Docker and Actions dependencies current.

---

## Security

| Control | Implementation |
|---|---|
| JWT authentication | HS256 access (30 min) and refresh (7 days) tokens with `jti`, issuer check, refresh rotation, Redis revocation list on logout |
| Consent | Privacy notice accepted before any content is processed (428 otherwise); version stored per user |
| Sensitive data | OTP / PIN / CVV / card / Aadhaar / PAN / account numbers / passwords masked before analysis, storage and logs; screenshots deleted after text extraction; analyses expire after 180 days |
| Phone OTP | HMAC-hashed codes in Redis, 5-minute expiry, attempt limit, resend cooldown, hourly cap per number, fails closed without Redis |
| Google OAuth | ID token verified with `google-auth` against `GOOGLE_CLIENT_ID`; verified email required |
| Passwords | bcrypt (cost 12), strength rules, timing-safe login (dummy hash for unknown users) |
| Rate limiting | slowapi + Redis, keyed by user ID or IP; stricter limits for auth, AI and uploads |
| Input validation | Pydantic schemas with length limits and enums; validation errors never echo input |
| File validation | Size caps, extension allow-list, **magic-byte sniffing**, Pillow verify, decompression-bomb guard, encrypted-PDF rejection, random server-side filenames, path-traversal guard |
| RBAC | `user` < `educator` < `admin` roles with permission sets (`backend/security/rbac.py`) |
| SQL injection | SQLAlchemy ORM / bound parameters only |
| XSS | HTML stripped from stored user text (nh3), strict CSP, `nosniff`, `X-Frame-Options: DENY`; JSON-only API |
| Audit logs | Every state-changing request (user, IP, path, status, request ID) plus auth and admin events in `audit_logs` |
| Prompt injection | User content is fenced as data in prompts, and LLM JSON is schema-checked and clamped |
| Containers | Non-root user, `init: true` (tini), health checks, CPU-only torch |

**Production checklist:**

* Set `ENVIRONMENT=production` and a random `SECRET_KEY`. The app refuses to start without one.
* Change the Postgres, admin and Grafana passwords.
* Restrict `CORS_ORIGINS`.
* Enable the `https` profile with `API_BIND=127.0.0.1`.
* Configure real SMTP and consider `REQUIRE_EMAIL_VERIFICATION=true`.
* Choose a real `SMS_PROVIDER` (with DLT registration for Indian numbers).
* Enable the `offsite` profile so backups leave the machine.
* Have native speakers review the draft translations in `backend/i18n/strings/`, the guardrail word
  lists, and the Hindi interface (`frontend/i18n/hi.json`).
* Have a lawyer review the privacy notice against the DPDP Act 2023 before launch.
* Turn on the `monitoring` profile and connect alerting.
* Replace the bundled knowledge summaries with official documents.

---

## Development

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
pytest                      # 254 tests: rule engine + quality gate, guardrails (12 languages), redaction,
                            # confidence, consent, report, readiness, voice commands, API, accounts,
                            # knowledge, phone OTP, family alerts, elder mode, rewards, languages, Hindi UI
BASE_URL=http://localhost:3000 python tests/e2e/ui_flow.py   # browser test against a running stack (Playwright)
ruff check backend tests scripts
PYTHONPATH=. DATABASE_URL=sqlite:// python scripts/evaluate_risk.py --calibrate   # detection report

# run against local services
export DATABASE_URL=postgresql+psycopg://suraksha:suraksha@localhost:5432/suraksha REDIS_URL=redis://localhost:6379/0 \
       OLLAMA_BASE_URL=http://localhost:11434 CHROMA_HOST=localhost UPLOAD_DIR=./uploads
alembic -c backend/alembic.ini upgrade head && python -m backend.seed.seed
uvicorn backend.main:app --reload
```

### Database migrations

Alembic lives in `backend/database/migrations`. `0001_initial_schema` creates all 15 tables: users,
scam_analyses, uploaded_files, learning_progress, chat_history, safety_alerts, audit_logs, courses,
lessons, flashcards, assessment_questions, quiz_attempts, user_activity, habit_checklist and
savings_checkins. `0002_accounts_knowledge_feedback` adds `auth_tokens`, `knowledge_documents`,
`analysis_feedback` and the user columns `email_verified`, `email_verified_at` and
`tokens_valid_after`, and marks existing Google accounts as verified.
`0003_phone_family_elder_rewards_languages` makes email optional and adds `phone`, `phone_verified`,
`city`, `user_type`, `preferences` and `xp` to users, plus `emergency_contacts`, `help_requests`,
`xp_events`, `user_achievements` and `lesson_translations`.
`0004_privacy_consent_report_readiness` adds `users.consent_version` / `consent_at`,
`uploaded_files.deleted_at`, `scam_analyses.reported_at` and the `readiness_items` table; existing
users are asked for consent once. `0005_user_state` adds `users.state` (Indian state / UT, picked
from the sign-up dropdown; the list lives in `backend/utils/india.py`). The container runs
`alembic upgrade head` on every start. To create a new
revision: `alembic -c backend/alembic.ini revision --autogenerate -m "describe change"`.

### Project structure

```
backend/
  main.py               FastAPI app, middleware, error handlers
  config.py             settings (env vars)
  api/                  router aggregation, auth/RBAC dependencies
  routers/              auth, scan, analyze, chat, voice, dashboard, learning, habits, family,
                        gamification, admin, system
  services/             business logic (scan, chat, learning, habits, dashboard, alerts, audit, files,
                        otp, sms, family, preferences, gamification, maintenance, report, readiness)
  i18n/                 12 languages + translated strings (strings/<code>.json)
  models/               SQLAlchemy models
  schemas/              Pydantic request/response models
  database/             engine/session, declarative base, Alembic migrations
  ai/                   Ollama client, prompts, rule patterns, risk engine, URL analysis, guardrails
                        (+ guardrail_lexicon for 12 languages), confidence
  ai/eval/              labelled dataset + evaluation / calibration
  ocr/                  Tesseract + PyMuPDF
  voice/                Whisper STT, Coqui TTS, voice-navigation commands
  rag/                  loaders (pdf/md/txt/html), chunker, ingest, fetcher, ChromaDB store, retriever,
                        knowledge/ (bundled docs), sources.json (official documents to fetch)
  security/             JWT, passwords, rate limit, RBAC, sanitisation, file validation, middleware
  workers/              Celery app and tasks
  seed/                 learning curriculum + seeder
  utils/                logging, Redis cache, text cleaning, redaction, Prometheus metrics
frontend/               web app (index.html + support.js), i18n.js + i18n/hi.json, vendored libraries
                        and fonts, nginx config
scripts/                start.sh, start_worker.sh, pull_models.sh, wait_for_db.py, ingest_knowledge.py,
                        evaluate_risk.py, backup.sh, restore_db.sh, offsite_sync.sh, smoke_test.py,
                        subset_icons.py
deploy/                 Caddyfile, Prometheus config + alert rules, Grafana provisioning + dashboard
tests/                  pytest suite, e2e/ui_flow.py (Playwright)
.github/                CI workflows, Dependabot
docker-compose.yml      postgres, redis, ollama (+init), chromadb, backend, worker, frontend, mailpit,
                        db-backup (+ prometheus, grafana, caddy, backup-offsite via profiles)
```

## Troubleshooting

* **`engine.llm_used` stays false.** The models are still downloading. Check
  `docker compose logs ollama-init` and `/health/ready`.
* **The first LLM call is slow.** On CPU, loading a model takes 20–60 s. `OLLAMA_KEEP_ALIVE` keeps it
  in memory afterwards.
* **Voice returns 503.** The image was built with `INSTALL_VOICE=false`, or the first request is
  still downloading Whisper or TTS weights into the `models` volume.
* **`knowledge_chunks: 0`.** Wait for `nomic-embed-text` to download, or trigger
  `POST /admin/knowledge/ingest`.
* **No emails arrive.** Check http://localhost:8025 (Mailpit) and `docker compose logs worker`. For a
  real provider, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` and `SMTP_STARTTLS`.
* **No OTP arrives.** With the default `email_bridge` provider it is in Mailpit
  (http://localhost:8025). Otherwise check `docker compose logs worker` for the gateway's error.
  A 429 means the per-number cooldown or hourly cap was hit.
* **A knowledge document shows `failed`.** The `error` column says why, for example a scanned PDF with
  OCR unavailable. Fix it and call `/admin/knowledge/documents/{id}/reingest`.

## SANGYAN evaluation criteria → where to look

| Criterion | What Suraksha AI does |
|---|---|
| Investor resilience & safety | 22 scam detectors + local LLM on screenshots, PDFs, WhatsApp and social posts; one-tap report-to-1930 flow; Get Help family alerts; automatic family alert on dangerous scans; learning, quizzes and habit coach; nominee / family-readiness checklist |
| Bharat-first usability & accessibility | Hindi + English interface; AI answers, guardrails and voice commands in 12 languages; voice assistant and voice navigation; elder mode (large text, simple verdicts, high contrast); phone + OTP login; ~410 KB first load; falls back to on-device rules when the server is unreachable |
| Trust, privacy & guardrails | Advice / price-prediction guardrails in 12 languages; confidence and "how to verify" on every result; sensitive numbers masked; screenshots deleted after reading; consent before processing; all AI local; no monetisation, broker links or product promotion |
| Technical execution & feasibility | `docker compose up`, 254 tests + browser e2e in CI, migrations, monitoring, backups, HTTPS profile; runs on a 16 GB PC with an 8 GB GPU; rule engine works with no GPU at all |
| Impact & scalability | `/admin/impact` (checks, reports, family alerts, quiz scores, users by language); stateless API behind Redis / Celery; more interface languages by adding one dictionary file |

Known limits: detection accuracy is measured only on a small hand-written set (132 messages); the
Hindi interface and the 12-language word lists need native-speaker review; the privacy notice needs
legal review.

## Helplines surfaced to users

National Cyber Crime Helpline **1930** · cybercrime.gov.in · SEBI SCORES · RBI Sachet · RBI
Integrated Ombudsman (cms.rbi.org.in) · Sanchar Saathi Chakshu.
