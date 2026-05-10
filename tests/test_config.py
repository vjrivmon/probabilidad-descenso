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


# --- parámetros del modelo Dixon-Coles (CP3) ---


def test_match_model_desconocido_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match="match_model desconocido"):
        ModelConfig(match_model="bayesian")


def test_match_model_valores_validos() -> None:
    assert ModelConfig(match_model="elo_logistic").match_model == "elo_logistic"
    assert ModelConfig(match_model="dixon_coles").match_model == "dixon_coles"


def test_dixon_coles_rho_fuera_de_rango_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match=r"\[-0.2, 0.2\]"):
        ModelConfig(dixon_coles_rho=0.5)
    with pytest.raises(ValidationError, match=r"\[-0.2, 0.2\]"):
        ModelConfig(dixon_coles_rho=-0.3)


def test_dixon_coles_rho_en_rango_valido() -> None:
    assert ModelConfig(dixon_coles_rho=0.0).dixon_coles_rho == 0.0
    assert ModelConfig(dixon_coles_rho=-0.15).dixon_coles_rho == -0.15


def test_goals_avg_no_positivo_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match="> 0"):
        ModelConfig(goals_avg=0.0)


def test_elo_to_goals_scale_no_positivo_levanta_validation_error() -> None:
    with pytest.raises(ValidationError, match="> 0"):
        ModelConfig(elo_to_goals_scale=-1.0)


def test_defaults_del_modelo_dixon_coles() -> None:
    cfg = ModelConfig()
    assert cfg.match_model == "elo_logistic"
    assert cfg.goals_avg == 1.35
    assert cfg.elo_to_goals_scale == 400.0
    assert cfg.dixon_coles_rho == -0.1


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
