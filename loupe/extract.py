"""Stufe 2: Frames herausholen. Skalierung im selben Aufruf.

Zwei Verfahren, gemessen in kalibrierung/00_extraktion.md:

  schnell     Input-Seek auf die Keyframe-Zeitstempel, -noaccurate_seek,
              parallel. Auf dem 2890x2100-Video 4,8 s / 20 s CPU.
  gruendlich  Ein Voll-Decode mit fps-Filter auf ~150 Frames.
              Auf demselben Video 39 s / 95 s CPU.

Nicht verwendet wird `-skip_frame nokey` (bei VP9 wirkungslos) und ebenso
wenig eine dichte Reihe exakter Seeks: Jeder exakte Seek dekodiert vom
vorangehenden Keyframe bis zum Ziel und ist in Summe teurer als ein einzelner
Voll-Decode (gemessen: 309 s CPU gegen 95 s).
"""

from __future__ import annotations

import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import config, probe
from .meldungen import text


class ExtraktFehler(RuntimeError):
    pass


@dataclass
class Frame:
    index: int
    zeit: float
    pfad: Path


_SKALIERUNG = f"scale=min({config.ARBEITSBREITE}\\,iw):-2"


def _ffmpeg(args: list[str]) -> None:
    erg = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *args],
        capture_output=True, text=True,
    )
    if erg.returncode != 0:
        raise ExtraktFehler(erg.stderr.strip()[:400])


def _ausduennen(ts: list[float], maximum: int) -> list[float]:
    if len(ts) <= maximum:
        return ts
    schritt = len(ts) / maximum
    return [ts[int(i * schritt)] for i in range(maximum)]


def _fehlende_stempel(ts: list[float], dauer: float, ziel: int) -> list[float]:
    """Zeitstempel zwischen den Keyframes, wenn diese zu duenn liegen.

    Fuer Material mit langem GOP. Diese Stempel muessen **exakt** angesteuert
    werden: Mit -noaccurate_seek rasten sie auf den naechstgelegenen Keyframe
    ein und ergaenzen damit genau nichts.

    Exakte Seeks sind teuer -- sie dekodieren vom vorigen Keyframe bis zum Ziel.
    Deshalb wird nur bis zur Untergrenze aufgefuellt, nicht auf Wunschdichte.
    Gemessen an 05 (8 min, GOP 10,2 s): Auffuellen auf 121 Frames kostet 115 s
    CPU gegen 20 s fuer die Keyframes allein. Wer dichtere Abtastung braucht,
    nimmt "gruendlich".
    """
    if len(ts) >= ziel:
        return []
    fehlend = ziel - len(ts)
    return [round(dauer * (i + 0.5) / fehlend, 3) for i in range(fehlend)]


def _seek_extraktion(
    video: Path,
    ziel_dir: Path,
    stempel: list[float],
    exakt: bool = False,
    versatz: int = 0,
) -> list[Frame]:
    def hole(paar: tuple[int, float]) -> Frame | None:
        i, t = paar
        i += versatz
        aus = ziel_dir / f"f{i:04d}.jpg"
        args = [] if exakt else ["-noaccurate_seek"]
        try:
            _ffmpeg([
                *args, "-ss", f"{t:.3f}", "-i", str(video),
                "-frames:v", "1", "-vf", _SKALIERUNG, "-q:v", "3", str(aus),
            ])
        except ExtraktFehler:
            return None
        return Frame(i, t, aus) if aus.exists() else None

    with ThreadPoolExecutor(max_workers=config.EXTRAKT_PARALLEL) as pool:
        ergebnisse = list(pool.map(hole, enumerate(stempel)))

    return [f for f in ergebnisse if f is not None]


def _voll_decode(video: Path, ziel_dir: Path, dauer: float, ziel_anzahl: int) -> list[Frame]:
    rate = max(ziel_anzahl / dauer, 0.05)
    _ffmpeg([
        "-i", str(video),
        "-vf", f"fps={rate:.4f},{_SKALIERUNG}",
        "-q:v", "3", str(ziel_dir / "f%04d.jpg"),
    ])
    dateien = sorted(ziel_dir.glob("f*.jpg"))
    return [Frame(i, (i + 0.5) / rate, p) for i, p in enumerate(dateien)]


class DauerFehler(ExtraktFehler):
    """Video liegt ausserhalb des unterstuetzten Laengenbereichs."""


def _minuten(s: float) -> str:
    m, rest = divmod(int(round(s)), 60)
    return f"{m}:{rest:02d}"


def pruefe_dauer(dauer: float, ueberlaenge: bool = False, sprache: str = "de") -> None:
    if dauer < config.DAUER_MIN_S:
        raise DauerFehler(text("zu_kurz", sprache, dauer=_minuten(dauer)))
    if dauer > config.DAUER_MAX_S and not ueberlaenge:
        raise DauerFehler(text("zu_lang", sprache, dauer=_minuten(dauer),
                               grenze=_minuten(config.DAUER_MAX_S)))


def extrahieren(
    video: Path,
    ziel_dir: Path,
    tiefe: str = "schnell",
    ueberlaenge: bool = False,
    sprache: str = "de",
) -> tuple[list[Frame], dict]:
    """Frames herausholen. Gibt Frames und einen Protokolleintrag zurueck."""
    if shutil.which("ffmpeg") is None:
        raise ExtraktFehler(text("kein_ffmpeg", sprache))

    ziel_dir.mkdir(parents=True, exist_ok=True)
    meta = probe.info(video, sprache)
    pruefe_dauer(meta.dauer, ueberlaenge, sprache)

    if tiefe == "gruendlich":
        frames = _voll_decode(video, ziel_dir, meta.dauer, config.FRAMES_ZIEL_GRUENDLICH)
        protokoll = {"verfahren": "voll_decode", "keyframes": None, "gop": None}
    else:
        keyframes = probe.keyframe_zeitstempel(video)
        gop = probe.gop_kennwerte(keyframes)
        stempel = _ausduennen(keyframes, config.FRAMES_MAX)
        frames = _seek_extraktion(video, ziel_dir, stempel)

        # Nur wenn die Keyframes allein zu duenn liegen, exakt nachsetzen.
        nachtrag = _fehlende_stempel(stempel, meta.dauer, config.FRAMES_MIN_SCHNELL)
        if nachtrag:
            frames += _seek_extraktion(
                video, ziel_dir, nachtrag, exakt=True, versatz=len(stempel)
            )
            frames.sort(key=lambda f: f.zeit)

        protokoll = {
            "verfahren": "keyframe_seek",
            "keyframes": len(keyframes),
            "aufgefuellt": len(nachtrag),
            "frames_pro_minute": round(len(frames) / (meta.dauer / 60), 1),
            "gop": gop,
        }

    if not frames:
        raise ExtraktFehler(text("nichts_lesbar", sprache))

    protokoll.update({
        "frames": len(frames),
        "codec": meta.codec,
        "quelle": f"{meta.breite}x{meta.hoehe}",
        "dauer_s": round(meta.dauer, 1),
    })
    return frames, protokoll
