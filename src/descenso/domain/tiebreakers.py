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
  6) Fair play / sorteo. Aquí: sorteo determinista con la `seed`.
"""

from __future__ import annotations

from collections.abc import Sequence

from descenso.domain.match import Match
from descenso.domain.standings import TeamRow


def resolve_order(
    rows: Sequence[TeamRow],
    played_matches: Sequence[Match],
    rng_seed: int | None = None,
) -> list[TeamRow]:
    """Devuelve `rows` ordenados de mejor a peor según las reglas de LaLiga."""
    raise NotImplementedError  # Fase 6
