"""Niveles de riesgo de las herramientas.

El nivel de riesgo es la pieza que permite al Permission Manager decidir si una
acción se ejecuta directamente, si exige confirmación explícita del usuario o si
queda bloqueada.
"""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """Riesgo asociado a una herramienta o a una invocación concreta."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> int:
        return _WEIGHTS[self]

    def at_least(self, other: "RiskLevel") -> bool:
        """``True`` si este nivel es igual o más peligroso que ``other``."""

        return self.weight >= other.weight

    @classmethod
    def max(cls, *levels: "RiskLevel") -> "RiskLevel":
        """Nivel más alto de los indicados (``LOW`` si no se pasa ninguno)."""

        return max(levels, key=lambda level: level.weight, default=cls.LOW)


_WEIGHTS: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


#: Descripción legible de cada nivel, expuesta al frontend en ``GET /api/tools``.
RISK_DESCRIPTIONS: dict[RiskLevel, str] = {
    RiskLevel.LOW: "Solo lectura o apertura de recursos. No modifica datos del usuario.",
    RiskLevel.MEDIUM: "Modifica el sistema de archivos de forma reversible (crear, copiar, mover, renombrar).",
    RiskLevel.HIGH: "Acción potencialmente destructiva o con impacto en el sistema. Requiere confirmación explícita.",
    RiskLevel.CRITICAL: "Acción irreversible. Deshabilitada salvo activación explícita en la configuración.",
}
