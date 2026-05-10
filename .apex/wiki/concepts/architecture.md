# Arquitectura — descenso (C4 + modelo)

# Arquitectura — `descenso`

CLI Python con arquitectura hexagonal ligera: `domain` puro, `adapters` para fuentes de datos externas, `application` con casos de uso, `cli` (Typer + Rich).

## C4 — Contexto

```mermaid
C4Context
title Contexto - descenso
Person(user, "Analista / Fran", "Ejecuta la CLI en terminal")
System(descenso, "descenso", "Modelo de probabilidad de descenso con memoria de forma")
System_Ext(clubelo, "clubelo.com", "Ratings Elo + fixtures (CSV)")
System_Ext(understat, "Understat", "xG/xGA por partido de LaLiga")
System_Ext(fbref, "FBref", "Calendario restante + match logs (verificacion)")
System_Ext(x, "X / Twitter", "Replies de @LaLigaenDirecto (scraping puntual)")
Rel(user, descenso, "simulate / report / compare / backtest")
Rel(descenso, clubelo, "GET Elo, Fixtures", "HTTPS/CSV")
Rel(descenso, understat, "scrape xG", "HTTPS")
Rel(descenso, fbref, "scrape schedule", "HTTPS")
Rel(descenso, x, "scrape replies (1 vez)", "HTTPS")
```

## C4 — Contenedores

```mermaid
C4Container
title Contenedores - descenso
Person(user, "Analista / Fran")
Container_Boundary(c, "descenso (paquete Python)") {
  Container(cli, "CLI", "Typer + Rich", "simulate / report / compare / backtest / data refresh")
  Container(app, "Application", "Use cases", "BuildStrengths, RunSimulation, CompareModels, Backtest, ScrapeReplies")
  Container(domain, "Domain", "Python puro", "Team, Match, Standings, StrengthModel, MatchModel, Simulator")
  Container(adapters, "Adapters", "httpx/pandas", "ClubeloElo, UnderstatXg, FbrefSchedule, CoachChangesFile")
  ContainerDb(cache, "Cache local", "Parquet/SQLite", "datos descargados + resultados de simulacion")
  Container(cfg, "Config", "YAML", "params del modelo + cambios de entrenador/bajas")
}
System_Ext(clubelo, "clubelo.com")
System_Ext(understat, "Understat")
System_Ext(fbref, "FBref")
Rel(user, cli, "comandos")
Rel(cli, app, "invoca")
Rel(app, domain, "usa")
Rel(app, adapters, "obtiene datos via puertos")
Rel(adapters, cache, "lee/escribe")
Rel(adapters, clubelo, "HTTPS")
Rel(adapters, understat, "HTTPS")
Rel(adapters, fbref, "HTTPS")
Rel(cli, cfg, "lee")
```

## El modelo (componente clave) — "memoria de forma"

```mermaid
flowchart TD
  A[Elo base por equipo<br/>clubelo]
  B[Match logs recientes<br/>resultado + xG/xGA]
  C[Cambios de entrenador<br/>+ bajas - config YAML]
  D[Calendario restante]
  E[Resultados fijados por el usuario<br/>opcional]
  B --> F[PerformanceRating por partido<br/>f resultado vs Elo rival, xG-goles, local/visitante]
  F --> G[FormRating equipo<br/>media ponderada exp. half-life ~75d]
  A --> H[R_eff = alpha·Elo + 1-alpha·FormRating<br/>+ delta_coach decae + delta_injuries]
  G --> H
  C --> H
  H --> I[MatchModel<br/>MVP: Elo-logistic W/D/L · v1: bivariate Poisson + Dixon-Coles desde xG]
  D --> J[Monte Carlo simulator<br/>N iteraciones vectorizado numpy]
  E --> J
  I --> J
  J --> K[Standings finales<br/>reglas LaLiga: pts -> head-to-head -> GD -> GF]
  K --> L["P(descenso) por equipo + P(posicion) + P(salvacion)"]
  L --> M[Reporte formato tweet + modo compare puro vs ajustado + Brier backtest]
```

### Definición del modelo (matemática)

- **Elo base** `E_i`: último valor de clubelo.com para el equipo *i*.
- **Performance rating** de un partido jugado por *i* contra *j* (en J fecha *t*):
  - Resultado esperado Elo: `W_exp = 1 / (1 + 10^(-(E_i + h·local - E_j)/400))`.
  - Resultado ajustado por suerte: en lugar del marcador real, mezclar con el resultado "merecido" según xG: `goals_adj = β·goals_real + (1−β)·xG`. Convertir `(goals_adj_i − goals_adj_j)` a un resultado en [0,1] vía función logística suave.
  - `perf = K · (resultado_ajustado − W_exp)` → variación de rating implícita de ese partido.
