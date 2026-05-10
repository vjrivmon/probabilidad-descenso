"""Caso de uso: comparar el modelo puro (solo Elo) con el ajustado (Elo + forma + ...)."""

from __future__ import annotations

from dataclasses import dataclass

from descenso.config import AppConfig


@dataclass(frozen=True)
class ComparisonRow:
    team: str
    p_pure: float
    p_adjusted: float
    delta: float  # p_adjusted - p_pure (en puntos porcentuales)
    note: str  # factor responsable del cambio (forma / xG / entrenador / bajas)


def compare_models(
    config: AppConfig, n_sims: int | None = None, seed: int | None = None
) -> list[ComparisonRow]:
    """Corre las dos variantes del modelo con la misma seed y devuelve la tabla comparativa."""
    raise NotImplementedError  # Fase 8 (CP2)
