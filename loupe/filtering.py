"""Stufe 3: von ~50-200 Frames auf ~20 Kandidaten.

Der Filter trifft eine **Zielmenge**, keine Schwelle. Absolute Schwellwerte
scheitern zwischen Videos: Laplacian-Varianz haengt an Aufloesung, Korn,
Blende und Grading und schwankt um Groessenordnungen. Ein Wert, der bei
Studiomaterial sauber trennt, wirft bei einem Nachtdreh alles weg.

Nebeneffekt: Die befuerchtete Talking-Head-Schwachstelle
braucht keine eigene Betriebsart. Wenn fast alles gleich aussieht, lockert
die Entdopplung von selbst, bis genug Kandidaten uebrig sind.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import config
from .extract import Frame
from .metrics import Messwerte, hamming, messen


@dataclass
class Kandidat:
    index: int
    zeit: float
    pfad: Path
    werte: Messwerte
    schaerfe_rang: float = 0.0     # 0-1, Perzentil innerhalb dieses Videos

    @property
    def id(self) -> str:
        return f"k{self.index:04d}"

    @property
    def zeitcode(self) -> str:
        m, s = divmod(self.zeit, 60)
        return f"{int(m):02d}:{s:05.2f}"


def _messen_alle(frames: list[Frame]) -> list[Kandidat]:
    kandidaten = []
    for f in frames:
        w = messen(f.pfad)
        if w is not None:
            kandidaten.append(Kandidat(f.index, f.zeit, f.pfad, w))
    return kandidaten


def _harte_ausschluesse(kandidaten: list[Kandidat]) -> tuple[list[Kandidat], int]:
    behalten = [
        k for k in kandidaten
        if config.HELLIGKEIT_MIN <= k.werte.helligkeit <= config.HELLIGKEIT_MAX
        and k.werte.clipping <= config.CLIPPING_MAX
    ]
    # Wenn die Ausschluesse fast alles treffen, ist das Material dunkel oder
    # hell -- dann greifen sie nicht, statt den Lauf leerlaufen zu lassen.
    if len(behalten) < config.KANDIDATEN_MIN:
        return kandidaten, 0
    return behalten, len(kandidaten) - len(behalten)


def _schaerfe_perzentil(kandidaten: list[Kandidat], anteil: float) -> list[Kandidat]:
    if not kandidaten:
        return []
    sortiert = sorted(kandidaten, key=lambda k: k.werte.schaerfe)
    for rang, k in enumerate(sortiert):
        k.schaerfe_rang = rang / max(1, len(sortiert) - 1)

    behalten = max(config.KANDIDATEN_ZIEL, int(len(sortiert) * anteil))
    return sortiert[-behalten:]


def _entdoppeln(kandidaten: list[Kandidat], abstand: int) -> list[Kandidat]:
    """Gierig: schaerfster zuerst, dann jeder, der weit genug weg ist."""
    gewaehlt: list[Kandidat] = []
    for k in sorted(kandidaten, key=lambda k: -k.werte.schaerfe):
        if all(hamming(k.werte.dhash, g.werte.dhash) >= abstand for g in gewaehlt):
            gewaehlt.append(k)
    return sorted(gewaehlt, key=lambda k: k.zeit)


def _luecken_fuellen(
    kandidaten: list[Kandidat], alle: list[Kandidat]
) -> list[Kandidat]:
    """Grosse Zeitluecken schliessen -- der Schaerfefilter ist zeitblind.

    Er rechnet relativ zum Video: Eine lange weiche Sequenz verliert komplett
    gegen scharfes Realmaterial, und ganze Passagen verschwinden aus dem
    Kandidatensatz (gemessen: 43 s Loch am Fossilien-Video). Wer dort etwas
    sucht -- etwa ein Motiv unten links, das nur in der Animation vorkommt --
    kann es nicht finden, egal wie gut die Auswahl danach arbeitet.

    Deshalb: Klafft zwischen zwei Kandidaten mehr als LUECKE_ANTEIL_DAUER der
    Laufzeit, kommt der schaerfste Frame aus der Luecke zurueck, auch wenn er
    unter der Perzentilschwelle liegt. Groesste Luecke zuerst, bis keine mehr
    klafft oder LUECKEN_FUELLUNGEN_MAX erreicht ist.
    """
    if not kandidaten or not alle:
        return kandidaten
    dauer = max(k.zeit for k in alle)
    schwelle = dauer * config.LUECKE_ANTEIL_DAUER
    gewaehlt = sorted(kandidaten, key=lambda k: k.zeit)
    drin = {k.index for k in gewaehlt}

    for _ in range(config.LUECKEN_FUELLUNGEN_MAX):
        raender = [0.0] + [k.zeit for k in gewaehlt] + [dauer]
        luecken = sorted(
            ((raender[i + 1] - raender[i], raender[i], raender[i + 1])
             for i in range(len(raender) - 1)),
            reverse=True,
        )
        breite, von, bis = luecken[0]
        if breite <= schwelle:
            break
        fuellung = [
            k for k in alle
            if von < k.zeit < bis and k.index not in drin
            and all(hamming(k.werte.dhash, g.werte.dhash) >= config.DHASH_ABSTAND_MIN
                    for g in gewaehlt)
        ]
        if not fuellung:
            break
        beste = max(fuellung, key=lambda k: k.werte.schaerfe)
        gewaehlt = sorted(gewaehlt + [beste], key=lambda k: k.zeit)
        drin.add(beste.index)
    return gewaehlt


def filtern(
    frames: list[Frame],
    schaerfe_perzentil: float = config.SCHAERFE_PERZENTIL,
) -> tuple[list[Kandidat], list[Kandidat], dict]:
    """Gibt (Kandidaten, alle vermessenen Frames, Protokoll) zurueck.

    Die vollstaendige Liste wandert in den Kontaktbogen -- ohne sie kann man
    nicht sehen, was der Filter weggeworfen hat, und ohne diese Sicht laeuft
    die Pipeline sauber durch und liefert trotzdem mittelmaessige Ergebnisse.
    """
    alle = _messen_alle(frames)
    nach_ausschluss, verworfen_hart = _harte_ausschluesse(alle)
    nach_schaerfe = _schaerfe_perzentil(nach_ausschluss, schaerfe_perzentil)

    abstand = config.DHASH_ABSTAND_START
    kandidaten = _entdoppeln(nach_schaerfe, abstand)
    while len(kandidaten) < config.KANDIDATEN_ZIEL and abstand > config.DHASH_ABSTAND_MIN:
        abstand -= 1
        kandidaten = _entdoppeln(nach_schaerfe, abstand)

    # Immer noch zu viele? Nach Schaerfe kappen, Zeitreihenfolge behalten.
    if len(kandidaten) > config.KANDIDATEN_ZIEL:
        beste = sorted(kandidaten, key=lambda k: -k.werte.schaerfe)[: config.KANDIDATEN_ZIEL]
        kandidaten = sorted(beste, key=lambda k: k.zeit)

    vor_fuellung = len(kandidaten)
    kandidaten = _luecken_fuellen(kandidaten, alle)

    protokoll = {
        "lueckenfuellung": len(kandidaten) - vor_fuellung,
        "vermessen": len(alle),
        "verworfen_belichtung": verworfen_hart,
        "nach_schaerfe": len(nach_schaerfe),
        "dhash_abstand_final": abstand,
        "kandidaten": len(kandidaten),
        "entdopplung_gelockert": abstand < config.DHASH_ABSTAND_START,
    }
    return kandidaten, alle, protokoll


def fallback(alle: list[Kandidat], anzahl: int) -> list[Kandidat]:
    """Gleichmaessig ueber die Laufzeit verteilte Frames.

    Greift, wenn die Bewertung nichts liefert. Das Ergebnis ist technisch
    zustande gekommen, nicht inhaltlich, und muss im Interface so
    gekennzeichnet werden.
    """
    if not alle:
        return []
    nach_zeit = sorted(alle, key=lambda k: k.zeit)
    if len(nach_zeit) <= anzahl:
        return nach_zeit
    schritt = len(nach_zeit) / anzahl
    return [nach_zeit[int((i + 0.5) * schritt)] for i in range(anzahl)]
