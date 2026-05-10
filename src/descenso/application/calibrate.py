"""Caso de uso: autocalibración de los parámetros del modelo ajustado.

Busca los `alpha`, `form_half_life_days` y `form_k_factor` que minimizan el Brier
medio del modelo ajustado en el backtest histórico, con `scipy.optimize.minimize`
(Nelder-Mead con bounds) y una **seed fija** para que el objetivo sea determinista
(si no, la varianza Monte Carlo lo haría saltar y el optimizador no convergería).

El estado as-of de cada temporada se prepara UNA sola vez (`prepare_seasons`) y se
reutiliza en cada evaluación del objetivo — cada evaluación es solo
`compute_strengths` + `run_monte_carlo` por temporada. Para que Nelder-Mead no
sufra con escalas tan distintas (alpha ∈ [0,1] vs half_life ∈ [15,200]), se
optimiza en coordenadas normalizadas a [0, 1].

Advertencia honesta: con tan pocas temporadas completas en openfootball (2-3) el
óptimo del backtest corre riesgo de sobreajuste; trátalo como un punto de partida,
no como la verdad. La calibración **no** escribe `config.yaml` por ti.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize

from descenso.application.backtest import (
    BACKTEST_SEED,
    PreparedSeason,
    adjusted_model_cfg,
    brier_logloss,
    evaluate_season,
    prepare_seasons,
    pure_model_cfg,
)
from descenso.config import AppConfig, ModelConfig

logger = logging.getLogger(__name__)

# Parámetros que se calibran y sus cotas.
_PARAM_ORDER: tuple[str, ...] = ("alpha", "form_half_life_days", "form_k_factor")
_PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "alpha": (0.0, 1.0),
    "form_half_life_days": (15.0, 200.0),
    "form_k_factor": (0.0, 120.0),
}


@dataclass(frozen=True)
class CalibrationResult:
    """Resultado de `calibrate`: parámetros óptimos y métricas antes/después."""

    seasons: list[int]
    horizon_gameweeks: int
    n_sims: int
    n_evaluations: int
    converged: bool
    initial_params: dict[str, float]
    best_params: dict[str, float]
    # Brier / log-loss medios sobre todos los (temporada, equipo)
    brier_pure: float  # baseline fija: alpha = 1.0, sin deltas
    brier_initial: float  # modelo ajustado con los params de config
    brier_best: float  # modelo ajustado con los params calibrados
    logloss_pure: float
    logloss_initial: float
    logloss_best: float

    @property
    def improvement_over_initial(self) -> float:
        if self.brier_initial == 0:
            return 0.0
        return (self.brier_initial - self.brier_best) / self.brier_initial

    @property
    def improvement_over_pure(self) -> float:
        if self.brier_pure == 0:
            return 0.0
        return (self.brier_pure - self.brier_best) / self.brier_pure


def _mean_metrics(
    prepared: list[PreparedSeason],
    model_cfg: ModelConfig,
    n_sims: int,
    seed: int,
) -> tuple[float, float]:
    """(Brier medio, log-loss medio) del modelo `model_cfg` sobre las temporadas dadas."""
    briers: list[float] = []
    loglosses: list[float] = []
    for ps in prepared:
        b, ll = brier_logloss(evaluate_season(ps, model_cfg, n_sims, seed), ps)
        briers.extend(b)
        loglosses.extend(ll)
    if not briers:
        return 0.0, 0.0
    return sum(briers) / len(briers), sum(loglosses) / len(loglosses)


def calibrate(
    seasons: list[int],
    config: AppConfig,
    horizon_gameweeks: int = 8,
    n_sims: int = 10_000,
    max_iter: int = 80,
    prepared: list[PreparedSeason] | None = None,
) -> CalibrationResult:
    """Autocalibra (alpha, form_half_life_days, form_k_factor) minimizando el Brier del backtest.

    Si `prepared` se pasa, se reutiliza (no hay descargas); si no, se construye con
    `prepare_seasons`. `n_sims` controla la suavidad del objetivo (más sims → menos
    "escalones" de tamaño 1/n_sims, pero más lento). `max_iter` es el tope de
    iteraciones de Nelder-Mead.
    """
    if prepared is None:
        prepared = prepare_seasons(seasons, config, horizon_gameweeks)
    if not prepared:
        raise ValueError(
            f"ninguna de las temporadas {seasons} está completa en openfootball "
            f"(¿has corrido `descenso data refresh`?)"
        )
    seed = BACKTEST_SEED

    brier_pure, logloss_pure = _mean_metrics(prepared, pure_model_cfg(config), n_sims, seed)
    initial_params = {k: float(getattr(config.model, k)) for k in _PARAM_ORDER}
    brier_initial, logloss_initial = _mean_metrics(
        prepared, adjusted_model_cfg(config), n_sims, seed
    )

    los = np.array([_PARAM_BOUNDS[k][0] for k in _PARAM_ORDER], dtype=float)
    his = np.array([_PARAM_BOUNDS[k][1] for k in _PARAM_ORDER], dtype=float)
    span = his - los

    def to_params(u: np.ndarray) -> dict[str, float]:
        v = los + np.clip(u, 0.0, 1.0) * span
        return {k: float(v[i]) for i, k in enumerate(_PARAM_ORDER)}

    n_eval = 0

    def objective(u: np.ndarray) -> float:
        nonlocal n_eval
        n_eval += 1
        cfg = adjusted_model_cfg(config, **to_params(u))
        brier, _ = _mean_metrics(prepared, cfg, n_sims, seed)
        return brier

    u0 = np.clip(
        (np.array([initial_params[k] for k in _PARAM_ORDER], dtype=float) - los) / span,
        0.0,
        1.0,
    )
    res = minimize(
        objective,
        u0,
        method="Nelder-Mead",
        bounds=[(0.0, 1.0)] * len(_PARAM_ORDER),
        options={"maxiter": max_iter, "xatol": 1e-3, "fatol": 1e-6, "adaptive": True},
    )
    best_params = to_params(np.asarray(res.x, dtype=float))
    brier_best, logloss_best = _mean_metrics(
        prepared, adjusted_model_cfg(config, **best_params), n_sims, seed
    )

    # Si la calibración no mejora respecto al config actual, devolvemos los params de
    # config (no tiene sentido sugerir algo peor por ruido del optimizador).
    if brier_best >= brier_initial:
        logger.info(
            "la calibración no mejora el Brier de config (%.5f >= %.5f); devuelvo los de config",
            brier_best,
            brier_initial,
        )
        best_params = dict(initial_params)
        brier_best, logloss_best = brier_initial, logloss_initial

    return CalibrationResult(
        seasons=[ps.season for ps in prepared],
        horizon_gameweeks=horizon_gameweeks,
        n_sims=n_sims,
        n_evaluations=n_eval,
        converged=bool(res.success),
        initial_params=initial_params,
        best_params=best_params,
        brier_pure=brier_pure,
        brier_initial=brier_initial,
        brier_best=brier_best,
        logloss_pure=logloss_pure,
        logloss_initial=logloss_initial,
        logloss_best=logloss_best,
    )


def suggest_config_yaml(result: CalibrationResult) -> str:
    """Fragmento YAML con los parámetros calibrados, listo para pegar en `config.yaml`."""
    p = result.best_params
    return (
        "model:\n"
        f"  alpha: {p['alpha']:.3f}\n"
        f"  form_half_life_days: {p['form_half_life_days']:.1f}\n"
        f"  form_k_factor: {p['form_k_factor']:.1f}\n"
    )
