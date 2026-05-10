"""Tests de la autocalibración (CP3) — con temporadas preparadas sintéticas (sin red)."""

from __future__ import annotations

import datetime as dt

import pytest

from descenso.application.backtest import PreparedSeason, adjusted_model_cfg
from descenso.application.calibrate import (
    CalibrationResult,
    _mean_metrics,
    calibrate,
    suggest_config_yaml,
)
from descenso.config import AppConfig, ModelConfig
from descenso.domain.match import Match
from descenso.domain.standings import build_table
from descenso.domain.team import Team

# Liga sintética de 6 equipos; los 3 con menos Elo (d, e, f) "descendieron".
_TEAM_IDS = ["a", "b", "c", "d", "e", "f"]
_ELO = {"a": 1700.0, "b": 1640.0, "c": 1600.0, "d": 1480.0, "e": 1430.0, "f": 1380.0}
_CUTOFF = dt.date(2099, 4, 1)


def _team(tid: str) -> Team:
    return Team(
        id=tid,
        name=tid.upper(),
        clubelo_name=None,
        understat_name=None,
        fbref_name=None,
        openfootball_name=tid.upper(),
    )


def _played() -> list[Match]:
    """Unos cuantos partidos jugados antes del corte (round-robin parcial)."""
    out: list[Match] = []
    gw = 1
    day = dt.date(2098, 9, 1)
    for i, h in enumerate(_TEAM_IDS):
        for a in _TEAM_IDS[i + 1 :]:
            # los equipos fuertes ganan más a menudo (sin ser determinista)
            hg, ag = (2, 0) if _ELO[h] >= _ELO[a] else (0, 1)
            out.append(
                Match(
                    season=2099,
                    gameweek=gw,
                    date=day,
                    home_team=h,
                    away_team=a,
                    home_goals=hg,
                    away_goals=ag,
                )
            )
            gw += 1
            day += dt.timedelta(days=7)
    return out


def _pending() -> list[Match]:
    """Partidos por simular (la vuelta, sin marcador)."""
    out: list[Match] = []
    gw = 100
    for i, h in enumerate(_TEAM_IDS):
        for a in _TEAM_IDS[i + 1 :]:
            out.append(Match(season=2099, gameweek=gw, home_team=a, away_team=h))
            gw += 1
    return out


def _prepared_season() -> PreparedSeason:
    played = _played()
    return PreparedSeason(
        season=2099,
        teams=[_team(t) for t in _TEAM_IDS],
        team_ids=list(_TEAM_IDS),
        base_table=build_table(_TEAM_IDS, played),
        played_asof=played,
        pending_asof=_pending(),
        elo=dict(_ELO),
        cutoff_date=_CUTOFF,
        cutoff_gameweek=30,
        relegated_real=frozenset({"d", "e", "f"}),
    )


def _config(alpha: float = 0.5) -> AppConfig:
    return AppConfig(model=ModelConfig(alpha=alpha, model_type="adjusted"))


# --------------------------------------------------------------------------- #
# _mean_metrics
# --------------------------------------------------------------------------- #


def test_mean_metrics_devuelve_dos_floats_en_rango() -> None:
    ps = _prepared_season()
    cfg = _config()
    brier, logloss = _mean_metrics([ps], adjusted_model_cfg(cfg), n_sims=400, seed=42)
    assert 0.0 <= brier <= 1.0
    assert logloss >= 0.0


def test_mean_metrics_lista_vacia_devuelve_ceros() -> None:
    brier, logloss = _mean_metrics([], adjusted_model_cfg(_config()), n_sims=100, seed=1)
    assert brier == 0.0 and logloss == 0.0


# --------------------------------------------------------------------------- #
# calibrate
# --------------------------------------------------------------------------- #


def test_calibrate_devuelve_resultado_coherente() -> None:
    ps = _prepared_season()
    result = calibrate(
        seasons=[2099],
        config=_config(),
        n_sims=600,
        max_iter=5,
        prepared=[ps],
    )
    assert isinstance(result, CalibrationResult)
    assert result.seasons == [2099]
    assert result.n_evaluations > 0
    # los parámetros calibrados están dentro de las cotas
    assert 0.0 <= result.best_params["alpha"] <= 1.0
    assert 15.0 <= result.best_params["form_half_life_days"] <= 200.0
    assert 0.0 <= result.best_params["form_k_factor"] <= 120.0
    # el modelo calibrado nunca es PEOR que config (si lo fuera, se devuelven los de config)
    assert result.brier_best <= result.brier_initial + 1e-12


def test_calibrate_sin_temporadas_preparadas_levanta_value_error() -> None:
    with pytest.raises(ValueError, match="ninguna de las temporadas"):
        calibrate(seasons=[2099], config=_config(), prepared=[])


def test_calibrate_es_determinista() -> None:
    ps1 = _prepared_season()
    ps2 = _prepared_season()
    r1 = calibrate(seasons=[2099], config=_config(), n_sims=500, max_iter=4, prepared=[ps1])
    r2 = calibrate(seasons=[2099], config=_config(), n_sims=500, max_iter=4, prepared=[ps2])
    assert r1.best_params == r2.best_params
    assert r1.brier_best == pytest.approx(r2.brier_best)


# --------------------------------------------------------------------------- #
# CalibrationResult: propiedades
# --------------------------------------------------------------------------- #


def _result(brier_pure: float, brier_initial: float, brier_best: float) -> CalibrationResult:
    return CalibrationResult(
        seasons=[2099],
        horizon_gameweeks=8,
        n_sims=1000,
        n_evaluations=10,
        converged=True,
        initial_params={"alpha": 0.5, "form_half_life_days": 75.0, "form_k_factor": 40.0},
        best_params={"alpha": 0.4, "form_half_life_days": 60.0, "form_k_factor": 50.0},
        brier_pure=brier_pure,
        brier_initial=brier_initial,
        brier_best=brier_best,
        logloss_pure=0.2,
        logloss_initial=0.19,
        logloss_best=0.18,
    )


def test_improvement_over_initial() -> None:
    r = _result(brier_pure=0.10, brier_initial=0.08, brier_best=0.06)
    assert r.improvement_over_initial == pytest.approx((0.08 - 0.06) / 0.08)


def test_improvement_over_pure() -> None:
    r = _result(brier_pure=0.10, brier_initial=0.08, brier_best=0.06)
    assert r.improvement_over_pure == pytest.approx((0.10 - 0.06) / 0.10)


def test_improvement_cero_si_baseline_cero() -> None:
    r = _result(brier_pure=0.0, brier_initial=0.0, brier_best=0.0)
    assert r.improvement_over_initial == 0.0
    assert r.improvement_over_pure == 0.0


# --------------------------------------------------------------------------- #
# suggest_config_yaml
# --------------------------------------------------------------------------- #


def test_suggest_config_yaml_formato() -> None:
    r = _result(brier_pure=0.1, brier_initial=0.08, brier_best=0.06)
    yaml_text = suggest_config_yaml(r)
    assert yaml_text.startswith("model:\n")
    assert "alpha: 0.400" in yaml_text
    assert "form_half_life_days: 60.0" in yaml_text
    assert "form_k_factor: 50.0" in yaml_text
    # debe ser YAML válido y reconstruir esos valores
    import yaml as yaml_mod

    parsed = yaml_mod.safe_load(yaml_text)
    assert parsed["model"]["alpha"] == pytest.approx(0.4)
