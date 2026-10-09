"""Statische Sichtungsseiten aus den Laufprotokollen.

Eine Seite je Video: Video oben, die Vorschläge darunter, und die
Herkunftsleiste — jeder Vorschlag als Marke an
der Stelle, aus der er stammt, alle verworfenen Kandidaten als feine Striche.
Klick auf eine Marke springt im Video an diese Stelle. Das ist die Sicht, an
der sich beurteilen lässt, ob die Auswahl wirklich die beste war.

    .venv/bin/python -m werkzeug.seiten
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loupe import config  # noqa: E402

# $ je Million Token (Stand Juli 2026)
PREISE = {
    "gpt-5.6-sol": (5.0, 30.0),
    "gpt-5.6-terra": (2.5, 15.0),
    "gpt-5.6-luna": (1.0, 6.0),
}

ACHSEN_KURZ = {
    "headline_bezug": "Headline",
    "motiv": "Motiv",
    "gesicht": "Gesicht",
    "lesbarkeit": "Lesbar",
    "textflaeche": "Textfläche",
}

STIL = """
:root{
  --room:#1E1D1B; --panel:#292825; --line:#3B3934;
  --ink:#EFECE4; --ink-dim:#9B968C; --brass:#C9A227; --cool:#7392A6;
}
*{box-sizing:border-box}
body{margin:0;background:var(--room);color:var(--ink);
  font:400 15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:36px 24px 80px}
a{color:var(--brass);text-decoration:none}
a:hover{text-decoration:underline}
a:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--brass);outline-offset:3px}

.kopf{border-bottom:1px solid var(--line);padding-bottom:20px;margin-bottom:28px}
.marke{font:500 12px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
  letter-spacing:.16em;color:var(--ink-dim);text-transform:none}
h1{font:600 30px/1.2 system-ui,sans-serif;letter-spacing:-.018em;margin:12px 0 8px;
  font-stretch:95%}
.besch{color:var(--ink-dim);max-width:62ch;margin:0}

.daten{display:flex;flex-wrap:wrap;gap:6px 22px;margin:20px 0 30px;
  font:400 12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ink-dim)}
.daten b{color:var(--ink);font-weight:500}
.warn{color:var(--cool)}

video{width:100%;background:#000;border:1px solid var(--line);display:block}

h2{font:500 13px/1 ui-monospace,monospace;letter-spacing:.12em;color:var(--ink-dim);
  margin:40px 0 16px;text-transform:none}

.karten{display:grid;gap:22px;grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}
.karte{background:var(--panel);border:1px solid var(--line);cursor:pointer;
  transition:border-color .12s ease}
.karte:hover,.karte.an{border-color:var(--brass)}
.karte img{width:100%;display:block}
.karte .txt{padding:13px 15px 16px}
.zeile{display:flex;justify-content:space-between;align-items:baseline;
  font:500 13px/1 ui-monospace,monospace;margin-bottom:9px}
.zeit{color:var(--brass)}
.score{color:var(--ink-dim)}
.grund{color:var(--ink);font-size:13.5px;margin:0 0 12px}
.achsen{display:grid;gap:4px;font:400 11.5px/1.3 ui-monospace,monospace;color:var(--ink-dim)}
.achse{display:grid;grid-template-columns:66px 1fr 26px;gap:8px;align-items:center}
.balken{height:3px;background:var(--line)}
.balken i{display:block;height:100%;background:var(--cool)}

.leiste{margin:26px 0 8px;position:relative;height:52px}
.leiste .spur{position:absolute;left:0;right:0;top:24px;height:3px;background:var(--line)}
.strich{position:absolute;top:20px;width:1px;height:11px;background:var(--ink-dim);
  opacity:.42}
.mark{position:absolute;top:12px;width:3px;height:27px;background:var(--brass);
  margin-left:-1px;cursor:pointer;transition:transform .12s ease,box-shadow .12s ease}
.mark.an{transform:scaleY(1.35);box-shadow:0 0 0 4px rgba(201,162,39,.18)}
.skala{display:flex;justify-content:space-between;
  font:400 11px/1 ui-monospace,monospace;color:var(--ink-dim)}

.fuss{margin-top:46px;padding-top:18px;border-top:1px solid var(--line);
  font-size:13px;color:var(--ink-dim);display:flex;flex-wrap:wrap;gap:20px}

.liste{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(250px,1fr))}
.liste a{display:block;background:var(--panel);border:1px solid var(--line);padding:16px 18px;
  color:var(--ink);text-decoration:none}
