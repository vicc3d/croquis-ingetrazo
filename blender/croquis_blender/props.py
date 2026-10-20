# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The panel's settings, kept with the scene (saved in the .blend): the
same choices as in IngeTrazo, with the same ranges and ready-made styles."""

import bpy
from bpy.props import (BoolProperty, EnumProperty, IntProperty,
                       PointerProperty, StringProperty)

from .core import presets as ps

STYLES = [(k, label, "") for k, (label, _c) in ps.PRESETS.items()] + [
    ("custom", "Custom", "Your own choices")]
TECHNIQUES = [("marker", "Marker", "Strokes of alcohol marker"),
              ("watercolour", "Watercolour", "Washes of watercolour"),
              ("ink", "Ink only", "Lines only, no colour")]
LIGHTS = [("classic", "Classic", "From the upper left, as a sketcher draws"),
          ("sun", "Sun", "The scene's Sun lamp")]
MATERIALS = [("colour", "Colour", "Each material in the nearest marker"),
             ("greys", "Greys", "Each material by how light it is"),
             ("contrast", "Contrast", "Light and shade only, the shade near black"),
             ("none", "None", "No material colour")]
SIZES = [("1600", "S", "1600 pixels wide"), ("2400", "M", "2400 pixels wide"),
         ("3600", "L", "3600 pixels wide"), ("0", "Custom", "A width of your own")]

_applying = False


def _papers():
    from .core import paper as pp
    return [(k, label, "") for k, (label, _rgb) in pp.PAPERS.items()] + [
        ("custom", "Your image", "An image of your own")]


def _as_dict(s) -> dict:
    """The settings as the plain dict Croquis's styles read."""
    out = {k: getattr(s, k) for k in ps.DEFAULTS if hasattr(s, k)}
    out["size"] = int(s.size)
    return ps.clean(out)


def _on_style(self, _context) -> None:
    global _applying
    if _applying or self.preset == "custom":
        return
    _applying = True
    try:
        for k, v in ps.PRESETS[self.preset][1].items():
            if hasattr(self, k):
                setattr(self, k, v)
    finally:
        _applying = False


def _on_choice(self, _context) -> None:
    """Touching a style's choice makes the drawing «Custom»."""
    global _applying
    if _applying:
        return
    _applying = True
    try:
        self.preset = ps.matching_preset(_as_dict(self))
    finally:
        _applying = False


def _b(name, default, desc=""):
    return BoolProperty(name=name, default=default, description=desc,
                        update=_on_choice)


def _i(name, key, desc="", subtype="NONE"):
    lo, hi = ps.RANGES[key]
    return IntProperty(name=name, default=ps.DEFAULTS[key], min=lo, max=hi,
                       description=desc, subtype=subtype)


class CroquisSettings(bpy.types.PropertyGroup):
    preset: EnumProperty(name="Style", items=STYLES, default=ps.DEFAULTS["preset"],
                         update=_on_style)
    # Line
    hand: _i("Hand", "hand", "From a ruler (0) to a loose hand (100)", "PERCENTAGE")
    outlines: _b("Outlines", True, "Outlines heavier than the edges inside")
    twice: _b("Twice", True, "Some lines drawn twice")
    breaks: _b("Breaks", True, "Long lines broken where the pen was lifted")
    # Technique, light, materials
    technique: EnumProperty(name="Technique", items=TECHNIQUES,
                            default=ps.DEFAULTS["technique"], update=_on_choice)
    light: EnumProperty(name="Light", items=LIGHTS, default=ps.DEFAULTS["light"])
    shadows: _b("Shadows", True, "Cast shadows, on the model and the ground")
    materials: EnumProperty(name="Materials", items=MATERIALS,
                            default=ps.DEFAULTS["materials"], update=_on_choice)
    ink_texture: _b("Dry brush", False, "High contrast: the black breaks up at its edges")
    natural: BoolProperty(name="Natural variation", default=False,
                          description="Each area of colour or hatching its own slant")
    # Hatching
    hatching: _b("Hatching in the shade", False, "Hatch the shade in ink")
    hatch_along: _b("Along the faces", True, "Along each face (off: one diagonal)")
    hatch_turn: _i("Turn", "hatch_turn", "Turn the hatching", "NONE")
    # Composition
    unfinished: _b("Free edges", True, "The colour thins out toward the edges")
    construction: _b("Construction", True, "Some lines run on as construction lines")
    ground: _b("Ground", False, "Loose strokes on the ground")
    # Fine settings
    weight: _i("Line weight", "weight")
    overshoot: _i("Overshoot", "overshoot")
    offset: _i("Off the lines", "offset")
    nib: _i("Nib", "nib")
    strength: _i("Intensity", "strength")
    # Paper and size
    paper: EnumProperty(name="Paper", items=lambda _s, _c: _papers_cached())
    paper_image: StringProperty(name="Image", subtype="FILE_PATH",
                                description="An image of your own as the paper")
    size: EnumProperty(name="Size", items=SIZES, default="2400")
    custom_width: _i("Width", "custom_width", "The drawing's width in pixels", "PIXEL")
    source: EnumProperty(name="From", items=[
        ("camera", "Camera", "The scene's camera, at the render's shape"),
        ("view", "This view", "What the 3D viewport shows")], default="camera")
    show_fine: BoolProperty(name="Fine settings", default=False)


_paper_items: list = []


def _papers_cached():
    # Blender wants the list kept alive while the enum is shown.
    if not _paper_items:
        _paper_items.extend(_papers())
    return _paper_items


def settings_dict(s) -> dict:
    return _as_dict(s)


classes = (CroquisSettings,)


def register() -> None:
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.croquis = PointerProperty(type=CroquisSettings)


def unregister() -> None:
    del bpy.types.Scene.croquis
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
