"""Tests de las piezas puras de la CLI y de los adaptadores que no tocan la red."""

from __future__ import annotations

from pathlib import Path

import pytest

from descenso.adapters.data.schedule import season_slug
from descenso.adapters.data.team_aliases import TeamAliasError, load_teams, resolve_from_source
from descenso.cli.app import _format_pct, _parse_fix
from descenso.domain.team import Team

ALIASES = Path("data/team_aliases.yaml")


@pytest.fixture(scope="module")
def teams() -> list[Team]:
    return load_teams(ALIASES)


def test_season_slug() -> None:
    assert season_slug(2025) == "2025-26"
    assert season_slug(1999) == "1999-00"
    assert season_slug(2009) == "2009-10"


@pytest.mark.parametrize(
    ("p", "expected"),
    [(0.9989, "99,89"), (0.0811, "08,11"), (1.0, "100,00"), (0.0, "00,00"), (0.5, "50,00")],
)
def test_format_pct(p: float, expected: str) -> None:
    assert _format_pct(p) == expected


def test_aliases_cover_all_teams_in_every_source(teams: list[Team]) -> None:
    assert len(teams) == 20
    for source in ("clubelo", "understat", "fbref", "openfootball"):
        for team in teams:
            resolved = resolve_from_source(teams, source, getattr(team, f"{source}_name"))
            assert resolved.id == team.id


def test_resolve_from_source_unknown_source(teams: list[Team]) -> None:
    with pytest.raises(TeamAliasError, match="fuente de datos desconocida"):
        resolve_from_source(teams, "transfermarkt", "Barcelona")


def test_resolve_from_source_orphan_name(teams: list[Team]) -> None:
    with pytest.raises(TeamAliasError, match="no está en el mapeo"):
        resolve_from_source(teams, "openfootball", "Cádiz CF")


def test_parse_fix_ok(teams: list[Team]) -> None:
    fx = _parse_fix("Levante 3-2 Osasuna", teams)
    assert (fx.home_team, fx.home_goals, fx.away_team, fx.away_goals) == (
        "levante",
        3,
        "osasuna",
        2,
    )


def test_parse_fix_uses_display_names_and_spacing(teams: list[Team]) -> None:
    fx = _parse_fix("Real Oviedo 0 - 0 Getafe CF", teams)
    assert fx.home_team == "real-oviedo"
    assert fx.away_team == "getafe"
    assert (fx.home_goals, fx.away_goals) == (0, 0)


def test_parse_fix_bad_format(teams: list[Team]) -> None:
    with pytest.raises(ValueError, match="no entiendo"):
        _parse_fix("Levante vs Osasuna", teams)


def test_parse_fix_unknown_team(teams: list[Team]) -> None:
    with pytest.raises(ValueError, match="no reconozco el equipo"):
        _parse_fix("Cadiz 1-0 Levante", teams)


def test_parse_fix_same_team(teams: list[Team]) -> None:
    with pytest.raises(ValueError, match="contra sí mismo"):
        _parse_fix("Levante 1-1 Levante UD", teams)


def test_parse_fix_absurd_score(teams: list[Team]) -> None:
    with pytest.raises(ValueError, match="marcador irreal"):
        _parse_fix("Levante 99-0 Osasuna", teams)
