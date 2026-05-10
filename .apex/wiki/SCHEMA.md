# Wiki Schema — descenso

## Convenciones

### Páginas
- Cada página es un archivo `.md` en su directorio correspondiente.
- Frontmatter YAML obligatorio: `title`, `created`, `updated`, `type`, `tags`.
- Mínimo 2 outbound `[[wikilinks]]` por página (excepto raw/).
- Tags deben pertenecer a la taxonomía definida abajo.

### Taxonomía de tags
- `domain`: Conceptos del dominio del proyecto
- `architecture`: Decisiones arquitectónicas
- `error`: Errores conocidos y lecciones
- `pattern`: Patrones reutilizables
- `decision`: Decisiones tomadas
- `data`: Fuentes de datos y esquemas
- `security`: Consideraciones de seguridad
- `performance`: Métricas y optimizaciones
- `design-inspiration`: Referencias visuales (de `skills/design-research`)
- `synthesis`: Páginas generadas por `lib/synthesis.py`
- `fútbol / analítica deportiva / predicción LaLiga`: Específico del dominio

### Tipos de página
| Tipo | Directorio | Descripción |
|------|-----------|-------------|
| entity | entities/ | Producto, servicio, componente concreto |
| concept | concepts/ | Idea abstracta, patrón, principio |
| comparison | comparisons/ | Análisis comparativo (A vs B) |
| query | queries/ | Pregunta frecuente con respuesta compilada |
| raw | raw/ | Fuente inmutable (no editar) |
| synthesis | synthesis/ | Resumen auto-generado por dreaming |

### Relación con el segundo cerebro

Fuera de `wiki/` hay tres árboles complementarios:

- `.apex/brand/` — identidad visual y estrategia (Thomas escribe, agente lee)
- `.apex/raw/` — fuentes brutas pre-síntesis (research, socratic, papers)
- `.apex/releases/` — pipeline de entrega (drafts → staging → published)

El pipeline `lib/ingest.py` lee `.apex/raw/` y promueve señales a
`wiki/entities/` o `wiki/concepts/`. El synthesizer `lib/synthesis.py`
escribe en `wiki/synthesis/` cuando la densidad crece.

### Contradicciones
Si dos páginas se contradicen, documentar en frontmatter:
```yaml
contradicts: [[otra-página]]
resolution: "Pendiente" | "Resuelto: se eligió X porque Y"
```

### Tamaño
- Mínimo: 100 palabras
- Máximo: 2000 palabras (si excede, dividir en sub-páginas)
