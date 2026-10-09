# Loupe

<img src="logo/00_handgezeichnet.svg" width="56" align="right" alt="">

Ein Web-Tool, in das man ein Video (1 bis 10 Minuten) sowie Headline und
Kurzbeschreibung gibt und daraus drei Thumbnail-Vorschläge bekommt. Die
Vorschläge sind **echte Frames aus dem Video**, keine erzeugten Bilder.

Der Job ist nicht Bilderzeugung, sondern Auswahl: aus einigen hundert
Kandidaten die drei besten finden.

---

## Aufbau

```
loupe/       Pipeline. Läuft ohne Web und ohne Cloud gegen lokale Dateien.
app/            FastAPI-Anwendung: Endpunkte, Worker, Oberfläche.
werkzeug/       Kalibriersatz und Seitengenerator für die Qualitätsschleife.
kalibrierung/   Belegte Messwerte. Grundlage für jede Schwellwert-Änderung.
```

Die Pipeline kennt die Cloud nicht. `app/` reicht ihr lokale Pfade und legt
die Ergebnisse ab — wer an der Auswahlqualität arbeitet, braucht weder
Railway noch Objektspeicher.

### Stufen

| Stufe | Was passiert | Ergebnis |
|---|---|---|
| 1 Eingang | Video kommt stückweise direkt zur App | — |
| 2 Extraktion | ffmpeg, Skalierung im selben Durchlauf | 40–200 Frames |
| 3 Filter | Schärfe, Belichtung, Entdopplung | ~20 Kandidaten |
| 4 Bewertung | Ein Vision-Call, strukturiertes JSON | Scores je Kandidat |
| 5 Ausgabe | Zuschnitt und Export aufs Volume | 3 oder 5 Vorschläge |

Drei Abweichungen vom ursprünglichen Konzept, jede durch Messung begründet
(siehe `kalibrierung/`):

**Der Zuschnitt läuft vor der Bewertung, nicht danach.** Bei 9:16 fallen 68 %
der Breite weg; das Modell muss beurteilen, was der Nutzer am Ende sieht.
Nachweis: Dasselbe Video liefert bei 16:9 andere Vorschläge als bei 9:16.

**Keyframes kommen aus den Paket-Flags, nicht aus dem Decoder.**
`-skip_frame nokey` ist bei VP9 wirkungslos — gemessen 5026 Frames statt 42.
Die Paket-Flag-Methode dekodiert nichts und funktioniert bei H.264, VP8, VP9
und AV1 gleichermaßen.

**Kein Objektspeicher.** Das Konzept führte „Upload geht am Backend vorbei"
als verbindliche Entscheidung, begründet mit Speicher- und Request-Limits.
Beides trägt nicht: Ein Upload wird stückweise auf die Platte geschrieben, nie
im Speicher gehalten, und Railway begrenzt nicht die Größe eines Requests,
sondern bricht nach fünf Minuten ab. Viele kurze Requests lösen das ohne S3.

Der Umweg kostete außerdem: Jedes Video wurde zweimal übertragen (Browser →
Spaces → Container), die fertigen Thumbnails lagen ohnehin schon auf dem
Volume und wurden nur hochgeladen, um von dort wieder geholt zu werden — und
das Quellvideo lag 28 Tage in Spaces, obwohl es nach der Extraktion nie wieder
gelesen wird. Es wird jetzt sofort verworfen.

---

## Lokal starten

Voraussetzung: Python 3.12 und ffmpeg im `PATH`.

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # ausfüllen
.venv/bin/python -m uvicorn app.main:app --reload --port 8000
```

Die Anwendung liegt dann auf `http://127.0.0.1:8000`. `GET /gesundheit` sagt,
welche Variablen noch fehlen.

### Nur die Pipeline, ohne Web

```bash
.venv/bin/python -m loupe.cli video.mp4 --headline "..." --beschreibung "..."
```

Nützliche Schalter für die Qualitätsschleife:

