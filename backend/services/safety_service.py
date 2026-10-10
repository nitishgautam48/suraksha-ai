"""Suraksha Safety Score and daily safety habits: the habit tracker's core.

Everything here is tracked from what the user actually does in the app, not from self-ticked boxes:
  * Daily Scam Drill: 3 real-style messages a day, "scam or genuine?", explained right after.
  * Safety Shield: one-time protection steps (WhatsApp two-step, UPI limit, Sanchar Saathi, ...).
  * Daily goals: drill, learn for 2 minutes, check before you trust (scan / link check).
  * Weekly challenge: one real-world action a week (teach a parent, report a spam call...).
  * Suraksha Safety Score (300-900, read like a credit score): combines all of the above.
No step recommends any financial product; it only builds scam-safety behaviour.
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.ai.risk_engine import analyze_rules
from backend.models import EmergencyContact, HabitChecklistItem, ScamAnalysis, User, UserActivity, XPEvent
from backend.services.activity_service import LEARNING_KINDS, record_activity, streaks
from backend.services.gamification_service import award

DRILLS_FILE = Path(__file__).resolve().parent.parent / "seed" / "drills.json"
DRILLS_PER_DAY = 3

# key, title, why it matters, how to do it, official link, auto (detected by the app)
SHIELD: tuple[dict[str, Any], ...] = (
    {"key": "sec_otp_pledge", "icon": "pin", "title": "Take the pledge: I never share OTP, PIN or CVV",
     "why": "Every bank fraud ends with a code you were tricked into sharing.",
     "how": "Tap Done to take the pledge. Banks, police and RBI never ask for these.", "link": "https://rbikehtahai.rbi.org.in/"},
    {"key": "sec_whatsapp_2step", "icon": "chat", "title": "Turn on WhatsApp two-step verification",
     "why": "Stops scammers taking over your WhatsApp with a stolen OTP and messaging your family.",
     "how": "WhatsApp > Settings > Account > Two-step verification > Turn on, and set a 6-digit PIN.",
     "link": "https://faq.whatsapp.com/1920866721452534"},
    {"key": "sec_upi_limit", "icon": "account_balance_wallet", "title": "Set a daily UPI limit you are comfortable with",
     "why": "Caps how much a scammer can take in one day if you are tricked.",
     "how": "Open your UPI app > Profile / Settings > Payment or transaction limit.", "link": "https://www.npci.org.in/"},
    {"key": "sec_sim_check", "icon": "sim_card", "title": "Check which mobile numbers are registered in your name",
     "why": "SIMs taken in your name are used for fraud. You can report and block numbers that aren't yours.",
     "how": "Visit Sanchar Saathi > 'Know mobile connections in your name' and log in with your number.",
     "link": "https://sancharsaathi.gov.in/"},
    {"key": "sec_aadhaar_lock", "icon": "fingerprint", "title": "Lock your Aadhaar biometrics",
     "why": "Prevents fraudsters using cloned fingerprints for AePS withdrawals from your bank account.",
     "how": "myAadhaar website or mAadhaar app > Lock / Unlock Biometrics.", "link": "https://myaadhaar.uidai.gov.in/"},
    {"key": "sec_bank_alerts", "icon": "notifications_active", "title": "Turn on SMS / email alerts for every transaction",
     "why": "You spot an unauthorised payment within minutes, and reporting fast limits your loss.",
     "how": "Your bank app > Alerts / Notifications, or ask your branch.", "link": "https://rbikehtahai.rbi.org.in/"},
    {"key": "sec_email_2fa", "icon": "mail_lock", "title": "Turn on 2-step verification for your email",
     "why": "Your email can reset every other password, so it needs the strongest protection.",
     "how": "Gmail: myaccount.google.com > Security > 2-Step Verification.", "link": "https://myaccount.google.com/security"},
    {"key": "sec_remote_apps", "icon": "screen_share", "title": "Remove screen-sharing apps you don't need",
     "why": "AnyDesk / TeamViewer / QuickSupport let a caller watch your OTPs and banking apps.",
     "how": "Uninstall them, and never install one because a caller asked you to.", "link": "https://cybercrime.gov.in/"},
    {"key": "sec_save_1930", "icon": "call", "title": "Save 1930 (Cyber Fraud Helpline) in your phone",
     "why": "Calling 1930 within the first hour gives the best chance of freezing stolen money.",
     "how": "Add a contact 'Cyber Fraud Helpline - 1930'. Do it for your parents too.", "link": "tel:1930"},
    {"key": "sec_trusted_contact", "icon": "family_restroom", "title": "Add a trusted family contact in Suraksha",
     "why": "They get alerted if you check something dangerous, and one tap reaches them for help.",
     "how": "Done automatically once you add a contact under Family Safety.", "link": None, "auto": True},
)  # fmt: skip
SHIELD_KEYS = {s["key"] for s in SHIELD}

WEEKLY_CHALLENGES: tuple[dict[str, str], ...] = (
    {"key": "teach_otp", "icon": "record_voice_over", "title": "Teach one family member: 'Banks never ask for OTP'",
     "detail": "Tell a parent or grandparent today. Most victims are scammed on a call they didn't expect."},
    {"key": "report_spam", "icon": "report", "title": "Report one spam or fraud call / SMS on Chakshu",
     "detail": "Sanchar Saathi's Chakshu helps the government block numbers used by scammers."},
    {"key": "check_register", "icon": "verified", "title": "Look up one 'tips' account on SEBI's register",
     "detail": "Pick a finfluencer or Telegram channel you follow and check whether it is SEBI-registered."},
    {"key": "digital_arrest_talk", "icon": "local_police", "title": "Talk with family about 'digital arrest'",
     "detail": "Police never arrest anyone on a video call or ask for money to 'verify' accounts."},
    {"key": "review_permissions", "icon": "admin_panel_settings", "title": "Review app permissions on your phone",
     "detail": "Remove SMS and accessibility access from apps that don't need them."},
    {"key": "parents_1930", "icon": "call", "title": "Save 1930 in your parents' phones",
     "detail": "Make sure everyone at home knows the cyber-fraud helpline."},
    {"key": "check_links", "icon": "link", "title": "Check 3 links before opening them this week",
     "detail": "Paste them into Suraksha's Link Checker before tapping."},
    {"key": "share_story", "icon": "forum", "title": "Share one scam story from the Learning Center",
     "detail": "Send a story lesson to your family WhatsApp group."},
)  # fmt: skip

DAILY_GOALS = (
    {"key": "drill", "icon": "quiz", "title": "Daily Scam Drill", "detail": "Spot 3 scams in 2 minutes", "page": "habits"},
    {
        "key": "learn",
        "icon": "school",
        "title": "Learn for 2 minutes",
        "detail": "A lesson, quiz or flash cards",
        "page": "learn",
    },
    {"key": "check", "icon": "gpp_maybe", "title": "Check before you trust", "detail": "Scan a message or link", "page": "msg"},
)

BANDS = ((750, "Excellent", "g"), (650, "Good", "p"), (500, "Building up", "a"), (0, "At risk", "r"))
WEIGHTS = {"shield": 0.30, "drill": 0.20, "consistency": 0.15, "awareness": 0.15, "vigilance": 0.10, "family": 0.10}
BOOSTERS = {
    "shield": ("shield", "Complete your Safety Shield steps", "habits"),
    "drill": ("quiz", "Do today's Scam Drill", "habits"),
    "consistency": ("local_fire_department", "Keep a daily safety streak", "habits"),
    "awareness": ("school", "Finish a scam-safety lesson and quiz", "learn"),
    "vigilance": ("gpp_maybe", "Check suspicious messages and links before acting", "msg"),
    "family": ("family_restroom", "Add a trusted contact and fill Family Readiness", "elder"),
}


# ---- drill bank ---------------------------------------------------------------------------------
@lru_cache
def drill_bank() -> dict[str, dict[str, Any]]:
    items = json.loads(DRILLS_FILE.read_text(encoding="utf-8"))
    return {i["id"]: i for i in items}


def _answers(db: Session, user_id: uuid.UUID, since: date) -> list[XPEvent]:
    start = datetime.combine(since, datetime.min.time(), tzinfo=UTC)
    return list(
        db.scalars(select(XPEvent).where(XPEvent.user_id == user_id, XPEvent.action == "drill", XPEvent.created_at >= start))
    )


def _today_answers(db: Session, user_id: uuid.UUID, today: date) -> dict[str, bool]:
    """item id -> answered correctly, for today's drill (XPEvent ref = 'YYYY-MM-DD:item')."""
    prefix = today.isoformat() + ":"
    rows = db.scalars(
        select(XPEvent).where(XPEvent.user_id == user_id, XPEvent.action == "drill", XPEvent.ref.startswith(prefix))
    ).all()
    return {r.ref.split(":", 1)[1]: r.xp > 0 for r in rows}


