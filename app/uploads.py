"""Stueckweiser Upload direkt zur Anwendung.

Warum nicht in einem Rutsch: Railway begrenzt die Groesse eines Requests
nicht, bricht aber nach **5 Minuten** ab. Ein 800-MB-Video bei 20 Mbit/s
braucht 5:20 und scheitert damit -- und zwar erst nach fuenf Minuten Warten,
also auf die unangenehmste Art.

Der Browser schneidet die Datei deshalb in Stuecke von 8 MB. Jeder Request
dauert Sekunden statt Minuten, das Zeitlimit ist damit kein Thema, und ein
abgerissenes Stueck laesst sich einzeln wiederholen, statt von vorn zu
beginnen.

Ersetzt den Presigned PUT nach S3. Das Konzept hatte den mit Speicher- und
Request-Limits begruendet; beides traegt nicht: Ein Upload wird stueckweise
auf die Platte geschrieben, nie im Speicher gehalten.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from . import config

#: Muss zum Wert in static/app.js passen.
TEILGROESSE = 8 * 1024 * 1024

_KENNUNG = re.compile(r"^[0-9a-f]{32}$")


class UploadFehler(RuntimeError):
    pass


@dataclass
class Upload:
    kennung: str
    dateiname: str
    groesse: int
    begonnen: float

    @property
    def ordner(self) -> Path:
        return config.UPLOADS / self.kennung


def _ordner(kennung: str) -> Path:
    """Pfad zu einem Upload. Prueft die Kennung, bevor sie in einen Pfad geht."""
    if not _KENNUNG.match(kennung):
        raise UploadFehler("Diese Upload-Kennung ist ungültig.")
    return config.UPLOADS / kennung


def anlegen(dateiname: str, groesse: int) -> Upload:
    if groesse > config.MAX_UPLOAD_BYTE:
        raise UploadFehler(
            f"Die Datei ist größer als {config.MAX_UPLOAD_BYTE // (1024*1024)} MB. "
            f"Kürze das Video oder exportiere es kleiner."
        )
    if groesse <= 0:
        raise UploadFehler("Die Datei ist leer.")

    kennung = uuid.uuid4().hex
    ordner = config.UPLOADS / kennung
    ordner.mkdir(parents=True, exist_ok=True)

    upload = Upload(kennung, Path(dateiname).name[:200], groesse, time.time())
    (ordner / "meta.json").write_text(
        json.dumps({
            "dateiname": upload.dateiname,
            "groesse": upload.groesse,
            "begonnen": upload.begonnen,
        }),
        encoding="utf-8",
    )
    return upload


def lesen(kennung: str) -> Upload:
    ordner = _ordner(kennung)
    try:
        d = json.loads((ordner / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise UploadFehler(
            "Dieser Upload ist abgelaufen. Lade das Video erneut hoch."
        ) from e
    return Upload(kennung, d["dateiname"], d["groesse"], d["begonnen"])


def teil_schreiben(kennung: str, index: int, daten: bytes) -> int:
    """Ein Stueck ablegen. Gibt die bisher empfangene Gesamtgroesse zurueck."""
    ordner = _ordner(kennung)
    if not ordner.is_dir():
        raise UploadFehler("Dieser Upload ist abgelaufen. Lade das Video erneut hoch.")
    if not 0 <= index < 100_000:
        raise UploadFehler("Ungültige Stücknummer.")
    if len(daten) > TEILGROESSE * 2:
        raise UploadFehler("Das Stück ist größer als erlaubt.")

    # Erst danebenschreiben, dann umbenennen: Ein abgebrochener Request
    # hinterlaesst so kein halbes Stueck, das spaeter mitgezaehlt wuerde.
    ziel = ordner / f"teil_{index:05d}"
    vorlaeufig = ordner / f".teil_{index:05d}.tmp"
    vorlaeufig.write_bytes(daten)
    vorlaeufig.replace(ziel)

    return sum(t.stat().st_size for t in ordner.glob("teil_*"))


def vollstaendig(kennung: str) -> bool:
    upload = lesen(kennung)
    teile = sorted(upload.ordner.glob("teil_*"))
    if not teile:
        return False
    erwartet = -(-upload.groesse // TEILGROESSE)      # aufgerundet
    return len(teile) == erwartet and \
        sum(t.stat().st_size for t in teile) == upload.groesse


def zusammensetzen(kennung: str, ziel: Path) -> Path:
    """Stuecke der Reihe nach in eine Datei schreiben."""
    upload = lesen(kennung)
    teile = sorted(upload.ordner.glob("teil_*"))
    if not teile:
        raise UploadFehler("Von diesem Upload ist nichts angekommen.")

    fehlend = -(-upload.groesse // TEILGROESSE) - len(teile)
    if fehlend > 0:
        raise UploadFehler(
            f"Der Upload ist unvollständig, es fehlen {fehlend} Stücke. "
            f"Lade das Video erneut hoch."
        )

    with ziel.open("wb") as aus:
        for teil in teile:
            with teil.open("rb") as ein:
                shutil.copyfileobj(ein, aus, length=1 << 20)
    return ziel


def verwerfen(kennung: str) -> None:
    try:
        shutil.rmtree(_ordner(kennung), ignore_errors=True)
    except UploadFehler:
        pass


def aufraeumen(stunden: int = 24) -> int:
    """Angefangene und nie beendete Uploads entfernen."""
    if not config.UPLOADS.is_dir():
        return 0
    grenze = time.time() - stunden * 3600
    entfernt = 0
    for ordner in config.UPLOADS.iterdir():
        if ordner.is_dir() and ordner.stat().st_mtime < grenze:
            shutil.rmtree(ordner, ignore_errors=True)
            entfernt += 1
    return entfernt