| Schalter | Wirkung |
|---|---|
| `--no-score` | Nur extrahieren und filtern, kein Modell-Aufruf, keine Kosten |
| `--rescore DIR` | Vorhandenen Kandidatensatz erneut bewerten, ohne Neuverarbeitung |
| `--tiefe gruendlich` | Voll-Decode statt Keyframes, ~150 Frames |
| `--format 9:16` | Zuschnitt und Export |
| `--ueberlaenge` | Videos über 5 Minuten trotzdem verarbeiten |
| `--transkript` | Tonspur auswerten und als Kontext mitgeben (Vorgabe aus) |
| `--sprache en` | Begründungen und Meldungen auf Englisch |
| `--motivlage oben_rechts` | Frames bevorzugen, deren Motiv dort liegt |

Jeder Lauf schreibt nach `ausgabe/<video>/`:
`01_alle_frames.jpg` und `02_kandidaten.jpg` (Kontaktbögen),
`vorschlaege/` und `lauf.json` mit allen Zwischenwerten.

Der Kalibriersatz und die Sichtungsseiten:

```bash
.venv/bin/python -m werkzeug.testlauf
.venv/bin/python -m werkzeug.seiten     # erzeugt ansicht/index.html
```

---

## Eingaben

**Headline und Beschreibung sind freiwillig.** Fehlen sie, weist ein
wegklickbarer Hinweis darauf hin, was das kostet — mehr nicht; die Analyse
läuft trotzdem.

Der Prompt kommt in vier Varianten, je nachdem was vorliegt: beides, nur
Headline, nur Beschreibung, nichts. Ohne Headline gibt es kein Ziel zum
Abgleichen, deshalb geht das Gewicht der Achse `headline_bezug` an Motiv und
Lesbarkeit — die Achsen, die ein Thumbnail auch ohne Zieltext beurteilbar
machen. Das steht in `Lauf.gewichte()` und ist damit kalibrierbar wie alles
andere.

**Der Startknopf trägt seinen Zustand in der Farbe**, nicht nur in der
Deckkraft: Solange kein Video vorliegt, sieht er aus wie die anderen ruhigen
Flächen; sobald eines da ist, wird er grün. Die Farbe ist dann das Signal,
dass es losgehen kann.

Der Ton ist Moos (`#7A9E5B`), kein Signalgrün — er hat annähernd dieselbe
Helligkeit wie das Messing (0,29 gegen 0,38) und gehört damit in dieselbe
gedämpfte Familie. Ein grelles Grün risse den Sichtungsraum auf und stünde in
Konkurrenz zu den Bildern. Schrift darauf 5,4:1, im gesperrten Zustand 5,0:1 —
auch ein nicht anwählbarer Knopf soll lesbar bleiben.

Damit teilen sich die beiden Akzente die Arbeit: **Messing markiert, was
gewählt ist; Grün startet etwas.**

**Alle Schalter liegen ohne Scrollen im sichtbaren Bereich**, auch auf einem
13-Zoll-Schirm. Gemessen bei 1280×720 — der engsten üblichen Desktopgröße:

| Zustand | Unterkante des Startknopfs | Reserve |
|---|---|---|
| leeres Formular | 708 px | 12 px |
| Video gewählt | 670 px | 50 px |

Die Analysetiefe liegt unter *Erweitert*: Sie wird selten umgestellt, und ihr
Hinweistext belastete den knappen Platz zusätzlich. Übrig bleiben zwei Reihen
zu je zwei Steuerungen — Thumbnail-Format neben Motiv im Bild, Anzahl neben
den beiden Kippschaltern. Drei Steuerungen in einer Reihe waren gequetscht:
Die Beschriftungen von „Anzahl Vorschläge" und „Motiv im Bild" liefen
ineinander.

Sobald ein Video gewählt ist, weicht das Ablagefeld der Dateizeile — seine
Aufforderung ist dann erledigt, und die 95 px werden gebraucht.

