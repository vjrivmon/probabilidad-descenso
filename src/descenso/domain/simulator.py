"""Simulador Monte Carlo del calendario restante (vectorizado con numpy)."""

from __future__ import annotations

from dataclasses import dataclass

from descenso.domain.match import Match
from descenso.domain.match_model import MatchModel
from descenso.domain.probabilities import RelegationProbabilities
from descenso.domain.standings import TeamRow


@dataclass
class SimulationConfig:
    n_sims: int = 100_000
    n_relegation: int = 3  # plazas de descenso en LaLiga
    seed: int | None = None


def run_monte_carlo(
    team_ids: list[str],
    base_table: list[TeamRow],
    remaining_matches: list[Match],
    strengths: dict[str, float],
    match_model: MatchModel,
    config: SimulationConfig,
) -> RelegationProbabilities:
    """Corre `config.n_sims` simulaciones del calendario restante.

    Para cada iteración: respeta los partidos con `is_fixed`, muestrea el resto
    con `match_model`, construye la clasificación final con las reglas de LaLiga
    y registra qué equipos caen en las últimas `n_relegation` plazas. Devuelve
    las probabilidades agregadas por equipo.
    """
    raise NotImplementedError  # Fase 6
