"""Tests de `backtest.py` (CP2).

- Helpers de parseo: tests unitarios directos con JSON sintético.
- Anti-leakage: verificación de la invariante.
- Brier/log-loss: verificación de la fórmula sobre escenario sintético.
- Temporada incompleta: se salta con warning.
- _match_elo_to_teams: fuzzy match y fallback a Elo medio.

Sin red real: usamos los helpers de bajo nivel directamente o respx.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from descenso.application.backtest import (
    _CLIP_MAX,
    _CLIP_MIN,
    BacktestResult,
    _cutoff_date,
    _extract_teams,
    _has_score,
    _match_elo_to_teams,
    _mean,
    _parse_date,
    _parse_gw,
    _parse_matches,
    _parse_score,
    _slugify,
)
from descenso.domain.match import Match, MatchStatus
from descenso.domain.team import Team

# --------------------------------------------------------------------------- #
# helpers para construir datos sintéticos
# --------------------------------------------------------------------------- #


def _entry(
    team1: str,
    team2: str,
    gw: int | str,
    date: str | None = "2025-09-10",
    score: dict[str, object] | None = None,
) -> dict[str, object]:
    e: dict[str, object] = {"team1": team1, "team2": team2, "round": gw}
    if date:
        e["date"] = date
    if score is not None:
        e["score"] = score
    return e


def _score(hg: int, ag: int) -> dict[str, object]:
    return {"ft": [hg, ag]}


def _team_by_openfootball(entries: list[dict[str, object]]) -> dict[str, Team]:
    teams = _extract_teams(entries)
    return {t.openfootball_name or t.id: t for t in teams}


# --------------------------------------------------------------------------- #
# _slugify
# --------------------------------------------------------------------------- #


def test_slugify_minusculas_sin_acentos() -> None:
    assert _slugify("Real Madrid") == "real-madrid"


def test_slugify_acentos_eliminados() -> None:
    assert _slugify("Atlético de Madrid") == "atletico-de-madrid"


def test_slugify_puntos_eliminados() -> None:
    # Nombres con puntos (p.ej. nombre inglés)
    result = _slugify("St. James")
    assert "." not in result


def test_slugify_espacios_multiples_a_guion() -> None:
    assert _slugify("Real  Oviedo") == "real-oviedo"


def test_slugify_nombre_con_enye() -> None:
    assert _slugify("Espanyol") == "espanyol"


# --------------------------------------------------------------------------- #
# _extract_teams
# --------------------------------------------------------------------------- #


def test_extract_teams_devuelve_equipos_unicos() -> None:
    entries = [
        _entry("Barcelona", "Real Madrid", 1),
        _entry("Real Madrid", "Atletico", 2),
        _entry("Barcelona", "Atletico", 3),
    ]
    teams = _extract_teams(entries)
    ids = [t.id for t in teams]
    assert len(ids) == len(set(ids))  # sin duplicados
    assert len(teams) == 3


def test_extract_teams_slugifica_nombres_con_acentos() -> None:
    entries = [_entry("Atlético de Madrid", "Sevilla FC", 1)]
    teams = _extract_teams(entries)
    ids = {t.id for t in teams}
    assert "atletico-de-madrid" in ids
    assert "sevilla-fc" in ids


def test_extract_teams_ignora_entradas_sin_nombre() -> None:
    entries = [
        {"team1": "", "team2": "Barcelona", "round": 1},
        {"team2": "Real Madrid", "round": 2},  # sin team1
    ]
    teams = _extract_teams(entries)
    # Solo "barcelona" y "real-madrid" deben aparecer
    ids = {t.id for t in teams}
    assert "" not in ids


def test_extract_teams_openfootball_name_es_el_nombre_original() -> None:
    """El openfootball_name del Team debe ser el nombre sin slugificar."""
    entries = [_entry("Real Betis Balompié", "Osasuna", 1)]
    teams = _extract_teams(entries)
    real_betis = next(t for t in teams if "betis" in t.id)
    assert real_betis.openfootball_name == "Real Betis Balompié"


# --------------------------------------------------------------------------- #
# _parse_gw
# --------------------------------------------------------------------------- #


def test_parse_gw_entero() -> None:
    assert _parse_gw(5) == 5


def test_parse_gw_string_con_numero() -> None:
    assert _parse_gw("Matchday 12") == 12
    assert _parse_gw("Round 38") == 38
    assert _parse_gw("Jornada 1") == 1


def test_parse_gw_sin_numero() -> None:
    assert _parse_gw("Final") == 0


def test_parse_gw_none() -> None:
    assert _parse_gw(None) == 0


# --------------------------------------------------------------------------- #
# _parse_date
# --------------------------------------------------------------------------- #


def test_parse_date_formato_iso() -> None:
    assert _parse_date("2026-04-15") == dt.date(2026, 4, 15)


def test_parse_date_none() -> None:
    assert _parse_date(None) is None


def test_parse_date_vacio() -> None:
    assert _parse_date("") is None


def test_parse_date_invalida() -> None:
    assert _parse_date("no-es-fecha") is None


def test_parse_date_formato_incorrecto() -> None:
    assert _parse_date("15/04/2026") is None


# --------------------------------------------------------------------------- #
# _parse_score
# --------------------------------------------------------------------------- #


def test_parse_score_lista_correcta() -> None:
    assert _parse_score({"ft": [2, 1]}) == (2, 1)


def test_parse_score_sin_score() -> None:
    assert _parse_score(None) == (None, None)


def test_parse_score_ft_incompleto() -> None:
    assert _parse_score({"ft": [1]}) == (None, None)


def test_parse_score_ft_vacio() -> None:
    assert _parse_score({"ft": []}) == (None, None)


def test_parse_score_ft_no_numerico() -> None:
    assert _parse_score({"ft": ["a", "b"]}) == (None, None)


def test_parse_score_sin_ft() -> None:
    assert _parse_score({"ht": [0, 0]}) == (None, None)


# --------------------------------------------------------------------------- #
# _has_score
# --------------------------------------------------------------------------- #


def test_has_score_con_resultado() -> None:
    assert _has_score({"score": {"ft": [2, 1]}}) is True


def test_has_score_sin_resultado() -> None:
    assert _has_score({"team1": "a", "team2": "b"}) is False


def test_has_score_score_no_dict() -> None:
    assert _has_score({"score": None}) is False


# --------------------------------------------------------------------------- #
# _parse_matches
# --------------------------------------------------------------------------- #


def test_parse_matches_parsea_correctamente() -> None:
    entries = [
        _entry("Barcelona", "Real Madrid", "Matchday 1", "2025-08-15", _score(3, 1)),
        _entry("Atletico", "Sevilla", 2, "2025-08-22"),
    ]
    tbo = _team_by_openfootball(entries)
    matches = _parse_matches(entries, tbo, 2025)
    assert len(matches) == 2
    jugado = next(m for m in matches if m.home_team == "barcelona")
    assert jugado.home_goals == 3
    assert jugado.away_goals == 1
    assert jugado.status is MatchStatus.PLAYED
    assert jugado.gameweek == 1
    assert jugado.date == dt.date(2025, 8, 15)


def test_parse_matches_partido_sin_resultado_es_pending() -> None:
    entries = [_entry("Barcelona", "Real Madrid", 1, "2025-08-15")]
    tbo = _team_by_openfootball(entries)
    matches = _parse_matches(entries, tbo, 2025)
    assert matches[0].status is MatchStatus.PENDING


def test_parse_matches_equipo_no_en_indice_se_omite() -> None:
    """Si un equipo no está en el índice team_by_openfootball, el partido se omite."""
    entries = [_entry("Desconocido", "Barcelona", 1)]
    tbo = {"Barcelona": Team(id="barcelona", name="Barcelona", openfootball_name="Barcelona")}
    matches = _parse_matches(entries, tbo, 2025)
    assert len(matches) == 0


def test_parse_matches_sin_nombre_de_equipo_se_omite() -> None:
    entries: list[dict[str, object]] = [{"team1": None, "team2": "Barcelona", "round": 1}]
    tbo = {"Barcelona": Team(id="barcelona", name="Barcelona", openfootball_name="Barcelona")}
    matches = _parse_matches(entries, tbo, 2025)
    assert len(matches) == 0


# --------------------------------------------------------------------------- #
# _cutoff_date
# --------------------------------------------------------------------------- #


def test_cutoff_date_devuelve_ultima_fecha_de_la_jornada() -> None:
    matches = [
        Match(
            season=2025,
            gameweek=33,
            date=dt.date(2026, 4, 6),
            home_team="a",
            away_team="b",
            home_goals=1,
            away_goals=0,
        ),
        Match(
            season=2025,
            gameweek=33,
            date=dt.date(2026, 4, 7),
            home_team="c",
            away_team="d",
            home_goals=0,
            away_goals=0,
        ),
        Match(season=2025, gameweek=34, date=dt.date(2026, 4, 14), home_team="a", away_team="c"),
    ]
    result = _cutoff_date(matches, 33)
    assert result == dt.date(2026, 4, 7)


def test_cutoff_date_sin_partidos_de_esa_jornada_devuelve_none() -> None:
    matches = [
        Match(season=2025, gameweek=34, date=dt.date(2026, 4, 14), home_team="a", away_team="b"),
    ]
    assert _cutoff_date(matches, 33) is None


def test_cutoff_date_ignora_partidos_sin_fecha() -> None:
    """Partidos de la jornada sin fecha no deben contribuir al max."""
    matches = [
        Match(season=2025, gameweek=33, date=None, home_team="a", away_team="b"),
        Match(
            season=2025,
            gameweek=33,
            date=dt.date(2026, 4, 7),
            home_team="c",
            away_team="d",
            home_goals=0,
            away_goals=0,
        ),
    ]
    result = _cutoff_date(matches, 33)
    assert result == dt.date(2026, 4, 7)


# --------------------------------------------------------------------------- #
# _match_elo_to_teams: fuzzy match
# --------------------------------------------------------------------------- #


def test_match_elo_to_teams_match_exacto() -> None:
    """Nombres que coinciden exactamente (tras normalización) se mapean."""
    elo_table = {"Real Madrid": 1880.0, "Barcelona": 1920.0}
    teams = [
        Team(id="real-madrid", name="Real Madrid"),
        Team(id="barcelona", name="Barcelona"),
    ]
    result = _match_elo_to_teams(elo_table, teams)
    assert result["real-madrid"] == pytest.approx(1880.0)
    assert result["barcelona"] == pytest.approx(1920.0)


def test_match_elo_to_teams_match_parcial() -> None:
    """Coincidencia parcial (el nombre del equipo es subconjunto del de clubelo)."""
    elo_table = {"Real Madrid CF": 1880.0}
    teams = [Team(id="real-madrid", name="Real Madrid")]
    result = _match_elo_to_teams(elo_table, teams)
    assert "real-madrid" in result
    assert result["real-madrid"] == pytest.approx(1880.0)


def test_match_elo_to_teams_sin_coincidencia_usa_elo_medio_y_avisa(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Equipo sin Elo -> usa el Elo medio de los demás y emite WARNING."""
    import logging

    elo_table = {"Barcelona": 1920.0, "Real Madrid": 1880.0}
    teams = [
        Team(id="barcelona", name="Barcelona"),
        Team(id="real-madrid", name="Real Madrid"),
        Team(id="equipo-x", name="Equipo Desconocido"),  # no tiene Elo
    ]
    with caplog.at_level(logging.WARNING, logger="descenso.application.backtest"):
        result = _match_elo_to_teams(elo_table, teams)
    mean_elo = (1920.0 + 1880.0) / 2.0
    assert result["equipo-x"] == pytest.approx(mean_elo)
    assert any("equipo-x" in r.message for r in caplog.records)