.liste a:hover{border-color:var(--brass);text-decoration:none}
.liste .art{color:var(--ink-dim);font-size:12.5px;margin-top:5px}

@media (max-width:620px){.wrap{padding:24px 16px 60px}h1{font-size:24px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

SKRIPT = """
const v=document.querySelector('video');
function paare(){
  document.querySelectorAll('[data-zeit]').forEach(el=>{
    const t=parseFloat(el.dataset.zeit), id=el.dataset.id;
    const partner=()=>document.querySelectorAll('[data-id="'+id+'"]');
    el.addEventListener('mouseenter',()=>partner().forEach(p=>p.classList.add('an')));
    el.addEventListener('mouseleave',()=>partner().forEach(p=>p.classList.remove('an')));
    el.addEventListener('click',()=>{ if(v){ v.currentTime=t; v.play(); } });
    if(el.tagName!=='DIV'||el.classList.contains('mark')){
      el.tabIndex=0;
      el.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){
        e.preventDefault(); if(v){ v.currentTime=t; v.play(); } } });
    }
  });
}
paare();
"""


def _zeitcode(s: float) -> str:
    m, rest = divmod(s, 60)
    return f"{int(m):02d}:{rest:05.2f}"


def _kosten(bewertung: dict) -> str:
    preise = PREISE.get(bewertung.get("modell", ""))
    if not preise or not bewertung.get("input_tokens"):
        return "—"
    ein, aus = preise
    d = bewertung["input_tokens"] / 1e6 * ein + bewertung["output_tokens"] / 1e6 * aus
    return f"{d*100:.2f} ct"


def _achsen(scores: dict) -> str:
    if not scores:
        return ""
    zeilen = []
    for schluessel, label in ACHSEN_KURZ.items():
        w = int(scores.get(schluessel, 0))
        zeilen.append(
            f'<div class="achse"><span>{label}</span>'
            f'<span class="balken"><i style="width:{w}%"></i></span>'
            f'<span>{w}</span></div>'
        )
    return f'<div class="achsen">{"".join(zeilen)}</div>'


def _leiste(d: dict, dauer: float) -> str:
    gewaehlt = {e["id"] for e in d["ergebnis"]}
    striche = "".join(
        f'<span class="strich" style="left:{100*b["zeit"]/dauer:.3f}%"></span>'
        for b in d.get("alle_bewertungen", [])
        if b["id"] not in gewaehlt
    )
    marken = "".join(
        f'<span class="mark" data-id="{e["id"]}" data-zeit="{e["zeit"]}" '
        f'style="left:{100*e["zeit"]/dauer:.3f}%" role="button" '
        f'aria-label="Vorschlag bei {e["zeitcode"]}"></span>'
        for e in d["ergebnis"]
    )
    return (
        f'<div class="leiste"><span class="spur"></span>{striche}{marken}</div>'
        f'<div class="skala"><span>00:00</span><span>{_zeitcode(dauer)}</span></div>'
    )


def seite(dir: Path, ziel: Path) -> tuple[Path, dict] | None:
    protokoll = dir / "lauf.json"
    if not protokoll.exists():
        return None
    d = json.loads(protokoll.read_text(encoding="utf-8"))

    ex, fi = d.get("extraktion", {}), d.get("filter", {})
    be = d.get("bewertung", {})
    dauer = float(ex.get("dauer_s") or 1)
    video_rel = f"../testvideos/{Path(d['video']).name}"

    exporte = sorted((dir / "vorschlaege").glob("*.jpg"))
    karten = []
    for e, bild in zip(d["ergebnis"], exporte):
        karten.append(
            f'<div class="karte" data-id="{e["id"]}" data-zeit="{e["zeit"]}" '
            f'role="button" tabindex="0">'
            f'<img src="../{bild.relative_to(config.ROOT)}" alt="Vorschlag bei {e["zeitcode"]}">'
            f'<div class="txt"><div class="zeile"><span class="zeit">{e["zeitcode"]}</span>'
            f'<span class="score">{e["gesamt"]:.1f}</span></div>'
            f'<p class="grund">{html.escape(e["begruendung"])}</p>'
            f'{_achsen(e.get("scores", {}))}</div></div>'
        )

    gop = ex.get("gop") or {}
    daten = [
        f'<span><b>{ex.get("quelle","?")}</b> {ex.get("codec","?")}</span>',
        f'<span>{_zeitcode(dauer)}</span>',
        f'<span>Keyframes <b>{ex.get("keyframes","—")}</b>'
        + (" festes GOP" if gop.get("festes_gop") else "") + "</span>",
        f'<span>{ex.get("frames")} Frames → <b>{fi.get("kandidaten")}</b> Kandidaten</span>',
        f'<span>dHash <b>{fi.get("dhash_abstand_final")}</b>'
        + (" gelockert" if fi.get("entdopplung_gelockert") else "") + "</span>",
        f'<span>{be.get("modell","—")}</span>',
        f'<span>{be.get("input_tokens","—")} in / {be.get("output_tokens","—")} out</span>',
        f'<span><b>{_kosten(be)}</b></span>',
        f'<span><b>{d.get("zeit_gesamt_s")} s</b></span>',
    ]
    if d.get("vorschlag_uebernommen") is False:
        daten.append(f'<span class="warn">Gruppenvorschlag verworfen '
                     f'(Mindestabstand {d.get("mindestabstand_s")} s)</span>')
    if d.get("fallback"):
        daten.append('<span class="warn">technischer Rückfall</span>')

    doc = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Loupe — {html.escape(d["headline"])}</title>
<style>{STIL}</style></head><body><div class="wrap">

<div class="kopf">
  <div class="marke">Loupe · {html.escape(Path(d["video"]).stem)}</div>
  <h1>{html.escape(d["headline"])}</h1>
  <p class="besch">{html.escape(d.get("beschreibung", ""))}</p>
</div>

<div class="daten">{"".join(daten)}</div>

<video controls preload="metadata" src="{video_rel}"></video>

<h2>Vorschläge — Format {d.get("format")}</h2>
<div class="karten">{"".join(karten)}</div>

<h2>Herkunft</h2>
{_leiste(d, dauer)}
<p class="besch" style="font-size:13px;margin-top:14px">
Feine Striche sind verworfene Kandidaten, Messingmarken die Vorschläge.
Zeigen oder klicken springt im Video an die Stelle.</p>

<div class="fuss">
  <a href="../{(dir / "01_alle_frames.jpg").relative_to(config.ROOT)}">Kontaktbogen: alle Frames</a>
  <a href="../{(dir / "02_kandidaten.jpg").relative_to(config.ROOT)}">Kontaktbogen: Kandidaten mit Scores</a>
  <a href="../{protokoll.relative_to(config.ROOT)}">lauf.json</a>
  <a href="index.html">Übersicht</a>
</div>

</div><script>{SKRIPT}</script></body></html>"""

    aus = ziel / f"{Path(d['video']).stem}.html"
    aus.write_text(doc, encoding="utf-8")
    return aus, d


def main() -> int:
    ziel = config.ROOT / "ansicht"
    ziel.mkdir(exist_ok=True)

    seiten = []
    for dir in sorted((config.ROOT / "ausgabe").iterdir()):
        if dir.is_dir() and (erg := seite(dir, ziel)):
            seiten.append(erg)
            print(f"  {erg[0].relative_to(config.ROOT)}")

    eintraege = "".join(
        f'<a href="{p.name}"><b>{html.escape(d["headline"])}</b>'
        f'<div class="art">{Path(d["video"]).stem} · {d.get("extraktion",{}).get("quelle","")} '
        f'· {d.get("zeit_gesamt_s")} s · {_kosten(d.get("bewertung",{}))}</div></a>'
        for p, d in seiten
    )
    (ziel / "index.html").write_text(f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Loupe — Kalibriersatz</title><style>{STIL}</style></head>
<body><div class="wrap">
<div class="kopf"><div class="marke">Loupe</div>
<h1>Kalibriersatz</h1>
<p class="besch">Vier Videos, Schnellmodus, Format 16:9, Modell {config.MODELL}.
Jede Seite zeigt Video, Vorschläge und Herkunftsleiste.</p></div>
<div class="liste">{eintraege}</div>
</div></body></html>""", encoding="utf-8")
    print(f"  {(ziel / 'index.html').relative_to(config.ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
