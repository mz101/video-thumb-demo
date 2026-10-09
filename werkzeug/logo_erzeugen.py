"""Logovarianten ueber Replicate erzeugen.

recraft-v3-svg statt eines Rastermodells: Ein Logo muss vom 16-px-Favicon bis
zum Druck scharf bleiben, und ein hochskaliertes PNG tut das nicht.

    .venv/bin/python -m werkzeug.logo_erzeugen
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

WURZEL = Path(__file__).resolve().parent.parent
load_dotenv(WURZEL / ".env")

MODELL = "recraft-ai/recraft-v3-svg"
ZIEL = WURZEL / "logo"

#: Vier Richtungen, damit es etwas zu vergleichen gibt statt nur zu nehmen,
#: was zuerst herauskommt. Der Name ist die Fadenlupe -- das Werkzeug, mit dem
#: man Dias auf dem Leuchttisch prueft.
VARIANTEN = {
    "01_lupe_seitlich": (
        "Minimal flat vector logo mark: a photographer's loupe seen from the side, "
        "a simple truncated cone with a round lens, drawn in clean geometric "
        "monoline strokes of even weight. Single warm brass gold colour on a "
        "transparent background. No text, no letters, no gradients, no shadows. "
        "Centred, generous margin, suitable as an app icon."
    ),
    "02_lupe_ueber_frame": (
        "Minimal flat vector logo mark: a circular lens sitting over the corner of "
        "a rectangle, as if a magnifier were inspecting a single frame. Geometric, "
        "monoline, even stroke weight, one warm brass gold colour on transparent "
        "background. No text, no letters, no gradients, no shadows. Centred, "
        "generous margin, suitable as an app icon."
    ),
    "03_filmstreifen_lupe": (
        "Minimal flat vector logo mark: three small rectangles in a row like frames "
        "of a filmstrip, with a circle outlining the middle one to mark it as the "
        "chosen frame. Strict geometry, monoline, even stroke weight, one warm "
        "brass gold colour on transparent background. No text, no letters, no "
        "gradients, no shadows. Centred, generous margin."
    ),
    "04_linsenring": (
        "Minimal flat vector logo mark: two concentric circles forming a lens ring, "
        "with a single short tick mark on the outer ring indicating a selected "
        "position, like a timeline marker. Precise geometry, monoline, even stroke "
        "weight, one warm brass gold colour on transparent background. No text, no "
        "letters, no gradients, no shadows. Centred, generous margin."
    ),
}


def _anfrage(pfad: str, daten: dict | None = None) -> dict:
    schluessel = os.getenv("REPLICATE_API_TOKEN")
    if not schluessel:
        raise SystemExit("REPLICATE_API_TOKEN ist nicht gesetzt.")
    r = urllib.request.Request(
        f"https://api.replicate.com/v1{pfad}",
        data=json.dumps(daten).encode() if daten else None,
        headers={"Authorization": f"Bearer {schluessel}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=120) as a:
        return json.loads(a.read())


def erzeugen(name: str, prompt: str) -> Path | None:
    lauf = _anfrage(f"/models/{MODELL}/predictions", {
        "input": {"prompt": prompt, "style": "line_art", "size": "1024x1024"},
    })

    for _ in range(90):
        if lauf["status"] in ("succeeded", "failed", "canceled"):
            break
        time.sleep(2)
        lauf = _anfrage(f"/predictions/{lauf['id']}")

    if lauf["status"] != "succeeded":
        print(f"  {name}: {lauf['status']} — {str(lauf.get('error'))[:80]}")
        return None

    adresse = lauf["output"]
    if isinstance(adresse, list):
        adresse = adresse[0]

    ZIEL.mkdir(exist_ok=True)
    datei = ZIEL / f"{name}.svg"
    with urllib.request.urlopen(adresse, timeout=60) as a:
        datei.write_bytes(a.read())
    print(f"  {name}: {datei.stat().st_size / 1024:.0f} kB → {datei.relative_to(WURZEL)}")
    return datei


def main() -> int:
    nur = sys.argv[1] if len(sys.argv) > 1 else None
    for name, prompt in VARIANTEN.items():
        if nur and nur not in name:
            continue
        try:
            erzeugen(name, prompt)
        except Exception as e:
            print(f"  {name}: {type(e).__name__}: {str(e)[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
