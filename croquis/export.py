# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""Saving a drawing: PNG, SVG in layers, PDF.

The ink is vector in SVG and PDF: every stroke (lines, hatching,
construction and ground strokes) is already a polygon, the outline of a
stroke with its changing width, so it goes out as a path, editable in
Inkscape, Affinity or Illustrator. The paper and the fill (marker,
watercolour, the masses of ink) are textures: they go as images, each in a
layer of its own under the ink, the fill multiplied onto the paper as a
marker's ink is.
"""
from __future__ import annotations

import base64
from xml.sax.saxutils import quoteattr

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMarginsF, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter, QPolygonF

from .drawing import INK, Layers, to_qimage
from .texts import tr

#: The resolution a PDF of a drawing in pixels is laid out at.
PDF_DPI = 300


def save_png(layers: Layers, path: str) -> bool:
    return layers.image().save(path, "PNG")


def _data_uri(img: QImage, fmt: str = "PNG", quality: int = -1) -> str:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, fmt, quality)
    mime = "image/jpeg" if fmt == "JPG" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(bytes(ba)).decode('ascii')}"


def _path_d(outline: np.ndarray) -> str:
    pts = np.round(outline, 2)
    head = f"M{pts[0, 0]:g},{pts[0, 1]:g}"
    return head + "L" + " ".join(f"{x:g},{y:g}" for x, y in pts[1:]) + "Z"


def svg_text(layers: Layers) -> str:
    """The drawing as SVG: three layers (Inkscape's, read by Affinity and
    Illustrator as groups), paper and fill as images, the ink as paths."""
    w, h = layers.width, layers.height
    ink = "#%02x%02x%02x" % INK
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'  <g id="paper" inkscape:groupmode="layer" inkscape:label={quoteattr(tr("Paper"))}>',
        f'    <image x="0" y="0" width="{w}" height="{h}" '
        f'xlink:href="{_data_uri(to_qimage(layers.sheet), "JPG", 92)}"/>',
        "  </g>",
    ]
    if layers.fill is not None:
        ox, oy = layers.origin
        fw, fh = layers.size
        fill = to_qimage(layers.fill * 255.0)
        out += [
            f'  <g id="fill" inkscape:groupmode="layer" '
            f'inkscape:label={quoteattr(tr("Colour and shade"))} style="mix-blend-mode:multiply">',
            f'    <image x="{ox}" y="{oy}" width="{fw}" height="{fh}" '
            f'xlink:href="{_data_uri(fill)}"/>',
            "  </g>",
        ]
    out.append(f'  <g id="ink" inkscape:groupmode="layer" inkscape:label={quoteattr(tr("Ink"))} '
               f'fill="{ink}" stroke="none">')
    for s in layers.strokes:
        op = max(0.0, min(1.0, s.opacity))
        attr = "" if op >= 0.999 else f' fill-opacity="{op:.2f}"'
        out.append(f'    <path d="{_path_d(s.outline)}"{attr}/>')
    out += ["  </g>", "</svg>", ""]
    return "\n".join(out)


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
