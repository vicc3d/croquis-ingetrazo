# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""IngeTrazo Croquis: the view of the model as a freehand sketch on paper.

An extension for IngeTrazo (setup(app), docs/plugins.md): a «Croquis» tab
in the side tray that draws the current view with the hand of an architect
sketching, from IngeTrazo's own exact hidden-line drawing. This first
version draws the lines; marker fills, shadows and washes come next.

Install: copy the ``croquis`` folder into IngeTrazo's plugins folder
(Extensions ▸ Open plugins folder) and restart IngeTrazo.
"""
from __future__ import annotations

__version__ = "0.1.0"


def setup(app) -> None:
    from .panel import CroquisPanel
    from .texts import tr
    panel = CroquisPanel(app)
    dock = app.add_panel("Croquis", panel)
    app.add_menu_action("Croquis…", lambda: (app.show_panel(dock), panel.draw()),
                        tip=tr("Draw a freehand sketch of the current view."))
