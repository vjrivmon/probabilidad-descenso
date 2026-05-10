"""Fuente de xG/xGA por partido: Understat (https://understat.com/league/La_liga/<year>).

Understat embebe los datos como JSON dentro de un <script> (`JSON.parse('...')`).
El parser debe ser defensivo: si no encuentra ese bloque, error explícito.
"""

from __future__ import annotations

import httpx

from descenso.adapters.data.cache import ParquetCache
from descenso.domain.match import Match
from descenso.domain.team import Team

UNDERSTAT_BASE = "https://understat.com/league/La_liga"


class UnderstatError(RuntimeError):
    """Understat cambió el formato o no respondió como se esperaba."""


class UnderstatXgSource:
    def __init__(self, cache: ParquetCache, client: httpx.Client | None = None) -> None:
        self.cache = cache
        self.client = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def fetch_match_xg(self, season: int, teams: list[Team]) -> list[Match]:
        """Devuelve los partidos jugados de la temporada con xG/xGA. Cachea en parquet.

        Si Understat no tiene xG de algún equipo (p.ej. recién ascendido en una
        temporada antigua), ese equipo simplemente aparece con menos partidos;
        el `StrengthModel` degrada a solo-Elo para él.
        """
        raise NotImplementedError  # Fase 7 (CP2)
