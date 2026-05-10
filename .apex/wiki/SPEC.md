# SPEC — descenso

# SPEC — `descenso`

## Problema

Los modelos públicos de probabilidad de descenso de LaLiga (@LaLigaenDirecto, eldescenso.com, asegunda.com) estiman la fuerza de cada equipo a partir de la foto fija de hoy (clasificación / Elo lento) y simulan el calendario restante. Al ser *memoryless*, los porcentajes oscilan de forma aparentemente arbitraria y no reflejan tendencia de juego, xG, cambios de entrenador ni bajas. Ver `concepts/problem-analysis`.

## Solución

CLI Python (`descenso`) que reemplaza la estimación de fuerza por una **fuerza efectiva con memoria de forma** — `R_i = α·Elo_base + (1−α)·FormRating_i + Δ_entrenador + Δ_bajas` — y la usa en una simulación Monte Carlo del calendario restante con las reglas de desempate de LaLiga. Salida en el formato exacto del tweet de Fran, más un modo `compare` (puro vs ajustado) y un `backtest` que mide la mejora (Brier/log-loss) sobre 2022-25. Ver `concepts/architecture`.

## Usuarios

- **Vicente (VisiLUD)** — desarrolla; quiere una herramienta defendible con datos verificables.
- **Fran Martínez (@LaLigaenDirecto)** — destinatario; trabaja en terminal; podría adoptarla porque replica su UX.
- **Colaboradores** (adrirbb y otros de los replies) — pueden editar `data/coach_changes.yaml` y los params de `config.yaml`, proponer factores.
- Frecuencia: tras cada jornada (≈ semanal) en el tramo final de temporada. Funciona **offline** una vez los datos están cacheados.

## Funcionalidad core (MVP — checkpoint 1)

- `descenso data refresh` → descarga Elo (clubelo) + calendario LaLiga (FBref) → cache parquet.
- Dominio: `Team`, `Match`, `Standings` con desempates LaLiga (pts → head-to-head → GD → GF), `EloLogisticMatchModel`, `Simulator` Monte Carlo **vectorizado** (numpy).
- `descenso simulate` interactivo (pide goles de cada partido pendiente, Enter = simular; `--fix "Levante 3-2 Osasuna"` repetible; `--sims N`, `--seed N`, `--no-interactive`) → ranking `[XX,XX%] Equipo` con el modelo **solo-Elo** (≈ reproduce el de Fran).
- `descenso report [--copy] [--top N]` → imprime el ranking de la última simulación en formato tweet.

## Funcionalidad extendida

**v1 — memoria de forma (checkpoint 2, el diferencial):**
- `UnderstatXgSource` (xG/xGA por partido, temporada actual).
- `StrengthModel`: `FormRating` (performance ratings ponderados exp., half-life ~75d), `R_eff` (blend α), `Δ_coach` (decae) leído de `data/coach_changes.yaml`, `Δ_inj` manual.
- `descenso compare` → tabla puro vs ajustado + Δ + nota explicativa por equipo.
- `descenso backtest [--seasons 2022,2023,2024] [--horizon 5]` → Brier score + log-loss, puro vs ajustado, sobre temporadas pasadas.
- `config.yaml` con todos los parámetros del modelo; análisis de sensibilidad documentado.

**v2 — refinamientos (checkpoint 3, opcional):**
- `BivariatePoissonDixonColesMatchModel` (marcadores realistas, fidelidad total al desempate por GD/H2H).
- Autocalibración de `α` y `half_life` minimizando el Brier del backtest.
- Feature experimental de **sentimiento** (NLP sobre replies/prensa) como ajuste extra opt-in y claramente etiquetado — solo si la investigación del checkpoint 0 sugiere que aporta.
- Export de informe HTML estático; matriz what-if; helper `descenso publish` que formatea (y opcionalmente publica) el tweet.

**Checkpoint 0 — investigación (uso único, paralelo, no bloquea):** `scripts/scrape_replies.py` → extraer los replies a @LaLigaenDirecto (o pegarlos en `data/replies.txt`) → `docs/community-factors.md` con los factores más pedidos, rankeados. Valida/ajusta el set de features.

## Stack

Python 3.11+ · Typer · Rich · httpx · pandas · numpy · scipy · pydantic v2 · pytest+cov · ruff · black · mypy. Cache Parquet. Repo GitHub **privado** llamado `descenso`. CI: GitHub Actions (lint + mypy + tests). Ver decisión #5.

## Arquitectura

Hexagonal ligera: `domain` puro / `adapters/data` (clubelo, understat, fbref, coach-changes-file, cache) / `application` (build_strengths, run_simulation, compare_models, backtest, scrape_replies) / `cli` (Typer). Ver `concepts/architecture` (diagramas C4 + flujo del modelo).

## Restricciones

- Solo fuentes de datos gratuitas (clubelo, Understat, FBref). Sin APIs de pago.
- Scraping resiliente: si una fuente cambia el HTML, error claro con URL y uso del cache previo avisando de la fecha — nunca un fallo silencioso.
- 100k simulaciones deben correr en pocos segundos (vectorización numpy obligatoria).
- `data/coach_changes.yaml` es entrada manual verificable; el modelo no inventa cambios de entrenador.
- Nombres de equipo: tabla de mapeo única clubelo ↔ understat ↔ fbref ↔ id interno.
- Sin emojis como iconos en código/salida (regla APEX); box-drawing y texto plano.

## Métricas de éxito

1. **Calibración**: en el backtest 2022-25 a 5 jornadas del final, Brier del modelo ajustado ≤ Brier del modelo puro (objetivo: mejora ≥ 5%). Si no se cumple, se documenta honestamente y se itera `config.yaml`.
2. **Estabilidad**: la varianza jornada-a-jornada de P(descenso) del modelo ajustado es menor que la del puro sobre el mismo backtest (menos "baile").
3. **Adoptabilidad**: `descenso simulate` produce, en <5 s para 100k sims, una salida copiable idéntica en formato al tweet de @LaLigaenDirecto.
4. **Explicabilidad**: `descenso compare` da, para cada equipo cuya prob. cambia ≥3 pp, una nota con el factor responsable (forma / xG / entrenador / bajas).

## Criterios de "hecho" por checkpoint

- **CP0**: `docs/community-factors.md` existe con ≥1 ronda de replies analizada y los factores rankeados.
- **CP1**: `descenso data refresh` y `descenso simulate --no-interactive --seed 1 --sims 100000` corren sin error en <5 s y dan un ranking coherente con la tabla real; tests de standings/tiebreakers/simulator verdes; CI verde; README con cómo arrancar y testear.
- **CP2**: `descenso compare` y `descenso backtest` funcionan; el backtest imprime Brier/log-loss puro vs ajustado; tests del `StrengthModel` (matemática de form rating, decay, blend) verdes; CI verde; sensibilidad de params documentada.
- **CP3** (opcional): match model Poisson+Dixon-Coles con tests; (opcional) autocalibración; (opcional) feature de sentimiento etiquetada experimental; CI verde.
