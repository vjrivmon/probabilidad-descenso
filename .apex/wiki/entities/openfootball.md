# openfootball/football.json — fuente del calendario

# openfootball/football.json

Repo público en GitHub ([openfootball/football.json](https://github.com/openfootball/football.json)) con calendarios + resultados de ligas en JSON, sin API key.

- **URL usada:** `https://raw.githubusercontent.com/openfootball/football.json/master/<temporada>/es.1.json` — p.ej. `2025-26/es.1.json` (carpeta = `season_slug(year)` → `"2025-26"`).
- **Formato:** `{"name": "...", "matches": [{"round": "Matchday 35", "date": "2026-05-08", "time": "21:00", "team1": "Levante UD", "team2": "CA Osasuna", "score": {"ht": [..], "ft": [1,3]}}, ...]}`. Si `score` está vacío / sin `ft` → partido pendiente. La jornada es solo etiqueta; lo que identifica un partido es `(temporada, team1, team2)`.
- **Nombres de equipo:** versión "larga" en español ("FC Barcelona", "Club Atlético de Madrid", "Real Betis Balompié", ...). Mapeados a los `id` internos vía el campo `openfootball_name` de `data/team_aliases.yaml` (verificado contra la respuesta real, 2026-05-10: 20 equipos LaLiga 2025-26, 380 partidos).
- **Por qué openfootball y no FBref:** FBref (`fbref.com/en/comps/12/schedule/...`) está detrás de Cloudflare y devuelve 403 ("Just a moment...") a cualquier cliente que no sea un navegador real — no es scrapeable con headers/backoff. openfootball cubre exactamente lo que necesita el CP1 sin coste ni clave. La verificación contra match logs de FBref (prevista en el SPEC para CP3) queda aplazada. Ver decisión #9.
- **Fallback:** `OpenFootballScheduleSource` cachea en `data/cache/schedule_<season>.parquet`; si la red falla y hay cache, lo usa avisando; si no hay cache, intenta `data/fixtures_override.csv` (columnas: `season,gameweek,date,home_team,away_team,home_goals,away_goals`; goles vacíos = pendiente); si tampoco, error explícito.
- **Riesgo conocido:** openfootball puede ir 1-2 jornadas por detrás respecto a los resultados más recientes. Mitigación: `data/fixtures_override.csv` + `--fix` para forzar resultados ya jugados que falten.

[Source: Web, 2026-05-10]
