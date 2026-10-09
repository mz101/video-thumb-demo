"""ffprobe-Zugriff: Metadaten und Keyframe-Zeitstempel.

Die Keyframe-Zeitstempel kommen aus den Paket-Flags, nicht aus dem Decoder.
`-skip_frame nokey` ist bei VP9 wirkungslos -- der native Decoder ignoriert
die Option und liefert alle Frames (gemessen: 5026 statt 42). Paket-Flags
dekodieren gar nichts und funktionieren codecunabhaengig.
Siehe kalibrierung/00_extraktion.md, Befund 1.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .meldungen import text


class ProbeFehler(RuntimeError):
    pass


@dataclass
class VideoInfo:
    pfad: Path
    codec: str
    breite: int
    hoehe: int
    dauer: float
    fps: float
    groesse: int

    @property
    def seitenverhaeltnis(self) -> float:
        return self.breite / self.hoehe


def _lauf(args: list[str]) -> str:
    erg = subprocess.run(args, capture_output=True, text=True)
    if erg.returncode != 0:
        raise ProbeFehler(erg.stderr.strip()[:400])
    return erg.stdout


def info(video: Path, sprache: str = "de") -> VideoInfo:
    roh = _lauf([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,r_frame_rate",
        "-show_entries", "format=duration,size",
        "-of", "json", str(video),
    ])
    d = json.loads(roh)
    if not d.get("streams"):
        raise ProbeFehler(text("keine_videospur", sprache))
    s, f = d["streams"][0], d["format"]

    zaehler, _, nenner = s.get("r_frame_rate", "0/1").partition("/")
    fps = float(zaehler) / float(nenner) if float(nenner or 0) else 0.0

    return VideoInfo(
        pfad=video,
        codec=s.get("codec_name", "?"),
        breite=int(s["width"]),
        hoehe=int(s["height"]),
        dauer=float(f["duration"]),
        fps=fps,
        groesse=int(f["size"]),
    )


def keyframe_zeitstempel(video: Path) -> list[float]:
    """Zeitstempel aller Keyframes, aus den Paket-Flags gelesen.

    Dekodiert nichts. Auf den Testvideos 0,1-0,2 s.
    """
    roh = _lauf([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "packet=pts_time,flags",
        "-of", "csv=p=0", str(video),
    ])
    ts: list[float] = []
    for zeile in roh.splitlines():
        teile = zeile.strip().split(",")
        if len(teile) >= 2 and "K" in teile[1]:
            try:
                ts.append(float(teile[0]))
            except ValueError:
                continue
    return sorted(ts)


def gop_kennwerte(ts: list[float]) -> dict[str, float]:
    """Median- und Maximalabstand der Keyframes.

    Sind beide gleich, liegt festes GOP vor -- die Keyframes tragen dann keine
    Szeneninformation. Das war bei allen vier Testvideos der Fall und ist der
    Grund, warum die Extraktion sich nicht auf Keyframe-Semantik verlaesst.
    """
    if len(ts) < 3:
        return {"median": 0.0, "max": 0.0, "festes_gop": 0.0}
    luecken = sorted(ts[i + 1] - ts[i] for i in range(len(ts) - 1))
    median = luecken[len(luecken) // 2]
    groesster = luecken[-1]
    festes_gop = 1.0 if groesster - median < 0.35 else 0.0
    return {"median": round(median, 2), "max": round(groesster, 2), "festes_gop": festes_gop}
