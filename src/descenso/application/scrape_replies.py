"""Caso de uso (uso único, CP0): resumir qué factores pide la afición en los replies
a @LaLigaenDirecto. NO es un componente de producción.

El fichero `data/replies.txt` se genera con `scripts/scrape_x_browser.py` (que toma
el control de un Chrome ya logueado vía CDP) o, si eso falla, pegando los replies a
mano. `summarize_factors` hace un conteo cualitativo simple por categoría de factor;
`scripts/scrape_replies.py` lo usa para producir `docs/community-factors.md`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

# Categoría -> palabras clave (en minúsculas, sin acentos no, tal cual; el matching
# normaliza el texto). El orden refleja, a grosso modo, lo que más aparece en los
# replies recogidos en mayo de 2026 — ver docs/community-factors.md.
KEYWORDS: dict[str, list[str]] = {
    "calendario / dificultad del run-in": [
        "calendario",
        "le queda",
        "le quedan",
        "lo que le queda",
        "rivales que",
        "partidos que quedan",
        "run-in",
        "fixture",
        "paseo",
    ],
    "explicabilidad (cómo funciona / qué tiene en cuenta)": [
        "como funciona",
        "cómo funciona",
        "que tiene en cuenta",
        "qué tiene en cuenta",
        "no tiene en cuenta",
        "no cuenta con",
        "como calculas",
        "cómo calculas",
        "como sacas",
        "cómo sacas",
        "explica",
        "no entiendo",
        "me explota",
    ],
    "frecuencia de actualización": [
        "actualiza",
        "actualizalo",
        "actualízalo",
        "porcentajes ya",
        "nuevos porcentajes",
        "tras el partido",
        "cuando juegue",
    ],
    "xg / merecimiento / suerte": [
        "xg",
        "goles esperados",
        "expected goals",
        "merec",
        "regalad",
        "le regalaron",
        "de churro",
        "rebote",
        "tuvo suerte",
    ],
    "forma / racha / momento": [
        "racha",
        "en forma",
        "momento de forma",
        "en racha",
        "tendencia",
        "viene de ganar",
        "viene de perder",
        "en caida",
        "en caída",
        "horas bajas",
        "dinamica",
        "dinámica",
    ],
    "cambio de entrenador": [
        "entrenador",
        "mister",
        "míster",
        "destitu",
        "cesa",
        "banquillo",
        "nuevo tecnico",
        "nuevo técnico",
        "cambio en el banquillo",
    ],
    "lesiones / bajas / sanciones": [
        "lesion",
        "lesión",
        "lesionad",
        "baja por",
        "bajas importantes",
        "sancionad",
        "enfermeria",
        "enfermería",
        "sin su",
    ],
    "moral / ánimo / presión / afición": [
        "moral",
        "animo",
        "ánimo",
        "autoestima",
        "confianza",
        "presion",
        "presión",
        "ambiente",
        "nervios",
    ],
    "mercado / fichajes / refuerzos": [
        "fichaje",
        "fichar",
        "mercado de invierno",
        "refuerzo",
        "se reforzo",
        "se reforzó",
    ],
    "objetivos / motivación (ya salvado, sin nada en juego)": [
        "no se juega nada",
        "sin nada en juego",
        "ya salvad",
        "ya descendid",
        "se relaja",
        "se la juega",
        "necesita ganar",
    ],
}

# Marcador del primer bloque "de la afición" que escribe el scraper. Todo lo que
# viene después (replies dirigidos a Fran + tweets que lo mencionan) cuenta; el
# bloque previo "## TWEETS DE @..." (los tweets del propio Fran) se descarta.
_COMMUNITY_MARKERS = ("## REPLIES", "## TWEETS que mencionan", "## TWEETS QUE MENCIONAN")


def _replies_text(raw: str) -> str:
    """Devuelve solo la parte "de la afición" del fichero (ignora los tweets propios de Fran).

    Si el fichero no trae las cabeceras del scraper (p.ej. replies pegados a mano),
    se devuelve entero.
    """
    positions = [raw.find(m) for m in _COMMUNITY_MARKERS]
    positions = [p for p in positions if p >= 0]
    return raw[min(positions) :] if positions else raw


def _normalize(text: str) -> str:
    return text.lower()


def summarize_factors(replies_path: Path = Path("data/replies.txt")) -> Counter[str]:
    """Cuenta menciones de cada categoría de factor en los replies (análisis cualitativo simple).

    Devuelve un `Counter` `{categoría: nº de coincidencias de palabra clave}`, que se
    interpreta como una *señal de demanda* (no una métrica exacta: hay falsos
    positivos/negativos; es un punto de partida para `docs/community-factors.md`).

    Lanza `FileNotFoundError` si el fichero no existe (hay que generarlo primero con
    `scripts/scrape_x_browser.py` o pegando los replies a mano).
    """
    raw = replies_path.read_text(encoding="utf-8")
    text = _normalize(_replies_text(raw))
    counts: Counter[str] = Counter()
    for category, words in KEYWORDS.items():
        counts[category] = sum(text.count(_normalize(w)) for w in words)
    return counts
