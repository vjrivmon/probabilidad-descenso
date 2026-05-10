"""Construcción de la clasificación a partir de los partidos jugados."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from descenso.domain.match import Match


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
    raise NotImplementedError  # Fase 6


def order_table(rows: Iterable[TeamRow], played_matches: Iterable[Match]) -> list[TeamRow]:
    """Ordena aplicando los desempates de LaLiga (ver `tiebreakers`)."""
    raise NotImplementedError  # Fase 6
