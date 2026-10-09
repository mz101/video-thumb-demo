# Kalibrierung — Stufe 2 (Extraktion)

Gemessen am 2026-07-28, ffmpeg 8.1.1, Apple Silicon (~5-fache effektive Parallelität).
Maßgeblich für Railway ist die **CPU-Zeit**, nicht die Wanduhr.

## Testmaterial

| Datei | Codec | Auflösung | Dauer | Größe | Gattung |
|---|---|---|---|---|---|
| 01_nature_svahken | VP9 | 1920×1080 @50 | 4:32 | 76 MB | ruhiges Naturmaterial |
| 02_fossilien | VP9 | 1280×720 @50 | 2:45 | 49 MB | geschnittener Erklärbeitrag |
| 03_christchurch | VP8 | 480×360 @29.97 | 3:45 | 13 MB | Kameraschwenks, niedrig aufgelöst |
| 04_kodak16mm_australia | VP9 | 2890×2100 @24 | 3:29 | 238 MB | Filmscan, Korn, hohe Auflösung |

Alle vier innerhalb des 60 s–5 min-Scopes. Alle vier sind Wikimedia-Transkodierungen —
darauf beruht ein Teil der Befunde, siehe Vorbehalt unten.

## Befund 1: `-skip_frame nokey` funktioniert bei VP9 nicht

Der native VP9-Decoder ignoriert die Option. Auf 04 lieferte sie **5026 Frames statt 42**
und dekodierte dabei das gesamte Video.

Bei H.264 arbeitet die Option korrekt (Gegenprobe mit x264-Testclip: 8 Pakete mit
Keyframe-Flag, 8 gelieferte Frames).

**Konsequenz:** Keyframe-Zeitstempel nicht über den Decoder bestimmen, sondern über die
Paket-Flags — `ffprobe -show_entries packet=pts_time,flags`, Zeilen mit `K`. Das
dekodiert überhaupt nichts und dauert 0,1–0,2 s pro Video, codecunabhängig.

## Befund 2: Keyframes liegen hier nicht an Schnittgrenzen

| Datei | Keyframes | Abstand Median | Abstand Max |
|---|---|---|---|
| 01 | 58 | 5,1 s | 5,1 s |
| 02 | 76 | 2,6 s | 2,6 s |
| 03 | 46 | 5,0 s | 5,0 s |
| 04 | 42 | 5,0 s | 5,0 s |

Median gleich Maximum bei allen vier: **festes GOP, kein einziger szenenwechselbedingter
Keyframe.** Die Annahme des Konzepts, Szenenwechsel kämen über den Keyframe-Pass gratis
mit, trägt bei diesem Material nicht.

Auch die Mengenangabe stimmt nicht: 42–76 statt der veranschlagten 100–200.

**Vorbehalt:** Alle vier Dateien sind Web-Transkodierungen mit festem GOP. Material direkt
aus Premiere oder Resolve hat in der Regel Scenecut-Erkennung aktiv und verhält sich
besser. Der Fall ist also der schlechte, nicht der typische — als Kalibriergrundlage
brauchbar, aber nicht verallgemeinerbar.

**Konsequenz:** Die Extraktion darf sich nicht auf Keyframe-Semantik verlassen. Sie zielt
auf eine Kandidatenzahl und füllt bei zu wenigen Keyframes mit gleichmäßiger Abtastung auf.

## Befund 3: Verfahrensvergleich (Video 04, ungünstigster Fall)

| Verfahren | Frames | Wanduhr | CPU-Zeit |
|---|---|---|---|
| A `-skip_frame nokey` (Konzept) | 5026 (defekt) | 52,7 s | 233 s |
| B Voll-Decode + `fps=0.72` | 151 | 39,0 s | 95 s |
| C Input-Seek auf Keyframe-Zeitstempel, `-noaccurate_seek`, 6-fach parallel | 42 | **4,8 s** | **20 s** |
| D 150 exakte Input-Seeks, 6-fach parallel | 150 | 65,1 s | 309 s |

D ist der teuerste Weg: Jeder exakte Seek dekodiert vom vorangehenden Keyframe bis zum
Ziel, im Mittel 2,5 s Material, dazu 150-mal Prozessstart auf eine 238-MB-Datei.
Dichte Abtastung gehört in **einen** Voll-Decode-Durchlauf, nicht in viele Seeks.