Was selten gebraucht wird — Adresse statt Upload, Tonspur, Schärfe-Schwelle,
Zwischenstufen — bleibt unter *Erweitert*. Dort ist Scrollen in Kauf genommen;
zugeklappt ist der Normalfall.

Stylesheet und Skript tragen eine Versionsmarke aus den Änderungszeiten
(`/static/app.js?v=…`). Ohne sie liefe nach einem Deploy altes JavaScript
gegen eine neue Schnittstelle.

Nach dem Start springt die Ansicht in den Sichtungsbereich — wer weit unten
im Formular geklickt hat, sähe den Fortschritt sonst nicht. Weiches Scrollen
mit Rückfall auf einen Sprung: Manche Umgebungen führen `behavior: smooth`
nicht aus, und dann bliebe man stehen, wo man war.

**Verlauf.** Unter dem Sichtungsbereich stehen die früheren Analysen mit
Vorschaubild, Headline und Zeitpunkt. Ein Klick holt die Vorschläge zurück —
ohne neue Verarbeitung und ohne Kosten, die Ergebnisse liegen ja im
Job-Datensatz. Angezeigt wird nur, was `AUFBEWAHRUNG_TAGE` überlebt hat.

Die Bildadressen tragen einen `stand`-Parameter und sind damit eindeutig;
deshalb dürfen sie zwischengespeichert werden. Ohne `stand` — etwa von Hand
eingegeben — kann der Inhalt wechseln, dann gilt `no-store`.

---

## Motiv im Bild

Ein Drittelraster in der Schalterreihe, 96 × 60 px mit Zellen von 30 × 18 px:
Wer „oben rechts" wählt, bekommt Frames
bevorzugt, deren Hauptmotiv dort liegt. **Es wird nichts zugeschnitten** — die
Komposition muss der Frame mitbringen. Ein zweiter Klick auf dieselbe Zelle
hebt die Wahl wieder auf.

Kein hartes Filter, sondern ein Aufschlag auf den Gesamtscore: 12 Punkte bei
genauer Übereinstimmung, 5 wenn eine Achse in die gewünschte Richtung zeigt
(„oben rechts" gewünscht, „oben mittig" bekommen). Die Mitte bekommt nie einen
Teilaufschlag — sie ist die Vorgabelage und wäre sonst bei vier von acht
Wünschen im Vorteil, obwohl sie das Gegenteil des Verlangten ist.

**Die Lage wird immer erhoben, auch ohne Wunsch.** Sie ist eine Eigenschaft
des Frames, nicht eine Bewertung gegen den Wunsch. Deshalb lässt sich die
gewünschte Position nachträglich ändern, ohne das Modell erneut zu fragen —
gemessen 41 ms im Container. Wer probieren will, wie „unten links" gegen
„mittig rechts" aussieht, zahlt dafür nichts.

Was das Modell dabei leistet, wurde vor dem Einbau geprüft:

- Eindeutige Testbilder (Scheibe auf ruhigem Grund, Zelle bekannt): 5 von 5.
- Echte Frames, Motiv nachweislich auf einer Seite montiert, Spiegeltest:
  8 von 8 spiegelstimmig, davon 7 mit korrektem links/rechts.
- Unbearbeitete Frames: fast immer „mitte" oder „kein klares Motiv" — weil
  Kameraleute zentrieren. Gemessen über 98 Kandidaten liegen je nach Verfahren
  51 bis 57 % außermittig, aber nur 5 bis 9 % in einer Ecke.

**Ecken bleiben also selten.** Wählt man „oben rechts", greift oft nur der
Teilaufschlag oder gar nichts.

**Dann steht das da.** Der Sichtungsbereich zeigt, wie weit der Wunsch aufging:

