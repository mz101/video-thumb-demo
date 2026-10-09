"""Stufe 4: ein Vision-Aufruf gegen OpenAI.

Aufbau der Anfrage:

* Das Modell sieht die **zugeschnittenen** Kandidaten -- also genau das Bild,
  das der Nutzer am Ende bekommt.
* Vor jedem Bild steht ein Textlabel mit Kennung und Zeitcode. Bei 20 Bildern
  am Stueck verwechseln Modelle sonst zuverlaessig die Nummern.
* `detail="low"` ist zwingend: `detail="auto"` entspricht bei GPT-5.6
  `original` und schickt die volle Aufloesung.
* Das Modell liefert Achsen-Scores fuer **alle** Kandidaten plus einen
  Gruppenvorschlag. Die Scores tragen Rerank, Kontaktbogen und Kalibrierung;
  der Gruppenvorschlag traegt die vergleichende Entscheidung, die aus
  unabhaengigen Einzelscores nicht entsteht. Die Aggregation und die
  Diversitaetspruefung laufen anschliessend in Code.
"""

from __future__ import annotations

import base64
import json
from concurrent.futures import ThreadPoolExecutor
import os
from dataclasses import dataclass
from typing import Any

import cv2
from openai import OpenAI

from . import config, crop
from .filtering import Kandidat
from .meldungen import text
from .metrics import hamming


class BewertungFehler(RuntimeError):
    pass


#: Die Achsen. Die Beschreibungen gehen in den Prompt und muessen deshalb in
#: der Sprache stehen, in der das Modell antworten soll -- sonst schreibt es
#: deutsche Begruendungen in eine englische Oberflaeche.
ACHSEN = ("headline_bezug", "motiv", "gesicht", "lesbarkeit", "textflaeche")

ACHSEN_TEXT = {
    "de": {
        "headline_bezug": "Wie stark stützt das Bild die Headline? Das ist die Hauptachse.",
        "motiv": "Bildqualität als Motiv: Komposition, Blickführung, Moment. Nicht Technik.",
        "gesicht": "Gesichter: sichtbar, offene Augen, brauchbarer Ausdruck. "
                   "Kein Gesicht im Bild: 0.",
        "lesbarkeit": "Trägt das Bild noch bei 320 px Breite? Klare Formen, kein Gewimmel.",
        "textflaeche": "Gibt es eine ruhige Fläche, auf der später Titeltext liegen könnte?",
    },
    "en": {
        "headline_bezug": "How strongly does the image support the headline? "
                          "This is the primary axis.",
        "motiv": "Quality as a subject: composition, where the eye goes, the moment. "
                 "Not technical quality.",
        "gesicht": "Faces: visible, eyes open, usable expression. No face in frame: 0.",
        "lesbarkeit": "Does the image still work at 320 px wide? Clear shapes, no clutter.",
        "textflaeche": "Is there a calm area where title text could sit later?",
    },
}


def _schema(anzahl: int) -> dict[str, Any]:
    achsen_props = {name: {"type": "integer", "minimum": 0, "maximum": 100}
                    for name in ACHSEN}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kandidaten", "vorschlag", "gesamteindruck"],
        "properties": {
            "kandidaten": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "scores", "begruendung"],
                    "properties": {
                        "id": {"type": "string"},
                        "scores": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": list(ACHSEN),
                            "properties": achsen_props,
                        },
                        "begruendung": {
                            "type": "string",
                            "description": "Ein Satz, der im Interface angezeigt wird.",
                        },
                    },
                },
            },
            "vorschlag": {
                "type": "array",
                "items": {"type": "string"},
                "description": f"Genau {anzahl} Kennungen, die zusammen die beste Gruppe ergeben.",
            },
            "gesamteindruck": {
                "type": "string",
                "description": "Ein Satz über das Material als Ganzes.",
            },
        },
    }


