"""Tests del informe HTML estático (CP3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from descenso.application.export_html import (
    _bar_svg,
    _fmt_pct,
    export_html_report,
    render_html_from_last_run,
)


def _last_run() -> dict[str, Any]:
    return {
        "created_at": "2026-05-10T19:30:00",
        "season": 2025,
        "n_played": 340,
        "n_pending": 40,
        "model_type": "adjusted",
        "n_sims": 100000,
        "seed": 1,
        "team_names": {
            "oviedo": "Real Oviedo",
            "levante": "Levante UD",
            "alaves": "Deportivo Alavés <test>",
            "osasuna": "CA Osasuna",
        },
        "applied_fixed": [["levante", 3, "osasuna", 2]],
        "teams": [
            {
                "team": "osasuna",
                "p_relegation": 0.00002,
                "expected_points": 48.2,
                "expected_position": 12.1,
            },
            {
                "team": "oviedo",
                "p_relegation": 0.998,
                "expected_points": 21.0,
                "expected_position": 19.8,
            },
            {
                "team": "levante",
                "p_relegation": 0.812,
                "expected_points": 30.4,
                "expected_position": 18.1,
            },
            {
                "team": "alaves",
                "p_relegation": 0.39,
                "expected_points": 36.0,
                "expected_position": 16.0,
            },
        ],
    }


def test_fmt_pct_usa_coma_decimal() -> None:
    assert _fmt_pct(0.8123) == "81,23"
    assert _fmt_pct(0.0) == "0,00"


def test_bar_svg_ancho_proporcional_y_minimo() -> None:
    big = _bar_svg(1.0)
    small = _bar_svg(0.0)
    assert "<svg" in big and "</svg>" in big
    assert 'class="bar-fg"' in big
    # ancho >= 1 incluso con p=0 (barra visible)
    assert 'width="1.0"' in small


def test_render_html_es_un_documento_completo() -> None:
    html = render_html_from_last_run(_last_run())
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html
    assert "<style>" in html and "</style>" in html
    # sin JavaScript ni recursos http externos
    assert "<script" not in html
    assert "http://" not in html
    # ningún emoji típico
    for ch in ("🎯", "⚽", "📊", "✅"):
        assert ch not in html


def test_render_html_ordena_por_probabilidad_descendente() -> None:
    html = render_html_from_last_run(_last_run())
    tbody = html.split("<tbody>", 1)[1]
    # Oviedo (99.8%) antes que Levante (81.2%) antes que Alavés (39%) en la tabla
    assert tbody.index("Real Oviedo") < tbody.index("Levante UD") < tbody.index("Deportivo")


def test_render_html_escapa_nombres_de_equipo() -> None:
    html = render_html_from_last_run(_last_run())
    assert "Deportivo Alavés &lt;test&gt;" in html
    assert "<test>" not in html


def test_render_html_incluye_una_fila_por_equipo_y_barras() -> None:
    html = render_html_from_last_run(_last_run())
    assert html.count('class="rank"') == 4
    assert html.count('<svg class="bar"') == 4


def test_render_html_marca_los_candidatos() -> None:
    html = render_html_from_last_run(_last_run())
    # Osasuna redondea a 0,00 % -> NO es candidato; los otros tres sí
    assert html.count('class="candidate"') == 3


def test_render_html_nota_de_resultados_fijados() -> None:
    html = render_html_from_last_run(_last_run())
    assert "Resultados fijados" in html
    assert "Levante UD vs CA Osasuna fijado" in html


def test_render_html_sin_fijados_no_pone_la_nota() -> None:
    data = _last_run()
    data["applied_fixed"] = []
    html = render_html_from_last_run(data)
    assert "Resultados fijados" not in html


def test_render_html_tolera_dict_minimo() -> None:
    """Un dict vacío no debe reventar (se usan defaults)."""
    html = render_html_from_last_run({})
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html


def test_render_html_temporada_terminada() -> None:
    data = _last_run()
    data["n_pending"] = 0
    html = render_html_from_last_run(data)
    assert "temporada terminada" in html


def test_render_html_incluye_la_nota_del_calendario() -> None:
    """La aclaración nº1 de la afición (el modelo sí simula el calendario restante)."""
    html = render_html_from_last_run(_last_run())
    assert "simula el calendario restante" in html
    assert 'class="note"' in html


def test_export_html_report_escribe_el_fichero(tmp_path: Path) -> None:
    out = tmp_path / "sub" / "informe.html"
    returned = export_html_report(_last_run(), out)
    assert returned == out
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert content.startswith("<!DOCTYPE html>")
    assert "Real Oviedo" in content


def test_export_html_report_acepta_string_path(tmp_path: Path) -> None:
    out = str(tmp_path / "informe.html")
    returned = export_html_report(_last_run(), Path(out))
    assert returned.exists()


@pytest.mark.parametrize("p", [0.0, 0.1, 0.5, 0.999, 1.0, 1.5, -0.2])
def test_bar_svg_no_revienta_con_valores_limite(p: float) -> None:
    svg = _bar_svg(p)
    assert svg.startswith("<svg")
