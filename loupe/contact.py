"""Kontaktbogen.

Kein Beiwerk. Das ist die Sicht, ohne die man Schwellwerte und Prompt nicht
justieren kann -- die Pipeline laeuft sonst sauber durch und liefert trotzdem
mittelmaessige Ergebnisse.

Zwei Boegen pro Lauf:
  02_kandidaten   die ~20, die durch den Filter kamen, mit Scores
  01_alle_frames  alles Extrahierte, verworfene gedaempft und beschriftet
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .filtering import Kandidat
from .scoring import Bewertet

# Farben nach der Gestaltungsrichtung (BGR, weil OpenCV).
RAUM = (27, 29, 30)
LINIE = (52, 57, 59)
TINTE = (228, 236, 239)
TINTE_MATT = (140, 150, 155)
MESSING = (39, 162, 201)
KUEHL = (166, 146, 115)


def _zelle(bild: np.ndarray, breite: int, hoehe: int) -> np.ndarray:
    h, w = bild.shape[:2]
    faktor = min(breite / w, hoehe / h)
    neu = cv2.resize(
        bild, (max(1, int(w * faktor)), max(1, int(h * faktor))),
        interpolation=cv2.INTER_AREA,
    )
    flaeche = np.full((hoehe, breite, 3), RAUM, dtype=np.uint8)
    y = (hoehe - neu.shape[0]) // 2
    x = (breite - neu.shape[1]) // 2
    flaeche[y : y + neu.shape[0], x : x + neu.shape[1]] = neu
    return flaeche


def _text(bogen, txt, x, y, farbe=TINTE, skala=0.4, dicke=1):
    cv2.putText(bogen, txt, (x, y), cv2.FONT_HERSHEY_SIMPLEX, skala, farbe, dicke, cv2.LINE_AA)


def _raster(
    eintraege: list[tuple[np.ndarray, list[tuple[str, tuple]]]],
    spalten: int,
    zellbreite: int,
    zellhoehe: int,
    kopf: str,
    ziel: Path,
) -> Path:
    if not eintraege:
        return ziel

    zeilen = (len(eintraege) + spalten - 1) // spalten
    rand, textraum, kopfraum = 12, 16, 46
    zh = zellhoehe + textraum * max(1, max(len(z[1]) for z in eintraege)) + rand

    breite = spalten * (zellbreite + rand) + rand
    hoehe = kopfraum + zeilen * zh + rand
    bogen = np.full((hoehe, breite, 3), RAUM, dtype=np.uint8)

    _text(bogen, kopf, rand, 28, TINTE, 0.52)
    cv2.line(bogen, (rand, kopfraum - 8), (breite - rand, kopfraum - 8), LINIE, 1)

    for i, (bild, zeilentexte) in enumerate(eintraege):
        r, c = divmod(i, spalten)
        x = rand + c * (zellbreite + rand)
        y = kopfraum + r * zh
        bogen[y : y + zellhoehe, x : x + zellbreite] = _zelle(bild, zellbreite, zellhoehe)
        for j, (txt, farbe) in enumerate(zeilentexte):
            _text(bogen, txt, x, y + zellhoehe + 13 + j * textraum, farbe, 0.38)

    ziel.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ziel), bogen)
    return ziel


def alle_frames(alle: list[Kandidat], behalten: set[str], ziel: Path) -> Path:
    eintraege = []
    for k in sorted(alle, key=lambda k: k.zeit):
        bild = cv2.imread(str(k.pfad), cv2.IMREAD_COLOR)
        if bild is None:
            continue
        drin = k.id in behalten
        if not drin:
            bild = (bild.astype(np.float32) * 0.32).astype(np.uint8)
        eintraege.append((bild, [
            (f"{k.zeitcode}  {'+' if drin else '-'}", MESSING if drin else TINTE_MATT),
            (f"sch {k.werte.schaerfe:.0f}  p{k.schaerfe_rang:.2f}", TINTE_MATT),
        ]))
    return _raster(eintraege, 8, 190, 108,
                   f"Alle extrahierten Frames — {len(behalten)} von {len(alle)} behalten", ziel)


def kandidaten(bewertet: list[Bewertet], auswahl: set[str], format: str, ziel: Path) -> Path:
    from . import crop

    eintraege = []
    for b in sorted(bewertet, key=lambda b: b.kandidat.zeit):
        try:
            bild = crop.vorschau(b.kandidat.pfad, format, kante=320)
        except ValueError:
            continue
        gewaehlt = b.kandidat.id in auswahl
        s = b.scores
        eintraege.append((bild, [
            (f"{b.kandidat.id}  {b.kandidat.zeitcode}  {'GEWAEHLT' if gewaehlt else ''}",
             MESSING if gewaehlt else TINTE),
            (f"gesamt {b.gesamt:5.1f}", MESSING if gewaehlt else KUEHL),
            (f"hl {s.get('headline_bezug',0):3d} mo {s.get('motiv',0):3d} "
             f"ge {s.get('gesicht',0):3d}", TINTE_MATT),
            (f"le {s.get('lesbarkeit',0):3d} tx {s.get('textflaeche',0):3d}", TINTE_MATT),
            (b.begruendung[:42], TINTE_MATT),
        ]))
    return _raster(eintraege, 5, 300, 172,
                   f"Kandidaten mit Bewertung — Format {format}", ziel)
