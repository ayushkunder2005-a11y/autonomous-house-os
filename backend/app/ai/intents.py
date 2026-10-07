import re
from typing import Protocol

from app.schemas.domain import StructuredIntent


class IntentProvider(Protocol):
    async def interpret(self, text: str) -> StructuredIntent: ...


class RulesIntentProvider:
    """Deterministic baseline. An LLM provider may replace it but cannot execute commands."""

    async def interpret(self, text: str) -> StructuredIntent:
        normalized = " ".join(text.lower().strip().split())
        if any(
            phrase in normalized
            for phrase in ("prepare the house for sleeping", "sleep mode", "bedtime")
        ):
            return StructuredIntent(
                intent="sleep_mode",
                scope="house",
                requires_confirmation=False,
                confidence=0.98,
                executable=True,
            )
        if any(
            phrase in normalized for phrase in ("away mode", "leaving the house", "i am leaving")
        ):
            return StructuredIntent(
                intent="away_mode",
                scope="house",
                requires_confirmation=True,
                confidence=0.92,
                executable=False,
                reason="Away mode may lock doors and requires confirmation",
            )
        temperature = re.search(
            r"(?:ac|air conditioner).*?(?:to|at)\s*(\d{2})(?:\s*°?c)?", normalized
        )
        if temperature:
            value = int(temperature.group(1))
            valid = 16 <= value <= 30
            return StructuredIntent(
                intent="set_temperature",
                scope="house" if "all" in normalized else "unspecified",
                parameters={"temperature": value},
                requires_confirmation=False,
                confidence=0.86,
                executable=valid,
                reason=None if valid else "Temperature violates the deterministic safety range",
            )
        return StructuredIntent(
            intent="unknown",
            scope="unknown",
            requires_confirmation=True,
            confidence=0.0,
            executable=False,
            reason="No supported intent matched",
        )


intent_provider: IntentProvider = RulesIntentProvider()
