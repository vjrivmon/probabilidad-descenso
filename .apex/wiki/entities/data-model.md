# Modelo de datos — descenso

# Modelo de datos — `descenso`

No hay base de datos relacional: los datos viven en memoria (pydantic) y se cachean en **Parquet** bajo `data/cache/`. El "esquema" es el de esos dataframes/objetos.

```mermaid
erDiagram
  TEAM ||--o{ MATCH : "juega (local/visitante)"
  TEAM ||--o{ COACH_CHANGE : tiene
  TEAM ||--o{ INJURY_ADJUSTMENT : tiene
  TEAM ||--o{ STRENGTH_SNAPSHOT : "se calcula"
  SIMULATION_RUN ||--o{ RELEGATION_RESULT : produce
  TEAM ||--o{ RELEGATION_RESULT : "aparece en"

  TEAM {
    string id PK "slug interno, ej. real-oviedo"
    string name "nombre display"
    string clubelo_name "nombre en clubelo.com"
    string understat_id "id en Understat"
    string fbref_id "id en FBref"
    float elo_base "último Elo clubelo"
    int position "posición actual en LaLiga"
    int points "puntos actuales"
    int gf "goles a favor"
    int ga "goles en contra"
  }
  MATCH {
    string id PK
    int season "año de inicio, ej. 2025"
    int gameweek "jornada 1..38"
    date date "fecha (puede ser tentativa si pendiente)"
    string home_team FK
    string away_team FK
    int home_goals "null si pendiente"
    int away_goals "null si pendiente"
    float home_xg "null si no disponible"
    float away_xg "null si no disponible"
    string status "played | pending"
    bool is_fixed "true si el usuario fijó el resultado en simulate"
  }
  COACH_CHANGE {
    string team FK
    date date "fecha del cambio"
    string new_coach
    float elo_bump "bonus inicial; null = usar default de config"
    string notes
  }
  INJURY_ADJUSTMENT {
    string team FK
    date as_of_date
    float elo_delta "ajuste manual (típ. negativo)"
    string notes "jugador(es) y motivo"
  }
  STRENGTH_SNAPSHOT {
    string team FK
    date as_of_date
    float elo_base
    float form_rating
    float delta_coach
    float delta_injuries
    float r_eff "fuerza efectiva final"
  }
  SIMULATION_RUN {
    string id PK "timestamp"
    datetime created_at
    int n_sims
    int seed
    string model_type "pure | adjusted"
    string config_hash "hash de config.yaml + datos usados"
    string fixed_results "JSON de resultados fijados"
  }
  RELEGATION_RESULT {
    string simulation_run_id FK
    string team FK
    float p_relegation
    float p_18th
    float p_19th
    float p_20th
    float p_safe
    float expected_points
    float expected_position
  }
```

## Ficheros de configuración (no en DB)

- `config.yaml`: `alpha` (blend Elo/forma), `form_half_life_days` (≈75), `home_advantage` (Elo points), `coach_bump_default` y `coach_bump_decay_matches`, `xg_blend_beta` (peso goles vs xG en el performance rating), `n_sims` default, `model_type` default, rutas de cache.
- `data/coach_changes.yaml`: lista seed de cambios de entrenador de la temporada actual + ajustes de bajas. Editable por colaboradores; es la pieza "humana/verificable" del modelo.
