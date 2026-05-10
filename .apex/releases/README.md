# Releases

Pipeline de entrega del proyecto:

- `drafts/` — feature branches / WIP, todo lo que aún no ha llegado a
  staging. Cada subdirectorio es una feature: `drafts/<feature-name>/`.
- `staging/` — código en pre-producción, esperando aprobación final.
  `staging/<version>/` con changelog parcial.
- `published/` — releases en producción. Cada release es
  `published/<version>/` con:
  - `CHANGELOG.md`
  - `rollback-plan.md`
  - `deploy-notes.md`

La skill `portfolio-publisher/SKILL.md` puede consumir `published/*` para
generar las entradas del portfolio automáticamente.
