"""Caso de uso: exportar el ranking de descenso a un informe HTML estático.

Genera un único fichero HTML autocontenido (CSS en línea, gráfico de barras en SVG
en línea, sin JavaScript ni dependencias externas ni emojis) a partir del
diccionario que `run_simulation.save_last_run` deja en `data/cache/last_run.json`.
"""

from __future__ import annotations

import datetime as dt
import html
from pathlib import Path
from typing import Any

from descenso.adapters.data.schedule import season_slug

_REPO_URL = "https://github.com/vjrivmon/probabilidad-descenso"

# Ancho (px) reservado para la barra de probabilidad dentro de su celda.
_BAR_WIDTH = 220


def _esc(value: object) -> str:
    return html.escape(str(value))


def _fmt_pct(p: float) -> str:
    return f"{p * 100:.2f}".replace(".", ",")


def _bar_svg(p: float) -> str:
    """Una barra horizontal proporcional a `p` ∈ [0, 1] como SVG en línea."""
    p = max(0.0, min(1.0, p))
    fill = max(1.0, p * _BAR_WIDTH)
    height = 14
    return (
        f'<svg class="bar" width="{_BAR_WIDTH}" height="{height}" '
        f'role="img" aria-label="{_fmt_pct(p)} por ciento">'
        f'<rect width="{_BAR_WIDTH}" height="{height}" rx="3" class="bar-bg"/>'
        f'<rect width="{fill:.1f}" height="{height}" rx="3" class="bar-fg"/>'
        f"</svg>"
    )


