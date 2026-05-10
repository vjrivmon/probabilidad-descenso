#!/usr/bin/env python3
"""Script de UN SOLO USO (checkpoint 0): recopila tweets de @LaLigaenDirecto y los
replies/menciones dirigidos a él, tomando el control de un Chrome **ya logueado** vía
CDP (Chrome DevTools Protocol). NO es parte del producto y NO usa la API de X.

Por qué así: la API de X es de pago y limitada; pero un navegador real logueado puede
leer el timeline público de una cuenta sin problema. La idea (el "agente que opera tu
navegador") es justo esa.

Requisitos:
  1. `pip install playwright`  (solo el paquete Python; `connect_over_cdp` no necesita
     descargar navegadores con `playwright install`).
  2. Arrancar Chrome con depuración remota y un perfil dedicado (Chrome moderno se
     niega a abrir el puerto con el perfil por defecto):

        google-chrome-stable --remote-debugging-port=9222 \\
            --user-data-dir="$HOME/.config/chrome-x-debug"

     y, en esa ventana, hacer login en https://x.com.
  3. Comprobar: http://localhost:9222/json/version debe devolver un JSON con
     `webSocketDebuggerUrl`.

Uso:
    python scripts/scrape_x_browser.py [--account LaLigaenDirecto] [--port 9222]
        [--out data/replies.txt]

Luego `python scripts/scrape_replies.py` resume los factores en docs/community-factors.md.

Aviso: scrapear x.com estando logueado va contra sus Términos de Servicio; es tu
cuenta y tu riesgo. Hazlo con moderación (este script mete pausas y se detiene cuando
deja de aparecer contenido nuevo o detecta un error/limite).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_EXTRACT_JS = r"""
() => {
  const out = [];
  for (const art of document.querySelectorAll('article[data-testid="tweet"]')) {
    const txtEl = art.querySelector('div[data-testid="tweetText"]');
    const text = txtEl ? txtEl.innerText.trim() : "";
    let handle = "";
    for (const a of art.querySelectorAll('a[role="link"]')) {
      const href = a.getAttribute('href') || "";
      if (/^\/[A-Za-z0-9_]+$/.test(href) && a.querySelector('span')) {
        handle = href.slice(1);
        break;
      }
    }
    if (text) out.push({handle, text});
  }
  return out;
}
"""

_ERROR_HINTS = (
    "algo ha ido mal",
    "something went wrong",
    "intentar de nuevo",
    "try again",
    "rate limit",
)


def _scroll_collect(page, label: str, max_scrolls: int, pause: float = 1.6) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    order: list[dict[str, str]] = []
    stagnant = 0
    for i in range(max_scrolls):
        before = len(order)
        for t in page.evaluate(_EXTRACT_JS):
            key = (t["handle"], t["text"])
            if key not in seen:
                seen.add(key)
                order.append(t)
        page.mouse.wheel(0, 3200)
        time.sleep(pause)
        body = page.inner_text("body")[:5000].lower()
        if any(h in body for h in _ERROR_HINTS):
            print(
                f"[{label}] aviso: posible límite/error en el scroll {i}; espero", file=sys.stderr
            )
            time.sleep(3.0)
        if len(order) == before:
            stagnant += 1
            if stagnant >= 3:
                print(
                    f"[{label}] sin contenido nuevo en 3 scrolls; paro en {i + 1}", file=sys.stderr
                )
                break
        else:
            stagnant = 0
    print(f"[{label}] {len(order)} entradas", file=sys.stderr)
    return order


def scrape(account: str, port: int, out_path: Path) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("falta playwright: `pip install playwright`", file=sys.stderr)
        raise SystemExit(2) from None

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://localhost:{port}")
        except Exception as exc:
            print(
                f"no pude conectar a Chrome en localhost:{port} ({exc}). "
                f"¿Está arrancado con --remote-debugging-port={port} --user-data-dir=...?",
                file=sys.stderr,
            )
            raise SystemExit(2) from exc
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        blocks: list[tuple[str, list[dict[str, str]]]] = []

        page.goto(f"https://x.com/{account}", wait_until="domcontentloaded", timeout=40_000)
        time.sleep(4)
        blocks.append(
            (f"TWEETS DE @{account} (timeline del perfil)", _scroll_collect(page, "perfil", 24))
        )

        page.goto(
            f"https://x.com/search?q=to%3A{account}&src=typed_query&f=live",
            wait_until="domcontentloaded",
            timeout=40_000,
        )
        time.sleep(4)
        blocks.append(
            (
                f"REPLIES / MENCIONES dirigidas a @{account} (búsqueda to:)",
                _scroll_collect(page, "replies", 30),
            )
        )

        page.goto(
            f"https://x.com/search?q=(%40{account})%20(descenso%20OR%20modelo%20OR%20probabilidad)"
            f"&src=typed_query&f=live",
            wait_until="domcontentloaded",
            timeout=40_000,
        )
        time.sleep(4)
        blocks.append(
            (
                f"TWEETS que mencionan a @{account} con 'descenso/modelo/probabilidad'",
                _scroll_collect(page, "keywords", 20),
            )
        )
        page.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# Recopilado de x.com el {time.strftime('%Y-%m-%d %H:%M')} (uso único, CP0)\n")
        fh.write(f"# Cuenta: @{account}\n\n")
        for title, items in blocks:
            fh.write(f"\n{'=' * 70}\n## {title}  ({len(items)} entradas)\n{'=' * 70}\n\n")
            for it in items:
                fh.write(f"[@{it['handle']}] {it['text']}\n\n")
                total += 1
    print(f"escrito {out_path} con {total} entradas", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scrapea @LaLigaenDirecto y replies vía CDP")
    parser.add_argument("--account", default="LaLigaenDirecto")
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--out", type=Path, default=Path("data/replies.txt"))
    args = parser.parse_args()
    scrape(args.account, args.port, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
