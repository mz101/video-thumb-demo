"""Der Kalibriersatz: vier Videos mit festen Eingaben.

Damit sind Läufe untereinander vergleichbar. Wer Schwellwerte oder Prompt
ändert, lässt das hier erneut laufen und stellt die Kontaktbögen daneben.

    .venv/bin/python -m werkzeug.testlauf
    .venv/bin/python -m werkzeug.testlauf --tiefe gruendlich
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loupe import config, pipeline          # noqa: E402
from loupe.config import Lauf               # noqa: E402

FAELLE = [
    {
        "datei": "01_nature_svahken.webm",
        "headline": "Wo das Wasser die Zeit misst",
        "beschreibung": (
            "Ruhige Naturaufnahmen aus dem Rentiergebiet Svahken Sijte im "
            "Femunden-Nationalpark, Norwegen. Zu sehen sind Flussläufe, Nebel über "
            "Wasser, Birkenwald und weite Fjellandschaft. Der stärkste Moment sind "
            "die Nahaufnahmen von strömendem Wasser."
        ),
        "art": "ruhiges Material, metaphorische Headline",
    },
    {
        "datei": "02_fossilien.webm",
        "headline": "Wie entstehen Fossilien?",
        "beschreibung": (
            "Erklärvideo über Fossilienbildung. Zu sehen sind Grafiken von "
            "Sedimentschichten, versteinerte Muscheln und Ammoniten in Nahaufnahme "
            "sowie Animationen, wie ein Tierkörper im Schlamm eingebettet wird. Der "
            "stärkste Moment ist die Nahaufnahme eines freigelegten Ammoniten."
        ),
        "art": "geschnittener Beitrag",
    },
    {
        "datei": "03_christchurch.webm",
        "headline": "Christ Church Cathedral: 1000 Jahre Dublin",
        "beschreibung": (
            "Rundgang durch die Christ Church Cathedral in Dublin. Zu sehen sind das "
            "gotische Mittelschiff, Steinbögen, Buntglasfenster und die Krypta. Der "
            "stärkste Moment ist der Blick das Mittelschiff hinauf."
        ),
        "art": "Schwenks, niedrig aufgelöst",
    },
    {
        "datei": "04_kodak16mm_australia.webm",
        "headline": "Australiens Natur auf 16-mm-Film",
        "beschreibung": (
            "Naturdokumentation auf Kodak-16-mm-Film. Zu sehen sind "
            "Küstenlandschaften, Eukalyptuswald, Vögel und Reptilien in Nahaufnahme. "
            "Sichtbares Filmkorn. Der stärkste Moment sind die Tieraufnahmen."
        ),
        "art": "Filmscan mit Korn, hochauflösend",
    },
]


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="testlauf")
    p.add_argument("--tiefe", choices=["schnell", "gruendlich"], default="schnell")
    p.add_argument("--format", choices=list(config.FORMATE), default="16:9")
    p.add_argument("--nur", help="Teilstring des Dateinamens")
    a = p.parse_args(argv)

    for fall in FAELLE:
        if a.nur and a.nur not in fall["datei"]:
            continue
        video = config.ROOT / "testvideos" / fall["datei"]
        if not video.exists():
            print(f"  fehlt: {video}", file=sys.stderr)
            continue

        print(f"\n=== {fall['datei']}  ({fall['art']})")
        lauf = Lauf(
            video=video,
            headline=fall["headline"],
            beschreibung=fall["beschreibung"],
            tiefe=a.tiefe,
            format=a.format,
            ausgabe=config.ROOT / "ausgabe" / video.stem,
        )
        lauf.ausgabe.mkdir(parents=True, exist_ok=True)
        erg = pipeline.voll(lauf, melden=lambda t: None)
        for rang, b in enumerate(erg.auswahl, 1):
            print(f"  {rang}. {b.kandidat.zeitcode}  {b.gesamt:5.1f}  {b.begruendung[:78]}")
        print(f"  {erg.protokoll['zeit_gesamt_s']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
