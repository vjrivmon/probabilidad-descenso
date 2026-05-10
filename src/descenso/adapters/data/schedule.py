"""Fuente del calendario de LaLiga (jugados + pendientes): openfootball/football.json.

FBref —la fuente original de este adaptador— está detrás de Cloudflare y devuelve
403 a cualquier cliente que no sea un navegador, así que no es scrapeable de forma
fiable. openfootball es un repo público en GitHub, sin API key, con la temporada
completa: cada partido trae jornada, fecha y, si ya se jugó, el marcador
(`score.ft`). URL: https://raw.githubusercontent.com/openfootball/football.json
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.team_aliases import TeamAliasError, resolve_from_source
from descenso.domain.match import Match
from descenso.domain.team import Team

logger = logging.getLogger(__name__)

OPENFOOTBALL_BASE = "https://raw.githubusercontent.com/openfootball/football.json/master"
OVERRIDE_FILE = Path("data/fixtures_override.csv")
_MATCHDAY_RE = re.compile(r"(\d+)")
# Columnas del DataFrame que se cachea / lee (un partido por fila).
_SCHEDULE_COLUMNS = [
    "season",
    "gameweek",
    "date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
]


class ScheduleError(RuntimeError):
    """No se pudo obtener/parsear el calendario (fuente caída, formato cambiado, ...)."""


def season_slug(season: int) -> str:
    """2025 -> '2025-26' (el formato de carpeta de openfootball)."""
    return f"{season}-{(season + 1) % 100:02d}"


class OpenFootballScheduleSource:
    def __init__(self, cache: ParquetCache, client: httpx.Client | None = None) -> None:
        self.cache = cache
        self.client = client or httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={
                "User-Agent": "descenso/0.1 (+https://github.com/vjrivmon/probabilidad-descenso)"
            },
        )

    def fetch_schedule(
        self, season: int, teams: list[Team], prefer_cache: bool = False
    ) -> list[Match]:
        """Devuelve todos los partidos de `season` (jugados con resultado, pendientes sin él).

        Deduplica por `(temporada, local, visitante)` (la jornada es solo una
        etiqueta). `prefer_cache=True` usa el cache si existe sin tocar la red. Si
        la red falla y hay cache, lo usa avisando; si no, intenta
        `data/fixtures_override.csv`; si tampoco, levanta `ScheduleError`.
        """
        cache_name = f"schedule_{season}"

        if prefer_cache and self.cache.has(cache_name):
            return self._matches_from_df(self.cache.load(cache_name))

        slug = season_slug(season)
        url = f"{OPENFOOTBALL_BASE}/{slug}/es.1.json"
        try:
            df = self._download(url, season, teams)
            self.cache.save(cache_name, df)
            return self._matches_from_df(df)
        except ScheduleError as exc:
            if self.cache.has(cache_name):
                logger.warning(
                    "no pude refrescar el calendario (%s); uso el cache previo (%s)",
                    exc,
                    self.cache.path(cache_name),
                )
                return self._matches_from_df(self.cache.load(cache_name))
            override = self._load_override(season, teams)
            if override is not None:
                logger.warning(
                    "no pude obtener el calendario online (%s); uso %s", exc, OVERRIDE_FILE
                )
                return override
            raise ScheduleError(
                f"{exc}. No hay cache previo ni {OVERRIDE_FILE}. Crea ese fichero "
                f"(columnas: {','.join(_SCHEDULE_COLUMNS)}; goles vacíos = partido pendiente) "
                f"o reintenta con conexión."
            ) from exc

    def _download(self, url: str, season: int, teams: list[Team]) -> pd.DataFrame:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ScheduleError(
                f"openfootball respondió {exc.response.status_code} a {url} "
                f"(¿temporada {season_slug(season)} aún sin publicar?)"
            ) from exc
        except httpx.HTTPError as exc:
            raise ScheduleError(f"no pude contactar con openfootball ({url}): {exc}") from exc
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise ScheduleError(f"openfootball ({url}) no devolvió JSON válido: {exc}") from exc
        raw_matches = data.get("matches") if isinstance(data, dict) else None
        if not isinstance(raw_matches, list) or not raw_matches:
            raise ScheduleError(
                f"el JSON de openfootball ({url}) no tiene una lista 'matches'; "
                f"puede que el formato haya cambiado — abre un issue"
            )
        return self._build_df(raw_matches, season, teams, source_label=url)

    def _build_df(
        self,
        raw_matches: list[dict[str, Any]],
        season: int,
        teams: list[Team],
        source_label: str,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for entry in raw_matches:
            name_home = entry.get("team1")
            name_away = entry.get("team2")
            if not name_home or not name_away:
                raise ScheduleError(f"un partido de {source_label} no tiene team1/team2: {entry!r}")
            try:
                home = resolve_from_source(teams, "openfootball", str(name_home))
                away = resolve_from_source(teams, "openfootball", str(name_away))
            except TeamAliasError as exc:
                raise ScheduleError(str(exc)) from exc
            hg, ag = _parse_score(entry.get("score"))
            rows.append(
                {
                    "season": season,
                    "gameweek": _parse_gameweek(entry.get("round")),
                    "date": _parse_date(entry.get("date")),
                    "home_team": home.id,
                    "away_team": away.id,
                    "home_goals": hg,
                    "away_goals": ag,
                }
            )
        df = pd.DataFrame(rows, columns=_SCHEDULE_COLUMNS)
        # La fuente "jugado con resultado" gana sobre un duplicado pendiente.
        df["_played"] = df["home_goals"].notna()
        df = (
            df.sort_values("_played", ascending=False)
            .drop_duplicates(subset=["season", "home_team", "away_team"], keep="first")
            .drop(columns="_played")
            .reset_index(drop=True)
        )
        df["home_goals"] = df["home_goals"].astype("Int64")
        df["away_goals"] = df["away_goals"].astype("Int64")
        return df

    def _load_override(self, season: int, teams: list[Team]) -> list[Match] | None:
        if not OVERRIDE_FILE.exists():
            return None
        try:
            df = pd.read_csv(OVERRIDE_FILE)
        except (pd.errors.ParserError, ValueError, OSError) as exc:
            raise ScheduleError(f"{OVERRIDE_FILE} no se puede leer como CSV: {exc}") from exc
        missing = set(_SCHEDULE_COLUMNS) - set(df.columns)
        if missing:
            raise ScheduleError(f"{OVERRIDE_FILE} no tiene las columnas {sorted(missing)}")
        known = {t.id for t in teams}
        bad = (set(df["home_team"]) | set(df["away_team"])) - known
        if bad:
            raise ScheduleError(f"{OVERRIDE_FILE} referencia equipos desconocidos: {sorted(bad)}")
        df = df[df["season"] == season].copy()
        df["home_goals"] = pd.to_numeric(df["home_goals"], errors="coerce").astype("Int64")
        df["away_goals"] = pd.to_numeric(df["away_goals"], errors="coerce").astype("Int64")
        return self._matches_from_df(df)

    @staticmethod
    def _matches_from_df(df: pd.DataFrame) -> list[Match]:
        matches: list[Match] = []
        for row in df.itertuples(index=False):
            hg = None if pd.isna(row.home_goals) else int(row.home_goals)
            ag = None if pd.isna(row.away_goals) else int(row.away_goals)
            raw_date = getattr(row, "date", None)
            date = None if raw_date is None or pd.isna(raw_date) else _coerce_date(raw_date)
            matches.append(
                Match(
                    season=int(row.season),
                    gameweek=int(row.gameweek),
                    date=date,
                    home_team=str(row.home_team),
                    away_team=str(row.away_team),
                    home_goals=hg,
                    away_goals=ag,
                )
            )
        return matches


def _parse_gameweek(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = _MATCHDAY_RE.search(value)
        if m:
            return int(m.group(1))
    return 0


def _parse_date(value: Any) -> str | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return None


def _coerce_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_score(score: Any) -> tuple[int | None, int | None]:
    if not isinstance(score, dict):
        return None, None
    ft = score.get("ft")
    if not isinstance(ft, (list, tuple)) or len(ft) != 2:
        return None, None
    try:
        return int(ft[0]), int(ft[1])
    except (TypeError, ValueError):
        return None, None
