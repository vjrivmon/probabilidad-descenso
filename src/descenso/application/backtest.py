"""Caso de uso: backtest histórico — ¿predice mejor el modelo ajustado que el puro?

Para cada temporada pasada y cada jornada del tramo final, reconstruye el estado
*as-of* esa jornada (¡sin data leakage!), predice P(descenso) con ambos modelos y
lo compara con el desenlace real. Reporta Brier score y log-loss.

Invariante anti-leakage (verificado en el código):
    ningún partido marcado 'jugado' tiene fecha > fecha_corte.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import math
import re
import unicodedata
from dataclasses import dataclass

import httpx
import pandas as pd

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.clubelo_elo import ClubeloError
from descenso.adapters.data.schedule import OPENFOOTBALL_BASE, season_slug
from descenso.adapters.data.understat_xg import UnderstatError, UnderstatXgSource
from descenso.config import AppConfig, ModelConfig
from descenso.domain.match import Match, MatchStatus
from descenso.domain.match_model import EloLogisticMatchModel
from descenso.domain.simulator import SimulationConfig, run_monte_carlo
from descenso.domain.standings import build_table, order_table
from descenso.domain.strength_model import compute_strengths, effective_strengths
from descenso.domain.team import Team

logger = logging.getLogger(__name__)

_CLIP_MIN = 1e-12
_CLIP_MAX = 1.0 - 1e-12

# Patrón de ronda para extraer número de jornada
_ROUND_RE = re.compile(r"(\d+)")


@dataclass(frozen=True)
class BacktestResult:
    seasons: list[int]
    horizon_gameweeks: int
    n_sims: int
    brier_pure: float
    brier_adjusted: float
    logloss_pure: float
    logloss_adjusted: float

    @property
    def brier_improvement(self) -> float:
        if self.brier_pure == 0:
            return 0.0
        return (self.brier_pure - self.brier_adjusted) / self.brier_pure


def run_backtest(
    seasons: list[int],
    config: AppConfig,
    horizon_gameweeks: int = 5,
    n_sims: int = 20_000,
    seed: int | None = None,
) -> BacktestResult:
    """Backtest histórico sin data leakage.

    Para cada temporada en `seasons`:
    1. Descarga el calendario completo de openfootball.
    2. Si no tiene 380 partidos jugados, la salta (temporada incompleta).
    3. Construye el estado as-of (jornada 38 - horizon_gameweeks).
    4. Baja el Elo de clubelo a la fecha de corte.
    5. Simula con ambos modelos (puro y ajustado).
    6. Calcula Brier y log-loss contra el desenlace real.

    Devuelve las medias agregadas sobre todos los (temporada, equipo).
    """
    if seed is None:
        seed = 42  # seed fija para reproducibilidad del backtest

    cache = ParquetCache(config.paths.cache_dir)
    client = httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={
            "User-Agent": ("descenso/0.1 (+https://github.com/vjrivmon/probabilidad-descenso)")
        },
    )

    brier_pure_vals: list[float] = []
    brier_adj_vals: list[float] = []
    logloss_pure_vals: list[float] = []
    logloss_adj_vals: list[float] = []
    seasons_used: list[int] = []

    for season in seasons:
        result = _backtest_season(
            season=season,
            config=config,
            horizon=horizon_gameweeks,
            n_sims=n_sims,
            seed=seed,
            cache=cache,
            client=client,
        )
        if result is None:
            continue

        seasons_used.append(season)
        bp, ba, lp, la = result
        brier_pure_vals.extend(bp)
        brier_adj_vals.extend(ba)
        logloss_pure_vals.extend(lp)
        logloss_adj_vals.extend(la)

    if not seasons_used:
        raise ValueError(
            f"ninguna de las temporadas {seasons} está completa en openfootball "
            f"(¿has corrido `descenso data refresh`?)"
        )

    return BacktestResult(
        seasons=seasons_used,
        horizon_gameweeks=horizon_gameweeks,
        n_sims=n_sims,
        brier_pure=_mean(brier_pure_vals),
        brier_adjusted=_mean(brier_adj_vals),
        logloss_pure=_mean(logloss_pure_vals),
        logloss_adjusted=_mean(logloss_adj_vals),
    )


# --------------------------------------------------------------------------- #
# lógica por temporada
# --------------------------------------------------------------------------- #


def _backtest_season(
    season: int,
    config: AppConfig,
    horizon: int,
    n_sims: int,
    seed: int,
    cache: ParquetCache,
    client: httpx.Client,
) -> tuple[list[float], list[float], list[float], list[float]] | None:
    """Devuelve (brier_pure[], brier_adj[], logloss_pure[], logloss_adj[]) o None si la salta."""
    slug = season_slug(season)
    cache_name = f"backtest_schedule_{season}"

    # Descargar o recuperar del cache
    raw_matches_data_or_none = _load_raw_matches(season, slug, cache_name, cache, client)
    if raw_matches_data_or_none is None:
        return None
    raw_matches_data: list[dict[str, object]] = raw_matches_data_or_none

    # Verificar que la temporada está completa (380 partidos jugados)
    played_count = sum(1 for m in raw_matches_data if _has_score(m))
    if played_count < 380:
        logger.warning(
            "temporada %s incompleta en openfootball (%d/380 jugados), la salto",
            slug,
            played_count,
        )
        return None

    # Construir equipos autocontenidos desde el JSON
    teams = _extract_teams(raw_matches_data)
    team_ids = [t.id for t in teams]
    team_by_openfootball: dict[str, Team] = {t.openfootball_name or t.id: t for t in teams}

    # Parsear todos los partidos
    all_matches = _parse_matches(raw_matches_data, team_by_openfootball, season)

    # Jornada de corte y fecha de corte
    cutoff_gw = 38 - horizon
    cutoff_date = _cutoff_date(all_matches, cutoff_gw)
    if cutoff_date is None:
        logger.warning(
            "temporada %s: no pude determinar la fecha de corte para jornada %d, la salto",
            slug,
            cutoff_gw,
        )
        return None

    # Estado as-of: jugados = GW <= cutoff y con fecha <= cutoff_date
    played_asof = [
        m
        for m in all_matches
        if m.status is MatchStatus.PLAYED
        and m.gameweek <= cutoff_gw
        and (m.date is None or m.date <= cutoff_date)
    ]
    # Los partidos posteriores al corte se simulan: hay que BORRARLES el marcador real
    # (en una temporada ya terminada todos lo tienen) o `run_monte_carlo` los trataría
    # como fijados y reproduciría la tabla real → Brier = 0 espurio.
    pending_asof = [
        m.model_copy(
            update={
                "home_goals": None,
                "away_goals": None,
                "home_xg": None,
                "away_xg": None,
                "is_fixed": False,
            }
        )
        for m in all_matches
        if not (
            m.status is MatchStatus.PLAYED
            and m.gameweek <= cutoff_gw
            and (m.date is None or m.date <= cutoff_date)
        )
    ]

    # Anti-leakage: ningún partido jugado debe tener fecha > cutoff_date
    for m in played_asof:
        if m.date is not None and m.date > cutoff_date:
            raise AssertionError(
                f"data leakage detectado en temporada {season}: partido {m.home_team} vs "
                f"{m.away_team} (fecha {m.date}) marcado como jugado pero es posterior "
                f"a la fecha de corte {cutoff_date}"
            )

    # Elo de clubelo a la fecha de corte
    elo_table = _fetch_elo_table(cutoff_date, season, cache, client)
    elo = _match_elo_to_teams(elo_table, teams)

    # (Opcional) xG de Understat — capturamos el error y continuamos
    try:
        xg_source = UnderstatXgSource(cache, client)
        xg_matches_all = xg_source.fetch_match_xg(season, teams, prefer_cache=True)
        # Enriquecer solo los partidos jugados as-of con xG
        played_asof = _merge_xg(played_asof, xg_matches_all, cutoff_date)
    except UnderstatError as exc:
        logger.debug(
            "xG de Understat no disponible para %s: %s; el modelo usa solo goles", season, exc
        )

    # Tabla base as-of
    base_table = build_table(team_ids, played_asof)

    match_model = EloLogisticMatchModel(
        home_advantage_elo=config.model.home_advantage_elo,
        draw_base=config.model.draw_base,
    )
    sim_cfg = SimulationConfig(n_sims=n_sims, n_relegation=3, seed=seed)

    # Simular con el modelo puro (alpha=1.0, sin deltas)
    pure_model_cfg = ModelConfig(**{**config.model.model_dump(), "alpha": 1.0})
    snapshots_pure = compute_strengths(
        elo_base=elo,
        played_matches=played_asof,
        coach_changes={},
        injury_adjustments={},
        as_of=cutoff_date,
        config=pure_model_cfg,
    )
    strengths_pure = effective_strengths(snapshots_pure)
    probs_pure = run_monte_carlo(
        team_ids, base_table, pending_asof, strengths_pure, match_model, sim_cfg
    )

    # Simular con el modelo ajustado (alpha de config, sin datos de entrenadores
    # históricos porque no los tenemos para temporadas pasadas)
    adj_model_cfg = ModelConfig(**{**config.model.model_dump(), "model_type": "adjusted"})
    snapshots_adj = compute_strengths(
        elo_base=elo,
        played_matches=played_asof,
        coach_changes={},
        injury_adjustments={},
        as_of=cutoff_date,
        config=adj_model_cfg,
    )
    strengths_adj = effective_strengths(snapshots_adj)
    probs_adj = run_monte_carlo(
        team_ids, base_table, pending_asof, strengths_adj, match_model, sim_cfg
    )

    # Desenlace real: construir la tabla final y ver quién descendió (posiciones 18-20)
    final_table = order_table(build_table(team_ids, all_matches), all_matches)
    n = len(final_table)
    relegated_real = {r.team for r in final_table[n - 3 :]}

    # Acumular métricas por equipo
    p_pure_map = {tp.team: tp.p_relegation for tp in probs_pure.teams}
    p_adj_map = {tp.team: tp.p_relegation for tp in probs_adj.teams}

    brier_pure: list[float] = []
    brier_adj: list[float] = []
    logloss_pure: list[float] = []
    logloss_adj: list[float] = []

    for team_id in team_ids:
        y = 1.0 if team_id in relegated_real else 0.0
        pp = p_pure_map.get(team_id, 0.0)
        pa = p_adj_map.get(team_id, 0.0)

        brier_pure.append((pp - y) ** 2)
        brier_adj.append((pa - y) ** 2)

        pp_c = max(_CLIP_MIN, min(_CLIP_MAX, pp))
        pa_c = max(_CLIP_MIN, min(_CLIP_MAX, pa))
        logloss_pure.append(-(y * math.log(pp_c) + (1.0 - y) * math.log(1.0 - pp_c)))
        logloss_adj.append(-(y * math.log(pa_c) + (1.0 - y) * math.log(1.0 - pa_c)))

    return brier_pure, brier_adj, logloss_pure, logloss_adj


# --------------------------------------------------------------------------- #
# helpers de openfootball
# --------------------------------------------------------------------------- #


def _load_raw_matches(
    season: int,
    slug: str,
    cache_name: str,
    cache: ParquetCache,
    client: httpx.Client,
) -> list[dict[str, object]] | None:
    """Devuelve la lista raw de matches del JSON de openfootball.

    Cachea en Parquet para no re-descargar. Si el cache existe, lo lee.
    Si falla la red, devuelve None.
    """
    # Cache en Parquet: columnas planas (no anidadas). Guardamos el JSON crudo
    # en un fichero separado para evitar serializar dicts anidados en Parquet.
    json_cache_path = cache.cache_dir / f"{cache_name}.json"
    if json_cache_path.exists():
        try:
            with json_cache_path.open("r", encoding="utf-8") as fh:
                cached: object = json.load(fh)
            if isinstance(cached, list):
                return [m for m in cached if isinstance(m, dict)]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("cache de openfootball corrupto (%s): %s", json_cache_path, exc)

    url = f"{OPENFOOTBALL_BASE}/{slug}/es.1.json"
    try:
        resp = client.get(url)
        resp.raise_for_status()
        data: object = resp.json()
    except Exception as exc:
        logger.warning(
            "no pude descargar el calendario de openfootball para %s (%s): %s",
            slug,
            url,
            exc,
        )
        return None

    raw_matches = data.get("matches") if isinstance(data, dict) else None
    if not isinstance(raw_matches, list) or not raw_matches:
        logger.warning("el JSON de openfootball (%s) no tiene una lista 'matches'", url)
        return None

    typed_matches: list[dict[str, object]] = [m for m in raw_matches if isinstance(m, dict)]

    cache.cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = json_cache_path.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(typed_matches, ensure_ascii=False), encoding="utf-8")
        tmp.replace(json_cache_path)
    except OSError as exc:
        logger.warning("no pude cachear el JSON de openfootball (%s): %s", json_cache_path, exc)

    return typed_matches


def _has_score(entry: dict[str, object]) -> bool:
    score = entry.get("score")
    if not isinstance(score, dict):
        return False
    ft = score.get("ft")
    return isinstance(ft, list) and len(ft) == 2


def _slugify(name: str) -> str:
    """Convierte un nombre de equipo en un slug estable: minúsculas, sin acentos, sin puntos."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    slug = ascii_.lower().replace(".", "").strip()
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"[^a-z0-9-]", "", slug)
    return slug


