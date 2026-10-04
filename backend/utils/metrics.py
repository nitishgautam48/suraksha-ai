"""Prometheus metrics. Works with several uvicorn workers via PROMETHEUS_MULTIPROC_DIR (set in start.sh)."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)

HTTP_REQUESTS = Counter("suraksha_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram(
    "suraksha_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120),
)
ANALYSES = Counter("suraksha_analyses_total", "Scam analyses performed", ["source_type", "risk_level", "llm_used"])
LLM_CALLS = Counter("suraksha_llm_requests_total", "Ollama requests", ["model", "kind", "outcome"])
LLM_LATENCY = Histogram(
    "suraksha_llm_request_duration_seconds",
    "Ollama request latency",
    ["model", "kind"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 20, 40, 80, 160, 300),
)
RAG_RETRIEVALS = Counter("suraksha_rag_retrievals_total", "RAG retrievals", ["outcome"])  # hit | empty | error
EMAILS = Counter("suraksha_emails_total", "Transactional emails", ["template", "outcome"])
SMS_MESSAGES = Counter("suraksha_sms_total", "SMS messages", ["provider", "purpose", "outcome"])
AUTH_EVENTS = Counter("suraksha_auth_events_total", "Authentication events", ["event"])
GUARDRAIL_BLOCKS = Counter("suraksha_guardrail_blocks_total", "Advice requests / outputs blocked", ["stage"])


@contextmanager
def track_llm(model: str, kind: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    except Exception:
        LLM_CALLS.labels(model, kind, "error").inc()
        raise
    else:
        LLM_CALLS.labels(model, kind, "ok").inc()
    finally:
        LLM_LATENCY.labels(model, kind).observe(time.perf_counter() - start)


def render_latest() -> tuple[bytes, str]:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return generate_latest(registry), CONTENT_TYPE_LATEST
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
