"""Caso de uso: cómo ha evolucionado la P(descenso) jornada a jornada en la temporada en curso.

Una de las cosas que más pide la afición (ver `docs/community-factors.md`) es ver la
serie de cada equipo: "¿cómo ha ido subiendo el % del Espanyol jornada tras jornada?".
Esto rebobina el calendario de la temporada actual: para cada una de las últimas N
jornadas completadas reconstruye el estado *de aquel momento* (clasificación con los
partidos hasta esa jornada, forma reciente as-of esa fecha, cambios de entrenador con
fecha <= esa fecha) y vuelve a correr la simulación con el modelo actual.

Simplificación honesta: el **Elo base de clubelo** se usa al valor de hoy en todos los
puntos (clubelo no cachea bien snapshots históricos y no queremos pisar el cache del
Elo actual). Lo que sí varía a lo largo de la serie es la clasificación, la forma
reciente, los cambios de entrenador y qué partidos quedan por jugar — que es la mayor
parte de lo que mueve el porcentaje. Para un histórico con el Elo "de cada fecha", usa
`descenso backtest` sobre temporadas pasadas.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from descenso.adapters.data.coach_changes_file import CoachChangesFile
from descenso.application.run_simulation import SimulationInputs, load_inputs
from descenso.config import AppConfig
from descenso.domain.match import Match, MatchStatus
from descenso.domain.match_model import make_match_model
from descenso.domain.simulator import SimulationConfig, run_monte_carlo
from descenso.domain.standings import build_table
from descenso.domain.strength_model import compute_strengths, effective_strengths
from descenso.domain.team import Team

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GameweekPoint:
    """Un punto de la serie: P(descenso) por equipo tras la jornada `gameweek`."""

    gameweek: int
    as_of_date: dt.date | None
    n_played: int
    p_relegation: dict[str, float]  # team_id -> P(descenso)


@dataclass(frozen=True)
class SeasonHistory:
    season: int
    teams: list[Team]
    model_type: str
    n_sims: int
    points: list[GameweekPoint]  # ordenados por jornada ascendente

    @property
    def team_names(self) -> dict[str, str]:
        return {t.id: t.name for t in self.teams}

    def candidate_team_ids(self, threshold: float = 0.005) -> list[str]:
        """Equipos que en alguna jornada de la serie superan `threshold` de P(descenso)."""
        ids: list[str] = []
        for t in self.teams:
            if any(pt.p_relegation.get(t.id, 0.0) >= threshold for pt in self.points):
                ids.append(t.id)
        # ordenados por el último punto, de mayor a menor
        last = self.points[-1].p_relegation if self.points else {}
        ids.sort(key=lambda tid: last.get(tid, 0.0), reverse=True)
        return ids


def season_history(
    config: AppConfig,
    n_gameweeks: int = 8,
    n_sims: int = 20_000,
    seed: int | None = None,
    prefer_cache: bool = True,
    inputs: SimulationInputs | None = None,
) -> SeasonHistory:
    """Reconstruye la serie de P(descenso) de las últimas `n_gameweeks` jornadas completadas.

    Lanza `ValueError` si no hay ninguna jornada jugada con fecha en el calendario.
    """
    if n_gameweeks < 1:
        raise ValueError(f"n_gameweeks debe ser >= 1, es {n_gameweeks}")

    if inputs is None:
        inputs = load_inputs(config, prefer_cache=prefer_cache)
    teams, elo, matches = inputs.teams, inputs.elo, inputs.matches
    team_ids = [t.id for t in teams]

    played = [m for m in matches if m.status is MatchStatus.PLAYED]
    if not played:
        raise ValueError("no hay partidos jugados en el calendario (¿has corrido `data refresh`?)")
    last_played_gw = max(m.gameweek for m in played)
    first_gw = max(1, last_played_gw - n_gameweeks + 1)

    coach_changes, injury_adjustments = CoachChangesFile(config.paths.coach_changes_file).load()
    use_adjusted = config.model.model_type == "adjusted"
    match_model = make_match_model(config.model)
    sim_cfg = SimulationConfig(n_sims=n_sims, n_relegation=config.model.n_relegation, seed=seed)

    points: list[GameweekPoint] = []
    for gw in range(first_gw, last_played_gw + 1):
        played_gw = [m for m in matches if m.status is MatchStatus.PLAYED and m.gameweek <= gw]
        pending_gw = [
            _strip_result(m)
            for m in matches
            if not (m.status is MatchStatus.PLAYED and m.gameweek <= gw)
        ]
        gw_dates = [m.date for m in played_gw if m.gameweek == gw and m.date is not None]
        as_of = max(gw_dates) if gw_dates else _latest_date(played_gw)

        base_table = build_table(team_ids, played_gw)
        if use_adjusted and as_of is not None:
            snapshots = compute_strengths(
                elo_base=elo,
                played_matches=played_gw,
                coach_changes=coach_changes,
                injury_adjustments=injury_adjustments,
                as_of=as_of,
                config=config.model,
            )
            strengths = effective_strengths(snapshots)
        else:
            strengths = dict(elo)

        probs = run_monte_carlo(team_ids, base_table, pending_gw, strengths, match_model, sim_cfg)
        points.append(
            GameweekPoint(
                gameweek=gw,
                as_of_date=as_of,
                n_played=len(played_gw),
                p_relegation={tp.team: tp.p_relegation for tp in probs.teams},
            )
        )

    return SeasonHistory(
        season=config.season,
        teams=teams,
        model_type=config.model.model_type,
        n_sims=n_sims,
        points=points,
    )


def _strip_result(m: Match) -> Match:
    """Devuelve el partido sin marcador (para simularlo) si lo tenía; si no, tal cual."""
    if m.status is MatchStatus.PENDING and not m.is_fixed:
        return m
    return m.model_copy(
        update={
            "home_goals": None,
            "away_goals": None,
            "home_xg": None,
            "away_xg": None,
            "is_fixed": False,
        }
    )


def _latest_date(matches: list[Match]) -> dt.date | None:
    dates = [m.date for m in matches if m.date is not None]
    return max(dates) if dates else None
