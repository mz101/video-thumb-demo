"""Prueft, dass ein Deploy auf ein Volume mit aelterem Schema startet.

Anlass: Der erste Railway-Deploy mit den Sprachspalten scheiterte beim Start
mit `no such column: meldung_key`. `CREATE TABLE IF NOT EXISTS` legt bei einer
bestehenden Datenbank nichts an, und getestet worden war nur gegen frische
Volumes -- die Migration fiel dadurch nie auf.

Jede kuenftige Schemaaenderung gehoert hier als weiterer Stand hinein.

    .venv/bin/python -m werkzeug.schema_pruefen
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

#: Die Schemata, die je in Betrieb waren, in ihrer historischen Reihenfolge.
STAENDE: dict[str, str] = {
    "v1 (Objektspeicher, einsprachig)": """
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY, status TEXT NOT NULL, stufe TEXT NOT NULL DEFAULT '',
          fortschritt REAL NOT NULL DEFAULT 0, object_key TEXT NOT NULL,
          quelle TEXT NOT NULL DEFAULT 'upload', headline TEXT NOT NULL,
          beschreibung TEXT NOT NULL DEFAULT '', einstellungen TEXT NOT NULL DEFAULT '{}',
          ergebnis TEXT, meldung TEXT, gezeigt TEXT NOT NULL DEFAULT '[]',
          erstellt REAL NOT NULL, geaendert REAL NOT NULL);
    """,
    "v2 (Upload direkt, einsprachig)": """
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY, status TEXT NOT NULL, stufe TEXT NOT NULL DEFAULT '',
          fortschritt REAL NOT NULL DEFAULT 0, quelle_ref TEXT NOT NULL,
          quelle TEXT NOT NULL DEFAULT 'upload', headline TEXT NOT NULL,
          beschreibung TEXT NOT NULL DEFAULT '', einstellungen TEXT NOT NULL DEFAULT '{}',
          ergebnis TEXT, meldung TEXT, gezeigt TEXT NOT NULL DEFAULT '[]',
          erstellt REAL NOT NULL, geaendert REAL NOT NULL);
    """,
    "leeres Volume (Erstinstallation)": "",
}


def _befuellen(pfad: Path, schema: str) -> None:
    if not schema.strip():
        return
    jetzt = time.time() - 3600
    db = sqlite3.connect(pfad)
    db.executescript(schema)
    spalten = [z[1] for z in db.execute("PRAGMA table_info(jobs)")]
    schluessel = "object_key" if "object_key" in spalten else "quelle_ref"
    db.execute(
        f"INSERT INTO jobs (id,status,stufe,fortschritt,{schluessel},headline,"
        f"erstellt,geaendert) VALUES (?,?,?,?,?,?,?,?)",
        ("alt", "laeuft", "Kandidaten werden bewertet", 0.5, "x.mp4",
         "Alter Job", jetzt, jetzt),
    )
    db.commit()
    db.close()


def pruefen() -> int:
    fehler = 0
    for name, schema in STAENDE.items():
        with tempfile.TemporaryDirectory(prefix="schema-") as tmp:
            import os
            os.environ["DATEN_PFAD"] = tmp
            for modul in [m for m in list(sys.modules) if m.startswith("app.")]:
                del sys.modules[modul]

            _befuellen(Path(tmp) / "loupe.db", schema)
            try:
                from app import db as jobdb
                jobdb.start()
                spalten = jobdb._spalten(jobdb.verbindung(), "jobs")
                fehlend = {"quelle_ref", "sprache", "meldung_key"} - spalten
                if fehlend:
                    raise AssertionError(f"Spalten fehlen: {fehlend}")
                jobdb.anlegen("u", "Nach der Migration", "", {}, sprache="en")
                print(f"  ok   {name}")
            except Exception as e:
                print(f"  FEHL {name}: {type(e).__name__}: {e}")
                fehler += 1
    return fehler


if __name__ == "__main__":
    print("Startet die Anwendung auf jedem je ausgelieferten Schema?")
    anzahl = pruefen()
    print("  alle Stände starten" if not anzahl else f"  {anzahl} Stände scheitern")
    raise SystemExit(1 if anzahl else 0)
