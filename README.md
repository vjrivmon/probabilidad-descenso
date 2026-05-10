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

Plan por checkpoints (cada uno usable):

- **CP0 — investigación (hecho):** recopilados los tweets de @LaLigaenDirecto y los replies/menciones dirigidos a él (con un Chrome logueado controlado vía CDP, sin la API de X — ver `scripts/scrape_x_browser.py`) y resumidos en [`docs/community-factors.md`](docs/community-factors.md). Conclusión corta: lo que más se pide es que el modelo "refleje el calendario" (ya lo hace: es un tema de comunicación) y que se explique mejor / actualice más rápido; xG y forma tienen soporte moderado; el "estado de ánimo" como factor apenas tiene demanda en los replies.
- **CP1 — MVP (funcionando):** `data refresh` (Elo de clubelo + calendario de [openfootball](https://github.com/openfootball/football.json)), dominio + simulador Monte Carlo vectorizado, `simulate` / `report` con el modelo puro (reproduce el enfoque de @LaLigaenDirecto). 100 000 simulaciones en ~1 s.
- **CP2 — el diferencial (funcionando):** `StrengthModel` con memoria de forma (rendimiento reciente ponderado exp. vs. Elo + decaimiento + bumps de entrenador / bajas de `coach_changes.yaml`), cableado en `simulate`; `compare` (puro vs. ajustado, equipo a equipo) y `backtest` (Brier / log-loss sobre temporadas pasadas, sin data leakage). La parte de **xG de Understat** está implementada pero hoy *inactiva* (ver nota); el análisis de sensibilidad de los parámetros está en [`docs/sensitivity.md`](docs/sensitivity.md).
- **CP3 — refinamientos (funcionando, salvo el sentimiento):** modelo de marcador **Poisson bivariada + Dixon-Coles** opcional (`model.match_model: dixon_coles` en `config.yaml`): los goles esperados de cada equipo salen de su fuerza efectiva (escala Elo) y los marcadores de dos Poisson independientes con la corrección de Dixon-Coles para los resultados bajos — marcadores más realistas, mejor fidelidad al desempate por diferencia de goles. `descenso calibrate` autocalibra `alpha` / `form_half_life_days` / `form_k_factor` minimizando el Brier del backtest (scipy Nelder-Mead, seed fija; no toca `config.yaml`, solo sugiere). `descenso report --html informe.html` escribe un informe HTML estático autocontenido (CSS y gráfico de barras SVG en línea, sin JavaScript). Pendiente: feature experimental de **sentimiento** (NLP) — depende del CP0 (analizar los replies de @LaLigaenDirecto), que aún no se ha hecho.

> Nota sobre las fuentes: FBref está detrás de Cloudflare y no es scrapeable → el calendario sale de `openfootball/football.json` (repo público, sin clave). El Elo viene de la API CSV de clubelo.com (endpoint de fecha). **Understat** ha dejado de servir a clientes no-navegador el bloque de datos embebido con el xG: `descenso data refresh` lo intenta y, si falla, sigue sin xG avisándolo; el modelo degrada solo a "solo goles reales". Si vuelve a ser accesible (o aparece otra fuente de xG), el modelo lo incorpora sin más cambios.

## Stack

Python 3.11+ · [Typer](https://typer.tiangolo.com/) (CLI) · [Rich](https://rich.readthedocs.io/) · httpx · pandas · numpy · scipy · pydantic v2. Cache local en Parquet. Solo fuentes de datos **gratuitas**: [clubelo.com](http://clubelo.com/) (Elo, API CSV), [openfootball/football.json](https://github.com/openfootball/football.json) (calendario), [Understat](https://understat.com/) (xG, CP2).

## Cómo empezar

```bash
# 1. Clonar y crear un entorno
git clone https://github.com/vjrivmon/probabilidad-descenso.git
cd probabilidad-descenso
python3 -m venv .venv && source .venv/bin/activate

# 2. Instalar (modo editable, con dependencias de desarrollo)
pip install -e ".[dev]"

# 3. Comandos
descenso --help
descenso data refresh                       # descarga Elo + calendario al cache local
descenso data show                          # qué hay en el cache y de qué fecha
descenso simulate                           # interactivo: introduce resultados o deja todo al azar
descenso simulate --no-interactive --sims 100000 --seed 1
descenso simulate --fix "Levante 3-2 Osasuna" --fix "Oviedo 0-0 Getafe"
descenso report --copy                      # reimprime el último ranking y lo copia al portapapeles
descenso report --top 6
descenso report --html informe.html         # además, escribe un informe HTML estático
descenso compare --sims 50000 --seed 1      # modelo puro vs. ajustado, equipo a equipo, con la nota del factor responsable
descenso backtest --seasons 2022,2023 --horizon 8   # Brier / log-loss puro vs. ajustado sobre temporadas pasadas
descenso calibrate --seasons 2022,2023 --horizon 8  # autocalibra alpha / half-life / K minimizando el Brier del backtest
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
| `descenso.adapters.data` | Descarga y cachea Elo (clubelo), calendario (openfootball), xG (Understat, CP2); lee `coach_changes.yaml` y `team_aliases.yaml`. Cache Parquet con escritura atómica; modo offline (`prefer_cache`) para que `simulate`/`report` no toquen la red. |
| `descenso.application` | Casos de uso: correr simulación (`run_simulation`), construir fuerzas (CP2), comparar modelos (CP2), backtest (CP2), autocalibración (`calibrate`, CP3), informe HTML (`export_html`, CP3). |
| `descenso.cli` | La interfaz de terminal (Typer + Rich). |

Más detalle (diagramas C4, modelo de datos, definición matemática del modelo, edge cases) en `.apex/wiki/` mientras el proyecto está en desarrollo.

## Contribuir

Lee [CONTRIBUTING.md](CONTRIBUTING.md). En corto: abre un issue para discutir, los cambios de modelo deben venir con su justificación (idealmente un número de backtest), y los datos que añadas a `data/` deben ser **verificables**.

## Licencia

MIT — ver [LICENSE](LICENSE).
