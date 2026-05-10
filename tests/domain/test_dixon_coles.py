"""Tests del modelo de partido Poisson bivariada + Dixon-Coles (CP3) y del factory."""

from __future__ import annotations

import numpy as np

from descenso.config import ModelConfig
from descenso.domain.match_model import (
    BivariatePoissonDixonColesModel,
    EloLogisticMatchModel,
    make_match_model,
)


def _model(rho: float = -0.1) -> BivariatePoissonDixonColesModel:
    return BivariatePoissonDixonColesModel(
        home_advantage_elo=65.0, goals_avg=1.35, elo_to_goals_scale=400.0, rho=rho
    )


# --------------------------------------------------------------------------- #
# factory
# --------------------------------------------------------------------------- #


def test_make_match_model_default_es_elo_logistic() -> None:
    mm = make_match_model(ModelConfig())
    assert isinstance(mm, EloLogisticMatchModel)


def test_make_match_model_dixon_coles() -> None:
    cfg = ModelConfig(match_model="dixon_coles", goals_avg=1.4, dixon_coles_rho=-0.05)
    mm = make_match_model(cfg)
    assert isinstance(mm, BivariatePoissonDixonColesModel)
    assert mm.goals_avg == 1.4
    assert mm.rho == -0.05


# --------------------------------------------------------------------------- #
# lambdas (goles esperados)
# --------------------------------------------------------------------------- #


def test_lambdas_equipos_iguales_solo_difieren_por_la_localia() -> None:
    mm = _model()
    lam_h, lam_a = mm._lambdas(np.array([1500.0]), np.array([1500.0]))
    # el local tiene la ventaja de campo -> espera más goles
    assert lam_h[0] > lam_a[0]
    # producto ~ goals_avg^2 (la localía multiplica por e^(+h/2g) y e^(-h/2g))
    np.testing.assert_allclose(lam_h[0] * lam_a[0], 1.35**2, rtol=1e-9)


def test_lambdas_local_mas_fuerte_espera_mas_goles() -> None:
    mm = _model()
    lam_h, lam_a = mm._lambdas(np.array([1800.0]), np.array([1400.0]))
    assert lam_h[0] > 1.35 > lam_a[0]


def test_lambdas_diferencia_de_elo_acotada() -> None:
    """Una diferencia de Elo absurda no desborda la exponencial."""
    mm = _model()
    lam_h, lam_a = mm._lambdas(np.array([99_999.0]), np.array([0.0]))
    assert np.isfinite(lam_h[0]) and np.isfinite(lam_a[0])
    assert lam_a[0] > 0.0


# --------------------------------------------------------------------------- #
# sample_scores
# --------------------------------------------------------------------------- #


def test_sample_scores_shapes_dtypes_y_no_negativos() -> None:
    mm = _model()
    rng = np.random.default_rng(0)
    n = 40_000
    hg, ag = mm.sample_scores(np.full(n, 1600.0), np.full(n, 1500.0), rng)
    assert hg.shape == (n,) and ag.shape == (n,)
    assert hg.dtype == np.int64 and ag.dtype == np.int64
    assert np.all(hg >= 0) and np.all(ag >= 0)


def test_sample_scores_media_aproxima_lambdas() -> None:
    mm = _model(rho=0.0)  # rho=0 -> Poisson independiente exacta
    rng = np.random.default_rng(1)
    n = 200_000
    hs, as_ = np.full(n, 1700.0), np.full(n, 1450.0)
    lam_h, lam_a = mm._lambdas(hs, as_)
    hg, ag = mm.sample_scores(hs, as_, rng)
    np.testing.assert_allclose(hg.mean(), lam_h[0], rtol=0.03)
    np.testing.assert_allclose(ag.mean(), lam_a[0], rtol=0.03)


def test_sample_scores_local_fuerte_gana_mas() -> None:
    mm = _model()
    rng = np.random.default_rng(2)
    n = 60_000
    hg, ag = mm.sample_scores(np.full(n, 1750.0), np.full(n, 1450.0), rng)
    assert (hg > ag).mean() > (ag > hg).mean()
    assert (hg > ag).mean() > 0.5


