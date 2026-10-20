# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""IngeTrazo Croquis: the view of the model as a freehand sketch on paper.

An extension for IngeTrazo (setup(app), docs/plugins.md): a «Croquis» tab
in the side tray that draws the current view with the hand of an architect
sketching: ink lines; the materials' colours in the nearest marker of the
box; light, shade and cast shadows in grey marker or in watercolour
washes, all a little off the lines; the shade hatched in ink; and the
sheet composed as a sketcher does: colour that fades out toward the
edges, construction lines, strokes on the ground.

Install: copy the ``croquis`` folder into IngeTrazo's plugins folder
(Extensions ▸ Open plugins folder) and restart IngeTrazo.
"""
from __future__ import annotations

__version__ = "0.12.0"


def setup(app) -> None:
    from .panel import CroquisPanel
    from .texts import tr
    panel = CroquisPanel(app)
    dock = app.add_panel("Croquis", panel)
    app.add_overlay(lambda viewport, painter: panel.live.paint(viewport, painter))
    app.add_menu_action("Croquis…", lambda: (app.show_panel(dock), panel.draw()),
                        tip=tr("Draw a freehand sketch of the current view."))
