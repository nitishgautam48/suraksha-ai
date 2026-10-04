from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

from backend.ai.guardrails import DISCLAIMER
from backend.security.sanitize import strip_html

LanguageCode = Literal["en", "hi", "gu", "mr", "ta", "bn", "te", "kn", "ml", "pa", "or", "as"]
RiskLevelStr = Literal["low", "medium", "high", "critical"]

# User text that is stored and echoed back: HTML is stripped (XSS defence in depth).
CleanStr = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(strip_html)]


def clean(max_length: int, min_length: int = 1):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
        AfterValidator(strip_html),
    ]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class Disclaimer(BaseModel):
    disclaimer: str = DISCLAIMER
