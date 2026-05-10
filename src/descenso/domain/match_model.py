"""Modelo de un partido: de fuerzas a probabilidades / marcadores muestreados.

Hay dos implementaciones del puerto `MatchModel`:

- `EloLogisticMatchModel` (CP1, default): W/D/L por una logística de Elo + localía,
  con el margen de goles muestreado de distribuciones calibradas a ojo.
- `BivariatePoissonDixonColesModel` (CP3): los goles esperados de cada equipo salen
  de su fuerza efectiva (escala Elo) -- lam_local = mu*exp(+d/(2*gamma)),
  lam_visitante = mu*exp(-d/(2*gamma)) con d = R_local + ventaja - R_visitante -- y
  los marcadores de dos Poisson independientes con la corrección de Dixon-Coles tau
  sobre los cuatro marcadores bajos. Da marcadores más realistas (mejor fidelidad al
  desempate por diferencia de goles).

`make_match_model(model_config)` devuelve el adecuado según `model_config.match_model`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from descenso.config import ModelConfig

# Distribuciones de marcador "calibradas a ojo" sobre datos típicos de LaLiga.
# Son parámetros del CP1 (modelo "puro"); en CP3 se sustituyen por Poisson+Dixon-Coles.
# Condicionadas al tipo de resultado y normalizadas a 1.
_DRAW_GOALS = np.array([0, 1, 2, 3])  # 0-0, 1-1, 2-2, 3-3
_DRAW_GOALS_P = np.array([0.35, 0.46, 0.15, 0.04])
_WIN_MARGIN = np.array([1, 2, 3, 4])
_WIN_MARGIN_P = np.array([0.55, 0.28, 0.12, 0.05])
_LOSER_GOALS = np.array([0, 1, 2, 3])
_LOSER_GOALS_P = np.array([0.50, 0.38, 0.10, 0.02])

# Dixon-Coles: pasadas máximas del rejection sampling de la corrección tau. Con
# |rho| <= 0.2 (validado en config) y goles esperados realistas (~1-2) la aceptación
# por pasada ronda el 80-95 %, así que 16 pasadas dejan un sesgo residual < 1e-5.
_DC_MAX_PASSES = 16
# Cota superior de goles para sumar el pmf conjunto en `outcome_probabilities` del
# modelo Dixon-Coles (P(>15 goles de un equipo) es ~0 para λ realistas).
_DC_GRID_MAX_GOALS = 15


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


def make_match_model(model_config: ModelConfig) -> MatchModel:
    """Devuelve el `MatchModel` indicado por `model_config.match_model`."""
    if model_config.match_model == "dixon_coles":
        return BivariatePoissonDixonColesModel(
            home_advantage_elo=model_config.home_advantage_elo,
            goals_avg=model_config.goals_avg,
            elo_to_goals_scale=model_config.elo_to_goals_scale,
            rho=model_config.dixon_coles_rho,
        )
    return EloLogisticMatchModel(
        home_advantage_elo=model_config.home_advantage_elo,
        draw_base=model_config.draw_base,
    )


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
    """CP3: goles esperados derivados de la fuerza efectiva (escala Elo) + dos Poisson
    independientes con la corrección de Dixon-Coles para los marcadores bajos.

        d         = R_local + ventaja_local - R_visitante
        lam_local = mu * exp(+d / (2*gamma))     lam_visit = mu * exp(-d / (2*gamma))
        P(x, y) ~ tau(x, y) * Poisson(x; lam_local) * Poisson(y; lam_visit)
        tau(0,0) = 1 - lam_local*lam_visit*rho,  tau(0,1) = 1 + lam_local*rho
        tau(1,0) = 1 + lam_visit*rho,  tau(1,1) = 1 - rho,  resto = 1

    `mu = goals_avg`, `gamma = elo_to_goals_scale`, `rho = dixon_coles_rho`. La diferencia
    de Elo se acota a +-1000 para no desbordar la exponencial con valores absurdos.
    """

    def __init__(
        self,
        home_advantage_elo: float,
        goals_avg: float,
        elo_to_goals_scale: float,
        rho: float,
    ) -> None:
        self.home_advantage_elo = home_advantage_elo
        self.goals_avg = goals_avg
        self.elo_to_goals_scale = elo_to_goals_scale
        self.rho = rho

    def _lambdas(self, hs: np.ndarray, as_: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        diff = np.clip(hs + self.home_advantage_elo - as_, -1000.0, 1000.0)
        half = diff / (2.0 * self.elo_to_goals_scale)
        lam_home = self.goals_avg * np.exp(half)
        lam_away = self.goals_avg * np.exp(-half)
        return lam_home, lam_away

    @staticmethod
    def _tau(
        x: np.ndarray, y: np.ndarray, lam_h: np.ndarray, lam_a: np.ndarray, rho: float
    ) -> np.ndarray:
        """τ_{λ,μ}(x, y) de Dixon-Coles: 1 salvo en los cuatro marcadores bajos."""
        tau = np.ones(np.broadcast_shapes(x.shape, y.shape, lam_h.shape, lam_a.shape), dtype=float)
        m00 = (x == 0) & (y == 0)
        m01 = (x == 0) & (y == 1)
        m10 = (x == 1) & (y == 0)
        m11 = (x == 1) & (y == 1)
        tau = np.where(m00, 1.0 - lam_h * lam_a * rho, tau)
        tau = np.where(m01, 1.0 + lam_h * rho, tau)
        tau = np.where(m10, 1.0 + lam_a * rho, tau)
        tau = np.where(m11, 1.0 - rho, tau)
        return np.clip(tau, 0.0, None)

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
        lam_h, lam_a = self._lambdas(hs, as_)

        # `np.asarray` para que un escalar de entrada (Poisson devuelve int de Python)
        # siga siendo un array y `_tau` pueda trabajar con `.shape`.
        home = np.asarray(rng.poisson(lam_h))
        away = np.asarray(rng.poisson(lam_a))
        if self.rho == 0.0:
            return home.astype(np.int64), away.astype(np.int64)

        # Rejection sampling: la propuesta es Poisson*Poisson, el objetivo tau*propuesta.
        # Se acepta cada muestra con probabilidad tau(x,y)/C, C = cota superior de tau por
        # elemento. Los rechazados se vuelven a muestrear (de la propuesta) hasta
        # `_DC_MAX_PASSES`; los que queden se aceptan tal cual (sesgo residual ínfimo).
        rho = self.rho
        c = np.maximum.reduce(
            [
                np.ones(shape, dtype=float),
                1.0 - lam_h * lam_a * rho,
                1.0 + lam_h * rho,
                1.0 + lam_a * rho,
                np.full(shape, 1.0 - rho, dtype=float),
            ]
        )
        done = np.zeros(shape, dtype=bool)
        for _ in range(_DC_MAX_PASSES):
            tau = self._tau(home, away, lam_h, lam_a, rho)
            newly = (~done) & (rng.random(shape) * c < tau)
            done |= newly
            if bool(done.all()):
                break
            resample = ~done
            home = np.where(resample, rng.poisson(lam_h), home)
            away = np.where(resample, rng.poisson(lam_a), away)
        return home.astype(np.int64), away.astype(np.int64)

    def outcome_probabilities(
        self, home_strength: np.ndarray, away_strength: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(P(gana local), P(empate), P(gana visitante)) sumando el pmf conjunto.

        Pensado para análisis y tests con arrays pequeños: construye una rejilla
        (..., G+1, G+1) con G = `_DC_GRID_MAX_GOALS`.
        """
        from scipy import stats  # import perezoso: solo lo necesita esta rama

        hs = np.asarray(home_strength, dtype=float)
        as_ = np.asarray(away_strength, dtype=float)
        shape = np.broadcast_shapes(hs.shape, as_.shape)
        hs = np.broadcast_to(hs, shape).astype(float)
        as_ = np.broadcast_to(as_, shape).astype(float)
        lam_h, lam_a = self._lambdas(hs, as_)

        goals = np.arange(_DC_GRID_MAX_GOALS + 1)
        # pmf marginales: (..., G+1)
        pmf_h = stats.poisson.pmf(goals, lam_h[..., None])
        pmf_a = stats.poisson.pmf(goals, lam_a[..., None])
        joint = pmf_h[..., :, None] * pmf_a[..., None, :]  # (..., G+1, G+1)

        gx = goals[:, None]
        gy = goals[None, :]
        lam_h_b = lam_h[..., None, None]
        lam_a_b = lam_a[..., None, None]
        tau = self._tau(
            np.broadcast_to(gx, joint.shape),
            np.broadcast_to(gy, joint.shape),
            np.broadcast_to(lam_h_b, joint.shape),
            np.broadcast_to(lam_a_b, joint.shape),
            self.rho,
        )
        joint = joint * tau
        total = joint.sum(axis=(-2, -1), keepdims=True)
        joint = joint / np.clip(total, 1e-300, None)

        upper = np.triu(np.ones((_DC_GRID_MAX_GOALS + 1, _DC_GRID_MAX_GOALS + 1)), k=1)  # x < y
        lower = np.tril(np.ones((_DC_GRID_MAX_GOALS + 1, _DC_GRID_MAX_GOALS + 1)), k=-1)  # x > y
        diag = np.eye(_DC_GRID_MAX_GOALS + 1)
        p_home = (joint * lower).sum(axis=(-2, -1))
        p_draw = (joint * diag).sum(axis=(-2, -1))
        p_away = (joint * upper).sum(axis=(-2, -1))
        return p_home, p_draw, p_away
