"""Tests del resumen de factores del CP0 (`summarize_factors`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from descenso.application.scrape_replies import KEYWORDS, _replies_text, summarize_factors

_SAMPLE = """# Recopilado de x.com el 2026-05-10 (uso único, CP0)
# Cuenta: @LaLigaenDirecto

======================================================================
## TWEETS DE @LaLigaenDirecto (timeline del perfil)  (2 entradas)
======================================================================

[@LaLigaenDirecto] Probabilidad de descenso: [99,91%] Oviedo. El calendario no se inventa.

[@LaLigaenDirecto] #DATO el Athletic iguala su récord de derrotas.

======================================================================
## REPLIES / MENCIONES dirigidas a @LaLigaenDirecto (búsqueda to:)  (3 entradas)
======================================================================

[@uno] No me creo el 5% del Valencia con el calendario que tiene; le queda un calendario fácil.

[@dos] Fran, explica cómo funciona el modelo, no entiendo nada, me explota el cerebro.

[@tres] Actualiza ya los porcentajes tras el partido.

======================================================================
## TWEETS que mencionan a @LaLigaenDirecto con 'descenso/modelo/probabilidad'  (1 entradas)
======================================================================

[@cuatro] Ese gol fue de churro, no merecía ganar; @LaLigaenDirecto el modelo no lo refleja.
"""


def test_replies_text_descarta_los_tweets_propios() -> None:
    section = _replies_text(_SAMPLE)
    # los tweets de Fran (timeline) no entran...
    assert "iguala su récord de derrotas" not in section
    # ...pero los replies y el bloque de menciones sí
    assert "le queda un calendario fácil" in section
    assert "de churro" in section


def test_replies_text_sin_cabeceras_devuelve_todo() -> None:
    raw = "uno dos tres\ncuatro cinco"
    assert _replies_text(raw) == raw


def test_summarize_factors_cuenta_categorias(tmp_path: Path) -> None:
    f = tmp_path / "replies.txt"
    f.write_text(_SAMPLE, encoding="utf-8")
    counts = summarize_factors(f)
    assert set(counts) == set(KEYWORDS)
    # "calendario" aparece 2 veces en los replies (no cuenta el del tweet de Fran)
    assert counts["calendario / dificultad del run-in"] >= 2
    assert counts["explicabilidad (cómo funciona / qué tiene en cuenta)"] >= 2
    assert counts["frecuencia de actualización"] >= 1
    assert counts["xg / merecimiento / suerte"] >= 1
    # categoría sin coincidencias
    assert counts["mercado / fichajes / refuerzos"] == 0


def test_summarize_factors_no_cuenta_los_tweets_de_fran(tmp_path: Path) -> None:
    """'el calendario no se inventa' está en un tweet de Fran -> no debe contar."""
    f = tmp_path / "replies.txt"
    f.write_text(_SAMPLE, encoding="utf-8")
    counts = summarize_factors(f)
    # en los replies: 'calendario' x2 + 'le queda' x1 = 3 (el 'calendario' del tweet
    # de Fran NO se cuenta; si se contara serían 4)
    assert counts["calendario / dificultad del run-in"] == 3


def test_summarize_factors_fichero_inexistente_levanta_filenotfound(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        summarize_factors(tmp_path / "no_existe.txt")
