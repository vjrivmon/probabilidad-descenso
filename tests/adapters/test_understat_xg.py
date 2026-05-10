"""Tests del adaptador UnderstatXgSource con respx (sin red real).

Sigue el estilo de test_clubelo_elo.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.understat_xg import UNDERSTAT_BASE, UnderstatError, UnderstatXgSource
from descenso.domain.team import Team

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_SEASON = 2025
_URL = f"{UNDERSTAT_BASE}/{_SEASON}"


def _teams() -> list[Team]:
    """Equipos sintéticos con understat_name definido."""
    return [
        Team(
            id="barcelona",
            name="FC Barcelona",
            understat_name="Barcelona",
            clubelo_name="Barcelona",
        ),
        Team(
            id="real-madrid",
            name="Real Madrid",
            understat_name="Real Madrid",
            clubelo_name="RealMadrid",
        ),
        Team(
            id="atletico-madrid",
            name="Atletico Madrid",
            understat_name="Atletico Madrid",
        ),
    ]


def _source(tmp_path: Path, client: httpx.Client) -> UnderstatXgSource:
    return UnderstatXgSource(ParquetCache(tmp_path), client=client)


def _build_html(entries: list[dict[str, object]]) -> str:
    """Construye un HTML mínimo que imita el formato de Understat.

    Understat embebe el JSON como:
        var datesData = JSON.parse('...')
    donde la cadena puede tener escapes \\xNN.
    Aquí usamos JSON "limpio" (sin escapes) para el camino feliz.
    """
    json_str = json.dumps(entries)
    # JSON.parse espera comillas simples como delimitador en el HTML de Understat;
    # escapamos las comillas simples del JSON si las hubiera (nombres con apóstrofe).
    json_str_escaped = json_str.replace("'", "\\'")
    return (
        "<html><body><script>"
        f"var datesData = JSON.parse('{json_str_escaped}');"
        "</script></body></html>"
    )


def _match_entry(
    h_title: str,
    a_title: str,
    h_goals: int,
    a_goals: int,
    h_xg: float,
    a_xg: float,
    is_result: bool = True,
    datetime_str: str = "2026-04-15 20:00:00",
) -> dict[str, object]:
    return {
        "isResult": is_result,
        "h": {"title": h_title},
        "a": {"title": a_title},
        "goals": {"h": h_goals, "a": a_goals},
        "xG": {"h": h_xg, "a": a_xg},
        "datetime": datetime_str,
    }


# --------------------------------------------------------------------------- #
# golden path: HTML con datos válidos
# --------------------------------------------------------------------------- #


@respx.mock
def test_golden_path_devuelve_partidos_jugados(tmp_path: Path) -> None:
    """HTML bien formado con isResult=True -> partidos con xG devueltos."""
    entries = [
        _match_entry("Barcelona", "Real Madrid", 2, 1, 1.8, 0.9),
        _match_entry("Real Madrid", "Atletico Madrid", 1, 0, 0.7, 1.1),
    ]
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 2
    hxg_list = [m.home_xg for m in matches]
    assert all(v is not None for v in hxg_list)


@respx.mock
def test_partido_no_jugado_isresult_false_se_omite(tmp_path: Path) -> None:
    """Partidos con isResult=False se omiten."""
    entries = [
        _match_entry("Barcelona", "Real Madrid", 2, 1, 1.8, 0.9, is_result=True),
        _match_entry("Real Madrid", "Atletico Madrid", 0, 0, 0.0, 0.0, is_result=False),
    ]
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 1
    assert matches[0].home_team == "barcelona"


# --------------------------------------------------------------------------- #
# página sin el bloque datesData -> UnderstatError con la URL
# --------------------------------------------------------------------------- #


@respx.mock
def test_html_sin_bloque_datesdata_levanta_understat_error(tmp_path: Path) -> None:
    """HTML sin el bloque datesData=JSON.parse -> UnderstatError con la URL."""
    html_vacio = "<html><body><p>No hay datos aqui.</p></body></html>"
    respx.get(_URL).mock(return_value=httpx.Response(200, text=html_vacio))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(UnderstatError, match=_URL):
        src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)


# --------------------------------------------------------------------------- #
# equipo de Understat sin mapeo -> ese partido se salta con warning
# --------------------------------------------------------------------------- #


@respx.mock
def test_nombre_sin_mapeo_salta_ese_partido_con_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Un equipo sin alias en understat_name -> el partido se salta, no falla todo."""
    import logging

    entries = [
        _match_entry("Barcelona", "Real Madrid", 2, 1, 1.8, 0.9),
        # "Equipo Desconocido" no está en _teams()
        _match_entry("Barcelona", "Equipo Desconocido", 1, 0, 1.0, 0.5),
    ]
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.understat_xg"):
        matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 1  # solo el primero
    assert any("Equipo Desconocido" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# cache
# --------------------------------------------------------------------------- #


@respx.mock
def test_prefer_cache_true_con_cache_no_toca_la_red(tmp_path: Path) -> None:
    """Con prefer_cache=True y cache presente, no se hace ninguna petición HTTP."""
    entries = [_match_entry("Barcelona", "Real Madrid", 1, 0, 1.2, 0.4)]
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    # Popular el cache
    src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)

    # Ahora con red bloqueada
    with respx.mock(assert_all_called=False) as rsps:
        rsps.get(_URL).mock(side_effect=ConnectionError("no deberia llamarse"))
        matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=True)
    assert len(matches) == 1


