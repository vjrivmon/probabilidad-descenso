# Análisis de sensibilidad del modelo ajustado (CP2)

Este documento mide qué efecto tienen los parámetros del modelo "con memoria de
forma" sobre la calidad de las predicciones, medida por **Brier score** y
**log-loss** en el backtest histórico (`descenso backtest`).

> Nota honesta: ahora mismo el componente de **xG** (la corrección de "suerte"
> con los goles esperados de Understat) **no entra** en estos números, porque
> understat.com ha dejado de servir a clientes no-navegador el bloque de datos
> embebido (igual que FBref tras Cloudflare). El modelo degrada automáticamente
> a "solo goles reales" (`xg_blend_beta` deja de actuar). Lo que mide este
> análisis es, por tanto, el aporte de la **forma reciente vs. el Elo de
> clubelo** y del **decaimiento temporal**, sin la parte de xG. El objetivo de
> mejora ≥5% del SPEC está pensado para el modelo completo (con xG); sin xG la
> mejora es real pero más modesta — ver la tabla.

## Metodología

- Backtest sobre las temporadas **2022-23 y 2023-24** (las que openfootball
  tiene completas; 2024-25 está incompleta y se salta automáticamente).
- Horizonte: se predice la zona de descenso **a 8 jornadas del final** (estado
  *as-of* la jornada 30, sin data leakage: solo partidos con fecha ≤ esa
  jornada y el Elo de clubelo de esa fecha).
- 8.000 simulaciones Monte Carlo por predicción, `seed` fija.
- "Puro" = `alpha = 1.0`, sin deltas de entrenador/bajas (≡ el modelo del CP1,
  ≈ el de @LaLigaenDirecto). "Ajustado" = el modelo con memoria de forma.
- `mejora%` = `(Brier_puro − Brier_ajustado) / Brier_puro · 100` (positivo = el
  ajustado predice mejor).

Reproducir: `descenso backtest --seasons 2022,2023 --horizon 8 --sims 8000`
(con los parámetros de `config.yaml`), o el barrido completo con un script que
varíe `model.alpha`, `model.form_half_life_days` y `model.form_k_factor` y llame
a `descenso.application.backtest.run_backtest`.

## Resultados

### Variando `alpha` (peso Elo vs. forma), con `half_life = 75 d`, `K = 20`

| alpha | Brier puro | Brier ajustado | mejora% | log-loss puro | log-loss aj. |
|------:|-----------:|---------------:|--------:|--------------:|-------------:|
| 1.00  | 0.0659     | 0.0659         | +0.00%  | 0.1984        | 0.1984       |
| 0.70  | 0.0659     | 0.0663         | −0.60%  | 0.1984        | 0.1995       |
| 0.50  | 0.0659     | 0.0658         | +0.07%  | 0.1984        | 0.1969       |
| 0.30  | 0.0659     | 0.0658         | +0.14%  | 0.1984        | 0.1961       |
| 0.10  | 0.0659     | 0.0657         | +0.18%  | 0.1984        | 0.1968       |

`alpha = 1.0` reproduce exactamente el modelo puro (control de sanidad). Con
`K = 20` (el valor inicial) el efecto de la forma es casi nulo: el factor K era
demasiado conservador.

### Variando `half_life` y `K`, con `alpha = 0.5`

| half_life (d) | K  | Brier puro | Brier ajustado | mejora% | log-loss puro | log-loss aj. |
|--------------:|---:|-----------:|---------------:|--------:|--------------:|-------------:|
| 30            | 20 | 0.0659     | 0.0656         | +0.43%  | 0.1984        | 0.1954       |
| 30            | 40 | 0.0659     | 0.0650         | +1.24%  | 0.1984        | 0.1930       |
| 30            | 80 | 0.0659     | 0.0648         | +1.58%  | 0.1984        | 0.1906       |
| 75            | 20 | 0.0659     | 0.0658         | +0.07%  | 0.1984        | 0.1969       |
| **75**        | **40** | **0.0659** | **0.0654** | **+0.65%** | **0.1984** | **0.1952** |
| 75            | 80 | 0.0659     | 0.0649         | +1.40%  | 0.1984        | 0.1916       |
| 150           | 20 | 0.0659     | 0.0658         | +0.06%  | 0.1984        | 0.1971       |
| 150           | 40 | 0.0659     | 0.0650         | +1.37%  | 0.1984        | 0.1924       |
| 150           | 80 | 0.0659     | 0.0654         | +0.76%  | 0.1984        | 0.1935       |

