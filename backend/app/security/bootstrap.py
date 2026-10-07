from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Permission, Role, User
from app.security.auth import hash_password

PERMISSIONS = {
    "house:read": "View houses, rooms, and status",
    "house:manage": "Manage houses, floors, and rooms",
    "device:read": "View devices and sensors",
    "device:manage": "Register and configure devices",
    "device:control": "Send validated commands to devices",
    "automation:read": "View automation and scenes",
    "automation:manage": "Configure and execute automation and scenes",
    "analytics:read": "View energy, water, memory, and health analytics",
    "telemetry:write": "Ingest trusted telemetry",
    "user:manage": "Manage users and roles",
    "audit:read": "View security and audit events",
}

ROLE_PERMISSIONS = {
    "owner": {"*"},
    "admin": {"*"},
    "operator": set(PERMISSIONS) - {"user:manage"},
    "member": {
        "house:read",
        "device:read",
        "device:control",
        "automation:read",
        "analytics:read",
    },
    "guest": {"house:read", "device:read"},
    "service": {"house:read", "device:read", "analytics:read", "telemetry:write"},
    "resident": {
        "house:read",
        "device:read",
        "device:control",
        "automation:read",
        "analytics:read",
    },
    "viewer": {"house:read", "device:read", "automation:read", "analytics:read"},
}


async def seed_security(
    db: AsyncSession,
    admin_email: str | None = None,
    admin_password: str | None = None,
    admin_pin: str | None = None,
) -> None:
    permissions: dict[str, Permission] = {}
    for code, description in PERMISSIONS.items():
        permission = await db.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code, description=description)
            db.add(permission)
        permissions[code] = permission

    roles: dict[str, Role] = {}
    for name, codes in ROLE_PERMISSIONS.items():
        role = await db.scalar(select(Role).where(Role.name == name))
        if role is None:
            role = Role(name=name, description=f"Built-in {name} role")
            db.add(role)
        role.permissions = (
            list(permissions.values()) if "*" in codes else [permissions[c] for c in codes]
        )
        roles[name] = role

    await db.flush()
    if admin_email and admin_password:
        normalized = admin_email.strip().lower()
        existing = await db.scalar(select(User).where(User.email == normalized))
        if existing is None:
            db.add(
                User(
                    email=normalized,
                    display_name="Administrator",
                    password_hash=hash_password(admin_password),
                    pin_code_hash=hash_password(admin_pin) if admin_pin else None,
                    role=roles["admin"],
                )
            )
    await db.commit()
