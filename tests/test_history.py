"""Tests de `season_history` (CP3 — evolución jornada a jornada de la temporada en curso)."""

from __future__ import annotations

import datetime as dt

import pytest

from descenso.application.history import GameweekPoint, SeasonHistory, season_history
from descenso.application.run_simulation import SimulationInputs
from descenso.config import AppConfig, ModelConfig
from descenso.domain.match import Match
from descenso.domain.team import Team

_TEAM_IDS = ["a", "b", "c", "d", "e", "f"]
_ELO = {"a": 1700.0, "b": 1640.0, "c": 1600.0, "d": 1480.0, "e": 1430.0, "f": 1380.0}


def _team(tid: str) -> Team:
    return Team(
        id=tid,
        name=tid.upper(),
        clubelo_name=None,
        understat_name=None,
        fbref_name=None,
        openfootball_name=tid.upper(),
    )


def _schedule(n_played_gw: int, n_total_gw: int = 5) -> list[Match]:
    """Round-robin de 6 equipos repartido en `n_total_gw` jornadas; `n_played_gw` jugadas."""
    pairs = [(h, a) for i, h in enumerate(_TEAM_IDS) for a in _TEAM_IDS[i + 1 :]]
    matches: list[Match] = []
    day = dt.date(2099, 9, 1)
    for k, (h, a) in enumerate(pairs):
        gw = (k % n_total_gw) + 1
        played = gw <= n_played_gw
        hg, ag = ((2, 0) if _ELO[h] >= _ELO[a] else (0, 2)) if played else (None, None)
        matches.append(
            Match(
                season=2099,
                gameweek=gw,
                date=day + dt.timedelta(days=7 * gw),
                home_team=h,
                away_team=a,
                home_goals=hg,
                away_goals=ag,
            )
        )
    return matches


def _inputs(n_played_gw: int = 4, n_total_gw: int = 6) -> SimulationInputs:
    return SimulationInputs(
        teams=[_team(t) for t in _TEAM_IDS],
        elo=dict(_ELO),
        matches=_schedule(n_played_gw, n_total_gw),
    )


def _config(model_type: str = "adjusted") -> AppConfig:
    return AppConfig(season=2099, model=ModelConfig(model_type=model_type, n_relegation=3))


def test_season_history_estructura() -> None:
    hist = season_history(_config(), n_gameweeks=3, n_sims=500, seed=1, inputs=_inputs(4, 6))
    assert isinstance(hist, SeasonHistory)
    assert hist.season == 2099
    assert hist.model_type == "adjusted"
    # 3 jornadas pedidas, 4 jugadas -> J2, J3, J4
    assert [pt.gameweek for pt in hist.points] == [2, 3, 4]
    for pt in hist.points:
        assert isinstance(pt, GameweekPoint)
        assert set(pt.p_relegation) == set(_TEAM_IDS)
        assert all(0.0 <= p <= 1.0 for p in pt.p_relegation.values())
        # P(descenso) suma a n_relegation (cada simulación marca exactamente 3 descensos)
        assert sum(pt.p_relegation.values()) == pytest.approx(3.0, abs=1e-9)


def test_season_history_clampa_a_las_jornadas_jugadas() -> None:
    # se piden 10 jornadas pero solo hay 3 jugadas (de 6 posibles)
    hist = season_history(_config(), n_gameweeks=10, n_sims=400, seed=2, inputs=_inputs(3, 6))
    assert [pt.gameweek for pt in hist.points] == [1, 2, 3]


def test_season_history_modelo_puro_usa_solo_elo() -> None:
    hist = season_history(_config("pure"), n_gameweeks=2, n_sims=400, seed=1, inputs=_inputs(3, 6))
    assert hist.model_type == "pure"
    assert len(hist.points) == 2


def test_season_history_sin_partidos_jugados_levanta_value_error() -> None:
    with pytest.raises(ValueError, match="no hay partidos jugados"):
        season_history(_config(), n_gameweeks=3, n_sims=200, inputs=_inputs(0, 6))


def test_season_history_n_gameweeks_invalido_levanta_value_error() -> None:
    with pytest.raises(ValueError, match="n_gameweeks"):
        season_history(_config(), n_gameweeks=0, n_sims=200, inputs=_inputs(4, 6))


def test_season_history_es_determinista() -> None:
    a = season_history(_config(), n_gameweeks=3, n_sims=600, seed=7, inputs=_inputs(4, 6))
    b = season_history(_config(), n_gameweeks=3, n_sims=600, seed=7, inputs=_inputs(4, 6))
    assert [pt.p_relegation for pt in a.points] == [pt.p_relegation for pt in b.points]


def test_candidate_team_ids_ordenados_por_el_ultimo_punto() -> None:
    hist = season_history(_config(), n_gameweeks=3, n_sims=800, seed=3, inputs=_inputs(4, 6))
    cands = hist.candidate_team_ids()
    assert cands  # hay candidatos
    last = hist.points[-1].p_relegation
    # están ordenados de mayor a menor P en el último punto
    assert cands == sorted(cands, key=lambda t: last[t], reverse=True)
    # los 3 equipos con menos Elo (d, e, f) deben estar entre los candidatos
    assert {"d", "e", "f"} <= set(cands)
