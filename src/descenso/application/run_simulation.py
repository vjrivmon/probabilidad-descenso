"""Caso de uso: correr una simulación Monte Carlo del calendario restante.

En el CP1 (modelo "puro") la fuerza efectiva de cada equipo es directamente su
Elo de clubelo; el blend con la forma / xG / entrenadores llega en el CP2
(`build_strengths`).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.clubelo_elo import ClubeloEloSource
from descenso.adapters.data.schedule import OpenFootballScheduleSource
from descenso.adapters.data.team_aliases import load_teams
from descenso.config import AppConfig
from descenso.domain.match import Match, MatchStatus
from descenso.domain.match_model import EloLogisticMatchModel
from descenso.domain.probabilities import RelegationProbabilities
from descenso.domain.simulator import SimulationConfig, run_monte_carlo
from descenso.domain.standings import build_table
from descenso.domain.team import Team

logger = logging.getLogger(__name__)

LAST_RUN_FILE = "last_run.json"


@dataclass(frozen=True)
class FixedResult:
    """Un resultado que el usuario fuerza (`--fix` o modo interactivo)."""

    home_team: str  # Team.id
    home_goals: int
    away_team: str  # Team.id
    away_goals: int


@dataclass(frozen=True)
class SimulationInputs:
    teams: list[Team]
    elo: dict[str, float]
    matches: list[Match]


@dataclass(frozen=True)
class SimulationOutcome:
    season: int
    teams: list[Team]
    n_played: int
    n_pending: int  # partidos que se han simulado (ya descontados los fijados)
    model_type: str
    probabilities: RelegationProbabilities
    applied_fixed: list[FixedResult]
    ignored_fixed: list[tuple[FixedResult, str]]  # (fix, motivo)
    notes: list[str]

    @property
    def team_names(self) -> dict[str, str]:
        return {t.id: t.name for t in self.teams}


def load_inputs(config: AppConfig, prefer_cache: bool = True) -> SimulationInputs:
    """Carga equipos, Elo y calendario (del cache si está disponible)."""
    teams = load_teams(config.paths.team_aliases_file)
    cache = ParquetCache(config.paths.cache_dir)
    elo = ClubeloEloSource(cache).fetch_current_elo(teams, prefer_cache=prefer_cache)
    matches = OpenFootballScheduleSource(cache).fetch_schedule(
        config.season, teams, prefer_cache=prefer_cache
    )
    return SimulationInputs(teams=teams, elo=elo, matches=matches)


def run_simulation(
    config: AppConfig,
    fixed_results: list[FixedResult] | None = None,
    n_sims: int | None = None,
    seed: int | None = None,
    prefer_cache: bool = True,
    inputs: SimulationInputs | None = None,
) -> SimulationOutcome:
    """Carga datos, aplica los resultados fijados, simula y devuelve P(descenso) por equipo."""
    inputs = inputs or load_inputs(config, prefer_cache=prefer_cache)
    teams, elo, matches = inputs.teams, inputs.elo, inputs.matches
    team_ids = [t.id for t in teams]

    matches, applied, ignored = _apply_fixed(matches, fixed_results or [])
    played = [m for m in matches if m.status is MatchStatus.PLAYED]
    pending = [m for m in matches if m.status is MatchStatus.PENDING]

    base_table = build_table(team_ids, played)

    notes: list[str] = []
    strengths = dict(elo)  # CP1: fuerza efectiva = Elo de clubelo
    if config.model.model_type == "adjusted":
        notes.append(
            "el modelo ajustado (forma + xG + entrenadores) llega en el CP2; "
            "esta simulación usa solo el Elo de clubelo (modelo puro)"
        )

    match_model = EloLogisticMatchModel(
        home_advantage_elo=config.model.home_advantage_elo,
        draw_base=config.model.draw_base,
    )
    sim_config = SimulationConfig(
        n_sims=n_sims if n_sims is not None else config.model.n_sims,
        n_relegation=config.model.n_relegation,
        seed=seed,
    )
    probabilities = run_monte_carlo(
        team_ids, base_table, pending, strengths, match_model, sim_config
    )

    return SimulationOutcome(
        season=config.season,
        teams=teams,
        n_played=len(played),
        n_pending=len(pending),
        model_type=config.model.model_type,
        probabilities=probabilities,
        applied_fixed=applied,
        ignored_fixed=ignored,
        notes=notes,
    )


def _apply_fixed(
    matches: list[Match], fixed: list[FixedResult]
) -> tuple[list[Match], list[FixedResult], list[tuple[FixedResult, str]]]:
    by_pair: dict[tuple[str, str], int] = {
        (m.home_team, m.away_team): i for i, m in enumerate(matches)
    }
    result = list(matches)
    applied: list[FixedResult] = []
    ignored: list[tuple[FixedResult, str]] = []
    for fx in fixed:
        idx = by_pair.get((fx.home_team, fx.away_team))
        if idx is None:
            swapped = by_pair.get((fx.away_team, fx.home_team))
            reason = (
                "ese emparejamiento no está en el calendario de la temporada"
                if swapped is None
                else f"en el calendario juega en casa {fx.away_team}, no {fx.home_team}"
            )
            ignored.append((fx, reason))
            continue
        existing = result[idx]
        if existing.status is MatchStatus.PLAYED and not existing.is_fixed:
            ignored.append(
                (fx, f"ese partido ya se jugó {existing.home_goals}-{existing.away_goals}")
            )
            continue
        result[idx] = existing.model_copy(
            update={
                "home_goals": fx.home_goals,
                "away_goals": fx.away_goals,
                "is_fixed": True,
            }
        )
        applied.append(fx)
    return result, applied, ignored


def save_last_run(outcome: SimulationOutcome, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / LAST_RUN_FILE
    payload = {
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "season": outcome.season,
        "n_played": outcome.n_played,
        "n_pending": outcome.n_pending,
        "model_type": outcome.model_type,
        "n_sims": outcome.probabilities.n_sims,
        "seed": outcome.probabilities.seed,
        "team_names": outcome.team_names,
        "applied_fixed": [
            [fx.home_team, fx.home_goals, fx.away_team, fx.away_goals]
            for fx in outcome.applied_fixed
        ],
        "teams": [
            {
                "team": tp.team,
                "p_relegation": tp.p_relegation,
                "expected_points": tp.expected_points,
                "expected_position": tp.expected_position,
            }
            for tp in outcome.probabilities.ranked()
        ],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_last_run(cache_dir: Path) -> dict[str, Any] | None:
    path = cache_dir / LAST_RUN_FILE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("no pude leer la última simulación (%s): %s", path, exc)
        return None
    return data if isinstance(data, dict) else None
