# Contribuir a `probabilidad-descenso`

Gracias por querer aportar. Este proyecto nace de una conversación abierta y la idea es que cualquiera pueda mejorarlo.

## Cómo empezar

1. Abre un **issue** describiendo lo que quieres cambiar (bug, dato, factor nuevo del modelo, refinamiento). Para cambios grandes, mejor discutirlo antes de escribir código.
2. Haz un fork, crea una rama, y abre un **pull request** contra `main`.
3. Antes de abrir el PR, asegúrate de que pasa todo en local:
   ```bash
   pip install -e ".[dev]"
   ruff check src tests
   black --check src tests
   mypy src tests
   pytest --cov
   ```
   El CI ejecuta exactamente eso; un PR no se mergea si está en rojo.

## Tipos de contribución

### Datos (`data/`)
- **`data/coach_changes.yaml`** — cambios de entrenador y bajas de la temporada en curso. Cada entrada debe incluir una fecha y una nota con la fuente o el motivo. **Nada inventado**: si no hay una fecha pública de cese, no entra.
- **`data/team_aliases.yaml`** — corrección de los nombres de equipo entre clubelo / Understat / FBref. Si una fuente cambia una grafía, este es el sitio.

### Modelo (`src/descenso/domain/`)
- Cualquier cambio en el modelo de fuerza, en el modelo de partido o en los desempates debe venir con:
  - tests nuevos o actualizados que lo cubran,
  - y, si afecta a las predicciones, el resultado de `descenso backtest` **antes y después** del cambio (Brier / log-loss). Un cambio que empeora el backtest sin una buena razón no se mergea.
- Mantén el dominio **puro** (sin IO, sin red): eso es lo que lo hace testeable y backtesteable.

### Adapters (`src/descenso/adapters/`)
- Si una fuente externa cambia su HTML/formato y rompe un parser, un PR que lo arregle es muy bienvenido. Los errores deben ser **explícitos** (qué URL, qué se esperaba), nunca un stacktrace crudo.

## Estilo

- Código y comentarios en español (es el idioma del proyecto y de su comunidad). Los nombres de símbolos pueden estar en inglés si encaja mejor.
- `ruff` + `black` mandan sobre el formato; no discutas con el formateador.
- Tipos: `mypy --strict`. Anótalo todo.
- Sin emojis en el código ni en la salida de la CLI (usa texto / box-drawing).

## Licencia

Al contribuir aceptas que tu aportación se publique bajo la licencia MIT del proyecto.
