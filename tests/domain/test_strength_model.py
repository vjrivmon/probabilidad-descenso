"""Tests unitarios de `strength_model` — el diferencial del proyecto (CP2).

No hace IO ni red: dominio puro con datos sintéticos.
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from descenso.config import ModelConfig
from descenso.domain.match import Match
from descenso.domain.strength_model import (
    StrengthSnapshot,
    _coach_bump,
    _performance_rating,
    compute_strengths,
    effective_strengths,
)

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_BASE = dt.date(2026, 1, 1)
_TODAY = dt.date(2026, 5, 10)


def _cfg(**kwargs: object) -> ModelConfig:
    defaults: dict[str, object] = {
        "alpha": 0.5,
        "form_half_life_days": 75.0,
        "form_window_matches": 15,
        "xg_blend_beta": 0.6,
        "form_k_factor": 20.0,
        "form_goal_diff_scale": 1.0,
        "home_advantage_elo": 65.0,
        "draw_base": 0.26,
        "coach_bump_default": 25.0,
        "coach_bump_decay_matches": 6,
        "n_sims": 100,
        "n_relegation": 3,
        "model_type": "adjusted",
    }
    defaults.update(kwargs)
    return ModelConfig(**defaults)


def _played(
    home: str,
    away: str,
    hg: int,
    ag: int,
    date: dt.date,
    season: int = 2025,
    gw: int = 1,
    home_xg: float | None = None,
    away_xg: float | None = None,
) -> Match:
    return Match(
        season=season,
        gameweek=gw,
        date=date,
        home_team=home,
        away_team=away,
        home_goals=hg,
        away_goals=ag,
        home_xg=home_xg,
        away_xg=away_xg,
    )


# --------------------------------------------------------------------------- #
# modelo puro: con alpha=1.0 y sin deltas, r_eff == elo_base exacto
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "team_id,elo_val",
    [
        ("equipo-a", 1500.0),
        ("equipo-b", 1350.0),
        ("equipo-c", 1800.0),
    ],
)
def test_modelo_puro_r_eff_igual_a_elo_base(team_id: str, elo_val: float) -> None:
    """Con alpha=1.0 y sin cambios/bajas, r_eff == elo_base exacto (modelo CP1)."""
    elo = {"equipo-a": 1500.0, "equipo-b": 1350.0, "equipo-c": 1800.0}
    cfg = _cfg(alpha=1.0)
    snaps = compute_strengths(
        elo_base=elo,
        played_matches=[],
        coach_changes={},
        injury_adjustments={},
        as_of=_TODAY,
        config=cfg,
    )
    snap = snaps[team_id]
    assert snap.r_eff == pytest.approx(elo_val), f"{team_id}: r_eff no coincide con elo_base"
    assert snap.elo_base == pytest.approx(elo_val)
    assert snap.form_rating == pytest.approx(elo_val)  # sin partidos, form_rating=elo_base


def test_modelo_puro_con_partidos_jugados_sigue_siendo_elo_base() -> None:
    """Con alpha=1.0, incluso con partidos, r_eff == elo_base (la forma no cuenta)."""
    elo = {"a": 1600.0, "b": 1400.0}
    matches = [_played("a", "b", 3, 0, dt.date(2026, 3, 1))]
    cfg = _cfg(alpha=1.0)
    snaps = compute_strengths(elo, matches, {}, {}, _TODAY, cfg)
    assert snaps["a"].r_eff == pytest.approx(1600.0)
    assert snaps["b"].r_eff == pytest.approx(1400.0)


# --------------------------------------------------------------------------- #
# direccionalidad de la forma
# --------------------------------------------------------------------------- #


def test_forma_positiva_para_equipo_que_sobrende() -> None:
    """Un equipo que gana a rivales con más Elo debe tener form_rating > elo_base."""
    # "a" (Elo 1400) gana a "b" (Elo 1800) 3 veces: sobre-rinde claramente
    elo = {"a": 1400.0, "b": 1800.0}
    matches = [
        _played("a", "b", 3, 0, dt.date(2026, 4, 1)),
        _played("b", "a", 0, 2, dt.date(2026, 4, 8)),
        _played("a", "b", 2, 0, dt.date(2026, 4, 15)),
    ]
    cfg = _cfg(alpha=0.5)
    snaps = compute_strengths(elo, matches, {}, {}, _TODAY, cfg)
    assert snaps["a"].form_rating > snaps["a"].elo_base, "a deberia sobrerendir"


def test_forma_negativa_para_equipo_que_infraende() -> None:
    """Un equipo que pierde continuamente frente a rivales con menos Elo tiene form < elo_base."""
    elo = {"a": 1800.0, "b": 1400.0}
    matches = [
        _played("a", "b", 0, 3, dt.date(2026, 4, 1)),
        _played("b", "a", 2, 0, dt.date(2026, 4, 8)),
        _played("a", "b", 0, 2, dt.date(2026, 4, 15)),
    ]
    cfg = _cfg(alpha=0.5)
    snaps = compute_strengths(elo, matches, {}, {}, _TODAY, cfg)
    assert snaps["a"].form_rating < snaps["a"].elo_base, "a deberia infrarendir"


# --------------------------------------------------------------------------- #
# decaimiento temporal
# --------------------------------------------------------------------------- #


def test_decaimiento_temporal_peso_mayor_en_partidos_recientes() -> None:
    """El mismo resultado pesa más cuanto más reciente es.

    Con UN solo partido, el peso se cancela (form = elo + perf independientemente
    del peso). Necesitamos DOS partidos de signo opuesto: el reciente gana, el
    antiguo pierde. Si el reciente pesa más, form_rating > elo_base.
    Si el antiguo pesara igual, se cancelarían y form_rating ≈ elo_base.
    """
    elo = {"a": 1500.0, "b": 1500.0}
    cfg = _cfg(alpha=0.0, form_half_life_days=30.0)

    # Partido muy reciente: victoria clara (sube la forma)
    match_reciente = _played("a", "b", 3, 0, _TODAY - dt.timedelta(days=1), gw=2)
    # Partido antiguo: derrota clara (baja la forma) — mucho menos peso por decaimiento
    match_antiguo = _played("b", "a", 3, 0, _TODAY - dt.timedelta(days=90), gw=1)

    snaps = compute_strengths(elo, [match_reciente, match_antiguo], {}, {}, _TODAY, cfg)
    # El partido reciente (victoria) pesa mucho más que el antiguo (derrota)
    # -> form_rating debe ser > elo_base
    assert snaps["a"].form_rating > snaps["a"].elo_base


def test_decaimiento_temporal_formula_exacta() -> None:
    """Verificación exacta de w_t = 0.5^(days/half_life)."""
    elo = {"a": 1500.0, "b": 1500.0}
    half_life = 50.0
    cfg = _cfg(
        alpha=0.0,
        form_half_life_days=half_life,
        form_k_factor=20.0,
        form_goal_diff_scale=1.0,
        home_advantage_elo=65.0,
    )

    age_days = 25
    match_date = _TODAY - dt.timedelta(days=age_days)
    match = _played("a", "b", 3, 0, match_date)
    snaps = compute_strengths(elo, [match], {}, {}, _TODAY, cfg)

    # Calcular manualmente el performance rating esperado
    # a juega en casa contra b (iguales en Elo), con ventaja de casa
    h = 65.0
    diff = max(-1000.0, min(1000.0, (1500.0 + h) - 1500.0))
    w_exp = 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))
    adj_for = 3.0  # sin xG, usa goles
    adj_against = 0.0
    result_adj = 1.0 / (1.0 + math.exp(-(adj_for - adj_against) / 1.0))
    perf = 20.0 * (result_adj - w_exp)

    w = math.pow(0.5, age_days / half_life)
    form_rating_expected = 1500.0 + (w * perf) / w  # = 1500 + perf (un solo partido)
    assert snaps["a"].form_rating == pytest.approx(form_rating_expected, abs=0.01)


# --------------------------------------------------------------------------- #
# ventana de forma
# --------------------------------------------------------------------------- #


def test_ventana_solo_ultimos_n_partidos() -> None:
    """Solo entran los form_window_matches más recientes; los viejos se ignoran."""
    elo = {"a": 1500.0, "b": 1500.0}
    cfg = _cfg(alpha=0.0, form_window_matches=2, form_half_life_days=9999.0)

    # 5 partidos: los 3 primeros son derrotas claras, los 2 últimos son victorias claras
    matches = [
        _played("a", "b", 0, 3, dt.date(2026, 1, 1)),
        _played("a", "b", 0, 3, dt.date(2026, 1, 8)),
        _played("a", "b", 0, 3, dt.date(2026, 1, 15)),
        _played("a", "b", 3, 0, dt.date(2026, 4, 1)),  # reciente — victoria
        _played("a", "b", 3, 0, dt.date(2026, 4, 8)),  # reciente — victoria
    ]
    snaps = compute_strengths(elo, matches, {}, {}, _TODAY, cfg)
    # Con window=2, solo cuentan las 2 victorias recientes: form_rating > elo_base
    assert snaps["a"].form_rating > snaps["a"].elo_base
    assert snaps["a"].n_form_matches == 2


# --------------------------------------------------------------------------- #
# equipo con 0 partidos en la ventana
# --------------------------------------------------------------------------- #


def test_equipo_sin_partidos_forma_igual_a_elo_base() -> None:
    """Un equipo con 0 partidos jugados tiene form_rating == elo_base, n_form=0."""
    elo = {"nuevo": 1450.0}
    cfg = _cfg(alpha=0.5)
    snaps = compute_strengths(elo, [], {}, {}, _TODAY, cfg)
    snap = snaps["nuevo"]
    assert snap.form_rating == pytest.approx(1450.0)
    assert snap.n_form_matches == 0
    # Sin forma y sin deltas, r_eff debe = elo_base con cualquier alpha
    assert snap.r_eff == pytest.approx(1450.0)


def test_equipo_con_todos_partidos_futuros_no_tiene_forma() -> None:
    """Partidos con fecha > as_of se ignoran para el cómputo de forma."""
    elo = {"a": 1500.0, "b": 1400.0}
    # Partido en el futuro
    partido_futuro = _played("a", "b", 3, 0, _TODAY + dt.timedelta(days=1))
    cfg = _cfg(alpha=0.5)
    snaps = compute_strengths(elo, [partido_futuro], {}, {}, _TODAY, cfg)
    assert snaps["a"].n_form_matches == 0
    assert snaps["a"].form_rating == pytest.approx(1500.0)


# --------------------------------------------------------------------------- #
# anti-leakage
# --------------------------------------------------------------------------- #


def test_antileakage_partidos_con_fecha_futura_se_ignoran() -> None:
    """Partidos con date > as_of NO alimentan la forma (protección anti-leakage)."""
    elo = {"a": 1500.0, "b": 1500.0}
    # Partido jugado 'mañana' — leakage
    partido_leakage = _played("a", "b", 3, 0, _TODAY + dt.timedelta(days=10))
    cfg = _cfg(alpha=0.0)
    snaps = compute_strengths(elo, [partido_leakage], {}, {}, _TODAY, cfg)
    # No debe influir en la forma
    assert snaps["a"].n_form_matches == 0


def test_antileakage_solo_cuenta_hasta_as_of() -> None:
    """Un partido el mismo día de as_of sí cuenta; el día siguiente no."""
    elo = {"a": 1500.0, "b": 1500.0}
    hoy = dt.date(2026, 4, 1)
    partido_valido = _played("a", "b", 3, 0, hoy)
    partido_futuro = _played("a", "b", 3, 0, hoy + dt.timedelta(days=1))
    cfg = _cfg(alpha=0.0)

    snaps_con_uno = compute_strengths(elo, [partido_valido], {}, {}, hoy, cfg)
    snaps_con_dos = compute_strengths(elo, [partido_valido, partido_futuro], {}, {}, hoy, cfg)
    assert snaps_con_uno["a"].n_form_matches == 1
    # El futuro no se cuenta: mismo resultado
    assert snaps_con_dos["a"].n_form_matches == 1
    assert snaps_con_dos["a"].form_rating == pytest.approx(snaps_con_uno["a"].form_rating)


def test_antileakage_partido_sin_fecha_se_ignora() -> None:
    """Un partido sin fecha (date=None) se ignora en el cómputo de forma."""
    elo = {"a": 1500.0, "b": 1400.0}
    partido_sin_fecha = Match(
        season=2025,
        gameweek=1,
        home_team="a",
        away_team="b",
        home_goals=3,
        away_goals=0,
    )
    cfg = _cfg(alpha=0.0)
    snaps = compute_strengths(elo, [partido_sin_fecha], {}, {}, _TODAY, cfg)
    assert snaps["a"].n_form_matches == 0


# --------------------------------------------------------------------------- #
# delta_coach
# --------------------------------------------------------------------------- #


def test_delta_coach_sin_partidos_desde_cambio_es_bump_completo() -> None:
    """Con 0 partidos desde el cambio, delta_coach == bump completo."""
    elo = {"a": 1500.0}
    change_date = dt.date(2026, 4, 1)
    coach_changes: dict[str, list[tuple[dt.date, float | None]]] = {"a": [(change_date, 30.0)]}
    cfg = _cfg(coach_bump_decay_matches=6)
    snaps = compute_strengths(elo, [], coach_changes, {}, _TODAY, cfg)
    assert snaps["a"].delta_coach == pytest.approx(30.0)


def test_delta_coach_tras_decay_matches_es_cero() -> None:
    """Tras decay_matches partidos desde el cambio, delta_coach == 0."""
    elo = {"a": 1500.0, "b": 1400.0}
    change_date = dt.date(2026, 3, 1)
    # 6 partidos jugados DESPUÉS del cambio (decay_matches=6)
    matches = [
        _played("a", "b", 1, 1, change_date + dt.timedelta(days=d)) for d in [5, 10, 15, 20, 25, 30]
    ]
    coach_changes: dict[str, list[tuple[dt.date, float | None]]] = {"a": [(change_date, 30.0)]}
    cfg = _cfg(coach_bump_decay_matches=6)
    snaps = compute_strengths(elo, matches, coach_changes, {}, _TODAY, cfg)
    assert snaps["a"].delta_coach == pytest.approx(0.0)


def test_delta_coach_mitad_de_decaimiento() -> None:
    """A mitad del decaimiento, delta_coach == bump * (1 - m/decay)."""
    elo = {"a": 1500.0, "b": 1400.0}
    change_date = dt.date(2026, 3, 1)
    bump = 24.0
    decay = 6
    # 3 partidos jugados tras el cambio (mitad del decay)
    matches = [_played("a", "b", 1, 1, change_date + dt.timedelta(days=d)) for d in [5, 10, 15]]
    coach_changes: dict[str, list[tuple[dt.date, float | None]]] = {"a": [(change_date, bump)]}
    cfg = _cfg(coach_bump_decay_matches=decay)
    snaps = compute_strengths(elo, matches, coach_changes, {}, _TODAY, cfg)
    expected = bump * (1.0 - 3 / decay)
    assert snaps["a"].delta_coach == pytest.approx(expected)


def test_delta_coach_usa_bump_default_si_none() -> None:
    """Si elo_bump es None en el cambio, usa coach_bump_default de config."""
    elo = {"a": 1500.0}
    change_date = dt.date(2026, 4, 1)
    coach_changes: dict[str, list[tuple[dt.date, float | None]]] = {"a": [(change_date, None)]}
    cfg = _cfg(coach_bump_default=40.0, coach_bump_decay_matches=6)
    snaps = compute_strengths(elo, [], coach_changes, {}, _TODAY, cfg)
    assert snaps["a"].delta_coach == pytest.approx(40.0)


def test_delta_coach_solo_cuenta_el_mas_reciente() -> None:
    """Con dos cambios de entrenador, solo cuenta el más reciente."""
    elo = {"a": 1500.0}
    change1 = dt.date(2026, 1, 10)
    change2 = dt.date(2026, 3, 15)
    coach_changes: dict[str, list[tuple[dt.date, float | None]]] = {
        "a": [(change1, 100.0), (change2, 30.0)]
    }
    cfg = _cfg(coach_bump_decay_matches=10)
    snaps = compute_strengths(elo, [], coach_changes, {}, _TODAY, cfg)
    # Solo cuenta el más reciente (change2 con bump=30.0), el de 100 se ignora
    assert snaps["a"].delta_coach == pytest.approx(30.0)


def test_delta_coach_cambio_futuro_se_ignora() -> None:
    """Un cambio de entrenador con fecha > as_of se ignora."""
    elo = {"a": 1500.0}
    change_date = _TODAY + dt.timedelta(days=5)
    coach_changes: dict[str, list[tuple[dt.date, float | None]]] = {"a": [(change_date, 50.0)]}
    cfg = _cfg()
    snaps = compute_strengths(elo, [], coach_changes, {}, _TODAY, cfg)
    assert snaps["a"].delta_coach == pytest.approx(0.0)


def test_delta_coach_solo_partidos_desde_el_cambio_cuentan_para_decay() -> None:
    """Partidos ANTES del cambio no cuentan para el decaimiento."""
    elo = {"a": 1500.0, "b": 1400.0}
    change_date = dt.date(2026, 3, 10)
    # 3 partidos ANTES del cambio + 1 partido DESPUÉS
    matches = [
        _played("a", "b", 1, 1, dt.date(2026, 2, 1)),
        _played("a", "b", 1, 1, dt.date(2026, 2, 10)),
        _played("a", "b", 1, 1, dt.date(2026, 2, 20)),
        _played("a", "b", 1, 1, dt.date(2026, 3, 20)),  # después del cambio
    ]
    coach_changes: dict[str, list[tuple[dt.date, float | None]]] = {"a": [(change_date, 24.0)]}
    cfg = _cfg(coach_bump_decay_matches=6)
    snaps = compute_strengths(elo, matches, coach_changes, {}, _TODAY, cfg)
    # Solo 1 partido desde el cambio -> decay = 1/6
    expected = 24.0 * (1.0 - 1 / 6)
    assert snaps["a"].delta_coach == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# delta_injuries
# --------------------------------------------------------------------------- #


def test_delta_injuries_se_suma_tal_cual() -> None:
    """El ajuste de bajas se suma directamente a r_eff."""
    elo = {"a": 1500.0}
    injury_adjustments = {"a": -30.0}
    cfg = _cfg(alpha=1.0)  # sin forma para simplificar
    snaps = compute_strengths(elo, [], {}, injury_adjustments, _TODAY, cfg)
    assert snaps["a"].r_eff == pytest.approx(1500.0 - 30.0)
    assert snaps["a"].delta_injuries == pytest.approx(-30.0)


def test_delta_injuries_equipo_sin_bajas_es_cero() -> None:
    elo = {"a": 1500.0, "b": 1400.0}
    cfg = _cfg(alpha=1.0)
    snaps = compute_strengths(elo, [], {}, {"b": -20.0}, _TODAY, cfg)
    assert snaps["a"].delta_injuries == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# dominant_factor
# --------------------------------------------------------------------------- #


def test_dominant_factor_forma_cuando_es_el_mayor() -> None:
    """dominant_factor == 'forma' cuando la forma aporta más que coach/bajas."""
    # Construimos un snapshot con forma dominante
    snap = StrengthSnapshot(
        team="a",
        as_of=_TODAY,
        elo_base=1500.0,
        form_rating=1560.0,
        n_form_matches=5,
        delta_coach=5.0,
        delta_injuries=-2.0,
        alpha=0.5,
    )
    # form_component = 0.5 * (1560 - 1500) = 30.0 (mayor en valor abs)
    assert snap.dominant_factor() == "forma"


def test_dominant_factor_cambio_entrenador_cuando_es_el_mayor() -> None:
    snap = StrengthSnapshot(
        team="a",
        as_of=_TODAY,
        elo_base=1500.0,
        form_rating=1502.0,
        n_form_matches=3,
        delta_coach=40.0,
        delta_injuries=0.0,
        alpha=0.5,
    )
    assert snap.dominant_factor() == "cambio de entrenador"


def test_dominant_factor_bajas_cuando_es_el_mayor() -> None:
    snap = StrengthSnapshot(
        team="a",
        as_of=_TODAY,
        elo_base=1500.0,
        form_rating=1502.0,
        n_form_matches=3,
        delta_coach=5.0,
        delta_injuries=-50.0,
        alpha=0.5,
    )
    assert snap.dominant_factor() == "bajas"


def test_dominant_factor_vacio_cuando_todo_es_cero() -> None:
    """Si no hay ningún ajuste significativo, devuelve ''."""
    snap = StrengthSnapshot(
        team="a",
        as_of=_TODAY,
        elo_base=1500.0,
        form_rating=1500.0,
        n_form_matches=0,
        delta_coach=0.0,
        delta_injuries=0.0,
        alpha=0.5,
    )
    assert snap.dominant_factor() == ""


def test_dominant_factor_vacio_con_ajuste_menor_a_epsilon() -> None:
    """Ajustes menores a 1e-9 se consideran cero."""
    snap = StrengthSnapshot(
        team="a",
        as_of=_TODAY,
        elo_base=1500.0,
        form_rating=1500.0 + 1e-11,
        n_form_matches=1,
        delta_coach=0.0,
        delta_injuries=0.0,
        alpha=0.5,
    )
    assert snap.dominant_factor() == ""


# --------------------------------------------------------------------------- #
# xG blend
# --------------------------------------------------------------------------- #


def test_xg_blend_difiere_de_solo_goles_cuando_xg_distinto() -> None:
    """Con xG muy distinto de los goles reales, form_rating difiere del caso sin xG."""
    elo = {"a": 1500.0, "b": 1500.0}
    cfg_xg = _cfg(alpha=0.0, xg_blend_beta=0.6, form_half_life_days=9999.0)
    cfg_sin_xg = _cfg(alpha=0.0, xg_blend_beta=0.6, form_half_life_days=9999.0)

    # Mismo resultado en goles (3-0), pero xG indica que fue suerte (0.5-1.8)
    partido_con_xg = _played("a", "b", 3, 0, dt.date(2026, 4, 1), home_xg=0.5, away_xg=1.8)
    partido_sin_xg = _played("a", "b", 3, 0, dt.date(2026, 4, 1))

    snaps_xg = compute_strengths(elo, [partido_con_xg], {}, {}, _TODAY, cfg_xg)
    snaps_sin = compute_strengths(elo, [partido_sin_xg], {}, {}, _TODAY, cfg_sin_xg)

    # Con xG de "mala suerte", la mejora de forma debe ser menor
    assert snaps_xg["a"].form_rating < snaps_sin["a"].form_rating


def test_xg_blend_sin_xg_usa_solo_goles_reales() -> None:
    """Si no hay xG, el performance rating usa solo goles reales (beta_eff=1)."""
    elo = {"a": 1500.0, "b": 1500.0}
    cfg = _cfg(alpha=0.0, xg_blend_beta=0.6)

    # Partido sin xG
    partido = _played("a", "b", 2, 1, dt.date(2026, 4, 1))
    snaps = compute_strengths(elo, [partido], {}, {}, _TODAY, cfg)

    # Calcular manualmente el performance rating sin xG (beta=1)
    h = 65.0
    diff = max(-1000.0, min(1000.0, (1500.0 + h) - 1500.0))
    w_exp = 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))
    result_adj = 1.0 / (1.0 + math.exp(-(2.0 - 1.0) / 1.0))
    perf = 20.0 * (result_adj - w_exp)
    expected_form = 1500.0 + perf

    assert snaps["a"].form_rating == pytest.approx(expected_form, abs=0.01)


# --------------------------------------------------------------------------- #
# clip de diferencia de Elo a ±1000
# --------------------------------------------------------------------------- #


def test_clip_elo_diferencia_absurda_no_rompe_calculo() -> None:
    """Con Elos absurdamente dispares, el clip a ±1000 evita overflow en 10^(x/400)."""
    elo = {"gigante": 99999.0, "enano": 1.0}
    partido = _played("gigante", "enano", 3, 0, dt.date(2026, 4, 1))
    cfg = _cfg(alpha=0.0)
    # No debe lanzar OverflowError ni NaN
    snaps = compute_strengths(elo, [partido], {}, {}, _TODAY, cfg)
    assert math.isfinite(snaps["gigante"].form_rating)
    assert math.isfinite(snaps["enano"].form_rating)


# --------------------------------------------------------------------------- #
# effective_strengths
# --------------------------------------------------------------------------- #


def test_effective_strengths_extrae_r_eff() -> None:
    """effective_strengths devuelve {team_id: r_eff} correctamente."""
    elo = {"a": 1500.0, "b": 1400.0}
    cfg = _cfg(alpha=1.0)
    snaps = compute_strengths(elo, [], {}, {}, _TODAY, cfg)
    result = effective_strengths(snaps)
    assert result == {"a": pytest.approx(1500.0), "b": pytest.approx(1400.0)}


# --------------------------------------------------------------------------- #
# form_component y r_eff formula
# --------------------------------------------------------------------------- #


def test_r_eff_formula_exacta() -> None:
    """r_eff = alpha*E + (1-alpha)*F + delta_coach + delta_injuries."""
    snap = StrengthSnapshot(
        team="a",
        as_of=_TODAY,
        elo_base=1500.0,
        form_rating=1550.0,
        n_form_matches=5,
        delta_coach=15.0,
        delta_injuries=-10.0,
        alpha=0.6,
    )
    expected = 0.6 * 1500.0 + 0.4 * 1550.0 + 15.0 + (-10.0)
    assert snap.r_eff == pytest.approx(expected)


def test_form_component_formula_exacta() -> None:
    """form_component = (1 - alpha) * (form_rating - elo_base)."""
    snap = StrengthSnapshot(
        team="a",
        as_of=_TODAY,
        elo_base=1500.0,
        form_rating=1560.0,
        n_form_matches=3,
        delta_coach=0.0,
        delta_injuries=0.0,
        alpha=0.4,
    )
    expected = (1.0 - 0.4) * (1560.0 - 1500.0)
    assert snap.form_component == pytest.approx(expected)


# --------------------------------------------------------------------------- #
# _coach_bump helper directo
# --------------------------------------------------------------------------- #


def test_coach_bump_sin_cambios_es_cero() -> None:
    assert _coach_bump([], [], _TODAY, 25.0, 6) == pytest.approx(0.0)


def test_coach_bump_con_varios_cambios_solo_el_mas_reciente() -> None:
    d1 = dt.date(2026, 1, 1)
    d2 = dt.date(2026, 3, 1)
    changes: list[tuple[dt.date, float | None]] = [(d1, 100.0), (d2, 50.0)]
    result = _coach_bump(changes, [], _TODAY, 25.0, 6)
    # El más reciente es d2 con bump=50
    assert result == pytest.approx(50.0)


def test_performance_rating_clip_a_1000() -> None:
    """_performance_rating no lanza OverflowError con diferencias absurdas."""
    match = _played("a", "b", 2, 1, _TODAY - dt.timedelta(days=1))
    cfg = _cfg()
    result = _performance_rating(
        match, team_is_home=True, elo_team=99999.0, elo_opp=1.0, config=cfg
    )
    assert math.isfinite(result)
