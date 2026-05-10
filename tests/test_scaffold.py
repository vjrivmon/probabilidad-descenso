"""Smoke tests del scaffold: el paquete importa y la CLI arranca."""

from __future__ import annotations

from typer.testing import CliRunner

import descenso
from descenso.cli.app import app
from descenso.config import AppConfig, load_config


def test_package_version() -> None:
    assert descenso.__version__ == "0.1.0"


def test_default_config_is_valid() -> None:
    cfg = AppConfig()
    assert 0.0 <= cfg.model.alpha <= 1.0
    assert cfg.model.form_half_life_days > 0


def test_load_config_from_repo_file() -> None:
    cfg = load_config()  # carga el config.yaml del repo
    assert cfg.season == 2025
    assert cfg.model.model_type in {"pure", "adjusted"}


def test_cli_help_runs() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "descenso" in result.output.lower()


def test_cli_subcommands_exist() -> None:
    runner = CliRunner()
    subcommands = ["simulate", "report", "compare", "backtest", "data"]
    for sub in subcommands:
        assert runner.invoke(app, [sub, "--help"]).exit_code == 0