| Fall | Hinweis |
|---|---|
| alle Vorschläge treffen | keiner |
| ein Teil trifft | „2 von 3 Vorschlägen zeigen das Motiv mittig rechts. Für die übrigen gab es keinen passenden Frame." |
| keiner trifft | „Kein Frame zeigt das Motiv oben rechts. Gezeigt werden die bestbewerteten Alternativen." |

Auf den Karten steht die **tatsächliche** Lage des Frames, als Eigenschaft
benannt und auf eigener Zeile: „Motiv mittig links". Neben dem Zeitcode war
zu wenig Platz — die Bewertung rutschte um. Ohne das Wort davor las sich die Angabe wie eine
Bestätigung — man hatte „oben links" gewählt und die Karte sagte „mittig
links". Messing bekommt sie nur beim genauen Treffer; dann trägt die Farbe die
Auskunft.

Das Modell nennt die Lage als **Punkt** (x/y in Prozent, kalibriert: 14 von
14 Montagen im richtigen Viertel, Spiegelabweichung ≤ 4). Die Rangfolge geht
über den **Abstand** zur Wunschzelle, gerastert in Kacheln von einer halben
Zellbreite — näher gewinnt, innerhalb einer Kachel entscheidet die Bewertung,
nicht das Koordinatenrauschen. Die Zelle wird nur noch abgeleitet und trägt
Beschriftung und Hinweis.

Nach der Analyse zeigt das Raster als Punktstärke, wo dieses Video überhaupt
Material hat — man wählt nicht mehr blind in eine leere Zelle.

Die Verortung läuft in einem **eigenen Modellaufruf** (in Häppchen von 8,
parallel zur Bewertung): Im großen Bewertungsaufruf verortete das Modell
nachweislich schlampig. Der Aufruf kennt den Wunsch nicht — er beschreibt,
statt zu gefallen. Bei Personen und Tieren zählt der Kopf als Anker.

Ist eine Position markiert, erscheint der Schalter **Priorität**: „Position"
setzt die Nähe zum Wunsch vor die Bewertung, „Qualität" umgekehrt — beides
kostenlos umschaltbar. Und der Schärfefilter füllt Zeitlücken über 1/8 der
Laufzeit wieder auf, damit lange weiche Sequenzen (Animationen) nicht komplett
aus dem Kandidatensatz verschwinden.

