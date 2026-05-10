"""Caso de uso: correr una simulación Monte Carlo del calendario restante."""

from __future__ import annotations

from descenso.config import AppConfig
from descenso.domain.probabilities import RelegationProbabilities


def run_simulation(
    config: AppConfig,
    fixed_results: list[tuple[str, int, str, int]] | None = None,
    n_sims: int | None = None,
    seed: int | None = None,
) -> RelegationProbabilities:
    """Carga datos, calcula fuerzas, simula y devuelve P(descenso) por equipo.

    `fixed_results`: lista de (equipo_local, goles_local, equipo_visitante, goles_visitante)
    que se respetan tal cual en todas las iteraciones.
    """
    raise NotImplementedError  # Fase 8
