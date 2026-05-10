"""Tests del adaptador OpenFootballScheduleSource con respx (sin red real).

Cubre: golden path, caída de red con/sin cache, fixtures_override.csv,
deduplicación de partidos, parseo de marcadores/jornadas/fechas, alias huérfanos.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest
import respx

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.schedule import (
    OPENFOOTBALL_BASE,
    OpenFootballScheduleSource,
    ScheduleError,
    _parse_date,
    _parse_gameweek,
    _parse_score,
    season_slug,
)
from descenso.domain.match import MatchStatus
from descenso.domain.team import Team

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

_SEASON = 2025
_SLUG = season_slug(_SEASON)
_URL = f"{OPENFOOTBALL_BASE}/{_SLUG}/es.1.json"


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
            clubelo_name="Real Madrid",
            openfootball_name="Real Madrid CF",
        ),
        Team(
            id="atletico-madrid",
            name="Atletico de Madrid",
            clubelo_name="Atletico",
            openfootball_name="Club Atletico de Madrid",
        ),
    ]


def _json_response(matches: list[dict]) -> str:  # type: ignore[type-arg]
    return json.dumps({"matches": matches})


def _partido_jugado(
    home: str, away: str, hg: int, ag: int, gw: int = 1, date: str = "2026-01-15"
) -> dict:  # type: ignore[type-arg]
    return {
        "round": f"Matchday {gw}",
        "date": date,
        "team1": home,
        "team2": away,
        "score": {"ft": [hg, ag]},
    }


def _partido_pendiente(home: str, away: str, gw: int = 1) -> dict:  # type: ignore[type-arg]
    return {"round": f"Matchday {gw}", "team1": home, "team2": away}


def _source(tmp_path: Path, client: httpx.Client) -> OpenFootballScheduleSource:
    return OpenFootballScheduleSource(ParquetCache(tmp_path), client=client)


# --------------------------------------------------------------------------- #
# golden path
# --------------------------------------------------------------------------- #


@respx.mock
def test_golden_path_devuelve_matches(tmp_path: Path) -> None:
    data = _json_response(
        [
            _partido_jugado("FC Barcelona", "Real Madrid CF", 2, 1, gw=1),
            _partido_pendiente("Real Madrid CF", "Club Atletico de Madrid", gw=2),
        ]
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, text=data))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 2
    played = [m for m in matches if m.status is MatchStatus.PLAYED]
    pending = [m for m in matches if m.status is MatchStatus.PENDING]
    assert len(played) == 1
    assert len(pending) == 1
    assert played[0].home_team == "barcelona"
    assert played[0].away_team == "real-madrid"
    assert played[0].home_goals == 2 and played[0].away_goals == 1


@respx.mock
def test_golden_path_guarda_en_cache(tmp_path: Path) -> None:
    data = _json_response([_partido_jugado("FC Barcelona", "Real Madrid CF", 1, 0)])
    respx.get(_URL).mock(return_value=httpx.Response(200, text=data))
    cache = ParquetCache(tmp_path)
    src = OpenFootballScheduleSource(cache, client=httpx.Client())
    src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)
    assert cache.has(f"schedule_{_SEASON}")


# --------------------------------------------------------------------------- #
# prefer_cache
# --------------------------------------------------------------------------- #


@respx.mock
def test_prefer_cache_usa_cache_sin_red(tmp_path: Path) -> None:
    data = _json_response([_partido_jugado("FC Barcelona", "Real Madrid CF", 1, 0)])
    respx.get(_URL).mock(return_value=httpx.Response(200, text=data))
    src = _source(tmp_path, httpx.Client())
    # Primer fetch -> guarda en cache
    src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)

    with respx.mock(assert_all_called=False) as rsps:
        rsps.get(_URL).mock(side_effect=ConnectionError("no debería llamarse"))
        matches = src.fetch_schedule(_SEASON, _teams(), prefer_cache=True)
    assert len(matches) == 1


# --------------------------------------------------------------------------- #
# caída de red con cache previo
# --------------------------------------------------------------------------- #


@respx.mock
def test_red_caida_con_cache_usa_cache_y_avisa(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    data = _json_response([_partido_jugado("FC Barcelona", "Real Madrid CF", 1, 0)])
    respx.get(_URL).mock(return_value=httpx.Response(200, text=data))
    src = _source(tmp_path, httpx.Client())
    src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)

    with respx.mock():
        respx.get(_URL).mock(return_value=httpx.Response(503, text="down"))
        with caplog.at_level(logging.WARNING, logger="descenso.adapters.data.schedule"):
            matches = src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)
    assert len(matches) == 1
    assert any("cache previo" in r.message for r in caplog.records)


@respx.mock
def test_red_caida_sin_cache_levanta_schedule_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(503, text="down"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_sin_conexion_sin_cache_levanta_schedule_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(side_effect=httpx.ConnectError("sin red"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="openfootball"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


# --------------------------------------------------------------------------- #
# fixtures_override.csv como fallback de emergencia
# --------------------------------------------------------------------------- #


@respx.mock
def test_fixtures_override_csv_se_usa_cuando_no_hay_cache_ni_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si la red falla y no hay cache, pero existe data/fixtures_override.csv, lo usa."""
    import descenso.adapters.data.schedule as schedule_mod

    override = tmp_path / "fixtures_override.csv"
    # Columnas requeridas: season,gameweek,date,home_team,away_team,home_goals,away_goals
    override.write_text(
        "season,gameweek,date,home_team,away_team,home_goals,away_goals\n"
        "2025,1,2026-01-15,barcelona,real-madrid,2,1\n"
        "2025,2,2026-02-20,atletico-madrid,barcelona,,\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(schedule_mod, "OVERRIDE_FILE", override)

    respx.get(_URL).mock(return_value=httpx.Response(503, text="down"))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)

    assert len(matches) == 2
    jugados = [m for m in matches if m.status is MatchStatus.PLAYED]
    pendientes = [m for m in matches if m.status is MatchStatus.PENDING]
    assert len(jugados) == 1 and len(pendientes) == 1
    assert jugados[0].home_team == "barcelona" and jugados[0].home_goals == 2


