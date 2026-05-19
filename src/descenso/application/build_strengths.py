"""Caso de uso: construir las fuerzas efectivas de los equipos a una fecha dada.

Carga Elo (clubelo), calendario (openfootball), xG (Understat, opcional) y
los datos manuales de entrenadores/bajas; invoca `compute_strengths` del dominio.

Si `config.model.model_type == 'pure'`, fuerza `alpha=1.0` y deltas vacíos, lo
que es matemáticamente equivalente a usar solo el Elo base de clubelo. Así,
`compare_models` puede reutilizar esta función para ambas variantes.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.clubelo_elo import ClubeloEloSource
from descenso.adapters.data.coach_changes_file import CoachChangesFile
from descenso.adapters.data.schedule import OpenFootballScheduleSource
from descenso.adapters.data.team_aliases import load_teams
from descenso.adapters.data.understat_xg import UnderstatError, UnderstatXgSource
from descenso.config import AppConfig, ModelConfig
from descenso.domain.match import Match, MatchStatus
from descenso.domain.strength_model import StrengthSnapshot, compute_strengths

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrengthBuildResult:
    """Resultado de `build_strengths`: snapshots por equipo y metadatos de la carga."""

    snapshots: dict[str, StrengthSnapshot]
    xg_available: bool
    n_coach_changes_applied: int  # cambios de entrenador con fecha <= as_of
    notes: list[str] = field(default_factory=list)


def build_strengths_from_data(
    elo: dict[str, float],
    played_matches: list[Match],
    config: AppConfig,
    as_of: dt.date | None = None,
    motivation_bonuses: dict[str, float] | None = None,
) -> StrengthBuildResult:
    """Calcula fuerzas a partir de datos ya cargados (Elo y partidos jugados).

    Usa esta función cuando los datos ya están disponibles (p.ej. en tests o en
    `compare_models` cuando los datos ya se cargaron). No hace IO.
    """
    as_of = as_of or dt.date.today()
    notes: list[str] = []

    # xG: ya debe estar en los played_matches si se cargó antes; si no, se degrada.
    has_xg = any(m.home_xg is not None for m in played_matches)
    if not has_xg:
        notes.append(
            "xG de Understat no disponible en los datos proporcionados; "
            "el modelo usa solo goles reales"
        )

    if config.model.model_type == "pure":
        model_cfg = ModelConfig(**{**config.model.model_dump(), "alpha": 1.0})
        effective_coach: dict[str, list[tuple[dt.date, float | None]]] = {}
        effective_injuries: dict[str, float] = {}
    else:
        model_cfg = config.model
        effective_coach = {}
        effective_injuries = {}

    snapshots = compute_strengths(
        elo_base=elo,
        played_matches=played_matches,
        coach_changes=effective_coach,
        injury_adjustments=effective_injuries,
        as_of=as_of,
        config=model_cfg,
        motivation_bonuses=motivation_bonuses,
    )

    return StrengthBuildResult(
        snapshots=snapshots,
        xg_available=has_xg,
        n_coach_changes_applied=0,
        notes=notes,
    )


def build_strengths(
    config: AppConfig,
    as_of: dt.date | None = None,
    prefer_cache: bool = True,
    motivation_bonuses: dict[str, float] | None = None,
) -> StrengthBuildResult:
    """Carga datos y calcula las fuerzas efectivas de cada equipo a `as_of`.

    Si `config.model.model_type == 'pure'`, usa `alpha=1.0` y deltas vacíos
    (equivale a solo Elo, idéntico al CP1). El parámetro `as_of` por defecto
    es `dt.date.today()`.

    Captura `UnderstatError` y continúa sin xG — el `strength_model` degrada
    automáticamente a `beta_eff=1` (solo goles reales).
    """
    as_of = as_of or dt.date.today()
    notes: list[str] = []

    cache = ParquetCache(config.paths.cache_dir)
    teams = load_teams(config.paths.team_aliases_file)

    # Elo base
    elo = ClubeloEloSource(cache).fetch_current_elo(teams, on_date=as_of, prefer_cache=prefer_cache)

    # Calendario (jugados + pendientes)
    matches: list[Match] = OpenFootballScheduleSource(cache).fetch_schedule(
        config.season, teams, prefer_cache=prefer_cache
    )

    # xG de Understat (opcional) — enriquece los partidos jugados
    xg_available = False
    try:
        xg_matches = UnderstatXgSource(cache).fetch_match_xg(
            config.season, teams, prefer_cache=prefer_cache
        )
        matches = _merge_xg(matches, xg_matches)
        xg_available = True
        logger.debug("xG de Understat cargado: %d partidos con xG", len(xg_matches))
    except UnderstatError as exc:
        notes.append(f"xG de Understat no disponible ({exc}); el modelo usa solo goles reales")
        logger.warning("xG de Understat no disponible: %s", exc)

    # Solo partidos ya jugados para el cómputo de forma
    played = [m for m in matches if m.status is MatchStatus.PLAYED]

    # Cambios de entrenador y bajas
    coach_changes, injury_adjustments = CoachChangesFile(config.paths.coach_changes_file).load()

    # Para el modelo "pure", forzamos alpha=1.0 y borramos los deltas
    if config.model.model_type == "pure":
        model_cfg = ModelConfig(**{**config.model.model_dump(), "alpha": 1.0})
        effective_coach: dict[str, list[tuple[dt.date, float | None]]] = {}
        effective_injuries: dict[str, float] = {}
    else:
        model_cfg = config.model
        effective_coach = coach_changes
        effective_injuries = injury_adjustments

    # Cuenta cambios aplicables (fecha <= as_of)
    n_coach = sum(
        1 for cambios in effective_coach.values() for fecha, _ in cambios if fecha <= as_of
    )

    snapshots = compute_strengths(
        elo_base=elo,
        played_matches=played,
        coach_changes=effective_coach,
        injury_adjustments=effective_injuries,
        as_of=as_of,
        config=model_cfg,
        motivation_bonuses=motivation_bonuses,
    )

    return StrengthBuildResult(
        snapshots=snapshots,
        xg_available=xg_available,
        n_coach_changes_applied=n_coach,
        notes=notes,
    )


def _merge_xg(schedule: list[Match], xg_matches: list[Match]) -> list[Match]:
    """Copia `home_xg`/`away_xg` de `xg_matches` a los partidos correspondientes.

    La clave de unión es `(home_team, away_team)`. Partidos de `schedule` que no
    aparecen en `xg_matches` se devuelven tal cual (sin xG).
    """
    xg_index: dict[tuple[str, str], Match] = {(m.home_team, m.away_team): m for m in xg_matches}
    result: list[Match] = []
    for m in schedule:
        xg_match = xg_index.get((m.home_team, m.away_team))
        if xg_match is not None and m.status is MatchStatus.PLAYED:
            m = m.model_copy(
                update={
                    "home_xg": xg_match.home_xg,
                    "away_xg": xg_match.away_xg,
                }
            )
        result.append(m)
    return result
