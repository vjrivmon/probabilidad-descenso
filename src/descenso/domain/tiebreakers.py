"""Reglas de desempate de LaLiga.

Orden oficial (art. 200 del Reglamento de LaLiga):
  1) Mayor número de puntos.
  2) Si dos equipos empatan: puntos en los enfrentamientos directos; luego
     diferencia de goles en los directos.
  3) Si tres o más equipos empatan: se construye una "mini-liga" SOLO con los
     partidos entre los empatados (puntos -> diferencia de goles en esa mini-liga);
     al resolver uno, los demás pueden seguir empatados -> se repite el proceso.
  4) Diferencia de goles general.
  5) Mayor número de goles a favor general.
  6) Fair play / sorteo. Aquí: sorteo determinista por id de equipo (estable y
     reproducible; `rng_seed` se acepta por compatibilidad pero el desempate por
     sorteo real es tan improbable a final de liga que no se aleatoriza).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from descenso.domain.match import Match, MatchStatus
from descenso.domain.standings import TeamRow


def _played(matches: Sequence[Match]) -> list[Match]:
    return [m for m in matches if m.status is MatchStatus.PLAYED]


def _h2h_subtable(teams: set[str], matches: Sequence[Match]) -> dict[str, tuple[int, int, int]]:
    """Para cada equipo de `teams`: (puntos, dif. de goles, goles a favor) contando
    SOLO los partidos jugados entre equipos de `teams`."""
    pts = dict.fromkeys(teams, 0)
    gd = dict.fromkeys(teams, 0)
    gf = dict.fromkeys(teams, 0)
    for m in matches:
        if m.home_team not in teams or m.away_team not in teams:
            continue
        assert m.home_goals is not None and m.away_goals is not None
        hg, ag = m.home_goals, m.away_goals
        gd[m.home_team] += hg - ag
        gd[m.away_team] += ag - hg
        gf[m.home_team] += hg
        gf[m.away_team] += ag
        if hg > ag:
            pts[m.home_team] += 3
        elif hg < ag:
            pts[m.away_team] += 3
        else:
            pts[m.home_team] += 1
            pts[m.away_team] += 1
    return {t: (pts[t], gd[t], gf[t]) for t in teams}


def _partition(items: list[str], key: Callable[[str], Any]) -> list[list[str]]:
    """Ordena `items` de mayor a menor `key` y los agrupa por `key` igual."""
    groups: list[list[str]] = []
    for t in sorted(items, key=key, reverse=True):
        if groups and key(groups[-1][0]) == key(t):
            groups[-1].append(t)
        else:
            groups.append([t])
    return groups


def resolve_order(
    rows: Sequence[TeamRow],
    played_matches: Sequence[Match],
    rng_seed: int | None = None,
) -> list[TeamRow]:
    """Devuelve `rows` ordenados de mejor a peor según las reglas de LaLiga."""
    row_by_team = {r.team: r for r in rows}
    if len(row_by_team) != len(rows):
        raise ValueError("hay equipos repetidos en la clasificación")
    matches = _played(played_matches)

    def general_key(team: str) -> tuple[int, int, int, str]:
        r = row_by_team[team]
        # mejor primero -> negamos lo "más grande es mejor"; el id desempata al alza
        return (-r.total_points, -r.gd, -r.gf, team)

    def resolve_tied(teams: list[str]) -> list[str]:
        """`teams` están todos empatados a puntos totales: resolver por h2h / mini-liga."""
        if len(teams) == 1:
            return teams
        sub = _h2h_subtable(set(teams), matches)
        if len(teams) == 2:
            a, b = teams
            ka, kb = sub[a][:2], sub[b][:2]  # (pts h2h, dif. goles h2h)
            if ka != kb:
                return [a, b] if ka > kb else [b, a]
            return sorted(teams, key=general_key)
        # tres o más: mini-liga -> puntos -> diferencia de goles en la mini-liga
        partitions = _partition(teams, key=lambda t: sub[t][:2])
        if len(partitions) == 1:
            # la mini-liga no separó a nadie -> caer a la clasificación general
            return sorted(teams, key=general_key)
        ordered: list[str] = []
        for part in partitions:
            ordered.extend(part if len(part) == 1 else resolve_tied(part))
        return ordered

    result: list[str] = []
    for group in _partition(list(row_by_team), key=lambda t: row_by_team[t].total_points):
        result.extend(group if len(group) == 1 else resolve_tied(group))
    return [row_by_team[t] for t in result]


# ---------------------------------------------------------------------------
# Versiones precomputadas para el simulador vectorizado (sin h2h recursivo)
# ---------------------------------------------------------------------------

def precompute_h2h(
    team_ids: list[str],
    played_matches: Sequence[Match],
) -> dict[tuple[str, str], tuple[int, int, int]]:
    """Precomputa los resultados h2h entre todos los pares de equipos.

    Devuelve `{(team_a, team_b): (pts_a, gd_a, gf_a)}` donde los valores son
    para `team_a` frente a `team_b` (solo partidos jugados entre ambos).
    """
    h2h: dict[tuple[str, str], tuple[int, int, int]] = {}
    for t1 in team_ids:
        for t2 in team_ids:
            if t1 != t2:
                h2h[(t1, t2)] = (0, 0, 0)

    for m in _played(played_matches):
        h, a = m.home_team, m.away_team
        if h not in set(team_ids) or a not in set(team_ids):
            continue
        hg, ag = m.home_goals, m.away_goals
        assert hg is not None and ag is not None

        # Actualizar registros de h2h para ambos equipos
        pts_h, gd_h, gf_h = h2h[(h, a)]
        pts_a, gd_a, gf_a = h2h[(a, h)]

        gf_h += hg
        gf_a += ag
        gd_h += hg - ag
        gd_a += ag - hg

        if hg > ag:
            pts_h += 3
        elif hg < ag:
            pts_a += 3
        else:
            pts_h += 1
            pts_a += 1

        h2h[(h, a)] = (pts_h, gd_h, gf_h)
        h2h[(a, h)] = (pts_a, gd_a, gf_a)

    return h2h


def build_h2h_lookup(
    team_ids: list[str],
    h2h_data: dict[tuple[str, str], tuple[int, int, int]],
) -> dict[str, dict[str, tuple[int, int, int]]]:
    """Convierte el formato de precompute_h2h a un lookup anidado.

    Devuelve `{team_a: {team_b: (pts, gd, gf)}}` para acceso rápido.
    """
    lookup: dict[str, dict[str, tuple[int, int, int]]] = {
        t: {} for t in team_ids
    }
    for (t1, t2), val in h2h_data.items():
        lookup[t1][t2] = val
    return lookup
