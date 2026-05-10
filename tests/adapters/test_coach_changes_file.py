"""Tests del adaptador CoachChangesFile (CP2).

No hace IO de red; usa ficheros temporales con tmp_path.
"""

from __future__ import annotations

import datetime as dt

import pytest

from descenso.adapters.data.coach_changes_file import CoachChangesFile

# Fecha "hoy" de referencia que usamos para verificar que los tests son
# deterministas. CoachChangesFile usa dt.date.today() internamente, pero
# los datos que usamos en tests siempre tienen fechas pasadas (2026-01-xx) o
# futuras respecto a la fecha real de hoy (2026-12-xx).

_PAST = dt.date.today() - dt.timedelta(days=30)
_FUTURE = dt.date.today() + dt.timedelta(days=30)


def _yaml_past() -> str:
    return _PAST.isoformat()


def _yaml_future() -> str:
    return _FUTURE.isoformat()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _write(tmp_path: object, content: str) -> CoachChangesFile:
    from pathlib import Path

    path = Path(str(tmp_path)) / "coach_changes.yaml"
    path.write_text(content, encoding="utf-8")
    return CoachChangesFile(path)


# --------------------------------------------------------------------------- #
# golden path: YAML válido
# --------------------------------------------------------------------------- #


def test_yaml_valido_devuelve_cambios_y_bajas(tmp_path: object) -> None:
    """YAML bien formado con coach_changes e injuries -> dicts correctos."""
    past_iso = _yaml_past()
    content = f"""
coach_changes:
  - team: real-oviedo
    date: {past_iso}
    new_coach: Nuevo Mister
    elo_bump: 25
injuries:
  - team: levante
    as_of: {past_iso}
    elo_delta: -20
"""
    ccf = _write(tmp_path, content)
    cambios, ajustes = ccf.load()
    assert "real-oviedo" in cambios
    assert len(cambios["real-oviedo"]) == 1
    _, bump = cambios["real-oviedo"][0]
    assert bump == pytest.approx(25.0)
    assert "levante" in ajustes
    assert ajustes["levante"] == pytest.approx(-20.0)


def test_elo_bump_none_se_devuelve_como_none(tmp_path: object) -> None:
    """Si no hay elo_bump, el valor en la lista es None (el caller usará el default)."""
    past_iso = _yaml_past()
    content = f"""
coach_changes:
  - team: celta-vigo
    date: {past_iso}
    new_coach: Sin Bump
"""
    ccf = _write(tmp_path, content)
    cambios, _ = ccf.load()
    _fecha, bump = cambios["celta-vigo"][0]
    assert bump is None


# --------------------------------------------------------------------------- #
# fechas futuras: se ignoran con warning
# --------------------------------------------------------------------------- #


