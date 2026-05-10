# @LaLigaenDirecto (Fran Martínez) — modelo de referencia

# @LaLigaenDirecto — Fran Martínez

Cuenta de X que publica jornada a jornada la probabilidad de descenso a 2ª de los candidatos de LaLiga (también probabilidades de Europa). Formato del tweet:

```
🚨 Probabilidad de descenso a 2ª División (actualizado tras el Mallorca 1-1 Villarreal):
[99,87%] Oviedo
[71,51%] Levante
[53,28%] Alavés
...
```

## Su herramienta (screenshot del usuario, 2026-05-10)

Script **Python interactivo en terminal**:
1. Para cada partido pendiente pide `Goles <equipo> (Enter para azar):` — permite fijar resultados o dejarlos al azar.
2. `Cargando datos ELO...` — usa ratings Elo (probablemente clubelo.com).
3. `Iniciando 100000 simulaciones de alta variabilidad` — Monte Carlo, 100k iteraciones.
4. Barra de progreso `Simulando: X%`.

## Crítica de la comunidad (replies)

- **adrirbb (@adrics4ever)**: lleva 3 jornadas cambiando los porcentajes a cada instante; no tiene en cuenta factores determinantes pese a las miles de simulaciones.
- **Fran**: "los porcentajes cambian a cada instante 🥲 ... es una modelización de la situación, no una bola de cristal".
- **VisiLUD (@PerSempreLUD)** (el usuario de este proyecto, Vicente): propone un sistema que recopile tendencias de todos los equipos involucrados, con datos reales y verificables, y que alimente el modelo con el "estado de ánimo" / modo de juego de cada equipo, no solo probabilidades puras.

## Equivalentes públicos

- **eldescenso.com** — miniliga del descenso 25/26, 10.000 sims Monte Carlo por escenario, what-if, mapa de impacto.
- **asegunda.com** — Monte Carlo + Poisson + probabilidades en tiempo real.
