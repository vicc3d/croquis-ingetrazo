# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Croquis for Blender: the camera's view as an architect's freehand
sketch. The drawing itself is IngeTrazo Croquis's (``core``, copied in
when the extension is built); this package reads the scene for it."""
from . import i18n, ops, props, ui

_modules = (i18n, props, ops, ui)


def register() -> None:
    for m in _modules:
        m.register()


def unregister() -> None:
    for m in reversed(_modules):
        m.unregister()
