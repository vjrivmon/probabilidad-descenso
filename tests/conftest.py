"""Fixtures compartidas para los tests."""

from __future__ import annotations

import pytest

from descenso.config import AppConfig, ModelConfig


@pytest.fixture
def pure_config() -> AppConfig:
    """Configuración del modelo 'puro' (solo Elo) — la línea base de comparación."""
    return AppConfig(model=ModelConfig(alpha=1.0, model_type="pure", n_sims=2000))


@pytest.fixture
def adjusted_config() -> AppConfig:
    """Configuración del modelo ajustado (Elo + forma + xG + entrenadores)."""
    return AppConfig(model=ModelConfig(alpha=0.5, model_type="adjusted", n_sims=2000))
