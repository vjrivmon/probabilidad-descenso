"""Caso de uso (uso único, CP0): recopilar los replies a @LaLigaenDirecto y resumir
qué factores pide la afición. NO es un componente de producción.

Estrategia: intentar leer los replies automáticamente; si falla (lo habitual con
X desde 2023), pedir al usuario que los pegue en `data/replies.txt`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

KEYWORDS = {
    "forma": ["forma", "racha", "momento", "tendencia", "estado de animo", "estado de ánimo"],
    "entrenador": ["entrenador", "míster", "mister", "cambio de banquillo", "destitu"],
    "lesiones": ["lesion", "lesión", "baja", "bajas", "sancionad"],
    "xg": ["xg", "goles esperados", "merecid"],
    "calendario": ["calendario", "rival", "dificultad", "fixture"],
    "moral": ["moral", "presion", "presión", "animo", "ánimo", "ambiente"],
}


def summarize_factors(replies_path: Path = Path("data/replies.txt")) -> Counter[str]:
    """Cuenta menciones de cada categoría de factor en los replies. Análisis cualitativo simple."""
    raise NotImplementedError  # CP0
