"""Simulador Monte Carlo del calendario restante (vectorizado con numpy)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from descenso.domain.match import Match
from descenso.domain.match_model import MatchModel
from descenso.domain.probabilities import RelegationProbabilities, TeamProbabilities
from descenso.domain.standings import TeamRow

# Cotas para empaquetar (puntos, dif. de goles, goles a favor) en una sola clave
# entera y poder hacer un único `argsort` por simulación. Holgadas para 38 jornadas
# (goles por partido acotados a 20 por el validador de `Match`).
_GD_OFFSET = 1_000  # la dif. de goles puede ser negativa
_GD_SPAN = 2_000  # > max(gd + offset)
_GF_SPAN = 1_000  # > max(gf) en una temporada


@dataclass
class SimulationConfig:
    n_sims: int = 100_000
    n_relegation: int = 3  # plazas de descenso en LaLiga
    seed: int | None = None


def run_monte_carlo(
    team_ids: list[str],
    base_table: list[TeamRow],
    remaining_matches: list[Match],
    strengths: dict[str, float],
    match_model: MatchModel,
    config: SimulationConfig,
) -> RelegationProbabilities:
    """Corre `config.n_sims` simulaciones del calendario restante.

    Para cada iteración: respeta los partidos con resultado fijado (`is_fixed`),
    muestrea el resto con `match_model`, construye la clasificación final y
    registra qué equipos caen en las últimas `n_relegation` plazas. Devuelve las
    probabilidades agregadas por equipo.

    Nota sobre los desempates: el ranking por simulación usa puntos -> diferencia
    de goles general -> goles a favor (las reglas exactas con enfrentamientos
    directos / mini-liga viven en `domain.tiebreakers.resolve_order`; aplicarlas
    por simulación no es vectorizable y su efecto sobre P(descenso) es marginal).
    """
    if config.n_sims <= 0:
        raise ValueError(f"n_sims debe ser > 0, es {config.n_sims}")
    n_teams = len(team_ids)
    if n_teams == 0:
        raise ValueError("no hay equipos que simular")

    idx = {t: i for i, t in enumerate(team_ids)}
    if len(idx) != n_teams:
        raise ValueError("hay equipos repetidos en team_ids")

    row_by_team = {r.team: r for r in base_table}
    missing = set(team_ids) - set(row_by_team)
    if missing:
        raise ValueError(f"la tabla base no cubre a estos equipos: {sorted(missing)}")

    n_sims = config.n_sims
    rng = np.random.default_rng(config.seed)

    base_pts = np.zeros(n_teams, dtype=np.int64)
    base_gf = np.zeros(n_teams, dtype=np.int64)
    base_ga = np.zeros(n_teams, dtype=np.int64)
    for t in team_ids:
        r = row_by_team[t]
        i = idx[t]
        base_pts[i] = r.total_points
        base_gf[i] = r.gf
        base_ga[i] = r.ga

    pts = np.tile(base_pts, (n_sims, 1))
    gf = np.tile(base_gf, (n_sims, 1))
    ga = np.tile(base_ga, (n_sims, 1))

    for m in remaining_matches:
        if m.home_team not in idx or m.away_team not in idx:
            bad = sorted({m.home_team, m.away_team} - set(idx))
            raise ValueError(f"partido pendiente con equipos fuera de la liga: {bad}")
        h, a = idx[m.home_team], idx[m.away_team]
        if m.home_goals is not None and m.away_goals is not None:
            hg = np.full(n_sims, m.home_goals, dtype=np.int64)
            ag = np.full(n_sims, m.away_goals, dtype=np.int64)
        else:
            if m.home_team not in strengths or m.away_team not in strengths:
                bad = sorted({m.home_team, m.away_team} - set(strengths))
                raise ValueError(f"falta la fuerza de: {bad}")
            hs = np.full(n_sims, float(strengths[m.home_team]))
            as_ = np.full(n_sims, float(strengths[m.away_team]))
            hg, ag = match_model.sample_scores(hs, as_, rng)
            hg = np.asarray(hg, dtype=np.int64)
            ag = np.asarray(ag, dtype=np.int64)

        gf[:, h] += hg
        ga[:, h] += ag
        gf[:, a] += ag
        ga[:, a] += hg
        home_win = hg > ag
        away_win = ag > hg
        draw = ~home_win & ~away_win
        pts[:, h] += np.where(home_win, 3, np.where(draw, 1, 0))
        pts[:, a] += np.where(away_win, 3, np.where(draw, 1, 0))

    gd = gf - ga
    sort_key = (pts * _GD_SPAN + (gd + _GD_OFFSET)) * _GF_SPAN + gf
    # de mejor a peor -> orden descendente; estable para que el "sorteo" sea reproducible
    order = np.argsort(-sort_key, axis=1, kind="stable")
    final_pos = np.empty((n_sims, n_teams), dtype=np.int64)
    rows_ix = np.arange(n_sims)[:, None]
    final_pos[rows_ix, order] = np.arange(1, n_teams + 1)[None, :]

    cutoff = n_teams - config.n_relegation
    relegated = final_pos > cutoff
    p_relegation = relegated.mean(axis=0)
    expected_points = pts.mean(axis=0)
    expected_position = final_pos.mean(axis=0)

    teams_out: list[TeamProbabilities] = []
    for t in team_ids:
        i = idx[t]
        positions, counts = np.unique(final_pos[:, i], return_counts=True)
        p_by_position = {int(p): float(c) / n_sims for p, c in zip(positions, counts, strict=True)}
        teams_out.append(
            TeamProbabilities(
                team=t,
                p_relegation=float(p_relegation[i]),
                p_by_position=p_by_position,
                expected_points=float(expected_points[i]),
                expected_position=float(expected_position[i]),
            )
        )

    return RelegationProbabilities(n_sims=n_sims, teams=teams_out, seed=config.seed)
