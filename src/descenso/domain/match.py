"""La entidad Match (un partido, jugado o pendiente)."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, model_validator


class MatchStatus(StrEnum):
    PLAYED = "played"
    PENDING = "pending"


class Match(BaseModel):
    """Un partido de liga. `home_goals`/`away_goals` son None si está pendiente."""

    season: int  # año de inicio de temporada, p.ej. 2025 para 2025-26
    gameweek: int  # jornada 1..38 (etiqueta; lo que importa es el par de equipos)
    date: dt.date | None = None
    home_team: str  # Team.id
    away_team: str  # Team.id
    home_goals: int | None = None
    away_goals: int | None = None
    home_xg: float | None = None
    away_xg: float | None = None
    is_fixed: bool = False  # el usuario forzó este resultado en `simulate`

    @property
    def status(self) -> MatchStatus:
        played = self.home_goals is not None and self.away_goals is not None
        return MatchStatus.PLAYED if played else MatchStatus.PENDING

    @property
    def key(self) -> tuple[int, str, str]:
        """Identidad de deduplicación: temporada + equipos (NO jornada)."""
        return (self.season, self.home_team, self.away_team)

    @model_validator(mode="after")
    def _check_goals(self) -> Match:
        for g in (self.home_goals, self.away_goals):
            if g is not None and (g < 0 or g > 20):
                raise ValueError(f"marcador fuera de rango razonable: {g}")
        if (self.home_goals is None) != (self.away_goals is None):
            raise ValueError("un partido tiene los dos goles o ninguno")
        if self.home_team == self.away_team:
            raise ValueError("un equipo no puede jugar contra sí mismo")
        return self
