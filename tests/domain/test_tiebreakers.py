"""Tests de las reglas de desempate de LaLiga (art. 200)."""

from __future__ import annotations

import pytest

from descenso.domain.match import Match
from descenso.domain.standings import TeamRow
from descenso.domain.tiebreakers import resolve_order


def _row(team: str, points: int, gf: int = 20, ga: int = 20, played: int = 20) -> TeamRow:
    return TeamRow(team=team, played=played, won=0, drawn=0, lost=0, gf=gf, ga=ga, points=points)


def _m(home: str, away: str, hg: int, ag: int, gw: int = 1) -> Match:
    return Match(
        season=2025, gameweek=gw, home_team=home, away_team=away, home_goals=hg, away_goals=ag
    )


def test_orders_by_points_first() -> None:
    rows = [_row("a", 30), _row("b", 50), _row("c", 40)]
    assert [r.team for r in resolve_order(rows, [])] == ["b", "c", "a"]


def test_two_teams_decided_by_head_to_head_points() -> None:
    # a y b empatan a 40; a ganó los dos enfrentamientos directos -> a por delante,
    # aunque b tenga mejor diferencia de goles general.
    rows = [_row("a", 40, gf=10, ga=20), _row("b", 40, gf=30, ga=10)]
    matches = [_m("a", "b", 2, 0), _m("b", "a", 0, 1, gw=2)]
    assert [r.team for r in resolve_order(rows, matches)] == ["a", "b"]


def test_two_teams_tied_h2h_fall_back_to_general_gd() -> None:
    # se repartieron los directos (1-1 y 0-0): empate en puntos y dif. directos
    # -> decide la diferencia de goles general (a: +5, b: -3).
    rows = [_row("a", 40, gf=25, ga=20), _row("b", 40, gf=17, ga=20)]
    matches = [_m("a", "b", 1, 1), _m("b", "a", 0, 0, gw=2)]
    assert [r.team for r in resolve_order(rows, matches)] == ["a", "b"]


def test_three_teams_resolved_by_mini_league() -> None:
    # a, b, c empatan a 10 puntos. Mini-liga entre ellos: a gana a b, b gana a c,
    # a empata con c -> a (4 pts) > b (3) > c (1).
    rows = [
        _row("x", 28),
        _row("a", 10, gf=8, ga=9),
        _row("b", 10, gf=10, ga=10),
        _row("c", 10, gf=12, ga=12),
    ]
    matches = [
        _m("a", "b", 2, 1),
        _m("b", "c", 1, 0, gw=2),
        _m("a", "c", 1, 1, gw=3),
        _m("x", "a", 3, 0, gw=4),  # irrelevante para el orden (las filas ya traen el total)
    ]
    assert [r.team for r in resolve_order(rows, matches)] == ["x", "a", "b", "c"]


def test_mini_league_partial_then_general() -> None:
    # a, b, c empatan a 10. En la mini-liga: a gana a b 1-0 y a c 1-0; b y c empatan
    # 1-1 -> a se separa (6 pts) pero b y c quedan idénticos en la mini-liga (1 pt,
    # dif. de goles 0) -> se cae a la dif. de goles general (b: +5, c: -5).
    rows = [
        _row("a", 10, gf=20, ga=10),
        _row("b", 10, gf=25, ga=20),
        _row("c", 10, gf=15, ga=20),
    ]
    matches = [
        _m("a", "b", 1, 0),
        _m("a", "c", 1, 0, gw=2),
        _m("b", "c", 1, 1, gw=3),
    ]
    assert [r.team for r in resolve_order(rows, matches)] == ["a", "b", "c"]


def test_no_matches_between_tied_teams_uses_general() -> None:
    # empatan a puntos y aún no se han enfrentado -> dif. de goles, luego goles a favor
    rows = [_row("a", 10, gf=12, ga=10), _row("b", 10, gf=20, ga=18), _row("c", 10, gf=14, ga=12)]
    # a: gd +2, b: gd +2, c: gd +2  -> desempata goles a favor: b(20) > c(14) > a(12)
    assert [r.team for r in resolve_order(rows, [])] == ["b", "c", "a"]


def test_tres_equipos_mini_liga_identica_cae_a_general_gd() -> None:
    """Tres equipos empatan a puntos y en la mini-liga quedan perfectamente igualados
    (todos 1 punto, diferencia de goles 0 entre ellos) -> se cae a la clasificación
    general (dif. de goles general). Cubre la rama 'len(partitions) == 1' de resolve_tied."""
    # Cada equipo gana uno y pierde uno en los enfrentamientos directos de manera que
    # la mini-liga queda: todos con 3 pts, dif. goles 0 en h2h
    rows = [
        _row("a", 10, gf=15, ga=10),  # gd general +5
        _row("b", 10, gf=12, ga=10),  # gd general +2
        _row("c", 10, gf=10, ga=12),  # gd general -2
    ]
    # a gana a b 1-0; b gana a c 1-0; c gana a a 1-0 -> cada uno 3 pts, gd=0 en mini-liga
    matches = [
        _m("a", "b", 1, 0),
        _m("b", "c", 1, 0, gw=2),
        _m("c", "a", 1, 0, gw=3),
    ]
    ordered = [r.team for r in resolve_order(rows, matches)]
    # desempate final por gd general: a(+5) > b(+2) > c(-2)
    assert ordered == ["a", "b", "c"]


def test_equipos_repetidos_en_clasificacion_levanta_error() -> None:
    """Si la clasificación tiene equipos repetidos, resolve_order lanza ValueError."""
    rows = [_row("a", 10), _row("a", 10)]  # "a" duplicado
    with pytest.raises(ValueError, match="repetidos"):
        resolve_order(rows, [])


def test_recursion_base_case_grupo_de_uno_no_rompe() -> None:
    """Cuando la mini-liga separa a un equipo en un grupo de 1, la recursión
    lo devuelve directamente (base case len==1 de resolve_tied)."""
    # a: 6 pts en mini-liga (gana a b y c); b: 3 pts; c: 0 pts -> 3 grupos de 1
    rows = [
        _row("a", 10, gf=18, ga=10),
        _row("b", 10, gf=15, ga=14),
        _row("c", 10, gf=10, ga=16),
    ]
    matches = [
        _m("a", "b", 2, 0),
        _m("a", "c", 1, 0, gw=2),
        _m("b", "c", 1, 0, gw=3),
    ]
    ordered = [r.team for r in resolve_order(rows, matches)]
    # La mini-liga los separa completamente: a(6pts) > b(3pts) > c(0pts)
    assert ordered == ["a", "b", "c"]


def test_dos_equipos_empatan_en_h2h_cae_a_general() -> None:
    """Dos equipos empatan también en el H2H directo -> clasificación general.
    Cubre la rama `return sorted(teams, key=general_key)` en el bloque de 2 equipos."""
    rows = [
        _row("a", 40, gf=25, ga=20),  # gd +5
        _row("b", 40, gf=20, ga=20),  # gd 0
    ]
    # Los dos H2H terminaron 0-0: pts h2h iguales, dif. goles h2h iguales
    matches = [
        _m("a", "b", 0, 0),
        _m("b", "a", 0, 0, gw=2),
    ]
    ordered = [r.team for r in resolve_order(rows, matches)]
    # cae a gd general: a(+5) > b(0)
    assert ordered == ["a", "b"]
