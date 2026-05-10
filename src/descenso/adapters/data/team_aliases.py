"""Mapeo único de nombres de equipo entre fuentes (clubelo / understat / fbref / id interno)."""

from __future__ import annotations

from pathlib import Path

import yaml

from descenso.domain.team import Team


class TeamAliasError(ValueError):
    """Un nombre de una fuente externa no está en el mapeo `data/team_aliases.yaml`."""


def load_teams(path: Path) -> list[Team]:
    """Carga la tabla de equipos/alias. Estructura del YAML: lista de dicts con
    id, name, clubelo_name, understat_name, fbref_name."""
    if not path.exists():
        raise FileNotFoundError(f"falta el fichero de alias de equipos: {path}")
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or []
    return [Team.model_validate(item) for item in raw]


def resolve_from_source(teams: list[Team], source: str, external_name: str) -> Team:
    """Devuelve el Team cuyo alias en `source` coincide con `external_name`.

    Levanta TeamAliasError si ningún equipo conocido tiene ese alias.
    """
    raise NotImplementedError  # Fase 7
