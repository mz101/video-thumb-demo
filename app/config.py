"""Umgebung der Web-Anwendung.

Getrennt von loupe/config.py: Dort stehen Kalibrierwerte, hier steht
Betrieb. Wer an der Auswahlqualitaet dreht, fasst diese Datei nicht an.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

WURZEL = Path(__file__).resolve().parent.parent
load_dotenv(WURZEL / ".env")


def umgebung(name: str, vorgabe: str = "") -> str:
    """Umgebungsvariable lesen und umschliessende Anfuehrungszeichen entfernen.

    python-dotenv streift Quotes ab, `docker run --env-file` nicht. Eine
    .env-Zeile `DO_SPACES_REGION="fra1"` funktioniert dadurch lokal und
    scheitert im Container mit `region_name '"fra1"'`. Der Fehler taucht dann
    erst beim Ablegen des Ergebnisses auf — nach dem bezahlten Modell-Aufruf.
    """
    wert = os.getenv(name, vorgabe).strip()
    if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
        wert = wert[1:-1].strip()
    return wert


# --- Ablage ----------------------------------------------------------------

#: Gemountetes Railway-Volume. Ohne Volume ist das Dateisystem fluechtig und
#: sowohl die Job-Datenbank als auch die Kandidaten fuer den zweiten Durchgang
#: waeren nach jedem Deploy weg.
DATEN = Path(umgebung("DATEN_PFAD", "/data"))
DATENBANK = DATEN / "loupe.db"
JOBS = DATEN / "jobs"
UPLOADS = DATEN / "uploads"

#: Aufbewahrung von Jobs und Kandidaten. Das Quellvideo faellt nicht darunter --
#: es wird direkt nach der Extraktion verworfen, weil es nie wieder gelesen wird.
AUFBEWAHRUNG_TAGE = int(umgebung("AUFBEWAHRUNG_TAGE", "28"))

#: Obergrenze fuer den Upload. Wird beim Anmelden des Uploads geprueft,
#: damit der Nutzer es vor der Uebertragung erfaehrt und nicht danach.
MAX_UPLOAD_BYTE = int(umgebung("MAX_UPLOAD_MB", "2048")) * 1024 * 1024


# --- Anmeldung -------------------------------------------------------------

BENUTZER = umgebung("APP_BENUTZER")
PASSWORT = umgebung("APP_PASSWORT")

#: Signiert das Session-Cookie. Ohne festen Wert werden alle Anmeldungen bei
#: jedem Neustart ungueltig — deshalb in Produktion setzen.
GEHEIMNIS = umgebung("SECRET_KEY") or secrets.token_urlsafe(32)
SITZUNG_TAGE = 14
COOKIE = "loupe_sitzung"

#: Sperre nach Fehlversuchen. Ein gemeinsames Passwort vor einem
#: OpenAI-Budget darf sich nicht beliebig oft durchprobieren lassen: je
#: Absender 5 Fehlversuche im Fenster, danach ist dieser Absender gesperrt,
#: bis der aelteste Versuch aus dem Fenster faellt. Die Gesamtgrenze faengt
#: verteilte Versuche und gefaelschte Absenderadressen ab -- sie sperrt dann
#: alle neuen Anmeldungen; bestehende Sitzungen laufen weiter.
ANMELDUNG_FENSTER_S = 15 * 60
ANMELDUNG_VERSUCHE = 5
ANMELDUNG_VERSUCHE_GESAMT = 50


# --- Upload ----------------------------------------------------------------

#: Das Video geht stueckweise direkt zur Anwendung, nicht ueber Objektspeicher.
#: Railway begrenzt die Requestgroesse nicht, bricht aber nach 5 Minuten ab --
#: deshalb viele kurze Requests statt eines langen. Siehe app/uploads.py.
#:
#: Angefangene und nie beendete Uploads werden nach dieser Frist verworfen.
UPLOAD_VERFALL_STUNDEN = int(umgebung("UPLOAD_VERFALL_STUNDEN", "24"))


# --- Betrieb ---------------------------------------------------------------

#: Ein gleichzeitiger Job. ffmpeg ist CPU-gebunden; zwei parallele Laeufe auf
#: einer geteilten Railway-CPU machen beide langsam, statt einen schnell.
GLEICHZEITIG = int(umgebung("GLEICHZEITIG", "1"))

PORT = int(umgebung("PORT", "8000"))


def pruefe_start() -> list[str]:
    """Fehlende Pflichtangaben melden, statt spaeter im Job zu scheitern."""
    fehlt = []
    if not BENUTZER or not PASSWORT:
        fehlt.append("APP_BENUTZER und APP_PASSWORT (Anmeldung)")
    if not umgebung("OPENAI_API_KEY"):
        fehlt.append("OPENAI_API_KEY (Bewertung)")
    if not DATEN.parent.exists() and not DATEN.exists():
        fehlt.append(f"DATEN_PFAD zeigt auf {DATEN}, dort ist nichts gemountet")
    return fehlt
