"""Ablauf der Pipeline und das Protokoll darueber.

Das Protokoll (lauf.json) ist der zweite Teil des Kalibrierwerkzeugs: Es
haelt jeden Zwischenwert fest, sodass sich zwei Laeufe vergleichen lassen.
Zusammen mit --rescore kostet eine Prompt-Iteration Sekunden statt Minuten.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import (config, contact, crop, extract, filtering, meldungen, scoring,
               transkript as transkript_modul)
from .config import Lauf
from .filtering import Kandidat


@dataclass
class Ergebnis:
    auswahl: list[scoring.Bewertet] = field(default_factory=list)
    bewertet: list[scoring.Bewertet] = field(default_factory=list)
    exporte: list[Path] = field(default_factory=list)
    protokoll: dict = field(default_factory=dict)
    fallback: bool = False


class Uhr:
    def __init__(self) -> None:
        self.zeiten: dict[str, float] = {}
        self._start = time.perf_counter()

    def stempel(self, name: str) -> None:
        jetzt = time.perf_counter()
        self.zeiten[name] = round(jetzt - self._start, 2)
        self._start = jetzt

    @property
    def gesamt(self) -> float:
        return round(sum(self.zeiten.values()), 2)


def _zwischenstand_schreiben(dir: Path, kandidaten: list[Kandidat], alle: list[Kandidat]) -> None:
    """Kandidaten fuer --rescore sichern.

    In der Web-App landet dasselbe auf dem Railway-Volume, damit ein zweiter
    Durchgang keine Neuverarbeitung braucht.
    """
    with (dir / "kandidaten.pkl").open("wb") as f:
        pickle.dump({"kandidaten": kandidaten, "alle": alle}, f)


def zwischenstand_lesen(dir: Path) -> tuple[list[Kandidat], list[Kandidat]]:
    with (dir / "kandidaten.pkl").open("rb") as f:
        d = pickle.load(f)
    return d["kandidaten"], d["alle"]


def verarbeiten(
    lauf: Lauf, melden=print, stufe=None
) -> tuple[list[Kandidat], list[Kandidat], dict]:
    """Stufe 2 und 3. Ohne Modell-Aufruf, damit sie einzeln kalibrierbar sind.

    `melden` bekommt Text fuer die CLI, `stufe` stabile Schluessel fuer die
    Fortschrittsanzeige der Web-App. Zwei Empfaenger, weil sich Anzeigetexte
    aendern duerfen, ohne dass die Zustandslogik mitwandert.
    """
    stufe = stufe or (lambda _: None)
    uhr = Uhr()
    arbeit = lauf.ausgabe / "frames"

    stufe("extrahiert")
    melden("Frames werden extrahiert")
    frames, p_extrakt = extract.extrahieren(
        lauf.video, arbeit, lauf.tiefe, lauf.ueberlaenge, lauf.sprache
    )
    uhr.stempel("extraktion")

    stufe("filtert")
    melden(f"{len(frames)} Frames werden gefiltert")
    kandidaten, alle, p_filter = filtering.filtern(frames, lauf.schaerfe_perzentil)
    uhr.stempel("filter")

    _zwischenstand_schreiben(lauf.ausgabe, kandidaten, alle)

    # Das Transkript entsteht hier und nicht in der Bewertung: Danach ist das
    # Quellvideo weg. Es wandert ins Protokoll und ueberlebt damit auch den
    # zweiten Durchgang, ohne erneut zu kosten.
    transkript_text, p_transkript = None, {"genutzt": False, "grund": "nicht angefordert"}
    if lauf.transkript:
        stufe("transkribiert")
        melden("Tonspur wird ausgewertet")
        transkript_text, p_transkript = transkript_modul.erzeugen(
            lauf.video, p_extrakt.get("dauer_s") or 0.0
        )
        uhr.stempel("transkript")

    protokoll = {
        "video": str(lauf.video),
        "headline": lauf.headline,
        "beschreibung": lauf.beschreibung,
        "tiefe": lauf.tiefe,
        "format": lauf.format,
        "extraktion": p_extrakt,
        "filter": p_filter,
        "transkript": p_transkript,
        "transkript_text": transkript_text,
        "zeiten_s": uhr.zeiten,
    }
    return kandidaten, alle, protokoll


def bewerten_und_waehlen(
    kandidaten: list[Kandidat],
    alle: list[Kandidat],
    lauf: Lauf,
    protokoll: dict,
    ueberspringen: set[str] | None = None,
    melden=print,
    stufe=None,
) -> Ergebnis:
    """Stufe 4 und 5."""
    stufe = stufe or (lambda _: None)
    uhr = Uhr()
    erg = Ergebnis(protokoll=protokoll)

    stufe("bewertet")
    melden(f"{len(kandidaten)} Kandidaten werden bewertet")
    try:
        # Eigener Aufruf fuer die Motivlage: Im Bewertungsaufruf verortet das
        # Modell nachweislich schlampig (Fisch unten links -> "mitte"), weil
        # dort drei Aufgaben um Aufmerksamkeit konkurrieren. Beide Aufrufe
        # brauchen nur die Kandidaten -- sie laufen parallel, die Verortung
        # kostet dadurch keine Wartezeit. Scheitert nur die Verortung, laeuft
        # der Rest weiter -- dann ohne Positionsauskunft.
        with ThreadPoolExecutor(max_workers=1) as nebenher:
            verortung = nebenher.submit(scoring.verorten, kandidaten, lauf)
            roh, verbrauch = scoring.bewerten(
                kandidaten, lauf, protokoll.get("transkript_text")
            )
            try:
                lagen, lagen_verbrauch = verortung.result()
                protokoll["verortung"] = lagen_verbrauch
            except Exception as e:                             # noqa: BLE001
                lagen = {}
                protokoll["verortung"] = {"fehler": str(e)}
        protokoll["bewertung"] = verbrauch
        protokoll["gesamteindruck"] = roh.get("gesamteindruck", "")
        erg.bewertet = scoring.aggregieren(kandidaten, roh, lauf, lagen)
        dauer = protokoll.get("extraktion", {}).get("dauer_s") or 0.0
        erg.auswahl, uebernommen = scoring.auswaehlen(
            erg.bewertet, lauf.anzahl, dauer, roh.get("vorschlag"), ueberspringen,
            motivlage_gewuenscht=lauf.motivlage in config.MOTIVLAGEN,
            lage_prio=lauf.lage_prio,
        )
        protokoll["vorschlag_uebernommen"] = uebernommen
        protokoll["mindestabstand_s"] = round(config.mindestabstand(dauer), 1)
        protokoll["motivlage_wunsch"] = lauf.motivlage
    except scoring.BewertungFehler as e:
        melden(f"Bewertung fehlgeschlagen ({e}) — technischer Rückfall")
        erg.fallback = True
        protokoll["fallback_grund"] = str(e)
        rueckfall = filtering.fallback(alle, lauf.anzahl)
        erg.auswahl = [
            scoring.Bewertet(k, {}, meldungen.text("fallback_begruendung", lauf.sprache), 0.0)
            for k in rueckfall
        ]
    uhr.stempel("bewertung")

    stufe("exportiert")
    melden("Vorschläge werden exportiert")
    ziel = lauf.ausgabe / "vorschlaege"
    # Alte Exporte raeumen: Nach einem Formatwechsel oder Rerank blieben sonst
    # Bilder im vorigen Zuschnitt liegen und der Nutzer laedt das falsche.
    if ziel.exists():
        for veraltet in ziel.glob("*.jpg"):
            veraltet.unlink()
    for rang, b in enumerate(erg.auswahl, 1):
        name = f"{rang}_{b.kandidat.id}_{b.kandidat.zeit:07.2f}s.jpg"
        erg.exporte.append(crop.export(b.kandidat.pfad, lauf.format, ziel / name))

    gewaehlt = {b.kandidat.id for b in erg.auswahl}
    contact.alle_frames(alle, {k.id for k in kandidaten}, lauf.ausgabe / "01_alle_frames.jpg")
    if erg.bewertet:
        contact.kandidaten(erg.bewertet, gewaehlt, lauf.format,
                           lauf.ausgabe / "02_kandidaten.jpg")
    uhr.stempel("export")

    protokoll["zeiten_s"].update(uhr.zeiten)
    protokoll["zeit_gesamt_s"] = round(sum(protokoll["zeiten_s"].values()), 2)
    protokoll["fallback"] = erg.fallback
    protokoll["motivlage_bilanz"] = lage_bilanz(erg.auswahl, lauf.motivlage)
    protokoll["ergebnis"] = [
        {
            "id": b.kandidat.id,
            "zeit": round(b.kandidat.zeit, 2),
            "zeitcode": b.kandidat.zeitcode,
            "gesamt": round(b.gesamt, 2),
            "scores": b.scores,
            "begruendung": b.begruendung,
            "motivlage": b.motivlage,
            "lage_stufe": b.lage_stufe,
        }
        for b in erg.auswahl
    ]
    protokoll["alle_bewertungen"] = [
        {
            "id": b.kandidat.id,
            "zeit": round(b.kandidat.zeit, 2),
            "gesamt": round(b.gesamt, 2),
            "scores": b.scores,
            "begruendung": b.begruendung,
            "motivlage": b.motivlage,
            "motiv_x": round(b.motiv_x, 1),
            "motiv_y": round(b.motiv_y, 1),
            "messwerte": b.kandidat.werte.als_dict(),
        }
        for b in erg.bewertet
    ]

    (lauf.ausgabe / "lauf.json").write_text(
        json.dumps(protokoll, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return erg


def lage_bilanz(auswahl: list[scoring.Bewertet], wunsch: str) -> dict:
    """Wie weit die gewuenschte Motivlage in der Auswahl erfuellt ist.

    Der Nutzer soll erfahren, wenn sein Wunsch nicht aufging -- sonst wirkt
    eine Auswahl wie eine Antwort auf die Frage, die sie gar nicht ist.
    """
    if wunsch not in config.MOTIVLAGEN:
        return {"gewuenscht": "egal"}
    genau = sum(1 for b in auswahl if b.lage_stufe == config.STUFE_GENAU)
    teils = sum(1 for b in auswahl if b.lage_stufe == config.STUFE_RICHTUNG)
    return {
        "gewuenscht": wunsch,
        "genau": genau,
        "teilweise": teils,
        "gesamt": len(auswahl),
        # „naehe": kein genauer Treffer, aber Frames in der verlangten
        # Richtung. Das pauschale „kein Frame zeigt das Motiv unten rechts"
        # verschwieg, dass zwei von drei immerhin rechts lagen.
        "stand": "genau" if genau == len(auswahl)
                 else ("teils" if genau else ("naehe" if teils else "keiner")),
    }


def voll(lauf: Lauf, melden=print) -> Ergebnis:
    kandidaten, alle, protokoll = verarbeiten(lauf, melden)
    return bewerten_und_waehlen(kandidaten, alle, lauf, protokoll, melden=melden)


def erneut_waehlen(
    lauf: Lauf,
    ueberspringen: set[str],
) -> Ergebnis:
    """Neue Auswahl **ohne** Modell-Aufruf und ohne Neuverarbeitung.

    Die Achsen-Scores aller Kandidaten liegen seit dem ersten Durchgang in
    lauf.json. Ein zweiter Durchgang ist damit reine Rechenarbeit: neu ordnen
    unter Ausschluss des bereits Gezeigten, Diversitaetsregel anwenden,
    exportieren. Kosten null.

    Das ist zugleich stabiler als ein zweiter Aufruf: Dreimal dieselbe Anfrage
    ergab fuer denselben Frame 84,8 / 61,3 / 82,4 -- die Modellscores streuen
    zwischen Laeufen erheblich.
    """
    kandidaten, _ = zwischenstand_lesen(lauf.ausgabe)
    protokoll = json.loads((lauf.ausgabe / "lauf.json").read_text(encoding="utf-8"))
    nach_id = {k.id: k for k in kandidaten}

    # Der gespeicherte Gesamtwert ist der reine Qualitaetswert, ohne Zutun des
    # damaligen Wunsches. Die Stufe wird schlicht neu gebildet -- so laesst
    # sich die gewuenschte Lage nachtraeglich aendern, ohne das Modell erneut
    # zu fragen.
    bewertet = []
    for e in protokoll.get("alle_bewertungen", []):
        if e["id"] not in nach_id:
            continue
        lage = e.get("motivlage", "")
        # Laeufe von vor dem Koordinaten-Umbau haben nur die Zelle. Deren
        # Mittelpunkt ist dann der Ersatzpunkt -- die Rangfolge verhaelt sich
        # damit wie die alte Stufenlogik, nur ueber den Abstand ausgedrueckt.
        if "motiv_x" in e:
            x, y = float(e["motiv_x"]), float(e["motiv_y"])
            klar = lage != config.KEIN_MOTIV
        else:
            mitte = config.zellmitte(lage)
            klar = mitte is not None
            x, y = mitte if klar else (50.0, 50.0)
        bewertet.append(scoring.Bewertet(
            kandidat=nach_id[e["id"]],
            scores=e.get("scores", {}),
            begruendung=e.get("begruendung", ""),
            gesamt=e.get("gesamt", 0.0),
            motivlage=lage,
            motiv_x=x,
            motiv_y=y,
            lage_stufe=config.lage_stufe(lauf.motivlage, lage),
            lage_band=config.lage_band(lauf.motivlage, x, y, klar),
            lage_abstand=config.lage_abstand(lauf.motivlage, x, y, klar),
        ))
    bewertet.sort(key=lambda b: -b.gesamt)
    if not bewertet:
        raise ValueError("Für diesen Job liegen keine gespeicherten Bewertungen vor.")

    dauer = protokoll.get("extraktion", {}).get("dauer_s") or 0.0
    auswahl, _ = scoring.auswaehlen(
        bewertet, lauf.anzahl, dauer, vorschlag=None,
        ueberspringen=ueberspringen,
        motivlage_gewuenscht=lauf.motivlage in config.MOTIVLAGEN,
        lage_prio=lauf.lage_prio,
    )

    erg = Ergebnis(auswahl=auswahl, bewertet=bewertet, protokoll=protokoll)
    ziel = lauf.ausgabe / "vorschlaege"
    if ziel.exists():
        for veraltet in ziel.glob("*.jpg"):
            veraltet.unlink()
    for rang, b in enumerate(auswahl, 1):
        name = f"{rang}_{b.kandidat.id}_{b.kandidat.zeit:07.2f}s.jpg"
        erg.exporte.append(crop.export(b.kandidat.pfad, lauf.format, ziel / name))

    protokoll["ergebnis"] = [
        {
            "id": b.kandidat.id,
            "zeit": round(b.kandidat.zeit, 2),
            "zeitcode": b.kandidat.zeitcode,
            "gesamt": round(b.gesamt, 2),
            "scores": b.scores,
            "begruendung": b.begruendung,
            "motivlage": b.motivlage,
            "lage_stufe": b.lage_stufe,
        }
        for b in auswahl
    ]
    protokoll["erneut_gewaehlt"] = protokoll.get("erneut_gewaehlt", 0) + 1
    protokoll["motivlage_wunsch"] = lauf.motivlage
    protokoll["motivlage_bilanz"] = lage_bilanz(auswahl, lauf.motivlage)
    (lauf.ausgabe / "lauf.json").write_text(
        json.dumps(protokoll, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return erg


def erschoepft(ausgabe: Path, gezeigt: set[str], anzahl: int) -> bool:
    """Sind noch genug ungezeigte Kandidaten fuer einen weiteren Durchgang da?"""
    try:
        protokoll = json.loads((ausgabe / "lauf.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    offen = [e for e in protokoll.get("alle_bewertungen", []) if e["id"] not in gezeigt]
    return len(offen) < anzahl
