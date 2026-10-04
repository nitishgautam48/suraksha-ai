from __future__ import annotations

import re

import bcrypt

from backend.config import settings


def hash_password(password: str) -> str:
    # bcrypt only uses the first 72 bytes; truncate explicitly so behaviour is deterministic.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        problems.append(f"must be at least {settings.PASSWORD_MIN_LENGTH} characters")
    if not re.search(r"[A-Za-z]", password):
        problems.append("must contain a letter")
    if not re.search(r"\d", password):
        problems.append("must contain a digit")
    return problems
