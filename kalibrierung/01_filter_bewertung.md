# Kalibrierung — Stufe 3 bis 5 (Filter, Bewertung, Auswahl)

Vier Videos, Modell `gpt-5.6-luna`, Format 16:9, Schnellmodus.
Werte vom 2026-07-28.

## Durchsatz des Filters

| Video | Frames | nach Schärfe | Kandidaten | dHash-Abstand | gelockert |
|---|---|---|---|---|---|
| 01 nature | 58 | 31 | 20 | 14 | nein |
| 02 fossilien | 76 | 41 | 20 | 14 | nein |
| 03 christchurch | 46 | 23 | 18 | 3 | **ja** |
| 04 kodak16mm | 42 | 20 | 20 | 3 | **ja** |

Die zielmengenbasierte Entdopplung arbeitet wie vorgesehen: Bei 03 und 04 —
langsame Schwenks, strukturell fast identische Frames — lockert sie
selbsttätig bis zur Untergrenze, statt den Lauf leerlaufen zu lassen. Das ist
die Talking-Head-Betriebsart, ohne Sonderweg.

03 bleibt mit 18 unter der Zielmenge 20, aber deutlich über `KANDIDATEN_MIN`.
Bei 480×360 gibt das Material nicht mehr her.

`SCHAERFE_PERZENTIL = 0.55` hat auf allen vier gehalten. Kein Lauf brauchte
den Regler aus dem Erweitert-Bereich.

## Laufzeit und Kosten

| Video | Extraktion | Filter | Bewertung | Export | gesamt |
|---|---|---|---|---|---|
| 01 | 2,3 s | 0,9 s | 16,3 s | 1,0 s | 20,5 s |
| 02 | 1,9 s | 1,1 s | 15,8 s | 1,3 s | 20,1 s |
| 03 | 0,7 s | 0,2 s | 11,8 s | 0,3 s | 12,9 s |
| 04 | 4,4 s | 0,9 s | **115,3 s** | 1,3 s | 121,9 s |

Der Ausreißer bei 04 ist **nicht reproduzierbar**: Zwei Wiederholungen
desselben Aufrufs über `--rescore` kamen in 14,1 s und 12,9 s zurück, bei
identischer Tokenzahl. API-Latenzspitze, kein Pipelinefehler.

Das ist die ehrliche Aufteilung: **Eigene Arbeit 3–7 s, Modell-Aufruf 12–16 s
im Normalfall — mit gelegentlichen Ausreißern um den Faktor 8, auf die wir
keinen Einfluss haben.** Die 45-s-Marke hält im Regelfall mit großem Abstand,
aber nicht garantiert. Die Fortschrittsanzeige muss das aushalten.

Verbrauch, über alle Läufe stabil: **~4400 Input-, ~1700 Output-Token.**
Mit Luna sind das **1,5 Cent** pro Lauf — die 3-Cent-Marke hält mit Reserve.
Mit Terra wären es 6,3 Cent, mit Sol 13,3 Cent.

`detail: "low"` ist der Grund für die niedrige Inputzahl: ~200 Token pro Bild
statt der Tausende bei Originalauflösung. Ohne die Angabe würde GPT-5.6
`original` verwenden (`auto` entspricht dort `original`).

## Diversitätsprüfung

Befund: Mit festem Mindestabstand von 6 s passierten bei 01 zwei Vorschläge
im Abstand von **6,4 s** (02:13,13 und 02:19,51) die Prüfung — in einem
4:32-Naturfilm dieselbe Einstellung.

Festlegung: Der Abstand ist laufzeitrelativ, `max(8 s, Dauer/20)`. Bei 01 sind
das 13,6 s. Zusätzlich muss der dHash-Abstand ≥ 8 sein — reiner Zeitabstand
genügt nicht, weil eine fest stehende Kamera nach zwei Minuten wieder dasselbe
Bild liefert. Das Konzept nennt beide Maße; beide sind jetzt aktiv.

Wirkung auf 01: Der Gruppenvorschlag des Modells wurde verworfen, die
Rangfolge nach Gesamtscore lieferte 02:13 / 03:15 / 04:16.

## Verhalten des Modells