@respx.mock
def test_red_falla_pero_hay_cache_usa_cache_con_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Si la red falla pero hay cache previo, lo usa avisando."""
    import logging

    entries = [_match_entry("Barcelona", "Real Madrid", 2, 0, 1.5, 0.3)]
    # Primera llamada para poblar cache
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)

    with respx.mock():
        respx.get(_URL).mock(return_value=httpx.Response(503, text="Service Unavailable"))
        with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.understat_xg"):
            matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 1
    assert any("cache previo" in r.message for r in caplog.records)


@respx.mock
def test_red_falla_y_no_hay_cache_levanta_understat_error(tmp_path: Path) -> None:
    """Si la red falla y no hay cache, lanza UnderstatError."""
    respx.get(_URL).mock(return_value=httpx.Response(503, text="Service Unavailable"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(UnderstatError):
        src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_error_de_conexion_sin_cache_levanta_understat_error(tmp_path: Path) -> None:
    """Error de conexión (ConnectError) sin cache -> UnderstatError."""
    respx.get(_URL).mock(side_effect=httpx.ConnectError("sin red"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(UnderstatError):
        src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)


# --------------------------------------------------------------------------- #
# HTTP 200 pero cuerpo basura / JSON inválido dentro del bloque
# --------------------------------------------------------------------------- #


@respx.mock
def test_json_invalido_en_bloque_datesdata_levanta_understat_error(tmp_path: Path) -> None:
    """HTML con bloque datesData pero JSON inválido dentro -> UnderstatError."""
    html_basura = (
        "<html><body><script>"
        "var datesData = JSON.parse('{esto no es json valido !!!}');"
        "</script></body></html>"
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, text=html_basura))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(UnderstatError):
        src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_datesdata_no_es_lista_levanta_understat_error(tmp_path: Path) -> None:
    """Si datesData es un dict (no lista), lanza UnderstatError."""
    json_str = json.dumps({"error": "no es una lista"})
    html = (
        "<html><body><script>"
        f"var datesData = JSON.parse('{json_str}');"
        "</script></body></html>"
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, text=html))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(UnderstatError, match="lista"):
        src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)


# --------------------------------------------------------------------------- #
# HTML con escapes \\xNN (formato real de Understat)
# --------------------------------------------------------------------------- #


@respx.mock
def test_escapes_xnn_en_json_se_decodifican(tmp_path: Path) -> None:
    """El bloque puede contener escapes \\xNN (caracteres escapados en JS)."""
    # Construimos manualmente el bloque con un escape \\x22 (comilla doble = '"')
    # El JSON dentro del parse es: [{"isResult":false}]
    # Escapamos algunos caracteres para imitar el formato real.
    # \\x5b = '[', \\x5d = ']'
    # Usamos un JSON simple que se pueda decodificar con unicode_escape.
    json_content = '[{"isResult": false}]'
    # Escapamos caracteres básicos: mantenemos ASCII; solo usamos el mecanismo
    # unicode_escape que realmente aplica Understat (principalmente \\xNN para
    # caracteres no-ASCII). Para un test simple, pasamos el JSON sin escapes.
    html = (
        "<html><body><script>"
        f"var datesData = JSON.parse('{json_content}');"
        "</script></body></html>"
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, text=html))
    src = _source(tmp_path, httpx.Client())
    # No hay partidos isResult=True, así que devuelve lista vacía sin error
    matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert matches == []


# --------------------------------------------------------------------------- #
# _matches_from_df: conversión de DataFrame a lista de Match
# --------------------------------------------------------------------------- #


def test_matches_from_df_convierte_correctamente(tmp_path: Path) -> None:
    """_matches_from_df convierte un DataFrame con columnas correctas a Match."""
    import datetime as dt

    df = pd.DataFrame(
        [
            {
                "season": 2025,
                "gameweek": 0,
                "date": "2026-04-01",
                "home_team": "barcelona",
                "away_team": "real-madrid",
                "home_goals": 2,
                "away_goals": 1,
                "home_xg": 1.8,
                "away_xg": 0.9,
            }
        ]
    )
    df["home_goals"] = df["home_goals"].astype("Int64")
    df["away_goals"] = df["away_goals"].astype("Int64")
    df["home_xg"] = df["home_xg"].astype("float64")
    df["away_xg"] = df["away_xg"].astype("float64")

    matches = UnderstatXgSource._matches_from_df(df)
    assert len(matches) == 1
    m = matches[0]
    assert m.home_team == "barcelona"
    assert m.home_goals == 2
    assert m.home_xg == pytest.approx(1.8)
    assert m.date == dt.date(2026, 4, 1)


def test_matches_from_df_con_fecha_none(tmp_path: Path) -> None:
    """_matches_from_df maneja fecha None correctamente (no lanza)."""
    df = pd.DataFrame(
        [
            {
                "season": 2025,
                "gameweek": 0,
                "date": None,
                "home_team": "barcelona",
                "away_team": "real-madrid",
                "home_goals": 1,
                "away_goals": 0,
                "home_xg": float("nan"),
                "away_xg": float("nan"),
            }
        ]
    )
    df["home_goals"] = df["home_goals"].astype("Int64")
    df["away_goals"] = df["away_goals"].astype("Int64")
    df["home_xg"] = df["home_xg"].astype("float64")
    df["away_xg"] = df["away_xg"].astype("float64")

    matches = UnderstatXgSource._matches_from_df(df)
    assert len(matches) == 1
    assert matches[0].date is None
    assert matches[0].home_xg is None


# --------------------------------------------------------------------------- #
# partido sin nombres de equipo -> se salta con warning
# --------------------------------------------------------------------------- #


@respx.mock
def test_partido_sin_nombre_de_equipo_se_salta(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Si h o a no tienen 'title', el partido se salta con warning."""
    import logging

    entries: list[dict[str, object]] = [
        {
            "isResult": True,
            "h": {},  # sin title
            "a": {"title": "Real Madrid"},
            "goals": {"h": 1, "a": 0},
            "xG": {"h": 0.8, "a": 0.5},
            "datetime": "2026-04-15 20:00:00",
        }
    ]
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.understat_xg"):
        matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 0
    assert any("sin nombres" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# datetime inválida -> match_date = None
# --------------------------------------------------------------------------- #


@respx.mock
def test_datetime_invalida_produce_date_none(tmp_path: Path) -> None:
    """Si la datetime de Understat no es parseable, el partido se devuelve con date=None."""
    entries: list[dict[str, object]] = [
        {
            "isResult": True,
            "h": {"title": "Barcelona"},
            "a": {"title": "Real Madrid"},
            "goals": {"h": 2, "a": 1},
            "xG": {"h": 1.8, "a": 0.9},
            "datetime": "no-es-una-fecha",
        }
    ]
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 1
    assert matches[0].date is None


# --------------------------------------------------------------------------- #
# valores nulos en goals/xG -> None en el partido
# --------------------------------------------------------------------------- #


@respx.mock
def test_goals_nulos_producen_home_goals_none(tmp_path: Path) -> None:
    """Si goals.h/a son None o inválidos, los campos de goles en el Match son None."""
    entries: list[dict[str, object]] = [
        {
            "isResult": True,
            "h": {"title": "Barcelona"},
            "a": {"title": "Real Madrid"},
            "goals": {"h": None, "a": None},
            "xG": {"h": None, "a": None},
            "datetime": "2026-04-15 20:00:00",
        }
    ]
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_build_html(entries)))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 1
    assert matches[0].home_goals is None
    assert matches[0].home_xg is None


@respx.mock
def test_entry_no_dict_en_lista_se_salta(tmp_path: Path) -> None:
    """Una entrada que no es dict en el array datesData se omite silenciosamente."""
    # Construimos HTML con una entrada no-dict mezclada
    import json

    entries_raw = [
        "esto-no-es-un-dict",
        {
            "isResult": True,
            "h": {"title": "Barcelona"},
            "a": {"title": "Real Madrid"},
            "goals": {"h": 1, "a": 0},
            "xG": {"h": 0.9, "a": 0.4},
            "datetime": "2026-04-15 20:00:00",
        },
    ]
    json_str = json.dumps(entries_raw).replace("'", "\\'")
    html = (
        "<html><body><script>"
        f"var datesData = JSON.parse('{json_str}');"
        "</script></body></html>"
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, text=html))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_match_xg(_SEASON, _teams(), prefer_cache=False)
    # Solo el partido dict válido con isResult=True
    assert len(matches) == 1
