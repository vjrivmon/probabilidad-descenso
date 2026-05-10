# probabilidad-descenso

**Probabilidad de descenso en LaLiga con memoria de forma.**

Una herramienta de terminal (CLI en Python) para estimar la probabilidad de que cada equipo baje a Segunda, mejorando el enfoque habitual —10.000/100.000 simulaciones Monte Carlo sobre la clasificación actual— con un factor que la afición lleva tiempo pidiendo: la **tendencia de juego de cada equipo**. En vez de tratar la "fuerza" de un equipo como una foto fija de la tabla, este modelo le da **memoria**:

```
fuerza_efectiva(equipo) = α · Elo_base  +  (1 − α) · FormRating  +  Δ_entrenador  +  Δ_bajas

FormRating = media de "rendimientos por partido" (resultado vs. calidad del rival,
             ajustado por xG − goles para descontar la suerte),
             ponderada exponencialmente con vida media ≈ 75 días
             → lo que se juega desde hace ~3 meses pesa; el inicio de temporada casi no.
```

Esa fuerza alimenta una simulación Monte Carlo del calendario restante (con las reglas de desempate reales de LaLiga: puntos → enfrentamientos directos → diferencia de goles → goles a favor) y produce el ranking en el mismo formato que se publica en redes:

```
[99,71%] Oviedo
[68,40%] Levante
[55,12%] Alavés
...
```

Con `α = 1` y sin ajustes recuperas el **modelo "puro"** (solo Elo), que sirve de línea base: el comando `compare` enseña, equipo a equipo, en qué se diferencia del modelo ajustado y por qué, y `backtest` mide sobre temporadas pasadas (Brier score / log-loss) si la "memoria de forma" realmente predice mejor.

> Origen: este proyecto nace de un hilo en X alrededor de la cuenta [@LaLigaenDirecto](https://x.com/LaLigaenDirecto), donde la comunidad pedía un modelo que tuviera en cuenta cambios de entrenador, rachas, lesiones y "estado de ánimo" en vez de solo probabilidades puras. Es **open source**: las contribuciones son bienvenidas — especialmente a `data/coach_changes.yaml` y a la calibración de `config.yaml`.

## Estado

En construcción. Plan por checkpoints (cada uno usable):

- **CP1 — MVP:** datos (Elo de clubelo + calendario de FBref) → `simulate` / `report` con el modelo puro (reproduce el enfoque de @LaLigaenDirecto).
- **CP2 — el diferencial:** xG de Understat + `StrengthModel` (forma + entrenadores + bajas) + `compare` + `backtest`.
- **CP3 — refinamientos (opcional):** marcadores con Poisson bivariada + Dixon-Coles, autocalibración de α/half-life, feature experimental de sentimiento (NLP), export HTML.

Lo que existe ahora es el **scaffold** (estructura, configuración, CLI con los comandos definidos, tests de humo). La lógica del modelo se implementa en los checkpoints siguientes.

## Stack

Python 3.11+ · [Typer](https://typer.tiangolo.com/) (CLI) · [Rich](https://rich.readthedocs.io/) · httpx · pandas · numpy · scipy · pydantic v2. Cache local en Parquet. Solo fuentes de datos **gratuitas**: [clubelo.com](http://clubelo.com/) (Elo), [Understat](https://understat.com/) (xG), [FBref](https://fbref.com/) (calendario).

## Cómo empezar

```bash
# 1. Clonar y crear un entorno
git clone https://github.com/vjrivmon/probabilidad-descenso.git
cd probabilidad-descenso
python3 -m venv .venv && source .venv/bin/activate

# 2. Instalar (modo editable, con dependencias de desarrollo)
pip install -e ".[dev]"

# 3. Comandos (los que aún no están implementados avisan; ver "Estado")
descenso --help
descenso data refresh        # descarga Elo + calendario + xG al cache local
descenso simulate            # interactivo: introduce resultados o deja todo al azar
descenso simulate --fix "Levante 3-2 Osasuna" --sims 100000 --seed 1
descenso report --copy       # imprime el ranking en formato tweet y lo copia al portapapeles
descenso compare             # modelo puro vs ajustado, con la diferencia por equipo
descenso backtest --seasons 2022,2023,2024 --horizon 5
```

Toda la configuración del modelo (α, vida media de la forma, ventaja de campo, bonus por cambio de entrenador, nº de simulaciones...) está en [`config.yaml`](config.yaml). Los cambios de entrenador y las bajas, en [`data/coach_changes.yaml`](data/coach_changes.yaml).

## Cómo testear

```bash
pytest                       # tests
pytest --cov --cov-report=html   # cobertura -> htmlcov/index.html
ruff check src tests         # lint
black --check src tests      # formato
mypy src tests               # tipos
```

## Cómo funciona (resumen)

| Capa | Qué hace |
|------|----------|
| `descenso.domain` | Entidades puras (`Team`, `Match`), clasificación + desempates de LaLiga, modelo de fuerza con memoria de forma, modelo de partido, simulador Monte Carlo vectorizado. Sin IO. |
| `descenso.adapters.data` | Descarga y cachea Elo (clubelo), calendario (FBref), xG (Understat); lee `coach_changes.yaml` y `team_aliases.yaml`. |
| `descenso.application` | Casos de uso: construir fuerzas, correr simulación, comparar modelos, backtest. |
| `descenso.cli` | La interfaz de terminal (Typer + Rich). |

Más detalle (diagramas C4, modelo de datos, definición matemática del modelo, edge cases) en `.apex/wiki/` mientras el proyecto está en desarrollo.

## Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md). En corto: abre un issue para discutir, los cambios de modelo deben venir con su justificación (idealmente un número de backtest), y los datos que añadas a `data/` deben ser **verificables**.

## Licencia

MIT — ver [LICENSE](LICENSE).
