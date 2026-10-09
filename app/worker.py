"""Hintergrund-Worker.

Ein Dienst mit Hintergrund-Tasks reicht fuer v1. Erst wenn ein laufender Job
die HTTP-Antworten ausbremst, werden Web und Worker getrennt.

Ein gleichzeitiger Job: ffmpeg ist CPU-gebunden, zwei parallele Laeufe auf
einer geteilten Railway-CPU machen beide langsam statt einen schnell. Wer
wartet, bekommt seine Position angezeigt statt eines stehenden Balkens.
"""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
import time
from pathlib import Path

from loupe import config as kalibrierung
from loupe import extract, pipeline
from loupe.config import Lauf

from . import config, db, quelle, uploads

log = logging.getLogger("loupe.worker")

_warteschlange: queue.Queue[str] = queue.Queue()
_gestartet = False

#: Anteil am Fortschritt je Stufe. Der Balken soll nicht springen, und die
#: Bewertung dauert erfahrungsgemaess laenger als alles andere zusammen.
#:
#: Hier steht nur der Schluessel, der Text in app/i18n.py -- damit die Anzeige
#: der Sprache des Betrachters folgt und nicht der, die beim Start des Jobs
#: gewaehlt war.
STUFEN = {
    "laedt": 0.00,
    "transkribiert": 0.08,
    "extrahiert": 0.16,
    "filtert": 0.36,
    "bewertet": 0.50,
    "exportiert": 0.90,
}


def einreihen(job_id: str) -> None:
    _warteschlange.put(job_id)


def starten() -> None:
    global _gestartet
    if _gestartet:
        return
    _gestartet = True
    for i in range(max(1, config.GLEICHZEITIG)):
        threading.Thread(target=_schleife, name=f"worker-{i}", daemon=True).start()
    threading.Thread(target=_aufraeumschleife, name="aufraeumer", daemon=True).start()

    # Jobs, die beim Neustart in der Warteschlange standen, wieder aufnehmen.
    for job in db.offene():
        einreihen(job.id)


def _schleife() -> None:
    while True:
        job_id = _warteschlange.get()
        try:
            _abarbeiten(job_id)
        except Exception:
            log.exception("Job %s abgebrochen", job_id)
            db.aendern(job_id, status="fehler", stufe="fehler",
                       meldung_key="api_verarbeitung")
        finally:
            _warteschlange.task_done()


def _aufraeumschleife() -> None:
    while True:
        try:
            if entfernt := db.aufraeumen():
                log.info("%d abgelaufene Jobs entfernt", entfernt)
            if verwaist := uploads.aufraeumen(config.UPLOAD_VERFALL_STUNDEN):
                log.info("%d angefangene Uploads entfernt", verwaist)
        except Exception:
            log.exception("Aufräumen fehlgeschlagen")
        time.sleep(6 * 3600)


def _stufe(job_id: str, name: str) -> None:
    db.aendern(job_id, stufe=name, fortschritt=STUFEN.get(name, 0.0))


def _lauf_aus_job(job: db.Job, video: Path) -> Lauf:
    e = job.einstellungen
    return Lauf(
        video=video,
        headline=job.headline,
        beschreibung=job.beschreibung,
        tiefe=e.get("tiefe", "schnell"),
        transkript=e.get("transkript", False),
        sprache=job.sprache,
        motivlage=e.get("motivlage", "egal"),
        lage_prio=e.get("lage_prio", "position"),
        format=e.get("format", "16:9"),
        gesichter_bevorzugen=e.get("gesichter", True),
        textflaeche=e.get("textflaeche", False),
        anzahl=int(e.get("anzahl", 3)),
        schaerfe_perzentil=float(e.get("schaerfe_perzentil", 0.55)),
        ausgabe=job.verzeichnis,
    )


def _ergebnis_zusammenstellen(job: db.Job, erg, lauf: Lauf) -> dict:
    """Die Vorschlaege liegen bereits auf dem Volume.

    Frueher wanderten sie von dort nach Spaces, um per signierter Adresse
    zurueckgeliefert zu werden. Das war ein Umweg: Die App kann sie direkt
    ausliefern, und die Adresse laeuft dann auch nicht nach 24 Stunden ab.
    """
    # Der zweite Durchgang schreibt andere Bilder an dieselben Raenge. Ohne
    # wechselnden Adressbestandteil zeigt der Browser die alten weiter -- er
    # hat sie unter genau dieser Adresse im Speicher.
    stand = int(time.time())

    vorschlaege = []
    for rang, (b, datei) in enumerate(zip(erg.auswahl, erg.exporte), 1):
        vorschlaege.append({
            "id": b.kandidat.id,
            "url": f"/api/jobs/{job.id}/vorschlag/{rang}?stand={stand}",
            "datei": datei.name,
            "zeit": round(b.kandidat.zeit, 2),
            "zeitcode": b.kandidat.zeitcode,
            "gesamt": round(b.gesamt, 1),
            "begruendung": b.begruendung,
            "scores": b.scores,
            "motivlage": b.motivlage,
            # Ob die Lage dem Wunsch *genau* entspricht. Die Oberflaeche soll
            # das nicht aus der Stufe zurueckrechnen muessen.
            "lage_treffer": b.lage_stufe == kalibrierung.STUFE_GENAU,
        })

    p = erg.protokoll

    # Wie viele Kandidaten je Rasterzelle ein Motiv haben. Damit zeigt die
    # Schaltflaeche VOR dem Markieren, wo dieses Video ueberhaupt Material
    # hat -- statt dass man blind waehlt und einen Rueckfall erklaert bekommt.
    dichte: dict[str, int] = {}
    for e in p.get("alle_bewertungen", []):
        zelle = e.get("motivlage", "")
        if zelle in kalibrierung.MOTIVLAGEN:
            dichte[zelle] = dichte.get(zelle, 0) + 1

    return {
        "vorschlaege": vorschlaege,
        "lage_dichte": dichte,
        "format": lauf.format,
        "dauer": p.get("extraktion", {}).get("dauer_s"),
        "fallback": erg.fallback,
        "mindestabstand": p.get("mindestabstand_s"),
        "motivlage": lauf.motivlage,
        "lage_prio": lauf.lage_prio,
        "motivlage_bilanz": p.get("motivlage_bilanz", {}),
        "kandidaten": [
            {"id": b["id"], "zeit": b["zeit"], "gesamt": b["gesamt"]}
            for b in p.get("alle_bewertungen", [])
        ],
        "kennzahlen": {
            "frames": p.get("extraktion", {}).get("frames"),
            "kandidaten": p.get("filter", {}).get("kandidaten"),
            "laufzeit": p.get("zeit_gesamt_s"),
            "entdopplung_gelockert": p.get("filter", {}).get("entdopplung_gelockert"),
            "transkript": bool((p.get("transkript") or {}).get("genutzt")),
        },
    }


