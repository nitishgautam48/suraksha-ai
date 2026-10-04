"""Celery application (Redis broker). Run: celery -A backend.workers.celery_app worker -B"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from backend.config import settings

celery_app = Celery(
    "suraksha",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["backend.workers.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
    result_expires=24 * 3600,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "ensure-knowledge-base": {"task": "suraksha.ensure_knowledge_base", "schedule": 600.0},
        "daily-habit-nudges": {"task": "suraksha.daily_nudges", "schedule": crontab(hour=9, minute=0)},
        "purge-expired-scans": {"task": "suraksha.purge_expired_scans", "schedule": 3600.0},
        "weekly-reports": {"task": "suraksha.weekly_reports", "schedule": crontab(day_of_week=1, hour=9, minute=5)},
    },
)
