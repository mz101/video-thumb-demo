"""Messwerte je Frame. Reine Bildtechnik, keine Inhaltsbewertung.

Alle Werte sind roh und absolut. Vergleichbar gemacht werden sie erst in
filtering.py, und zwar als Perzentil innerhalb *desselben* Videos -- ein
Laplacian-Wert von 120 heisst bei einem Nachtdreh etwas anderes als bei einer
Studioaufnahme.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Messwerte:
    schaerfe: float          # Varianz des Laplace-Operators
    helligkeit: float        # mittlere Luminanz, 0-255
    clipping: float          # Anteil abgesoffener oder ausgefressener Pixel
    kontrast: float          # Standardabweichung der Luminanz
    dhash: int               # 64-Bit-Differenzhash
    textflaeche: float       # 0-1, Ruhe der ruhigsten Drittelflaeche
    textflaeche_lage: str    # oben | mitte | unten

    def als_dict(self) -> dict:
        d = asdict(self)
        d["dhash"] = f"{self.dhash:016x}"
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()}


def _dhash(grau: np.ndarray, kante: int = 8) -> int:
    klein = cv2.resize(grau, (kante + 1, kante), interpolation=cv2.INTER_AREA)
    bits = klein[:, 1:] > klein[:, :-1]
    wert = 0
    for bit in bits.flatten():
        wert = (wert << 1) | int(bit)
    return wert


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _textflaeche(grau: np.ndarray) -> tuple[float, str]:
    """Wie ruhig ist die ruhigste waagerechte Drittelflaeche?

    Kantendichte als Mass. Ein Frame mit einer glatten Himmels- oder
    Wandflaeche traegt spaeter Text; einer mit Struktur ueberall nicht.
    """
    kanten = cv2.Canny(grau, 60, 160)
    h = kanten.shape[0]
    drittel = {
        "oben": kanten[: h // 3],
        "mitte": kanten[h // 3 : 2 * h // 3],
        "unten": kanten[2 * h // 3 :],
    }
    dichten = {name: float(np.count_nonzero(a)) / a.size for name, a in drittel.items()}
    lage = min(dichten, key=dichten.get)
    # 0,12 Kantenanteil gilt als "voll" -- darueber ist keine Flaeche mehr ruhig.
    ruhe = max(0.0, 1.0 - dichten[lage] / 0.12)
    return min(1.0, ruhe), lage


def messen(pfad: Path) -> Messwerte | None:
    bild = cv2.imread(str(pfad), cv2.IMREAD_COLOR)
    if bild is None:
        return None
    grau = cv2.cvtColor(bild, cv2.COLOR_BGR2GRAY)

    dunkel = float(np.count_nonzero(grau < 6)) / grau.size
    hell = float(np.count_nonzero(grau > 249)) / grau.size
    ruhe, lage = _textflaeche(grau)

    return Messwerte(
        schaerfe=float(cv2.Laplacian(grau, cv2.CV_64F).var()),
        helligkeit=float(grau.mean()),
        clipping=dunkel + hell,
        kontrast=float(grau.std()),
        dhash=_dhash(grau),
        textflaeche=ruhe,
        textflaeche_lage=lage,
    )
