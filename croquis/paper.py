# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""The sheet the drawing goes on: a few papers, or an image of your own.

Each paper is its tone and its grain (and, for the ruled ones, its grid),
made at the drawing's size, so it scales with it. An image of your own (a
scanned sketchbook page, a texture) is either repeated, when it is small,
or stretched to cover the sheet, keeping its proportions.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

#: Key → (label, base colour).
PAPERS = {
    "cream": ("Cream", (247, 243, 234)),
    "white": ("White", (252, 252, 250)),
    "kraft": ("Kraft", (198, 172, 134)),
    "grey": ("Toned grey", (208, 207, 202)),
    "tracing": ("Tracing", (236, 240, 240)),
    "grid": ("Squared", (248, 247, 242)),
    "dots": ("Dotted", (248, 247, 242)),
}
#: Below this width an image of your own is repeated, not stretched.
TILE_BELOW = 1000


def _grain(h: int, w: int, seed: int, cell: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    gh, gw = max(2, h // cell + 1), max(2, w // cell + 1)
    g = rng.normal(0.0, 1.0, (gh, gw))
    pad = np.pad(g, 1, mode="edge")
    g = sum(pad[i:i + gh, j:j + gw] for i in range(3) for j in range(3)) / 9.0
    return np.kron(g, np.ones((cell, cell)))[:h, :w]


def _fibres(h: int, w: int, seed: int, n: int) -> np.ndarray:
    """Short darker fibres, as in kraft paper."""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w))
    for _ in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        a = rng.uniform(0, np.pi)
        L = rng.uniform(4, 22)
        t = np.linspace(0, L, int(L) + 1)
        xs = np.clip((x + t * np.cos(a)).astype(int), 0, w - 1)
        ys = np.clip((y + t * np.sin(a)).astype(int), 0, h - 1)
        out[ys, xs] -= rng.uniform(0.3, 1.0)
    return out


def make(kind: str, width: int, height: int, seed: int = 7,
         image: str = "") -> np.ndarray:
    """The sheet, (H, W, 3) floats 0..255."""
    if kind == "custom" and image:
        own = _from_image(image, width, height)
        if own is not None:
            return own
        kind = "cream"
    _label, base = PAPERS.get(kind, PAPERS["cream"])
    h, w = height, width
    rgb = np.array(base, dtype=np.float64)[None, None, :]
    if kind == "kraft":
        tone = 1.0 + 0.05 * _grain(h, w, seed) + 0.04 * _fibres(h, w, seed + 1, (w * h) // 900)
    elif kind == "tracing":
        cloud = _grain(h, w, seed, cell=max(3, w // 30))
        tone = 1.0 + 0.015 * _grain(h, w, seed + 1) + 0.025 * cloud
    elif kind == "white":
        tone = 1.0 + 0.015 * _grain(h, w, seed)
    else:
        tone = 1.0 + 0.035 * _grain(h, w, seed)
    sheet = rgb * tone[:, :, None]
    if kind in ("grid", "dots"):
        step = max(6, int(round(h / 36)))         # about 5 mm on an A4
        ink = np.array((150, 175, 205), dtype=np.float64)
        if kind == "grid":
            lines = np.zeros((h, w), dtype=bool)
            lines[::step, :] = True
            lines[:, ::step] = True
            a = 0.35
        else:
            lines = np.zeros((h, w), dtype=bool)
            r = max(1, step // 12)
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    lines[(step // 2 + dy)::step, (step // 2 + dx)::step] = True
            a = 0.55
        sheet[lines] = sheet[lines] * (1 - a) + ink * a
    return np.clip(sheet, 0, 255).astype(np.float32)


#: Where there is no Qt (Blender), how to read an image of your own:
#: ``path -> (H, W, 3) floats 0..255`` or None. The host sets it.
IMAGE_READER = None


def _from_image(path: str, width: int, height: int):
    """An image of your own as the sheet: repeated when small, else
    stretched to cover it (cropped to keep its proportions)."""
    if not Path(path).is_file():
        return None
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QImage, QPainter
    except ImportError:
        return _from_array(path, width, height)
    src = QImage(path)
    if src.isNull():
        return None
    out = QImage(width, height, QImage.Format_RGB32)
    p = QPainter(out)
    if src.width() < TILE_BELOW:
        from PySide6.QtGui import QBrush
        p.fillRect(0, 0, width, height, QBrush(src))
    else:
        scaled = src.scaled(width, height, Qt.KeepAspectRatioByExpanding,
                            Qt.SmoothTransformation)
        p.drawImage((width - scaled.width()) // 2, (height - scaled.height()) // 2, scaled)
    p.end()
    out = out.convertToFormat(QImage.Format_RGB888)
    a = np.frombuffer(out.constBits(), dtype=np.uint8,
                      count=out.bytesPerLine() * height)
    return a.reshape(height, out.bytesPerLine())[:, :width * 3].reshape(
        height, width, 3).astype(np.float32)


def _from_array(path: str, width: int, height: int):
    """:func:`_from_image` with :data:`IMAGE_READER` and NumPy."""
    src = IMAGE_READER(path) if IMAGE_READER is not None else None
    if src is None or not src.size:
        return None
    src = np.asarray(src, dtype=np.float32)[:, :, :3]
    h, w = src.shape[:2]
    if w < TILE_BELOW:
        ry, rx = -(-height // h), -(-width // w)
        return np.tile(src, (ry, rx, 1))[:height, :width].copy()
    k = max(width / w, height / h)
    from .drawing import resize_array
    big = resize_array(src.astype(np.float64), max(width, int(round(w * k))),
                       max(height, int(round(h * k))))
    y0 = (big.shape[0] - height) // 2
    x0 = (big.shape[1] - width) // 2
    return big[y0:y0 + height, x0:x0 + width].astype(np.float32)
