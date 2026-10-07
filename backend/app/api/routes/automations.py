from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.intents import intent_provider
from app.api.dependencies import AutomationEngineDep
from app.database.session import get_db
from app.models.domain import User
from app.models.operations import AIDecision, Automation, Scene
from app.schemas.domain import (
    AutomationCreate,
    AutomationRead,
    NaturalLanguageCommand,
    SceneCreate,
    SceneRead,
    StructuredIntent,
)
from app.security.auth import CurrentUser, ensure_house_access, require_permission

router = APIRouter()


@router.get("/houses/{house_id}/automations", response_model=list[AutomationRead])
async def list_automations(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Automation]:
    ensure_house_access(user, house_id)
    return list((await db.scalars(select(Automation).where(Automation.house_id == house_id))).all())


@router.post("/automations", response_model=AutomationRead, status_code=201)
async def create_automation(
    payload: AutomationCreate,
    user: Annotated[User, Depends(require_permission("automation:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Automation:
    ensure_house_access(user, payload.house_id)
    automation = Automation(**payload.model_dump())
    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    return automation


@router.post("/automations/{automation_id}/execute", status_code=202)
async def execute_automation(
    automation_id: str,
    user: Annotated[User, Depends(require_permission("automation:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    engine: AutomationEngineDep,
) -> dict[str, Any]:
    automation = await db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    ensure_house_access(user, automation.house_id)
    command_ids = await engine.execute(db, automation, user.id)
    return {"automation_id": automation.id, "command_ids": command_ids}


@router.get("/houses/{house_id}/scenes", response_model=list[SceneRead])
async def list_scenes(
    house_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Scene]:
    ensure_house_access(user, house_id)
    return list((await db.scalars(select(Scene).where(Scene.house_id == house_id))).all())


@router.post("/scenes", response_model=SceneRead, status_code=201)
async def create_scene(
    payload: SceneCreate,
    user: Annotated[User, Depends(require_permission("automation:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Scene:
    ensure_house_access(user, payload.house_id)
    scene = Scene(**payload.model_dump())
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    return scene


@router.post("/scenes/{scene_id}/execute", status_code=202)
async def execute_scene(
    scene_id: str,
    user: Annotated[User, Depends(require_permission("automation:manage"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    engine: AutomationEngineDep,
) -> dict[str, Any]:
    scene = await db.get(Scene, scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    ensure_house_access(user, scene.house_id)
    command_ids = await engine.execute_scene(db, scene, user.id)
    return {"scene_id": scene.id, "command_ids": command_ids}


@router.post("/intents", response_model=StructuredIntent)
async def process_intent(
    payload: NaturalLanguageCommand,
    user: Annotated[User, Depends(require_permission("device:control"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    engine: AutomationEngineDep,
) -> StructuredIntent:
    ensure_house_access(user, payload.house_id)
    intent = await intent_provider.interpret(payload.text)
    decision = AIDecision(
        house_id=payload.house_id,
        provider="rules",
        model="deterministic-v1",
        input_summary=payload.text,
        structured_intent=intent.model_dump(),
        validation_status="validated" if intent.executable else "rejected",
        executed=False,
        rationale=intent.reason or "Matched a deterministic intent rule",
    )
    db.add(decision)
    if payload.execute and intent.executable and not intent.requires_confirmation:
        mode = intent.intent.removesuffix("_mode")
        scene = await db.scalar(
            select(Scene).where(
                Scene.house_id == payload.house_id,
                Scene.enabled.is_(True),
                (Scene.mode == mode) | (Scene.name.ilike(intent.intent.replace("_", " "))),
            )
        )
        if scene:
            await engine.execute_scene(db, scene, user.id)
            decision.executed = True
        else:
            intent.executable = False
            intent.reason = "No configured scene maps to this validated intent"
            decision.validation_status = "no_execution_plan"
    await db.commit()
    return intent
