# Propuesta de valor — "descenso"

# Propuesta de valor — `descenso`

## El problema latente

Fran Martínez (@LaLigaenDirecto) publica jornada a jornada la probabilidad de descenso de los candidatos. Su herramienta (screenshot 2026-05-10) es un **script Python interactivo en terminal** que: pide los goles de cada partido pendiente (Enter = azar), "carga datos ELO", y lanza **100.000 simulaciones de alta variabilidad** Monte Carlo. Herramientas equivalentes públicas: eldescenso.com, asegunda.com (Monte Carlo + Poisson + Dixon-Coles).

El reproche recurrente de la comunidad (adrirbb, VisiLUD y otros en los replies): **los porcentajes oscilan a cada instante y no capturan factores determinantes**. La causa raíz es que la "fuerza" de cada equipo en el modelo se deriva esencialmente de la **clasificación actual / Elo de base** (clubelo, que se mueve lento), tratada como *memoryless*: cada resultado mueve la tabla y por tanto el output, pero el modelo no "recuerda" ni pondera **cómo** ha jugado un equipo en los últimos meses.

## Lo que falta (validado con el usuario, 2026-05-10)

1. **Forma reciente con decaimiento temporal** — que pese más cómo se juega desde hace ~3 meses que desde la jornada 1. Cada equipo evoluciona.
2. **Métricas avanzadas xG/xGA** — rendimiento *merecido*, no solo el resultado. Detecta equipos sobrevalorados/infravalorados por la tabla.
3. **Fuerza dinámica tipo Elo/SPI ajustada por forma** — sustituir "puntos en la tabla" por un rating que se actualiza partido a partido y descuenta lo viejo.
4. **Eventos discretos**: cambios de entrenador (efecto rebote), bajas/lesiones clave.
5. **"Estado de ánimo"** — versión rigurosa: combinación de 1-4. Versión experimental: sentimiento NLP de tweets/prensa (best-effort, no crítico).

## Qué aporta esta solución

Un **modelo de probabilidad de descenso con memoria de forma**: en lugar de simular sobre la foto fija de la tabla + Elo lento, simula sobre una **fuerza efectiva por equipo** = Elo base ajustado por (a) forma reciente ponderada exponencialmente, (b) diferencial xG−goles (suerte), (c) bumps manuales por cambio de entrenador / bajas. Salida en **formato terminal idéntico al de Fran** (ranking `[XX,XX%] Equipo`) para que sea directamente adoptable, más un modo comparativo (modelo puro vs. ajustado) que hace visible *por qué* difieren.

El scraping de @LaLigaenDirecto es **investigación de requisitos puntual** (una sola vez): extraer los replies para confirmar qué factores pide la afición. No es un componente de producción continuo.

## Decisiones de alcance (usuario, 2026-05-10)

- Destinatario: herramienta para que Fran pudiera adoptarla (aunque no la haya pedido). Trabaja en terminal → **Python CLI** (`.py`).
- Datos: **solo fuentes gratuitas** (clubelo.com API, Understat, FBref, scraping de calendario).
- X/Twitter: acceso **de una sola vez** (sin API de producción).
- Factores prioritarios elegidos: xG/xGA, Elo dinámico, peso temporal a los últimos ~3 meses, cambios de entrenador.

[Source: User, 2026-05-10]