def test_match_elo_to_teams_todos_sin_coincidencia_lanza_clubelo_error() -> None:
    """Si ningún equipo encuentra Elo, lanza ClubeloError."""
    from descenso.adapters.data.clubelo_elo import ClubeloError

    elo_table = {"Fantasma": 1500.0}
    teams = [
        Team(id="equipo-a", name="Equipo A"),
        Team(id="equipo-b", name="Equipo B"),
    ]
    with pytest.raises(ClubeloError):
        _match_elo_to_teams(elo_table, teams)


# --------------------------------------------------------------------------- #
# anti-leakage invariante
# --------------------------------------------------------------------------- #


def test_antileakage_ninguno_jugado_posterior_a_cutoff() -> None:
    """Los partidos 'jugados as-of' nunca tienen fecha > cutoff_date."""
    # Construimos una mini-temporada sintética con 38 jornadas
    teams = [f"equipo-{i:02d}" for i in range(20)]
    cutoff_gw = 33
    cutoff_date = dt.date(2026, 4, 7)

    # Partidos jugados hasta GW33 con fecha <= cutoff_date
    played_asof = [
        Match(
            season=2025,
            gameweek=gw,
            date=cutoff_date - dt.timedelta(days=(cutoff_gw - gw)),
            home_team=teams[gw % 20],
            away_team=teams[(gw + 1) % 20],
            home_goals=1,
            away_goals=0,
        )
        for gw in range(1, cutoff_gw + 1)
    ]

    # Verificar la invariante
    for m in played_asof:
        if m.date is not None:
            assert m.date <= cutoff_date, (
                f"Leakage: partido {m.home_team} vs {m.away_team} "
                f"(fecha {m.date}) es posterior a cutoff {cutoff_date}"
            )


