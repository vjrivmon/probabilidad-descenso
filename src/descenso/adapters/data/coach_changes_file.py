"""Lee `data/coach_changes.yaml`: cambios de entrenador y ajustes por bajas.

Esta es la pieza "humana/verificable" del modelo, editable por los colaboradores.
Estructura del YAML:

    coach_changes:
      - team: real-oviedo
        date: 2026-02-15
        new_coach: "Nombre Apellido"
        elo_bump: 25        # opcional; si falta, se usa coach_bump_default de config
        notes: "..."
    injuries:
      - team: levante
        as_of: 2026-05-01
        elo_delta: -20
        notes: "baja del 9 titular"
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path


class CoachChangesFile:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> tuple[dict[str, list[tuple[dt.date, float | None]]], dict[str, float]]:
        """Devuelve (cambios_por_equipo, ajustes_bajas_por_equipo).

        Ignora (con warning) entradas con fecha futura o malformadas. Si el fichero
        no existe, devuelve estructuras vacías (el modelo funciona sin estos ajustes).
        """
        raise NotImplementedError  # Fase 7 (CP2)
