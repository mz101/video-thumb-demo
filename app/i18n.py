"""Sprachen der Oberflaeche. Deutsch ist die Vorgabe.

Ein Katalog fuer Vorlagen und Browser gleichermassen: Was in app.js an Texten
gebraucht wird, wird als JSON in die Seite gereicht, statt eine zweite Liste
zu pflegen. Zwei Kataloge laufen sonst auseinander.

Die Sprachwahl haengt am Cookie, nicht am Pfad -- die Adresse eines Jobs soll
in beiden Sprachen dieselbe sein.
"""

from __future__ import annotations

import json

from fastapi import Request

SPRACHEN = {"de": "Deutsch", "en": "English"}
VORGABE = "de"
COOKIE = "loupe_sprache"

TEXTE: dict[str, dict[str, str]] = {
    # --- Rahmen ------------------------------------------------------------
    "marke": {"de": "Loupe", "en": "Loupe"},
    #: Nennt die Faehigkeit, nicht das Ausgabeformat. „Thumbnails aus echten
    #: Frames" beschrieb, was hinten herauskommt -- und wurde damit enger,
    #: je mehr das Werkzeug kann (Transkript, Motivlage, Formate).
    "untertitel": {"de": "Findet den stärksten Moment im Video",
                   "en": "Finds the strongest moment in a video"},
    #: Urheberzeile unter dem Anmeldefeld. „developed by" bleibt in beiden
    #: Sprachen stehen -- es gehoert zur Signatur, nicht zur Oberflaeche.
    "entwickelt_von": {"de": "developed by", "en": "developed by"},
    "abmelden": {"de": "Abmelden", "en": "Sign out"},
    "sprache": {"de": "Sprache", "en": "Language"},

    # --- Anmeldung ---------------------------------------------------------
    "anmelden_titel": {"de": "Loupe — anmelden", "en": "Loupe — sign in"},
    "name": {"de": "Name", "en": "Name"},
    "passwort": {"de": "Passwort", "en": "Password"},
    "anmelden": {"de": "Anmelden", "en": "Sign in"},
    "anmeldung_falsch": {
        "de": "Name oder Passwort stimmt nicht. Versuche es erneut.",
        "en": "That name or password is not right. Try again.",
    },
    "anmeldung_gesperrt": {
        "de": "Zu viele Fehlversuche. Die Anmeldung ist für {minuten} min gesperrt.",
        "en": "Too many failed attempts. Sign-in is locked for {minuten} min.",
    },

    # --- Eingaben ----------------------------------------------------------
    "video": {"de": "Video", "en": "Video"},
    "ablage_ziehen": {"de": "Video hierher ziehen", "en": "Drop a video here"},
    "ablage_hilfe": {
        "de": "MP4, MOV, WebM · bis {mb} MB · 1 bis {minuten} Minuten",
        "en": "MP4, MOV, WebM · up to {mb} MB · 1 to {minuten} minutes",
    },
    "datei_waehlen": {"de": "Datei auswählen", "en": "Choose a file"},
    "entfernen": {"de": "Entfernen", "en": "Remove"},

    "headline": {"de": "Headline", "en": "Headline"},
    "headline_platzhalter": {
        "de": "Der Titel, unter dem das Video erscheint",
        "en": "The title the video will appear under",
    },
    "beschreibung": {"de": "Videobeschreibung", "en": "Video description"},
    "beschreibung_hilfe": {
        "de": "Was ist im Video zu sehen, und welcher Moment ist der stärkste? "
              "Konkrete Angaben wirken besser als Werbetext.",
        "en": "What is in the video, and which moment is the strongest? "
              "Concrete detail works better than marketing copy.",
    },

    # --- Schalter ----------------------------------------------------------
    "tiefe": {"de": "Analysetiefe", "en": "Analysis depth"},
    "schnell": {"de": "Schnell", "en": "Fast"},
    "gruendlich": {"de": "Gründlich", "en": "Thorough"},
    "tiefe_hinweis": {
        "de": "Gründlich rechnet das ganze Video durch: rund zwei Minuten "
              "statt einer halben.",
        "en": "Thorough decodes the whole video: about two minutes instead "
              "of half a minute.",
    },
    "format": {"de": "Thumbnail-Format", "en": "Thumbnail format"},
    "gesichter": {"de": "Gesichter bevorzugen", "en": "Prefer faces"},
    "textflaeche": {"de": "Platz für Titeltext", "en": "Room for title text"},
    "anzahl": {"de": "Anzahl Vorschläge", "en": "Number of proposals"},

    # --- Motivlage ---------------------------------------------------------
    "motivlage": {"de": "Motiv im Bild", "en": "Subject in frame"},
    "motivlage_hilfe": {
        "de": "Bevorzugt Frames, deren Hauptmotiv dort liegt. Es wird nicht "
              "zugeschnitten — findet sich kein passender Frame, greift die "
              "Regel nicht.",
        "en": "Prefers frames whose main subject sits there. Nothing is "
              "cropped — if no frame fits, the rule simply does not apply.",
    },
    "lage_egal": {"de": "egal", "en": "any"},
    "lage_oben_links": {"de": "oben links", "en": "top left"},
    "lage_oben_mitte": {"de": "oben mittig", "en": "top centre"},
    "lage_oben_rechts": {"de": "oben rechts", "en": "top right"},
    "lage_mitte_links": {"de": "mittig links", "en": "middle left"},
    "lage_mitte": {"de": "mittig", "en": "centre"},
    "lage_mitte_rechts": {"de": "mittig rechts", "en": "middle right"},
    "lage_unten_links": {"de": "unten links", "en": "bottom left"},
    "lage_unten_mitte": {"de": "unten mittig", "en": "bottom centre"},
    "lage_unten_rechts": {"de": "unten rechts", "en": "bottom right"},
    "lage_kein_klares_motiv": {"de": "kein klares Motiv", "en": "no clear subject"},
    "lage_neu": {"de": "Wird neu geordnet", "en": "Reordering"},

    #: Prioritaet neben dem Raster -- nur sichtbar, wenn eine Position
    #: markiert ist. Entscheidet, was zuerst zaehlt, wenn Lage und Bildstaerke
    #: nicht zusammenkommen.
    "prio": {"de": "Priorität", "en": "Priority"},
    "prio_position": {"de": "Position", "en": "Position"},
    "prio_qualitaet": {"de": "Qualität", "en": "Quality"},
    "prio_hilfe": {
        "de": "Was zuerst zählt, wenn Lage und Bildstärke nicht zusammenkommen.",
        "en": "What counts first when position and image strength conflict.",
    },

    #: Fuer die Dichteanzeige im Raster nach der Analyse.
    "lage_anzahl_keine": {"de": "keine Kandidaten", "en": "no candidates"},
    "lage_anzahl_eins": {"de": "1 Kandidat", "en": "1 candidate"},
    "lage_anzahl": {"de": "{n} Kandidaten", "en": "{n} candidates"},

    #: Vor die Lage auf der Karte. Ohne dieses Wort las sich „mittig links"
    #: wie eine Behauptung, man habe bekommen was man wollte -- obwohl man
    #: „oben links" gewaehlt hatte.
    "motiv_kurz": {"de": "Motiv", "en": "subject"},

    #: Wenn der Positionswunsch nicht aufgeht, muss das dastehen. Eine
    #: Auswahl ohne Hinweis sähe aus wie eine Antwort auf die Frage, die sie
    #: gar nicht ist.
    "lage_keiner": {
        "de": "Kein Frame zeigt das Motiv {lage}. Gezeigt werden die "
              "bestbewerteten Alternativen.",
        "en": "No frame shows the subject {lage}. The best-rated alternatives "
              "are shown instead.",
    },
    "lage_teils": {
        "de": "{n} von {gesamt} Vorschlägen zeigen das Motiv {lage}. Für die "
              "übrigen gab es keinen passenden Frame.",
        "en": "{n} of {gesamt} proposals show the subject {lage}. For the "
              "others there was no matching frame.",
    },
    #: Bei genau einem Treffer stimmt sonst die Verbform nicht -- „1 von 3
    #: Vorschlägen zeigen" bzw. „1 of 3 proposals show".
    "lage_teils_eins": {
        "de": "1 von {gesamt} Vorschlägen zeigt das Motiv {lage}. Für die "
              "übrigen gab es keinen passenden Frame.",
        "en": "1 of {gesamt} proposals shows the subject {lage}. For the "
              "others there was no matching frame.",
    },

    #: Kein genauer Treffer, aber die Richtung stimmt. Ohne diesen Fall stand
    #: „kein Frame zeigt das Motiv unten rechts" auch dann da, wenn zwei von
    #: drei Vorschlaegen rechts lagen.
    "lage_naehe": {
        "de": "Kein Frame zeigt das Motiv genau {lage}. {n} von {gesamt} "
              "kommen dieser Richtung am nächsten.",
        "en": "No frame shows the subject exactly {lage}. {n} of {gesamt} "
              "come closest to that direction.",
    },
    #: Seit die Lage die Rangstufe bestimmt, liegen meist *alle* Vorschlaege
    #: in der verlangten Richtung. „3 von 3 kommen am nächsten" klingt dann
    #: nach einer Einschraenkung, die es nicht gibt.
    "lage_naehe_alle": {
        "de": "Kein Frame zeigt das Motiv genau {lage}. Alle Vorschläge "
              "liegen aber in dieser Richtung.",
        "en": "No frame shows the subject exactly {lage}. All proposals do "
              "lie in that direction, though.",
    },
    "lage_naehe_eins": {
        "de": "Kein Frame zeigt das Motiv genau {lage}. 1 von {gesamt} kommt "
              "dieser Richtung am nächsten.",
        "en": "No frame shows the subject exactly {lage}. 1 of {gesamt} comes "
              "closest to that direction.",
    },

    #: Trenner *und* Beschriftung des Adressfeldes in einem. Getrennt kostete
    #: das zwei Zeilen, und die Einstellungen darunter rutschten auf einem
    #: 13-Zoll-Schirm unter den Rand.
    "oder_adresse": {"de": "oder Adresse eines vorhandenen Videos",
                     "en": "or address of an existing video"},

    # --- Erweitert ---------------------------------------------------------
    "erweitert": {"de": "Erweitert", "en": "Advanced"},
    "quellurl": {"de": "Adresse eines vorhandenen Videos",
                 "en": "Address of an existing video"},
    "schaerfe": {"de": "Schärfe-Schwelle", "en": "Sharpness threshold"},
    "schaerfe_hilfe": {
        "de": "Anteil der Frames, der nach Schärfe weiterkommt. Runterdrehen, "
              "wenn der Standardfilter zu viel wegwirft.",
        "en": "Share of frames that pass the sharpness filter. Turn it down "
              "when the default discards too much.",
    },
    "zwischenstufen": {"de": "Zwischenstufen anzeigen", "en": "Show intermediate steps"},
    "transkript": {"de": "Tonspur auswerten", "en": "Use the audio track"},
    "transkript_hilfe": {
        "de": "Transkribiert das Video und gibt den Text als Kontext mit. Hilft "
              "bei Material, in dem gesprochen wird. Bei Musik oder Atmo wird "
              "es verworfen.",
        "en": "Transcribes the video and passes the text along as context. "
              "Helps with material where someone speaks. Music or ambience "
              "is discarded.",
    },
    "start": {"de": "Analyse starten", "en": "Start analysis"},

    #: Headline und Beschreibung sind freiwillig. Der Hinweis sagt, was man
    #: sich mit dem Weglassen einhandelt -- und laesst sich wegklicken.
    #: Kurz gehalten. Der Hinweis steht direkt unter den beiden Feldern, der
    #: Bezug ist also klar -- und drei Zeilen kosteten 77 px in einer Spalte,
    #: die ohne Scrollen auf einen 13-Zoll-Schirm passen soll.
    "hinweis_felder": {
        "de": "Beides ist freiwillig — verbessert die Auswahl aber deutlich.",
        "en": "Both are optional — but they improve the selection considerably.",
    },
    "hinweis_weg": {"de": "Hinweis schließen", "en": "Dismiss this note"},

    # --- Sichtungsbereich --------------------------------------------------
    "leer_titel": {"de": "Noch nichts zu sichten", "en": "Nothing to review yet"},
    "leer_text": {
        "de": "Lege ein Video ab und starte die Analyse. Die Vorschläge "
              "erscheinen hier.",
        "en": "Drop a video and start the analysis. The proposals will "
              "appear here.",
    },
    "fertig": {"de": "Analyse fertig", "en": "Analysis complete"},
    "frames": {"de": "Frames", "en": "frames"},
    "kandidaten": {"de": "Kandidaten", "en": "candidates"},
    "herkunft": {"de": "Herkunft", "en": "Origin"},
    "herkunft_hilfe": {
        "de": "Feine Striche sind verworfene Kandidaten, Messingmarken die "
              "Vorschläge.",
        "en": "Thin strokes are discarded candidates, brass marks are the "
              "proposals.",
    },
    "sichern": {"de": "Thumbnail sichern", "en": "Save thumbnail"},
    "neue": {"de": "{anzahl} neue Vorschläge", "en": "{anzahl} new proposals"},
    "neue_hilfe": {
        "de": "Nutzt die vorhandene Bewertung — ohne neue Videoverarbeitung "
              "und ohne weitere Modellkosten.",
        "en": "Uses the scoring that already exists — no reprocessing and no "
              "further model cost.",
    },
    "wird_neu_gewaehlt": {"de": "Wird neu gewählt", "en": "Choosing again"},
    "herunterladen": {"de": "Herunterladen", "en": "Download"},

    # --- Verlauf -----------------------------------------------------------
    "verlauf": {"de": "Verlauf", "en": "History"},
    "verlauf_leer": {
        "de": "Noch keine früheren Analysen.",
        "en": "No earlier analyses yet.",
    },
    "verlauf_hilfe": {
        "de": "Frühere Analysen. Anklicken holt die Vorschläge zurück — ohne "
              "neue Verarbeitung und ohne Kosten.",
        "en": "Earlier analyses. Click one to bring its proposals back — no "
              "reprocessing and no cost.",
    },
    "ohne_headline": {"de": "Ohne Headline", "en": "No headline"},
    "verlauf_weg": {
        "de": "Dieser Eintrag ist abgelaufen.",
        "en": "This entry has expired.",
    },
    "mit_transkript": {"de": "mit Tonspur", "en": "with audio"},

    # --- Zustände und Fehler ----------------------------------------------
    "wird_gestartet": {"de": "Wird gestartet", "en": "Starting"},
    "uebertragung": {"de": "Video wird übertragen — {prozent} %",
                     "en": "Uploading video — {prozent} %"},
    "fehler_titel": {"de": "Das hat nicht geklappt", "en": "That did not work"},
    "erneut": {"de": "Erneut versuchen", "en": "Try again"},
    "fehler_anfrage": {
        "de": "Die Anfrage ist nicht durchgekommen. Versuche es erneut.",
        "en": "The request did not get through. Try again.",
    },
    "fehler_kein_video": {
        "de": "Das ist keine Videodatei. Lege eine MP4-, MOV- oder WebM-Datei ab.",
        "en": "That is not a video file. Drop an MP4, MOV or WebM file.",
    },
    "fehler_upload": {
        "de": "Das Video ließ sich nicht vollständig übertragen. Prüfe die "
              "Verbindung und versuche es erneut.",
        "en": "The video could not be transferred completely. Check your "
              "connection and try again.",
    },
    "fehler_leer": {
        "de": "Es kamen keine Vorschläge zurück.",
        "en": "No proposals came back.",
    },
    "rueckfall": {
        "de": "Die Bewertung hat nichts geliefert. Diese Auswahl kam technisch "
              "zustande, nicht inhaltlich — gleichmäßig über das Video "
              "verteilte Frames.",
        "en": "The scoring returned nothing. This selection was made on "
              "technical grounds, not on content — frames spread evenly "
              "across the video.",
    },
    "erschoepft": {
        "de": "Alle Kandidaten waren durch. Die Auswahl beginnt wieder von vorn.",
        "en": "All candidates had been shown. The selection starts over.",
    },

    # --- Stufen (Fortschritt) ---------------------------------------------
    "stufe_wartet": {"de": "Wird gleich gestartet", "en": "Starting shortly"},
    "stufe_position": {"de": "Position {n} in der Warteschlange",
                       "en": "Position {n} in the queue"},
    "stufe_laedt": {"de": "Video wird bereitgestellt", "en": "Preparing the video"},
    "stufe_transkribiert": {"de": "Tonspur wird ausgewertet",
                            "en": "Reading the audio track"},
    "stufe_extrahiert": {"de": "Frames werden extrahiert", "en": "Extracting frames"},
    "stufe_filtert": {"de": "Kandidaten werden gefiltert", "en": "Filtering candidates"},
    "stufe_bewertet": {"de": "Kandidaten werden bewertet", "en": "Scoring candidates"},
    "stufe_exportiert": {"de": "Vorschläge werden zugeschnitten",
                         "en": "Cropping proposals"},
    "stufe_fertig": {"de": "Analyse fertig", "en": "Analysis complete"},
    "stufe_fehler": {"de": "Fehler", "en": "Error"},

    # --- Meldungen der Schnittstelle --------------------------------------
    "api_nicht_angemeldet": {"de": "Nicht angemeldet.", "en": "Not signed in."},
    "api_job_weg": {"de": "Diesen Job gibt es nicht mehr.",
                    "en": "That job no longer exists."},
    "api_vorschlag_weg": {"de": "Diesen Vorschlag gibt es nicht.",
                          "en": "That proposal does not exist."},
    "api_bild_abgelaufen": {
        "de": "Dieses Bild ist abgelaufen. Starte die Analyse erneut.",
        "en": "This image has expired. Start the analysis again.",
    },
    "api_laeuft_noch": {"de": "Die Analyse läuft noch. Warte, bis sie fertig ist.",
                        "en": "The analysis is still running. Wait until it finishes."},
    "api_kandidaten_weg": {
        "de": "Die Kandidaten dieses Jobs sind abgelaufen. Starte die Analyse erneut.",
        "en": "The candidates for this job have expired. Start the analysis again.",
    },
    "api_beides": {
        "de": "Lade entweder ein Video hoch oder trage eine Adresse ein — "
              "beides zusammen geht nicht.",
        "en": "Either upload a video or enter an address — not both at once.",
    },
    "api_format": {"de": "Unbekanntes Format.", "en": "Unknown format."},
    "api_motivlage": {"de": "Unbekannte Motivlage.", "en": "Unknown subject position."},
    "api_anzahl": {"de": "Es sind 3 oder 5 Vorschläge möglich.",
                   "en": "Three or five proposals are possible."},
    "api_upload_unvollstaendig": {
        "de": "Der Upload ist noch nicht vollständig angekommen. Warte einen "
              "Moment und versuche es erneut.",
        "en": "The upload has not fully arrived yet. Wait a moment and try again.",
    },
    "api_zu_gross": {
        "de": "Die Datei ist größer als {mb} MB. Kürze das Video oder "
              "exportiere es kleiner.",
        "en": "The file is larger than {mb} MB. Shorten the video or export "
              "it smaller.",
    },
    "api_headline_lang": {
        "de": "Die Headline geht nicht durch: sie ist zu lang (höchstens 120 Zeichen).",
        "en": "The headline does not pass: it is too long (120 characters at most).",
    },
    "api_beschreibung_lang": {
        "de": "Die Beschreibung geht nicht durch: sie ist zu lang "
              "(höchstens 500 Zeichen).",
        "en": "The description does not pass: it is too long (500 characters "
              "at most).",
    },
    "api_eingabe": {
        "de": "Eine der Angaben passt nicht. Prüfe die Eingaben und versuche "
              "es erneut.",
        "en": "One of the entries does not fit. Check them and try again.",
    },
    "api_neustart": {
        "de": "Der Dienst wurde neu gestartet. Starte die Analyse erneut.",
        "en": "The service was restarted. Start the analysis again.",
    },
    "api_verarbeitung": {
        "de": "Bei der Verarbeitung ist etwas schiefgegangen. Starte die "
              "Analyse erneut.",
        "en": "Something went wrong during processing. Start the analysis again.",
    },
}