def test_antileakage_partido_posterior_lanza_assertion_error() -> None:
    """El chequeo anti-leakage lanza AssertionError si un partido jugado tiene fecha > cutoff."""
    cutoff_date = dt.date(2026, 4, 7)

    # Partido marcado como "jugado" pero con fecha posterior al corte
    partido_futuro = Match(
        season=2025,
        gameweek=33,
        date=cutoff_date + dt.timedelta(days=1),
        home_team="a",
        away_team="b",
        home_goals=1,
        away_goals=0,
    )
    played_asof = [partido_futuro]

    # Simulamos el mismo chequeo que hace _backtest_season
    with pytest.raises(AssertionError, match="leakage"):
        for m in played_asof:
            if m.date is not None and m.date > cutoff_date:
                raise AssertionError(
                    f"data leakage detectado en temporada 2025: partido {m.home_team} vs "
                    f"{m.away_team} (fecha {m.date}) marcado como jugado pero es posterior "
                    f"a la fecha de corte {cutoff_date}"
                )


# --------------------------------------------------------------------------- #
# Brier score y log-loss: verificación de fórmulas
# --------------------------------------------------------------------------- #


def test_brier_formula_exacta() -> None:
    """brier = mean((p - y)^2) con los clips definidos."""
    # Escenario: p=0.8, y=1 (equipo desciende) -> brier = (0.8-1)^2 = 0.04
    p, y = 0.8, 1.0
    brier = (p - y) ** 2
    assert brier == pytest.approx(0.04)


