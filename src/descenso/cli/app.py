"""CLI `descenso` — punto de entrada.

Subcomandos:
    descenso data refresh   Descarga/actualiza Elo (clubelo) y calendario (openfootball) al cache.
    descenso data show      Muestra qué hay en el cache y de qué fecha.
    descenso simulate       Interactivo: pide goles de cada partido pendiente (Enter = simular).
    descenso report         Imprime el ranking de la última simulación en formato tweet.
    descenso compare        Tabla modelo puro vs ajustado + Δ + nota.   (CP2)
    descenso backtest       Brier / log-loss puro vs ajustado sobre temporadas pasadas.  (CP2)
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import shutil
import subprocess
import sys
import unicodedata
from typing import NoReturn

import typer
from rich.console import Console

from descenso.adapters.data.cache import ParquetCache
from descenso.adapters.data.clubelo_elo import CACHE_NAME as ELO_CACHE_NAME
from descenso.adapters.data.clubelo_elo import ClubeloEloSource, ClubeloError
from descenso.adapters.data.schedule import OpenFootballScheduleSource, ScheduleError, season_slug
from descenso.adapters.data.team_aliases import TeamAliasError, load_teams
from descenso.adapters.data.understat_xg import UnderstatError, UnderstatXgSource
from descenso.application.backtest import run_backtest
from descenso.application.compare_models import compare_models
from descenso.application.run_simulation import (
    FixedResult,
    SimulationOutcome,
    load_inputs,
    load_last_run,
    run_simulation,
    save_last_run,
)
from descenso.config import AppConfig, load_config
from descenso.domain.match import Match, MatchStatus
from descenso.domain.team import Team

app = typer.Typer(
    help="Probabilidad de descenso en LaLiga con memoria de forma.", no_args_is_help=True
)
data_app = typer.Typer(help="Gestión de los datos (Elo, calendario).", no_args_is_help=True)
app.add_typer(data_app, name="data")

console = Console()
err_console = Console(stderr=True)

_FIX_RE = re.compile(r"^\s*(.+?)\s+(\d{1,2})\s*-\s*(\d{1,2})\s+(.+?)\s*$")
_SCORE_RE = re.compile(r"^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$")


# --------------------------------------------------------------------------- #
# infraestructura común
# --------------------------------------------------------------------------- #
def _setup_logging() -> None:
    # WARNING+ a stderr; silencia el INFO de httpx pero deja pasar los avisos de
    # los adaptadores ("uso el cache previo del ...").
    logging.basicConfig(level=logging.WARNING, format="[descenso] %(message)s", stream=sys.stderr)


def _die(message: str) -> NoReturn:
    err_console.print(f"[bold red]error:[/] {message}")
    raise typer.Exit(1)


def _config() -> AppConfig:
    try:
        return load_config()
    except Exception as exc:  # error de config: mostrarlo claro y salir
        _die(f"no pude leer config.yaml: {exc}")


# --------------------------------------------------------------------------- #
# data refresh / show
# --------------------------------------------------------------------------- #
@data_app.command("refresh")
def data_refresh() -> None:
    """Descarga/actualiza Elo (clubelo) y calendario (openfootball) al cache local."""
    _setup_logging()
    config = _config()
    cache = ParquetCache(config.paths.cache_dir)
    try:
        teams = load_teams(config.paths.team_aliases_file)
    except (TeamAliasError, FileNotFoundError) as exc:
        _die(str(exc))

    with console.status("descargando Elo de clubelo.com…"):
        try:
            elo = ClubeloEloSource(cache).fetch_current_elo(teams, prefer_cache=False)
        except ClubeloError as exc:
            _die(str(exc))
    console.print(f"Elo (clubelo.com): {len(elo)} equipos.")

    slug = season_slug(config.season)
    with console.status(f"descargando el calendario {slug} de openfootball…"):
        try:
            matches = OpenFootballScheduleSource(cache).fetch_schedule(
                config.season, teams, prefer_cache=False
            )
        except (ScheduleError, TeamAliasError) as exc:
            _die(str(exc))
    played = sum(1 for m in matches if m.status is MatchStatus.PLAYED)
    pending = len(matches) - played
    console.print(
        f"Calendario {slug}: {len(matches)} partidos ({played} jugados, {pending} pendientes)."
    )

    with console.status("intentando descargar xG de understat.com…"):
        try:
            xg_matches = UnderstatXgSource(cache).fetch_match_xg(
                config.season, teams, prefer_cache=False
            )
            console.print(f"xG (understat.com): {len(xg_matches)} partidos con xG.")
        except UnderstatError as exc:
            err_console.print(
                f"[yellow]aviso:[/] no se pudo descargar xG de Understat: {exc}\n"
                f"  (el modelo funciona sin xG; se usaran solo goles reales)"
            )

    console.print(f"Cache: {config.paths.cache_dir.resolve()}")


@data_app.command("show")
def data_show() -> None:
    """Muestra el contenido y la antigüedad del cache."""
    _setup_logging()
    config = _config()
    cache = ParquetCache(config.paths.cache_dir)
    xg_cache_name = f"understat_xg_{config.season}"
    entries = [
        (ELO_CACHE_NAME, "Elo (clubelo.com)"),
        (f"schedule_{config.season}", f"Calendario {season_slug(config.season)}"),
        (xg_cache_name, f"xG Understat {season_slug(config.season)}"),
    ]
    any_found = False
    for name, label in entries:
        path = cache.path(name)
        if path.exists():
            any_found = True
            mtime = dt.datetime.fromtimestamp(path.stat().st_mtime)
            try:
                rows = len(cache.load(name))
            except Exception as exc:  # cache corrupto: avisar, no reventar
                console.print(f"{label}: [yellow]cache ilegible[/] ({exc}) — corre `data refresh`.")
                continue
            console.print(f"{label}: {rows} filas · actualizado {mtime:%Y-%m-%d %H:%M}.")
        else:
            console.print(f"{label}: [dim]sin cache[/] — corre `descenso data refresh`.")
    last = load_last_run(config.paths.cache_dir)
    if last:
        console.print(
            f"Última simulación: {last.get('created_at', '?')} · "
            f"{last.get('n_sims', '?')} sims · seed {last.get('seed')}."
        )
    if not any_found:
        console.print("[dim](el cache está vacío; empieza por `descenso data refresh`)[/]")


# --------------------------------------------------------------------------- #
# simulate
# --------------------------------------------------------------------------- #
@app.command()
def simulate(
    sims: int = typer.Option(100_000, help="número de simulaciones Monte Carlo"),
    fix: list[str] = typer.Option(
        None, "--fix", help='fijar un resultado, p.ej. --fix "Levante 3-2 Osasuna" (repetible)'
    ),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="no preguntar resultados; simular todo lo no fijado"
    ),
    seed: int = typer.Option(None, help="semilla para reproducibilidad"),
) -> None:
    """Simula el calendario restante y muestra la probabilidad de descenso por equipo."""
    _setup_logging()
    config = _config()
    if sims < 1:
        _die(f"--sims debe ser ≥ 1 (es {sims}).")
    if sims < 1000:
        err_console.print(f"[yellow]aviso:[/] {sims} simulaciones es poco; recomiendo ≥ 1000.")

    try:
        inputs = load_inputs(config, prefer_cache=True)
    except (ClubeloError, ScheduleError, TeamAliasError, FileNotFoundError) as exc:
        _die(f"{exc}\n(¿has corrido `descenso data refresh` con conexión?)")

    fixed: list[FixedResult] = []
    for spec in fix or []:
        try:
            fixed.append(_parse_fix(spec, inputs.teams))
        except ValueError as exc:
            _die(str(exc))

    interactive = not no_interactive and sys.stdin.isatty() and sys.stdout.isatty()
    if interactive:
        fixed_pairs = {(f.home_team, f.away_team) for f in fixed}
        pending = [
            m
            for m in inputs.matches
            if m.status is MatchStatus.PENDING and (m.home_team, m.away_team) not in fixed_pairs
        ]
        fixed.extend(_prompt_pending(pending, {t.id: t.name for t in inputs.teams}))

    with console.status(f"simulando {sims} iteraciones…"):
        outcome = run_simulation(config, fixed_results=fixed, n_sims=sims, seed=seed, inputs=inputs)

    _render_outcome(outcome)
    path = save_last_run(outcome, config.paths.cache_dir)
    console.print(f"[dim]guardado: {path}  ·  usa `descenso report` para reimprimirlo[/]")


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
@app.command()
def report(
    copy: bool = typer.Option(False, "--copy", help="copiar el ranking al portapapeles"),
    top: int = typer.Option(
        0, help="mostrar solo los N equipos con más probabilidad (0 = todos los candidatos)"
    ),
) -> None:
    """Imprime el ranking de la última simulación en formato tweet."""
    _setup_logging()
    config = _config()
    last = load_last_run(config.paths.cache_dir)
    if last is None:
        err_console.print(
            "[yellow]no hay ninguna simulación previa; corro una con los defaults…[/]"
        )
        try:
            inputs = load_inputs(config, prefer_cache=True)
            outcome = run_simulation(config, inputs=inputs)
        except (ClubeloError, ScheduleError, TeamAliasError, FileNotFoundError) as exc:
            _die(f"{exc}\n(corre `descenso data refresh` con conexión primero)")
        save_last_run(outcome, config.paths.cache_dir)
        ranked = [(tp.team, tp.p_relegation) for tp in outcome.probabilities.ranked()]
        names = outcome.team_names
        header = _header_line(outcome.season, outcome.n_played, outcome.n_pending)
        applied = [(f.home_team, f.away_team) for f in outcome.applied_fixed]
    else:
        names = {str(k): str(v) for k, v in last.get("team_names", {}).items()}
        ranked = [(t["team"], float(t["p_relegation"])) for t in last.get("teams", [])]
        ranked.sort(key=lambda x: x[1], reverse=True)
        header = _header_line(
            int(last.get("season", config.season)),
            int(last.get("n_played", 0)),
            int(last.get("n_pending", 0)),
        )
        applied = [(fx[0], fx[2]) for fx in last.get("applied_fixed", [])]

    block = _ranking_block(ranked, names, applied, top=top, header=header)
    typer.echo(block)
    if copy:
        if _copy_to_clipboard(block):
            console.print("[dim](copiado al portapapeles)[/]")
        else:
            err_console.print(
                "[yellow]no pude copiar al portapapeles (¿sin xclip/wl-copy?); cópialo a mano.[/]"
            )


# --------------------------------------------------------------------------- #
# compare / backtest (CP2)
# --------------------------------------------------------------------------- #
@app.command()
def compare(
    sims: int = typer.Option(50_000, help="número de simulaciones por modelo"),
    seed: int = typer.Option(None, help="semilla para reproducibilidad"),
) -> None:
    """Compara el modelo puro (solo Elo) con el ajustado (Elo + forma + xG + entrenadores)."""
    _setup_logging()
    config = _config()
    if sims < 1:
        _die(f"--sims debe ser >= 1 (es {sims}).")

    with console.status("cargando datos y calculando fuerzas…"):
        try:
            rows = compare_models(config, n_sims=sims, seed=seed)
        except Exception as exc:
            _die(str(exc))

    if not rows:
        _die("no se obtuvieron filas de comparación.")

    # `compare_models` ya cargó los equipos (vía `load_inputs`) sin error, así que
    # `load_teams` aquí no debería fallar; si falla, que propague a `_die` arriba.
    names = {t.id: t.name for t in load_teams(config.paths.team_aliases_file)}

    # Cabecera
    slug = season_slug(config.season)
    console.print(f"\n[bold]Comparacion de modelos — LaLiga {slug}[/]")
    console.print(
        f"[dim]{sims} simulaciones · seed {seed} · "
        f"modelo puro (alpha=1.0) vs ajustado (alpha={config.model.alpha})[/]"
    )

    # Tabla Rich
    from rich.table import Table

    tabla = Table(show_header=True, header_style="bold")
    tabla.add_column("Equipo", style="", min_width=20)
    tabla.add_column("Puro (%)", justify="right")
    tabla.add_column("Ajustado (%)", justify="right")
    tabla.add_column("Δ (pp)", justify="right")
    tabla.add_column("Nota", style="dim")

    for row in rows:
        delta_str = f"{row.delta:+.2f}"
        delta_style = "green" if row.delta < 0 else ("red" if row.delta > 0 else "")
        tabla.add_row(
            names.get(row.team, row.team),
            f"{row.p_pure * 100:.2f}",
            f"{row.p_adjusted * 100:.2f}",
            f"[{delta_style}]{delta_str}[/{delta_style}]" if delta_style else delta_str,
            row.note,
        )

    console.print(tabla)

    # Ranking del modelo ajustado en texto plano (copiable)
    console.print("\n[dim]-- Ranking ajustado (copiable) --[/]")
    ranked = [(r.team, r.p_adjusted) for r in rows]
    header = _header_line(config.season, 0, 0)
    typer.echo(_ranking_block(ranked, names, [], top=0, header=header))


@app.command()
def backtest(
    seasons: str = typer.Option(
        "2022,2023,2024", help="temporadas (año de inicio) separadas por comas"
    ),
    horizon: int = typer.Option(5, help="jornadas antes del final desde las que predecir"),
    sims: int = typer.Option(20_000, help="simulaciones por predicción"),
    seed: int = typer.Option(None, help="semilla para reproducibilidad (default: 42)"),
) -> None:
    """Backtest histórico: Brier / log-loss del modelo puro vs el ajustado."""
    _setup_logging()
    config = _config()

    # Parsear la lista de temporadas
    try:
        season_list = [int(s.strip()) for s in seasons.split(",") if s.strip()]
    except ValueError as exc:
        _die(f"--seasons debe ser una lista de años separados por comas: {exc}")
    if not season_list:
        _die("--seasons está vacío.")

    console.print(
        f"\n[bold]Backtest historico[/] — temporadas: {season_list} · "
        f"horizonte: {horizon} jornadas · {sims} simulaciones"
    )
    console.print("[dim](descargando datos, puede tardar unos minutos la primera vez)[/]\n")

    with console.status("corriendo el backtest…"):
        try:
            result = run_backtest(
                seasons=season_list,
                config=config,
                horizon_gameweeks=horizon,
                n_sims=sims,
                seed=seed,
            )
        except ValueError as exc:
            _die(str(exc))
        except Exception as exc:
            _die(f"error en el backtest: {exc}")

    # Tabla de resultados
    from rich.table import Table

    tabla = Table(show_header=True, header_style="bold")
    tabla.add_column("Métrica", min_width=20)
    tabla.add_column("Puro", justify="right")
    tabla.add_column("Ajustado", justify="right")
    tabla.add_column("Mejora", justify="right")

    def _fmt_metric(p: float, a: float) -> tuple[str, str, str]:
        mejora = (p - a) / p * 100 if p > 0 else 0.0
        color = "green" if mejora > 0 else ("red" if mejora < 0 else "")
        mejora_str = f"[{color}]{mejora:+.1f}%[/{color}]" if color else f"{mejora:+.1f}%"
        return f"{p:.4f}", f"{a:.4f}", mejora_str

    bp, ba, mbrier = _fmt_metric(result.brier_pure, result.brier_adjusted)
    lp, la, mlogloss = _fmt_metric(result.logloss_pure, result.logloss_adjusted)

    tabla.add_row("Brier score", bp, ba, mbrier)
    tabla.add_row("Log-loss", lp, la, mlogloss)
    console.print(tabla)

    # Frase honesta sobre la mejora
    brier_pct = result.brier_improvement * 100
    console.print(f"\n[bold]Temporadas usadas:[/] {result.seasons}")
    console.print(f"[bold]Horizonte:[/] {result.horizon_gameweeks} jornadas antes del final")
    console.print(f"[bold]Simulaciones:[/] {result.n_sims}")

    if brier_pct > 0:
        console.print(
            f"\nel modelo ajustado mejora el Brier un [green]{brier_pct:.1f}%[/] "
            f"frente al modelo puro."
        )
    elif brier_pct < 0:
        console.print(
            f"\nel modelo ajustado [red]no mejora[/] el Brier (empeora un "
            f"{abs(brier_pct):.1f}%) — puede que los parametros necesiten ajuste."
        )
    else:
        console.print("\nel modelo ajustado no produce diferencia apreciable en Brier.")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _norm(text: str) -> str:
    return _strip_accents(text).casefold().strip()


def _resolve_team(token: str, teams: list[Team]) -> Team:
    needle = _norm(token)
    if not needle:
        raise ValueError("nombre de equipo vacío")
    exact: list[Team] = []
    partial: list[Team] = []
    for team in teams:
        candidates = {
            _norm(team.id),
            _norm(team.name),
            _norm(team.id.split("-")[-1]),
            _norm(team.name.split()[-1]),
            *(_norm(c) for c in (team.clubelo_name, team.openfootball_name) if c),
        }
        candidates.discard("")
        if needle in candidates:
            exact.append(team)
        elif any(needle in c or c in needle for c in candidates):
            partial.append(team)
    hits = exact or partial
    if len(hits) == 1:
        return hits[0]
    valid = ", ".join(sorted(t.name for t in teams))
    if not hits:
        raise ValueError(f"no reconozco el equipo {token!r}. Equipos válidos: {valid}")
    raise ValueError(
        f"{token!r} es ambiguo (encaja con: {', '.join(t.name for t in hits)}). Sé más específico."
    )


def _parse_fix(spec: str, teams: list[Team]) -> FixedResult:
    m = _FIX_RE.match(spec)
    if not m:
        raise ValueError(
            f'no entiendo --fix {spec!r}; el formato es "Equipo Local 3-2 Equipo Visitante".'
        )
    home_raw, hg_raw, ag_raw, away_raw = m.groups()
    hg, ag = int(hg_raw), int(ag_raw)
    if hg > 20 or ag > 20:
        raise ValueError(f"marcador irreal en --fix {spec!r} (máx. 20 goles por equipo).")
    home = _resolve_team(home_raw, teams)
    away = _resolve_team(away_raw, teams)
    if home.id == away.id:
        raise ValueError(f"--fix {spec!r}: un equipo no puede jugar contra sí mismo.")
    return FixedResult(home_team=home.id, home_goals=hg, away_team=away.id, away_goals=ag)


def _prompt_pending(pending: list[Match], names: dict[str, str]) -> list[FixedResult]:
    if not pending:
        return []
    console.print(
        f"\n{len(pending)} partidos pendientes. Escribe el marcador (p.ej. [bold]2-1[/]) o "
        "Enter para simularlo. Ctrl-D corta y simula el resto.\n"
    )
    out: list[FixedResult] = []
    for m in sorted(pending, key=lambda x: (x.gameweek, x.home_team)):
        home_name = names.get(m.home_team, m.home_team)
        away_name = names.get(m.away_team, m.away_team)
        prompt_label = f"  J{m.gameweek:>2}  {home_name} vs {away_name}  ->"
        try:
            answer = typer.prompt(prompt_label, default="", show_default=False).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim](corto las preguntas; simulo el resto)[/]")
            break
        if not answer:
            continue
        sm = _SCORE_RE.match(answer)
        if not sm:
            err_console.print(f"  [yellow]no entendí {answer!r}; lo dejo al azar.[/]")
            continue
        hg, ag = int(sm.group(1)), int(sm.group(2))
        if hg > 20 or ag > 20:
            err_console.print("  [yellow]marcador irreal; lo dejo al azar.[/]")
            continue
        out.append(
            FixedResult(home_team=m.home_team, home_goals=hg, away_team=m.away_team, away_goals=ag)
        )
    return out


def _format_pct(p: float) -> str:
    return f"{p * 100:05.2f}".replace(".", ",")


def _header_line(season: int, n_played: int, n_pending: int) -> str:
    suffix = "temporada terminada" if n_pending == 0 else f"{n_pending} partidos restantes"
    return f"descenso · LaLiga {season_slug(season)} · {n_played} partidos jugados · {suffix}"


def _ranking_block(
    ranked: list[tuple[str, float]],
    names: dict[str, str],
    applied_fixed: list[tuple[str, str]],
    top: int,
    header: str,
) -> str:
    # Equipos cuya probabilidad no se redondea a 0,00 % (los "candidatos" del tweet).
    shown = [(tid, p) for tid, p in ranked if round(p * 100, 2) > 0.0]
    if top > 0:
        shown = shown[:top]
    elif not shown:  # nadie con P>0 (raro): muestra los 3 últimos de todas formas
        shown = ranked[:3]
    width = max((len(names.get(t, t)) for t, _ in shown), default=0)
    line = "-" * max(40, width + 12)
    parts = [line, "Probabilidad de descenso a 2ª División"]
    if applied_fixed:
        forced = "; ".join(
            f"{names.get(h, h)} vs {names.get(a, a)} fijado" for h, a in applied_fixed
        )
        parts.append(f"(con: {forced}; resto simulado)")
    parts.append("")
    for tid, p in shown:
        parts.append(f"[{_format_pct(p)}%] {names.get(tid, tid)}")
    parts.append(line)
    return "\n".join(parts)


def _render_outcome(outcome: SimulationOutcome) -> None:
    console.print(f"\n[bold]{_header_line(outcome.season, outcome.n_played, outcome.n_pending)}[/]")
    console.print(
        f"[dim]modelo: {outcome.model_type} · {outcome.probabilities.n_sims} sims · "
        f"seed {outcome.probabilities.seed}[/]"
    )
    for note in outcome.notes:
        err_console.print(f"[yellow]nota:[/] {note}")
    for fx, reason in outcome.ignored_fixed:
        names = outcome.team_names
        err_console.print(
            f"[yellow]--fix ignorado:[/] {names.get(fx.home_team, fx.home_team)} "
            f"{fx.home_goals}-{fx.away_goals} {names.get(fx.away_team, fx.away_team)} ({reason})"
        )
    ranked = [(tp.team, tp.p_relegation) for tp in outcome.probabilities.ranked()]
    applied = [(f.home_team, f.away_team) for f in outcome.applied_fixed]
    typer.echo("")
    typer.echo(_ranking_block(ranked, outcome.team_names, applied, top=0, header=""))


def _copy_to_clipboard(text: str) -> bool:
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["pbcopy"]):
        if shutil.which(cmd[0]) is None:
            continue
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), check=True, capture_output=True)
            return True
        except (OSError, subprocess.CalledProcessError):
            continue
    return False


if __name__ == "__main__":
    app()
