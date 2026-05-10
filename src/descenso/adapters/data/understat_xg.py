"""Fuente de xG/xGA por partido: Understat (https://understat.com/league/La_liga/<year>).

Understat embebe los datos como JSON dentro de un <script> (`JSON.parse('...')`).
El parser debe ser defensivo: si no encuentra ese bloque, lanza UnderstatError
con la URL y la descripción del problema.

ADVERTENCIA: a partir de 2025-26, understat.com devuelve a clientes no-navegador
una página recortada (~18 KB) sin los bloques `var ... = JSON.parse('...')`.
El código es defensivo: captura ese caso y lanza UnderstatError para que los
callers (build_strengths, run_simulation) sigan sin xG.
"""

from __future__ import annotations

import codecs
import contextlib
import datetime as dt
import json
import logging
import re

import httpx
import pandas as pd

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.team_aliases import TeamAliasError, resolve_from_source
from descenso.domain.match import Match
from descenso.domain.team import Team

logger = logging.getLogger(__name__)

UNDERSTAT_BASE = "https://understat.com/league/La_liga"

# Patrón para extraer el bloque datesData = JSON.parse('...')
# Understat usa escapes \xNN dentro de la cadena, y comillas simples como delimitador.
_DATES_DATA_RE = re.compile(
    r"""var\s+datesData\s*=\s*JSON\.parse\('((?:[^'\\]|\\.)*)'\)""",
    re.DOTALL,
)

# Columnas del DataFrame cacheado (un partido por fila)
_XG_COLUMNS = [
    "season",
    "gameweek",
    "date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "home_xg",
    "away_xg",
]

# User-Agent de navegador realista para evitar bloqueos
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class UnderstatError(RuntimeError):
    """Understat cambió el formato, no respondió como se esperaba o no es scrapeable."""


