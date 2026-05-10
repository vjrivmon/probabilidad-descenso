"""Tests del caso de uso run_simulation: _apply_fixed, save/load_last_run, run_simulation completo.

No toca la red: usa SimulationInputs directamente para inyectar datos de prueba.
"""

from __future__ import annotations

import json
from pathlib import Path

from descenso.application.run_simulation import (
    FixedResult,
    SimulationInputs,
    SimulationOutcome,
    _apply_fixed,
    load_last_run,
    run_simulation,
    save_last_run,
)
from descenso.config import AppConfig, ModelConfig
from descenso.domain.match import Match, MatchStatus
from descenso.domain.probabilities import RelegationProbabilities, TeamProbabilities
from descenso.domain.team import Team

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _teams() -> list[Team]:
    return [
        Team(id="a", name="Equipo A", clubelo_name="A", openfootball_name="A"),
        Team(id="b", name="Equipo B", clubelo_name="B", openfootball_name="B"),
        Team(id="c", name="Equipo C", clubelo_name="C", openfootball_name="C"),
        Team(id="d", name="Equipo D", clubelo_name="D", openfootball_name="D"),
    ]


def _elo() -> dict[str, float]:
    return {"a": 1800.0, "b": 1700.0, "c": 1600.0, "d": 1500.0}


def _partido_pendiente(home: str, away: str, gw: int = 1) -> Match:
    return Match(season=2025, gameweek=gw, home_team=home, away_team=away)


def _partido_jugado(home: str, away: str, hg: int, ag: int, gw: int = 1) -> Match:
    return Match(
        season=2025, gameweek=gw, home_team=home, away_team=away, home_goals=hg, away_goals=ag
    )


def _config_rapida() -> AppConfig:
    return AppConfig(model=ModelConfig(model_type="pure", n_sims=500))


def _inputs_basicos() -> SimulationInputs:
    matches = [
        _partido_jugado("a", "b", 2, 1, gw=1),
        _partido_jugado("c", "d", 1, 0, gw=1),
        _partido_pendiente("a", "c", gw=2),
        _partido_pendiente("b", "d", gw=2),
    ]
    return SimulationInputs(teams=_teams(), elo=_elo(), matches=matches)


# --------------------------------------------------------------------------- #
# _apply_fixed
# --------------------------------------------------------------------------- #


def test_apply_fixed_aplica_resultado_sobre_pendiente() -> None:
    matches = [_partido_pendiente("a", "b")]
    fx = FixedResult(home_team="a", home_goals=3, away_team="b", away_goals=0)
    result, applied, ignored = _apply_fixed(matches, [fx])
    assert len(applied) == 1 and len(ignored) == 0
    assert result[0].home_goals == 3 and result[0].away_goals == 0
    assert result[0].is_fixed is True


def test_apply_fixed_ignora_si_ya_jugado_con_resultado_real() -> None:
    """Si el partido ya tiene resultado real (no fijado), el fix se ignora con motivo."""
    matches = [_partido_jugado("a", "b", 1, 1)]
    fx = FixedResult(home_team="a", home_goals=3, away_team="b", away_goals=0)
    _, applied, ignored = _apply_fixed(matches, [fx])
    assert len(applied) == 0
    assert len(ignored) == 1
    motivo = ignored[0][1]
    assert "1-1" in motivo  # menciona el marcador real


def test_apply_fixed_ignora_con_motivo_si_emparejamiento_no_existe() -> None:
    matches = [_partido_pendiente("a", "b")]
    fx = FixedResult(home_team="c", home_goals=2, away_team="d", away_goals=1)
    _, applied, ignored = _apply_fixed(matches, [fx])
    assert len(applied) == 0
    assert len(ignored) == 1
    assert "no está en el calendario" in ignored[0][1]


def test_apply_fixed_ignora_con_motivo_si_emparejamiento_invertido() -> None:
    """Si el par existe pero con los lados cambiados, el motivo menciona quién juega en casa."""
    matches = [_partido_pendiente("b", "a")]  # b es local, a es visitante
    fx = FixedResult(home_team="a", home_goals=2, away_team="b", away_goals=1)
    _, applied, ignored = _apply_fixed(matches, [fx])
    assert len(applied) == 0
    assert len(ignored) == 1
    assert "b" in ignored[0][1]  # menciona el equipo que realmente juega en casa