def _extract_teams(raw_matches: list[dict[str, object]]) -> list[Team]:
    """Construye la lista de equipos únicos desde el JSON de openfootball."""
    seen: dict[str, Team] = {}
    for entry in raw_matches:
        for key in ("team1", "team2"):
            name = entry.get(key)
            if not isinstance(name, str) or not name:
                continue
            slug = _slugify(name)
            if slug not in seen:
                seen[slug] = Team(
                    id=slug,
                    name=name,
                    openfootball_name=name,
                    clubelo_name=None,
                    understat_name=None,
                    fbref_name=None,
                )
    return list(seen.values())


def _parse_matches(
    raw_matches: list[dict[str, object]],
    team_by_openfootball: dict[str, Team],
    season: int,
) -> list[Match]:
    """Parsea los partidos del JSON a objetos Match."""
    matches: list[Match] = []
    for entry in raw_matches:
        name1 = entry.get("team1")
        name2 = entry.get("team2")
        if not isinstance(name1, str) or not isinstance(name2, str):
            continue
        home = team_by_openfootball.get(name1)
        away = team_by_openfootball.get(name2)
        if home is None or away is None:
            continue

        gw = _parse_gw(entry.get("round"))
        date = _parse_date(entry.get("date"))
        hg, ag = _parse_score(entry.get("score"))

        matches.append(
            Match(
                season=season,
                gameweek=gw,
                date=date,
                home_team=home.id,
                away_team=away.id,
                home_goals=hg,
                away_goals=ag,
            )
        )
    return matches


