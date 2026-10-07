from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.database.session import get_db
from app.models.domain import User

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
settings = get_settings()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def create_access_token(user: User) -> tuple[str, int]:
    expires = timedelta(minutes=settings.access_token_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": user.id,
        "email": user.email,
        "iat": now,
        "exp": now + expires,
        "type": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256"), int(expires.total_seconds())


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id or payload.get("type") != "access":
            raise credentials_error
    except InvalidTokenError as exc:
        raise credentials_error from exc
    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(permission: str):
    async def permission_dependency(user: CurrentUser) -> User:
        granted = {item.code for item in user.role.permissions}
        if "*" not in granted and permission not in granted:
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return user

    return permission_dependency


def ensure_house_access(user: User, house_id: str) -> None:
    granted = {item.code for item in user.role.permissions}
    if (
        user.house_id != house_id
        and "*" not in granted
        and user.role.name not in {"admin", "owner"}
    ):
        raise HTTPException(status_code=403, detail="House access denied")