**Metaphorische Headline** („Wo das Wasser die Zeit misst", 01): Trägt. Das
Modell zieht die Beschreibung heran und begründet über sie — „macht das Wasser
unmittelbar zum Träger von Zeit". Die befürchtete Schwachstelle
hat sich bei diesem Material nicht gezeigt; die getrennte Rolle von Headline
und Beschreibung im Prompt reicht offenbar aus.

**Score-Niveau ist nicht kalibriert.** 04 (Tieraufnahmen, klare Motive) landet
bei 81–85, 01 (ruhige Landschaft) bei 57–70 — bei ähnlicher subjektiver
Qualität. Die Zahlen sind **innerhalb** eines Laufs vergleichbar, nicht
zwischen Läufen. Für die Auswahl reicht das; als Anzeige im Interface wären
absolute Zahlen irreführend.

**Streuung zwischen Läufen ist erheblich.** Dreimal derselbe Aufruf auf 04
ergab für denselben Frame 84,8 / 61,3 / 82,4. Der dritte Platz wechselte
zwischen zwei Kandidaten. Konsequenz: Der Rerank aus den vorhandenen Scores
ist nicht nur billiger, sondern auch stabiler als ein zweiter Modell-Aufruf.

## Offen

- Kein Talking-Head-Material im Testsatz. Die Gattung, bei der die
  größte Schwachstelle vermutet wird,, ist ungeprüft.
- Alle vier Videos sind Wikimedia-Transkodierungen mit festem GOP. Material
  mit szenenabhängigen Keyframes wurde nicht kalibriert.
- „Gründlich" ist gebaut, aber nicht gegen „Schnell" verglichen — offen, ob
  die ~150 Frames überhaupt bessere Vorschläge liefern als die ~50.

## Motivlage: Aufschlag war der falsche Mechanismus

Gemeldet: drei Screenshots, drei verschiedene Markierungen, jedes Mal
dieselben drei Frames.

Nachgemessen am Regenwald-Video (20 Kandidaten, ein Bewertungslauf, dann
alle neun Wünsche gegen „egal" gehalten):

| | Aufschlag (12/5 Punkte) | Rangstufe |
|---|---|---|
| Wünsche, die die Auswahl ändern | 4 von 9 | 7–8 von 9 |
| meist geänderte Vorschläge | 1 von 3 | 3 von 3 |

Der Grund steht in den Grundwerten: Sie reichen von 21,7 bis 80,7. Über
diese Spanne konnte ein Bonus von 12 Punkten nichts ausrichten — ein Frame
mit der richtigen Lage, aber mittelmäßiger Bewertung kam nie nach oben.

Verlangt war ohnehin etwas anderes: „gibt es kein passendes Thumbnail, so
soll ein Hinweis erscheinen und dann die alternativ besten." Das ist eine
Vorauswahl mit Rückfall, keine Gewichtung. Die Lage bestimmt jetzt die
Stufe (genau / richtige Richtung / kein Bezug), innerhalb der Stufe
entscheidet die Bewertung.

Was das kostet, je nachdem wie selten die gewünschte Lage ist:

| Wunsch | Durchschnittsbewertung | gegen „egal" |
|---|---|---|
| egal | 66,8 | — |
| oben links | 60,8 | −6,0 |
| unten links | 49,3 | −17,5 |
| unten rechts | 44,0 | −22,8 |

Eine verdeckte Mindestqualität wäre falsch: Sie würde genau den Fehler
wiederholen, der gemeldet wurde — die Markierung bliebe wirkungslos, ohne
dass es jemand sieht. Der Hinweis über den Vorschlägen sagt stattdessen,
wenn die Lage nicht genau aufgeht.

## Die obere Zeile fehlt am Material, nicht am Modell

In denselben 20 Kandidaten: 13 mittlere Zeile, 1 unten, **0 oben**, keine
Ecke. Dazu 6 ohne klares Motiv.

Der Verdacht lag nahe, dass das Modell die senkrechte Achse gar nicht
nutzt. Gegentest mit Montagen, bei denen das Motiv nachweislich oben oder
unten sitzt: **12 von 12 richtig zugeordnet**, sechsmal „oben", sechsmal
„unten". Das Modell kann es also. In echtem Material sitzt das Motiv nur
fast immer auf mittlerer Höhe — so wird gefilmt.

Folge für die Bedienung: „oben links" wird selten einen genauen Treffer
finden. Die Stufe „richtige Richtung" fängt das ab, der Hinweis benennt es.

## Koordinaten statt Zellen

Zwei Umbauten, gemeinsam kalibriert:

**Kann das Modell Koordinaten?** Montagen mit dem Motiv nachweislich in
einem Viertel, Original und Spiegelung gemischt im selben Aufruf. Wo das
Modell ein Motiv erkennt: **14 von 14 im richtigen Viertel**,
Spiegelabweichung Median 1, Maximum 4 (von 100). Die Koordinaten sind bei
`detail: low` stabil.

Ein erster Testlauf mass 6 von 16 — Testfehler: Montagen aus vier
*verschiedenen* Szenen lasen sich als Collage ohne Hauptmotiv, das Modell
antwortete anweisungsgemäß „kein klares Motiv" (50/50). Drei Quadranten
mit derselben ruhigen Fläche machen das Motiv eindeutig.

**Rangfolge über Abstandsbänder.** Der Abstand zur Wunschzellmitte,
gerastert in Kacheln von 24 (halbe Zelldiagonale = 23,6, also deckt Band 0
genau die Wunschzelle). Roh sortiert würden 3 Prozentpunkte
Koordinatenrauschen entscheiden; innerhalb einer Kachel entscheidet die
Bewertung. Kandidaten ohne klares Motiv laufen in Band 6 ganz hinten mit.

Wirkung am Regenwald-Video, gleiche Messanlage wie beim Stufen-Umbau:
weiterhin ändern 7 von 9 Wünschen die Auswahl, aber die Qualitätskosten
sinken — maximal −14,5 statt −23,5 im Schnitt, weil „fast richtig" jetzt
zwischen „genau" und „egal wo" liegt statt auf einer der beiden Seiten.

Die Zellgrenze verliert ihre Härte: Ein Motiv bei x=28 ist der Zelle
„mittig links" zugeschrieben, gewinnt aber bei Wunsch „mittig" zu Recht —
es ist fast zentriert. Zelle bleibt Beschriftung, Abstand ist die Wahrheit.

Altläufe ohne Koordinaten (vor dem Umbau) laufen über die Zellmitte als
Ersatzpunkt — die Rangfolge verhält sich dann wie die alte Stufenlogik.

## Das Raster zeigt die Dichte

Nach der Analyse kennt das Protokoll die Lage jedes Kandidaten. Das
3×3-Raster zeigt sie als Punktstärke: kräftig = dort liegen Kandidaten,
blass = leer, Titel mit Anzahl („mittig — 17 Kandidaten"). Man sieht vor
dem Markieren, was das Video hergibt, statt blind zu wählen und einen
Rückfall erklärt zu bekommen. Ohne Ergebnis bleibt das Raster neutral.

## Der Fall „Fisch bei 1:15" — drei Reparaturen und ein Schalter

Gemeldet: Bei 1:15 liegt das Motiv unten links, ausgewählt wurde es nie.
Nachverfolgt durch alle Stationen; der Moment scheiterte an dreien.

**Zeitlücken im Filter.** Das Schärfe-Perzentil rechnet relativ zum Video:
Die gerenderte Unterwassersequenz (Schärfe 12–25) verlor komplett gegen das
Realmaterial (bis 566) — zwischen Sekunde 37 und 81 überlebte kein Frame.
Jetzt wird nach dem Eindampfen jede Lücke über 1/8 der Laufzeit mit dem
schärfsten Frame aus der Lücke gefüllt (max. 4 Füllungen), auch unter der
Schwelle. Am Fossilien-Video: 4 Füllungen, größte Restlücke 21 s.

**Verortung im eigenen Aufruf.** Im Bewertungsaufruf (24 Bilder, Bewertung +
Begründung + Gruppenvorschlag) verortete das Modell den Fisch als „mitte"
(38,55); fokussiert gefragt kam (22,66). Drei Aufgaben konkurrieren um
Aufmerksamkeit. Die Lage wird jetzt in einem eigenen Aufruf erhoben — der
den Wunsch absichtlich nicht kennt — und läuft **parallel** zur Bewertung:
Laufzeit 35,6 s statt 58 s sequenziell, Mehrkosten ~0,3 ct.

**Häppchen von 8.** Auch im eigenen Aufruf pendelte der Kopf-Anker bei 24
Bildern zwischen (25,74) und (43,55) — die Streuung kreuzte die
Entscheidungsgrenze. Mit 8 Bildern je Aufruf (parallel): dreimal
hintereinander Band 0–2 gegen Band 3 der Mitte-Frames. Kopf-Anker im
Prompt („bei Personen und Tieren zählt Gesicht/Auge"): isoliert gemessen
verschiebt er (45,48) → (33,76).

**Kachel 24 → 12.** Mit 24 lagen Fisch (Abstand 26–35) und Bildmitte (47)
im selben Band — die Qualität entschied, die Position verlor. 12 trennt
beide und bleibt beim Dreifachen des gemessenen Rauschens (max. 4).

Ergebnis Ende-zu-Ende: Wunsch „unten links" wählt den Fisch als Treffer
(einmal sogar 3/3 genau), „unten rechts" wählt anders. Der ursprüngliche
Screenshot-Befund — identische Auswahl für beide Ecken — ist damit behoben,
soweit das Material es hergibt.

**Priorität Position/Qualität.** Sichtbar nur bei markierter Position.
„Position": Abstandsband zuerst, Bewertung innerhalb der Kachel.
„Qualität": Bewertung zuerst (8er-Stufen), Nähe zum Wunsch innerhalb der
Stufe. Wechsel ist ein kostenloser Rerank.
