"""Job-Zustand in SQLite auf dem gemounteten Volume.

Eine echte Datenbank lohnt in v1 nicht. Zwei Dinge sind trotzdem noetig:
WAL, weil der Worker-Thread schreibt waehrend HTTP-Anfragen lesen, und ein
Volume, weil das Container-Dateisystem fluechtig ist.
"""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config

_lokal = threading.local()
_schreibsperre = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  status        TEXT NOT NULL,          -- wartet|laeuft|fertig|fehler
  stufe         TEXT NOT NULL DEFAULT 'wartet',  -- Schluessel, kein Text:
                                                 -- uebersetzt wird beim Ausliefern
  fortschritt   REAL NOT NULL DEFAULT 0,
  quelle_ref    TEXT NOT NULL,
  quelle        TEXT NOT NULL DEFAULT 'upload',   -- upload|url
  sprache       TEXT NOT NULL DEFAULT 'de',
  headline      TEXT NOT NULL,
  beschreibung  TEXT NOT NULL DEFAULT '',
  einstellungen TEXT NOT NULL DEFAULT '{}',
  ergebnis      TEXT,
  meldung       TEXT,
  meldung_key   TEXT,
  gezeigt       TEXT NOT NULL DEFAULT '[]',
  erstellt      REAL NOT NULL,
  geaendert     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_erstellt ON jobs(erstellt);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
