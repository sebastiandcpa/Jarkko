"""AgentEngine: orquesta el flujo completo.

    usuario → IA / IntentParser → Planner → Validator → Permission Manager
            → Tool Executor → Windows → Verification → resultado

Un solo motor para las dos identidades (JARVIS y EKKO): la identidad solo cambia
el tono del mensaje final.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.agent.executor import ActionOutcome, ActionStatus, ToolExecutor
from app.agent.intent_parser import IntentParser
from app.agent.planner import ExecutionPlan, Planner, PlanStatus, PlannedAction
from app.providers.base import AIProvider, IntentResult
from app.providers.factory import get_provider
from app.services.activity import ActivityService, activity_service
from app.services.assistants import AssistantProfile, resolve_assistant
from app.services.confirmations import (
    ConfirmationError,
    ConfirmationStore,
    PendingConfirmation,
    confirmation_store,
)
from app.services.events import AssistantStatus, EventBus, EventType, event_bus
from app.tools.bootstrap import get_registry
from app.tools.registry import ToolRegistry
from app.voice.service import VoiceService, get_voice_service
from app.utils.redaction import sanitize_arguments

logger = logging.getLogger(__name__)

HISTORY_TURNS = 8


class ChatStatus:
    SUCCESS = "success"
    ERROR = "error"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    NO_ACTION = "no_action"


@dataclass(slots=True)
class ChatOutcome:
    conversation_id: str
    assistant: str
    message: str
    status: str
    actions: list[ActionOutcome] = field(default_factory=list)
    requires_confirmation: bool = False
    confirmations: list[dict[str, Any]] = field(default_factory=list)
    intent: dict[str, Any] | None = None

    def to_public(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "assistant": self.assistant,
            "message": self.message,
            "status": self.status,
            "actions": [action.to_public() for action in self.actions],
            "requires_confirmation": self.requires_confirmation,
            "confirmations": self.confirmations,
            "intent": self.intent,
        }


class AgentEngine:
    """Punto de entrada del agente para la API."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        provider: AIProvider | None = None,
        planner: Planner | None = None,
        executor: ToolExecutor | None = None,
        events: EventBus | None = None,
        activity: ActivityService | None = None,
        confirmations: ConfirmationStore | None = None,
        voice: VoiceService | None = None,
    ) -> None:
        self.registry = registry or get_registry()
        self.provider = provider or get_provider()
        self.planner = planner or Planner(self.registry)
        self.executor = executor or ToolExecutor()
        self.events = events or event_bus
        self.activity = activity or activity_service
        self.confirmations = confirmations or confirmation_store
        self.voice = voice or get_voice_service()
        self.intent_parser = IntentParser(self.provider, self.registry)

    # ------------------------------------------------------------------
    # conversación
    # ------------------------------------------------------------------
    async def chat(
        self,
        message: str,
        *,
        assistant: str = "jarkko",
        conversation_id: str | None = None,
    ) -> ChatOutcome:
        profile = resolve_assistant(assistant)
        conversation = conversation_id or uuid.uuid4().hex
        self.events.publish_status(AssistantStatus.THINKING, assistant=profile.key, conversation_id=conversation)

        history = await self.activity.history(conversation, limit=HISTORY_TURNS)
        await self.activity.log_message(
            conversation_id=conversation, assistant=profile.key, role="user", content=message
        )

        intent = await self.intent_parser.parse(message, assistant=profile.key, history=history)

        if not intent.actions:
            return await self._finish_without_actions(intent, profile, conversation)

        self.events.publish_status(AssistantStatus.PLANNING, assistant=profile.key, conversation_id=conversation)
        self.events.publish(
            EventType.ACTION_PLANNING,
            {
                "assistant": profile.key,
                "conversation_id": conversation,
                "actions": [action.to_public() for action in intent.actions],
                "confidence": round(intent.confidence, 2),
            },
        )

        plan = self.planner.plan(intent.actions)

        if plan.requires_confirmation:
            return await self._finish_awaiting_confirmation(plan, intent, profile, conversation)

        outcomes = await self._execute_plan(plan, profile=profile, conversation_id=conversation)
        return await self._finish_executed(outcomes, intent, profile, conversation, message)

    # ------------------------------------------------------------------
    # ejecución directa (POST /api/actions/execute)
    # ------------------------------------------------------------------
    async def execute_action(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        assistant: str = "jarkko",
        conversation_id: str | None = None,
        speak: bool = True,
    ) -> ActionOutcome:
        """``speak=False`` para lecturas que dispara la interfaz (navegar archivos):
        JARKKO no debe narrar cada clic del usuario."""

        profile = resolve_assistant(assistant)
        action = self.planner.plan_raw(tool_name, arguments)

        if action.status is PlanStatus.REJECTED:
            self.events.publish_status(AssistantStatus.ERROR, assistant=profile.key)
            outcome = await self.executor.record_non_execution(
                action,
                status=ActionStatus.REJECTED,
                assistant=profile.key,
                conversation_id=conversation_id,
            )
            self.events.publish_status(AssistantStatus.IDLE, assistant=profile.key)
            if speak:
                self._speak_action(outcome)
            return outcome

        if action.status is PlanStatus.NEEDS_CONFIRMATION:
            pending = self._request_confirmation(action, profile=profile, conversation_id=conversation_id)
            if speak:
                self.voice.say_later(self.voice.plan_for_chat(
                    chat_status="awaiting_confirmation", reply="", actions=[]
                ))
            return await self.executor.record_non_execution(
                action,
                status=ActionStatus.AWAITING_CONFIRMATION,
                message=(
                    f"Esta acción tiene riesgo {action.risk_level.value} y necesita confirmación "
                    "explícita. Confírmala en /api/actions/confirm."
                ),
                confirmation_id=pending.id,
                assistant=profile.key,
                conversation_id=conversation_id,
            )

        self.events.publish_status(AssistantStatus.EXECUTING, assistant=profile.key)
        outcome = await self.executor.execute(
            action, assistant=profile.key, conversation_id=conversation_id
        )
        self.events.publish_status(
            AssistantStatus.SUCCESS if outcome.succeeded else AssistantStatus.ERROR,
            assistant=profile.key,
        )
        self.events.publish_status(AssistantStatus.IDLE, assistant=profile.key)
        if speak:
            self._speak_action(outcome)
        return outcome

    # ------------------------------------------------------------------
    # confirmación (POST /api/actions/confirm)
    # ------------------------------------------------------------------
    async def confirm(
        self, confirmation_id: str, *, approved: bool, assistant: str | None = None
    ) -> ActionOutcome:
        pending: PendingConfirmation = self.confirmations.consume(confirmation_id)
        profile = resolve_assistant(assistant or pending.assistant)

        if not approved:
            self.events.publish_status(AssistantStatus.IDLE, assistant=profile.key)
            await self.activity.record(
                tool=pending.tool,
                arguments=pending.arguments,
                risk_level=pending.risk_level,
                status=ActionStatus.CANCELLED.value,
                message="El usuario canceló la acción.",
                assistant=profile.key,
                conversation_id=pending.conversation_id,
            )
            cancelled = ActionOutcome(
                tool=pending.tool,
                status=ActionStatus.CANCELLED,
                message="Acción cancelada. No hice nada.",
                arguments=sanitize_arguments(pending.arguments),
                confirmation_id=confirmation_id,
            )
            self._speak_action(cancelled)
            return cancelled

        # Se revalida: el sistema de archivos pudo cambiar desde que se pidió la confirmación.
        action = self.planner.plan_raw(pending.tool, pending.arguments, confirmed=True)
        if action.status is not PlanStatus.READY:
            self.events.publish_status(AssistantStatus.ERROR, assistant=profile.key)
            outcome = await self.executor.record_non_execution(
                action,
                status=ActionStatus.REJECTED,
                message=(action.error or {}).get("message")
                or "La acción dejó de ser válida desde que se pidió la confirmación.",
                confirmation_id=confirmation_id,
                assistant=profile.key,
                conversation_id=pending.conversation_id,
            )
            self.events.publish_status(AssistantStatus.IDLE, assistant=profile.key)
            return outcome

        self.events.publish_status(AssistantStatus.EXECUTING, assistant=profile.key)
        outcome = await self.executor.execute(
            action, assistant=profile.key, conversation_id=pending.conversation_id
        )
        outcome.confirmation_id = confirmation_id
        self.events.publish_status(
            AssistantStatus.SUCCESS if outcome.succeeded else AssistantStatus.ERROR,
            assistant=profile.key,
        )
        self.events.publish_status(AssistantStatus.IDLE, assistant=profile.key)
        self._speak_action(outcome)
        return outcome

    # ------------------------------------------------------------------
    # internos
    # ------------------------------------------------------------------
    async def _execute_plan(
        self, plan: ExecutionPlan, *, profile: AssistantProfile, conversation_id: str
    ) -> list[ActionOutcome]:
        outcomes: list[ActionOutcome] = []
        halted = False

        for action in plan.actions:
            if action.status is PlanStatus.REJECTED:
                outcomes.append(
                    await self.executor.record_non_execution(
                        action,
                        status=ActionStatus.REJECTED,
                        assistant=profile.key,
                        conversation_id=conversation_id,
                    )
                )
                continue

            if halted:
                outcomes.append(
                    await self.executor.record_non_execution(
                        action,
                        status=ActionStatus.SKIPPED,
                        message="No se ejecutó porque una acción anterior falló.",
                        assistant=profile.key,
                        conversation_id=conversation_id,
                    )
                )
                continue

            self.events.publish_status(
                AssistantStatus.EXECUTING, assistant=profile.key, conversation_id=conversation_id
            )
            outcome = await self.executor.execute(
                action, assistant=profile.key, conversation_id=conversation_id
            )
            outcomes.append(outcome)
            if not outcome.succeeded:
                halted = True

        return outcomes

    def _request_confirmation(
        self,
        action: PlannedAction,
        *,
        profile: AssistantProfile,
        conversation_id: str | None,
    ) -> PendingConfirmation:
        pending = self.confirmations.create(
            tool=action.tool_name,
            arguments=action.raw_arguments,
            risk_level=action.risk_level.value,
            description=action.description(),
            assistant=profile.key,
            conversation_id=conversation_id,
        )
        self.events.publish_status(
            AssistantStatus.WAITING_CONFIRMATION, assistant=profile.key, conversation_id=conversation_id
        )
        self.events.publish(EventType.CONFIRMATION_REQUIRED, pending.to_public())
        return pending

    def _speak_action(self, outcome: ActionOutcome) -> None:
        """Locución para una acción suelta (ejecución directa o confirmación)."""

        if outcome.status is ActionStatus.AWAITING_CONFIRMATION:
            chat_status = "awaiting_confirmation"
        else:
            chat_status = ChatStatus.SUCCESS if outcome.succeeded else ChatStatus.ERROR
        self.voice.say_later(
            self.voice.plan_for_chat(
                chat_status=chat_status, reply=outcome.message, actions=[outcome]
            )
        )

    def _speak(
        self,
        *,
        chat_status: str,
        reply: str,
        intent: IntentResult,
        actions: list[ActionOutcome] | None = None,
    ) -> None:
        """Pone a JARKKO a hablar sin bloquear la respuesta HTTP.

        Lo hablado no es lo escrito: en voz va una frase corta y fija (la que suena
        con su voz de identidad desde el caché) y en pantalla el detalle completo.
        """

        plan = self.voice.plan_for_chat(
            chat_status=chat_status,
            reply=reply,
            actions=actions or [],
            intent_rule=intent.matched_rule,
            needs_clarification=intent.needs_clarification,
        )
        self.voice.say_later(plan)

    async def _finish_without_actions(
        self, intent: IntentResult, profile: AssistantProfile, conversation: str
    ) -> ChatOutcome:
        status = ChatStatus.NO_ACTION
        # Una explicación de por qué no se pudo no lleva muletilla delante: «Aquí estoy.
        # No encuentro la carpeta X» suena a que no se ha enterado de nada.
        message = profile.style(
            intent.reply, status="clarification" if intent.needs_clarification else "idle"
        )
        self.events.publish_status(AssistantStatus.IDLE, assistant=profile.key, conversation_id=conversation)
        self._speak(chat_status=status, reply=message, intent=intent)
        await self.activity.log_message(
            conversation_id=conversation, assistant=profile.key, role="assistant", content=message
        )
        return ChatOutcome(
            conversation_id=conversation,
            assistant=profile.key,
            message=message,
            status=status,
            intent=intent.to_public(),
        )

    async def _finish_awaiting_confirmation(
        self,
        plan: ExecutionPlan,
        intent: IntentResult,
        profile: AssistantProfile,
        conversation: str,
    ) -> ChatOutcome:
        """Si algo del plan necesita confirmación, no se ejecuta nada del plan."""

        outcomes: list[ActionOutcome] = []
        confirmations: list[dict[str, Any]] = []

        for action in plan.actions:
            if action.status is PlanStatus.NEEDS_CONFIRMATION:
                pending = self._request_confirmation(
                    action, profile=profile, conversation_id=conversation
                )
                confirmations.append(pending.to_public())
                outcomes.append(
                    await self.executor.record_non_execution(
                        action,
                        status=ActionStatus.AWAITING_CONFIRMATION,
                        message=f"Pendiente de tu confirmación: {action.description()}",
                        confirmation_id=pending.id,
                        assistant=profile.key,
                        conversation_id=conversation,
                    )
                )
            elif action.status is PlanStatus.REJECTED:
                outcomes.append(
                    await self.executor.record_non_execution(
                        action,
                        status=ActionStatus.REJECTED,
                        assistant=profile.key,
                        conversation_id=conversation,
                    )
                )
            else:
                outcomes.append(
                    await self.executor.record_non_execution(
                        action,
                        status=ActionStatus.SKIPPED,
                        message="En espera: el plan incluye una acción que requiere confirmación.",
                        assistant=profile.key,
                        conversation_id=conversation,
                    )
                )

        reply = await self._compose(
            "", intent, outcomes, profile, status=ChatStatus.AWAITING_CONFIRMATION
        )
        self._speak(
            chat_status=ChatStatus.AWAITING_CONFIRMATION,
            reply=reply,
            intent=intent,
            actions=outcomes,
        )
        await self.activity.log_message(
            conversation_id=conversation, assistant=profile.key, role="assistant", content=reply
        )
        return ChatOutcome(
            conversation_id=conversation,
            assistant=profile.key,
            message=reply,
            status=ChatStatus.AWAITING_CONFIRMATION,
            actions=outcomes,
            requires_confirmation=True,
            confirmations=confirmations,
            intent=intent.to_public(),
        )

    async def _finish_executed(
        self,
        outcomes: list[ActionOutcome],
        intent: IntentResult,
        profile: AssistantProfile,
        conversation: str,
        message: str,
    ) -> ChatOutcome:
        ok = bool(outcomes) and all(outcome.succeeded for outcome in outcomes)
        status = ChatStatus.SUCCESS if ok else ChatStatus.ERROR
        reply = await self._compose(message, intent, outcomes, profile, status=status)

        self.events.publish_status(
            AssistantStatus.SUCCESS if ok else AssistantStatus.ERROR,
            assistant=profile.key,
            conversation_id=conversation,
        )
        self.events.publish_status(AssistantStatus.IDLE, assistant=profile.key, conversation_id=conversation)
        self._speak(chat_status=status, reply=reply, intent=intent, actions=outcomes)
        await self.activity.log_message(
            conversation_id=conversation, assistant=profile.key, role="assistant", content=reply
        )
        return ChatOutcome(
            conversation_id=conversation,
            assistant=profile.key,
            message=reply,
            status=status,
            actions=outcomes,
            requires_confirmation=False,
            intent=intent.to_public(),
        )

    async def _compose(
        self,
        message: str,
        intent: IntentResult,
        outcomes: list[ActionOutcome],
        profile: AssistantProfile,
        *,
        status: str,
    ) -> str:
        payload = [outcome.to_public() for outcome in outcomes]
        try:
            composed = await self.provider.compose_reply(
                message, intent, payload, assistant=profile.key
            )
        except Exception:  # noqa: BLE001 - la respuesta nunca debe tumbar la petición
            logger.exception("Fallo al redactar la respuesta con el proveedor")
            composed = None
        if not composed:
            composed = " ".join(item["message"] for item in payload if item.get("message")) or intent.reply
        return profile.style(composed, status=status)


_engine: AgentEngine | None = None


def get_engine() -> AgentEngine:
    """Motor compartido por la aplicación."""

    global _engine
    if _engine is None:
        _engine = AgentEngine()
    return _engine


def reset_engine() -> None:
    """Fuerza la reconstrucción del motor.  Uso en tests."""

    global _engine
    _engine = None
