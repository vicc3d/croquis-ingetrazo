# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Saving a drawing in IngeTrazo: PNG, SVG in layers, PDF (with Qt; the
SVG is :mod:`.vector`'s, shared with Blender).

The ink is vector in SVG and PDF: every stroke (lines, hatching,
construction and ground strokes) is already a polygon, the outline of a
stroke with its changing width, so it goes out as a path, editable in
Inkscape, Affinity or Illustrator. The paper and the fill (marker,
watercolour, the masses of ink) are textures: they go as images, each in a
layer of its own under the ink, the fill multiplied onto the paper as a
marker's ink is.
"""
from __future__ import annotations


import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPolygonF

from .drawing import INK, Layers
from .host import to_qimage
from .texts import tr

#: The resolution a PDF of a drawing in pixels is laid out at.
PDF_DPI = 300


def save_png(layers: Layers, path: str) -> bool:
    return layers.image().save(path, "PNG")


def qt_encode(rgb: np.ndarray, fmt: str, quality: int = -1) -> bytes:
    """A picture encoded by Qt, for :mod:`.vector`."""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    to_qimage(rgb).save(buf, fmt, quality)
    return bytes(ba)


def svg_text(layers: Layers) -> str:
    """The drawing as SVG in layers (:func:`.vector.svg_text`, the same as
    Blender's), its layers named in the user's language."""
    from . import vector
    return vector.svg_text(layers, qt_encode,
                           (tr("Paper"), tr("Colour and shade"), tr("Ink")))


def save_svg(layers: Layers, path: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg_text(layers))
        return True
    except OSError:
        return False


def save_pdf(layers: Layers, path: str, dpi: int = PDF_DPI) -> bool:
    """One page the drawing's size at ``dpi``: the paper and the fill as
    one image, the ink as vector paths over it."""
    w, h = layers.width, layers.height
    writer = QPdfWriter(path)
    writer.setResolution(dpi)
    size = QPageSize(QSizeF(w / dpi * 25.4, h / dpi * 25.4), QPageSize.Millimeter,
                     "Croquis", QPageSize.ExactMatch)
    writer.setPageLayout(QPageLayout(size, QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
    writer.setTitle("Croquis")
    p = QPainter()
    if not p.begin(writer):
        return False
    p.setRenderHint(QPainter.Antialiasing, True)
    target = QRectF(0, 0, writer.width(), writer.height())
    k = target.width() / w
    p.drawImage(target, to_qimage(layers.coloured_sheet()))
    p.scale(k, k)
    p.setPen(Qt.NoPen)
    for s in layers.strokes:
        a = int(255 * max(0.0, min(1.0, s.opacity)))
        p.setBrush(QColor(INK[0], INK[1], INK[2], a))
        p.drawPolygon(QPolygonF([QPointF(float(x), float(y)) for x, y in s.outline]))
    p.end()
    return True


def save(layers: Layers, path: str) -> bool:
    """By the file's extension: .svg, .pdf, else PNG."""
    low = path.lower()
    if low.endswith(".svg"):
        return save_svg(layers, path)
    if low.endswith(".pdf"):
        return save_pdf(layers, path)
    return save_png(layers, path)
