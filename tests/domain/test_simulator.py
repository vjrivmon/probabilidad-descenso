"""Tests del simulador Monte Carlo (CP1)."""

from __future__ import annotations

import pytest

from descenso.domain.match import Match
from descenso.domain.match_model import EloLogisticMatchModel
from descenso.domain.simulator import SimulationConfig, run_monte_carlo
from descenso.domain.standings import TeamRow


def _row(team: str, points: int, gf: int = 20, ga: int = 20, played: int = 30) -> TeamRow:
    return TeamRow(team=team, played=played, won=0, drawn=0, lost=0, gf=gf, ga=ga, points=points)


def _model() -> EloLogisticMatchModel:
    return EloLogisticMatchModel(home_advantage_elo=65.0, draw_base=0.26)


def test_no_remaining_matches_is_deterministic() -> None:
    teams = ["a", "b", "c", "d"]
    base = [_row("a", 50), _row("b", 40), _row("c", 30), _row("d", 20)]
    cfg = SimulationConfig(n_sims=500, n_relegation=2, seed=1)
    res = run_monte_carlo(teams, base, [], {}, _model(), cfg)
    by = {t.team: t for t in res.teams}
    assert by["a"].p_relegation == 0.0 and by["b"].p_relegation == 0.0
    assert by["c"].p_relegation == 1.0 and by["d"].p_relegation == 1.0
    assert by["a"].expected_position == 1.0 and by["d"].expected_position == 4.0
    assert by["a"].expected_points == pytest.approx(50.0)
    assert by["a"].p_by_position == {1: 1.0}


def test_fixed_results_are_respected() -> None:
    teams = ["a", "b"]
    base = [_row("a", 10), _row("b", 10)]
    fixed = Match(
        season=2025,
        gameweek=38,
        home_team="a",
        away_team="b",
        home_goals=3,
        away_goals=0,
        is_fixed=True,
    )
    cfg = SimulationConfig(n_sims=200, n_relegation=1, seed=1)
    res = run_monte_carlo(teams, base, [fixed], {}, _model(), cfg)
    by = {t.team: t for t in res.teams}
    assert by["a"].expected_points == pytest.approx(13.0)
    assert by["a"].p_relegation == 0.0
    assert by["b"].p_relegation == 1.0


def test_probabilities_well_formed_and_reproducible() -> None:
    teams = ["a", "b", "c", "d", "e", "f"]
    base = [
        _row("a", 30),
        _row("b", 28),
        _row("c", 27),
        _row("d", 26),
        _row("e", 25),
        _row("f", 24),
    ]
    matches: list[Match] = []
    gw = 1
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            matches.append(Match(season=2025, gameweek=gw, home_team=teams[i], away_team=teams[j]))
            gw += 1
    strengths = dict.fromkeys(teams, 1500.0)
    cfg = SimulationConfig(n_sims=3000, n_relegation=3, seed=123)

    r1 = run_monte_carlo(teams, base, matches, strengths, _model(), cfg)
    r2 = run_monte_carlo(teams, base, matches, strengths, _model(), cfg)
    p1 = {t.team: t.p_relegation for t in r1.teams}
    p2 = {t.team: t.p_relegation for t in r2.teams}

    assert p1 == p2  # misma semilla -> mismo resultado
    assert all(0.0 <= v <= 1.0 for v in p1.values())
    assert sum(p1.values()) == pytest.approx(3.0)  # exactamente n_relegation por simulación
    assert p1["f"] > p1["a"]  # el colista actual corre más riesgo que el líder de la zona
    for t in r1.teams:
        assert sum(t.p_by_position.values()) == pytest.approx(1.0)
        assert 1.0 <= t.expected_position <= float(len(teams))


def test_rejects_table_missing_a_team() -> None:
    with pytest.raises(ValueError, match="no cubre"):
        run_monte_carlo(
            ["a", "b"], [_row("a", 10)], [], {}, _model(), SimulationConfig(n_sims=10, seed=1)
        )


def test_rejects_non_positive_sims() -> None:
    with pytest.raises(ValueError, match="n_sims"):
        run_monte_carlo(
            ["a", "b"],
            [_row("a", 10), _row("b", 10)],
            [],
            {},
            _model(),
            SimulationConfig(n_sims=0, seed=1),
        )
