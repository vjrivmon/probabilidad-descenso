"""Factor de motivación contextual para el último tramo de temporada.

Analiza la clasificación actual y los partidos restantes para determinar cuánto
"le importa" ganar a cada equipo. Se expresa como un bonus en puntos Elo que
se suma a la fuerza efectiva.

Categorías:
- eliminado: fuera de toda lucha matemática -> 0
- sin_objetivo: ya salvado / ya sin opciones de Europa -> 0
- lucha_salvacion: puede descender pero no está en zona -> boost moderado
- zona_descenso: en puestos de descenso -> boost alto
- lucha_europa: puede ganar/perder Europa -> boost moderado-alto

El cálculo es determinista y no depende del RNG de la simulación.
"""

from __future__ import annotations

from dataclasses import dataclass

from descenso.domain.standings import TeamRow

# Posiciones objetivo (LaLiga: top 4 UCL, 5 EL, 6 UECL)
_UCL_TOP = 4
_EL_TOP = 5
_UECL_TOP = 6
_RELEGATION_BOTTOM = 18  # puestos 18-20 descienden


@dataclass(frozen=True)
class MotivationInfo:
    """Resultado del cálculo de motivación para un equipo."""

    team: str
    category: str
    bonus_elo: float
    reason: str


def compute_motivation(
    standings: list[TeamRow],
    remaining_by_team: dict[str, int],
    n_relegation: int = 3,
) -> dict[str, MotivationInfo]:
    """Calcula el bonus de motivación para cada equipo.

    - `standings`: clasificación actual (ordenada por puntos).
    - `remaining_by_team`: `{team_id: nº de partidos que le quedan}`.
    - `n_relegation`: plazas de descenso (3 en LaLiga).

    Devuelve `{team_id: MotivationInfo}`.
    """
    n_teams = len(standings)
    rel_zone_start = n_teams - n_relegation  # posición 18 (0-indexed: 17)
    europa_zone_end = _UECL_TOP  # posiciones 1-6

    # Puntos máxima alcanzable por cada equipo
    max_extra = {}
    for r in standings:
        rm = remaining_by_team.get(r.team, 0)
        max_extra[r.team] = r.total_points + rm * 3

    # El punto mínimo para salvarse es el de la posición justo encima del descenso
    # (simplificación: usamos los puntos del equipo en posición rel_zone_start)
    if rel_zone_start < len(standings):
        safety_threshold = standings[rel_zone_start].total_points
    else:
        safety_threshold = 0

    results: dict[str, MotivationInfo] = {}

    for i, r in enumerate(standings):
        pos = i + 1  # 1-indexed
        team = r.team
        pts = r.total_points
        rm = remaining_by_team.get(team, 0)
        max_pts = max_extra[team]

        # --- ELIMINADO (sin posibilidad matemática) ---
        # No puede alcanzar ni la salvación ni Europa
        min_salvacion = safety_threshold
        if max_pts < min_salvacion and max_pts < standings[0].total_points:
            # Si ya no puede ni salvarse ni ganar nada -> eliminado
            # Pero verificamos: si está en zona de descenso y no puede salvarse -> eliminado
            if pos > rel_zone_start:
                # Ya en zona de descenso, no puede salir
                results[team] = MotivationInfo(
                    team=team,
                    category="eliminado",
                    bonus_elo=0.0,
                    reason="eliminado matemáticamente",
                )
                continue
            # Si está fuera de zona pero no puede alcanzar a nadie arriba
            can_reach_europa = max_pts >= (standings[europa_zone_end - 1].total_points if europa_zone_end <= n_teams else 999)
            if not can_reach_europa:
                results[team] = MotivationInfo(
                    team=team,
                    category="sin_objetivo",
                    bonus_elo=0.0,
                    reason="sin opciones europeas ni de descenso",
                )
                continue

        # --- ZONA DE DESCENSO (posiciones 18-20) ---
        if pos > rel_zone_start:
            # Puede salir si gana y otros pierden
            can_exit = max_pts >= min_salvacion
            if can_exit:
                results[team] = MotivationInfo(
                    team=team,
                    category="zona_descenso",
                    bonus_elo=40.0,
                    reason=f"en zona de descenso (p{pos}), necesita resultados",
                )
            else:
                results[team] = MotivationInfo(
                    team=team,
                    category="eliminado",
                    bonus_elo=5.0,  # mínimo: jugando el orgullo
                    reason="en zona de descenso, sin posibilidad de salida",
                )
            continue

        # --- LUCHA POR LA SALVACIÓN (fuera de zona pero cerca) ---
        margin = pts - safety_threshold
        if margin <= 3 and rm > 0:
            # Está a 0-3 puntos de la zona -> alta motivación
            bonus = 30.0 if margin <= 1 else 20.0 if margin <= 2 else 10.0
            results[team] = MotivationInfo(
                team=team,
                category="lucha_salvacion",
                bonus_elo=bonus,
                reason=f"a {margin} pts de zona de descenso",
            )
            continue

        # --- LUCHA POR EUROPA ---
        in_europa_now = pos <= europa_zone_end
        can_reach_europa_now = max_pts >= (
            standings[europa_zone_end - 1].total_points
            if europa_zone_end <= n_teams
            else 999
        )

        if in_europa_now and rm > 0:
            # Puede perder la plaza
            # Cuántos puntos le separan del que viene detrás
            if europa_zone_end < n_teams:
                below_europa = standings[europa_zone_end].total_points
                gap = pts - below_europa
                if gap <= 3:
                    bonus = 25.0 if gap <= 1 else 15.0
                    results[team] = MotivationInfo(
                        team=team,
                        category="lucha_europa",
                        bonus_elo=bonus,
                        reason=f"defendiendo plaza europea (a {gap} pts del 7º)",
                    )
                    continue

        if not in_europa_now and can_reach_europa_now and rm > 0:
            # Puede entrar en Europa
            above = standings[europa_zone_end - 1].total_points
            gap = above - pts
            if gap <= 6:
                bonus = 20.0 if gap <= 3 else 10.0
                results[team] = MotivationInfo(
                    team=team,
                    category="lucha_europa",
                    bonus_elo=bonus,
                    reason=f"luchando por Europa (a {gap} pts del top 6)",
                )
                continue

        # --- SIN OBJETIVO (ya salvado, sin Europa cercana) ---
        results[team] = MotivationInfo(
            team=team,
            category="sin_objetivo",
            bonus_elo=0.0,
            reason="salvado / sin opciones europeas",
        )

    return results
