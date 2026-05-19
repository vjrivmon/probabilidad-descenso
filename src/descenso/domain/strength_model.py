"""El modelo de fuerza efectiva con "memoria de forma" — el diferencial del proyecto.

    R_i = alpha * E_i + (1 - alpha) * F_i + delta_coach_i + delta_injuries_i

donde `E_i` es el Elo base de clubelo y `F_i` el *form rating*: el Elo base más la
media ponderada exponencialmente (vida media `form_half_life_days`) de los
"performance ratings" por partido de los últimos `form_window_matches` partidos.
El performance rating de un partido compara el resultado (mezclado con el xG para
descontar suerte) con el resultado esperado por Elo frente a ese rival, ajustando
por localía:

    W_exp   = 1 / (1 + 10^(-((E_i + h·local_i) - (E_j + h·local_j)) / 400))
    g_adj   = beta·goles_reales + (1 - beta)·xG          (beta_eff = 1 si falta el xG)
    result  = 1 / (1 + exp(-(g_adj_i - g_adj_j) / s))
    perf    = K · (result - W_exp)
    F_i     = E_i + Σ_t w_t·perf_t / Σ_t w_t,   w_t = 0.5^((as_of - t).days / half_life)

Con `alpha = 1` y sin deltas se obtiene exactamente el modelo "puro" (≈ el de
@LaLigaenDirecto): `R_i = E_i`. Útil como línea base para `compare` y `backtest`.

Módulo de dominio puro: no hace IO ni red — para que sea testeable y
backtesteable. Importante para el backtest: `compute_strengths` solo debe ver
partidos con fecha <= `as_of` (sin data leakage); el caso de uso que lo llama es
responsable de filtrarlos.
"""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

from descenso.config import ModelConfig
from descenso.domain.match import Match, MatchStatus


@dataclass(frozen=True)
class StrengthSnapshot:
    """La fuerza efectiva de un equipo a una fecha, con sus componentes desglosados."""

    team: str
    as_of: dt.date
    elo_base: float  # E_i (último Elo de clubelo a la fecha)
    form_rating: float  # F_i (escala Elo, absoluto)
    n_form_matches: int  # cuántos partidos jugados alimentaron el form rating
    delta_coach: float  # Delta_coach(i): bonus por cambio de entrenador (decae)
    delta_injuries: float  # Delta_inj(i): ajuste manual por bajas
    alpha: float  # peso del Elo base frente al form rating (1.0 = modelo puro)
    delta_motivation: float = 0.0  # bonus por motivación contextual (última jornada)

    @property
    def form_component(self) -> float:
        """Aporte neto de la forma a R_eff: `(1 - alpha) · (F_i - E_i)`."""
        return (1.0 - self.alpha) * (self.form_rating - self.elo_base)

    @property
    def r_eff(self) -> float:
        """Fuerza efectiva final: `alpha·E + (1-alpha)·F + Delta_coach + Delta_inj + Delta_motivation`."""
        return (
            self.alpha * self.elo_base
            + (1.0 - self.alpha) * self.form_rating
            + self.delta_coach
            + self.delta_injuries
            + self.delta_motivation
        )

    def dominant_factor(self) -> str:
        """El factor (forma / entrenador / bajas / motivación) que más mueve `R_eff` frente al Elo puro.

        Devuelve '' si ninguno aporta nada (modelo equivalente al puro para este equipo).
        """
        candidates = {
            "forma": self.form_component,
            "cambio de entrenador": self.delta_coach,
            "bajas": self.delta_injuries,
            "motivación": self.delta_motivation,
        }
        best = max(candidates, key=lambda k: abs(candidates[k]))
        return best if abs(candidates[best]) > 1e-9 else ""