**Verfahren C über alle vier:**

| Datei | Frames | Wanduhr | JPEG-Summe |
|---|---|---|---|
| 01 | 58 | 1,5 s | 5,1 MB |
| 02 | 76 | 2,6 s | 5,2 MB |
| 03 | 46 | 0,9 s | 1,3 MB |
| 04 | 42 | 5,4 s | 9,4 MB |

## Nachtrag: Video 05 (AV1, 8:05, Everest/Context News)

Nachgereichtes Testmaterial, 1920×1080 AV1, 484,9 s, 336 MB. Liegt mit 8:05
**ausserhalb** des 5-min-Scopes; nur mit `--ueberlaenge` verarbeitet.

**AV1 funktioniert ohne Anpassung.** Die Paket-Flag-Methode ist tatsaechlich
codecunabhaengig: 48 Keyframes gefunden, Extraktion 1,9 s.

**Laengstes GOP im Satz: 10,2 s Median.** 48 Frames auf 8 Minuten sind
5,9 Frames/min -- der Filter ging entsprechend hungrig hinein (48 → 26 → 20)
und hat kaum gefiltert.

**Verfahrensvergleich fuer das Auffuellen (73 Zusatzframes):**

| Verfahren | Wanduhr | CPU |
|---|---|---|
| 73 exakte Seeks | 20,3 s | 117 s |
| Voll-Decode + `fps=0.25` (121 Frames) | 43,5 s | 114 s |

Das widerspricht dem Befund von Video 04, wo Seeks dreimal so teuer waren wie
der Voll-Decode. **Nicht das Verfahren entscheidet, sondern die Aufloesung:**
Bei 2890×2100 ist das Vorwaertsdekodieren nach dem Seek teuer, bei 1920×1080
kostet es dasselbe wie ein Voll-Decode. Die Wanduhr-Differenz ist reine
Parallelisierbarkeit (610 % gegen 286 % CPU-Auslastung) und verschwindet auf
Railway mit zwei vCPU.

Beide Wege kosten ~115 s CPU gegen 20 s fuer die Keyframes allein. **Fuer den
Schnellmodus ist Auffuellen auf Wunschdichte damit keine Option** -- es
spraengte die 45-s-Marke. Wer dichtere Abtastung braucht, nimmt "gruendlich".

## Behobener Fehler: Auffuellen war wirkungslos

Das Auffuellen lief mit `-noaccurate_seek` und rastete damit auf genau die
Keyframes ein, die es ergaenzen sollte. Die Doubletten warf anschliessend die
Entdopplung weg -- der Schritt kostete Zeit und tat nichts.

Nachgestellt an einem x264-Clip mit `-g 900 -sc_threshold 0` (90 s, **3
Keyframes**): Nach der Korrektur 3 Keyframes plus **37 exakt angesteuerte
Frames**, daraus 20 unterscheidbare Kandidaten. Vorher waeren es drei gewesen.

Solches Material ist nicht exotisch: Lange feste GOPs liefern
Bildschirmaufnahmen, Screencasts und manche Hardware-Encoder.

Exakte Seeks laufen jetzt nur fuer den Nachtrag, die Keyframes weiterhin mit
`-noaccurate_seek`. Kosten im Extremfall oben: 18,1 s fuer 37 Nachtraege.

## Festlegung

**Schnell** = Verfahren C. Keyframe-Zeitstempel aus den Paket-Flags, `-noaccurate_seek`,
parallel. Liegt die Zahl unter 40, mit gleichmäßig verteilten Zeitstempeln auffüllen.
Kosten auf 04: 20 s CPU.

**Gründlich** = Verfahren B. Ein Voll-Decode mit `fps`-Filter auf ~150 Frames.
Kosten auf 04: 95 s CPU — auf Railway realistisch 1,5–2,5 min. So ist es in der UI zu
beziffern, nicht als „etwas länger".

**Skalierung** im selben Aufruf, aber als `scale=min(1280,iw):-2`. Reines `scale=1280:-2`
würde 03 (480×360) hochrechnen — mehr Bytes, kein zusätzliches Bild.

Die Größenordnung der JPEG-Summe (1–10 MB pro Video) bestätigt, dass die Kandidaten auf
das Railway-Volume passen und nicht nach Spaces müssen.
