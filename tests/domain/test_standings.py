"""Tests de la construcción y ordenación de la clasificación."""

from __future__ import annotations

import pytest

from descenso.domain.match import Match
from descenso.domain.standings import build_table, order_table


def _m(home: str, away: str, hg: int | None = None, ag: int | None = None, gw: int = 1) -> Match:
    return Match(
        season=2025, gameweek=gw, home_team=home, away_team=away, home_goals=hg, away_goals=ag
    )


def test_build_table_counts_results() -> None:
    teams = ["a", "b", "c"]
    matches = [_m("a", "b", 2, 0), _m("b", "c", 1, 1, gw=2), _m("c", "a", 0, 3, gw=3)]
    table = {r.team: r for r in build_table(teams, matches)}

    assert table["a"].played == 2
    assert table["a"].won == 2
    assert table["a"].points == 6
    assert table["a"].gf == 5
    assert table["a"].ga == 0
    assert table["a"].gd == 5

    assert table["b"].points == 1
    assert table["b"].drawn == 1
    assert table["b"].lost == 1
    assert table["b"].gd == -2

    assert table["c"].points == 1
    assert table["c"].gf == 1
    assert table["c"].ga == 4


def test_build_table_ignores_pending_matches() -> None:
    table = {r.team: r for r in build_table(["a", "b"], [_m("a", "b")])}
    assert table["a"].played == 0
    assert table["a"].points == 0


def test_build_table_applies_points_adjustment() -> None:
    rows = build_table(["a", "b"], [_m("a", "b", 1, 0)], points_adjustments={"a": -3})
    table = {r.team: r for r in rows}
    assert table["a"].points == 3
    assert table["a"].points_adjustment == -3
    assert table["a"].total_points == 0


def test_build_table_rejects_unknown_team_in_match() -> None:
    with pytest.raises(ValueError, match="fuera de la liga"):
        build_table(["a", "b"], [_m("a", "zzz", 1, 0)])


def test_build_table_rejects_unknown_team_in_adjustments() -> None:
    with pytest.raises(ValueError, match="desconocidos"):
        build_table(["a", "b"], [], points_adjustments={"zzz": 3})


def test_order_table_breaks_tie_by_general_gd() -> None:
    # b y c empatan a 1 punto; el partido directo fue 1-1 -> decide la dif. de goles general
    teams = ["a", "b", "c"]
    matches = [_m("a", "b", 2, 0), _m("b", "c", 1, 1, gw=2), _m("c", "a", 0, 3, gw=3)]
    ordered = [r.team for r in order_table(build_table(teams, matches), matches)]
    assert ordered == ["a", "b", "c"]
