"""Tests del modelo de partido Elo-logístico (CP1)."""

from __future__ import annotations

import numpy as np

from descenso.domain.match_model import EloLogisticMatchModel


def _model() -> EloLogisticMatchModel:
    return EloLogisticMatchModel(home_advantage_elo=65.0, draw_base=0.26)


def test_outcome_probabilities_are_a_distribution() -> None:
    mm = _model()
    home = np.array([1500.0, 1800.0, 1400.0])
    away = np.array([1500.0, 1400.0, 1800.0])
    p_home, p_draw, p_away = mm.outcome_probabilities(home, away)
    np.testing.assert_allclose(p_home + p_draw + p_away, 1.0)
    assert np.all(p_home > 0.0) and np.all(p_draw > 0.0) and np.all(p_away > 0.0)


def test_stronger_and_home_team_favoured() -> None:
    mm = _model()
    p_home, _, p_away = mm.outcome_probabilities(np.array([1800.0]), np.array([1400.0]))
    assert p_home[0] > p_away[0]
    # misma fuerza pero jugando en casa: el local es favorito
    p_home_eq, _, p_away_eq = mm.outcome_probabilities(np.array([1500.0]), np.array([1500.0]))
    assert p_home_eq[0] > p_away_eq[0]


def test_huge_favourite_rarely_loses() -> None:
    mm = _model()
    p_home, _, p_away = mm.outcome_probabilities(np.array([2000.0]), np.array([1300.0]))
    assert p_home[0] > 0.85
    assert p_away[0] < 0.05


def test_sample_scores_shapes_dtypes_and_bias() -> None:
    mm = _model()
    rng = np.random.default_rng(42)
    n = 30_000
    home_goals, away_goals = mm.sample_scores(np.full(n, 1650.0), np.full(n, 1500.0), rng)
    assert home_goals.shape == (n,) and away_goals.shape == (n,)
    assert home_goals.dtype.kind == "i" and away_goals.dtype.kind == "i"
    assert np.all(home_goals >= 0) and np.all(away_goals >= 0)
    assert home_goals.max() < 12 and away_goals.max() < 12
    # el equipo más fuerte y local gana más de lo que pierde
    assert (home_goals > away_goals).mean() > (away_goals > home_goals).mean()
    # los marcadores empatados generados son... empates
    drawn = home_goals == away_goals
    assert np.array_equal(home_goals[drawn], away_goals[drawn])


def test_sample_scores_is_reproducible_with_same_seed() -> None:
    mm = _model()
    home, away = np.full(2000, 1500.0), np.full(2000, 1480.0)
    a_h, a_a = mm.sample_scores(home, away, np.random.default_rng(7))
    b_h, b_a = mm.sample_scores(home, away, np.random.default_rng(7))
    assert np.array_equal(a_h, b_h) and np.array_equal(a_a, b_a)


def test_sample_categorical_size_cero_devuelve_array_vacio() -> None:
    """_sample_categorical con size=0 debe devolver un array vacío sin errores."""
    from descenso.domain.match_model import _sample_categorical

    rng = np.random.default_rng(1)
    vals = np.array([0, 1, 2])
    probs = np.array([0.3, 0.4, 0.3])
    result = _sample_categorical(vals, probs, 0, rng)
    assert result.shape == (0,)
    assert result.dtype == np.int64
