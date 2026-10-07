from fastapi import APIRouter

from app.api.routes import (
    analytics,
    auth,
    automations,
    contract,
    devices,
    houses,
    realtime,
    simulation,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(houses.router, prefix="/houses", tags=["houses"])
api_router.include_router(devices.router, tags=["devices"])
api_router.include_router(automations.router, tags=["automation"])
api_router.include_router(analytics.router, tags=["analytics"])
api_router.include_router(simulation.router, prefix="/simulation", tags=["simulation"])
api_router.include_router(realtime.router, tags=["realtime"])
api_router.include_router(contract.router, tags=["architecture-contract"])
