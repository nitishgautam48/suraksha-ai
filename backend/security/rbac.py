"""Role-based access control."""

from __future__ import annotations

from backend.models.enums import Role

# Higher number = more privileges. A role satisfies any requirement at or below its rank.
ROLE_RANK = {Role.USER.value: 0, Role.EDUCATOR.value: 1, Role.ADMIN.value: 2}

PERMISSIONS: dict[str, set[str]] = {
    Role.USER.value: {"scan", "analyze", "chat", "voice", "learn", "habits", "alerts", "dashboard"},
    Role.EDUCATOR.value: {"content:generate", "content:write"},
    Role.ADMIN.value: {"users:read", "users:write", "audit:read", "knowledge:ingest"},
}


def has_role(user_role: str, required: Role) -> bool:
    return ROLE_RANK.get(user_role, -1) >= ROLE_RANK[required.value]


def permissions_for(role: str) -> set[str]:
    rank = ROLE_RANK.get(role, -1)
    perms: set[str] = set()
    for r, r_rank in ROLE_RANK.items():
        if r_rank <= rank:
            perms |= PERMISSIONS[r]
    return perms


def has_permission(role: str, permission: str) -> bool:
    return permission in permissions_for(role)
