"""Edge cases del simulador que aún no están cubiertos (equipos repetidos,
equipos sin fuerza, equipo fuera del partido pendiente).
"""

from __future__ import annotations

import pytest

from descenso.domain.match import Match
from descenso.domain.match_model import EloLogisticMatchModel
from descenso.domain.simulator import SimulationConfig, run_monte_carlo
from descenso.domain.standings import TeamRow


def _row(team: str, points: int) -> TeamRow:
    return TeamRow(team=team, played=10, won=3, drawn=1, lost=6, gf=15, ga=20, points=points)


def _model() -> EloLogisticMatchModel:
    return EloLogisticMatchModel(home_advantage_elo=65.0, draw_base=0.26)


def _cfg(n: int = 100) -> SimulationConfig:
    return SimulationConfig(n_sims=n, n_relegation=1, seed=7)


# --------------------------------------------------------------------------- #
# Equipos repetidos en team_ids
# --------------------------------------------------------------------------- #


def test_equipo_repetido_en_team_ids_levanta_error() -> None:
    with pytest.raises(ValueError, match="repetidos"):
        run_monte_carlo(
            ["a", "a", "b"],
            [_row("a", 10), _row("b", 5)],
            [],
            {},
            _model(),
            _cfg(),
        )


# --------------------------------------------------------------------------- #
# Partido pendiente con equipo fuera de la liga
# --------------------------------------------------------------------------- #


def test_partido_pendiente_con_equipo_fuera_levanta_error() -> None:
    teams = ["a", "b"]
    base = [_row("a", 20), _row("b", 15)]
    pendiente = Match(season=2025, gameweek=1, home_team="a", away_team="z")  # z no está en league
    with pytest.raises(ValueError, match="fuera de la liga"):
        run_monte_carlo(teams, base, [pendiente], {"a": 1500.0, "z": 1400.0}, _model(), _cfg())


# --------------------------------------------------------------------------- #
# Partido pendiente pero falta la fuerza de un equipo
# --------------------------------------------------------------------------- #


def test_partido_pendiente_sin_fuerza_levanta_error() -> None:
    teams = ["a", "b"]
    base = [_row("a", 20), _row("b", 15)]
    pendiente = Match(season=2025, gameweek=1, home_team="a", away_team="b")
    with pytest.raises(ValueError, match="falta la fuerza"):
        # strengths vacío -> b no tiene fuerza
        run_monte_carlo(teams, base, [pendiente], {"a": 1500.0}, _model(), _cfg())


# --------------------------------------------------------------------------- #
# Lista de equipos vacía
# --------------------------------------------------------------------------- #


def test_lista_de_equipos_vacia_levanta_error() -> None:
    with pytest.raises(ValueError, match="no hay equipos"):
        run_monte_carlo([], [], [], {}, _model(), _cfg())


# --------------------------------------------------------------------------- #
# n_sims = 0
# --------------------------------------------------------------------------- #


def test_n_sims_cero_levanta_error() -> None:
    with pytest.raises(ValueError, match="n_sims"):
        run_monte_carlo(
            ["a", "b"],
            [_row("a", 10), _row("b", 5)],
            [],
            {},
            _model(),
            SimulationConfig(n_sims=0, seed=1),
        )
