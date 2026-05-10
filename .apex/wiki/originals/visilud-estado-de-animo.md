# Idea original — alimentar el modelo con el "estado de ánimo" de cada equipo

# Idea original del usuario

> "Quiero que se haga un sistema que sea capaz de recopilar las tendencias de todos los equipos involucrados, con opiniones empíricas y con datos reales y verificables. (...) Falta justo ese factor, que al modelo de predicción se pueda alimentar por el estado de ánimo y que no SOLO se base en probabilidades puras y duras. (...) Influyen cosas como cambios de entrenadores, que tenga más peso el cómo se juega desde hace 3 meses y no desde principio de temporada, cada equipo evoluciona y no tener en cuenta estos datos me parece un error."

[Source: User (VisiLUD / @PerSempreLUD), 2026-05-10]

## Interpretación operativa

"Estado de ánimo" = momentum / forma efectiva, cuantificable como: forma reciente con decaimiento temporal (ventana ~3 meses) + diferencial xG vs goles (rendimiento merecido) + ajustes por eventos discretos (cambio de entrenador, bajas clave). Es lo que distingue este proyecto del modelo memoryless de @LaLigaenDirecto.
