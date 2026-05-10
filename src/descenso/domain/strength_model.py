"""El modelo de fuerza efectiva con "memoria de forma" — el diferencial del proyecto.

R_i = alpha * Elo_base_i + (1 - alpha) * FormRating_i + delta_coach_i + delta_injuries_i

FormRating_i = media ponderada exponencialmente (half-life ~75 días) de los
"performance ratings" por partido del equipo i. El performance rating de un
partido compara el resultado (mezclado con el xG para descontar suerte) con el
resultado esperado por Elo frente a ese rival, ajustando por localía.

Con alpha=1 y sin deltas se obtiene el modelo "puro" (≈ el de @LaLigaenDirecto):
útil como línea base para `compare` y `backtest`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from descenso.config import ModelConfig
from descenso.domain.match import Match


@dataclass(frozen=True)
class StrengthSnapshot:
    team: str
    as_of: dt.date
    elo_base: float
    form_rating: float
    delta_coach: float
    delta_injuries: float

    @property
    def r_eff(self) -> float:
        # El blend Elo/forma ya está incorporado en `form_rating` vs `elo_base`
        # por `compute_strengths`; este campo expone solo la suma final.
        raise NotImplementedError  # Fase 6 (CP2)


def compute_strengths(
    elo_base: dict[str, float],
    played_matches: list[Match],
    coach_changes: dict[str, list[tuple[dt.date, float]]],
    injury_adjustments: dict[str, float],
    as_of: dt.date,
    config: ModelConfig,
) -> dict[str, StrengthSnapshot]:
    """Calcula la fuerza efectiva de cada equipo a fecha `as_of`.

    Importante para el backtest: solo debe usar `played_matches` con fecha <= as_of
    (sin data leakage).
    """
    raise NotImplementedError  # Fase 6 (CP2). En CP1 se usa solo `elo_base`.
