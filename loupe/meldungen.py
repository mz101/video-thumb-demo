"""Meldungen der Pipeline in beiden Sprachen.

Die Texte stehen hier und nicht verstreut im Code, weil sie den Nutzer
erreichen: Ein Fehler aus der Extraktion landet unveraendert im Sichtungs-
bereich. Wer die Oberflaeche auf Englisch stellt, darf dort keinen deutschen
Satz aus dem Maschinenraum vorfinden.

Sie sagen, was passiert ist und was jetzt zu tun ist -- ohne Entschuldigung
und ohne Fachbegriffe.
"""

from __future__ import annotations

SPRACHEN = ("de", "en")
VORGABE = "de"

TEXTE: dict[str, dict[str, str]] = {
    "kein_ffmpeg": {
        "de": "ffmpeg ist nicht installiert oder nicht im PATH.",
        "en": "ffmpeg is not installed or not on the PATH.",
    },
    "keine_videospur": {
        "de": "Die Datei enthält keine Videospur.",
        "en": "The file contains no video track.",
    },
    "nichts_lesbar": {
        "de": "Aus dem Video ließ sich kein einziges Bild lesen. "
              "Möglicherweise ist die Datei beschädigt.",
        "en": "Not a single frame could be read from the video. "
              "The file may be damaged.",
    },
    "zu_kurz": {
        "de": "Das Video ist {dauer} lang. Unter einer Minute gibt es zu wenige "
              "verschiedene Momente für eine Auswahl.",
        "en": "The video is {dauer} long. Under a minute there are too few "
              "distinct moments to choose from.",
    },
    #: Ohne Hinweis auf den CLI-Schalter: In der Oberflaeche laesst er sich
    #: nicht setzen, und ein Rat, den man nicht befolgen kann, ist keiner.
    #: Die CLI haengt ihren eigenen Hinweis an.
    "zu_lang": {
        "de": "Das Video ist {dauer} lang, verarbeitet werden bis {grenze}. "
              "Kürze das Video oder exportiere einen Ausschnitt.",
        "en": "The video is {dauer} long, up to {grenze} is processed. "
              "Shorten the video or export an excerpt.",
    },
    "zu_lang_cli": {
        "de": " Mit --ueberlaenge wird es trotzdem verarbeitet.",
        "en": " With --ueberlaenge it is processed anyway.",
    },
    "kein_schluessel": {
        "de": "OPENAI_API_KEY ist nicht gesetzt.",
        "en": "OPENAI_API_KEY is not set.",
    },
    "keine_kandidaten": {
        "de": "Keine Kandidaten zu bewerten.",
        "en": "No candidates to score.",
    },
    "kein_json": {
        "de": "Die Antwort des Modells war kein gültiges JSON: {grund}",
        "en": "The model's response was not valid JSON: {grund}",
    },
    "vorschau_kaputt": {
        "de": "Vorschau nicht kodierbar: {id}",
        "en": "Could not encode preview: {id}",
    },
    "fallback_begruendung": {
        "de": "Technisch ausgewählt, nicht inhaltlich.",
        "en": "Selected on technical grounds, not on content.",
    },
}


def text(schluessel: str, sprache: str = VORGABE, **werte) -> str:
    eintrag = TEXTE.get(schluessel, {})
    roh = eintrag.get(sprache) or eintrag.get(VORGABE) or schluessel
    try:
        return roh.format(**werte)
    except (KeyError, IndexError):
        return roh


def pruefe_sprache(sprache: str | None) -> str:
    return sprache if sprache in SPRACHEN else VORGABE
