"""Zuschnitt -- laeuft VOR der Bewertung, nicht danach.

Das Konzept hat den Zuschnitt als Stufe 5 gefuehrt. Bei 9:16 wirft man damit
68 % der Breite weg, nachdem das Modell entschieden hat: Ein Frame, der als
16:9 stark ist -- zwei Personen, Blickachse quer durchs Bild -- ist als 9:16
Ausschuss, und das Modell hat ihn nie so gesehen.

Wo zugeschnitten wird, entscheidet ein Energiemass (Kantendichte) mit
Mittenpraeferenz. Kein Gesichtsdetektor: Haar-Cascades sind bei Profilen
unzuverlaessig, und alles Bessere zoege ein Modell ins Image, das
bewusst nicht hinein soll (kein PyTorch, kein CLIP).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config


def _energiefenster(energie: np.ndarray, fenster: int, achse: int) -> int:
    """Position des energiereichsten Fensters, mit Zug zur Mitte."""
    laenge = energie.shape[achse]
    if fenster >= laenge:
        return 0

    profil = energie.sum(axis=1 - achse).astype(np.float64)
    kumuliert = np.concatenate([[0.0], np.cumsum(profil)])
    summen = kumuliert[fenster:] - kumuliert[:-fenster]

    positionen = np.arange(len(summen))
    mitte = (laenge - fenster) / 2.0
    # Milde Mittenpraeferenz: bei annaehernd gleicher Energie gewinnt die Mitte,
    # weil aussermittige Schnitte bei Bewegtbild schnell willkuerlich wirken.
    strafe = 1.0 - 0.35 * (np.abs(positionen - mitte) / max(mitte, 1.0)) ** 2
    return int(np.argmax(summen * strafe))


def zuschneiden(bild: np.ndarray, format: str) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    h, w = bild.shape[:2]
    zb, zh = config.FORMATE[format]
    ziel = zb / zh
    ist = w / h

    if abs(ist - ziel) < 0.01:
        return bild, (0, 0, w, h)

    grau = cv2.cvtColor(bild, cv2.COLOR_BGR2GRAY)
    energie = cv2.Canny(grau, 60, 160).astype(np.float32)
    energie = cv2.GaussianBlur(energie, (0, 0), sigmaX=max(w, h) / 60.0)

    if ist > ziel:
        neu_w = int(round(h * ziel))
        x = _energiefenster(energie, neu_w, achse=1)
        return bild[:, x : x + neu_w], (x, 0, neu_w, h)

    neu_h = int(round(w / ziel))
    y = _energiefenster(energie, neu_h, achse=0)
    return bild[y : y + neu_h], (0, y, w, neu_h)


def vorschau(pfad: Path, format: str, kante: int = config.VORSCHAU_KANTE) -> np.ndarray:
    """Zugeschnittenes Bild, runterskaliert fuer den Modell-Aufruf."""
    bild = cv2.imread(str(pfad), cv2.IMREAD_COLOR)
    if bild is None:
        raise ValueError(f"Bild nicht lesbar: {pfad}")
    geschnitten, _ = zuschneiden(bild, format)
    h, w = geschnitten.shape[:2]
    faktor = kante / max(h, w)
    if faktor < 1.0:
        geschnitten = cv2.resize(
            geschnitten, (max(1, int(w * faktor)), max(1, int(h * faktor))),
            interpolation=cv2.INTER_AREA,
        )
    return geschnitten


def export(pfad: Path, format: str, ziel: Path) -> Path:
    """Finaler Export in voller Arbeitsaufloesung."""
    bild = cv2.imread(str(pfad), cv2.IMREAD_COLOR)
    if bild is None:
        raise ValueError(f"Bild nicht lesbar: {pfad}")
    geschnitten, _ = zuschneiden(bild, format)

    breite = config.EXPORT_BREITE[format]
    zb, zh = config.FORMATE[format]
    hoehe = int(round(breite * zh / zb))
    h, w = geschnitten.shape[:2]
    interpolation = cv2.INTER_AREA if breite < w else cv2.INTER_CUBIC
    geschnitten = cv2.resize(geschnitten, (breite, hoehe), interpolation=interpolation)

    ziel.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ziel), geschnitten, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return ziel
