"""Tests de `compare_models` (CP2).

Como compare_models depende de IO (carga datos reales), la estrategia es:
1. Testear la lógica pura de comparación usando mocks de las funciones IO.
2. Testear la estructura del resultado (ComparisonRow) y el ordenado.
3. Testear la reproducibilidad (misma seed -> mismos resultados).
4. Testear el umbral del 3pp para las notas.

No tocamos la red real. Usamos unittest.mock para parchear load_inputs,
build_strengths y run_simulation.
"""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

from descenso.application.build_strengths import StrengthBuildResult
from descenso.application.compare_models import (
    ComparisonRow,
    _default_seed,
    compare_models,
)
from descenso.config import AppConfig, ModelConfig
from descenso.domain.match import Match
from descenso.domain.probabilities import RelegationProbabilities, TeamProbabilities
from descenso.domain.strength_model import StrengthSnapshot
from descenso.domain.team import Team

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_TODAY = dt.date(2026, 5, 10)
_TEAMS = ["equipo-a", "equipo-b", "equipo-c", "equipo-d", "equipo-e", "equipo-f"]


def _tp(team: str, p_rel: float) -> TeamProbabilities:
    return TeamProbabilities(
        team=team,
        p_relegation=p_rel,
        p_by_position={1: 0.0},
        expected_points=30.0,
        expected_position=3.0,
    )


def _rel_probs(teams_p: dict[str, float]) -> RelegationProbabilities:
    return RelegationProbabilities(
        n_sims=100,
        teams=[_tp(t, p) for t, p in teams_p.items()],
        seed=42,
    )


def _snap(
    team: str,
    elo: float = 1500.0,
    form: float = 1500.0,
    delta_coach: float = 0.0,
    delta_inj: float = 0.0,
) -> StrengthSnapshot:
    return StrengthSnapshot(
        team=team,
        as_of=_TODAY,
        elo_base=elo,
        form_rating=form,
        n_form_matches=5,
        delta_coach=delta_coach,
        delta_injuries=delta_inj,
        alpha=0.5,
    )


def _build_result(snapshots: dict[str, StrengthSnapshot]) -> StrengthBuildResult:
    return StrengthBuildResult(
        snapshots=snapshots,
        xg_available=True,
        n_coach_changes_applied=0,
        notes=[],
    )


def _sim_inputs(teams: list[str]) -> object:
    """Crea un SimulationInputs sintético."""
    team_objs = [Team(id=t, name=t) for t in teams]
    elo = dict.fromkeys(teams, 1500.0)
    matches: list[Match] = []
    # Creamos un SimulationInputs con el dataclass real
    from descenso.application.run_simulation import SimulationInputs

    return SimulationInputs(teams=team_objs, elo=elo, matches=matches)


def _sim_outcome(probs: RelegationProbabilities) -> object:
    """Crea un SimulationOutcome sintético."""
    from descenso.application.run_simulation import SimulationOutcome

    team_objs = [Team(id=t.team, name=t.team) for t in probs.teams]
    return SimulationOutcome(
        season=2025,
        teams=team_objs,
        n_played=0,
        n_pending=0,
        model_type="adjusted",
        probabilities=probs,
        applied_fixed=[],
        ignored_fixed=[],
        notes=[],
    )


def _cfg() -> AppConfig:
    return AppConfig(model=ModelConfig(alpha=0.5, model_type="adjusted", n_sims=100))


# --------------------------------------------------------------------------- #
# _default_seed
# --------------------------------------------------------------------------- #


def test_default_seed_es_determinista_para_misma_temporada() -> None:
    """Misma temporada -> misma seed (en el mismo día)."""
    s1 = _default_seed(2025)
    s2 = _default_seed(2025)
    assert s1 == s2


def test_default_seed_difiere_entre_temporadas() -> None:
    """Temporadas distintas -> seeds distintas."""
    s1 = _default_seed(2025)
    s2 = _default_seed(2024)
    assert s1 != s2


def test_default_seed_en_rango_int32() -> None:
    """La seed está en [0, 2^31)."""
    seed = _default_seed(2025)
    assert 0 <= seed < 2**31


# --------------------------------------------------------------------------- #
# compare_models: estructura del resultado
# --------------------------------------------------------------------------- #


