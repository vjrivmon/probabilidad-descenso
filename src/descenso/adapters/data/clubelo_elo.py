"""Fuente de ratings Elo: clubelo.com (API CSV pública, http://clubelo.com/API).

Se usa el endpoint de fecha (`http://api.clubelo.com/<YYYY-MM-DD>`), que devuelve
el Elo de todos los clubes a esa fecha en una sola petición CSV
(`Rank,Club,Country,Level,Elo,From,To`), en vez de una petición por equipo.
"""

from __future__ import annotations

import datetime as dt
import io
import logging

import httpx
import pandas as pd

from descenso.adapters.data.cache import ParquetCache
from descenso.domain.team import Team

logger = logging.getLogger(__name__)

CLUBELO_BASE = "http://api.clubelo.com"
CACHE_NAME = "clubelo_elo"
_REQUIRED_COLUMNS = {"Club", "Elo"}


class ClubeloError(RuntimeError):
    """clubelo.com no respondió como se esperaba (caído, formato cambiado, ...)."""


class ClubeloEloSource:
    def __init__(self, cache: ParquetCache, client: httpx.Client | None = None) -> None:
        self.cache = cache
        self.client = client or httpx.Client(timeout=20.0, follow_redirects=True)

    def fetch_current_elo(
        self,
        teams: list[Team],
        on_date: dt.date | None = None,
        prefer_cache: bool = False,
    ) -> dict[str, float]:
        """Devuelve `{team.id: elo}` para `on_date` (hoy por defecto).

        - `prefer_cache=True`: si hay cache, lo usa sin tocar la red (modo offline de
          `simulate`/`report`); solo va a la red si no hay cache.
        - `prefer_cache=False` (`data refresh`): pide a clubelo y reescribe el cache;
          si clubelo está caído pero hay cache previo, lo usa avisando de la fecha;
          si no hay cache, levanta `ClubeloError` con la URL y el detalle del fallo.
        """
        on_date = on_date or dt.date.today()

        if prefer_cache and self.cache.has(CACHE_NAME):
            df = self.cache.load(CACHE_NAME)
        else:
            url = f"{CLUBELO_BASE}/{on_date.isoformat()}"
            try:
                df = self._download(url)
                self.cache.save(CACHE_NAME, df)
            except ClubeloError:
                if not self.cache.has(CACHE_NAME):
                    raise
                logger.warning(
                    "no pude refrescar el Elo de clubelo (%s); uso el cache previo (%s)",
                    url,
                    self.cache.path(CACHE_NAME),
                )
                df = self.cache.load(CACHE_NAME)

        return self._extract(df, teams)

    def _download(self, url: str) -> pd.DataFrame:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ClubeloError(f"clubelo.com respondió {exc.response.status_code} a {url}") from exc
        except httpx.HTTPError as exc:
            raise ClubeloError(f"no pude contactar con clubelo.com ({url}): {exc}") from exc
        try:
            df = pd.read_csv(io.StringIO(resp.text))
        except (pd.errors.ParserError, ValueError) as exc:
            raise ClubeloError(
                f"clubelo.com devolvió algo que no es un CSV de Elo ({url}): {exc}"
            ) from exc
        missing = _REQUIRED_COLUMNS - set(df.columns)
        if missing or df.empty:
            raise ClubeloError(
                f"el CSV de clubelo.com ({url}) no tiene el formato esperado "
                f"(faltan columnas {sorted(missing)} o está vacío); abre un issue"
            )
        keep = [c for c in ("Club", "Elo", "From", "To") if c in df.columns]
        return df.loc[:, keep].copy()

    @staticmethod
    def _extract(df: pd.DataFrame, teams: list[Team]) -> dict[str, float]:
        by_name = {str(club): float(elo) for club, elo in zip(df["Club"], df["Elo"], strict=True)}
        result: dict[str, float] = {}
        missing: list[str] = []
        for team in teams:
            name = team.clubelo_name
            if name is None or name not in by_name:
                missing.append(team.id)
                continue
            result[team.id] = by_name[name]
        if missing:
            raise ClubeloError(
                f"clubelo.com no trae Elo para: {missing}; revisa el campo `clubelo_name` "
                f"de esos equipos en data/team_aliases.yaml"
            )
        return result
