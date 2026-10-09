"""Pipeline als CLI: Video rein, Vorschlaege plus Kontaktbogen raus.

    loupe video.mp4 --headline "..." --beschreibung "..."
    loupe video.mp4 --headline "..." --no-score      # ohne Modell-Aufruf
    loupe --rescore ausgabe/video               # nur neu bewerten
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, contact, extract, meldungen, pipeline
from .config import Lauf


def _melder(still: bool):
    def melden(text: str) -> None:
        if not still:
            print(f"  {text}", file=sys.stderr)
    return melden


def _bericht(erg, lauf: Lauf) -> None:
    p = erg.protokoll
    ex = p.get("extraktion", {})
    fi = p.get("filter", {})

    print()
    print(f"  {ex.get('quelle','?')} {ex.get('codec','?')}, {ex.get('dauer_s','?')} s")
    if ex.get("gop"):
        gop = ex["gop"]
        art = "festes GOP" if gop["festes_gop"] else "szenenabhängig"
        print(f"  Keyframes: {ex.get('keyframes')} ({art}, Median {gop['median']} s)"
              + (f", {ex['aufgefuellt']} ergänzt" if ex.get("aufgefuellt") else ""))
    print(f"  {ex.get('frames')} Frames → {fi.get('nach_schaerfe')} nach Schärfe "
          f"→ {fi.get('kandidaten')} Kandidaten"
          + ("  [Entdopplung gelockert]" if fi.get("entdopplung_gelockert") else ""))

    if (tr := p.get("transkript")) and tr.get("genutzt"):
        print(f"  Transkript: {tr['woerter']} Wörter über {tr['minuten']} min "
              f"({tr['modell']})")
    elif tr and tr.get("grund") != "nicht angefordert":
        print(f"  Transkript übersprungen: {tr['grund']}")
    if b := p.get("bewertung"):
        print(f"  Modell {b['modell']}: {b['input_tokens']} in / {b['output_tokens']} out"
              + ("  [mit Transkript]" if b.get("mit_transkript") else ""))
    if (bl := p.get("motivlage_bilanz", {})).get("gewuenscht", "egal") != "egal":
        if bl["stand"] == "genau":
            print(f"  Motivlage {bl['gewuenscht']}: alle {bl['gesamt']} Vorschläge")
        elif bl["stand"] == "teils":
            print(f"  Motivlage {bl['gewuenscht']}: nur {bl['genau']} von "
                  f"{bl['gesamt']} Vorschlägen — für die übrigen gab es keinen "
                  f"passenden Frame")
        else:
            print(f"  Motivlage {bl['gewuenscht']}: kein passender Frame, "
                  f"gezeigt werden die bestbewerteten")
    if p.get("vorschlag_uebernommen") is False and not erg.fallback:
        print("  Gruppenvorschlag verworfen (Mindestabstand), Rangfolge nach Score")
    if erg.fallback:
        print("  ACHTUNG: technischer Rückfall — Auswahl kam nicht inhaltlich zustande")

    print()
    for rang, b in enumerate(erg.auswahl, 1):
        lage = f"  [{b.motivlage}{'  Treffer' if b.lage_stufe == 2 else ('  Richtung' if b.lage_stufe else '')}]" \
            if b.motivlage else ""
        print(f"  {rang}. {b.kandidat.zeitcode}  {b.gesamt:5.1f}{lage}  {b.begruendung}")
    print()
    print(f"  Zeiten: {p.get('zeiten_s')}  gesamt {p.get('zeit_gesamt_s')} s")
    print(f"  → {lauf.ausgabe}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="loupe",
        description="Drei Thumbnail-Vorschläge aus einem Video, plus Kontaktbogen.",
    )
    p.add_argument("video", nargs="?", type=Path)
    p.add_argument("--headline", default="")
    p.add_argument("--beschreibung", default="")
    p.add_argument("--tiefe", choices=["schnell", "gruendlich"], default="schnell")
    p.add_argument("--format", choices=list(config.FORMATE), default="16:9")
    p.add_argument("--anzahl", type=int, choices=[3, 5], default=3)
    p.add_argument("--keine-gesichter", action="store_true",
                   help="Gesichter nicht höher gewichten")
    p.add_argument("--textflaeche", action="store_true",
                   help="Frames mit ruhiger Fläche für Titeltext bevorzugen")
    p.add_argument("--schaerfe-perzentil", type=float, default=config.SCHAERFE_PERZENTIL)
    p.add_argument("--ueberlaenge", action="store_true",
                   help="Videos über 5 min trotzdem verarbeiten")
    p.add_argument("--transkript", action="store_true",
                   help="Tonspur transkribieren und als Kontext mitgeben "
                        "(Vorgabe aus; kostet ~0,3 ct je Minute Video)")
    p.add_argument("--sprache", choices=["de", "en"], default="de",
                   help="Sprache der Begründungen und Meldungen")
    p.add_argument("--motivlage", choices=["egal", *config.MOTIVLAGEN], default="egal",
                   help="Frames bevorzugen, deren Hauptmotiv dort liegt "
                        "(Vorgabe: egal). Kein hartes Filter — findet sich nichts, "
                        "greift die Regel nicht.")
    p.add_argument("--ausgabe", type=Path)
    p.add_argument("--no-score", action="store_true",
                   help="Nur extrahieren und filtern, kein Modell-Aufruf")
    p.add_argument("--rescore", type=Path, metavar="DIR",
                   help="Vorhandenen Kandidatensatz erneut bewerten")
    p.add_argument("--ueberspringen", default="",
                   help="Kennungen, die nicht gewählt werden dürfen (Rerank)")
    p.add_argument("--still", action="store_true")
    a = p.parse_args(argv)

    melden = _melder(a.still)

    if a.rescore:
        return _rescore(a, melden)

    if a.video is None:
        p.error("Ohne --rescore wird ein Videopfad gebraucht.")
    if not a.video.exists():
        print(f"Die Datei {a.video} gibt es nicht.", file=sys.stderr)
        return 2
    ausgabe = a.ausgabe or config.ROOT / "ausgabe" / a.video.stem
    lauf = Lauf(
        video=a.video,
        headline=a.headline,
        beschreibung=a.beschreibung,
        tiefe=a.tiefe,
        format=a.format,
        gesichter_bevorzugen=not a.keine_gesichter,
        textflaeche=a.textflaeche,
        anzahl=a.anzahl,
        schaerfe_perzentil=a.schaerfe_perzentil,
        ueberlaenge=a.ueberlaenge,
        transkript=a.transkript,
        sprache=a.sprache,
        motivlage=a.motivlage,
        ausgabe=ausgabe,
    )
    ausgabe.mkdir(parents=True, exist_ok=True)

    try:
        kandidaten, alle, protokoll = pipeline.verarbeiten(lauf, melden)
    except extract.DauerFehler as e:
        zusatz = meldungen.text("zu_lang_cli", a.sprache) if not a.ueberlaenge else ""
        print(f"\n  {e}{zusatz}\n", file=sys.stderr)
        return 1
    except extract.ExtraktFehler as e:
        print(f"\n  {e}\n", file=sys.stderr)
        return 1

    if a.no_score:
        contact.alle_frames(alle, {k.id for k in kandidaten},
                            ausgabe / "01_alle_frames.jpg")
        (ausgabe / "lauf.json").write_text(
            json.dumps(protokoll, indent=2, ensure_ascii=False), encoding="utf-8")
        fi = protokoll["filter"]
        print(f"\n  {protokoll['extraktion']['frames']} Frames "
              f"→ {fi['kandidaten']} Kandidaten "
              f"(dHash-Abstand {fi['dhash_abstand_final']})")
        print(f"  Zeiten: {protokoll['zeiten_s']}")
        print(f"  → {ausgabe}\n")
        return 0

    erg = pipeline.bewerten_und_waehlen(
        kandidaten, alle, lauf, protokoll,
        ueberspringen=set(filter(None, a.ueberspringen.split(","))),
        melden=melden,
    )
    _bericht(erg, lauf)
    return 0


def _rescore(a, melden) -> int:
    dir = a.rescore
    if not (dir / "kandidaten.pkl").exists():
        print(f"In {dir} liegt kein gesicherter Kandidatensatz.", file=sys.stderr)
        return 2

    kandidaten, alle = pipeline.zwischenstand_lesen(dir)
    alt = json.loads((dir / "lauf.json").read_text(encoding="utf-8"))

    lauf = Lauf(
        video=Path(alt["video"]),
        headline=a.headline or alt.get("headline", ""),
        beschreibung=a.beschreibung or alt.get("beschreibung", ""),
        tiefe=alt.get("tiefe", "schnell"),
        format=a.format,
        gesichter_bevorzugen=not a.keine_gesichter,
        textflaeche=a.textflaeche,
        anzahl=a.anzahl,
        transkript=a.transkript,
        sprache=a.sprache,
        motivlage=a.motivlage,
        ausgabe=dir,
    )
    melden(f"{len(kandidaten)} gesicherte Kandidaten, keine Neuverarbeitung")

    erg = pipeline.bewerten_und_waehlen(
        kandidaten, alle, lauf,
        {**alt, "zeiten_s": {}},
        ueberspringen=set(filter(None, a.ueberspringen.split(","))),
        melden=melden,
    )
    _bericht(erg, lauf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
