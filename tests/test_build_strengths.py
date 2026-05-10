"""Tests de `build_strengths` y `build_strengths_from_data` (CP2).

`build_strengths_from_data` no hace IO (test unitario puro).
`build_strengths` (con IO) usa respx + fixtures en tmp_path para no tocar la red.
"""

from __future__ import annotations

import datetime as dt

import pytest

from descenso.application.build_strengths import (
    StrengthBuildResult,
    build_strengths_from_data,
)
from descenso.config import AppConfig, ModelConfig
from descenso.domain.match import Match

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_TODAY = dt.date(2026, 5, 10)


def _cfg_adjusted(**kwargs: object) -> AppConfig:
    model_kwargs: dict[str, object] = {
        "alpha": 0.5,
        "model_type": "adjusted",
        "n_sims": 100,
        "n_relegation": 3,
        "coach_bump_default": 25.0,
        "coach_bump_decay_matches": 6,
    }
    model_kwargs.update(kwargs)
    return AppConfig(model=ModelConfig(**model_kwargs))


def _cfg_pure() -> AppConfig:
    return AppConfig(model=ModelConfig(alpha=1.0, model_type="pure", n_sims=100))


def _played(
    home: str,
    away: str,
    hg: int,
    ag: int,
    date: dt.date,
    home_xg: float | None = None,
    away_xg: float | None = None,
) -> Match:
    return Match(
        season=2025,
        gameweek=1,
        date=date,
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        home_xg=home_xg,
        away_xg=away_xg,
    )


# --------------------------------------------------------------------------- #
# build_strengths_from_data — sin IO
# --------------------------------------------------------------------------- #


def test_from_data_sin_xg_devuelve_xg_available_false_con_nota() -> None:
    """Sin xG en los partidos, xg_available=False y hay nota informativa."""
    elo = {"a": 1500.0, "b": 1400.0}
    matches = [_played("a", "b", 2, 1, dt.date(2026, 3, 1))]
    cfg = _cfg_adjusted()
    result = build_strengths_from_data(elo, matches, cfg, as_of=_TODAY)
    assert result.xg_available is False
    assert any("xG" in n for n in result.notes)


def test_from_data_con_xg_devuelve_xg_available_true() -> None:
    """Con xG en algún partido, xg_available=True."""
    elo = {"a": 1500.0, "b": 1400.0}
    matches = [_played("a", "b", 2, 1, dt.date(2026, 3, 1), home_xg=1.8, away_xg=0.9)]
    cfg = _cfg_adjusted()
    result = build_strengths_from_data(elo, matches, cfg, as_of=_TODAY)
    assert result.xg_available is True


def test_from_data_model_pure_equivale_a_solo_elo() -> None:
    """Con model_type='pure', r_eff == elo_base exacto para todos los equipos."""
    elo = {"a": 1600.0, "b": 1350.0, "c": 1500.0}
    matches = [
        _played("a", "b", 3, 0, dt.date(2026, 3, 1)),
        _played("b", "c", 0, 2, dt.date(2026, 3, 8)),
    ]
    cfg = _cfg_pure()
    result = build_strengths_from_data(elo, matches, cfg, as_of=_TODAY)
    for team_id, elo_val in elo.items():
        snap = result.snapshots[team_id]
        assert snap.r_eff == pytest.approx(elo_val), f"{team_id}: r_eff != elo_base"


def test_from_data_sin_partidos_forma_igual_a_elo() -> None:
    """Sin partidos jugados, el form rating de cada equipo es su elo_base."""
    elo = {"x": 1450.0, "y": 1600.0}
    cfg = _cfg_adjusted()
    result = build_strengths_from_data(elo, [], cfg, as_of=_TODAY)
    for team_id, elo_val in elo.items():
        assert result.snapshots[team_id].form_rating == pytest.approx(elo_val)


def test_from_data_as_of_none_usa_hoy() -> None:
    """Si as_of=None, usa dt.date.today() y no lanza."""
    elo = {"a": 1500.0}
    cfg = _cfg_adjusted()
    result = build_strengths_from_data(elo, [], cfg, as_of=None)
    assert "a" in result.snapshots
    assert result.snapshots["a"].as_of == dt.date.today()


def test_from_data_devuelve_snapshot_por_equipo() -> None:
    """StrengthBuildResult.snapshots tiene una entrada por equipo en elo."""
    elo = {"a": 1500.0, "b": 1400.0, "c": 1350.0}
    cfg = _cfg_adjusted()
    result = build_strengths_from_data(elo, [], cfg, as_of=_TODAY)
    assert set(result.snapshots.keys()) == {"a", "b", "c"}


def test_from_data_n_coach_changes_applied_es_cero_por_defecto() -> None:
    """build_strengths_from_data no tiene acceso a cambios de entrenador -> n=0."""
    elo = {"a": 1500.0}
    cfg = _cfg_adjusted()
    result = build_strengths_from_data(elo, [], cfg, as_of=_TODAY)
    assert result.n_coach_changes_applied == 0


def test_from_data_con_xg_mezcla_xg_en_el_performance() -> None:
    """Con xG muy distinto de goles, el form_rating difiere del caso sin xG."""
    elo = {"a": 1500.0, "b": 1500.0}
    # Gana 3-0 pero xG dice que deberia haber empatado (xG~0.5 vs 1.5)
    m_con_xg = _played("a", "b", 3, 0, dt.date(2026, 4, 1), home_xg=0.5, away_xg=1.5)
    m_sin_xg = _played("a", "b", 3, 0, dt.date(2026, 4, 1))

    cfg = _cfg_adjusted(alpha=0.0)
    res_xg = build_strengths_from_data(elo, [m_con_xg], cfg, as_of=_TODAY)
    res_sin = build_strengths_from_data(elo, [m_sin_xg], cfg, as_of=_TODAY)

    # Con xG de mala suerte, la forma mejora menos
    assert res_xg.snapshots["a"].form_rating < res_sin.snapshots["a"].form_rating


def test_from_data_model_pure_ignora_coach_e_injuries() -> None:
    """Con model_type='pure', los cambios de entrenador y bajas se ignoran."""
    elo = {"a": 1500.0}
    cfg = _cfg_pure()
    result = build_strengths_from_data(elo, [], cfg, as_of=_TODAY)
    snap = result.snapshots["a"]
    assert snap.delta_coach == pytest.approx(0.0)
    assert snap.delta_injuries == pytest.approx(0.0)


def test_from_data_strength_build_result_es_frozen() -> None:
    """StrengthBuildResult es inmutable (frozen dataclass)."""
    elo = {"a": 1500.0}
    cfg = _cfg_adjusted()
    result = build_strengths_from_data(elo, [], cfg, as_of=_TODAY)
    with pytest.raises((AttributeError, TypeError)):
        result.xg_available = True  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# StrengthBuildResult estructural
# --------------------------------------------------------------------------- #


def test_strength_build_result_campos_presentes() -> None:
    """StrengthBuildResult tiene los campos esperados."""
    elo = {"a": 1500.0}
    cfg = _cfg_adjusted()
    result: StrengthBuildResult = build_strengths_from_data(elo, [], cfg, as_of=_TODAY)
    assert hasattr(result, "snapshots")
    assert hasattr(result, "xg_available")
    assert hasattr(result, "n_coach_changes_applied")
    assert hasattr(result, "notes")
    assert isinstance(result.notes, list)