def test_fecha_futura_coach_change_ignorada(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Un cambio de entrenador con fecha futura se ignora con WARNING."""
    future_iso = _yaml_future()
    content = f"""
coach_changes:
  - team: real-oviedo
    date: {future_iso}
    elo_bump: 30
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        cambios, _ = ccf.load()
    assert "real-oviedo" not in cambios
    assert any("futura" in r.message for r in caplog.records)


def test_fecha_futura_injury_ignorada(tmp_path: object, caplog: pytest.LogCaptureFixture) -> None:
    """Una entrada de bajas con fecha futura se ignora con WARNING."""
    future_iso = _yaml_future()
    content = f"""
injuries:
  - team: levante
    as_of: {future_iso}
    elo_delta: -20
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        _, ajustes = ccf.load()
    assert "levante" not in ajustes
    assert any("futura" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# entradas malformadas: se ignoran con warning, las buenas salen
# --------------------------------------------------------------------------- #


def test_fecha_malformada_se_ignora_las_buenas_salen(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Una entrada con fecha no ISO se ignora; las bien formadas salen."""
    past_iso = _yaml_past()
    content = f"""
coach_changes:
  - team: equipo-bueno
    date: {past_iso}
    elo_bump: 20
  - team: equipo-malo
    date: "no-es-una-fecha"
    elo_bump: 15
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        cambios, _ = ccf.load()
    assert "equipo-bueno" in cambios
    assert "equipo-malo" not in cambios


def test_team_ausente_se_ignora(tmp_path: object, caplog: pytest.LogCaptureFixture) -> None:
    """Entrada sin campo 'team' se ignora con warning."""
    past_iso = _yaml_past()
    content = f"""
coach_changes:
  - date: {past_iso}
    elo_bump: 10
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        cambios, _ = ccf.load()
    assert cambios == {}


def test_team_vacio_se_ignora(tmp_path: object, caplog: pytest.LogCaptureFixture) -> None:
    """Entrada con team='' se ignora con warning."""
    past_iso = _yaml_past()
    content = f"""
coach_changes:
  - team: ""
    date: {past_iso}
    elo_bump: 10
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        cambios, _ = ccf.load()
    assert cambios == {}


def test_elo_bump_no_numerico_se_ignora_usa_none(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """elo_bump no numérico provoca warning; la entrada sale con bump=None."""
    past_iso = _yaml_past()
    content = f"""
coach_changes:
  - team: equipo-x
    date: {past_iso}
    elo_bump: "no-es-numero"
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        cambios, _ = ccf.load()
    # Sí debe salir (con bump=None)
    assert "equipo-x" in cambios
    _, bump = cambios["equipo-x"][0]
    assert bump is None


def test_elo_delta_no_numerico_injury_se_ignora(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """elo_delta no numérico en injuries -> la entrada se ignora con warning."""
    past_iso = _yaml_past()
    content = f"""
injuries:
  - team: equipo-y
    as_of: {past_iso}
    elo_delta: "hola"
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        _, ajustes = ccf.load()
    assert "equipo-y" not in ajustes


def test_entrada_no_dict_en_lista_se_ignora(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Una entrada que no es un dict (p.ej. un string) se ignora con warning."""
    content = """
coach_changes:
  - "esto-no-es-un-dict"
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        cambios, _ = ccf.load()
    assert cambios == {}


# --------------------------------------------------------------------------- #
# injuries: varias del mismo equipo -> gana la más reciente
# --------------------------------------------------------------------------- #


def test_injuries_varias_del_mismo_equipo_gana_la_mas_reciente(tmp_path: object) -> None:
    """Si hay varias entradas de bajas para el mismo equipo, gana la más reciente."""
    past1 = (dt.date.today() - dt.timedelta(days=60)).isoformat()
    past2 = (dt.date.today() - dt.timedelta(days=10)).isoformat()
    content = f"""
injuries:
  - team: atletico-madrid
    as_of: {past1}
    elo_delta: -10
  - team: atletico-madrid
    as_of: {past2}
    elo_delta: -35
"""
    ccf = _write(tmp_path, content)
    _, ajustes = ccf.load()
    # La más reciente es past2 con elo_delta=-35
    assert ajustes["atletico-madrid"] == pytest.approx(-35.0)


# --------------------------------------------------------------------------- #
# fichero inexistente -> ({}, {})
# --------------------------------------------------------------------------- #


def test_fichero_inexistente_devuelve_dicts_vacios(tmp_path: object) -> None:
    """Si el fichero no existe, load() devuelve ({}, {}) sin error."""
    from pathlib import Path

    path = Path(str(tmp_path)) / "no_existe.yaml"
    ccf = CoachChangesFile(path)
    cambios, ajustes = ccf.load()
    assert cambios == {}
    assert ajustes == {}


# --------------------------------------------------------------------------- #
# YAML sintácticamente roto -> ValueError con nombre del fichero
# --------------------------------------------------------------------------- #


def test_yaml_roto_levanta_value_error_con_nombre_fichero(tmp_path: object) -> None:
    """YAML sintácticamente inválido -> ValueError con el nombre del fichero."""
    from pathlib import Path

    path = Path(str(tmp_path)) / "roto.yaml"
    path.write_text("coach_changes:\n  - {fecha: [unclosed", encoding="utf-8")
    ccf = CoachChangesFile(path)
    with pytest.raises(ValueError, match=r"roto\.yaml"):
        ccf.load()


# --------------------------------------------------------------------------- #
# YAML con valor no-dict en la raíz -> ValueError
# --------------------------------------------------------------------------- #


def test_yaml_raiz_no_dict_levanta_value_error(tmp_path: object) -> None:
    """Si la raíz del YAML no es un dict, lanza ValueError."""
    content = "- elemento1\n- elemento2\n"
    from pathlib import Path

    path = Path(str(tmp_path)) / "lista.yaml"
    path.write_text(content, encoding="utf-8")
    ccf = CoachChangesFile(path)
    with pytest.raises(ValueError):
        ccf.load()


# --------------------------------------------------------------------------- #
# múltiples cambios: ordenados por fecha (ascendente)
# --------------------------------------------------------------------------- #


def test_multiples_cambios_ordenados_por_fecha(tmp_path: object) -> None:
    """La lista de cambios por equipo está ordenada por fecha ascendente."""
    past1 = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    past2 = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    content = f"""
coach_changes:
  - team: sevilla
    date: {past2}
    elo_bump: 30
  - team: sevilla
    date: {past1}
    elo_bump: 20
"""
    ccf = _write(tmp_path, content)
    cambios, _ = ccf.load()
    fechas = [fecha for fecha, _ in cambios["sevilla"]]
    assert fechas == sorted(fechas)


# --------------------------------------------------------------------------- #
# YAML vacío
# --------------------------------------------------------------------------- #


def test_yaml_vacio_devuelve_dicts_vacios(tmp_path: object) -> None:
    """Un YAML vacío (o solo comentarios) -> ({}, {})."""
    content = "# sin datos\n"
    ccf = _write(tmp_path, content)
    cambios, ajustes = ccf.load()
    assert cambios == {}
    assert ajustes == {}


# --------------------------------------------------------------------------- #
# coach_changes no es lista: se ignora con warning
# --------------------------------------------------------------------------- #


def test_coach_changes_no_lista_se_ignora_con_warning(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Si coach_changes no es una lista (es un dict), se ignora con warning."""
    content = """
coach_changes:
  team: real-oviedo
  date: 2026-01-01
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        cambios, _ = ccf.load()
    assert cambios == {}
    assert any("lista" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# injuries: entrada no-dict
# --------------------------------------------------------------------------- #


def test_injuries_entrada_no_dict_se_ignora(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Una entrada de injuries que no es un dict se ignora con warning."""
    content = """
injuries:
  - "esto-no-es-un-dict"
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        _, ajustes = ccf.load()
    assert ajustes == {}
    assert any("injuries" in r.message for r in caplog.records)


def test_injuries_team_ausente_se_ignora(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Entrada de injuries sin campo team se ignora con warning."""
    past_iso = _yaml_past()
    content = f"""
injuries:
  - as_of: {past_iso}
    elo_delta: -10
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        _, ajustes = ccf.load()
    assert ajustes == {}


def test_injuries_as_of_ausente_se_ignora(
    tmp_path: object, caplog: pytest.LogCaptureFixture
) -> None:
    """Entrada de injuries sin campo as_of se ignora."""
    content = """
injuries:
  - team: levante
    elo_delta: -10
"""
    import logging

    ccf = _write(tmp_path, content)
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.coach_changes_file"):
        _, ajustes = ccf.load()
    assert ajustes == {}
    assert any("ausente" in r.message for r in caplog.records)
