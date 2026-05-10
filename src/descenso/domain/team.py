"""La entidad Team."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Team(BaseModel):
    """Un equipo de LaLiga, con sus identificadores en las distintas fuentes."""

    id: str = Field(description="slug interno estable, p.ej. 'real-oviedo'")
    name: str = Field(description="nombre para mostrar, p.ej. 'Real Oviedo'")
    clubelo_name: str | None = Field(default=None, description="nombre en clubelo.com")
    understat_name: str | None = Field(default=None, description="nombre/id en Understat")
    fbref_name: str | None = Field(default=None, description="nombre en FBref")
    elo_base: float | None = Field(default=None, description="último Elo de clubelo")

    model_config = {"frozen": True}
