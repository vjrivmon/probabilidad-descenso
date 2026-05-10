# Análisis del problema — por qué oscilan los porcentajes

# Análisis del problema

## El síntoma

@LaLigaenDirecto publica P(descenso) jornada a jornada. Tres jornadas seguidas los % de varios equipos (Espanyol, Sevilla, Alavés, Elche, Girona...) bailan de forma que a la afición le parece arbitraria. Fran responde, con razón, que "los porcentajes cambian a cada instante" porque es una *modelización de la situación, no una bola de cristal*. Pero adrirbb insiste: con miles de simulaciones, el modelo *debería* capturar factores determinantes y no lo hace.

## La causa raíz

Un modelo Monte Carlo de descenso necesita dos cosas: (1) el **calendario restante** y (2) una **estimación de fuerza** de cada equipo para simular cada partido. El calendario es fijo; toda la varianza viene de (2). En el modelo de Fran (y en eldescenso.com / asegunda.com), la fuerza es esencialmente **función de la foto fija de hoy**: la clasificación actual y/o un Elo de base (clubelo) que se mueve despacio. Es un modelo **memoryless**:

- No distingue un equipo que lleva 8 partidos jugando bien y sumando de uno que sumó lo mismo con un calendario fácil y rendimiento pobre (xG en contra).
- No descuenta el rendimiento de hace 7 meses: el 0-0 de la jornada 3 pesa igual que el 4-0 de la semana pasada.
- No ve cambios de entrenador, bajas, ni rachas.

Resultado: cada resultado nuevo mueve la tabla → mueve la fuerza estimada → mueve los % de forma aparentemente desproporcionada, porque la fuerza estimada es **demasiado sensible al último resultado y demasiado insensible a la tendencia**. Es ruido, no señal.

## La solución

Reemplazar "fuerza = foto de hoy" por "fuerza = foto de hoy *con memoria ponderada de cómo se ha jugado*". Concretamente `R_i = α·Elo_base + (1−α)·FormRating_i + Δ_entrenador + Δ_bajas`, donde `FormRating` es un promedio de rendimientos por partido (resultado vs. calidad del rival, ajustado por xG−goles para descontar suerte) ponderado exponencialmente con half-life ≈ 75 días. Esto:

1. Estabiliza los % (un resultado aislado mueve poco si la tendencia no cambia).
2. Incorpora los factores que pide la comunidad, todos con **datos verificables** (clubelo, Understat, fechas públicas de cese de entrenadores).
3. Es **falsable**: se backtestea contra 2022-25 y se mide (Brier/log-loss) si predice mejor que el modelo puro. Si no mejora, se dice y se ajusta — eso *también* es valor frente a la crítica.

## Valor que no existe hoy

Ninguna de las herramientas públicas (eldescenso, asegunda, el propio @LaLigaenDirecto) incorpora memoria de forma + xG + eventos discretos *y* publica una validación histórica de que eso ayuda. Esa combinación —modelo interpretable + número de calibración defendible + salida en el formato exacto del tweet— es el hueco.
