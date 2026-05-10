"""CLI `descenso` — punto de entrada.

Subcomandos:
    descenso data refresh   Descarga/actualiza Elo (clubelo), calendario (FBref) y xG (Understat).
    descenso data show      Muestra qué hay en el cache y de qué fecha.
    descenso simulate       Interactivo: pide goles de cada partido pendiente (Enter = simular).
    descenso report         Imprime el ranking de la última simulación en formato tweet.
    descenso compare        Tabla modelo puro vs ajustado + Δ + nota.   (CP2)
    descenso backtest       Brier / log-loss puro vs ajustado sobre temporadas pasadas.  (CP2)
"""

from __future__ import annotations

import typer

app = typer.Typer(
    help="Probabilidad de descenso en LaLiga con memoria de forma.", no_args_is_help=True
)
data_app = typer.Typer(help="Gestión de los datos (Elo, calendario, xG).", no_args_is_help=True)
app.add_typer(data_app, name="data")


@data_app.command("refresh")
def data_refresh() -> None:
    """Descarga/actualiza los datos externos al cache local."""
    raise typer.Exit(_not_yet("data refresh"))


@data_app.command("show")
def data_show() -> None:
    """Muestra el contenido y la antigüedad del cache."""
    raise typer.Exit(_not_yet("data show"))


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
    raise typer.Exit(_not_yet("simulate"))


@app.command()
def report(
    copy: bool = typer.Option(False, "--copy", help="copiar el ranking al portapapeles"),
    top: int = typer.Option(
        0, help="mostrar solo los N equipos con más probabilidad (0 = todos los candidatos)"
    ),
) -> None:
    """Imprime el ranking de la última simulación en formato tweet."""
    raise typer.Exit(_not_yet("report"))


@app.command()
def compare(
    sims: int = typer.Option(50_000, help="número de simulaciones por modelo"),
    seed: int = typer.Option(None, help="semilla para reproducibilidad"),
) -> None:
    """Compara el modelo puro (solo Elo) con el ajustado (Elo + forma + xG + entrenadores)."""
    raise typer.Exit(_not_yet("compare"))


@app.command()
def backtest(
    seasons: str = typer.Option(
        "2022,2023,2024", help="temporadas (año de inicio) separadas por comas"
    ),
    horizon: int = typer.Option(5, help="jornadas antes del final desde las que predecir"),
    sims: int = typer.Option(20_000, help="simulaciones por predicción"),
) -> None:
    """Backtest histórico: Brier / log-loss del modelo puro vs el ajustado."""
    raise typer.Exit(_not_yet("backtest"))


def _not_yet(cmd: str) -> int:
    typer.secho(
        f"[descenso] '{cmd}' aún no está implementado (scaffold de Fase 5).", fg=typer.colors.YELLOW
    )
    return 1


if __name__ == "__main__":
    app()
