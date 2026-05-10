"""Tests del cache Parquet local (escritura atómica, creación de directorio)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from descenso.adapters.data.cache import ParquetCache

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _df_elo() -> pd.DataFrame:
    return pd.DataFrame({"Club": ["Barcelona", "Real Madrid"], "Elo": [1900.0, 1880.0]})


# --------------------------------------------------------------------------- #
# path / has
# --------------------------------------------------------------------------- #


def test_path_construye_nombre_correcto(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    assert cache.path("clubelo_elo") == tmp_path / "clubelo_elo.parquet"


def test_has_devuelve_false_si_no_existe(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    assert not cache.has("clubelo_elo")


def test_has_devuelve_true_despues_de_save(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    cache.save("clubelo_elo", _df_elo())
    assert cache.has("clubelo_elo")


# --------------------------------------------------------------------------- #
# save / load
# --------------------------------------------------------------------------- #


def test_save_y_load_roundtrip(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    df_orig = _df_elo()
    cache.save("clubelo_elo", df_orig)
    df_leido = cache.load("clubelo_elo")
    pd.testing.assert_frame_equal(df_leido.reset_index(drop=True), df_orig.reset_index(drop=True))


def test_save_crea_el_directorio_si_no_existe(tmp_path: Path) -> None:
    cache_dir = tmp_path / "subcarpeta" / "cache"
    assert not cache_dir.exists()
    cache = ParquetCache(cache_dir)
    cache.save("test", _df_elo())
    assert cache_dir.exists()
    assert cache.has("test")


def test_save_es_atomico_tmp_luego_replace(tmp_path: Path) -> None:
    """El fichero .parquet.tmp no debe existir tras un save exitoso."""
    cache = ParquetCache(tmp_path)
    cache.save("clubelo_elo", _df_elo())
    assert not (tmp_path / "clubelo_elo.parquet.tmp").exists()
    assert (tmp_path / "clubelo_elo.parquet").exists()


def test_save_sobreescribe_el_anterior(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    df1 = pd.DataFrame({"Club": ["Barcelona"], "Elo": [1900.0]})
    df2 = pd.DataFrame({"Club": ["Real Madrid"], "Elo": [1880.0]})
    cache.save("clubelo_elo", df1)
    cache.save("clubelo_elo", df2)
    df_leido = cache.load("clubelo_elo")
    assert list(df_leido["Club"]) == ["Real Madrid"]


def test_load_lanza_error_si_no_existe(tmp_path: Path) -> None:
    cache = ParquetCache(tmp_path)
    with pytest.raises(FileNotFoundError):
        cache.load("inexistente")
