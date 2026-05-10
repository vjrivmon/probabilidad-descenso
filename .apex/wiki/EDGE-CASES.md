# Edge cases — descenso

# Edge cases — `descenso`

Prioridad: **[B]** = bloquea el MVP (CP1) · **[B2]** = bloquea CP2 · **[P]** = post-MVP / nice-to-have.

## 1. Fuentes de datos externas

- **[B] clubelo.com caído o cambia el formato CSV.** → Error claro con la URL y el código HTTP; si hay cache previo, usarlo avisando de la fecha ("⚠ usando Elo del 2026-05-02, no he podido refrescar"); si no hay cache, abortar con instrucciones. Nunca seguir con Elo=0.
- **[B] FBref devuelve 403 / rate-limit (suele pasar con scraping agresivo).** → Backoff + un solo reintento; respetar `robots.txt`/delays; cachear agresivamente; mensaje claro si falla. Permitir un fichero de calendario manual `data/fixtures_override.csv` como salida de emergencia.
- **[B2] Understat cambia el HTML/JSON embebido (el `JSON.parse(...)` dentro de `<script>`).** → Parser defensivo: si no encuentra el bloque esperado, error explícito ("el formato de Understat cambió, abre un issue") en vez de un stacktrace; degradar a modelo solo-Elo (`α=1`) avisándolo en el header.
- **[B] Nombres de equipo no coinciden entre fuentes** (clubelo "Ath Bilbao" vs understat "Athletic Club" vs fbref "Athletic Club" vs id interno "athletic-club"). → Tabla de mapeo única `data/team_aliases.yaml`; al cargar, si un nombre de una fuente no está en el mapeo → error que nombra el alias huérfano y para. Tests que verifican que los 20 equipos de la temporada mapean en las 3 fuentes.
- **[P] clubelo no tiene a un equipo recién ascendido todavía** (Elo provisional). → Usar el Elo de "promoción" de clubelo si existe; si no, inicializar con el Elo medio de los 3 últimos ascendidos históricos y marcarlo como `low_confidence`.
- **[B] Sin conexión a internet.** → `data refresh` falla limpio; el resto de comandos funcionan con el cache; si no hay cache, mensaje claro: "ejecuta `descenso data refresh` con conexión primero".
- **[P] Respuesta HTTP 200 pero cuerpo vacío / truncado.** → Validar tamaño/estructura mínima antes de cachear; no sobrescribir un cache bueno con basura.

## 2. Datos del calendario / resultados

- **[B] Partido aplazado sin fecha nueva** (habitual en LaLiga: lluvia, coincidencia con competición europea, etc.). → Tratarlo como pendiente normal (cuenta para la simulación); si se juega fuera de orden, la jornada es solo una etiqueta, lo que importa es que el partido exista una vez. Deduplicar por `{season, home, away}` no por `{season, gameweek}`.
- **[B] Partido contado dos veces** (aparece como pendiente en una fuente y jugado en otra). → La fuente "jugado con resultado" gana; deduplicar por equipos+temporada.
- **[B] El usuario fija un resultado para un partido ya jugado** (`--fix "Levante 3-2 Osasuna"` cuando ya terminó 1-1). → Avisar ("ese partido ya se jugó 1-1; ¿quieres sobrescribirlo? usa --force") y por defecto ignorar el fix.
- **[B] El usuario fija un partido que no existe / equipo mal escrito** (`--fix "Barca 2-0 RealMadrid"`). → Fuzzy match contra los alias; si la confianza es baja, error que lista los nombres válidos. No fallar silenciosamente dejando el partido al azar.
- **[B] Marcador absurdo en un fix** (`--fix "Levante 99-0 Osasuna"` o negativo). → Validar 0 ≤ goles ≤ 20 (cota generosa); rechazar negativos/no-enteros con mensaje.
- **[B] Cero partidos pendientes** (temporada terminada). → No simular: imprimir la clasificación final real y P(descenso) = {1.0 para los 3 últimos, 0.0 resto}. Mensaje: "temporada terminada, esto es el resultado real".
- **[P] Un equipo retirado de la competición / sanción administrativa de puntos.** → Soportar un `points_adjustment` por equipo en config (poco probable pero existe el precedente). Fuera de MVP.
- **[B] Resta de puntos / arrastre histórico mal aplicado** → La clasificación de partida se calcula SIEMPRE desde los partidos jugados + ajustes explícitos, nunca se "confía" en una tabla scrapeada como verdad sin recomputarla.

## 3. Reglas de LaLiga / desempates

- **[B] Empate a puntos entre 2 equipos.** → Desempate: 1) puntos en los enfrentamientos directos, 2) dif. de goles en los directos, 3) dif. de goles general, 4) goles a favor general. (Si los directos aún no se han jugado todos, los puntos directos pueden estar incompletos — usar lo disponible; en la simulación los directos siempre acaban jugados, así que ahí es consistente.)
- **[B] Empate a puntos entre 3+ equipos** ("mini-liga" de enfrentamientos directos). → Construir la sub-clasificación solo con los partidos entre los empatados (puntos → dif. goles en esa mini-liga → ...); si sigue el empate, dif. de goles general → goles a favor. Implementar el algoritmo recursivo (al eliminar uno, los demás pueden seguir empatados). **Esto es lo más fácil de implementar mal** — tests dedicados con escenarios reales (p.ej. el triple empate Cádiz/Granada/Almería 23/24).
- **[B] Empate absoluto irresoluble** (mismos puntos, mismo H2H, mismo GD, mismos GF — raro pero posible en una simulación). → Desempatar por sorteo determinista con la `seed` (no por orden alfabético, eso sesgaría). Documentarlo.
- **[P] Plazas de descenso ≠ 3** (no aplica a LaLiga ahora, pero parametrizar `n_relegation=3` por si acaso). → Config.

