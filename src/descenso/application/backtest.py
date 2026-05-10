"""Caso de uso: backtest histórico — ¿predice mejor el modelo ajustado que el puro?

Para cada temporada pasada y cada jornada del tramo final, reconstruye el estado
*as-of* esa jornada (¡sin data leakage!), predice P(descenso) con ambos modelos y
lo compara con el desenlace real. Reporta Brier score y log-loss.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestResult:
    seasons: list[int]
    horizon_gameweeks: int
    n_sims: int
    brier_pure: float
    brier_adjusted: float
    logloss_pure: float
    logloss_adjusted: float

    @property
    def brier_improvement(self) -> float:
        if self.brier_pure == 0:
            return 0.0
        return (self.brier_pure - self.brier_adjusted) / self.brier_pure


def run_backtest(
    seasons: list[int], horizon_gameweeks: int = 5, n_sims: int = 20_000
) -> BacktestResult:
    raise NotImplementedError  # Fase 8 (CP2)