- **Form rating** `F_i = E_i^{ref} + Σ_t w_t · perf_t / Σ_t w_t`, con `w_t = 0.5^((hoy − t)/half_life)`, `half_life ≈ 75 días` (≈ "los últimos 3 meses pesan; el inicio de temporada casi no").
- **Fuerza efectiva** `R_i = α·E_i + (1−α)·F_i + Δ_coach(i) + Δ_inj(i)`:
  - `α ≈ 0.5` (calibrable por backtest).
  - `Δ_coach`: bonus que decae tras un cambio de entrenador (p.ej. +25 Elo el 1er partido, decae a 0 en ~6 partidos) — efecto rebote documentado.
  - `Δ_inj`: ajuste manual opcional por bajas clave (config YAML).
- **Match model** para simular un partido pendiente *i* vs *j*:
  - **MVP**: `W/D/L` por Elo-logístico sobre `R_i − R_j + h`; muestrear margen de goles de una distribución calibrada (para tiebreakers de GD).
  - **v1**: fuerzas de ataque/defensa derivadas de `R` + xG histórico → **Poisson bivariada con corrección de Dixon-Coles** para marcadores bajos realistas.
- **Monte Carlo**: N iteraciones (default 100.000, vectorizado). Resultados fijados por el usuario se respetan; el resto se muestrea. Cada iteración → clasificación final con reglas LaLiga (puntos → puntos head-to-head entre empatados → diff. goles head-to-head → diff. goles general → goles a favor). Contar posiciones de descenso (bottom 3). Agregar → `P(descenso)_i`.
- **Validación**: backtest sobre 2022-23, 2023-24, 2024-25; en cada jornada predecir y comparar con la realidad. Métricas: **Brier score** y **log-loss**. Comparar modelo puro (`α=1`, sin form, sin bumps) vs. ajustado. Este número es la prueba empírica de que la "memoria de forma" mejora — la respuesta directa a la crítica de adrirbb.

## Stack

Python 3.11+ · `typer` (CLI) · `rich` (progreso/tablas; el ranking final se imprime en texto plano copiable) · `httpx` (fetch) · `pandas` (data wrangling) · `numpy` (Monte Carlo vectorizado) · `scipy` (Poisson/Dixon-Coles) · `pydantic` v2 (config y modelos de dominio) · `pytest` + `pytest-cov` · `ruff` + `black` · `mypy --strict`. Cache: ficheros Parquet en `data/cache/` (+ SQLite opcional). Scraping puntual de X: `scripts/scrape_replies.py` intenta `snscrape`/lectura web y, si falla (frágil), pide pegar los replies en `data/replies.txt`.

## Estructura de directorios

```
descenso/
  pyproject.toml
  README.md  CLAUDE.md
  config.yaml                 # params del modelo
  data/
    coach_changes.yaml        # cambios de entrenador + bumps + bajas (seed manual)
    cache/                    # parquet de datos descargados y simulaciones (gitignored)
    replies.txt               # input del scraping puntual de X (gitignored)
  src/descenso/
    domain/                   # Team, Match, Standings, StrengthModel, MatchModel, Simulator, tiebreakers
    application/              # build_strengths, run_simulation, compare_models, backtest, scrape_replies
    adapters/
      data/                   # clubelo_elo.py, understat_xg.py, fbref_schedule.py, coach_changes_file.py, cache.py
    cli/                      # app.py (Typer): simulate, report, compare, backtest, data
    config.py                 # carga/validación de config.yaml
  scripts/scrape_replies.py   # uso único: investigación de requisitos en X
  tests/                      # unit (domain) + integration (adapters con datos reales cacheados) + e2e (CLI)
  .github/workflows/ci.yml
```

## Nota sobre "Fase 2 visual"

Al ser una herramienta de **terminal** (no app web/móvil), los sub-pasos de design system visual (paleta, tipografía, iconografía, wireframes en Pencil/Stitch, mapa de navegación en Excalidraw) no aplican. El "artefacto visual" equivalente es: (a) los diagramas C4/flow de arriba, (b) el mockup ASCII de la sesión de terminal (ver `concepts/cli-ux`). Iconografía: solo texto/box-drawing, **sin emojis** (regla APEX). Salida del ranking en texto plano para que sea pegable en un tweet.