def test_apply_fixed_sobreescribe_resultado_previamente_fijado() -> None:
    """Un fix puede sobreescribir otro fix (is_fixed=True)."""
    # Partido ya fijado antes
    partido_fijado = Match(
        season=2025,
        gameweek=1,
        home_team="a",
        away_team="b",
        home_goals=1,
        away_goals=0,
        is_fixed=True,
    )
    fx = FixedResult(home_team="a", home_goals=3, away_team="b", away_goals=2)
    result, applied, ignored = _apply_fixed([partido_fijado], [fx])
    assert len(applied) == 1 and len(ignored) == 0
    assert result[0].home_goals == 3


def test_apply_fixed_multiples_fixes() -> None:
    matches = [
        _partido_pendiente("a", "b", gw=1),
        _partido_pendiente("c", "d", gw=2),
    ]
    fixes = [
        FixedResult(home_team="a", home_goals=2, away_team="b", away_goals=0),
        FixedResult(home_team="c", home_goals=1, away_team="d", away_goals=1),
    ]
    result, applied, ignored = _apply_fixed(matches, fixes)
    assert len(applied) == 2 and len(ignored) == 0
    assert result[0].home_goals == 2
    assert result[1].home_goals == 1


def test_apply_fixed_lista_vacia_no_modifica_nada() -> None:
    matches = [_partido_pendiente("a", "b")]
    result, applied, ignored = _apply_fixed(matches, [])
    assert len(applied) == 0 and len(ignored) == 0
    assert result[0].status is MatchStatus.PENDING


# --------------------------------------------------------------------------- #
# run_simulation (integracion con dominio real, sin red)
# --------------------------------------------------------------------------- #


def test_run_simulation_devuelve_outcome_coherente() -> None:
    inputs = _inputs_basicos()
    config = _config_rapida()
    outcome = run_simulation(config, inputs=inputs, seed=42)
    assert isinstance(outcome, SimulationOutcome)
    assert outcome.n_played == 2
    assert outcome.n_pending == 2
    probs = {tp.team: tp.p_relegation for tp in outcome.probabilities.teams}
    for p in probs.values():
        assert 0.0 <= p <= 1.0


def test_run_simulation_reproducible_con_misma_seed() -> None:
    inputs = _inputs_basicos()
    config = _config_rapida()
    o1 = run_simulation(config, inputs=inputs, seed=99)
    o2 = run_simulation(config, inputs=inputs, seed=99)
    p1 = {tp.team: tp.p_relegation for tp in o1.probabilities.teams}
    p2 = {tp.team: tp.p_relegation for tp in o2.probabilities.teams}
    assert p1 == p2


def test_run_simulation_resultado_distinto_seed_distinta() -> None:
    """Seeds distintas deben producir resultados distintos (con alta probabilidad).

    Usamos 4 equipos con partidos pendientes para que el resultado aleatorio
    importe y las probabilidades intermedias (0 < p < 1) puedan diferir.
    """
    equipos = _teams()  # 4 equipos
    matches = [_partido_pendiente("a", "b", gw=i) for i in range(1, 10)] + [
        _partido_pendiente("c", "d", gw=i) for i in range(1, 10)
    ]
    inputs = SimulationInputs(teams=equipos, elo=_elo(), matches=matches)
    config = AppConfig(model=ModelConfig(model_type="pure", n_sims=5000, n_relegation=1))
    o1 = run_simulation(config, inputs=inputs, seed=1)
    o2 = run_simulation(config, inputs=inputs, seed=9999)
    p1 = {tp.team: tp.p_relegation for tp in o1.probabilities.teams}
    p2 = {tp.team: tp.p_relegation for tp in o2.probabilities.teams}
    # Con seeds distintas y muchos partidos pendientes, al menos una prob. debe diferir
    assert p1 != p2


def test_run_simulation_temporada_terminada_probabilidades_deterministas() -> None:
    """Si no quedan partidos pendientes, P(descenso) es 0 ó 1 exacto."""
    matches = [
        _partido_jugado("a", "b", 3, 0),
        _partido_jugado("c", "d", 1, 2),
    ]
    inputs = SimulationInputs(teams=_teams()[:4], elo=_elo(), matches=matches)
    config = AppConfig(model=ModelConfig(model_type="pure", n_sims=200, n_relegation=2))
    outcome = run_simulation(config, inputs=inputs, seed=1)
    probs = {tp.team: tp.p_relegation for tp in outcome.probabilities.teams}
    for p in probs.values():
        assert p in (0.0, 1.0)


