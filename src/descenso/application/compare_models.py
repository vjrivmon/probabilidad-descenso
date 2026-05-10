"""Caso de uso: comparar el modelo puro (solo Elo) con el ajustado (Elo + forma + ...)."""

from __future__ import annotations

from dataclasses import dataclass

from descenso.application.build_strengths import StrengthBuildResult, build_strengths
from descenso.application.run_simulation import (
    load_inputs,
    run_simulation,
)
from descenso.config import AppConfig, ModelConfig


@dataclass(frozen=True)
class ComparisonRow:
    team: str
    p_pure: float
    p_adjusted: float
    delta: float  # p_adjusted - p_pure (en puntos porcentuales)
    note: str  # factor responsable del cambio (forma / xG / entrenador / bajas)


def compare_models(
    config: AppConfig, n_sims: int | None = None, seed: int | None = None
) -> list[ComparisonRow]:
    """Corre las dos variantes del modelo con la misma seed y devuelve la tabla comparativa.

    Si `seed` es None, se genera una seed determinista a partir de la temporada y
    la fecha para que la comparación sea reproducible en el mismo día pero distinta
    entre temporadas. Ambos modelos usan la misma seed para que la comparación sea
    justa (no interviene la varianza Monte Carlo).

    Devuelve la lista ordenada por `p_adjusted` descendente.
    """
    if seed is None:
        seed = _default_seed(config.season)

    # Cargamos los datos una sola vez para ambos modelos
    inputs = load_inputs(config, prefer_cache=True)

    # Config del modelo puro (alpha=1.0, sin deltas)
    pure_config = config.model_copy(
        update={"model": ModelConfig(**{**config.model.model_dump(), "model_type": "pure"})}
    )

    # Config del modelo ajustado (tal como está en config)
    adj_config = config.model_copy(
        update={"model": ModelConfig(**{**config.model.model_dump(), "model_type": "adjusted"})}
    )

    # Cargamos el build_result del modelo ajustado para reutilizarlo en compare
    adj_build: StrengthBuildResult = build_strengths(adj_config, prefer_cache=True)

    # Simulaciones con la misma seed y los mismos inputs
    outcome_pure = run_simulation(
        pure_config,
        n_sims=n_sims,
        seed=seed,
        inputs=inputs,
        prefer_cache=True,
    )
    outcome_adj = run_simulation(
        adj_config,
        n_sims=n_sims,
        seed=seed,
        inputs=inputs,
        prefer_cache=True,
        _build_result=adj_build,
    )

    p_pure_map = {tp.team: tp.p_relegation for tp in outcome_pure.probabilities.teams}
    p_adj_map = {tp.team: tp.p_relegation for tp in outcome_adj.probabilities.teams}

    rows: list[ComparisonRow] = []
    for team_id in p_adj_map:
        p_pure = p_pure_map.get(team_id, 0.0)
        p_adj = p_adj_map[team_id]
        delta = (p_adj - p_pure) * 100.0  # en puntos porcentuales

        note = ""
        if abs(delta) >= 3.0:
            snap = adj_build.snapshots.get(team_id)
            if snap is not None:
                factor = snap.dominant_factor()
                if factor:
                    sign = "+" if snap.r_eff > snap.elo_base else "-"
                    note = f"{factor} ({sign}) " f"R={snap.r_eff:.0f} vs Elo={snap.elo_base:.0f}"
                else:
                    note = "sin ajuste dominante"

        rows.append(
            ComparisonRow(
                team=team_id,
                p_pure=p_pure,
                p_adjusted=p_adj,
                delta=delta,
                note=note,
            )
        )

    # Ordenar por p_adjusted descendente
    rows.sort(key=lambda r: r.p_adjusted, reverse=True)
    return rows


def _default_seed(season: int) -> int:
    """Seed determinista para una temporada: mismo resultado en el mismo día."""
    import datetime as dt

    today = dt.date.today()
    # Combina temporada y día del año para que sea reproducible
    return int(season * 1000 + today.timetuple().tm_yday) % (2**31)
