"""Modelo de un partido: de fuerzas a probabilidades / marcadores muestreados."""

from __future__ import annotations

from typing import Protocol

import numpy as np

# Distribuciones de marcador "calibradas a ojo" sobre datos típicos de LaLiga.
# Son parámetros del CP1 (modelo "puro"); en CP3 se sustituyen por Poisson+Dixon-Coles.
# Condicionadas al tipo de resultado y normalizadas a 1.
_DRAW_GOALS = np.array([0, 1, 2, 3])  # 0-0, 1-1, 2-2, 3-3
_DRAW_GOALS_P = np.array([0.35, 0.46, 0.15, 0.04])
_WIN_MARGIN = np.array([1, 2, 3, 4])
_WIN_MARGIN_P = np.array([0.55, 0.28, 0.12, 0.05])
_LOSER_GOALS = np.array([0, 1, 2, 3])
_LOSER_GOALS_P = np.array([0.50, 0.38, 0.10, 0.02])


class MatchModel(Protocol):
    """Puerto: dado un par de equipos, sabe muestrear el resultado de un partido."""

    def sample_scores(
        self,
        home_strength: np.ndarray,
        away_strength: np.ndarray,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Muestrea (goles_local, goles_visitante) de forma vectorizada.

        Las entradas son arrays paralelos (un valor por partido a simular en una
        iteración, o por iteración para un partido). Devuelve arrays de enteros.
        """
        ...


def _sample_categorical(
    values: np.ndarray, probs: np.ndarray, size: int, rng: np.random.Generator
) -> np.ndarray:
    """Muestrea `size` valores de una categórica vía búsqueda en la CDF (vectorizado)."""
    if size == 0:
        return np.empty(0, dtype=np.int64)
    cdf = np.cumsum(probs)
    cdf = cdf / cdf[-1]
    idx = np.searchsorted(cdf, rng.random(size), side="right")
    idx = np.clip(idx, 0, len(values) - 1)
    return values[idx].astype(np.int64)


class EloLogisticMatchModel:
    """MVP (CP1): W/D/L por Elo-logístico sobre la diferencia de fuerza + localía;
    el margen de goles se muestrea de una distribución calibrada para respetar
    los desempates por diferencia de goles."""

    def __init__(self, home_advantage_elo: float, draw_base: float) -> None:
        self.home_advantage_elo = home_advantage_elo
        self.draw_base = draw_base

    def outcome_probabilities(
        self, home_strength: np.ndarray, away_strength: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(P(gana local), P(empate), P(gana visitante)) por partido, vectorizado.

        Punto de partida: la fórmula de Elo da el "rendimiento esperado"
        E = 1 / (1 + 10^(-Δ/400)) (cuenta victoria=1, empate=0.5). De ahí se
        reparte una probabilidad de empate que es máxima (`draw_base`) cuando los
        equipos son iguales y decae al alejarse Δ de 0.
        """
        hs = np.asarray(home_strength, dtype=float)
        as_ = np.asarray(away_strength, dtype=float)
        delta = hs + self.home_advantage_elo - as_
        expected = 1.0 / (1.0 + np.power(10.0, -delta / 400.0))
        p_draw = self.draw_base * (1.0 - np.abs(2.0 * expected - 1.0))
        p_home = expected - 0.5 * p_draw
        p_away = 1.0 - p_home - p_draw
        p_home = np.clip(p_home, 1e-9, None)
        p_draw = np.clip(p_draw, 1e-9, None)
        p_away = np.clip(p_away, 1e-9, None)
        total = p_home + p_draw + p_away
        return p_home / total, p_draw / total, p_away / total

    def sample_scores(
        self,
        home_strength: np.ndarray,
        away_strength: np.ndarray,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray]:
        hs = np.asarray(home_strength, dtype=float)
        as_ = np.asarray(away_strength, dtype=float)
        shape = np.broadcast_shapes(hs.shape, as_.shape)
        hs = np.broadcast_to(hs, shape)
        as_ = np.broadcast_to(as_, shape)
        p_home, p_draw, _ = self.outcome_probabilities(hs, as_)
        u = rng.random(hs.shape)
        # 0 = gana local, 1 = empate, 2 = gana visitante
        outcome = np.where(u < p_home, 0, np.where(u < p_home + p_draw, 1, 2))

        home_goals = np.empty(hs.shape, dtype=np.int64)
        away_goals = np.empty(hs.shape, dtype=np.int64)

        is_draw = outcome == 1
        n_draw = int(is_draw.sum())
        draw_scores = _sample_categorical(_DRAW_GOALS, _DRAW_GOALS_P, n_draw, rng)
        home_goals[is_draw] = draw_scores
        away_goals[is_draw] = draw_scores

        is_decisive = ~is_draw
        n_dec = int(is_decisive.sum())
        margin = _sample_categorical(_WIN_MARGIN, _WIN_MARGIN_P, n_dec, rng)
        loser = _sample_categorical(_LOSER_GOALS, _LOSER_GOALS_P, n_dec, rng)
        winner = loser + margin
        home_wins = outcome[is_decisive] == 0
        home_goals[is_decisive] = np.where(home_wins, winner, loser)
        away_goals[is_decisive] = np.where(home_wins, loser, winner)

        return home_goals, away_goals


class BivariatePoissonDixonColesModel:
    """v2 (CP3): fuerzas de ataque/defensa derivadas de R + xG histórico;
    marcadores de una Poisson bivariada con corrección de Dixon-Coles para
    marcadores bajos."""

    def __init__(self, home_advantage: float) -> None:
        self.home_advantage = home_advantage

    def sample_scores(
        self,
        home_strength: np.ndarray,
        away_strength: np.ndarray,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError  # Fase 12 (CP3)
