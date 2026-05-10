"""Caso de uso: construir las fuerzas efectivas de los equipos a una fecha dada."""

from __future__ import annotations

import datetime as dt

from descenso.config import AppConfig
from descenso.domain.strength_model import StrengthSnapshot


def build_strengths(config: AppConfig, as_of: dt.date | None = None) -> dict[str, StrengthSnapshot]:
    """Carga datos (Elo, partidos, cambios de entrenador, bajas) y devuelve las fuerzas.

    Si `config.model.model_type == 'pure'`, el resultado es equivalente a usar solo
    el Elo base de clubelo (línea base del modelo de @LaLigaenDirecto).
    """
    raise NotImplementedError  # Fase 8
