"""Optionale Tonspur-Auswertung als globaler Kontext fuer die Bewertung.

**Vorgabe aus.** Die Messung vor dem Einbau (drei Videos, jeweils derselbe
Kandidatensatz mit und ohne Transkript bewertet) ergab:

* Auf die Auswahl wirkt es kaum. 05 Everest: 3 von 3 Vorschlaegen identisch.
  02 Fossilien: 2 von 3, die dritte Aenderung war dieselbe Einstellung eine
  Sekunde spaeter.
* Wo es half, war das Vokabular der Begruendungen: „Ammonitenstruktur" wurde
  zu „fossiler Pfeilschwanzkrebs". Diese Saetze stehen im Interface.
* Das ist ein **globaler** Effekt, kein zeitlicher. Deshalb hier kein
  Zeitstempel-Modell: `whisper-1` kostet $0,006/min, liefert Segmentzeiten --
  und die brachten messbar nichts. `gpt-4o-mini-transcribe` kostet die
  Haelfte, kann keine Zeitstempel und holt den belegten Nutzen.

Warum ueberhaupt: Talking-Head-Material fehlt im Kalibriersatz. Dort tragen
die Bilder fast keine Unterscheidung, und der Ton waere das Einzige, was einen
Moment vom anderen trennt. Fuer diesen Fall ist der Schalter gedacht.

Bild und Ton fallen bei geschnittenem Material auseinander -- der Kommentar
spricht ueber etwas anderes, als zu sehen ist. Der Prompt sagt das
ausdruecklich, damit das Transkript nicht als Bildbeschreibung missverstanden
wird.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from openai import OpenAI

MODELL = os.getenv("OPENAI_TRANSKRIPT_MODELL", "gpt-4o-mini-transcribe")

#: Unter dieser Wortdichte gilt die Tonspur als sprachlos: Musik, Atmo,
#: Notenzeichen. Gemessen am Naturfilm 01 -- 27 „Woerter" auf 4,5 Minuten,
#: durchweg ♪-Zeichen. Ein sprechender Mensch liegt bei 120 bis 160.
WOERTER_PRO_MINUTE_MIN = 15

#: Was ins Prompt geht. Ein 5-min-Video liegt bei rund 750 Woertern.
MAX_ZEICHEN = 4000

_NOTEN = re.compile(r"[♪♫🎵🎶\[\](){}]|\b(musik|music|applaus|applause)\b", re.I)


def hat_tonspur(video: Path) -> bool:
    erg = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    )
    return erg.returncode == 0 and bool(erg.stdout.strip())


def _audio_ziehen(video: Path, ziel: Path) -> Path:
    """Mono, 16 kHz, 32 kbit/s. Ein 5-min-Video wiegt damit rund 1,2 MB --
    die API nimmt bis 25 MB, das ist also unkritisch."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k", str(ziel)],
        capture_output=True, text=True, check=True,
    )
    return ziel


def _hat_sprache(text: str, dauer: float) -> bool:
    sauber = _NOTEN.sub(" ", text)
    woerter = len(sauber.split())
    if dauer <= 0:
        return woerter > 20
    return woerter / (dauer / 60) >= WOERTER_PRO_MINUTE_MIN


def erzeugen(video: Path, dauer: float) -> tuple[str | None, dict]:
    """Transkript holen. Gibt (Text oder None, Protokoll) zurueck.

    Ein Fehlschlag ist nie fatal -- das Transkript ist Zusatzkontext, kein
    Bestandteil der Auswahl. Bricht es weg, laeuft die Bewertung wie zuvor.
    """
    protokoll: dict = {"modell": MODELL, "genutzt": False}

    if not hat_tonspur(video):
        protokoll["grund"] = "keine Tonspur"
        return None, protokoll

    schluessel = os.getenv("OPENAI_API_KEY")
    if not schluessel:
        protokoll["grund"] = "kein API-Schlüssel"
        return None, protokoll

    try:
        with tempfile.TemporaryDirectory(prefix="loupe-ton-") as tmp:
            audio = _audio_ziehen(video, Path(tmp) / "ton.mp3")
            protokoll["audio_mb"] = round(audio.stat().st_size / 1e6, 2)
            with audio.open("rb") as f:
                antwort = OpenAI(api_key=schluessel).audio.transcriptions.create(
                    model=MODELL, file=f, response_format="json",
                )
        roh = (getattr(antwort, "text", "") or "").strip()
    except subprocess.CalledProcessError:
        protokoll["grund"] = "Tonspur nicht lesbar"
        return None, protokoll
    except Exception as e:                        # API-Fehler, Netz, Kontingent
        protokoll["grund"] = f"{type(e).__name__}"
        return None, protokoll

    protokoll["woerter"] = len(roh.split())
    protokoll["minuten"] = round(dauer / 60, 2)

    if not _hat_sprache(roh, dauer):
        protokoll["grund"] = "keine zusammenhängende Sprache (Musik oder Atmo)"
        return None, protokoll

    protokoll["genutzt"] = True
    return roh[:MAX_ZEICHEN], protokoll


def kosten_schaetzung(dauer: float) -> float:
    """Cent. gpt-4o-mini-transcribe liegt bei $0,003 je Minute."""
    return round(dauer / 60 * 0.003 * 100, 2)