#: Diese Schluessel gehen an den Browser. Bewusst eine Auswahl statt des
#: ganzen Katalogs -- was nur die Vorlagen brauchen, muss nicht mitgeliefert
#: werden.
FUER_BROWSER = (
    "fertig", "frames", "kandidaten", "herkunft", "herkunft_hilfe", "sichern",
    "neue", "neue_hilfe", "wird_neu_gewaehlt", "mit_transkript",
    "wird_gestartet", "uebertragung", "fehler_titel", "erneut",
    "fehler_anfrage", "fehler_kein_video", "fehler_upload", "fehler_leer",
    "rueckfall", "erschoepft", "leer_titel", "leer_text",
    "herunterladen", "verlauf", "verlauf_leer", "verlauf_hilfe",
    "ohne_headline", "verlauf_weg", "motivlage", "lage_neu",
    "lage_keiner", "lage_teils", "lage_teils_eins",
    "lage_naehe", "lage_naehe_eins", "lage_naehe_alle", "motiv_kurz",
    "lage_anzahl_keine", "lage_anzahl_eins", "lage_anzahl",
    *(f"lage_{z}" for z in (
        "egal", "oben_links", "oben_mitte", "oben_rechts",
        "mitte_links", "mitte", "mitte_rechts",
        "unten_links", "unten_mitte", "unten_rechts", "kein_klares_motiv")),
)