"""


#: Die Datenbank hiess bis zur Umbenennung sichtung.db. Sie liegt auf dem
#: Volume und ueberlebt Deploys -- ohne diesen Schritt faende die Anwendung
#: nach der Umbenennung eine leere Datenbank vor und alle Jobs waeren fort.
ALTE_NAMEN = ("sichtung.db",)


def _datei_uebernehmen() -> str | None:
    if config.DATENBANK.exists():
        return None
    for alt in ALTE_NAMEN:
        quelle = config.DATEN / alt
        if not quelle.exists():
            continue
        for endung in ("", "-wal", "-shm"):      # WAL-Begleitdateien mitnehmen
            begleiter = config.DATEN / f"{alt}{endung}"
            if begleiter.exists():
                begleiter.rename(config.DATEN / f"{config.DATENBANK.name}{endung}")
        return alt
    return None


def verbindung() -> sqlite3.Connection:
    if not hasattr(_lokal, "db"):
        config.DATEN.mkdir(parents=True, exist_ok=True)
        if (alt := _datei_uebernehmen()):
            logging.getLogger("loupe.db").info(
                "Datenbank übernommen: %s → %s", alt, config.DATENBANK.name
            )
        db = sqlite3.connect(config.DATENBANK, timeout=30, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=NORMAL")
        _lokal.db = db
    return _lokal.db


#: Spalten, die im Lauf der Entwicklung dazugekommen sind, mit ihrer
#: Definition. `CREATE TABLE IF NOT EXISTS` legt bei einer **bestehenden**
#: Datenbank nichts an -- ein Deploy auf ein Volume mit aelterem Schema
#: scheiterte daran beim Start.
NACHGEREICHT: dict[str, str] = {
    "sprache": "TEXT NOT NULL DEFAULT 'de'",
    "meldung_key": "TEXT",
}

#: Umbenennungen, alt -> neu.
UMBENANNT: dict[str, str] = {
    "object_key": "quelle_ref",
}

#: Gueltige Werte fuer `stufe`. Frueher stand dort Anzeigetext, heute ein
#: Schluessel; alte Zeilen wuerden sonst als „stufe_Analyse fertig" auftauchen.
STUFEN_SCHLUESSEL = {
    "wartet", "laedt", "transkribiert", "extrahiert", "filtert",
    "bewertet", "exportiert", "fertig", "fehler",
}


def _spalten(db: sqlite3.Connection, tabelle: str) -> set[str]:
    return {z["name"] for z in db.execute(f"PRAGMA table_info({tabelle})")}


def _migrieren(db: sqlite3.Connection) -> list[str]:
    """Bestehende Datenbank auf den aktuellen Stand bringen.

    Introspektion statt Versionszaehler: So ist es gleichgueltig, von welchem
    Stand aus migriert wird, und ein zweiter Aufruf tut nichts.
    """
    vorhanden = _spalten(db, "jobs")
    if not vorhanden:                       # Tabelle gibt es noch nicht
        return []

    getan: list[str] = []

    for alt, neu in UMBENANNT.items():
        if alt in vorhanden and neu not in vorhanden:
            db.execute(f"ALTER TABLE jobs RENAME COLUMN {alt} TO {neu}")
            getan.append(f"{alt} → {neu}")
            vorhanden = _spalten(db, "jobs")

    for name, definition in NACHGEREICHT.items():
        if name not in vorhanden:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            getan.append(f"+{name}")

    # Alte Anzeigetexte in `stufe` durch Schluessel ersetzen.
    platzhalter = ",".join("?" * len(STUFEN_SCHLUESSEL))
    veraltet = db.execute(
        f"SELECT COUNT(*) AS n FROM jobs WHERE stufe NOT IN ({platzhalter})",
        tuple(STUFEN_SCHLUESSEL),
    ).fetchone()["n"]
    if veraltet:
        db.execute(
            f"UPDATE jobs SET stufe = CASE status WHEN 'fertig' THEN 'fertig' "
            f"ELSE 'fehler' END WHERE stufe NOT IN ({platzhalter})",
            tuple(STUFEN_SCHLUESSEL),
        )
        getan.append(f"{veraltet}× Stufe normalisiert")

    if getan:
        db.commit()
    return getan


def start() -> None:
    config.JOBS.mkdir(parents=True, exist_ok=True)
    db = verbindung()
    db.executescript(SCHEMA)          # nur beim ersten Start wirksam
    db.commit()
    if getan := _migrieren(db):       # danach: bestehendes Schema nachziehen
        logging.getLogger("loupe.db").info(
            "Datenbank migriert: %s", ", ".join(getan)
        )
    # Jobs, die beim letzten Herunterfahren mitten im Lauf waren, sind tot.
    with _schreibsperre:
        db.execute(
            "UPDATE jobs SET status='fehler', stufe='fehler', meldung_key='api_neustart' "
            "WHERE status IN ('laeuft','wartet')"
        )
        db.commit()


@dataclass
class Job:
    id: str
    status: str
    stufe: str
    fortschritt: float
    quelle_ref: str
    quelle: str
    sprache: str
    headline: str
    beschreibung: str
    einstellungen: dict
    ergebnis: dict | None
    meldung: str | None
    meldung_key: str | None
    gezeigt: list[str]
    erstellt: float
    geaendert: float

    @property
    def verzeichnis(self) -> Path:
        return config.JOBS / self.id

    def als_antwort(self) -> dict[str, Any]:
        d = {
            "job_id": self.id,
            "status": self.status,
            "stage_key": self.stufe,
            "progress": round(self.fortschritt, 3),
        }
        if self.meldung:
            d["message"] = self.meldung
        if self.meldung_key:
            d["message_key"] = self.meldung_key
        if self.status == "fertig" and self.ergebnis:
            d["results"] = self.ergebnis
        return d


def _zu_job(zeile: sqlite3.Row) -> Job:
    return Job(
        id=zeile["id"],
        status=zeile["status"],
        stufe=zeile["stufe"],
        fortschritt=zeile["fortschritt"],
        quelle_ref=zeile["quelle_ref"],
        quelle=zeile["quelle"],
        sprache=zeile["sprache"],
        headline=zeile["headline"],
        beschreibung=zeile["beschreibung"],
        einstellungen=json.loads(zeile["einstellungen"]),
        ergebnis=json.loads(zeile["ergebnis"]) if zeile["ergebnis"] else None,
        meldung=zeile["meldung"],
        meldung_key=zeile["meldung_key"],
        gezeigt=json.loads(zeile["gezeigt"]),
        erstellt=zeile["erstellt"],
        geaendert=zeile["geaendert"],
    )


def anlegen(quelle_ref: str, headline: str, beschreibung: str,
            einstellungen: dict, quelle: str = "upload",
            sprache: str = "de") -> Job:
    job_id = uuid.uuid4().hex[:16]
    jetzt = time.time()
    with _schreibsperre:
        verbindung().execute(
            "INSERT INTO jobs (id,status,stufe,fortschritt,quelle_ref,quelle,sprache,"
            "headline,beschreibung,einstellungen,erstellt,geaendert) "
            "VALUES (?,'wartet','wartet',0,?,?,?,?,?,?,?,?)",
            (job_id, quelle_ref, quelle, sprache, headline, beschreibung,
             json.dumps(einstellungen), jetzt, jetzt),
        )
        verbindung().commit()
    return holen(job_id)


def holen(job_id: str) -> Job | None:
    zeile = verbindung().execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _zu_job(zeile) if zeile else None


def aendern(job_id: str, **felder: Any) -> None:
    if not felder:
        return
    for name in ("einstellungen", "ergebnis", "gezeigt"):
        if name in felder and not isinstance(felder[name], (str, type(None))):
            felder[name] = json.dumps(felder[name], ensure_ascii=False)
    felder["geaendert"] = time.time()
    satz = ", ".join(f"{k}=?" for k in felder)
    with _schreibsperre:
        verbindung().execute(
            f"UPDATE jobs SET {satz} WHERE id=?", (*felder.values(), job_id)
        )
        verbindung().commit()


def offene() -> list[Job]:
    zeilen = verbindung().execute(
        "SELECT * FROM jobs WHERE status='wartet' ORDER BY erstellt"
    ).fetchall()
    return [_zu_job(z) for z in zeilen]


def verlauf(grenze: int = 24) -> list[Job]:
    """Fertige Jobs, neueste zuerst. Grundlage fuer den Verlauf.

    Nur `fertig`: Ein abgebrochener Job hat nichts zu zeigen, und der Verlauf
    soll zum Wiederfinden dienen, nicht zum Nachhalten von Fehlversuchen.
    """
    zeilen = verbindung().execute(
        "SELECT * FROM jobs WHERE status='fertig' ORDER BY erstellt DESC LIMIT ?",
        (max(1, min(grenze, 100)),),
    ).fetchall()
    return [_zu_job(z) for z in zeilen]


def warteposition(job_id: str) -> int:
    """Nullbasiert: 0 heisst, der Job ist als naechster dran."""
    zeilen = verbindung().execute(
        "SELECT id FROM jobs WHERE status='wartet' ORDER BY erstellt"
    ).fetchall()
    for i, z in enumerate(zeilen):
        if z["id"] == job_id:
            return i
    return 0


def aufraeumen() -> int:
    """Abgelaufene Jobs entfernen. Gibt die Anzahl zurueck.

    Loescht das Volume-Verzeichnis gemeinsam mit dem Datensatz. Seit der
    Abloesung des Objektspeichers gibt es nichts mehr, was ausserhalb liegen
    und verwaisen koennte -- und das Quellvideo wird ohnehin direkt nach der
    Extraktion verworfen, statt die Aufbewahrungsfrist abzusitzen.
    """
    grenze = time.time() - config.AUFBEWAHRUNG_TAGE * 86400
    zeilen = verbindung().execute(
        "SELECT id FROM jobs WHERE erstellt < ?", (grenze,)
    ).fetchall()

    for zeile in zeilen:
        shutil.rmtree(config.JOBS / zeile["id"], ignore_errors=True)

    if zeilen:
        with _schreibsperre:
            verbindung().execute("DELETE FROM jobs WHERE erstellt < ?", (grenze,))
            verbindung().commit()
    return len(zeilen)
