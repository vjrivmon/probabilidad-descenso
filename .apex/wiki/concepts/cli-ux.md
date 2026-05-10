# UX de terminal — descenso (mockups ASCII + flujos)

# UX de terminal — `descenso`

## Mapa de comandos (= "mapa de navegación")

```
descenso
├── data refresh        # descarga/actualiza Elo (clubelo), xG (Understat), calendario (FBref) → cache
├── data show           # qué datos hay en cache y de qué fecha
├── simulate            # interactivo: pide goles de cada partido pendiente (Enter = simular), corre N sims
│     --sims N (def 100000)  --fix "Levante 3-2 Osasuna" (repetible)  --no-interactive  --seed N
├── report              # imprime el ranking en formato tweet a partir de la última simulación (o corre una)
│     --copy            # copia al portapapeles  --top N
├── compare             # tabla puro vs ajustado + Δ + Brier del backtest
└── backtest            # corre el backtest histórico (2022-25), imprime Brier/log-loss puro vs ajustado
      --seasons 2022,2023,2024  --horizon 5
```

## Mockup — `descenso simulate`

```
$ descenso simulate --sims 100000

  descenso · LaLiga 2025-26 · jornada 33 · 6 jornadas restantes
  datos: Elo clubelo 2026-05-09 · xG Understat hasta J32 · forma half-life 75d · alpha 0.5

  Introduce resultados (Enter = simular ese partido):

  J33  Rayo Vallecano    vs  Girona             - : -
  J33  Atletico de Madrid vs Celta de Vigo       - : -
  J33  Levante           vs  Osasuna             3 : 2
  J34  ...                                       (Enter en blanco aqui = simular todo lo demas)

  fuerzas ajustadas por forma ... OK (20 equipos)
  simulando 100000 iteraciones (alta variabilidad)
  [##########################------] 81%   ~2s

  ----------------------------------------------------
  Probabilidad de descenso a 2a Division
  (tras Levante 3-2 Osasuna; resto simulado)

  [99,71%] Oviedo
  [68,40%] Levante
  [55,12%] Alaves
  [16,03%] Elche
  [13,88%] Girona
  [12,90%] Espanyol
  [10,44%] Sevilla
  [08,11%] Mallorca
  [05,77%] Valencia
  ----------------------------------------------------
  guardado: data/cache/sim_2026-05-10T1742.parquet  (usa 'descenso report --copy' para el tweet)
```

## Mockup — `descenso compare`

```
$ descenso compare

  Modelo PURO (solo Elo, sin memoria)   vs   AJUSTADO (Elo + forma + xG + entrenadores)

  Equipo              Puro     Ajustado    Δ        nota
  Oviedo              99,9 %   99,7 %      -0,2
  Levante             74,8 %   68,4 %      -6,4     racha buena: xG > goles ult. 6
  Alaves              48,1 %   55,1 %      +7,0     1 victoria en 8; forma a la baja
  Espanyol            22,1 %   14,8 %      -7,3     cambio de entrenador + repunte xG
  Sevilla             15,9 %   10,4 %      -5,5     mejor xGA desde marzo
  ...

  Backtest 2022-25 (prediccion a 5 jornadas del final):
    modelo puro       Brier 0.0791   log-loss 0.271
    modelo ajustado   Brier 0.0683   log-loss 0.238     -> mejora 13,7 %
```

## User flows

**Flujo principal (happy path):** `data refresh` → `simulate` (deja todo al azar o fija algún resultado) → ve el ranking → `report --copy` → pega el tweet.

**Flujo secundario (escenario what-if):** `simulate --fix "Levante 3-2 Osasuna" --fix "Oviedo 0-0 Getafe"` → ve cómo cambian las probabilidades con esos resultados forzados.

**Flujo de error:** `data refresh` falla porque Understat cambió el HTML / no hay internet → mensaje claro con el detalle del error y la URL que falló; usa el cache anterior si existe (`avisando de la fecha`) o aborta con instrucciones; nunca un "algo salió mal" genérico. Si faltan xG de un equipo recién ascendido → degradar a solo-Elo para ese equipo y avisarlo en el header.