_PROMPT_DE = """Du wählst Thumbnails für ein Video aus. Du erzeugst keine Bilder, du beurteilst vorgelegte.

{ziel}
{transkript}
Du bekommst {achsenzahl} Achsen, jeweils 0 bis 100:
{achsen}

Bewerte **jeden** vorgelegten Kandidaten auf allen Achsen und schreibe je einen Satz
Begründung. Die Begründung wird dem Nutzer angezeigt: konkret, kein Werbeton, kein
Fachjargon. **Schreibe alle Begründungen auf Deutsch.**

Schlage anschließend genau {anzahl} Kandidaten als Gruppe vor. Sie müssen
**unterschiedliche Momente** zeigen — verschiedene Einstellungen, verschiedene Passagen des
Videos. Mehrere fast gleiche Frames aus derselben Einstellung sind ein schlechter Vorschlag,
auch wenn jeder für sich stark ist.

Achte besonders auf Ausschussgründe, die eine reine Bildmessung nicht sieht: geschlossene
oder halb geschlossene Augen, Mundstellungen mitten im Sprechen, abgeschnittene Köpfe,
Bewegungsunschärfe im Motiv, Übergangsframes aus Blenden.
{zusatz}

Die Bilder liegen dir bereits im Zielformat {format} zugeschnitten vor — beurteile,
was du siehst, nicht was außerhalb liegen könnte."""

_PROMPT_EN = """You are choosing thumbnails for a video. You do not create images, you judge the ones given to you.

{ziel}
{transkript}
You get {achsenzahl} axes, each 0 to 100:
{achsen}

Score **every** candidate on all axes and write one sentence of reasoning for each. The
reasoning is shown to the user: concrete, no marketing tone, no jargon. **Write all
reasoning in English.**

Then propose exactly {anzahl} candidates as a group. They must show **different moments** —
different shots, different passages of the video. Several near-identical frames from the
same shot are a poor proposal, even if each is strong on its own.

Pay particular attention to disqualifiers that pixel measurements cannot see: closed or
half-closed eyes, mouth shapes mid-speech, cropped heads, motion blur on the subject,
transition frames from dissolves.
{zusatz}

The images have already been cropped to the target format {format} — judge what you see,
not what might lie outside the frame."""

#: Kopfteil des Prompts. Headline und Beschreibung sind freiwillig -- fehlt
#: beides, gibt es kein Ziel zum Abgleichen, und das Modell muss die Frames
#: als Thumbnails an sich beurteilen. Das ausdruecklich zu sagen ist besser,
#: als ihm ein leeres Anfuehrungszeichenpaar vorzulegen.
_ZIEL = {
    "de": {
        "beides": 'Headline, unter der das Video erscheint:\n„{headline}"\n\n'
                  'Beschreibung des Videos:\n{beschreibung}\n\n'
                  'Die Headline ist das Ziel, gegen das du matchst. Die Beschreibung '
                  'liefert dir das Vokabular und sagt dir, was überhaupt zu sehen sein '
                  'sollte — besonders wenn die Headline zugespitzt oder metaphorisch ist '
                  'und kein Frame sie wörtlich abbildet.',
        "nur_headline": 'Headline, unter der das Video erscheint:\n„{headline}"\n\n'
                        'Sie ist das Ziel, gegen das du matchst. Eine Beschreibung des '
                        'Videos liegt nicht vor — erschließe dir aus den Bildern selbst, '
                        'worum es geht.',
        "nur_beschreibung": 'Beschreibung des Videos:\n{beschreibung}\n\n'
                            'Eine Headline gibt es nicht. Beurteile die Frames danach, wie '
                            'gut sie dieses Video als Thumbnail vertreten.',
        "nichts": 'Weder Headline noch Beschreibung liegen vor. Beurteile die Frames '
                  'als Thumbnails an sich: ein klarer Moment, ein starkes Motiv, gute '
                  'Lesbarkeit bei kleiner Darstellung. Die Achse headline_bezug '
                  'bewertest du als allgemeine Eignung, dieses Video zu vertreten.',
    },
    "en": {
        "beides": 'Headline the video will appear under:\n"{headline}"\n\n'
                  'Description of the video:\n{beschreibung}\n\n'
                  'The headline is the target you match against. The description gives '
                  'you the vocabulary and tells you what should be visible at all — '
                  'especially when the headline is pointed or metaphorical and no frame '
                  'depicts it literally.',
        "nur_headline": 'Headline the video will appear under:\n"{headline}"\n\n'
                        'It is the target you match against. No description of the video '
                        'was given — work out from the images themselves what this is about.',
        "nur_beschreibung": 'Description of the video:\n{beschreibung}\n\n'
                            'There is no headline. Judge the frames by how well they '
                            'represent this video as a thumbnail.',
        "nichts": 'Neither a headline nor a description was given. Judge the frames as '
                  'thumbnails in their own right: a clear moment, a strong subject, good '
                  'legibility at small size. Score the headline_bezug axis as general '
                  'suitability to represent this video.',
    },
}