def test_sample_scores_reproducible_con_misma_seed() -> None:
    mm = _model()
    hs, as_ = np.full(3000, 1550.0), np.full(3000, 1500.0)
    a_h, a_a = mm.sample_scores(hs, as_, np.random.default_rng(9))
    b_h, b_a = mm.sample_scores(hs, as_, np.random.default_rng(9))
    assert np.array_equal(a_h, b_h) and np.array_equal(a_a, b_a)


def test_sample_scores_rho_negativo_sube_los_empates_a_cero() -> None:
    """Con rho < 0 (como en LaLiga) hay más 0-0 que con Poisson independiente."""
    rng_a = np.random.default_rng(3)
    rng_b = np.random.default_rng(3)
    n = 150_000
    hs, as_ = np.full(n, 1500.0), np.full(n, 1500.0)
    indep = _model(rho=0.0).sample_scores(hs, as_, rng_a)
    dc = _model(rho=-0.18).sample_scores(hs, as_, rng_b)
    p00_indep = ((indep[0] == 0) & (indep[1] == 0)).mean()
    p00_dc = ((dc[0] == 0) & (dc[1] == 0)).mean()
    assert p00_dc > p00_indep


def test_sample_scores_acepta_arrays_heterogeneos() -> None:
    mm = _model()
    rng = np.random.default_rng(4)
    hs = np.array([1500.0, 1800.0, 1400.0, 1600.0])
    as_ = np.array([1500.0, 1400.0, 1800.0, 1550.0])
    hg, ag = mm.sample_scores(hs, as_, rng)
    assert hg.shape == (4,) and ag.shape == (4,)


def test_sample_scores_escalar_devuelve_escalar() -> None:
    mm = _model()
    rng = np.random.default_rng(5)
    hg, ag = mm.sample_scores(np.array(1600.0), np.array(1500.0), rng)
    assert int(hg) >= 0 and int(ag) >= 0


# --------------------------------------------------------------------------- #
# outcome_probabilities
# --------------------------------------------------------------------------- #


def test_outcome_probabilities_es_una_distribucion() -> None:
    mm = _model()
    home = np.array([1500.0, 1800.0, 1400.0])
    away = np.array([1500.0, 1400.0, 1800.0])
    p_h, p_d, p_a = mm.outcome_probabilities(home, away)
    np.testing.assert_allclose(p_h + p_d + p_a, 1.0, rtol=1e-9)
    assert np.all(p_h > 0.0) and np.all(p_d > 0.0) and np.all(p_a > 0.0)


def test_outcome_probabilities_local_mas_fuerte_es_favorito() -> None:
    mm = _model()
    p_h, _, p_a = mm.outcome_probabilities(np.array([1850.0]), np.array([1400.0]))
    assert p_h[0] > p_a[0]
    # mismo equipo en casa también favorito
    p_h_eq, _, p_a_eq = mm.outcome_probabilities(np.array([1500.0]), np.array([1500.0]))
    assert p_h_eq[0] > p_a_eq[0]


def test_outcome_probabilities_coincide_con_la_simulacion() -> None:
    """La P(victoria local) analítica debe estar cerca de la frecuencia muestreada."""
    mm = _model()
    p_h, p_d, p_a = mm.outcome_probabilities(np.array([1650.0]), np.array([1500.0]))
    rng = np.random.default_rng(11)
    n = 200_000
    hg, ag = mm.sample_scores(np.full(n, 1650.0), np.full(n, 1500.0), rng)
    np.testing.assert_allclose((hg > ag).mean(), p_h[0], atol=0.01)
    np.testing.assert_allclose((hg == ag).mean(), p_d[0], atol=0.01)
    np.testing.assert_allclose((hg < ag).mean(), p_a[0], atol=0.01)


def test_outcome_probabilities_rho_cero_es_poisson_independiente() -> None:
    from scipy import stats

    mm = _model(rho=0.0)
    lam_h, lam_a = mm._lambdas(np.array([1550.0]), np.array([1500.0]))
    _, p_d, _ = mm.outcome_probabilities(np.array([1550.0]), np.array([1500.0]))
    # P(empate) = sum_k Poisson(k; lam_h) * Poisson(k; lam_a)
    k = np.arange(0, 30)
    p_draw_ref = float((stats.poisson.pmf(k, lam_h[0]) * stats.poisson.pmf(k, lam_a[0])).sum())
    np.testing.assert_allclose(p_d[0], p_draw_ref, rtol=1e-3)
