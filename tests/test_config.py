"""Tests adicionales del módulo config (cubre líneas aún no alcanzadas)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from descenso.config import AppConfig, ModelConfig, load_config

# --------------------------------------------------------------------------- #
# Validadores de ModelConfig
# --------------------------------------------------------------------------- #


def test_alpha_fuera_de_rango_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match=r"\[0, 1\]"):
        ModelConfig(alpha=1.5)


def test_draw_base_fuera_de_rango_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match=r"\[0, 1\]"):
        ModelConfig(draw_base=-0.1)


def test_xg_blend_beta_fuera_de_rango_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match=r"\[0, 1\]"):
        ModelConfig(xg_blend_beta=1.1)


def test_form_half_life_days_cero_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match="> 0"):
        ModelConfig(form_half_life_days=0.0)


def test_form_half_life_days_negativo_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match="> 0"):
        ModelConfig(form_half_life_days=-10.0)


def test_model_type_desconocido_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match="desconocido"):
        ModelConfig(model_type="neural_network")


def test_model_type_pure_valido() -> None:
    cfg = ModelConfig(model_type="pure")
    assert cfg.model_type == "pure"


def test_model_type_adjusted_valido() -> None:
    cfg = ModelConfig(model_type="adjusted")
    assert cfg.model_type == "adjusted"


# --------------------------------------------------------------------------- #
# load_config
# --------------------------------------------------------------------------- #


def test_load_config_sin_fichero_devuelve_defaults(tmp_path: Path) -> None:
    """Si no existe el fichero de config, se usan los valores por defecto."""
    cfg = load_config(tmp_path / "no_existe.yaml")
    assert isinstance(cfg, AppConfig)
    assert cfg.season == 2025


def test_load_config_desde_yaml_custom(tmp_path: Path) -> None:
    f = tmp_path / "config.yaml"
    f.write_text("season: 2024\nmodel:\n  n_sims: 50000\n  model_type: pure\n", encoding="utf-8")
    cfg = load_config(f)
    assert cfg.season == 2024
    assert cfg.model.n_sims == 50000
    assert cfg.model.model_type == "pure"


def test_load_config_yaml_vacio_devuelve_defaults(tmp_path: Path) -> None:
    f = tmp_path / "config.yaml"
    f.write_text("", encoding="utf-8")
    cfg = load_config(f)
    assert cfg.season == 2025