#: Die Verortung laeuft in einem EIGENEN Aufruf, nicht im Bewertungsaufruf.
#: Gemessen am Fossilien-Video: Im grossen Aufruf (24 Bilder, Bewertung +
#: Begruendung + Gruppenvorschlag gleichzeitig) verortete das Modell den
#: Fisch unten links als "mitte" (38,55) -- fokussiert gefragt kam (22,66).
#: Die Lage ist eine Eigenschaft des Frames und wird immer erhoben, auch ohne
#: Wunsch: dadurch laesst sich die Position spaeter kostenlos aendern, und
#: das Raster kann zeigen, wo das Video ueberhaupt Material hat.
#:
#: Der Aufruf erfaehrt den Wunsch absichtlich nicht -- er soll beschreiben,
#: nicht gefallen.
_VERORTUNG = {
    "de": """Bestimme für jedes Bild die Lage des Hauptmotivs — des Gegenstands oder der
Person, um die es geht. motiv_x und motiv_y in Prozent: 0/0 ist die linke obere
Ecke, 100/100 die rechte untere. Gemeint ist der Mittelpunkt des Motivs, nicht
seine Ausdehnung.

Bei Personen und Tieren zählt der Kopf als Anker — nenne den Punkt von Gesicht
bzw. Auge, nicht die Mitte der Körperfläche. So beantworten auch Menschen die
Frage, wo ein Motiv „sitzt".

Gibt es kein erkennbares Hauptmotiv, sondern eine Landschaft, eine Textur oder
eine gleichmäßig gefüllte Fläche, setze motiv_klar auf false (x und y dann 50).
Rate nicht. Sonst nichts: keine Bewertung, keine Auswahl — nur die Lage.""",
    "en": """For each image, locate the main subject — the object or person the shot is
about. motiv_x and motiv_y in percent: 0/0 is the top-left corner, 100/100 the
bottom-right. Report the subject's centre point, not its extent.

For people and animals the head is the anchor — report the point of the face or
eye, not the centre of the body area. That matches how people answer where a
subject "sits".

If there is no recognisable main subject but a landscape, a texture or an evenly
filled surface, set motiv_klar to false (x and y to 50). Do not guess. Nothing
else: no scoring, no selection — position only.""",
}

_VERORTUNG_SCHEMA: dict[str, Any] = {
    "type": "object", "additionalProperties": False, "required": ["bilder"],
    "properties": {"bilder": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["id", "motiv_klar", "motiv_x", "motiv_y"],
        "properties": {
            "id": {"type": "string"},
            "motiv_klar": {"type": "boolean"},
            "motiv_x": {"type": "integer", "minimum": 0, "maximum": 100},
            "motiv_y": {"type": "integer", "minimum": 0, "maximum": 100},
        }}}},
}


def _verorten_haeppchen(kandidaten: list[Kandidat], lauf) -> tuple[dict, dict]:
    sprache = lauf.sprache if lauf.sprache in ("de", "en") else "de"
    inhalt: list[dict[str, Any]] = [
        {"type": "input_text", "text": _VERORTUNG[sprache]}
    ]
    for k in kandidaten:
        inhalt.append({"type": "input_text", "text": f"Bild {k.id}"})
        inhalt.append(_bild_teil(k, lauf.format))

    antwort = OpenAI(api_key=os.getenv("OPENAI_API_KEY")).responses.create(
        model=config.MODELL,
        input=[{"role": "user", "content": inhalt}],
        text={"format": {"type": "json_schema", "name": "verortung",
                         "strict": True, "schema": _VERORTUNG_SCHEMA}},
    )
    daten = json.loads(antwort.output_text)
    lagen = {
        b["id"]: (bool(b["motiv_klar"]), float(b["motiv_x"]), float(b["motiv_y"]))
        for b in daten.get("bilder", [])
    }
    return lagen, {"input_tokens": antwort.usage.input_tokens,
                   "output_tokens": antwort.usage.output_tokens}


