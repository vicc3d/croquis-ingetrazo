# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The panel's settings as one plain dict, the ready-made styles, and how
both turn into the drawing's styles.

A style (Ink, Grey marker…) sets the choices that make its look; the hand,
the line weight and the size stay the user's. Touching any of a style's
choices afterwards makes the drawing «Custom».
"""
from __future__ import annotations

import json

from .compose import Composition
from .marker import MarkerStyle
from .paper import PAPERS
from .strokes import LineStyle

DEFAULTS = {
    "preset": "colour_marker",
    "hand": 60, "weight": 20, "overshoot": 100,
    "outlines": True, "twice": True, "breaks": True,
    "technique": "marker",            # marker, watercolour or ink
    "light": "classic", "shadows": True,
    "materials": "colour",            # colour, greys, contrast or none
    "natural": False, "ink_texture": False,
    "hatching": False, "hatch_along": True, "hatch_turn": 0,
    "offset": 12, "nib": 26, "strength": 100,
    "unfinished": True, "construction": True, "ground": False,
    "size": 2400,
    "paper": "cream", "paper_image": "",
    "custom_format": "A4", "custom_width": 3000, "dpi": 300,
}

#: The range the panel lets each number take; settings read back are held
#: to it (a damaged file must not ask for a drawing gigapixels wide).
RANGES = {
    "hand": (0, 100), "weight": (5, 40), "overshoot": (0, 200),
    "offset": (0, 40), "nib": (10, 60), "strength": (20, 150),
    "hatch_turn": (-90, 90), "custom_width": (400, 12000),
}
#: The values the panel offers for each choice; another falls back to the
#: default.
CHOICES = {
    "technique": ("marker", "watercolour", "ink"),
    "light": ("classic", "sun"),
    "materials": ("colour", "greys", "contrast", "none"),
    "size": (1600, 2400, 3600, 0),
    "paper": (*PAPERS, "custom"),
    "custom_format": ("A5", "A4", "A3", "px"),
    "dpi": (150, 300),
}

#: The ready-made styles: what each sets. Key → (label, choices).
PRESETS = {
    "ink": ("Ink", {
        "technique": "ink", "hatching": False, "shadows": True,
        "materials": "none", "outlines": True, "twice": True,
        "unfinished": False, "construction": True, "ground": False}),
    "grey_marker": ("Grey marker", {
        "technique": "marker", "materials": "none", "shadows": True,
        "hatching": False, "outlines": True, "twice": True,
        "unfinished": True, "construction": True, "ground": False}),
    "colour_marker": ("Colour marker", {
        "technique": "marker", "materials": "colour", "shadows": True,
        "hatching": False, "outlines": True, "twice": True,
        "unfinished": True, "construction": True, "ground": False}),
    "watercolour": ("Watercolour", {
        "technique": "watercolour", "materials": "colour", "shadows": True,
        "hatching": True, "hatch_along": False, "outlines": True,
        "twice": True, "unfinished": True, "construction": True,
        "ground": False}),
    "hatched": ("Hatched", {
        "technique": "ink", "hatching": True, "hatch_along": True,
        "shadows": True, "materials": "none", "outlines": True,
        "twice": False, "unfinished": False, "construction": True,
        "ground": True}),
    "contrast": ("High contrast", {
        "technique": "marker", "materials": "contrast", "shadows": True,
        "hatching": False, "outlines": True, "twice": False,
        "unfinished": False, "construction": False, "ground": False,
        "ink_texture": False}),
}


def apply_preset(state: dict, key: str) -> dict:
    out = dict(state)
    out.update(PRESETS[key][1])
    out["preset"] = key
    return out


def matching_preset(state: dict) -> str:
    """The style whose choices the settings still have, or ``custom``."""
    for key, (_label, choices) in PRESETS.items():
        if all(state.get(k) == v for k, v in choices.items()):
            return key
    return "custom"


def clean(raw) -> dict:
    """Settings read back: unknown keys dropped, missing ones defaulted,
    each of its kind."""
    out = dict(DEFAULTS)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    if not isinstance(raw, dict):
        return out
    for k, d in DEFAULTS.items():
        v = raw.get(k, d)
        if isinstance(d, bool):
            out[k] = bool(v)
        elif isinstance(d, int):
            try:
                out[k] = int(v)
            except (TypeError, ValueError):
                out[k] = d
        else:
            out[k] = str(v)
        if k in RANGES:
            lo, hi = RANGES[k]
            out[k] = min(max(out[k], lo), hi)
        if k in CHOICES and out[k] not in CHOICES[k]:
            out[k] = d
    if out["preset"] != "custom" and out["preset"] not in PRESETS:
        out["preset"] = DEFAULTS["preset"]
    return out


def line_style(s: dict) -> LineStyle:
    return LineStyle(hand=s["hand"] / 100.0, width=s["weight"] / 10.0,
                     profile_scale=2.0 if s["outlines"] else 1.0,
                     overshoot=s["overshoot"] / 100.0,
                     double_stroke=s["twice"], breaks=s["breaks"])


def marker_style(s: dict) -> MarkerStyle:
    return MarkerStyle(
        enabled=s["technique"] != "ink",
        medium="watercolour" if s["technique"] == "watercolour" else "marker",
        light=s["light"], offset=float(s["offset"]), width=float(s["nib"]),
        strength=s["strength"] / 100.0, shadows=s["shadows"], colour=True,
        colour_mode=s["materials"], hatching=s["hatching"],
        hatch_along=s["hatch_along"], hatch_turn=float(s["hatch_turn"]),
        natural=s["natural"], ink_texture=s["ink_texture"])


def composition(s: dict) -> Composition:
    return Composition(unfinished=s["unfinished"], construction=s["construction"],
                       ground=s["ground"])