def todays_drill_ids(db: Session, user_id: uuid.UUID, today: date | None = None) -> list[str]:
    """Same 3 items all day for a user; at least one scam and one genuine; avoids recently-seen items."""
    today = today or date.today()
    bank = drill_bank()
    recent = {
        e.ref.split(":", 1)[1]
        for e in _answers(db, user_id, today - timedelta(days=21))
        if not e.ref.startswith(today.isoformat())
    }
    rng = random.Random(f"{user_id}:{today.isoformat()}")
    scams = [i for i, d in bank.items() if d["label"] == "scam"]
    genuine = [i for i, d in bank.items() if d["label"] == "genuine"]

    def fresh(ids: list[str]) -> list[str]:
        return [i for i in ids if i not in recent] or ids

    picks = [rng.choice(fresh(scams)), rng.choice(fresh(genuine))]
    rest = [i for i in fresh(scams + genuine) if i not in picks] or [i for i in bank if i not in picks]
    picks.append(rng.choice(sorted(rest)))
    rng.shuffle(picks)
    return picks


def _explain(item: dict[str, Any]) -> dict[str, Any]:
    rules = analyze_rules(item["text"])
    signals = list(dict.fromkeys(f.label for f in rules.flags))[:4] if item["label"] == "scam" else []
    marks = [{"start": s.start, "end": s.end} for s in rules.spans][:8] if item["label"] == "scam" else []
    return {"tip": item["tip"], "signals": signals, "marks": marks}


