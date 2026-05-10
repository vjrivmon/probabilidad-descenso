"""Modelo de un partido: de fuerzas a probabilidades / marcadores muestreados."""

from __future__ import annotations

from typing import Protocol

import numpy as np


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


class EloLogisticMatchModel:
    """MVP (CP1): W/D/L por Elo-logístico sobre la diferencia de fuerza + localía;
    el margen de goles se muestrea de una distribución calibrada para respetar
    los desempates por diferencia de goles."""

    def __init__(self, home_advantage_elo: float, draw_base: float) -> None:
        self.home_advantage_elo = home_advantage_elo
        self.draw_base = draw_base

    def sample_scores(
        self,
        home_strength: np.ndarray,
        away_strength: np.ndarray,
        rng: np.random.Generator,
    ) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError  # Fase 6


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