def test_compare_models_devuelve_lista_de_comparison_row() -> None:
    """compare_models devuelve una lista de ComparisonRow."""
    teams = _TEAMS

    p_pure = dict.fromkeys(teams, 0.1)
    p_adj = dict.fromkeys(teams, 0.1)
    snapshots = {t: _snap(t) for t in teams}

    inputs = _sim_inputs(teams)
    outcome_pure = _sim_outcome(_rel_probs(p_pure))
    outcome_adj = _sim_outcome(_rel_probs(p_adj))
    build_res = _build_result(snapshots)

    with (
        patch(
            "descenso.application.compare_models.load_inputs",
            return_value=inputs,
        ),
        patch(
            "descenso.application.compare_models.build_strengths",
            return_value=build_res,
        ),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=[outcome_pure, outcome_adj],
        ),
    ):
        cfg = _cfg()
        rows = compare_models(cfg, n_sims=100, seed=42)

    assert isinstance(rows, list)
    assert all(isinstance(r, ComparisonRow) for r in rows)
    assert len(rows) == len(teams)


def test_compare_models_ordenado_por_p_adjusted_desc() -> None:
    """La lista de ComparisonRow está ordenada por p_adjusted descendente."""
    teams = ["a", "b", "c"]
    p_pure = {"a": 0.2, "b": 0.5, "c": 0.1}
    p_adj = {"a": 0.25, "b": 0.45, "c": 0.15}
    snapshots = {t: _snap(t) for t in teams}

    inputs = _sim_inputs(teams)
    outcome_pure = _sim_outcome(_rel_probs(p_pure))
    outcome_adj = _sim_outcome(_rel_probs(p_adj))
    build_res = _build_result(snapshots)

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=[outcome_pure, outcome_adj],
        ),
    ):
        rows = compare_models(_cfg(), n_sims=100, seed=42)

    p_vals = [r.p_adjusted for r in rows]
    assert p_vals == sorted(p_vals, reverse=True)


def test_compare_models_delta_es_p_adj_menos_p_pure_en_pp() -> None:
    """delta = (p_adj - p_pure) * 100 en puntos porcentuales."""
    teams = ["a"]
    p_pure = {"a": 0.20}
    p_adj = {"a": 0.25}
    snapshots = {"a": _snap("a")}

    inputs = _sim_inputs(teams)
    outcome_pure = _sim_outcome(_rel_probs(p_pure))
    outcome_adj = _sim_outcome(_rel_probs(p_adj))
    build_res = _build_result(snapshots)

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=[outcome_pure, outcome_adj],
        ),
    ):
        rows = compare_models(_cfg(), n_sims=100, seed=42)

    assert rows[0].delta == pytest.approx(5.0)


def test_compare_models_nota_vacia_cuando_delta_menor_3pp() -> None:
    """Si |delta| < 3pp, la nota está vacía."""
    teams = ["a"]
    p_pure = {"a": 0.20}
    p_adj = {"a": 0.21}  # delta = 1pp < 3pp
    snapshots = {"a": _snap("a", form=1502.0)}

    inputs = _sim_inputs(teams)
    outcome_pure = _sim_outcome(_rel_probs(p_pure))
    outcome_adj = _sim_outcome(_rel_probs(p_adj))
    build_res = _build_result(snapshots)

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=[outcome_pure, outcome_adj],
        ),
    ):
        rows = compare_models(_cfg(), n_sims=100, seed=42)

    assert rows[0].note == ""


def test_compare_models_nota_con_factor_cuando_delta_mayor_3pp() -> None:
    """Si |delta| >= 3pp y hay factor dominante, la nota lo nombra."""
    teams = ["a"]
    p_pure = {"a": 0.10}
    p_adj = {"a": 0.15}  # delta = 5pp >= 3pp
    # Snapshot con forma dominante: form_rating muy distinto de elo_base
    snapshots = {"a": _snap("a", elo=1500.0, form=1560.0)}  # form_component=30

    inputs = _sim_inputs(teams)
    outcome_pure = _sim_outcome(_rel_probs(p_pure))
    outcome_adj = _sim_outcome(_rel_probs(p_adj))
    build_res = _build_result(snapshots)

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=[outcome_pure, outcome_adj],
        ),
    ):
        rows = compare_models(_cfg(), n_sims=100, seed=42)

    # La nota debe mencionar el factor
    assert "forma" in rows[0].note