def test_run_simulation_con_fix_aplicado() -> None:
    matches = [_partido_pendiente("a", "b")]
    inputs = SimulationInputs(teams=_teams()[:2], elo={"a": 1600.0, "b": 1400.0}, matches=matches)
    config = AppConfig(model=ModelConfig(model_type="pure", n_sims=200, n_relegation=1))
    fx = FixedResult(home_team="a", home_goals=5, away_team="b", away_goals=0)
    outcome = run_simulation(config, fixed_results=[fx], inputs=inputs, seed=1)
    assert len(outcome.applied_fixed) == 1
    assert len(outcome.ignored_fixed) == 0


def test_run_simulation_modelo_ajustado_anade_nota() -> None:
    """Con model_type='adjusted', run_simulation añade una nota avisando que es CP2."""
    inputs = _inputs_basicos()
    config = AppConfig(model=ModelConfig(model_type="adjusted", n_sims=200))
    outcome = run_simulation(config, inputs=inputs, seed=1)
    assert any("modelo ajustado" in n for n in outcome.notes)


def test_run_simulation_team_names_property() -> None:
    inputs = _inputs_basicos()
    config = _config_rapida()
    outcome = run_simulation(config, inputs=inputs, seed=1)
    names = outcome.team_names
    assert names["a"] == "Equipo A"
    assert len(names) == 4


# --------------------------------------------------------------------------- #
# save_last_run / load_last_run
# --------------------------------------------------------------------------- #


def _fake_outcome() -> SimulationOutcome:
    probs = RelegationProbabilities(
        n_sims=500,
        seed=42,
        teams=[
            TeamProbabilities(
                team="a",
                p_relegation=0.15,
                p_by_position={1: 0.5, 2: 0.3, 3: 0.2},
                expected_points=45.0,
                expected_position=2.0,
            ),
            TeamProbabilities(
                team="b",
                p_relegation=0.85,
                p_by_position={3: 0.7, 4: 0.3},
                expected_points=30.0,
                expected_position=3.5,
            ),
        ],
    )
    teams = [
        Team(id="a", name="Equipo A", openfootball_name="A"),
        Team(id="b", name="Equipo B", openfootball_name="B"),
    ]
    return SimulationOutcome(
        season=2025,
        teams=teams,
        n_played=10,
        n_pending=5,
        model_type="pure",
        probabilities=probs,
        applied_fixed=[],
        ignored_fixed=[],
        notes=[],
    )


def test_save_last_run_crea_json_legible(tmp_path: Path) -> None:
    outcome = _fake_outcome()
    path = save_last_run(outcome, tmp_path)
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["season"] == 2025
    assert data["n_sims"] == 500
    assert data["seed"] == 42
    assert len(data["teams"]) == 2


def test_save_last_run_crea_directorio_si_no_existe(tmp_path: Path) -> None:
    cache_dir = tmp_path / "nueva_carpeta"
    assert not cache_dir.exists()
    save_last_run(_fake_outcome(), cache_dir)
    assert cache_dir.exists()


def test_save_last_run_es_atomico(tmp_path: Path) -> None:
    """El fichero .json.tmp no debe quedar tras un save exitoso."""
    save_last_run(_fake_outcome(), tmp_path)
    assert not (tmp_path / "last_run.json.tmp").exists()
    assert (tmp_path / "last_run.json").exists()


def test_load_last_run_devuelve_none_si_no_existe(tmp_path: Path) -> None:
    assert load_last_run(tmp_path) is None


def test_load_last_run_roundtrip(tmp_path: Path) -> None:
    outcome = _fake_outcome()
    save_last_run(outcome, tmp_path)
    data = load_last_run(tmp_path)
    assert data is not None
    assert data["season"] == 2025
    assert data["n_played"] == 10
    assert data["team_names"] == {"a": "Equipo A", "b": "Equipo B"}


def test_load_last_run_devuelve_none_si_json_corrupto(tmp_path: Path) -> None:
    (tmp_path / "last_run.json").write_text("esto no es json", encoding="utf-8")
    result = load_last_run(tmp_path)
    assert result is None


def test_save_last_run_con_fixes_aplicados(tmp_path: Path) -> None:
    outcome = _fake_outcome()
    outcome_con_fix = SimulationOutcome(
        season=outcome.season,
        teams=outcome.teams,
        n_played=outcome.n_played,
        n_pending=outcome.n_pending,
        model_type=outcome.model_type,
        probabilities=outcome.probabilities,
        applied_fixed=[FixedResult(home_team="a", home_goals=2, away_team="b", away_goals=1)],
        ignored_fixed=[],
        notes=[],
    )
    path = save_last_run(outcome_con_fix, tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["applied_fixed"]) == 1
    assert data["applied_fixed"][0] == ["a", 2, "b", 1]
