"""Construcción de la clasificación a partir de los partidos jugados."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from descenso.domain.match import Match, MatchStatus


@dataclass(frozen=True)
class TeamRow:
    team: str
    played: int
    won: int
    drawn: int
    lost: int
    gf: int
    ga: int
    points: int
    points_adjustment: int = 0  # sanciones administrativas (raro)

    @property
    def gd(self) -> int:
        return self.gf - self.ga

    @property
    def total_points(self) -> int:
        return self.points + self.points_adjustment


def build_table(
    team_ids: Iterable[str],
    matches: Iterable[Match],
    points_adjustments: dict[str, int] | None = None,
) -> list[TeamRow]:
    """Construye la tabla recomputándola desde los partidos jugados.

    Nunca se confía en una clasificación scrapeada como verdad: se calcula aquí
    a partir de los resultados (más, si los hay, ajustes administrativos de puntos).
    """
    ids = list(team_ids)
    known = set(ids)
    adjustments = dict(points_adjustments or {})

    unknown_adj = set(adjustments) - known
    if unknown_adj:
        raise ValueError(f"ajustes de puntos para equipos desconocidos: {sorted(unknown_adj)}")

    acc: dict[str, dict[str, int]] = {
        t: {"played": 0, "won": 0, "drawn": 0, "lost": 0, "gf": 0, "ga": 0, "points": 0}
        for t in ids
    }

    for m in matches:
        if m.status is not MatchStatus.PLAYED:
            continue
        if m.home_team not in known or m.away_team not in known:
            missing = sorted({m.home_team, m.away_team} - known)
            raise ValueError(
                f"el partido (jornada {m.gameweek}) {m.home_team} vs {m.away_team} referencia "
                f"equipos fuera de la liga: {missing}"
            )
        assert m.home_goals is not None and m.away_goals is not None  # garantizado por status
        hg, ag = m.home_goals, m.away_goals
        h, a = acc[m.home_team], acc[m.away_team]
        h["played"] += 1
        a["played"] += 1
        h["gf"] += hg
        h["ga"] += ag
        a["gf"] += ag
        a["ga"] += hg
        if hg > ag:
            h["won"] += 1
            h["points"] += 3
            a["lost"] += 1
        elif hg < ag:
            a["won"] += 1
            a["points"] += 3
            h["lost"] += 1
        else:
            h["drawn"] += 1
            a["drawn"] += 1
            h["points"] += 1
            a["points"] += 1

    return [
        TeamRow(
            team=t,
            played=acc[t]["played"],
            won=acc[t]["won"],
            drawn=acc[t]["drawn"],
            lost=acc[t]["lost"],
            gf=acc[t]["gf"],
            ga=acc[t]["ga"],
            points=acc[t]["points"],
            points_adjustment=adjustments.get(t, 0),
        )
        for t in ids
    ]


def order_table(rows: Iterable[TeamRow], played_matches: Iterable[Match]) -> list[TeamRow]:
    """Ordena aplicando los desempates de LaLiga (ver `tiebreakers`)."""
    from descenso.domain.tiebreakers import resolve_order

    return resolve_order(list(rows), list(played_matches))
