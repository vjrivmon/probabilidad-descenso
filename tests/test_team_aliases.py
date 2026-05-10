"""Tests adicionales del módulo team_aliases (cubre líneas aún no alcanzadas)."""

from __future__ import annotations

from pathlib import Path

import pytest

from descenso.adapters.data.team_aliases import TeamAliasError, load_teams, resolve_from_source
from descenso.domain.team import Team

# --------------------------------------------------------------------------- #
# load_teams — errores de fichero
# --------------------------------------------------------------------------- #


def test_load_teams_falta_fichero(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="falta el fichero"):
        load_teams(tmp_path / "no_existe.yaml")


def test_load_teams_yaml_malformado(tmp_path: Path) -> None:
    f = tmp_path / "aliases.yaml"
    f.write_text("clave: : : valor incorrecto\n", encoding="utf-8")
    with pytest.raises(TeamAliasError, match="YAML válido"):
        load_teams(f)


def test_load_teams_no_es_lista(tmp_path: Path) -> None:
    f = tmp_path / "aliases.yaml"
    f.write_text("id: barcelona\nname: FC Barcelona\n", encoding="utf-8")
    with pytest.raises(TeamAliasError, match="lista de equipos"):
        load_teams(f)


def test_load_teams_ids_duplicados(tmp_path: Path) -> None:
    f = tmp_path / "aliases.yaml"
    f.write_text(
        "- id: barcelona\n  name: FC Barcelona\n" "- id: barcelona\n  name: FC Barcelona 2\n",
        encoding="utf-8",
    )
    with pytest.raises(TeamAliasError, match="repetidos"):
        load_teams(f)


def test_load_teams_yaml_vacio_devuelve_lista_vacia(tmp_path: Path) -> None:
    f = tmp_path / "aliases.yaml"
    f.write_text("", encoding="utf-8")
    teams = load_teams(f)
    assert teams == []


def test_load_teams_carga_equipos_correctamente(tmp_path: Path) -> None:
    f = tmp_path / "aliases.yaml"
    f.write_text(
        "- id: barcelona\n  name: FC Barcelona\n  clubelo_name: Barcelona\n",
        encoding="utf-8",
    )
    teams = load_teams(f)
    assert len(teams) == 1
    assert teams[0].id == "barcelona"
    assert teams[0].clubelo_name == "Barcelona"


# --------------------------------------------------------------------------- #
# resolve_from_source — fuentes conocidas / desconocidas
# --------------------------------------------------------------------------- #


def _equipo_completo() -> Team:
    return Team(
        id="barcelona",
        name="FC Barcelona",
        clubelo_name="Barcelona",
        understat_name="Barcelona",
        fbref_name="Barcelona",
        openfootball_name="FC Barcelona",
    )


def test_resolve_from_source_todas_las_fuentes_conocidas() -> None:
    equipo = _equipo_completo()
    for fuente, alias in [
        ("clubelo", "Barcelona"),
        ("understat", "Barcelona"),
        ("fbref", "Barcelona"),
        ("openfootball", "FC Barcelona"),
    ]:
        result = resolve_from_source([equipo], fuente, alias)
        assert result.id == "barcelona"


def test_resolve_from_source_espacio_extra_en_nombre_externo() -> None:
    """El alias externo con espacios extra al inicio/final debe resolverse igual."""
    equipo = _equipo_completo()
    result = resolve_from_source([equipo], "clubelo", "  Barcelona  ")
    assert result.id == "barcelona"


def test_resolve_from_source_fuente_desconocida_menciona_fuentes_validas() -> None:
    equipo = _equipo_completo()
    with pytest.raises(TeamAliasError, match="transfermarkt"):
        resolve_from_source([equipo], "transfermarkt", "Barcelona")


def test_resolve_from_source_alias_huerfano_nombra_el_alias() -> None:
    equipo = _equipo_completo()
    with pytest.raises(TeamAliasError, match="Cádiz CF"):
        resolve_from_source([equipo], "openfootball", "Cádiz CF")


def test_resolve_from_source_equipo_con_alias_none_no_resuelve() -> None:
    """Un equipo con clubelo_name=None no debe matchear ningún nombre externo."""
    equipo = Team(id="nuevo", name="Nuevo FC", clubelo_name=None)
    with pytest.raises(TeamAliasError):
        resolve_from_source([equipo], "clubelo", "Nuevo")


def test_resolve_from_source_lista_vacia_levanta_error() -> None:
    with pytest.raises(TeamAliasError):
        resolve_from_source([], "openfootball", "FC Barcelona")
