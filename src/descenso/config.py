"""Carga y validación de `config.yaml` (parámetros del modelo y rutas)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator


class ModelConfig(BaseModel):
    """Parámetros del modelo de fuerza y de la simulación."""

    alpha: float = Field(
        0.5, description="peso del Elo base frente al FormRating (1.0 = modelo puro)"
    )
    form_half_life_days: float = Field(
        75.0, description="vida media del decaimiento temporal de la forma"
    )
    form_window_matches: int = Field(
        15, description="máximo de partidos recientes considerados para la forma"
    )
    xg_blend_beta: float = Field(
        0.6, description="peso de los goles reales frente al xG en el performance rating"
    )
    home_advantage_elo: float = Field(65.0, description="ventaja de campo en puntos Elo")
    draw_base: float = Field(
        0.26, description="probabilidad base de empate (suelo) en el modelo logístico"
    )
    coach_bump_default: float = Field(
        25.0, description="bonus Elo inicial tras un cambio de entrenador"
    )
    coach_bump_decay_matches: int = Field(
        6, description="partidos en los que el bonus de entrenador decae a 0"
    )
    n_sims: int = Field(100_000, description="número de simulaciones Monte Carlo por defecto")
    n_relegation: int = Field(3, description="plazas de descenso")
    model_type: str = Field(
        "adjusted", description="'pure' (solo Elo) o 'adjusted' (Elo + forma + ...)"
    )

    @field_validator("alpha", "xg_blend_beta", "draw_base")
    @classmethod
    def _unit_interval(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"debe estar en [0, 1], es {v}")
        return v

    @field_validator("form_half_life_days")
    @classmethod
    def _positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"debe ser > 0, es {v}")
        return v

    @field_validator("model_type")
    @classmethod
    def _known_model(cls, v: str) -> str:
        if v not in {"pure", "adjusted"}:
            raise ValueError(f"model_type desconocido: {v!r}")
        return v


class Paths(BaseModel):
    cache_dir: Path = Path("data/cache")
    coach_changes_file: Path = Path("data/coach_changes.yaml")
    team_aliases_file: Path = Path("data/team_aliases.yaml")


class AppConfig(BaseModel):
    season: int = Field(2025, description="año de inicio de la temporada en curso")
    model: ModelConfig = ModelConfig()
    paths: Paths = Paths()


DEFAULT_CONFIG_FILE = Path("config.yaml")


def load_config(path: Path | None = None) -> AppConfig:
    """Carga la configuración desde YAML; si no existe el fichero, usa los valores por defecto."""
    path = path or DEFAULT_CONFIG_FILE
    if not path.exists():
        return AppConfig()
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return AppConfig.model_validate(raw)