def test_compare_models_nota_sin_ajuste_dominante_cuando_todo_cero() -> None:
    """Si delta >= 3pp pero el snapshot no tiene ajuste dominante, la nota lo indica."""
    teams = ["a"]
    p_pure = {"a": 0.10}
    p_adj = {"a": 0.15}  # delta = 5pp
    # Snapshot sin forma ni ajustes
    snapshots = {"a": _snap("a", elo=1500.0, form=1500.0, delta_coach=0.0, delta_inj=0.0)}

    inputs = _sim_inputs(teams)
    outcome_pure = _sim_outcome(_rel_probs(p_pure))
    outcome_adj = _sim_outcome(_rel_probs(p_adj))
    build_res = _build_result(snapshots)

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=[outcome_pure, outcome_adj],
        ),
    ):
        rows = compare_models(_cfg(), n_sims=100, seed=42)

    assert "sin ajuste dominante" in rows[0].note


# --------------------------------------------------------------------------- #
# reproducibilidad: misma seed -> mismas filas
# --------------------------------------------------------------------------- #


def test_compare_models_reproducible_con_misma_seed() -> None:
    """Dos llamadas con la misma seed producen exactamente las mismas filas."""
    teams = ["a", "b", "c"]
    p_pure = {"a": 0.3, "b": 0.5, "c": 0.1}
    p_adj = {"a": 0.35, "b": 0.45, "c": 0.15}
    snapshots = {t: _snap(t) for t in teams}

    inputs = _sim_inputs(teams)
    build_res = _build_result(snapshots)

    def _make_outcomes() -> list[object]:
        return [
            _sim_outcome(_rel_probs(p_pure)),
            _sim_outcome(_rel_probs(p_adj)),
        ]

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=_make_outcomes(),
        ),
    ):
        rows1 = compare_models(_cfg(), n_sims=100, seed=42)

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=_make_outcomes(),
        ),
    ):
        rows2 = compare_models(_cfg(), n_sims=100, seed=42)

    assert [(r.team, r.p_pure, r.p_adjusted, r.delta) for r in rows1] == [
        (r.team, r.p_pure, r.p_adjusted, r.delta) for r in rows2
    ]


# --------------------------------------------------------------------------- #
# ComparisonRow: estructura
# --------------------------------------------------------------------------- #


def test_comparison_row_frozen() -> None:
    """ComparisonRow es inmutable (frozen dataclass)."""
    row = ComparisonRow(team="a", p_pure=0.1, p_adjusted=0.15, delta=5.0, note="forma")
    with pytest.raises((AttributeError, TypeError)):
        row.p_pure = 0.2  # type: ignore[misc]


def test_comparison_row_campos_presentes() -> None:
    row = ComparisonRow(team="a", p_pure=0.1, p_adjusted=0.15, delta=5.0, note="")
    assert row.team == "a"
    assert row.p_pure == pytest.approx(0.1)
    assert row.p_adjusted == pytest.approx(0.15)
    assert row.delta == pytest.approx(5.0)
    assert row.note == ""


def test_compare_models_seed_none_usa_seed_por_defecto() -> None:
    """Con seed=None, compare_models genera una seed determinista y no falla."""
    teams = ["a", "b"]
    p_pure = {"a": 0.3, "b": 0.1}
    p_adj = {"a": 0.3, "b": 0.1}
    snapshots = {t: _snap(t) for t in teams}

    inputs = _sim_inputs(teams)
    outcome_pure = _sim_outcome(_rel_probs(p_pure))
    outcome_adj = _sim_outcome(_rel_probs(p_adj))
    build_res = _build_result(snapshots)

    with (
        patch("descenso.application.compare_models.load_inputs", return_value=inputs),
        patch("descenso.application.compare_models.build_strengths", return_value=build_res),
        patch(
            "descenso.application.compare_models.run_simulation",
            side_effect=[outcome_pure, outcome_adj],
        ),
    ):
        rows = compare_models(_cfg(), n_sims=100, seed=None)

    assert len(rows) == 2