def compute_strengths(
    elo_base: dict[str, float],
    played_matches: list[Match],
    coach_changes: dict[str, list[tuple[dt.date, float | None]]],
    injury_adjustments: dict[str, float],
    as_of: dt.date,
    config: ModelConfig,
    motivation_bonuses: dict[str, float] | None = None,
) -> dict[str, StrengthSnapshot]:
    """Calcula la fuerza efectiva de cada equipo de `elo_base` a fecha `as_of`.

    - `played_matches`: partidos ya jugados (con marcador). Se ignoran los que no
      tengan fecha o cuya fecha sea posterior a `as_of` (protección anti-leakage).
    - `coach_changes`: `{team_id: [(fecha_cambio, elo_bump_o_None), ...]}`. Solo
      cuenta el cambio más reciente con fecha <= `as_of`; el bonus decae a 0 en
      `config.coach_bump_decay_matches` partidos jugados desde el cambio.
    - `injury_adjustments`: `{team_id: elo_delta}` vigente a `as_of` (lo resuelve
      el adaptador del fichero de bajas).

    Con `config.alpha == 1.0` y sin cambios/bajas el resultado es equivalente a
    usar solo `elo_base` (modelo puro).

    `motivation_bonuses`: `{team_id: elo_delta}` por motivación contextual (ej.
    bonus en última jornada para equipos luchando por salvación). Se suma como
    un delta adicional a la fuerza efectiva.
    """
    alpha = config.alpha
    half_life = config.form_half_life_days
    window = config.form_window_matches
    decay_matches = config.coach_bump_decay_matches

    # Partidos jugados, con fecha, no posteriores a as_of — agrupados por equipo.
    usable = [
        m
        for m in played_matches
        if m.status is MatchStatus.PLAYED and m.date is not None and m.date <= as_of
    ]
    by_team: dict[str, list[Match]] = {team_id: [] for team_id in elo_base}
    for m in usable:
        if m.home_team in by_team:
            by_team[m.home_team].append(m)
        if m.away_team in by_team:
            by_team[m.away_team].append(m)

    snapshots: dict[str, StrengthSnapshot] = {}
    for team_id, e_i in elo_base.items():
        team_matches = sorted(by_team[team_id], key=_match_date, reverse=True)

        recent = team_matches[:window]
        num = 0.0
        den = 0.0
        for m in recent:
            assert m.date is not None  # garantizado por el filtro `usable`
            age_days = (as_of - m.date).days
            w = math.pow(0.5, age_days / half_life)
            is_home = m.home_team == team_id
            elo_opp = elo_base.get(m.away_team if is_home else m.home_team, e_i)
            num += w * _performance_rating(m, is_home, e_i, elo_opp, config)
            den += w
        form_rating = e_i + (num / den) if den > 0.0 else e_i

        delta_coach = _coach_bump(
            coach_changes.get(team_id, []),
            team_matches,
            as_of,
            config.coach_bump_default,
            decay_matches,
        )
        delta_inj = injury_adjustments.get(team_id, 0.0)
        delta_mot = (motivation_bonuses or {}).get(team_id, 0.0)

        snapshots[team_id] = StrengthSnapshot(
            team=team_id,
            as_of=as_of,
            elo_base=e_i,
            form_rating=form_rating,
            n_form_matches=len(recent),
            delta_coach=delta_coach,
            delta_injuries=delta_inj,
            alpha=alpha,
            delta_motivation=delta_mot,
        )
    return snapshots


def effective_strengths(snapshots: dict[str, StrengthSnapshot]) -> dict[str, float]:
    """Atajo: `{team_id: r_eff}` a partir de los snapshots (lo que consume el simulador)."""
    return {team_id: snap.r_eff for team_id, snap in snapshots.items()}


def _match_date(match: Match) -> dt.date:
    """Fecha del partido (los call sites garantizan que no es None)."""
    assert match.date is not None
    return match.date


def _performance_rating(
    match: Match, team_is_home: bool, elo_team: float, elo_opp: float, config: ModelConfig
) -> float:
    """`perf = K · (result_adj - W_exp)` para el equipo indicado en este partido."""
    h = config.home_advantage_elo
    eff_team = elo_team + (h if team_is_home else 0.0)
    eff_opp = elo_opp + (0.0 if team_is_home else h)
    # Clip de la diferencia a ±1000 para no desbordar 10^(x/400) con valores absurdos.
    diff = max(-1000.0, min(1000.0, eff_team - eff_opp))
    w_exp = 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))

    if team_is_home:
        goals_for, goals_against = match.home_goals, match.away_goals
        xg_for, xg_against = match.home_xg, match.away_xg
    else:
        goals_for, goals_against = match.away_goals, match.home_goals
        xg_for, xg_against = match.away_xg, match.home_xg
    # `usable` garantiza que el partido está jugado → goles no son None.
    assert goals_for is not None and goals_against is not None

    if xg_for is None or xg_against is None:
        adj_for, adj_against = float(goals_for), float(goals_against)
    else:
        beta = config.xg_blend_beta
        adj_for = beta * goals_for + (1.0 - beta) * xg_for
        adj_against = beta * goals_against + (1.0 - beta) * xg_against

    result_adj = 1.0 / (1.0 + math.exp(-(adj_for - adj_against) / config.form_goal_diff_scale))
    return config.form_k_factor * (result_adj - w_exp)


def _coach_bump(
    changes: list[tuple[dt.date, float | None]],
    team_played_matches: list[Match],
    as_of: dt.date,
    default_bump: float,
    decay_matches: int,
) -> float:
    """Bonus Elo del cambio de entrenador más reciente con fecha <= as_of, ya decaído.

    Decae linealmente a 0 a lo largo de `decay_matches` partidos jugados *después*
    del cambio. No se acumulan varios cambios: solo cuenta el último.
    """
    applicable = [(d, b) for (d, b) in changes if d <= as_of]
    if not applicable:
        return 0.0
    change_date, raw_bump = max(applicable, key=lambda db: db[0])
    bump = default_bump if raw_bump is None else raw_bump
    played_since = sum(
        1 for m in team_played_matches if m.date is not None and change_date < m.date <= as_of
    )
    if played_since >= decay_matches:
        return 0.0
    return bump * (1.0 - played_since / decay_matches)