def sprache_aus(request: Request) -> str:
    """Deutsch, bis jemand ausdruecklich umschaltet.

    Bewusst **ohne** Auswertung von Accept-Language: Ein deutschsprachiger
    Nutzer mit englisch eingestelltem Browser -- verbreitet -- bekaeme sonst
    eine englische Oberflaeche, obwohl Deutsch die Vorgabe sein soll. Die
    Umschaltung ist sichtbar in der Kopfleiste; das reicht und ist
    vorhersagbar.
    """
    keks = request.cookies.get(COOKIE)
    return keks if keks in SPRACHEN else VORGABE


def text(schluessel: str, sprache: str = VORGABE, **werte) -> str:
    eintrag = TEXTE.get(schluessel, {})
    roh = eintrag.get(sprache) or eintrag.get(VORGABE) or schluessel
    try:
        return roh.format(**werte)
    except (KeyError, IndexError):
        return roh


def katalog(sprache: str) -> dict[str, str]:
    return {k: text(k, sprache) for k in FUER_BROWSER}


def katalog_json(sprache: str) -> str:
    return json.dumps(katalog(sprache), ensure_ascii=False)


class Uebersetzer:
    """Wird den Vorlagen als `t` gereicht: {{ t.headline }}."""

    def __init__(self, sprache: str) -> None:
        self.sprache = sprache

    def __getattr__(self, schluessel: str) -> str:
        return text(schluessel, self.sprache)

    def __call__(self, schluessel: str, **werte) -> str:
        return text(schluessel, self.sprache, **werte)
