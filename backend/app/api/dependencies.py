from typing import Annotated

from fastapi import Depends, Request

from app.automation.engine import AutomationEngine
from app.devices.service import DeviceService
from app.services.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def get_device_service(runtime: Annotated[Runtime, Depends(get_runtime)]) -> DeviceService:
    return runtime.devices


def get_automation_engine(runtime: Annotated[Runtime, Depends(get_runtime)]) -> AutomationEngine:
    return runtime.automations


DeviceServiceDep = Annotated[DeviceService, Depends(get_device_service)]
AutomationEngineDep = Annotated[AutomationEngine, Depends(get_automation_engine)]
