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
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class CoachChangesFile:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(
        self,
    ) -> tuple[dict[str, list[tuple[dt.date, float | None]]], dict[str, float]]:
        """Devuelve (cambios_por_equipo, ajustes_bajas_por_equipo).

        `cambios_por_equipo[team_id]` es una lista de `(fecha, elo_bump_o_None)`
        ordenada por fecha, con solo las entradas con fecha <= hoy.

        `ajustes_bajas_por_equipo[team_id]` es el `elo_delta` de la entrada de
        bajas más reciente con `as_of <= hoy` (si hay varias gana la más reciente;
        no se suman).

        Ignora con warning las entradas con fecha futura o malformadas. Si el
        fichero no existe, devuelve estructuras vacías (el modelo funciona sin
        estos ajustes). Si el YAML está sintácticamente roto, lanza ValueError
        con el nombre del fichero.
        """
        if not self.path.exists():
            return {}, {}

        try:
            with self.path.open("r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ValueError(
                f"{self.path}: el fichero de cambios de entrenador no es un YAML válido: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise ValueError(
                f"{self.path}: se esperaba un dict en el YAML, se recibió " f"{type(raw).__name__}"
            )

        today = dt.date.today()

        # --- coach_changes ---
        cambios: dict[str, list[tuple[dt.date, float | None]]] = {}
        for i, entry in enumerate(_iter_list(raw, "coach_changes", self.path)):
            if not isinstance(entry, dict):
                logger.warning(
                    "%s: entrada #%d de coach_changes no es un dict, la ignoro: %r",
                    self.path,
                    i,
                    entry,
                )
                continue

            team_id = _safe_str(entry.get("team"), "team en entrada #%d de coach_changes", i)
            if team_id is None:
                continue

            fecha = _safe_date(
                entry.get("date"),
                f"{self.path}: entrada #{i} de coach_changes (team={team_id})",
            )
            if fecha is None:
                continue

            if fecha > today:
                logger.warning(
                    "%s: entrada #%d de coach_changes (team=%s, date=%s) tiene fecha futura, "
                    "la ignoro",
                    self.path,
                    i,
                    team_id,
                    fecha,
                )
                continue

            raw_bump = entry.get("elo_bump")
            elo_bump: float | None = None
            if raw_bump is not None:
                try:
                    elo_bump = float(raw_bump)
                except (TypeError, ValueError):
                    logger.warning(
                        "%s: entrada #%d de coach_changes (team=%s): elo_bump=%r no es "
                        "un número, uso el valor por defecto de config",
                        self.path,
                        i,
                        team_id,
                        raw_bump,
                    )

            cambios.setdefault(team_id, []).append((fecha, elo_bump))

        # Ordenar por fecha (ascendente) — el caller recibe la lista completa y
        # decide cuál aplica (normalmente el último)
        for team_id in cambios:
            cambios[team_id].sort(key=lambda x: x[0])

        # --- injuries ---
        ajustes_raw: dict[str, list[tuple[dt.date, float]]] = {}
        for i, entry in enumerate(_iter_list(raw, "injuries", self.path)):
            if not isinstance(entry, dict):
                logger.warning(
                    "%s: entrada #%d de injuries no es un dict, la ignoro: %r",
                    self.path,
                    i,
                    entry,
                )
                continue

            team_id = _safe_str(entry.get("team"), "team en entrada #%d de injuries", i)
            if team_id is None:
                continue

            fecha = _safe_date(
                entry.get("as_of"),
                f"{self.path}: entrada #{i} de injuries (team={team_id}, campo as_of)",
            )
            if fecha is None:
                continue

            if fecha > today:
                logger.warning(
                    "%s: entrada #%d de injuries (team=%s, as_of=%s) tiene fecha futura, "
                    "la ignoro",
                    self.path,
                    i,
                    team_id,
                    fecha,
                )
                continue

            raw_delta = entry.get("elo_delta")
            try:
                elo_delta = float(raw_delta)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                logger.warning(
                    "%s: entrada #%d de injuries (team=%s): elo_delta=%r no es un número, "
                    "la ignoro",
                    self.path,
                    i,
                    team_id,
                    raw_delta,
                )
                continue

            ajustes_raw.setdefault(team_id, []).append((fecha, elo_delta))

        # La entrada más reciente con as_of <= hoy gana (no se suman)
        ajustes: dict[str, float] = {}
        for team_id, lista in ajustes_raw.items():
            mas_reciente = max(lista, key=lambda x: x[0])
            ajustes[team_id] = mas_reciente[1]

        return cambios, ajustes


# --------------------------------------------------------------------------- #
# helpers privados
# --------------------------------------------------------------------------- #


def _iter_list(raw: dict[str, object], key: str, path: Path) -> list[object]:
    """Devuelve `raw[key]` como lista, o [] si no existe / es None."""
    val = raw.get(key)
    if val is None:
        return []
    if not isinstance(val, list):
        logger.warning(
            "%s: se esperaba una lista en `%s`, se encontró %s — lo ignoro",
            path,
            key,
            type(val).__name__,
        )
        return []
    return val


def _safe_str(value: object, context: str, idx: int) -> str | None:
    """Convierte value a str no vacío, o devuelve None tras un warning."""
    if not value or not str(value).strip():
        logger.warning(
            "%s: `team` vacío o ausente, ignoro la entrada",
            context % idx,
        )
        return None
    return str(value).strip()


def _safe_date(value: object, context: str) -> dt.date | None:
    """Parsea value como fecha ISO, o devuelve None tras un warning."""
    if value is None:
        logger.warning("%s: campo de fecha ausente, ignoro la entrada", context)
        return None
    # PyYAML puede parsear fechas automáticamente a datetime.date
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        logger.warning(
            "%s: fecha %r no está en formato ISO (YYYY-MM-DD), ignoro la entrada",
            context,
            value,
        )
        return None