class UnderstatXgSource:
    def __init__(self, cache: ParquetCache, client: httpx.Client | None = None) -> None:
        self.cache = cache
        self.client = client or httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        )

    def fetch_match_xg(
        self,
        season: int,
        teams: list[Team],
        prefer_cache: bool = False,
    ) -> list[Match]:
        """Devuelve los partidos jugados de la temporada con xG/xGA. Cachea en Parquet.

        - `prefer_cache=True`: si hay cache, lo usa sin tocar la red.
        - `prefer_cache=False`: descarga y reescribe el cache; si falla pero hay
          cache previo, lo usa avisando; si no hay cache, lanza UnderstatError.

        Si un nombre de equipo de Understat no está en el mapeo, ese partido se
        salta con un warning (no falla toda la carga).
        """
        cache_name = f"understat_xg_{season}"

        if prefer_cache and self.cache.has(cache_name):
            return self._matches_from_df(self.cache.load(cache_name))

        url = f"{UNDERSTAT_BASE}/{season}"
        try:
            df = self._download(url, season, teams)
            self.cache.save(cache_name, df)
            return self._matches_from_df(df)
        except UnderstatError:
            if self.cache.has(cache_name):
                logger.warning(
                    "no pude refrescar el xG de Understat (%s); uso el cache previo (%s)",
                    url,
                    self.cache.path(cache_name),
                )
                return self._matches_from_df(self.cache.load(cache_name))
            raise

    def _download(self, url: str, season: int, teams: list[Team]) -> pd.DataFrame:
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise UnderstatError(
                f"Understat respondió {exc.response.status_code} a {url} "
                f"(¿temporada {season} sin publicar?)"
            ) from exc
        except httpx.HTTPError as exc:
            raise UnderstatError(f"no pude contactar con understat.com ({url}): {exc}") from exc

        return self._parse_html(resp.text, url, season, teams)

    def _parse_html(self, html: str, url: str, season: int, teams: list[Team]) -> pd.DataFrame:
        """Extrae los partidos del bloque datesData embebido en el HTML de Understat."""
        match = _DATES_DATA_RE.search(html)
        if not match:
            raise UnderstatError(
                f"el formato de Understat cambió: no se encontró el bloque "
                f"`datesData = JSON.parse('...')` en {url}; "
                f"abre un issue en https://github.com/vjrivmon/probabilidad-descenso"
            )

        escaped = match.group(1)
        # Understat usa escapes \xNN (bytes en latin-1 o utf-8) dentro de la cadena JS.
        # unicode_escape decodifica \xNN y \uNNNN.
        try:
            raw_json = codecs.decode(escaped, "unicode_escape")
        except (UnicodeDecodeError, ValueError) as exc:
            raise UnderstatError(
                f"no pude decodificar los escapes del bloque datesData de {url}: {exc}"
            ) from exc

        try:
            entries = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise UnderstatError(
                f"el JSON de datesData de Understat ({url}) no es válido: {exc}"
            ) from exc

        if not isinstance(entries, list):
            raise UnderstatError(
                f"se esperaba una lista en datesData de {url}, "
                f"se recibió {type(entries).__name__}"
            )

        rows: list[dict[str, object]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            # Solo partidos ya jugados
            if not entry.get("isResult"):
                continue

            h_info = entry.get("h") or {}
            a_info = entry.get("a") or {}
            goals_info = entry.get("goals") or {}
            xg_info = entry.get("xG") or {}

            h_title = h_info.get("title") if isinstance(h_info, dict) else None
            a_title = a_info.get("title") if isinstance(a_info, dict) else None
            if not h_title or not a_title:
                logger.warning(
                    "Understat (%s): partido sin nombres de equipo, lo salto: %r", url, entry
                )
                continue

            try:
                home_team = resolve_from_source(teams, "understat", str(h_title))
                away_team = resolve_from_source(teams, "understat", str(a_title))
            except TeamAliasError as exc:
                logger.warning(
                    "Understat (%s): %s — salto este partido (%s vs %s)",
                    url,
                    exc,
                    h_title,
                    a_title,
                )
                continue

            try:
                raw_date = str(entry.get("datetime", "") or "")
                # Understat devuelve "YYYY-MM-DD HH:MM:SS" o similar
                match_date: dt.date | None = dt.datetime.fromisoformat(
                    raw_date.replace(" ", "T")
                ).date()
            except (ValueError, TypeError):
                match_date = None

            def _float(val: object) -> float | None:
                try:
                    return float(val)  # type: ignore[arg-type]  # float() acepta str y Number
                except (TypeError, ValueError):
                    return None

            def _int(val: object) -> int | None:
                if val is None:
                    return None
                try:
                    return int(str(val))
                except (TypeError, ValueError):
                    return None

            rows.append(
                {
                    "season": season,
                    "gameweek": 0,  # Understat no da jornada; se rellena como 0
                    "date": match_date.isoformat() if match_date else None,
                    "home_team": home_team.id,
                    "away_team": away_team.id,
                    "home_goals": _int(
                        goals_info.get("h") if isinstance(goals_info, dict) else None
                    ),
                    "away_goals": _int(
                        goals_info.get("a") if isinstance(goals_info, dict) else None
                    ),
                    "home_xg": _float(xg_info.get("h") if isinstance(xg_info, dict) else None),
                    "away_xg": _float(xg_info.get("a") if isinstance(xg_info, dict) else None),
                }
            )

        df = pd.DataFrame(rows, columns=_XG_COLUMNS)
        # Tipos robustos
        df["home_goals"] = pd.to_numeric(df["home_goals"], errors="coerce").astype("Int64")
        df["away_goals"] = pd.to_numeric(df["away_goals"], errors="coerce").astype("Int64")
        df["home_xg"] = pd.to_numeric(df["home_xg"], errors="coerce").astype("float64")
        df["away_xg"] = pd.to_numeric(df["away_xg"], errors="coerce").astype("float64")
        return df

    @staticmethod
    def _matches_from_df(df: pd.DataFrame) -> list[Match]:
        matches: list[Match] = []
        for row in df.itertuples(index=False):
            hg = None if pd.isna(row.home_goals) else int(row.home_goals)
            ag = None if pd.isna(row.away_goals) else int(row.away_goals)
            hxg_raw = getattr(row, "home_xg", None)
            axg_raw = getattr(row, "away_xg", None)
            hxg = None if hxg_raw is None or pd.isna(hxg_raw) else float(hxg_raw)
            axg = None if axg_raw is None or pd.isna(axg_raw) else float(axg_raw)
            raw_date = getattr(row, "date", None)
            date: dt.date | None = None
            if raw_date is not None and not (isinstance(raw_date, float) and pd.isna(raw_date)):
                with contextlib.suppress(ValueError):
                    date = dt.date.fromisoformat(str(raw_date))
            matches.append(
                Match(
                    season=int(row.season),
                    gameweek=int(row.gameweek),
                    date=date,
                    home_team=str(row.home_team),
                    away_team=str(row.away_team),
                    home_goals=hg,
                    away_goals=ag,
                    home_xg=hxg,
                    away_xg=axg,
                )
            )
        return matches
