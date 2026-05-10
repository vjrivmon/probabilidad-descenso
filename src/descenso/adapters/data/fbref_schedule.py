"""Fuente del calendario de LaLiga (jugados + pendientes): FBref.

URL de referencia: https://fbref.com/en/comps/12/schedule/La-Liga-Scores-and-Fixtures
"""

from __future__ import annotations

import httpx

from descenso.adapters.data.cache import ParquetCache
from descenso.domain.match import Match
from descenso.domain.team import Team


class FbrefError(RuntimeError):
    """FBref no respondió como se esperaba (403/rate-limit, formato cambiado, ...)."""


class FbrefScheduleSource:
    def __init__(self, cache: ParquetCache, client: httpx.Client | None = None) -> None:
        self.cache = cache
        self.client = client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "descenso/0.1 (+https://github.com/vjrivmon/probabilidad-descenso)"
            },
        )

    def fetch_schedule(self, season: int, teams: list[Team]) -> list[Match]:
        """Devuelve todos los partidos de la temporada (jugados con resultado, pendientes sin él).

        Deduplica por (temporada, local, visitante). Si FBref devuelve 403, hace un
        reintento con backoff; si sigue fallando, levanta FbrefError y sugiere
        `data/fixtures_override.csv` como salida de emergencia.
        """
        raise NotImplementedError  # Fase 7