def render_html_from_last_run(data: dict[str, Any]) -> str:
    """Construye el HTML del informe a partir del dict de `last_run.json`."""
    season = int(data.get("season", 0))
    n_played = int(data.get("n_played", 0))
    n_pending = int(data.get("n_pending", 0))
    model_type = str(data.get("model_type", "?"))
    n_sims = data.get("n_sims", "?")
    seed = data.get("seed")
    created_at = str(data.get("created_at", ""))
    names_raw = data.get("team_names", {})
    names: dict[str, str] = {}
    if isinstance(names_raw, dict):
        names = {str(k): str(v) for k, v in names_raw.items()}

    teams_raw = data.get("teams", [])
    rows: list[tuple[str, float, float, float]] = []
    if isinstance(teams_raw, list):
        for t in teams_raw:
            if not isinstance(t, dict):
                continue
            tid = str(t.get("team", ""))
            rows.append(
                (
                    tid,
                    float(t.get("p_relegation", 0.0)),
                    float(t.get("expected_points", 0.0)),
                    float(t.get("expected_position", 0.0)),
                )
            )
    rows.sort(key=lambda r: r[1], reverse=True)

    applied_raw = data.get("applied_fixed", [])
    applied: list[tuple[str, str]] = []
    if isinstance(applied_raw, list):
        for fx in applied_raw:
            if isinstance(fx, (list, tuple)) and len(fx) == 4:
                applied.append((str(fx[0]), str(fx[2])))

    slug = season_slug(season) if season else "?"
    suffix = "temporada terminada" if n_pending == 0 else f"{n_pending} partidos restantes"
    subtitle_bits = [
        f"modelo {model_type}",
        f"{n_sims} simulaciones",
    ]
    if seed is not None:
        subtitle_bits.append(f"seed {seed}")
    if created_at:
        subtitle_bits.append(f"generado {created_at}")
    subtitle = " · ".join(subtitle_bits)

    table_rows: list[str] = []
    for i, (tid, p, exp_pts, exp_pos) in enumerate(rows, start=1):
        candidate = round(p * 100, 2) > 0.0
        cls = ' class="candidate"' if candidate else ""
        name = names.get(tid, tid)
        table_rows.append(
            "<tr{cls}>"
            '<td class="rank">{rank}</td>'
            '<td class="team">{name}</td>'
            '<td class="pct">{pct}%</td>'
            '<td class="bar-cell">{bar}</td>'
            '<td class="num">{pts}</td>'
            '<td class="num">{pos}</td>'
            "</tr>".format(
                cls=cls,
                rank=i,
                name=_esc(name),
                pct=_fmt_pct(p),
                bar=_bar_svg(p),
                pts=f"{exp_pts:.1f}",
                pos=f"{exp_pos:.1f}",
            )
        )

    applied_html = ""
    if applied:
        items = "; ".join(
            f"{_esc(names.get(h, h))} vs {_esc(names.get(a, a))} fijado" for h, a in applied
        )
        applied_html = f'<p class="note">Resultados fijados: {items}; resto simulado.</p>'

    generated_now = dt.datetime.now().isoformat(timespec="seconds")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Probabilidad de descenso · LaLiga {_esc(slug)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica,
                 Arial, sans-serif;
    margin: 0; padding: 2rem 1rem; background: #f6f7f8; color: #1a1d21; line-height: 1.45;
  }}
  main {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 .25rem; }}
  .subtitle {{ color: #5b6470; font-size: .9rem; margin: 0 0 .25rem; }}
  .meta {{ color: #5b6470; font-size: .9rem; margin: 0 0 1.25rem; }}
  .note {{ color: #5b6470; font-size: .85rem; font-style: italic; margin: .25rem 0 1rem; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
           overflow: hidden; box-shadow: 0 1px 2px rgba(0,0,0,.06), 0 1px 8px rgba(0,0,0,.04); }}
  thead th {{ text-align: left; font-size: .75rem; text-transform: uppercase; letter-spacing: .04em;
              color: #5b6470; padding: .6rem .75rem; border-bottom: 1px solid #e6e8eb; }}
  tbody td {{ padding: .5rem .75rem; border-bottom: 1px solid #f0f1f3; font-size: .95rem; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  tr.candidate td.team {{ font-weight: 600; }}
  td.rank {{ color: #9aa1aa; width: 2rem; text-align: right; font-variant-numeric: tabular-nums; }}
  td.pct, td.num {{ font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }}
  td.pct {{ font-weight: 600; }}
  td.num {{ color: #5b6470; }}
  td.bar-cell {{ width: {_BAR_WIDTH + 8}px; }}
  svg.bar {{ display: block; }}
  svg.bar .bar-bg {{ fill: #eceef0; }}
  svg.bar .bar-fg {{ fill: #d6453d; }}
  footer {{ margin-top: 1.5rem; color: #9aa1aa; font-size: .8rem; }}
  footer a {{ color: inherit; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #16181b; color: #e6e8eb; }}
    table {{ background: #1f2226; box-shadow: none; }}
    thead th, .subtitle, .meta, .note, td.num {{ color: #9aa1aa; }}
    thead th {{ border-bottom-color: #2a2e33; }}
    tbody td {{ border-bottom-color: #25282c; }}
    svg.bar .bar-bg {{ fill: #2a2e33; }}
  }}
</style>
</head>
<body>
<main>
  <h1>Probabilidad de descenso a Segunda</h1>
  <p class="subtitle">LaLiga {_esc(slug)} · {n_played} partidos jugados · {_esc(suffix)}</p>
  <p class="meta">{_esc(subtitle)}</p>
  {applied_html}
  <table>
    <thead>
      <tr>
        <th></th><th>Equipo</th><th>P(descenso)</th><th></th>
        <th>Pts. esp.</th><th>Pos. esp.</th>
      </tr>
    </thead>
    <tbody>
      {"".join(table_rows)}
    </tbody>
  </table>
  <footer>
    Generado por <a href="{_REPO_URL}">descenso</a> el {_esc(generated_now)}.
    Modelo de fuerza con memoria de forma + Monte Carlo sobre el calendario restante.
  </footer>
</main>
</body>
</html>
"""


def export_html_report(data: dict[str, Any], path: Path) -> Path:
    """Escribe el informe HTML en `path` (creando los directorios necesarios). Devuelve `path`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html_from_last_run(data), encoding="utf-8")
    return path
