"""Tests del adaptador ClubeloEloSource con respx (sin red real)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import httpx
import pytest
import respx

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.clubelo_elo import CLUBELO_BASE, ClubeloEloSource, ClubeloError
from descenso.domain.team import Team

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_HOY = dt.date(2026, 5, 10)
_URL = f"{CLUBELO_BASE}/{_HOY.isoformat()}"

_CSV_OK = (
    "Rank,Club,Country,Level,Elo,From,To\n"
    "1,Barcelona,ESP,1,1920.5,2026-01-01,2026-12-31\n"
    "2,RealMadrid,ESP,1,1880.0,2026-01-01,2026-12-31\n"
    "5,Oviedo,ESP,1,1350.0,2026-01-01,2026-12-31\n"
)

_CSV_SIN_ELO = "Rank,Club,Country,Level\n1,Barcelona,ESP,1\n"
_CSV_VACIO = "Rank,Club,Country,Level,Elo,From,To\n"


def _teams() -> list[Team]:
    return [
        Team(
            id="barcelona",
            name="FC Barcelona",
            clubelo_name="Barcelona",
            openfootball_name="FC Barcelona",
        ),
        Team(
            id="real-madrid",
            name="Real Madrid",
            clubelo_name="RealMadrid",
            openfootball_name="Real Madrid CF",
        ),
        Team(
            id="real-oviedo",
            name="Real Oviedo",
            clubelo_name="Oviedo",
            openfootball_name="Real Oviedo",
        ),
    ]


def _source(tmp_path: Path, client: httpx.Client) -> ClubeloEloSource:
    return ClubeloEloSource(ParquetCache(tmp_path), client=client)


# --------------------------------------------------------------------------- #
# golden path: respuesta OK
# --------------------------------------------------------------------------- #


@respx.mock
def test_golden_path_devuelve_elo_por_team_id(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_OK))
    src = _source(tmp_path, httpx.Client())
    elo = src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)
    assert elo["barcelona"] == pytest.approx(1920.5)
    assert elo["real-madrid"] == pytest.approx(1880.0)
    assert elo["real-oviedo"] == pytest.approx(1350.0)


@respx.mock
def test_golden_path_guarda_en_cache(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_OK))
    cache = ParquetCache(tmp_path)
    src = ClubeloEloSource(cache, client=httpx.Client())
    src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)
    assert cache.has("clubelo_elo")


# --------------------------------------------------------------------------- #
# prefer_cache: usa el cache sin tocar la red
# --------------------------------------------------------------------------- #


@respx.mock
def test_prefer_cache_usa_cache_sin_red(tmp_path: Path) -> None:
    """Con prefer_cache=True y cache disponible, no se hace ninguna petición HTTP."""
    # Primero populamos el cache con una petición real mockeada
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_OK))
    src = _source(tmp_path, httpx.Client())
    src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)

    # Ahora quitamos el mock (cualquier petición HTTP lanzaría ConnectionError)
    # y pedimos con prefer_cache=True
    with respx.mock(assert_all_called=False) as rsps:
        rsps.get(_URL).mock(side_effect=ConnectionError("no debería llamarse"))
        elo = src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=True)
    assert elo["barcelona"] == pytest.approx(1920.5)


@respx.mock
def test_prefer_cache_sin_cache_va_a_la_red(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_OK))
    src = _source(tmp_path, httpx.Client())
    # No hay cache previo -> debe ir a la red aunque prefer_cache=True
    elo = src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=True)
    assert "barcelona" in elo


# --------------------------------------------------------------------------- #
# clubelo caído — con y sin cache previo
# --------------------------------------------------------------------------- #


@respx.mock
def test_clubelo_caido_con_cache_previo_usa_cache_y_avisa(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Si clubelo falla (5xx) pero hay cache, lo usa avisando con WARNING."""
    # Popular el cache
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_OK))
    src = _source(tmp_path, httpx.Client())
    src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)

    # Simular caída
    with respx.mock():
        respx.get(_URL).mock(return_value=httpx.Response(503, text="Service Unavailable"))
        import logging

        with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.clubelo_elo"):
            elo = src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)
    assert "barcelona" in elo
    assert any("cache previo" in r.message for r in caplog.records)