def verorten(kandidaten: list[Kandidat], lauf) -> tuple[dict[str, tuple[bool, float, float]], dict]:
    """Motivlage aller Kandidaten, in parallelen Haeppchen.

    Kleine Aufrufe halten den Kopf-Anker stabil (siehe config.
    VERORTUNG_HAEPPCHEN); parallel kosten sie die Laufzeit eines einzigen.
    Gibt ({id: (klar, x, y)}, Verbrauch) zurueck.
    """
    stuecke = [
        kandidaten[i:i + config.VERORTUNG_HAEPPCHEN]
        for i in range(0, len(kandidaten), config.VERORTUNG_HAEPPCHEN)
    ]
    lagen: dict[str, tuple[bool, float, float]] = {}
    verbrauch = {"input_tokens": 0, "output_tokens": 0, "aufrufe": len(stuecke)}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for teil, teil_verbrauch in pool.map(
            lambda s: _verorten_haeppchen(s, lauf), stuecke
        ):
            lagen.update(teil)
            verbrauch["input_tokens"] += teil_verbrauch["input_tokens"]
            verbrauch["output_tokens"] += teil_verbrauch["output_tokens"]
    return lagen, verbrauch


_ZUSATZ = {
    "de": {
        "gesichter": "Frames mit gut sichtbaren Gesichtern sind erwünscht.",
        "textflaeche": "Auf dem Bild soll später Titeltext liegen; ruhige Flächen sind wichtig.",
    },
    "en": {
        "gesichter": "Frames with clearly visible faces are wanted.",
        "textflaeche": "Title text will be placed on the image later; calm areas matter.",
    },
}

_TRANSKRIPT = {
    "de": """
Zusätzlich liegt dir die Tonspur des Videos als Transkript vor:

{text}

Nutze es als Hinweis darauf, worum es im Video geht und welches Vokabular passt.
**Achtung:** Gesprochenes und Gezeigtes fallen bei geschnittenem Material nicht zusammen —
über etwas zu reden heißt nicht, es zu zeigen. Das Transkript beschreibt nicht die Bilder.
Was du siehst, hat Vorrang; benenne nichts, was du nicht im Bild erkennst.
""",
    "en": """
You are also given the video's audio as a transcript:

{text}

Use it as a hint about what the video is about and which vocabulary fits.
**Careful:** in edited material, what is said and what is shown do not line up — talking
about something is not showing it. The transcript does not describe the images. What you
see takes precedence; do not name anything you cannot make out in the frame.
""",
}


def _anweisung(lauf, anzahl: int, transkript: str | None = None) -> str:
    sprache = lauf.sprache if lauf.sprache in ("de", "en") else "de"
    beschriftung = ACHSEN_TEXT[sprache]
    zusatz = [_ZUSATZ[sprache]["gesichter"]] if lauf.gesichter_bevorzugen else []
    if lauf.textflaeche:
        zusatz.append(_ZUSATZ[sprache]["textflaeche"])

    headline, beschreibung = lauf.headline.strip(), lauf.beschreibung.strip()
    fall = ("beides" if headline and beschreibung else
            "nur_headline" if headline else
            "nur_beschreibung" if beschreibung else "nichts")
    ziel = _ZIEL[sprache][fall].format(headline=headline, beschreibung=beschreibung)

    vorlage = _PROMPT_DE if sprache == "de" else _PROMPT_EN
    return vorlage.format(
        ziel=ziel,
        achsenzahl=len(ACHSEN),
        achsen="\n".join(f"- {n}: {beschriftung[n]}" for n in ACHSEN),
        anzahl=anzahl,
        zusatz=" ".join(zusatz),
        format=lauf.format,
        transkript=_TRANSKRIPT[sprache].format(text=transkript) if transkript else "",
    )


