"""Loupe — Thumbnail-Auswahl aus echten Videoframes."""

import sys

__version__ = "0.1.0"

#: Das Paket hiess bis Juli 2026 `sichtung`. Die gesicherten Kandidatensaetze
#: (kandidaten.pkl) liegen auf dem Volume und tragen den damaligen Modulpfad in
#: der Datei -- Pickle speichert ihn mit. Ohne diese Aliasse scheitert der
#: zweite Durchgang eines Jobs von vor der Umbenennung mit
#: `ModuleNotFoundError: No module named 'sichtung'`.
#:
#: Faellt weg, sobald die Aufbewahrungsfrist alle alten Jobs ueberholt hat.
_ALTER_NAME = "sichtung"

if _ALTER_NAME not in sys.modules:
    sys.modules[_ALTER_NAME] = sys.modules[__name__]
    for _teil in ("config", "filtering", "metrics", "extract", "probe",
                  "crop", "scoring", "pipeline", "meldungen", "transkript"):
        try:
            sys.modules[f"{_ALTER_NAME}.{_teil}"] = __import__(
                f"{__name__}.{_teil}", fromlist=[_teil]
            )
        except ImportError:                      # Modul umbenannt oder entfernt
            pass