def _abarbeiten(job_id: str) -> None:
    job = db.holen(job_id)
    if job is None or job.status not in ("wartet",):
        return

    db.aendern(job_id, status="laeuft")
    _stufe(job_id, "laedt")
    job.verzeichnis.mkdir(parents=True, exist_ok=True)

    # Das Quellvideo lebt nur waehrend der Verarbeitung, in einem
    # TemporaryDirectory. Nach der Extraktion wird es nie wieder gelesen --
    # weder der zweite Durchgang noch ein Formatwechsel fassen es an, beide
    # arbeiten auf den Kandidaten. Es aufzubewahren waeren Hunderte MB je Job
    # ohne jeden Nutzen.
    with tempfile.TemporaryDirectory(prefix="loupe-") as tmp:
        try:
            if job.quelle == "url":
                video = quelle.laden(job.quelle_ref, Path(tmp) / "quelle")
            else:
                upload = uploads.lesen(job.quelle_ref)
                video = uploads.zusammensetzen(
                    job.quelle_ref, Path(tmp) / upload.dateiname
                )
        except (quelle.QuellFehler, uploads.UploadFehler) as e:
            db.aendern(job_id, status="fehler", stufe="fehler", meldung=str(e))
            return
        finally:
            # Die Stuecke werden nicht mehr gebraucht, sobald sie
            # zusammengesetzt sind -- oder wenn es schiefging.
            if job.quelle == "upload":
                uploads.verwerfen(job.quelle_ref)

        lauf = _lauf_aus_job(job, video)
        still = lambda _: None                                    # noqa: E731
        stufe = lambda name: _stufe(job_id, name)                 # noqa: E731

        try:
            kandidaten, alle, protokoll = pipeline.verarbeiten(
                lauf, melden=still, stufe=stufe
            )
            erg = pipeline.bewerten_und_waehlen(
                kandidaten, alle, lauf, protokoll, melden=still, stufe=stufe
            )
        except extract.DauerFehler as e:
            db.aendern(job_id, status="fehler", stufe="fehler", meldung=str(e))
            return
        except extract.ExtraktFehler as e:
            db.aendern(job_id, status="fehler", stufe="fehler", meldung=str(e))
            return

        ergebnis = _ergebnis_zusammenstellen(job, erg, lauf)

    db.aendern(
        job_id, status="fertig", stufe="fertig", fortschritt=1.0,
        ergebnis=ergebnis,
        gezeigt=[v["id"] for v in ergebnis["vorschlaege"]],
    )


def erneut_waehlen(job: db.Job, motivlage: str | None = None,
                   lage_prio: str | None = None) -> dict:
    """Zweiter Durchgang. Kein Modell-Aufruf, keine Neuverarbeitung.

    Zwei Anlaesse, die sich unterscheiden muessen:

    * „Drei neue Vorschlaege" -- das bereits Gezeigte wird ausgeschlossen.
    * Geaenderte Motivlage oder Prioritaet -- dann soll die *beste* Auswahl
      fuer die neue Regel kommen, auch wenn sie schon einmal zu sehen war.
      Etwas auszuschliessen waere hier falsch.
    """
    lauf = _lauf_aus_job(job, job.verzeichnis / "unbenutzt")
    gewechselt = (motivlage is not None and motivlage != lauf.motivlage) or                  (lage_prio is not None and lage_prio != lauf.lage_prio)
    neu = dict(job.einstellungen)
    if motivlage is not None:
        lauf.motivlage = neu["motivlage"] = motivlage
    if lage_prio is not None:
        lauf.lage_prio = neu["lage_prio"] = lage_prio
    if neu != job.einstellungen:
        db.aendern(job.id, einstellungen=neu)

    gezeigt = set() if gewechselt else set(job.gezeigt)

    if gezeigt and pipeline.erschoepft(job.verzeichnis, gezeigt, lauf.anzahl):
        gezeigt = set()  # Von vorn, statt mit zu wenigen Vorschlaegen zu enden.

    erg = pipeline.erneut_waehlen(lauf, gezeigt)
    ergebnis = _ergebnis_zusammenstellen(job, erg, lauf)
    ergebnis["erneut"] = True
    ergebnis["durchlauf_erschoepft"] = not gezeigt

    db.aendern(
        job.id, ergebnis=ergebnis, status="fertig", stufe="fertig",
        fortschritt=1.0,
        gezeigt=sorted(gezeigt | {v["id"] for v in ergebnis["vorschlaege"]}),
    )
    return ergebnis
