"""Fuente de ratings Elo: clubelo.com (API CSV pública, http://clubelo.com/API)."""

from __future__ import annotations

import datetime as dt

import httpx

from descenso.adapters.data.cache import ParquetCache
from descenso.domain.team import Team

CLUBELO_BASE = "http://api.clubelo.com"


class ClubeloError(RuntimeError):
    """clubelo.com no respondió como se esperaba (caído, formato cambiado, ...)."""


class ClubeloEloSource:
    def __init__(self, cache: ParquetCache, client: httpx.Client | None = None) -> None:
        self.cache = cache
        self.client = client or httpx.Client(timeout=20.0, follow_redirects=True)

    def fetch_current_elo(
        self, teams: list[Team], on_date: dt.date | None = None
    ) -> dict[str, float]:
        """Devuelve {team.id: elo} para `on_date` (hoy por defecto). Cachea el CSV crudo.

        Si clubelo está caído usa el cache previo avisando de la fecha; si no hay
        cache, levanta ClubeloError con la URL y el código HTTP.
        """
        raise NotImplementedError  # Fase 7