Ohne diesen Hinweis sähe die Auswahl aus wie eine Antwort auf die Frage, die
sie gar nicht ist. Drei Fälle: kein Bezug, richtige Richtung ohne genauen
Treffer („naehe"), und ein Teil getroffen. Ohne den mittleren stand „kein
Frame zeigt das Motiv unten rechts" auch dann da, wenn zwei von drei
immerhin rechts lagen. Der Hinweis ist gedämpft gehalten — er meldet eine
Auskunft, keinen Fehlschlag. Die CLI schreibt dieselbe Bilanz in ihren
Bericht.

Bei gesetztem Wunsch tritt der Gruppenvorschlag des Modells zurück. Es
entscheidet über die Position ausdrücklich nicht; würde sein Vorschlag
trotzdem gewinnen, ginge der Wunsch stillschweigend unter.

---

## Sprachen

Die Oberfläche gibt es auf Deutsch und Englisch, umschaltbar in der Kopfleiste.
**Deutsch ist die Vorgabe** — bewusst ohne Auswertung von `Accept-Language`:
Ein deutschsprachiger Nutzer mit englisch eingestelltem Browser bekäme sonst
eine englische Oberfläche. Die Wahl hängt an einem Cookie, nicht am Pfad; die
Adresse eines Jobs ist in beiden Sprachen dieselbe.

Übersetzt ist mehr als die sichtbare Oberfläche:

- Fehlermeldungen der Schnittstelle folgen der Sprache des Anfragenden
  (`app/i18n.py`).
- Meldungen aus der Pipeline — Videodauer außerhalb des Scopes, keine
  Videospur, nichts lesbar — kommen aus `loupe/meldungen.py`.
- **Die Begründungen des Modells** entstehen in der gewählten Sprache. Der
  Bewertungsprompt liegt zweisprachig vor; sonst stünden deutsche Sätze in
  einer englischen Oberfläche.
- Die Fortschrittsstufen werden erst beim Ausliefern übersetzt, in der Sprache
  des Betrachters — nicht in der, die beim Start des Jobs galt.

Ein Katalog für Server und Browser: Was `app.js` an Texten braucht, reicht die
Vorlage als JSON in die Seite. Zwei getrennte Listen laufen sonst auseinander.

---

## Tonspur auswerten (optional, Vorgabe aus)

Der Schalter unter *Erweitert* transkribiert das Video und gibt den Text als
globalen Kontext an die Bewertung. Gedacht für Material, in dem gesprochen wird.

**Vor dem Einbau gemessen** — derselbe Kandidatensatz zweimal bewertet, mit
und ohne Transkript:

| Video | Übereinstimmung | Änderung |
|---|---|---|
| Everest (engl. Doku, Interviews) | 3 von 3 | keine |
| Fossilien (dt. Erklärvideo) | 2 von 3 | dieselbe Einstellung, eine Sekunde später |
| Naturfilm | — | 27 „Wörter", davon alle Notenzeichen |

**Auf die Auswahl wirkt es kaum.** Wo es half, war das Vokabular der
Begründungen: „Ammonitenstruktur" wurde zu „fossiler Pfeilschwanzkrebs".
Diese Sätze stehen im Interface, das ist echter Gewinn — aber ein *globaler*
Effekt, kein zeitlicher.

Deshalb **kein Zeitstempel-Modell**: `whisper-1` liefert Segmentzeiten und
kostet $0,006/min; die zeitliche Zuordnung brachte messbar nichts.
`gpt-4o-mini-transcribe` kostet die Hälfte, kann keine Zeitstempel und holt
den belegten Nutzen. Kosten mit Transkript: **2,2 ct statt 1,5 ct** bei einem
2:45-Video, gegenüber 3,4 ct mit der Zeitstempel-Variante.

Zwei eingebaute Vorbehalte:

- **Tonlose oder musikbespielte Videos werden verworfen.** Unter 15 Wörtern je
  Minute gilt die Tonspur als sprachlos; der Text geht dann gar nicht erst ins
  Prompt. Gemessen am Naturfilm: 0 Wörter, korrekt übersprungen.
- **Bild und Ton fallen bei geschnittenem Material auseinander** — der
  Kommentar spricht über etwas anderes, als zu sehen ist. Der Prompt sagt das
  ausdrücklich, damit das Transkript nicht als Bildbeschreibung gelesen wird.

Offen bleibt die eigentliche Frage: **Talking-Head-Material fehlt weiterhin.**
Dort tragen die Bilder fast keine Unterscheidung, und die Tonspur wäre das
Einzige, was einen Moment vom anderen trennt. Für genau diesen Fall ist der
Schalter gedacht — belegt ist der Nutzen dort noch nicht.

---

## Auf Railway deployen

### 1. Volume anlegen — zuerst, nicht zuletzt

Ohne gemountetes Volume ist das Dateisystem flüchtig. Job-Datenbank,
Kandidaten und fertige Thumbnails wären nach jedem Deploy weg. Seit dem
Wegfall des Objektspeichers hängt alles daran.

Im Railway-Dienst unter **Data → Add Volume**, Mount-Pfad **`/data`**.
Größe: 10 GB reichen für rund 1000 gleichzeitig aufbewahrte Jobs (2–11 MB je
Job). Nachgeprüft: Container zerstört und neu erzeugt — Job, Bilder und
Rerank waren unverändert da.

### 2. Variablen setzen

Alle Schlüssel aus `.env.example` unter **Variables** eintragen, ohne
Anführungszeichen. `PORT` setzt Railway selbst. `DATEN_PFAD` muss `/data`
sein und zum Mount-Pfad passen.

`SECRET_KEY` erzeugen:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Ohne festen Wert werden alle Anmeldungen bei jedem Neustart ungültig.

### 3. Deployen

Railway erkennt das `Dockerfile` und benutzt es statt Nixpacks — nötig, weil
ffmpeg als Systempaket gebraucht wird. Kein Build-Command, kein Start-Command
konfigurieren; beides steht im Dockerfile.

### 4. Prüfen

`GET /gesundheit` liefert `{"status":"ok", ...}` samt `ablage_beschreibbar`,
sobald alles gesetzt und das Volume erreichbar ist.

---

## Betrieb

**Ein gleichzeitiger Job.** ffmpeg ist CPU-gebunden; zwei parallele Läufe auf
einer geteilten CPU machen beide langsam statt einen schnell. Wer wartet,
bekommt seine Position angezeigt. Erst bei mehr als zwei vCPU lohnt
`GLEICHZEITIG=2`.

**Aufräumen** läuft alle sechs Stunden und entfernt Jobs samt
Volume-Verzeichnis nach `AUFBEWAHRUNG_TAGE` (Vorgabe 28) sowie angefangene,
nie beendete Uploads nach `UPLOAD_VERFALL_STUNDEN` (Vorgabe 24).

**Platzbedarf:** 2–11 MB je Job — Kandidaten und Thumbnails. Das Quellvideo
liegt nur während der Verarbeitung da, in einem `TemporaryDirectory`. Bei 20
Jobs am Tag und 28 Tagen Aufbewahrung sind das rund 6 GB.

**Neustart** setzt laufende und wartende Jobs auf Fehler mit der Meldung
„Der Dienst wurde neu gestartet." Kein Job bleibt still hängen.

**Schemaänderungen** werden beim Start automatisch nachgezogen. `CREATE TABLE
IF NOT EXISTS` legt bei einer bestehenden Datenbank nichts an — ein Deploy auf
ein Volume mit älterem Schema scheiterte deshalb einmal beim Start. Die
Migration arbeitet per Introspektion statt Versionszähler: Es ist gleichgültig,
von welchem Stand aus migriert wird, und ein zweiter Aufruf tut nichts.

Nach jeder Schemaänderung gehört der alte Stand in `werkzeug/schema_pruefen.py`
und dieser Lauf zum Pflichtprogramm vor dem Deploy:

```bash
.venv/bin/python -m werkzeug.schema_pruefen
```

### Kosten

Gemessen über fünf Testvideos, je Lauf **~4300 Input- und ~1700 Output-Token**:

| Modell | je Lauf | 1000 Läufe |
|---|---|---|
| `gpt-5.6-luna` | 1,45 ct | 14,51 $ |
| `gpt-5.6-terra` | 3,63 ct | 36,28 $ |
| `gpt-5.6-sol` | 7,26 ct | 72,56 $ |

**Die Kosten hängen nicht an der Videolänge.** Ein 2:45-Video kostet dasselbe
wie ein 8:05-Video, weil der Filter immer bei ~20 Kandidaten landet. Die
Spannweite über alle Läufe war 1,38 bis 1,53 Cent.

Ein zweiter Durchgang („Drei neue Vorschläge") kostet **nichts** — er nutzt
die gespeicherten Achsen-Scores und ruft das Modell nicht erneut auf.
Gemessen: 0,02 Sekunden.

Außer der OpenAI-Rechnung und Railway fallen keine Kosten an. Objektspeicher,
Egress und doppelte Übertragung sind mit dem Umbau entfallen.

### Laufzeit

| | eigene Arbeit | Modell-Aufruf | gesamt |
|---|---|---|---|
| Schnell, 3 min | 3–7 s | 12–16 s | 13–21 s |
| Gründlich, 3 min | 40–95 s | 12–16 s | ~2 min |

Der Modell-Aufruf ist der unbeherrschbare Teil: In einem von fünfzehn Läufen
dauerte er 115 s statt 14 s, bei identischer Tokenzahl. Die
Fortschrittsanzeige benennt deshalb die laufende Stufe, statt einen Balken
ohne Auskunft zu zeigen.

---

## Endpunkte

```
POST /api/uploads               → { upload_id, teilgroesse }
PUT  /api/uploads/{id}/{n}      Stück hochladen (8 MB)
POST /api/jobs                  → { job_id }
GET  /api/jobs/{id}             → { status, stage, progress, results? }
GET  /api/verlauf               → { eintraege }  frühere Analysen
GET  /api/jobs/{id}/vorschlag/{rang}?stand=…[&laden=1]
POST /api/jobs/{id}/rerank      → { job_id }
GET  /gesundheit                → { status, fehlende_konfiguration, ablage }
GET  /sprache/{de|en}           Sprache umschalten, zurück zur Herkunftsseite
```

Der Upload läuft stückweise, weil Railway einen Request nach fünf Minuten
abbricht: Ein 800-MB-Video bei 20 Mbit/s bräuchte 5:20 und scheiterte — nach
fünf Minuten Warten. In 8-MB-Stücken dauert jeder Request Sekunden, und ein
abgerissenes Stück wird einzeln wiederholt statt alles von vorn.

Alle `/api/`-Endpunkte verlangen eine gültige Sitzung. Der Zugangsschutz ist
kein Nutzerkonto-System — er verhindert, dass jeder, der die Adresse kennt,
das OpenAI-Budget verbraucht.

Damit sich das gemeinsame Passwort nicht durchprobieren lässt, sperrt die
Anmeldung nach **fünf Fehlversuchen in 15 Minuten** den Absender, nach
**50 Fehlversuchen insgesamt** alle neuen Anmeldungen — bestehende Sitzungen
laufen weiter. Während der Sperre wird das Passwort gar nicht erst geprüft,
die Antwort ist `429` mit `Retry-After`. Die Zähler liegen im Speicher des
einen Prozesses; ein Neustart leert sie.

Der Job-Zustand liegt in SQLite mit WAL. Status wird gepollt.

---

## Bekannte Grenzen

**Talking-Head-Material ist ungeprüft.** Der Kalibriersatz enthält kein Video
mit einer durchgehend sprechenden Person — genau die Gattung, bei der die
Entdopplung am meisten wegwirft. Der adaptive Filter ist dafür ausgelegt, aber
nicht daran gemessen.

**„Gründlich" ist nicht gegen „Schnell" verglichen.** Ob die ~150 Frames
bessere Vorschläge liefern als die ~50, ist offen.

**Scores sind nur innerhalb eines Laufs vergleichbar.** Dreimal derselbe
Aufruf ergab für denselben Frame 84,8 / 61,3 / 82,4. Deshalb läuft die
Aggregation in Code und der zweite Durchgang aus gespeicherten Werten — das
ist nicht nur billiger, sondern auch stabiler.

**Videos über 10 Minuten** werden abgewiesen. Die Grenze lag zunächst bei 5;
angehoben, weil in der Praxis längere Beiträge anfielen. Was daran hängt: die
Kosten nicht — der Filter landet unabhängig von der Länge bei ~20 Kandidaten.
Die Abtastdichte schon: Bei 10 min und 10 s GOP bleiben 6 Frames je Minute,
und dichteres Abtasten kostet ~115 s CPU statt 20 s. Wer mehr braucht, nimmt
„Gründlich". Die Tonspur-Auswertung kostet linear mit der Länge — bei 10 min
rund 3 ct, also mehr als der Rest des Laufs zusammen.

**Der Name** war bis Juli 2026 „Sichtung". Datenbankdatei, Cookies und
Paketname sind mitgewandert; die alte `sichtung.db` wird beim ersten Start
übernommen, damit auf einem bestehenden Volume keine Jobs verlorengehen.