@respx.mock
def test_fixtures_override_csv_con_equipos_desconocidos_levanta_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import descenso.adapters.data.schedule as schedule_mod

    override = tmp_path / "fixtures_override.csv"
    override.write_text(
        "season,gameweek,date,home_team,away_team,home_goals,away_goals\n"
        "2025,1,2026-01-15,equipo-inexistente,real-madrid,2,1\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(schedule_mod, "OVERRIDE_FILE", override)

    respx.get(_URL).mock(return_value=httpx.Response(503, text="down"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="desconocidos"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_fixtures_override_csv_ilegible_levanta_schedule_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si el override existe pero no se puede leer (OSError), levanta ScheduleError."""
    from unittest.mock import patch

    import descenso.adapters.data.schedule as schedule_mod

    override = tmp_path / "fixtures_override.csv"
    override.write_text("dummy", encoding="utf-8")
    monkeypatch.setattr(schedule_mod, "OVERRIDE_FILE", override)

    respx.get(_URL).mock(return_value=httpx.Response(503, text="down"))
    src = _source(tmp_path, httpx.Client())

    with (
        patch("pandas.read_csv", side_effect=OSError("permiso denegado")),
        pytest.raises(ScheduleError, match="no se puede leer"),
    ):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_fixtures_override_csv_con_columnas_faltantes_levanta_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import descenso.adapters.data.schedule as schedule_mod

    override = tmp_path / "fixtures_override.csv"
    override.write_text(
        "season,home_team,away_team\n2025,barcelona,real-madrid\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(schedule_mod, "OVERRIDE_FILE", override)

    respx.get(_URL).mock(return_value=httpx.Response(503, text="down"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="columnas"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_sin_red_ni_cache_ni_override_levanta_schedule_error_con_instrucciones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import descenso.adapters.data.schedule as schedule_mod

    override = tmp_path / "fixtures_override_inexistente.csv"
    monkeypatch.setattr(schedule_mod, "OVERRIDE_FILE", override)

    respx.get(_URL).mock(return_value=httpx.Response(503, text="down"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="reintenta con conexión"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


# --------------------------------------------------------------------------- #
# deduplicación de partidos
# --------------------------------------------------------------------------- #


@respx.mock
def test_partido_duplicado_jugado_gana_sobre_pendiente(tmp_path: Path) -> None:
    """Si un partido aparece como pendiente Y como jugado, el jugado prevalece."""
    data = _json_response(
        [
            # primero el pendiente, luego el jugado (orden que testea el sort)
            _partido_pendiente("FC Barcelona", "Real Madrid CF", gw=1),
            _partido_jugado("FC Barcelona", "Real Madrid CF", 3, 1, gw=1),
        ]
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, text=data))
    src = _source(tmp_path, httpx.Client())
    matches = src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)
    # Debe quedar un solo partido (deduplicado) y con resultado
    barca_real = [m for m in matches if m.home_team == "barcelona" and m.away_team == "real-madrid"]
    assert len(barca_real) == 1
    assert barca_real[0].status is MatchStatus.PLAYED
    assert barca_real[0].home_goals == 3


# --------------------------------------------------------------------------- #
# alias huérfanos (nombre de equipo no mapeado)
# --------------------------------------------------------------------------- #


@respx.mock
def test_nombre_equipo_no_mapeado_levanta_schedule_error(tmp_path: Path) -> None:
    """Un nombre de openfootball sin entrada en team_aliases -> ScheduleError con el alias."""
    data = _json_response(
        [_partido_jugado("FC Barcelona", "Cádiz CF", 2, 0)]  # "Cádiz CF" no está en _teams()
    )
    respx.get(_URL).mock(return_value=httpx.Response(200, text=data))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="no está en el mapeo"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


# --------------------------------------------------------------------------- #
# JSON inválido / formato inesperado
# --------------------------------------------------------------------------- #


@respx.mock
def test_json_invalido_levanta_schedule_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text="esto no es json!!!"))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="JSON"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_json_sin_clave_matches_levanta_schedule_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=json.dumps({"rounds": []})))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="matches"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_json_matches_vacio_levanta_schedule_error(tmp_path: Path) -> None:
    respx.get(_URL).mock(return_value=httpx.Response(200, text=json.dumps({"matches": []})))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="matches"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


@respx.mock
def test_partido_sin_team1_levanta_schedule_error(tmp_path: Path) -> None:
    data = _json_response([{"round": "Matchday 1", "team2": "Real Madrid CF"}])
    respx.get(_URL).mock(return_value=httpx.Response(200, text=data))
    src = _source(tmp_path, httpx.Client())
    with pytest.raises(ScheduleError, match="team1"):
        src.fetch_schedule(_SEASON, _teams(), prefer_cache=False)


# --------------------------------------------------------------------------- #
# helpers unitarios de parseo
# --------------------------------------------------------------------------- #


def test_parse_gameweek_con_entero() -> None:
    assert _parse_gameweek(5) == 5


def test_parse_gameweek_con_string_matchday() -> None:
    assert _parse_gameweek("Matchday 12") == 12


def test_parse_gameweek_con_string_sin_numero() -> None:
    assert _parse_gameweek("Final") == 0


def test_parse_gameweek_con_none() -> None:
    assert _parse_gameweek(None) == 0


def test_parse_date_iso() -> None:
    assert _parse_date("2026-01-15") == "2026-01-15"


def test_parse_date_invalida() -> None:
    assert _parse_date("no-es-fecha") is None


def test_parse_date_none() -> None:
    assert _parse_date(None) is None


def test_parse_date_vacia() -> None:
    assert _parse_date("") is None


def test_parse_score_lista_dos_elementos() -> None:
    assert _parse_score({"ft": [2, 1]}) == (2, 1)


def test_parse_score_no_dict() -> None:
    assert _parse_score(None) == (None, None)


def test_parse_score_ft_no_lista() -> None:
    assert _parse_score({"ft": "2-1"}) == (None, None)


def test_parse_score_ft_lista_mal_longitud() -> None:
    assert _parse_score({"ft": [2, 1, 0]}) == (None, None)


def test_parse_score_elementos_no_numericos() -> None:
    assert _parse_score({"ft": ["x", "y"]}) == (None, None)


# --------------------------------------------------------------------------- #
# season_slug
# --------------------------------------------------------------------------- #


def test_season_slug_2025() -> None:
    assert season_slug(2025) == "2025-26"


def test_season_slug_limite_siglo() -> None:
    assert season_slug(1999) == "1999-00"


# --------------------------------------------------------------------------- #
# _coerce_date (función interna de parseo de fechas desde el DataFrame)
# --------------------------------------------------------------------------- #


def test_coerce_date_con_instancia_date() -> None:
    """Si el valor ya es un dt.date, lo devuelve tal cual (rama de isinstance)."""
    import datetime as _dt

    from descenso.adapters.data.schedule import _coerce_date

    d = _dt.date(2026, 3, 15)
    assert _coerce_date(d) == d


def test_coerce_date_con_string_invalido() -> None:
    from descenso.adapters.data.schedule import _coerce_date

    assert _coerce_date("no-es-fecha-valida") is None


def test_coerce_date_con_string_iso() -> None:
    import datetime as _dt

    from descenso.adapters.data.schedule import _coerce_date

    result = _coerce_date("2026-01-15")
    assert result == _dt.date(2026, 1, 15)
