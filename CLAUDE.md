# CLAUDE.md — guía para agentes en este repositorio

## Qué es esto

`probabilidad-descenso` — CLI en Python que estima la probabilidad de descenso en LaLiga con un modelo de fuerza **con memoria de forma** (Elo de clubelo + xG de Understat + rendimiento reciente ponderado exponencialmente + ajustes por cambio de entrenador / bajas), simulada con Monte Carlo sobre el calendario restante. Repo **público, open source (MIT)**. El paquete/CLI se llama `descenso`; el repo en GitHub, `probabilidad-descenso`.

Contexto del nacimiento del proyecto, decisiones, diagramas y edge cases: en `.apex/wiki/` (gestionado con el sistema APEX — ver `.apex/`).

## Reglas del proyecto

- **Idioma**: código, comentarios, docstrings, mensajes de la CLI y commits en **español**. Nombres de símbolos en inglés si encaja.
- **Sin emojis** como iconos en el código ni en la salida (texto plano / box-drawing).
- **Dominio puro**: `src/descenso/domain/` no hace IO ni red — para que sea testeable y backtesteable. Toda IO va en `src/descenso/adapters/`.
- **Errores explícitos**: nunca tragarse una excepción con un mensaje genérico. Si una fuente externa falla, decir qué URL y qué se esperaba; loguear el traceback.
- **Reproducibilidad**: RNG explícito (`np.random.default_rng(seed)`), nunca el `random` global.
- **Sin data leakage en el backtest**: al predecir la jornada N, usar solo partidos con fecha ≤ N y el Elo de esa fecha. Hay (debe haber) un test que lo verifica.
- **Datos verificables**: lo que entre en `data/coach_changes.yaml` debe tener fecha y fuente. El modelo no inventa cambios de entrenador.
- **Monte Carlo vectorizado**: 100k simulaciones deben correr en pocos segundos → numpy vectorizado, nada de bucles Python por iteración.
- **Conventional commits** (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`).

## Stack

Python ≥3.11 · Typer · Rich · httpx · pandas · numpy · scipy · pydantic v2 · PyYAML · pyarrow. Dev: pytest + pytest-cov · ruff · black · mypy (strict) · respx. Cache local en Parquet bajo `data/cache/` (gitignored).

## Comandos

```bash
pip install -e ".[dev]"          # instalar
ruff check src tests             # lint
black --check src tests          # formato
mypy src tests                   # tipos
pytest --cov --cov-report=term-missing   # tests + cobertura
descenso --help                  # la CLI
```

## Estructura

- `src/descenso/domain/` — `Team`, `Match`, `standings`/`tiebreakers` (reglas LaLiga, incl. mini-liga de empates a 3+), `strength_model` (el diferencial), `match_model` (Elo-logístico en CP1; Poisson+Dixon-Coles en CP3), `simulator` (Monte Carlo vectorizado), `probabilities`.
- `src/descenso/adapters/data/` — `clubelo_elo` (Elo, endpoint de fecha de clubelo.com), `schedule` (calendario LaLiga vía openfootball/football.json — FBref está tras Cloudflare; `data/fixtures_override.csv` como salida de emergencia), `understat_xg` (xG; **Understat ya no sirve el bloque de datos embebido a clientes no-navegador → el adaptador levanta `UnderstatError` y el modelo degrada solo a "solo goles reales"; el cableado está listo para cuando vuelva a ser accesible**), `coach_changes_file`, `team_aliases`, `cache` (Parquet atómico). Los `fetch_*` aceptan `prefer_cache=True` para modo offline (`simulate`/`report` leen el cache; `data refresh` fuerza red).
- `src/descenso/application/` — `build_strengths`, `run_simulation`, `compare_models`, `backtest`, `scrape_replies` (CP0, uso único).
- `src/descenso/cli/app.py` — Typer: `data refresh|show`, `simulate`, `report`, `compare`, `backtest`.
- `config.yaml` — parámetros del modelo. `data/coach_changes.yaml`, `data/team_aliases.yaml` — datos editables.
- `tests/` — `domain/` (unit), smoke de la CLI; integración con datos cacheados; e2e.

## Checkpoints (estado del roadmap)

- **CP1 (MVP)**: `data refresh` (Elo de clubelo + calendario de openfootball), dominio + simulador, `simulate`/`report` con modelo **puro**. Criterio: `descenso simulate --no-interactive --seed 1 --sims 100000` < 5 s, ranking coherente con la tabla real, tests y CI verdes.
- **CP2 (hecho, salvo xG)**: `StrengthModel` (forma/entrenadores/bajas) cableado en `simulate`, `compare`, `backtest` (sin data leakage). Understat (xG) implementado pero inactivo (ver arriba). El backtest imprime Brier/log-loss puro vs ajustado; sin xG la mejora es modesta (~0.5-1.5%, ver `docs/sensitivity.md`), no el ≥5% del SPEC (ese objetivo asume el modelo completo con xG). Params nuevos en `config.yaml`: `form_k_factor` (default 40.0), `form_goal_diff_scale` (1.0).
- **CP3 (opcional)**: Poisson+Dixon-Coles, autocalibración, sentimiento NLP (opt-in, experimental), export HTML.