def _parse_gw(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        m = _ROUND_RE.search(value)
        if m:
            return int(m.group(1))
    return 0


def _parse_date(value: object) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_score(score: object) -> tuple[int | None, int | None]:
    if not isinstance(score, dict):
        return None, None
    ft = score.get("ft")
    if not isinstance(ft, (list, tuple)) or len(ft) != 2:
        return None, None
    try:
        return int(ft[0]), int(ft[1])
    except (TypeError, ValueError):
        return None, None


def _cutoff_date(matches: list[Match], cutoff_gw: int) -> dt.date | None:
    """La fecha del último partido de la jornada cutoff_gw."""
    dates = [m.date for m in matches if m.gameweek == cutoff_gw and m.date is not None]
    return max(dates) if dates else None


# --------------------------------------------------------------------------- #
# helpers de clubelo (backtest)
# --------------------------------------------------------------------------- #


def _fetch_elo_table(
    on_date: dt.date,
    season: int,
    cache: ParquetCache,
    client: httpx.Client,
) -> dict[str, float]:
    """Descarga (o lee del cache) el CSV de clubelo para `on_date`.

    Devuelve `{nombre_clubelo: elo}`.
    Verifica que cada fila cumpla `From <= on_date <= To` (clubelo devuelve
    rangos de validez).
    """
    import io

    cache_name = f"backtest_clubelo_{on_date.isoformat()}"
    clubelo_url = f"http://api.clubelo.com/{on_date.isoformat()}"

    if cache.has(cache_name):
        df = cache.load(cache_name)
    else:
        try:
            resp = client.get(clubelo_url)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text))
            cache.save(cache_name, df)
        except Exception as exc:
            if cache.has(cache_name):
                logger.warning(
                    "no pude refrescar el Elo de clubelo (%s); uso cache: %s",
                    clubelo_url,
                    exc,
                )
                df = cache.load(cache_name)
            else:
                raise ClubeloError(
                    f"no pude obtener el Elo de clubelo para {on_date} ({clubelo_url}): {exc}"
                ) from exc

    if "Club" not in df.columns or "Elo" not in df.columns:
        raise ClubeloError(
            f"el CSV de clubelo.com ({clubelo_url}) no tiene el formato esperado "
            f"(faltan columnas Club/Elo)"
        )

    result: dict[str, float] = {}
    for _, row in df.iterrows():
        club = str(row["Club"])
        elo = float(row["Elo"])
        # Verificar rango de validez si están las columnas
        if "From" in df.columns and "To" in df.columns:
            try:
                from_date = dt.date.fromisoformat(str(row["From"]))
                to_date = dt.date.fromisoformat(str(row["To"]))
                if not (from_date <= on_date <= to_date):
                    continue  # fila no válida para esta fecha
            except ValueError:
                pass  # si no parsea, incluimos igual
        result[club] = elo
    return result


