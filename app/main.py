"""HTTP-Schnittstelle.

Endpunkte:

    POST /api/uploads          → { upload_id, teilgroesse }
    PUT  /api/uploads/{id}/{n}  Stück hochladen
    POST /api/jobs             → { job_id }
    GET  /api/jobs/{id}        → { status, stage, progress, results? }
    POST /api/jobs/{id}/rerank → { job_id }

Dazu die Anmeldung und die Auslieferung der Oberflaeche.
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from loupe import config as kalibrierung

from . import auth, config, db, i18n, quelle, uploads, worker

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("loupe")

HIER = Path(__file__).resolve().parent

#: Versionsmarke fuer Stylesheet und Skript. Ohne sie laeuft nach einem Deploy
#: altes JavaScript gegen eine neue Schnittstelle -- der Browser haelt die
#: Dateien unter unveraenderter Adresse fest. Aus den Aenderungszeiten der
#: Dateien, damit sie sich nur bewegt, wenn sich wirklich etwas geaendert hat.
def _stand_statisch() -> str:
    zeiten = [p.stat().st_mtime for p in (HIER / "static").glob("*")]
    return str(int(max(zeiten))) if zeiten else "0"


STAND = _stand_statisch()
app = FastAPI(title="Loupe", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=HIER / "static"), name="static")
vorlagen = Jinja2Templates(directory=str(HIER / "vorlagen"))


@app.on_event("startup")
def start() -> None:
    fehlt = config.pruefe_start()
    if fehlt:
        log.warning("Unvollständige Konfiguration: %s", "; ".join(fehlt))
    db.start()
    worker.starten()
    log.info("Loupe bereit, Daten unter %s", config.DATEN)


# --- Anmeldung -------------------------------------------------------------

def _sicher(request: Request) -> bool:
    return request.url.scheme == "https" or \
        request.headers.get("x-forwarded-proto") == "https"


def sprache(request: Request) -> str:
    return i18n.sprache_aus(request)


def uebersetzer(request: Request) -> i18n.Uebersetzer:
    return i18n.Uebersetzer(i18n.sprache_aus(request))


def fehler(request: Request, code: int, schluessel: str, **werte) -> HTTPException:
    """HTTP-Fehler in der Sprache des Anfragenden."""
    return HTTPException(status_code=code,
                         detail=i18n.text(schluessel, i18n.sprache_aus(request), **werte))


def erforderlich(request: Request) -> str:
    benutzer = auth.angemeldet(request)
    if not benutzer:
        raise fehler(request, 401, "api_nicht_angemeldet")
    return benutzer


@app.get("/anmelden", response_class=HTMLResponse)
def anmeldeseite(request: Request, fehler: str = ""):
    if auth.angemeldet(request):
        return RedirectResponse("/", status_code=303)
    return vorlagen.TemplateResponse(request, "anmelden.html", {
        "t": uebersetzer(request), "sprache": sprache(request),
        "sprachen": i18n.SPRACHEN, "fehler": fehler, "stand": STAND,
    })


def _anmeldung_abgelehnt(request: Request, meldung: str, code: int,
                         kopf: dict[str, str] | None = None):
    return vorlagen.TemplateResponse(
        request, "anmelden.html",
        {"t": uebersetzer(request), "sprache": sprache(request),
         "sprachen": i18n.SPRACHEN, "stand": STAND, "fehler": meldung},
        status_code=code, headers=kopf,
    )


@app.post("/anmelden")
def anmelden(request: Request, benutzer: str = Form(""), passwort: str = Form("")):
    wer = auth.absender(request)
    # Vor der Passwortpruefung: Waehrend der Sperre darf auch ein richtiges
    # Passwort nichts verraten, sonst liefe das Durchprobieren einfach weiter.
    warten = auth.gesperrt(wer)
    if warten:
        log.warning("Anmeldung gesperrt fuer %s, noch %d s", wer, warten)
        minuten = math.ceil(warten / 60)
        return _anmeldung_abgelehnt(
            request, i18n.text("anmeldung_gesperrt", sprache(request), minuten=minuten),
            429, {"Retry-After": str(warten)},
        )
    if not auth.pruefe(benutzer, passwort):
        auth.fehlschlag(wer)
        return _anmeldung_abgelehnt(
            request, i18n.text("anmeldung_falsch", sprache(request)), 401)
    auth.erfolg(wer)
    antwort = RedirectResponse("/", status_code=303)
    auth.cookie_setzen(antwort, auth.ausstellen(benutzer), _sicher(request))
    return antwort


@app.post("/abmelden")
def abmelden():
    antwort = RedirectResponse("/anmelden", status_code=303)
    auth.cookie_loeschen(antwort)
    return antwort


@app.get("/sprache/{code}")
def sprache_waehlen(code: str, request: Request):
    """Sprache umschalten und dorthin zurueck, wo man war.

    Am Cookie, nicht am Pfad: Die Adresse eines Jobs soll in beiden Sprachen
    dieselbe sein.
    """
    ziel = request.headers.get("referer") or "/"
    if not ziel.startswith(str(request.base_url).rstrip("/")):
        ziel = "/"                      # keine fremden Weiterleitungsziele
    antwort = RedirectResponse(ziel, status_code=303)
    if code in i18n.SPRACHEN:
        antwort.set_cookie(i18n.COOKIE, code, max_age=365 * 86400,
                           samesite="lax", path="/")
    return antwort


@app.get("/", response_class=HTMLResponse)
def oberflaeche(request: Request):
    if not auth.angemeldet(request):
        return RedirectResponse("/anmelden", status_code=303)
    s = sprache(request)
    return vorlagen.TemplateResponse(request, "app.html", {
        "t": i18n.Uebersetzer(s),
        "sprache": s,
        "sprachen": i18n.SPRACHEN,
        "katalog": i18n.katalog_json(s),
        "stand": STAND,
        "formate": list(kalibrierung.FORMATE),
        "motivlagen": list(kalibrierung.MOTIVLAGEN),
        "max_mb": config.MAX_UPLOAD_BYTE // (1024 * 1024),
        "max_minuten": int(kalibrierung.DAUER_MAX_S // 60),
        "schaerfe_vorgabe": kalibrierung.SCHAERFE_PERZENTIL,
    })


@app.get("/gesundheit")
def gesundheit():
    fehlt = config.pruefe_start()
    return {
        "status": "ok" if not fehlt else "unvollständig",
        "fehlende_konfiguration": fehlt,
        "ablage": str(config.DATEN),
        "ablage_beschreibbar": os.access(config.DATEN, os.W_OK),
    }


#: Fehler sagen, was passiert ist und was jetzt zu tun ist -- ohne
#: Fachbegriffe aus dem Maschinenraum. Pydantic meldet auf Englisch und in
#: seiner eigenen Sprache; das wird hier uebersetzt, bevor es die Oberflaeche
#: erreicht.
#: Headline und Beschreibung sind freiwillig -- zu lang bleibt trotzdem ein
#: Fehler, fehlend nicht mehr.
_FELDER = {
    "headline": "api_headline_lang",
    "beschreibung": "api_beschreibung_lang",
}


@app.exception_handler(RequestValidationError)
def eingabe_fehler(request: Request, ausnahme: RequestValidationError):
    """Fehler sagen, was passiert ist und was jetzt zu tun ist.

    Pydantic meldet auf Englisch und in seiner eigenen Sprache; das wird hier
    uebersetzt, bevor es die Oberflaeche erreicht.
    """
    s = i18n.sprache_aus(request)
    for eintrag in ausnahme.errors():
        feld = str(eintrag["loc"][-1])
        if feld in _FELDER and "too_long" in eintrag["type"]:
            return JSONResponse({"detail": i18n.text(_FELDER[feld], s)}, status_code=422)
    return JSONResponse({"detail": i18n.text("api_eingabe", s)}, status_code=422)


# --- API -------------------------------------------------------------------

class UploadAnfrage(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    size: int


@app.post("/api/uploads")
def upload_anfordern(anfrage: UploadAnfrage, request: Request,
                     _: str = Depends(erforderlich)):
    """Upload anmelden. Das Video kommt anschliessend stueckweise.

    Frueher lieferte dieser Endpunkt eine signierte S3-Adresse, damit der
    Upload am Backend vorbeigeht. Das Konzept begruendete das mit Speicher-
    und Request-Limits; beides traegt nicht: Stuecke werden direkt auf die
    Platte geschrieben, und Railway begrenzt nicht die Groesse, sondern die
    Dauer eines Requests. Viele kurze Requests loesen das ohne Objektspeicher.
    """
    try:
        upload = uploads.anlegen(anfrage.filename, anfrage.size)
    except uploads.UploadFehler as e:
        raise fehler(request, 413, "api_zu_gross",
                     mb=config.MAX_UPLOAD_BYTE // (1024 * 1024)) from e
    return {"upload_id": upload.kennung, "teilgroesse": uploads.TEILGROESSE}


@app.put("/api/uploads/{upload_id}/{teil}")
async def upload_teil(upload_id: str, teil: int, request: Request,
                      _: str = Depends(erforderlich)):
    daten = await request.body()
    try:
        empfangen = uploads.teil_schreiben(upload_id, teil, daten)
    except uploads.UploadFehler as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"empfangen": empfangen}


class JobAnfrage(BaseModel):
    upload_id: str = ""
    quell_url: str = ""
    headline: str = Field(default="", max_length=120)
    beschreibung: str = Field(default="", max_length=500)
    tiefe: str = "schnell"
    format: str = "16:9"
    gesichter: bool = True
    textflaeche: bool = False
    anzahl: int = 3
    transkript: bool = False
    motivlage: str = "egal"
    lage_prio: str = "position"
    schaerfe_perzentil: float = kalibrierung.SCHAERFE_PERZENTIL


@app.post("/api/jobs")
def job_starten(anfrage: JobAnfrage, request: Request,
                _: str = Depends(erforderlich)):
    if bool(anfrage.upload_id) == bool(anfrage.quell_url):
        raise fehler(request, 400, "api_beides")
    if anfrage.format not in kalibrierung.FORMATE:
        raise fehler(request, 400, "api_format")
    if anfrage.anzahl not in (3, 5):
        raise fehler(request, 400, "api_anzahl")

    if anfrage.quell_url:
        art, referenz = "url", anfrage.quell_url.strip()
        try:
            quelle.pruefen(referenz)
        except quelle.QuellFehler as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    else:
        art, referenz = "upload", anfrage.upload_id
        try:
            if not uploads.vollstaendig(referenz):
                raise fehler(request, 400, "api_upload_unvollstaendig")
        except uploads.UploadFehler as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    job = db.anlegen(
        quelle_ref=referenz,
        headline=anfrage.headline.strip(),
        beschreibung=anfrage.beschreibung.strip(),
        quelle=art,
        sprache=sprache(request),
        einstellungen={
            "tiefe": anfrage.tiefe if anfrage.tiefe in ("schnell", "gruendlich") else "schnell",
            "format": anfrage.format,
            "gesichter": anfrage.gesichter,
            "textflaeche": anfrage.textflaeche,
            "anzahl": anfrage.anzahl,
            "transkript": anfrage.transkript,
            "motivlage": anfrage.motivlage
            if anfrage.motivlage in kalibrierung.MOTIVLAGEN else "egal",
            "lage_prio": anfrage.lage_prio
            if anfrage.lage_prio in ("position", "qualitaet") else "position",
            "schaerfe_perzentil": max(0.1, min(0.95, anfrage.schaerfe_perzentil)),
        },
    )
    worker.einreihen(job.id)
    return {"job_id": job.id}


@app.get("/api/verlauf")
def verlauf(request: Request, grenze: int = 24, _: str = Depends(erforderlich)):
    """Frueher gelaufene Analysen, damit man ein Ergebnis wiederfindet.

    Liefert nur, was zum Anzeigen der Zeile noetig ist -- nicht die vollen
    Ergebnisse. Die holt die Oberflaeche erst beim Anklicken nach.
    """
    eintraege = []
    for job in db.verlauf(grenze):
        vorschlaege = (job.ergebnis or {}).get("vorschlaege", [])
        if not vorschlaege:
            continue
        eintraege.append({
            "job_id": job.id,
            "headline": job.headline,
            "erstellt": job.erstellt,
            "format": (job.ergebnis or {}).get("format", ""),
            "anzahl": len(vorschlaege),
            "bild": vorschlaege[0]["url"],
        })
    return {"eintraege": eintraege}


@app.get("/api/jobs/{job_id}")
def job_abfragen(job_id: str, request: Request, _: str = Depends(erforderlich)):
    job = db.holen(job_id)
    if job is None:
        raise fehler(request, 404, "api_job_weg")

    s = sprache(request)
    antwort = job.als_antwort()

    # Stufen und Fehler werden erst hier uebersetzt, in der Sprache des
    # Betrachters -- nicht in der, die beim Start des Jobs gewaehlt war.
    if job.status == "wartet":
        position = db.warteposition(job_id)
        antwort["stage"] = (i18n.text("stufe_wartet", s) if position == 0
                            else i18n.text("stufe_position", s, n=position + 1))
    else:
        antwort["stage"] = i18n.text(f"stufe_{job.stufe}", s)
    if job.meldung_key:
        antwort["message"] = i18n.text(job.meldung_key, s)
    return antwort


@app.get("/api/jobs/{job_id}/vorschlag/{rang}")
def vorschlag_ausliefern(job_id: str, rang: int, request: Request, laden: int = 0,
                         stand: int = 0, _: str = Depends(erforderlich)):
    """Ein fertiges Thumbnail vom Volume ausliefern.

    Ersetzt die signierte S3-Adresse. Die Datei liegt ohnehin auf dem Volume;
    sie erst hochzuladen, um sie dann von dort zu holen, war ein Umweg -- und
    die Adresse lief nach 24 Stunden ab, diese nicht.
    """
    job = db.holen(job_id)
    if job is None or not job.ergebnis:
        raise fehler(request, 404, "api_job_weg")

    vorschlaege = job.ergebnis.get("vorschlaege", [])
    if not 1 <= rang <= len(vorschlaege):
        raise fehler(request, 404, "api_vorschlag_weg")

    datei = (job.verzeichnis / "vorschlaege" / vorschlaege[rang - 1]["datei"]).resolve()
    # Kein Ausbruch aus dem Job-Verzeichnis, egal was in der Datenbank steht.
    if not datei.is_file() or job.verzeichnis.resolve() not in datei.parents:
        raise fehler(request, 410, "api_bild_abgelaufen")

    # Mit `stand` ist die Adresse eindeutig: Ein zweiter Durchgang vergibt
    # einen neuen Stand, der Inhalt unter dieser Adresse aendert sich also
    # nie. Dann darf der Browser sie behalten -- sonst laedt der Verlauf bei
    # jedem Blick alle Vorschaubilder neu.
    #
    # Ohne `stand` -- etwa bei einer von Hand eingegebenen Adresse -- kann der
    # Inhalt wechseln, und Zwischenspeichern waere falsch.
    kopf = {"Cache-Control": "private, max-age=604800, immutable" if stand
            else "no-store"}
    if laden:
        name = f"thumbnail_{vorschlaege[rang - 1]['zeitcode'].replace(':', '-')}.jpg"
        kopf["Content-Disposition"] = f'attachment; filename="{name}"'
    return FileResponse(datei, media_type="image/jpeg", headers=kopf)


class RerankAnfrage(BaseModel):
    motivlage: str | None = None
    lage_prio: str | None = None


@app.post("/api/jobs/{job_id}/rerank")
def job_erneut(job_id: str, request: Request, anfrage: RerankAnfrage | None = None,
               _: str = Depends(erforderlich)):
    job = db.holen(job_id)
    if job is None:
        raise fehler(request, 404, "api_job_weg")
    if job.status != "fertig":
        raise fehler(request, 409, "api_laeuft_noch")
    if not (job.verzeichnis / "kandidaten.pkl").exists():
        raise fehler(request, 410, "api_kandidaten_weg")
    lage = (anfrage.motivlage if anfrage else None)
    if lage is not None and lage != "egal" and lage not in kalibrierung.MOTIVLAGEN:
        raise fehler(request, 400, "api_motivlage")
    prio = (anfrage.lage_prio if anfrage else None)
    if prio is not None and prio not in ("position", "qualitaet"):
        raise fehler(request, 400, "api_motivlage")
    try:
        worker.erneut_waehlen(job, lage, prio)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return {"job_id": job.id}
