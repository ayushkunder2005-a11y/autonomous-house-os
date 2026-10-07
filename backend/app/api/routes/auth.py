from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.events.service import event_service
from app.models.domain import Role, User
from app.models.operations import AuditLog
from app.schemas.auth import Token, UserCreate, UserRead
from app.security.auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    require_permission,
    verify_password,
)

router = APIRouter()


def user_response(user: User) -> UserRead:
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        house_id=user.house_id,
        is_active=user.is_active,
        role_name=user.role.name,
        permissions=sorted(item.code for item in user.role.permissions),
    )


@router.post("/token", response_model=Token)
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Token:
    user = await db.scalar(select(User).where(User.email == form.username.strip().lower()))
    valid = (
        user is not None and user.is_active and verify_password(form.password, user.password_hash)
    )
    db.add(
        AuditLog(
            actor_id=user.id if user else None,
            action="auth.login",
            resource_type="user",
            resource_id=user.id if user else None,
            ip_address=request.client.host if request.client else None,
            success=bool(valid),
            details={"email": form.username.strip().lower()},
        )
    )
    await db.commit()
    if not valid or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires = create_access_token(user)
    return Token(access_token=token, expires_in=expires)


@router.get("/me", response_model=UserRead)
async def me(user: CurrentUser) -> UserRead:
    return user_response(user)


@router.post("/users", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    admin: Annotated[User, Depends(require_permission("user:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    email = payload.email.lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email is already registered")
    role = await db.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        raise HTTPException(status_code=422, detail="Unknown role")
    user = User(
        email=email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        pin_code_hash=hash_password(payload.security_pin) if payload.security_pin else None,
        role=role,
        house_id=payload.house_id,
    )
    db.add(user)
    await db.flush()
    await event_service.append(
        db,
        house_id=payload.house_id,
        source=f"user:{admin.id}",
        event_type="user.created",
        message=f"User {email} created with role {role.name}",
        remember=False,
    )
    await db.commit()
    await db.refresh(user)
    return user_response(user)