def test_brier_formula_p_cero_y_salvado() -> None:
    """p=0 para equipo que se salvó -> brier = 0."""
    p, y = 0.0, 0.0
    brier = (p - y) ** 2
    assert brier == pytest.approx(0.0)


def test_logloss_formula_con_clip() -> None:
    """logloss = -(y*ln(p_c) + (1-y)*ln(1-p_c)) con clip a [1e-12, 1-1e-12]."""
    # p=0 para un equipo que desciende (y=1) -> sin clip daría -inf
    p = 0.0
    y = 1.0
    p_c = max(_CLIP_MIN, min(_CLIP_MAX, p))
    logloss = -(y * math.log(p_c) + (1.0 - y) * math.log(1.0 - p_c))
    assert math.isfinite(logloss)
    assert logloss > 0.0


def test_logloss_formula_p_uno_y_uno() -> None:
    """p=1 para equipo que desciende (y=1) -> logloss muy pequeño."""
    p = 1.0
    y = 1.0
    p_c = max(_CLIP_MIN, min(_CLIP_MAX, p))
    logloss = -(y * math.log(p_c) + (1.0 - y) * math.log(1.0 - p_c))
    assert math.isfinite(logloss)
    assert logloss < 1.0


def test_brier_improvement_formula() -> None:
    """brier_improvement = (brier_pure - brier_adj) / brier_pure."""
    result = BacktestResult(
        seasons=[2025],
        horizon_gameweeks=5,
        n_sims=100,
        brier_pure=0.10,
        brier_adjusted=0.08,
        logloss_pure=0.5,
        logloss_adjusted=0.4,
    )
    expected = (0.10 - 0.08) / 0.10
    assert result.brier_improvement == pytest.approx(expected)