def _norm_name(name: str) -> str:
    """Normaliza un nombre para la comparación fuzzy: minúsculas, sin acentos."""
    nfkd = unicodedata.normalize("NFKD", name)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def _match_elo_to_teams(
    elo_table: dict[str, float],
    teams: list[Team],
) -> dict[str, float]:
    """Casa los equipos del backtest con las filas de clubelo por comparación de slug.

    Si no encuentra Elo para un equipo, usa el Elo medio de los demás y avisa.
    """
    norm_elo: dict[str, float] = {_norm_name(k): v for k, v in elo_table.items()}
    result: dict[str, float] = {}
    missing: list[str] = []

    for team in teams:
        # Intenta por slug del id del equipo
        slug_id = _norm_name(team.id.replace("-", " "))
        slug_name = _norm_name(team.name)
        elo_val: float | None = None

        for needle in (slug_id, slug_name):
            # Búsqueda exacta
            if needle in norm_elo:
                elo_val = norm_elo[needle]
                break
            # Búsqueda parcial: uno contiene al otro
            for k, v in norm_elo.items():
                if needle in k or k in needle:
                    elo_val = v
                    break
            if elo_val is not None:
                break

        if elo_val is not None:
            result[team.id] = elo_val
        else:
            missing.append(team.id)

    if missing and result:
        mean_elo = sum(result.values()) / len(result)
        for team_id in missing:
            result[team_id] = mean_elo
            logger.warning(
                "backtest: no encontré Elo en clubelo para %r; uso Elo medio (%.0f)",
                team_id,
                mean_elo,
            )
    elif missing:
        raise ClubeloError(
            f"backtest: no encontré Elo de clubelo para ningún equipo de la temporada "
            f"({list(missing)})"
        )

    return result


def _merge_xg(
    played: list[Match],
    xg_matches: list[Match],
    cutoff_date: dt.date,
) -> list[Match]:
    """Copia home_xg/away_xg de xg_matches a played (solo partidos con fecha <= cutoff_date)."""
    xg_index: dict[tuple[str, str], Match] = {(m.home_team, m.away_team): m for m in xg_matches}
    result: list[Match] = []
    for m in played:
        xg_m = xg_index.get((m.home_team, m.away_team))
        if xg_m is not None and (m.date is None or m.date <= cutoff_date):
            m = m.model_copy(update={"home_xg": xg_m.home_xg, "away_xg": xg_m.away_xg})
        result.append(m)
    return result


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
