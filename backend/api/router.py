"""Aggregates all routers into the public API."""

from fastapi import APIRouter

from backend.routers import (
    admin,
    analyze,
    auth,
    chat,
    dashboard,
    family,
    gamification,
    habits,
    learning,
    scan,
    system,
    voice,
)

api_router = APIRouter()
for module in (system, auth, scan, analyze, chat, voice, dashboard, learning, habits, family, gamification, admin):
    api_router.include_router(module.router)
