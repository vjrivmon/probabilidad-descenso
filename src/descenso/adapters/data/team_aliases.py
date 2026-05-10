"""Mapeo único de nombres de equipo entre fuentes (clubelo / understat / fbref / openfootball)."""

from __future__ import annotations

from pathlib import Path

import yaml

from descenso.domain.team import Team

# Fuentes externas soportadas -> atributo del modelo Team con el alias correspondiente.
SOURCE_FIELDS: dict[str, str] = {
    "clubelo": "clubelo_name",
    "understat": "understat_name",
    "fbref": "fbref_name",
    "openfootball": "openfootball_name",
}


class TeamAliasError(ValueError):
    """Un nombre de una fuente externa no está en el mapeo `data/team_aliases.yaml`."""


def load_teams(path: Path) -> list[Team]:
    """Carga la tabla de equipos/alias. Estructura del YAML: lista de dicts con
    id, name y los *_name de cada fuente."""
    if not path.exists():
        raise FileNotFoundError(f"falta el fichero de alias de equipos: {path}")
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or []
    except yaml.YAMLError as exc:
        raise TeamAliasError(f"{path} no es un YAML válido: {exc}") from exc
    if not isinstance(raw, list):
        raise TeamAliasError(f"{path} debe ser una lista de equipos, no {type(raw).__name__}")
    teams = [Team.model_validate(item) for item in raw]
    ids = [t.id for t in teams]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise TeamAliasError(f"{path}: ids de equipo repetidos: {sorted(dup)}")
    return teams


def resolve_from_source(teams: list[Team], source: str, external_name: str) -> Team:
    """Devuelve el Team cuyo alias en `source` coincide con `external_name`.

    Levanta TeamAliasError si la fuente es desconocida o si ningún equipo conocido
    tiene ese alias (nombrando el alias huérfano, para que el usuario lo añada al
    fichero de mapeo).
    """
    if source not in SOURCE_FIELDS:
        raise TeamAliasError(
            f"fuente de datos desconocida {source!r}; conocidas: {sorted(SOURCE_FIELDS)}"
        )
    field = SOURCE_FIELDS[source]
    needle = external_name.strip()
    for team in teams:
        alias = getattr(team, field)
        if alias is not None and alias.strip() == needle:
            return team
    raise TeamAliasError(
        f"el nombre {external_name!r} de la fuente {source!r} no está en el mapeo de equipos: "
        f"añade '{field}: {external_name}' al equipo correspondiente en data/team_aliases.yaml"
    )