## Conclusiones y elección de defaults

1. **El factor K importa más que `alpha` o `half_life`.** Con `K = 20` casi no
   se nota la forma; con `K ≥ 40` aparece una mejora consistente (y mayor en
   log-loss que en Brier — la forma ayuda sobre todo a no estar *muy* seguro de
   un descenso/salvación que luego no pasa).
2. **El óptimo del barrido** es `alpha = 0.5`, `half_life = 30`, `K = 80`
   (+1.58% Brier, ~4% log-loss), pero es solo el óptimo *sobre 2 temporadas* —
   con tan poca muestra, un `half_life` de 30 días y `K = 80` corren riesgo de
   sobreajuste (mucho peso a las últimas 4-5 jornadas).
3. **Defaults elegidos en `config.yaml`**: `alpha = 0.5`, `half_life = 75 d`,
   `form_k_factor = 40.0`. Es un punto medido: net-positivo (+0.65% Brier,
   +1.6% log-loss) sin tirar todo el peso a la forma reciente. Quien quiera
   exprimir el backtest puede subir `form_k_factor` a 60-80 y/o bajar
   `form_half_life_days` a 30-50, asumiendo el riesgo.
4. **No se alcanza el +5% del SPEC** con estos datos. Es esperable sin la
   corrección por xG (que descuenta la suerte partido a partido). Cuando
   Understat (o una fuente equivalente de xG) vuelva a ser accesible, el modelo
   lo incorpora solo (`xg_blend_beta`) y este análisis debería repetirse.

## Autocalibración (`descenso calibrate`, CP3)

`descenso calibrate --seasons 2022,2023 --horizon 8` busca los `alpha`,
`form_half_life_days` y `form_k_factor` que minimizan el Brier medio del modelo
ajustado en el backtest, con `scipy.optimize.minimize` (Nelder-Mead con bounds, en
coordenadas normalizadas) y una **seed fija** para que el objetivo sea
determinista. El estado as-of de cada temporada se prepara una sola vez
(`PreparedSeason`) y se reutiliza en cada evaluación, así que cada paso del
optimizador es solo una pasada Monte Carlo por temporada.

Devuelve los parámetros óptimos, las métricas antes/después (puro / config /
calibrado) y un fragmento de YAML listo para pegar en `config.yaml` — **no** lo
escribe por ti. Aviso: con solo 2-3 temporadas completas en openfootball el óptimo
del backtest puede estar sobreajustado (tiende a `half_life` corto y `K` alto, que
dan mucho peso a las últimas jornadas); trátalo como punto de partida, no como la
verdad. Si la calibración no encuentra nada mejor que el `config.yaml` actual,
devuelve los parámetros de config sin cambios.

## Modelo de marcador Dixon-Coles (CP3)

El barrido de arriba usa el modelo de marcador del CP1 (`elo_logistic`: W/D/L
logístico + margen muestreado). Con `model.match_model: dixon_coles` los goles de
cada equipo se muestrean de dos Poisson independientes con la corrección de
Dixon-Coles (`goals_avg`, `elo_to_goals_scale`, `dixon_coles_rho`) — marcadores
más realistas y mejor fidelidad al desempate por diferencia de goles. El efecto
sobre P(descenso) suele ser pequeño (las posiciones dependen sobre todo del W/D/L,
que ambos modelos reproducen de forma comparable); este modelo es más "suave" que
el logístico: no llega a probabilidades tan extremas para diferencias de Elo
moderadas. Repetir el barrido con `dixon_coles` queda pendiente.

## Estabilidad (varianza jornada-a-jornada)

El SPEC pide también que la P(descenso) del modelo ajustado "baile" menos entre
jornadas que la del puro. Medirlo requiere correr el backtest jornada a jornada
en el tramo final y comparar la varianza de la serie por equipo — pendiente de
automatizar (`descenso backtest` hoy agrega sobre un solo horizonte). El efecto
esperado: como `R_eff` mete el Elo de clubelo (que se mueve poco partido a
partido) más una media ponderada de forma (también suave), la entrada del
simulador es más estable que un Elo puro que reacciona a saltos a cada resultado
sorpresa.
