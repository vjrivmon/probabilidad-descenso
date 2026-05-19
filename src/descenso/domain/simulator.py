"""Simulador Monte Carlo del calendario restante (vectorizado con numpy)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from descenso.domain.match import Match
from descenso.domain.match_model import MatchModel
from descenso.domain.probabilities import RelegationProbabilities, TeamProbabilities
from descenso.domain.standings import TeamRow
from descenso.domain.tiebreakers import build_h2h_lookup, precompute_h2h

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


def _resolve_tiebreaker_with_h2h(
    sim_idx: int,
    pts_row: np.ndarray,
    gf_row: np.ndarray,
    ga_row: np.ndarray,
    team_ids: list[str],
    idx: dict[str, int],
    h2h_lookup: dict[str, dict[str, tuple[int, int, int]]],
) -> np.ndarray:
    """Resuelve el orden de una simulación usando desempates h2h de LaLiga.

    Devuelve un array con la posición final (1 = mejor) de cada equipo.
    """
    n_teams = len(team_ids)

    # Crear lista de (team, pts, gd, gf) para ordenar
    rows = []
    for i, tid in enumerate(team_ids):
        rows.append((tid, int(pts_row[i]), int(gf_row[i] - ga_row[i]), int(gf_row[i])))

    # Ordenar por puntos (descendente), luego recursivamente desempatar
    def sort_with_tiebreak(team_rows):
        if len(team_rows) <= 1:
            return team_rows

        # Agrupar por puntos
        by_pts = defaultdict(list)
        for tr in team_rows:
            by_pts[tr[1]].append(tr)

        result = []
        for pts_val in sorted(by_pts.keys(), reverse=True):
            group = by_pts[pts_val]
            if len(group) == 1:
                result.append(group[0])
                continue

            # Empate a puntos: resolver con mini-liga h2h
            team_names = [tr[0] for tr in group]
            if len(team_names) == 2:
                a, b = team_names
                pts_a, gd_a, gf_a = h2h_lookup.get(a, {}).get(b, (0, 0, 0))
                pts_b, gd_b, gf_b = h2h_lookup.get(b, {}).get(a, (0, 0, 0))
                if pts_a != pts_b:
                    if pts_a > pts_b:
                        result.extend([tr for tr in group if tr[0] == a])
                        result.extend([tr for tr in group if tr[0] == b])
                    else:
                        result.extend([tr for tr in group if tr[0] == b])
                        result.extend([tr for tr in group if tr[0] == a])
                elif gd_a != gd_b:
                    if gd_a > gd_b:
                        result.extend([tr for tr in group if tr[0] == a])
                        result.extend([tr for tr in group if tr[0] == b])
                    else:
                        result.extend([tr for tr in group if tr[0] == b])
                        result.extend([tr for tr in group if tr[0] == a])
                else:
                    # Empate total: usar gd general, luego gf, luego id
                    result.extend(sorted(group, key=lambda tr: (-tr[2], -tr[3], tr[0])))
            else:
                # 3+ equipos empatados: mini-liga
                sub = {}
                for t in team_names:
                    sub_pts, sub_gd, sub_gf = 0, 0, 0
                    for opp in team_names:
                        if opp == t:
                            continue
                        h2h_pts, h2h_gd, h2h_gf = h2h_lookup.get(t, {}).get(opp, (0, 0, 0))
                        sub_pts += h2h_pts
                        sub_gd += h2h_gd
                        sub_gf += h2h_gf
                    sub[t] = (sub_pts, sub_gd, sub_gf)

                # Particionar por (pts_h2h, gd_h2h)
                sub_groups = defaultdict(list)
                for tr in group:
                    t = tr[0]
                    key = (sub[t][0], sub[t][1])
                    sub_groups[key].append(tr)

                sorted_keys = sorted(sub_groups.keys(), key=lambda k: (-k[0], -k[1]))
                for key in sorted_keys:
                    sub_group = sub_groups[key]
                    if len(sub_group) == 1:
                        result.append(sub_group[0])
                    else:
                        # Empate persistente en mini-liga: usar gd general
                        result.extend(sorted(sub_group, key=lambda tr: (-tr[2], -tr[3], tr[0])))

        return result

    sorted_rows = sort_with_tiebreak(rows)

    # Asignar posiciones
    positions = np.zeros(n_teams, dtype=np.int64)
    for pos, tr in enumerate(sorted_rows, start=1):
        i = idx[tr[0]]
        positions[i] = pos

    return positions


def run_monte_carlo(
    team_ids: list[str],
    base_table: list[TeamRow],
    remaining_matches: list[Match],
    strengths: dict[str, float],
    match_model: MatchModel,
    config: SimulationConfig,
    played_matches: list[Match] | None = None,
) -> RelegationProbabilities:
    """Corre `config.n_sims` simulaciones del calendario restante.

    Para cada iteración: respeta los partidos con resultado fijado (`is_fixed`),
    muestrea el resto con `match_model`, construye la clasificación final usando
    desempates h2h de LaLiga y registra qué equipos caen en las últimas
    `n_relegation` plazas. Devuelve las probabilidades agregadas por equipo.

    Si se pasa `played_matches`, se usa para desempates h2h (recomendado para
    la última jornada cuando hay muchos empatados).
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

    # --- Desempate ---
    if played_matches is not None:
        # Desempate h2h completo (más lento pero correcto)
        h2h_data = precompute_h2h(team_ids, played_matches)
        h2h_lookup = build_h2h_lookup(team_ids, h2h_data)

        final_pos = np.empty((n_sims, n_teams), dtype=np.int64)
        for sim_i in range(n_sims):
            pos = _resolve_tiebreaker_with_h2h(
                sim_i, pts[sim_i], gf[sim_i], ga[sim_i],
                team_ids, idx, h2h_lookup,
            )
            final_pos[sim_i] = pos
    else:
        # Desempate rápido por (pts, gd, gf) — aproximación
        gd = gf - ga
        sort_key = (pts * _GD_SPAN + (gd + _GD_OFFSET)) * _GF_SPAN + gf
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
