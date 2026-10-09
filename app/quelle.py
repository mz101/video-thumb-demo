"""Video von einer fremden Adresse holen.

Der Erweitert-Bereich erlaubt statt eines Uploads eine bereits vorhandene
Adresse. Der Server ruft sie selbst ab -- ohne Pruefung waere das eine
SSRF-Flaeche: Wer eine Adresse im internen Netz eintraegt, laesst den
Container dorthin greifen.

Fruehere Heimat: app/spaces.py. Der Teil hat den Abbau des Objektspeichers
ueberlebt, weil er mit S3 nie etwas zu tun hatte.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import config


class QuellFehler(RuntimeError):
    pass


def _aufloesen(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise QuellFehler(
            "Der Hostname in der Adresse lässt sich nicht auflösen. Prüfe die Schreibweise."
        ) from e
    return [ipaddress.ip_address(i[4][0]) for i in infos]


def _ist_intern(adresse) -> bool:
    return (adresse.is_private or adresse.is_loopback or adresse.is_link_local
            or adresse.is_reserved or adresse.is_multicast or adresse.is_unspecified)


def pruefen(url: str) -> None:
    teile = urllib.parse.urlparse(url)
    if teile.scheme not in ("http", "https"):
        raise QuellFehler("Die Adresse muss mit http:// oder https:// beginnen.")
    if not teile.hostname:
        raise QuellFehler("Die Adresse enthält keinen gültigen Hostnamen.")
    if any(_ist_intern(a) for a in _aufloesen(teile.hostname)):
        raise QuellFehler(
            "Diese Adresse zeigt in ein privates Netz und kann nicht geladen werden."
        )


class _KeineWeiterleitung(urllib.request.HTTPRedirectHandler):
    """Weiterleitungen selbst pruefen, statt ihnen blind zu folgen.

    Sonst umgeht eine oeffentliche Adresse, die auf 169.254.169.254 zeigt,
    die Eingangspruefung.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        pruefen(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def laden(url: str, ziel: Path) -> Path:
    pruefen(url)
    oeffner = urllib.request.build_opener(_KeineWeiterleitung)
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Loupe/0.1"})

    gelesen = 0
    try:
        with oeffner.open(anfrage, timeout=60) as antwort, ziel.open("wb") as datei:
            while stueck := antwort.read(1 << 20):
                gelesen += len(stueck)
                if gelesen > config.MAX_UPLOAD_BYTE:
                    raise QuellFehler(
                        f"Die Datei ist größer als "
                        f"{config.MAX_UPLOAD_BYTE // (1024*1024)} MB. "
                        f"Kürze das Video oder exportiere es kleiner."
                    )
                datei.write(stueck)
    except QuellFehler:
        raise
    except urllib.error.HTTPError as e:
        raise QuellFehler(
            f"Die Adresse antwortet mit Fehler {e.code}. Prüfe, ob sie noch gültig ist."
        ) from e
    except Exception as e:
        raise QuellFehler(
            "Die Adresse ist nicht erreichbar. Prüfe sie und versuche es erneut."
        ) from e

    if gelesen == 0:
        raise QuellFehler("Unter dieser Adresse liegt keine Datei.")
    return ziel