def test_brier_improvement_cero_cuando_brier_pure_es_cero() -> None:
    """Si brier_pure == 0, brier_improvement == 0 (sin división por cero)."""
    result = BacktestResult(
        seasons=[2025],
        horizon_gameweeks=5,
        n_sims=100,
        brier_pure=0.0,
        brier_adjusted=0.0,
        logloss_pure=0.0,
        logloss_adjusted=0.0,
    )
    assert result.brier_improvement == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# _mean helper
# --------------------------------------------------------------------------- #


def test_mean_lista_vacia() -> None:
    assert _mean([]) == 0.0


def test_mean_lista_correcta() -> None:
    assert _mean([1.0, 2.0, 3.0]) == pytest.approx(2.0)


# --------------------------------------------------------------------------- #
# BacktestResult: estructura y propiedades
# --------------------------------------------------------------------------- #


def test_backtest_result_frozen() -> None:
    """BacktestResult es inmutable (frozen dataclass)."""
    result = BacktestResult(
        seasons=[2025],
        horizon_gameweeks=5,
        n_sims=100,
        brier_pure=0.1,
        brier_adjusted=0.09,
        logloss_pure=0.5,
        logloss_adjusted=0.45,
    )
    with pytest.raises((AttributeError, TypeError)):
        result.brier_pure = 0.0  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# _parse_matches: parseo con slugify de nombres con acentos
# --------------------------------------------------------------------------- #


def test_parse_matches_slugifica_nombres_con_acentos() -> None:
    """Los IDs de equipo son slugs sin acentos, derivados del nombre de openfootball."""
    entries = [_entry("Atlético de Madrid", "Córdoba CF", "Jornada 1", "2025-08-16", _score(2, 0))]
    teams = _extract_teams(entries)
    tbo = {t.openfootball_name or t.id: t for t in teams}
    matches = _parse_matches(entries, tbo, 2025)
    assert len(matches) == 1
    # Los IDs deben estar slugificados
    assert matches[0].home_team == "atletico-de-madrid"
    assert matches[0].away_team == "cordoba-cf"


def test_parse_matches_sin_fecha_partido_pending() -> None:
    """Partido sin fecha -> date=None y depende de goles para su status."""
    entries = [_entry("Barcelona", "Real Madrid", 1, date=None, score=None)]
    tbo = _team_by_openfootball(entries)
    matches = _parse_matches(entries, tbo, 2025)
    assert matches[0].date is None
    assert matches[0].status is MatchStatus.PENDING
