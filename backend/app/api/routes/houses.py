from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.models.domain import Floor, House, Room, User
from app.schemas.domain import FloorCreate, FloorRead, HouseCreate, HouseRead, RoomCreate, RoomRead
from app.security.auth import CurrentUser, ensure_house_access, require_permission

router = APIRouter()


@router.get("", response_model=list[HouseRead])
async def list_houses(
    user: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> list[House]:
    statement = select(House).order_by(House.name)
    if user.role.name not in {"admin", "owner"}:
        statement = statement.where(House.id == user.house_id)
    return list((await db.scalars(statement)).all())


@router.post("", response_model=HouseRead, status_code=201)
async def create_house(
    payload: HouseCreate,
    user: Annotated[User, Depends(require_permission("house:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> House:
    house = House(name=payload.name, timezone=payload.timezone)
    db.add(house)
    await db.commit()
    await db.refresh(house)
    return house


@router.post("/{house_id}/floors", response_model=FloorRead, status_code=201)
async def create_floor(
    house_id: str,
    payload: FloorCreate,
    user: Annotated[User, Depends(require_permission("house:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Floor:
    ensure_house_access(user, house_id)
    if await db.get(House, house_id) is None:
        raise HTTPException(status_code=404, detail="House not found")
    floor = Floor(house_id=house_id, **payload.model_dump())
    db.add(floor)
    await db.commit()
    await db.refresh(floor)
    return floor


@router.post("/{house_id}/rooms", response_model=RoomRead, status_code=201)
async def create_room(
    house_id: str,
    payload: RoomCreate,
    user: Annotated[User, Depends(require_permission("house:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Room:
    ensure_house_access(user, house_id)
    floor = await db.get(Floor, payload.floor_id)
    if floor is None or floor.house_id != house_id:
        raise HTTPException(status_code=422, detail="Floor is not part of this house")
    room = Room(**payload.model_dump())
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


@router.get("/{house_id}/rooms", response_model=list[RoomRead])
async def list_rooms(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Room]:
    ensure_house_access(user, house_id)
    return list(
        (
            await db.scalars(
                select(Room)
                .join(Floor)
                .where(Floor.house_id == house_id)
                .order_by(Floor.level, Room.name)
            )
        ).all()
    )
