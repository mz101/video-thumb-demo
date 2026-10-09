"""Kalibrierwerte und Umgebung.

Alle Zahlen, die die Auswahl beeinflussen, stehen hier und nirgends sonst.
Die Kalibrierung dreht ausschliesslich an diesen Werten; wer sie im
Code verstreut, kann nicht mehr kalibrieren.

Belegte Werte siehe kalibrierung/.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


# --- Extraktion ------------------------------------------------------------

#: Breite, auf die im selben ffmpeg-Aufruf skaliert wird. Nichts nach der
#: Extraktion sieht jemals 4K. min(...) verhindert Hochrechnen kleiner Quellen.
ARBEITSBREITE = 1280

#: Laengengrenzen. Das Konzept setzte 5 min; auf 10 angehoben, weil in der
#: Praxis laengere Beitraege anfielen.
#:
#: Was daran haengt: Die Kosten nicht -- der Filter landet unabhaengig von der
#: Laenge bei ~20 Kandidaten. Die Abtastdichte schon: Bei 10 min und 10 s GOP
#: bleiben 6 Frames je Minute. Wer da mehr braucht, nimmt "gruendlich".
#: Und die Tonspur-Auswertung kostet linear mit der Laenge -- bei 10 min rund
#: 3 ct, also mehr als der Rest des Laufs zusammen.
DAUER_MIN_S = 60.0
DAUER_MAX_S = 600.0

#: Schnellmodus: Keyframes aus den Paket-Flags. Liegt die Zahl darunter, wird
#: mit gleichmaessig verteilten Zeitstempeln aufgefuellt -- fuer Material mit
#: langem GOP, das sonst zu wenige Kandidaten liefert.
FRAMES_MIN_SCHNELL = 40

#: Gruendlich: ein Voll-Decode mit fps-Filter auf diese Zielzahl.
FRAMES_ZIEL_GRUENDLICH = 150

#: Obergrenze auch im Schnellmodus. Kurz-GOP-Material (02: 2,6 s) liefert sonst
#: mehr Frames als der Filter braucht, und jeder kostet Decode-Zeit.
FRAMES_MAX = 200

#: Parallele ffmpeg-Prozesse bei der Seek-Extraktion.
EXTRAKT_PARALLEL = min(6, (os.cpu_count() or 4))


# --- Technischer Filter ----------------------------------------------------

#: Zielmenge fuer die Bewertung. Der Filter trifft *diese Zahl*, nicht eine
#: Schwelle -- Laplacian-Werte sind zwischen Videos nicht vergleichbar.
KANDIDATEN_ZIEL = 20

#: Der Schaerfefilter rechnet relativ zum Video. Eine lange weiche Sequenz
#: (Animation, Nachtaufnahme) verliert dann komplett gegen scharfes
#: Realmaterial: Am Fossilien-Video ueberlebte zwischen Sekunde 37 und 81
#: kein einziger Frame -- 43 Sekunden Video ohne Vertretung. Klafft nach dem
#: Filtern eine Luecke groesser als dieser Anteil der Laufzeit, kommt der
#: jeweils beste Frame aus der Luecke zurueck, auch unter der Schwelle.
LUECKE_ANTEIL_DAUER = 1 / 8
LUECKEN_FUELLUNGEN_MAX = 4

#: Untergrenze. Wird sie unterschritten, laeuft der Fallback.
KANDIDATEN_MIN = 6

#: Anteil der Frames, der nach Schaerfe ueberlebt, bevor entdoppelt wird.
#: Perzentil, kein Absolutwert.
SCHAERFE_PERZENTIL = 0.55

#: Harte Ausschluesse -- absichtlich sehr locker gesetzt. Sie sollen kaputte
#: Frames wegnehmen (Schwarzblende, Weissblitz), nicht kuratieren.
HELLIGKEIT_MIN = 18.0
HELLIGKEIT_MAX = 242.0
CLIPPING_MAX = 0.55

#: Entdopplung: Hamming-Abstand der dHashes, ab dem zwei Frames als
#: verschieden gelten. Startwert; wird gesenkt, bis KANDIDATEN_ZIEL erreicht
#: ist. Das ist die Talking-Head-Betriebsart -- ohne Sonderweg.
DHASH_ABSTAND_START = 14
DHASH_ABSTAND_MIN = 3

#: Nachgelagerte Diversitaetspruefung. Das Konzept verlangt sie zusaetzlich
#: zur Anweisung im Prompt -- die Anweisung allein genuegt nicht.
#:
#: Der Abstand ist laufzeitrelativ, nicht fest. Kalibrierbefund: Mit festen 6 s
#: passierten bei 01 (4:32 Naturmaterial) zwei Vorschlaege im Abstand von 6,4 s
#: die Pruefung, obwohl es dieselbe Einstellung war. Ein fester Wert, der bei
#: 2 min taugt, ist bei 5 min zu lasch.
DIVERSITAET_MIN_ABSTAND_S = 8.0        # Untergrenze
DIVERSITAET_ANTEIL_DAUER = 1 / 20      # bei 272 s ergibt das 13,6 s

#: Zeitabstand allein reicht nicht: Eine fest stehende Kamera liefert nach
#: zwei Minuten wieder dasselbe Bild. Das Konzept nennt beide Masse.
DIVERSITAET_MIN_HASH = 8


def mindestabstand(dauer: float) -> float:
    return max(DIVERSITAET_MIN_ABSTAND_S, dauer * DIVERSITAET_ANTEIL_DAUER)


# --- Bewertung -------------------------------------------------------------

#: Kantenlaenge, auf die Kandidaten fuer den Modell-Aufruf runterskaliert
#: werden. Zusammen mit detail="low" -- ohne das schickt GPT-5.6 die
#: Originalaufloesung (detail="auto" entspricht dort "original").
VORSCHAU_KANTE = 512

MODELL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

#: Bilder je Verortungsaufruf. Mit 24 Bildern in einem Aufruf pendelte der
#: Kopf-Anker des Fisch-Frames zwischen (25,74) und (43,55) -- die Streuung
#: kreuzte die Entscheidungsgrenze. Mit 8 je Aufruf blieb er in drei
#: Wiederholungen bei Band 0-2 gegen Band 3 der Mitte-Frames. Die Haeppchen
#: laufen parallel, die Laufzeit bleibt die eines Aufrufs.
VERORTUNG_HAEPPCHEN = 8

#: Gewichtung der Achsen bei der Aggregation. Laeuft in Code, nicht im Modell --
#: sonst hat die Kalibrierung keine Stellschraube.
ACHSEN_GEWICHTE: dict[str, float] = {
    "headline_bezug": 0.34,
    "motiv": 0.24,
    "gesicht": 0.14,
    "lesbarkeit": 0.20,
    "textflaeche": 0.08,
}

#: Zusatzgewicht, wenn der Schalter "Gesichter bevorzugen" an ist.
GEWICHT_GESICHT_BONUS = 0.12

#: Zusatzgewicht, wenn "Platz fuer Titeltext" an ist.
GEWICHT_TEXTFLAECHE_BONUS = 0.16


# --- Motivlage -------------------------------------------------------------

#: Drittelraster, von oben links nach unten rechts gelesen.
MOTIVLAGEN = (
    "oben_links", "oben_mitte", "oben_rechts",
    "mitte_links", "mitte", "mitte_rechts",
    "unten_links", "unten_mitte", "unten_rechts",
)

#: Antwort des Modells, wenn es kein Hauptmotiv ausmachen kann -- Landschaft,
#: Textur, gleichmaessig gefuellte Flaeche. Dann greift der Wunsch nicht.
KEIN_MOTIV = "kein_klares_motiv"

#: Aufschlag auf den Gesamtscore, wenn die Lage dem Wunsch entspricht. Kein
#: hartes Filter: Ein schwaches Bild an der richtigen Stelle soll ein starkes
#: an der falschen nicht verdraengen.
#:
#: Ein Aufschlag in Scorepunkten war der falsche Mechanismus. Gemessen am
#: Regenwald-Video: Die Grundwerte reichen von 21,7 bis 80,7 -- ueber diese
#: Spanne konnte ein Bonus von 12 nichts ausrichten. Fuenf von neun Wuenschen
#: aenderten die Auswahl ueberhaupt nicht.
#:
#: Verlangt war ohnehin etwas anderes: "gibt es kein passendes Thumbnail, so
#: soll ein Hinweis erscheinen und dann die alternativ besten". Das ist eine
#: Vorauswahl mit Rueckfall, keine Gewichtung. Die Lage bestimmt jetzt die
#: *Stufe*; innerhalb einer Stufe entscheidet die Bewertung.
STUFE_GENAU = 2         #: Motiv sitzt genau in der gewuenschten Zelle
STUFE_RICHTUNG = 1      #: eine Achse stimmt, in der verlangten Richtung
STUFE_OHNE = 0          #: kein Bezug zum Wunsch


def _versatz(lage: str) -> tuple[int, int]:
    """Zeile und Spalte als Versatz von der Mitte: -1, 0 oder +1."""
    i = MOTIVLAGEN.index(lage)
    return i // 3 - 1, i % 3 - 1


def lage_stufe(wunsch: str, ist: str) -> int:
    """Wie gut eine Lage dem Wunsch entspricht: 2, 1 oder 0.

    Die Zwischenstufe gilt nur, wenn das Motiv **in die gewuenschte Richtung**
    verschoben ist. Die Mitte bekommt sie nicht -- sie ist die Vorgabelage und
    zaehlte sonst bei vier von acht Wuenschen als Teiltreffer, obwohl sie genau
    das Gegenteil dessen ist, was verlangt wurde.
    """
    if wunsch == "egal" or ist in ("", KEIN_MOTIV) or ist not in MOTIVLAGEN:
        return STUFE_OHNE
    if wunsch == ist:
        return STUFE_GENAU

    wz, ws = _versatz(wunsch)
    iz, isp = _versatz(ist)
    verlangt = [(w, i) for w, i in ((wz, iz), (ws, isp)) if w != 0]
    if not verlangt:                       # Wunsch war die Mitte -- nur genau
        return STUFE_OHNE
    if any(w == -i and i != 0 for w, i in verlangt):     # gegenlaeufig
        return STUFE_OHNE
    return STUFE_RICHTUNG if any(w == i for w, i in verlangt) else STUFE_OHNE


#: Das Modell nennt die Lage als Punkt (x/y in Prozent), nicht als Zelle.
#: Gemessen an Montagen mit bekannter Position: 14 von 14 im richtigen
#: Viertel, Spiegelabweichung Median 1 von 100 -- die Koordinaten sind bei
#: detail=low stabil. Die Zelle wird daraus abgeleitet und traegt weiterhin
#: Beschriftung und Hinweis; die *Rangfolge* rechnet mit dem Abstand.
#:
#: Der Abstand ist in Kacheln gerastert. Roh sortiert wuerden 3 Prozentpunkte
#: Koordinatenrauschen entscheiden, welcher Frame gewinnt -- innerhalb einer
#: Kachel entscheidet stattdessen die Bewertung.
#:
#: 24 (halbe Zelldiagonale) war zu grob: Am Fossilien-Video lagen der Fisch
#: unten links (Abstand 26-35 zum Wunsch) und ein totmittiger Frame (47) im
#: selben Band -- die Qualitaet entschied, die Position verlor. 12 trennt die
#: beiden und liegt immer noch beim Dreifachen des gemessenen Rauschens
#: (Spiegelabweichung maximal 4).
LAGE_KACHEL = 12.0

#: Kandidaten ohne klares Motiv laufen ganz hinten mit -- hinter dem
#: entferntesten echten Motiv (Bilddiagonale 141 / Kachel 12 -> 11).
LAGE_BAND_OHNE_MOTIV = 12

#: Prioritaet "Qualitaet": Bewertung zuerst, in Stufen dieser Breite --
#: innerhalb einer Stufe entscheidet die Naehe zum Positionswunsch. Das
#: Spiegelbild der Positions-Prioritaet.
QUALITAETS_KACHEL = 8.0


def zelle_von_punkt(x: float, y: float) -> str:
    """Drittelraster-Zelle, in der der Punkt (Prozent) liegt."""
    spalte = min(int(x * 3 / 100), 2)
    zeile = min(int(y * 3 / 100), 2)
    return MOTIVLAGEN[zeile * 3 + spalte]


def zellmitte(lage: str) -> tuple[float, float] | None:
    """Mittelpunkt einer Zelle in Prozent -- Ersatzkoordinaten fuer Laeufe,
    die vor dem Umbau nur die Zelle gespeichert haben."""
    if lage not in MOTIVLAGEN:
        return None
    i = MOTIVLAGEN.index(lage)
    return ((i % 3) * 100 / 3 + 100 / 6, (i // 3) * 100 / 3 + 100 / 6)


def lage_abstand(wunsch: str, x: float, y: float, klar: bool) -> float:
    """Abstand des Motivpunkts zur Wunschzellmitte, in Prozentpunkten.
    Ohne klares Motiv jenseits jeder echten Entfernung."""
    if wunsch not in MOTIVLAGEN:
        return 0.0
    if not klar:
        return 999.0
    wx, wy = zellmitte(wunsch)
    return ((x - wx) ** 2 + (y - wy) ** 2) ** 0.5


def lage_band(wunsch: str, x: float, y: float, klar: bool) -> int:
    """Abstandsband zum Wunsch: 0 = an der Wunschzellmitte, dann je Kachel
    eins weiter. Innerhalb eines Bandes entscheidet die Bewertung."""
    if wunsch not in MOTIVLAGEN:
        return 0
    if not klar:
        return LAGE_BAND_OHNE_MOTIV
    abstand = lage_abstand(wunsch, x, y, klar)
    return min(int(abstand // LAGE_KACHEL), LAGE_BAND_OHNE_MOTIV - 1)


# --- Formate ---------------------------------------------------------------

FORMATE: dict[str, tuple[int, int]] = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "1:1": (1, 1),
}

EXPORT_BREITE: dict[str, int] = {
    "16:9": 1280,
    "9:16": 720,
    "1:1": 1080,
}


@dataclass
class Lauf:
    """Ein Durchlauf. Entspricht den Schaltern der Oberflaeche."""

    video: Path
    headline: str
    beschreibung: str
    tiefe: str = "schnell"           # schnell | gruendlich
    format: str = "16:9"
    gesichter_bevorzugen: bool = True
    textflaeche: bool = False
    anzahl: int = 3
    schaerfe_perzentil: float = SCHAERFE_PERZENTIL
    ueberlaenge: bool = False
    transkript: bool = False
    sprache: str = "de"
    motivlage: str = "egal"          # "egal" oder ein Wert aus MOTIVLAGEN
    lage_prio: str = "position"      # position | qualitaet
    ausgabe: Path = field(default_factory=lambda: ROOT / "ausgabe")

    def gewichte(self) -> dict[str, float]:
        g = dict(ACHSEN_GEWICHTE)
        # Ohne Headline hat die Hauptachse keinen Bezugspunkt. Ihr Gewicht
        # geht dann an Motiv und Lesbarkeit -- das sind die Achsen, die ein
        # Thumbnail auch ohne Zieltext beurteilbar machen.
        if not self.headline.strip():
            frei = g.pop("headline_bezug")
            g["motiv"] += frei * 0.6
            g["lesbarkeit"] += frei * 0.4
        if self.gesichter_bevorzugen:
            g["gesicht"] += GEWICHT_GESICHT_BONUS
        if self.textflaeche:
            g["textflaeche"] += GEWICHT_TEXTFLAECHE_BONUS
        summe = sum(g.values())
        return {k: v / summe for k, v in g.items()}
