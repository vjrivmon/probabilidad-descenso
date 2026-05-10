# Factores que pide la afición — análisis de los replies de @LaLigaenDirecto (CP0)

> Resultado del **checkpoint 0** del proyecto: recopilar los tweets de
> [@LaLigaenDirecto](https://x.com/LaLigaenDirecto) y los replies/menciones dirigidos a
> él, y ver qué factores echa de menos la gente en su modelo de probabilidad de
> descenso. Esto **valida o ajusta** la lista de features del modelo (forma reciente,
> cambios de entrenador, bajas, xG…) y decide si la *feature experimental de
> sentimiento* del CP3 tiene demanda real.

## Metodología

- `data/replies.txt` se recopiló de x.com (timeline del perfil de @LaLigaenDirecto +
  búsqueda `to:LaLigaenDirecto` "latest" + búsqueda del handle con `descenso`/`modelo`/
  `probabilidad`), con un Chrome logueado controlado vía CDP — ver
  `scripts/scrape_x_browser.py`. No es un censo exhaustivo: es una muestra de los
  últimos cientos de tweets/replies.
- `scripts/scrape_replies.py` cuenta, sobre la **sección de replies/menciones** (los
  tweets del propio Fran se ignoran), cuántas veces aparece cada palabra clave de cada
  categoría de factor (`descenso.application.scrape_replies.KEYWORDS`). Es un conteo
  cualitativo grosero: hay falsos positivos y negativos; sirve como señal de demanda
  relativa, no como métrica exacta.


## Conteo de menciones

| Categoría | Menciones (proxy) |
|---|---:|
| calendario / dificultad del run-in | 31 |
| explicabilidad (cómo funciona / qué tiene en cuenta) | 26 |
| frecuencia de actualización | 24 |
| forma / racha / momento | 20 |
| cambio de entrenador | 14 |
| xg / merecimiento / suerte | 9 |
| moral / ánimo / presión / afición | 9 |
| mercado / fichajes / refuerzos | 4 |
| objetivos / motivación (ya salvado, sin nada en juego) | 4 |
| lesiones / bajas / sanciones | 1 |

## Lectura

1. **Lo que más se repite NO es "añade tal factor", sino una mezcla de
   percepción + explicabilidad:** la queja estrella es que los porcentajes "bailan"
   cada jornada y que el modelo "no tiene en cuenta el calendario" de un equipo
   ("con el calendario que tiene no puede tener un 5 %", "el del Alavés es un paseo").
   En realidad el modelo **sí** simula el calendario restante con las reglas de
   desempate — es un problema de comunicación, no una feature que falte. Mucha gente
   también pide directamente "explica cómo funciona" y "actualiza ya los porcentajes".
   → Acciones más rentables que cualquier factor nuevo: (a) `descenso compare` /
   `report --html` ya van en esa dirección (explican el porqué del cambio); (b)
   convendría una nota fija recordando que el calendario restante ya entra en la
   simulación; (c) las actualizaciones rápidas son cuestión de pipeline, no de modelo.

2. **xG / "merecimiento" / suerte** aparece de forma recurrente ("metió el que le
   regalaron", "no merecía ganar", "de churro"). Esto **respalda** el componente de
   xG del modelo (CP2: `xg_blend_beta`, descontar suerte partido a partido) — está
   implementado y a la espera de que Understat (u otra fuente) vuelva a ser accesible.

3. **Forma / racha / momento** aparece bastante (es de los términos más frecuentes),
   aunque por debajo de las quejas sobre calendario/explicabilidad/actualización y a
   menudo entremezclado con piques de afición. Da soporte —moderado— al componente de
   "memoria de forma" del modelo (CP2). Era más una idea de los autores que un clamor
   explícito, pero los replies no la contradicen.

4. **Cambio de entrenador, lesiones/bajas, mercado de invierno, motivación de
   equipos ya salvados/descendidos**: apariciones modestas (la mayoría de "entrenador"
   son comentarios de club, no peticiones "ten en cuenta el cambio de míster"). Soporte
   débil-medio; el cableado existe (`data/coach_changes.yaml`), pero no es prioritario.

5. **Sentimiento / ánimo / moral del vestuario**: demanda **escasa y poco
   específica**. Las menciones de "presión"/"nervios"/"ánimo" son, casi siempre, el
   aficionado nervioso por su equipo ("dame porcentajes que me tienes nervioso"), no
   una petición de modelar el estado anímico de la plantilla. El "estado de ánimo" que
   motivó la idea original lo cubren mejor los datos duros (Elo, forma reciente, xG). →
   Por la propia condición del SPEC ("la feature de sentimiento solo si el CP0 sugiere
   que aporta"), **el CP0 no respalda construir esa feature** como un factor del
   modelo. Si se hace, que sea estrictamente opt-in, etiquetada experimental y con esta
   nota explícita.

6. **Mucho ruido irrelevante:** buena parte de los replies son piques entre
   aficiones, quejas arbitrales y la lucha por Champions/Europa — nada que ver con
   factores del modelo de descenso. Es esperable en una cuenta grande.


---
_Generado por `scripts/scrape_replies.py` a partir de `data/replies.txt` el 2026-05-10._
