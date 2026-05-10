#!/usr/bin/env python3
"""Script de UN SOLO USO (checkpoint 0): recopilar los replies a @LaLigaenDirecto
y resumir qué factores echa de menos la afición. NO es parte del producto.

Uso:
    python scripts/scrape_replies.py   # intenta scrapear; si falla pide data/replies.txt
    python scripts/scrape_replies.py --file data/replies.txt

Notas:
- El scraping de X está roto la mayor parte del tiempo desde 2023. Lo esperado es
  pegar los replies a mano en data/replies.txt (un reply por línea o por bloque).
- Salida: imprime el conteo de menciones por categoría de factor y propone el
  contenido para docs/community-factors.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permite ejecutar el script sin instalar el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from descenso.application.scrape_replies import summarize_factors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resumen de factores pedidos en los replies de @LaLigaenDirecto"
    )
    parser.add_argument(
        "--file", type=Path, default=Path("data/replies.txt"), help="fichero con los replies"
    )
    args = parser.parse_args()

    counts = summarize_factors(args.file)  # noqa: F841  (se usará al implementar CP0)
    raise NotImplementedError(
        "CP0: pendiente de implementar el resumen y la escritura de docs/community-factors.md"
    )


if __name__ == "__main__":
    raise SystemExit(main())
