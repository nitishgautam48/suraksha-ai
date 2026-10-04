"""Offline evaluation and threshold calibration for the scam risk engine.

Dataset format (JSON Lines): {"text": ..., "label": "scam"|"legit", "category": ..., "split": "tune"|"holdout"}
The bundled dataset.jsonl is hand-written; grow it with real, consented user feedback exported from
GET /admin/feedback/export (same format).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DATASET = Path(__file__).with_name("dataset.jsonl")


@dataclass
class Scored:
    row: dict[str, Any]
    score: int
    flags: list[str]


def load(path: Path | None = None, split: str | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in (path or DEFAULT_DATASET).read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if split in (None, "all") or r.get("split", "tune") == split]


def score_rows(rows: list[dict[str, Any]], use_llm: bool = False) -> list[Scored]:
    from backend.ai.analyzer import analyze_content
    from backend.ai.risk_engine import analyze_rules
    from backend.utils.redact import redact
    from backend.utils.text import clean_text

    out = []
    for r in rows:
        if use_llm:
            res = analyze_content(r["text"], source="message", language="en")
            out.append(Scored(r, res.risk_score, [f["key"] for f in res.warning_flags]))
        else:
            res = analyze_rules(redact(clean_text(r["text"]))[0])  # same preprocessing as production
            out.append(Scored(r, res.score, [f.key for f in res.flags]))
    return out


def metrics_at(scored: list[Scored], threshold: int) -> dict[str, float | int]:
    tp = sum(s.score >= threshold and s.row["label"] == "scam" for s in scored)
    fp = sum(s.score >= threshold and s.row["label"] != "scam" for s in scored)
    fn = sum(s.score < threshold and s.row["label"] == "scam" for s in scored)
    tn = sum(s.score < threshold and s.row["label"] != "scam" for s in scored)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def calibrate(scored: list[Scored], min_precision: float = 0.95) -> dict[str, Any]:
    """Suggest RISK_MEDIUM_THRESHOLD: the highest threshold that still reaches the best achievable recall
    while keeping precision >= min_precision (highest = largest safety margin above legit messages).
    Also reports score quantiles of scam examples to inform the high / critical bands."""
    sweep = [metrics_at(scored, t) for t in range(5, 100, 5)] + [metrics_at(scored, t) for t in range(21, 30)]
    sweep.sort(key=lambda m: m["threshold"])
    ok = [m for m in sweep if m["precision"] >= min_precision] or sweep
    best_recall = max(m["recall"] for m in ok)
    medium = max((m for m in ok if m["recall"] == best_recall), key=lambda m: m["threshold"])
    scam_scores = sorted(s.score for s in scored if s.row["label"] == "scam")
    legit_scores = sorted(s.score for s in scored if s.row["label"] != "scam")

    def q(p: float) -> int:
        return scam_scores[min(int(p * len(scam_scores)), len(scam_scores) - 1)] if scam_scores else 0

    return {
        "suggested_medium_threshold": medium["threshold"],
        "max_legit_score": legit_scores[-1] if legit_scores else 0,
        "scam_score_quantiles": {"p10": q(0.1), "p25": q(0.25), "p50": q(0.5), "p75": q(0.75)},
        "sweep": sweep,
    }


def category_recall(scored: list[Scored], threshold: int) -> dict[str, str]:
    hit, total = Counter(), Counter()
    for s in scored:
        if s.row["label"] == "scam":
            cat = s.row.get("category") or "uncategorised"
            total[cat] += 1
            hit[cat] += s.score >= threshold
    return {c: f"{hit[c]}/{total[c]}" for c in sorted(total)}


def errors(scored: list[Scored], threshold: int) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list] = defaultdict(list)
    for s in scored:
        is_scam = s.row["label"] == "scam"
        if is_scam and s.score < threshold:
            out["false_negatives"].append({"score": s.score, "flags": s.flags, "text": s.row["text"][:140]})
        elif not is_scam and s.score >= threshold:
            out["false_positives"].append({"score": s.score, "flags": s.flags, "text": s.row["text"][:140]})
    return dict(out)


def report(scored: list[Scored], medium: int, high: int) -> dict[str, Any]:
    return {
        "examples": len(scored),
        "warning_level": metrics_at(scored, medium),  # flagged as medium or above
        "scam_level": metrics_at(scored, high),  # flagged as high or above
        "category_recall_at_medium": category_recall(scored, medium),
        "errors_at_medium": errors(scored, medium),
    }