def _bild_teil(kandidat: Kandidat, format: str) -> dict[str, Any]:
    bild = crop.vorschau(kandidat.pfad, format)
    ok, puffer = cv2.imencode(".jpg", bild, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise BewertungFehler(text("vorschau_kaputt", "de", id=kandidat.id))
    b64 = base64.b64encode(puffer.tobytes()).decode()
    return {
        "type": "input_image",
        "image_url": f"data:image/jpeg;base64,{b64}",
        "detail": "low",
    }


def bewerten(kandidaten: list[Kandidat], lauf,
             transkript: str | None = None) -> tuple[dict, dict]:
    """Ein Aufruf. Gibt (Ergebnis, Verbrauchsprotokoll) zurueck."""
    if not kandidaten:
        raise BewertungFehler(text("keine_kandidaten", lauf.sprache))

    schluessel = os.getenv("OPENAI_API_KEY")
    if not schluessel:
        raise BewertungFehler(text("kein_schluessel", lauf.sprache))

    inhalt: list[dict[str, Any]] = [
        {"type": "input_text", "text": _anweisung(lauf, lauf.anzahl, transkript)}
    ]
    for k in kandidaten:
        inhalt.append({
            "type": "input_text",
            "text": (f"Kandidat {k.id} — Zeitcode {k.zeitcode}"
                     if lauf.sprache == "de"
                     else f"Candidate {k.id} — timecode {k.zeitcode}"),
        })
        inhalt.append(_bild_teil(k, lauf.format))

    client = OpenAI(api_key=schluessel)
    antwort = client.responses.create(
        model=config.MODELL,
        input=[{"role": "user", "content": inhalt}],
        text={
            "format": {
                "type": "json_schema",
                "name": "thumbnail_bewertung",
                "strict": True,
                "schema": _schema(lauf.anzahl),
            }
        },
    )

    try:
        ergebnis = json.loads(antwort.output_text)
    except (json.JSONDecodeError, AttributeError) as e:
        raise BewertungFehler(text("kein_json", lauf.sprache, grund=e)) from e

    verbrauch = {
        "modell": config.MODELL,
        "bilder": len(kandidaten),
        "mit_transkript": bool(transkript),
        "input_tokens": getattr(antwort.usage, "input_tokens", None),
        "output_tokens": getattr(antwort.usage, "output_tokens", None),
    }
    return ergebnis, verbrauch


# --- Aggregation: laeuft in Code, nicht im Modell --------------------------

@dataclass
class Bewertet:
    kandidat: Kandidat
    scores: dict[str, int]
    begruendung: str
    gesamt: float
    motivlage: str = ""
    motiv_x: float = 50.0
    motiv_y: float = 50.0
    lage_stufe: int = 0
    lage_band: int = 0
    lage_abstand: float = 0.0


def aggregieren(kandidaten: list[Kandidat], ergebnis: dict, lauf,
                lagen: dict[str, tuple[bool, float, float]] | None = None,
                ) -> list[Bewertet]:
    gewichte = lauf.gewichte()
    nach_id = {k.id: k for k in kandidaten}
    lagen = lagen or {}
    bewertet: list[Bewertet] = []

    for eintrag in ergebnis.get("kandidaten", []):
        k = nach_id.get(eintrag.get("id"))
        if k is None:
            continue
        scores = eintrag.get("scores", {})
        gesamt = sum(gewichte.get(a, 0.0) * float(scores.get(a, 0)) for a in gewichte)

        # Die Lage ist eine Eigenschaft des Frames: ein Punkt, vom eigenen
        # Verortungsaufruf genannt. Zelle, Stufe und Abstandsband entstehen
        # erst hier, im Vergleich mit dem Wunsch -- deshalb laesst sich der
        # Wunsch spaeter aendern, ohne das Modell erneut zu fragen.
        #
        # `gesamt` bleibt der reine Qualitaetswert. Frueher steckte der
        # Positionsbonus mit drin -- dann sprang die angezeigte Bewertung
        # desselben Frames, sobald man den Wunsch aenderte.
        klar, x, y = lagen.get(k.id, (False, 50.0, 50.0))
        lage = config.zelle_von_punkt(x, y) if klar else config.KEIN_MOTIV

        bewertet.append(Bewertet(
            k, scores, eintrag.get("begruendung", ""), gesamt, lage, x, y,
            config.lage_stufe(lauf.motivlage, lage),
            config.lage_band(lauf.motivlage, x, y, klar),
            config.lage_abstand(lauf.motivlage, x, y, klar),
        ))

    return sorted(bewertet, key=lambda b: -b.gesamt)


def _verschieden(a: Bewertet, b: Bewertet, abstand: float) -> bool:
    """Zeitabstand *und* Hash-Abstand muessen stimmen."""
    return (
        abs(a.kandidat.zeit - b.kandidat.zeit) >= abstand
        and hamming(a.kandidat.werte.dhash, b.kandidat.werte.dhash)
        >= config.DIVERSITAET_MIN_HASH
    )


def auswaehlen(
    bewertet: list[Bewertet],
    anzahl: int,
    dauer: float,
    vorschlag: list[str] | None = None,
    ueberspringen: set[str] | None = None,
    motivlage_gewuenscht: bool = False,
    lage_prio: str = "position",
) -> tuple[list[Bewertet], bool]:
    """Endauswahl mit Diversitaetspruefung.

    Der Gruppenvorschlag des Modells hat Vorrang -- er traegt die vergleichende
    Entscheidung, die aus unabhaengigen Einzelscores nicht entsteht. Verletzt er
    die Diversitaetsregel, greift die Rangfolge nach Gesamtscore.
    Gibt (Auswahl, Vorschlag_uebernommen) zurueck.
    """
    ueberspringen = ueberspringen or set()
    abstand = config.mindestabstand(dauer)
    nach_id = {b.kandidat.id: b for b in bewertet}

    # Bei gesetztem Positionswunsch tritt der Gruppenvorschlag zurueck. Das
    # Modell entscheidet ueber die Position ausdruecklich nicht -- wuerde sein
    # Vorschlag trotzdem gewinnen, ginge der Wunsch des Nutzers stillschweigend
    # unter. Genau das ist beim ersten Bau passiert.
    if vorschlag and not ueberspringen and not motivlage_gewuenscht:
        gruppe = [nach_id[i] for i in vorschlag if i in nach_id]
        if len(gruppe) == anzahl and all(
            _verschieden(gruppe[i], gruppe[j], abstand)
            for i in range(len(gruppe))
            for j in range(i + 1, len(gruppe))
        ):
            return sorted(gruppe, key=lambda b: b.kandidat.zeit), True

    # Bei gesetztem Wunsch entscheidet die Prioritaet, wer zuerst zaehlt --
    # beides in Kacheln gerastert, damit nicht drei Punkte Rauschen den
    # Ausschlag geben. Ein Aufschlag auf den Score reichte nicht -- die
    # Grundwerte streuen ueber 59 Punkte.
    #
    # position:  Abstand zur Wunschzelle zuerst, Bewertung innerhalb der
    #            Kachel. Wer markiert, meint es.
    # qualitaet: Bewertung zuerst (Stufen von QUALITAETS_KACHEL), Naehe zum
    #            Wunsch innerhalb der Stufe. Fuer alle, denen ein starkes
    #            Bild wichtiger ist als die Ecke.
    if motivlage_gewuenscht:
        if lage_prio == "qualitaet":
            bewertet = sorted(bewertet, key=lambda b: (
                -int(b.gesamt // config.QUALITAETS_KACHEL), b.lage_abstand))
        else:
            bewertet = sorted(bewertet, key=lambda b: (b.lage_band, -b.gesamt))

    auswahl: list[Bewertet] = []
    for b in bewertet:
        if b.kandidat.id in ueberspringen:
            continue
        if all(_verschieden(b, g, abstand) for g in auswahl):
            auswahl.append(b)
        if len(auswahl) == anzahl:
            break

    # Reicht die Diversitaet nicht fuer die gewuenschte Zahl, lieber enger
    # beieinander als zu wenige Vorschlaege. Das Interface zeigt auf der
    # Herkunftsleiste ohnehin, dass die Auswahl klumpt.
    if len(auswahl) < anzahl:
        gewaehlt = {b.kandidat.id for b in auswahl}
        for b in bewertet:
            if b.kandidat.id in ueberspringen or b.kandidat.id in gewaehlt:
                continue
            auswahl.append(b)
            gewaehlt.add(b.kandidat.id)
            if len(auswahl) == anzahl:
                break

    return sorted(auswahl, key=lambda b: b.kandidat.zeit), False