@respx.mock
def test_clubelo_caido_sin_cache_levanta_clubelo_error(tmp_path: Path) -> None:
    """Si clubelo falla y NO hay cache, lanza ClubeloError con la URL."""
    respx.get(_URL).mock(return_value=httpx.Response(503, text="Service Unavailable"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ClubeloError, match=_URL):
        src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)


@respx.mock
def test_sin_conexion_sin_cache_levanta_clubelo_error(tmp_path: Path) -> None:
    """Error de red (HTTPError) sin cache -> ClubeloError con la URL."""
    respx.get(_URL).mock(side_effect=httpx.ConnectError("sin red"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ClubeloError, match="clubelo"):
        src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)


# --------------------------------------------------------------------------- #
# formato del CSV roto
# --------------------------------------------------------------------------- #


@respx.mock
def test_csv_sin_columna_elo_levanta_clubelo_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_SIN_ELO))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ClubeloError, match="formato esperado"):
        src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)


@respx.mock
def test_csv_vacio_levanta_clubelo_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_VACIO))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ClubeloError, match="formato esperado"):
        src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)


@respx.mock
def test_respuesta_no_csv_levanta_clubelo_error(tmp_path: Path) -> None:
    """Respuesta 200 pero con HTML en vez de CSV."""
    respx.get(_URL).mock(return_value=httpx.Response(200, text="<html>not csv</html>"))
    src = _source(tmp_path, httpx.Client())
    # El HTML puede que lo parsee como CSV de 1 col sin Elo -> formato inválido
    with pytest.raises(ClubeloError):
        src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)


@respx.mock
def test_csv_mal_formado_pandas_parser_error_levanta_clubelo_error(tmp_path: Path) -> None:
    """Si pandas no puede parsear el CSV (ParserError), levanta ClubeloError con la URL."""
    from unittest.mock import patch

    import pandas.errors

    respx.get(_URL).mock(return_value=httpx.Response(200, text="Rank,Club\n1,Barcelona"))
    src = _source(tmp_path, httpx.Client())

    with (
        patch("pandas.read_csv", side_effect=pandas.errors.ParserError("csv roto")),
        pytest.raises(ClubeloError, match="no es un CSV"),
    ):
        src.fetch_current_elo(_teams(), on_date=_HOY, prefer_cache=False)


# --------------------------------------------------------------------------- #
# equipos sin alias en clubelo
# --------------------------------------------------------------------------- #


@respx.mock
def test_equipo_sin_clubelo_name_levanta_clubelo_error(tmp_path: Path) -> None:
    """Un Team con clubelo_name=None debe aparecer en el error de 'no trae Elo para'."""
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_OK))
    equipos_con_huerfano = [*_teams(), Team(id="sin-alias", name="Sin Alias", clubelo_name=None)]
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ClubeloError, match="sin-alias"):
        src.fetch_current_elo(equipos_con_huerfano, on_date=_HOY, prefer_cache=False)


@respx.mock
def test_equipo_no_presente_en_csv_levanta_clubelo_error(tmp_path: Path) -> None:
    """Un Team cuyo clubelo_name no aparece en el CSV -> ClubeloError con el id."""
    respx.get(_URL).mock(return_value=httpx.Response(200, text=_CSV_OK))
    equipos = [*_teams(), Team(id="equipo-fantasma", name="Fantasma", clubelo_name="Fantasma")]
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ClubeloError, match="equipo-fantasma"):
        src.fetch_current_elo(equipos, on_date=_HOY, prefer_cache=False)


# --------------------------------------------------------------------------- #
# fecha on_date: usa hoy por defecto
# --------------------------------------------------------------------------- #


@respx.mock
def test_on_date_none_usa_fecha_de_hoy(tmp_path: Path) -> None:
    """Si on_date=None, la URL debe incluir la fecha actual."""
    today = dt.date.today()
    url_hoy = f"{CLUBELO_BASE}/{today.isoformat()}"
    respx.get(url_hoy).mock(return_value=httpx.Response(200, text=_CSV_OK))
    src = _source(tmp_path, httpx.Client())
    elo = src.fetch_current_elo(_teams(), on_date=None, prefer_cache=False)
    assert "barcelona" in elo
