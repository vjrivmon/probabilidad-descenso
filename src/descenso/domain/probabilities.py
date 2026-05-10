"""Resultado agregado de una simulación: probabilidades de descenso por equipo."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TeamProbabilities:
    team: str
    p_relegation: float
    p_by_position: dict[int, float]  # posición final -> probabilidad
    expected_points: float
    expected_position: float

    @property
    def p_safe(self) -> float:
        return 1.0 - self.p_relegation


@dataclass(frozen=True)
class RelegationProbabilities:
    n_sims: int
    teams: list[TeamProbabilities]
    seed: int | None = None

    def ranked(self) -> list[TeamProbabilities]:
        """Equipos ordenados por probabilidad de descenso, de mayor a menor."""
        return sorted(self.teams, key=lambda t: t.p_relegation, reverse=True)