def drill_state(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    today = date.today()
    answered = _today_answers(db, user_id, today)
    items = []
    for i in todays_drill_ids(db, user_id, today):
        d = drill_bank()[i]
        item = {"id": i, "text": d["text"], "answered": i in answered}
        if i in answered:
            item |= {"correct": answered[i], "label": d["label"], **_explain(d)}
        items.append(item)
    month = _answers(db, user_id, today - timedelta(days=29))
    correct = sum(1 for e in month if e.xp > 0)
    cur, best = streaks(db, user_id, ("drill",))
    return {
        "date": today,
        "items": items,
        "done": len(answered) >= DRILLS_PER_DAY,
        "correct_today": sum(answered.values()),
        "accuracy_30d": round(100 * correct / len(month), 1) if month else None,
        "answered_30d": len(month),
        "streak_days": cur,
        "best_streak_days": best,
    }


def answer_drill(db: Session, user_id: uuid.UUID, item_id: str, answer: str) -> dict[str, Any]:
    today = date.today()
    if item_id not in todays_drill_ids(db, user_id, today):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That message is not part of today's drill")
    item = drill_bank()[item_id]
    answered = _today_answers(db, user_id, today)
    if item_id in answered:
        correct, xp = answered[item_id], 0
    else:
        correct = answer == item["label"]
        xp = award(db, user_id, "drill", ref=f"{today.isoformat()}:{item_id}", xp=10 if correct else 0)
        record_activity(db, user_id, "drill")
        answered[item_id] = correct
        if len(answered) >= DRILLS_PER_DAY:
            xp += award(db, user_id, "drill_day", ref=today.isoformat())
        db.commit()
    return {
        "id": item_id,
        "correct": correct,
        "label": item["label"],
        "xp_awarded": xp,
        "done": len(answered) >= DRILLS_PER_DAY,
        "remaining": max(DRILLS_PER_DAY - len(answered), 0),
        **_explain(item),
    }


# ---- Safety Shield (one-time protection steps) --------------------------------------------------
def _auto_shield(db: Session, user_id: uuid.UUID) -> set[str]:
    done = set()
    if db.scalar(select(func.count()).select_from(EmergencyContact).where(EmergencyContact.user_id == user_id)):
        done.add("sec_trusted_contact")
    return done


def shield(db: Session, user_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = {
        r.item_key: r
        for r in db.scalars(
            select(HabitChecklistItem).where(HabitChecklistItem.user_id == user_id, HabitChecklistItem.item_key.in_(SHIELD_KEYS))
        )
    }
    auto = _auto_shield(db, user_id)
    out = []
    for s in SHIELD:
        row = rows.get(s["key"])
        out.append({**s, "auto": bool(s.get("auto")), "done": s["key"] in auto or bool(row and row.completed),
                    "done_at": row.completed_at if row and row.completed else None})  # fmt: skip
    return out


def set_shield(db: Session, user_id: uuid.UUID, key: str, completed: bool) -> None:
    item = next((s for s in SHIELD if s["key"] == key), None)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown safety step")
    if item.get("auto"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This step is completed automatically")
    row = db.scalar(select(HabitChecklistItem).where(HabitChecklistItem.user_id == user_id, HabitChecklistItem.item_key == key))
    if row is None:
        row = HabitChecklistItem(user_id=user_id, item_key=key)
        db.add(row)
    row.completed = completed
    row.completed_at = datetime.now(UTC) if completed else None
    record_activity(db, user_id, "habit")
    db.flush()
    if completed:
        award(db, user_id, "shield_step", ref=key)
    db.commit()


# ---- daily goals & weekly challenge -------------------------------------------------------------
def _activity_days(db: Session, user_id: uuid.UUID, since: date) -> dict[date, set[str]]:
    rows = db.execute(
        select(UserActivity.activity_date, UserActivity.kind).where(
            UserActivity.user_id == user_id, UserActivity.activity_date >= since
        )
    ).all()
    out: dict[date, set[str]] = {}
    for d, kind in rows:
        out.setdefault(d, set()).add(kind)
    return out


def _goal_done(kinds: set[str], goal: str) -> bool:
    if goal == "drill":
        return "drill" in kinds
    if goal == "learn":
        return bool(kinds & set(LEARNING_KINDS))
    return "scan" in kinds


def daily_goals(db: Session, user_id: uuid.UUID, drill_done: bool) -> dict[str, Any]:
    today = date.today()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    acts = _activity_days(db, user_id, days[0])
    goals = []
    for g in DAILY_GOALS:
        week = [_goal_done(acts.get(d, set()), g["key"]) for d in days]
        done = drill_done if g["key"] == "drill" else week[-1]
        goals.append({**g, "done": done, "week": week})
    return {
        "goals": goals,
        "days": [d.strftime("%a") for d in days],
        "completed": sum(g["done"] for g in goals),
        "total": len(goals),
    }


def _iso_week(d: date | None = None) -> str:
    y, w, _ = (d or date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def weekly_challenge(db: Session, user_id: uuid.UUID) -> dict[str, Any]:
    week = _iso_week()
    ch = WEEKLY_CHALLENGES[date.today().isocalendar()[1] % len(WEEKLY_CHALLENGES)]
    done = bool(
        db.scalar(select(XPEvent.id).where(XPEvent.user_id == user_id, XPEvent.action == "weekly_challenge", XPEvent.ref == week))
    )
    ends = date.today() + timedelta(days=6 - date.today().weekday())
    return {**ch, "week": week, "done": done, "xp": 40, "days_left": (ends - date.today()).days}


def complete_weekly_challenge(db: Session, user_id: uuid.UUID) -> int:
    xp = award(db, user_id, "weekly_challenge", ref=_iso_week())
    record_activity(db, user_id, "habit")
    db.commit()
    return xp


# ---- Suraksha Safety Score ----------------------------------------------------------------------
def _band(score: int) -> tuple[str, str]:
    return next((label, tone) for floor, label, tone in BANDS if score >= floor)


def safety_score(db: Session, user: User, shield_items: list[dict], drill: dict, awareness: float, ef_progress: float) -> dict:
    from backend.services.readiness_service import overview as readiness_overview

    uid = user.id
    today = date.today()
    acts = _activity_days(db, uid, today - timedelta(days=13))
    active = sum(1 for kinds in acts.values() if kinds & {"drill", "scan", *LEARNING_KINDS})
    scans_30 = (
        db.scalar(
            select(func.count())
            .select_from(ScamAnalysis)
            .where(ScamAnalysis.user_id == uid, ScamAnalysis.created_at >= datetime.now(UTC) - timedelta(days=30))
        )
        or 0
    )
    has_contact = "sec_trusted_contact" in {s["key"] for s in shield_items if s["done"]}
    readiness = readiness_overview(db, uid, user.language or "en")["score_pct"] / 100
    accuracy = (drill["accuracy_30d"] or 0) / 100
    parts = {
        "shield": sum(s["done"] for s in shield_items) / len(shield_items),
        "drill": accuracy * min(1.0, drill["answered_30d"] / 15),
        "consistency": min(active / 14, 1.0),
        "awareness": min(awareness / 100, 1.0),
        "vigilance": min(scans_30 / 3, 1.0),
        "family": (float(has_contact) + readiness + min(ef_progress / 100, 1.0)) / 3,
    }
    score = round(300 + 600 * sum(WEIGHTS[k] * v for k, v in parts.items()))
    label, tone = _band(score)

    # weekly history in preferences, to show "+24 this week"
    prefs = dict(user.preferences or {})
    hist = dict(prefs.get("safety_score_history") or {})
    week = _iso_week()
    previous = next((v for k, v in sorted(hist.items(), reverse=True) if k < week), None)
    if hist.get(week) != score:
        hist[week] = score
        prefs["safety_score_history"] = dict(sorted(hist.items())[-12:])
        user.preferences = prefs
        db.commit()

    boosters = sorted(
        (
            {
                "key": k,
                "icon": BOOSTERS[k][0],
                "title": BOOSTERS[k][1],
                "page": BOOSTERS[k][2],
                "points": round(600 * WEIGHTS[k] * (1 - v)),
            }  # fmt: skip
            for k, v in parts.items()
            if v < 0.999
        ),
        key=lambda b: -b["points"],
    )
    return {
        "score": score,
        "min": 300,
        "max": 900,
        "band": label,
        "tone": tone,
        "pct": round((score - 300) / 6, 1),
        "change": (score - previous) if previous is not None else None,
        "history": [{"week": k, "score": v} for k, v in sorted(hist.items())][-8:],
        "parts": [
            {"key": k, "label": _part_label(k), "pct": round(v * 100), "weight": round(WEIGHTS[k] * 100)}
            for k, v in parts.items()
        ],
        "boosters": [b for b in boosters if b["points"] > 0][:4],
    }


def _part_label(key: str) -> str:
    return {
        "shield": "Safety Shield",
        "drill": "Scam-spotting skill",
        "consistency": "Daily consistency",
        "awareness": "Scam awareness",
        "vigilance": "Checks before trusting",
        "family": "Family & money readiness",
    }[key]