## 4. El modelo / la matemática

- **[B2] Un equipo tiene < N partidos en la ventana de forma** (recién ascendido a mitad de cómputo, o inicio de temporada). → `FormRating` con los partidos que haya; si hay 0, `R_eff = Elo_base` (degradar a puro para ese equipo) y marcarlo. No dividir por cero en `Σw_t`.
- **[B2] `α` fuera de [0,1] o `half_life ≤ 0` en config.yaml.** → Validación pydantic con mensaje; no arrancar.
- **[B2] xG faltante para algunos partidos pero no todos.** → El performance rating de ese partido usa solo el resultado real (`β=1` para ese partido), no se descarta el partido.
- **[B2] Cambio de entrenador con fecha futura o malformada en `coach_changes.yaml`.** → Validación de fechas; ignorar (con warning) cambios con fecha posterior a "hoy".
- **[B2] Dos cambios de entrenador del mismo equipo muy seguidos.** → El `Δ_coach` se cuenta desde el más reciente; no se acumulan bumps.
- **[B] N simulaciones = 0 o negativo.** → Validar `--sims ≥ 1` (recomendado ≥ 1000 con warning si menos).
- **[B] Probabilidad de empate degenera** (si el modelo logístico da P(draw) ≈ 0 para diferencias de fuerza grandes). → Modelo de empate con un suelo razonable calibrado (los empates en LaLiga rondan el 25%); no permitir P(draw)=0.
- **[P] Overflow/underflow en `10^(x/400)` para diferencias de Elo enormes** (no debería pasar con valores reales ~1300-2000). → Clip de la diferencia a ±1000.
- **[B] Reproducibilidad rota** (resultado distinto con la misma seed). → RNG explícito (`np.random.default_rng(seed)`), nada de `random` global; test que corre dos veces con la misma seed y compara.
- **[B2] Backtest con data leakage** (usar xG/Elo de fechas posteriores a la jornada que se predice). → El backtest debe reconstruir el estado **as-of** la jornada N (solo partidos ≤ N, Elo de esa fecha). Test que verifica que ningún input del backtest tiene fecha > la jornada predicha. Es el bug más peligroso del CP2.
- **[P] Todas las temporadas del backtest tienen muy pocos equipos "en peligro real"** (poca señal para el Brier). → Reportar también el Brier restringido a los ~6 equipos de la zona baja, no solo los 20.

## 5. CLI / UX / entorno

- **[B] Terminal sin TTY** (CI, pipe, `descenso simulate | tee`). → Detectar `sys.stdout.isatty()`; si no es TTY, comportarse como `--no-interactive` (todo al azar salvo `--fix`) y barra de progreso simple/silenciosa.
- **[B] Terminal estrecha (< 60 columnas)** — la tabla de `compare` no cabe. → Layout que se adapta al ancho (Rich lo hace); si es muy estrecha, formato lista en vez de tabla.
- **[P] Terminal sin soporte de color/UTF-8** (algunos SSH viejos). → Rich degrada solo; el ranking final es ASCII puro de todos modos.
- **[B] El usuario hace Ctrl-C a mitad de simulación.** → Salir limpio (no dejar un parquet a medias); mensaje "cancelado".
- **[B] `--copy` (portapapeles) sin entorno gráfico / sin `xclip`/`wl-copy`.** → No fallar la ejecución: imprimir el texto igualmente y avisar "no pude copiar al portapapeles, cópialo a mano".
- **[B] `descenso report` sin ninguna simulación previa.** → Correr una simulación con los defaults automáticamente (avisando) en vez de error.
- **[B] `data/cache/` no existe o sin permisos de escritura.** → Crear el directorio; si no se puede, error claro con la ruta.
- **[P] Dos `descenso simulate` a la vez escribiendo el mismo parquet.** → Nombre de fichero con timestamp+pid; no se pisan.
- **[P] Locale del sistema con coma decimal vs punto** al imprimir `[99,87%]`. → Formateo manual con coma (es el formato del tweet español), independiente del locale.

## 6. Scraping puntual de X (CP0, no producción)

- **[B0] snscrape roto / X bloquea** (lo habitual desde 2023). → El script lo intenta, captura el fallo, y cae a: "pega los replies en `data/replies.txt` y vuelve a ejecutar". No es un error del proyecto, es lo esperado.
- **[P] Replies con emojis/menciones/links** al analizar factores. → Normalizar texto; contar menciones de palabras clave ("forma", "racha", "entrenador", "lesion", "xG", "calendario"...). Es un análisis cualitativo, no necesita NLP fino.
- **[P] Muy pocos replies recogidos.** → Documentar la muestra ("n=23 replies de 2 tweets") sin sobreinterpretar.

## 7. Seguridad / robustez general

- **[B] YAML/CSV malformado en cualquier fichero de `data/`.** → Errores de parseo capturados con el nombre del fichero y la línea; no stacktrace crudo.
- **[B] Inyección vía nombre de fichero / argumento** (`--fix` con caracteres raros). → Solo se parsea con un regex estricto `^(.+?)\s+(\d+)-(\d+)\s+(.+?)$` y luego fuzzy-match contra una lista cerrada de equipos; nada se evalúa ni se mete en shell.
- **[P] Cache parquet corrupto** (interrumpido a media escritura). → Escribir a `*.tmp` y `os.replace` atómico; al leer, si falla, borrar y re-descargar.
- **[B] Ningún secreto en el repo** (es público): no hay API keys; si en v2 se añade publicación a X, las credenciales van por variable de entorno y `.env` está en `.gitignore`.
