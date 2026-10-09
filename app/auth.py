"""Anmeldung mit Name und Passwort.

Keine Nutzerkonten -- das steht ausdruecklich nicht im Scope. Das hier ist ein
Zugangsschutz: Die Anwendung liegt oeffentlich auf Railway mit einem
OpenAI-Schluessel dahinter, und ohne Schranke kann jeder, der die Adresse
kennt, das Budget verbrauchen.
"""

from __future__ import annotations

import hmac
import math
import threading
import time
from collections import deque

from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer

from . import config

_serialisierer = URLSafeTimedSerializer(config.GEHEIMNIS, salt="loupe-sitzung")


# --- Sperre nach Fehlversuchen ---------------------------------------------
#
# Im Speicher, nicht in der Datenbank: Es laeuft genau ein Prozess (siehe
# Dockerfile), und ein Neustart, der die Zaehler leert, ist hinnehmbar.

_sperre = threading.Lock()
_je_absender: dict[str, deque[float]] = {}
_gesamt: deque[float] = deque()


def absender(request: Request) -> str:
    """Adresse des Anfragenden.

    Hinter Railways Proxy steht der Client im X-Forwarded-For. Der Proxy haengt
    an, also zaehlt der letzte Eintrag -- die davor kann der Client selbst
    mitschicken. Wer trotzdem faelscht, laeuft in die Gesamtgrenze.
    """
    weitergeleitet = request.headers.get("x-forwarded-for", "")
    if weitergeleitet:
        return weitergeleitet.split(",")[-1].strip()
    return request.client.host if request.client else "unbekannt"


def _ausduennen(versuche: deque[float], jetzt: float) -> None:
    while versuche and versuche[0] <= jetzt - config.ANMELDUNG_FENSTER_S:
        versuche.popleft()


def gesperrt(wer: str) -> int:
    """Verbleibende Sperrzeit in Sekunden, 0 wenn eine Anmeldung erlaubt ist."""
    jetzt = time.time()
    with _sperre:
        _ausduennen(_gesamt, jetzt)
        eigene = _je_absender.get(wer)
        if eigene is not None:
            _ausduennen(eigene, jetzt)
            if not eigene:
                del _je_absender[wer]
                eigene = None
        warten = 0.0
        if len(_gesamt) >= config.ANMELDUNG_VERSUCHE_GESAMT:
            warten = _gesamt[0] + config.ANMELDUNG_FENSTER_S - jetzt
        if eigene and len(eigene) >= config.ANMELDUNG_VERSUCHE:
            warten = max(warten, eigene[0] + config.ANMELDUNG_FENSTER_S - jetzt)
    return math.ceil(warten)


def fehlschlag(wer: str) -> None:
    jetzt = time.time()
    with _sperre:
        _je_absender.setdefault(wer, deque()).append(jetzt)
        _gesamt.append(jetzt)


def erfolg(wer: str) -> None:
    """Nach gelungener Anmeldung zaehlen die eigenen Fehlversuche nicht mehr."""
    with _sperre:
        _je_absender.pop(wer, None)


def pruefe(benutzer: str, passwort: str) -> bool:
    """Vergleich in konstanter Zeit, damit sich nichts erraten laesst."""
    if not config.BENUTZER or not config.PASSWORT:
        return False
    return (
        hmac.compare_digest(benutzer.strip(), config.BENUTZER)
        and hmac.compare_digest(passwort, config.PASSWORT)
    )


def ausstellen(benutzer: str) -> str:
    return _serialisierer.dumps({"b": benutzer, "t": int(time.time())})


def angemeldet(request: Request) -> str | None:
    keks = request.cookies.get(config.COOKIE)
    if not keks:
        return None
    try:
        daten = _serialisierer.loads(keks, max_age=config.SITZUNG_TAGE * 86400)
    except BadSignature:
        return None
    return daten.get("b")


def cookie_setzen(antwort, wert: str, sicher: bool) -> None:
    antwort.set_cookie(
        config.COOKIE, wert,
        max_age=config.SITZUNG_TAGE * 86400,
        httponly=True,
        samesite="lax",
        secure=sicher,
        path="/",
    )


def cookie_loeschen(antwort) -> None:
    antwort.delete_cookie(config.COOKIE, path="/")
