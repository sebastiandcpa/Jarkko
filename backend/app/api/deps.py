"""Dependencias compartidas por las rutas."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends

from app.agent.engine import AgentEngine, get_engine
from app.config import Settings, get_settings
from app.services.activity import ActivityService, activity_service
from app.services.confirmations import ConfirmationStore, confirmation_store
from app.tools.registry import ToolRegistry

#: Momento de arranque del proceso, para el uptime de /api/health.
PROCESS_START = time.monotonic()


def uptime_seconds() -> int:
    return int(time.monotonic() - PROCESS_START)


def provide_engine() -> AgentEngine:
    return get_engine()


def provide_settings() -> Settings:
    return get_settings()


def provide_registry(engine: AgentEngine = Depends(provide_engine)) -> ToolRegistry:
    return engine.registry


def provide_activity() -> ActivityService:
    return activity_service


def provide_confirmations() -> ConfirmationStore:
    return confirmation_store


EngineDep = Annotated[AgentEngine, Depends(provide_engine)]
SettingsDep = Annotated[Settings, Depends(provide_settings)]
RegistryDep = Annotated[ToolRegistry, Depends(provide_registry)]
ActivityDep = Annotated[ActivityService, Depends(provide_activity)]
ConfirmationsDep = Annotated[ConfirmationStore, Depends(provide_confirmations)]
