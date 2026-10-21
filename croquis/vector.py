# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Victor Crespo (3dvic.com · github.com/vicc3d)
"""A drawing as SVG in layers and as PDF, with no toolkit: shared by
IngeTrazo and Blender.

The ink is vector in both: every stroke is already a polygon (the outline
of a stroke with its changing width), so it goes out as a path, editable
in Inkscape, Affinity or Illustrator. The paper and the fill are
textures: in SVG each its own layer under the ink, the fill multiplied
onto the paper as a marker's ink is; in PDF one picture, the paper with
the fill laid on it.

Pictures are encoded by the host (``encode(rgb, fmt, quality) -> bytes``,
``fmt`` "PNG" or "JPG"; Qt in IngeTrazo, Blender's own in Blender); without
one, or when it cannot, PNG is written here with zlib.
"""
from __future__ import annotations

import base64
import struct
import zlib
from xml.sax.saxutils import quoteattr

import numpy as np

INK = (29, 26, 23)


# ---- Pictures -------------------------------------------------------------

def png_bytes(rgb: np.ndarray) -> bytes:
    """``rgb`` (H, W, 3) bytes as a PNG file."""
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8)
    h, w = rgb.shape[:2]
    raw = np.empty((h, w * 3 + 1), np.uint8)
    raw[:, 0] = 0                                    # no filter
    raw[:, 1:] = rgb.reshape(h, w * 3)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw.tobytes(), 6))
            + chunk(b"IEND", b""))


def _bytes(rgb: np.ndarray):
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def _encoded(rgb: np.ndarray, fmt: str, quality: int, encode):
    """``(bytes, fmt)`` of a picture: the host's, or PNG from here."""
    if encode is not None:
        try:
            data = encode(rgb, fmt, quality)
            if data:
                return data, fmt
        except Exception:                # noqa: BLE001 (the host could not)
            pass
    return png_bytes(rgb), "PNG"


def _data_uri(rgb, fmt, quality, encode) -> str:
    data, fmt = _encoded(rgb, fmt, quality, encode)
    mime = "image/jpeg" if fmt == "JPG" else "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


# ---- SVG -------------------------------------------------------------------

def _path_d(outline: np.ndarray) -> str:
    pts = np.round(outline, 2)
    head = f"M{pts[0, 0]:g},{pts[0, 1]:g}"
    return head + "L" + " ".join(f"{x:g},{y:g}" for x, y in pts[1:]) + "Z"


def svg_text(layers, encode=None, labels=("Paper", "Colour and shade", "Ink")) -> str:
    """The drawing as SVG: three layers (Inkscape's, read by Affinity and
    Illustrator as groups), paper and fill as pictures, the ink as paths.
    ``labels``: the layers' names, in the user's language."""
    w, h = layers.width, layers.height
    ink = "#%02x%02x%02x" % INK
    paper, colour, ink_name = labels
    out = [
        '<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'  <g id="paper" inkscape:groupmode="layer" inkscape:label={quoteattr(paper)}>',
        f'    <image x="0" y="0" width="{w}" height="{h}" '
        f'xlink:href="{_data_uri(_bytes(layers.sheet), "JPG", 92, encode)}"/>',
        "  </g>",
    ]
    if layers.fill is not None:
        ox, oy = layers.origin
        fw, fh = layers.size
        out += [
            f'  <g id="fill" inkscape:groupmode="layer" '
            f'inkscape:label={quoteattr(colour)} style="mix-blend-mode:multiply">',
            f'    <image x="{ox}" y="{oy}" width="{fw}" height="{fh}" '
            f'xlink:href="{_data_uri(_bytes(layers.fill * 255.0), "PNG", -1, encode)}"/>',
            "  </g>",
        ]
    out.append(f'  <g id="ink" inkscape:groupmode="layer" inkscape:label={quoteattr(ink_name)} '
               f'fill="{ink}" stroke="none">')
    for s in layers.strokes:
        op = max(0.0, min(1.0, s.opacity))
        attr = "" if op >= 0.999 else f' fill-opacity="{op:.2f}"'
        out.append(f'    <path d="{_path_d(s.outline)}"{attr}/>')
    out += ["  </g>", "</svg>", ""]
    return "\n".join(out)


# ---- PDF -------------------------------------------------------------------

def pdf_bytes(layers, dpi: int = 300, encode=None, title: str = "Croquis") -> bytes:
    """One page the drawing's size at ``dpi``: the paper with the fill as
    one picture, the ink as filled paths over it (even-odd, as drawn),
    each at its opacity."""
    w, h = layers.width, layers.height
    k = 72.0 / dpi                                   # pixels → points
    pw, ph = w * k, h * k
    sheet = _bytes(layers.coloured_sheet())
    data, fmt = _encoded(sheet, "JPG", 92, encode)
    if fmt == "JPG":
        image = (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
                 f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
                 f"/Length {len(data)} >>").encode(), data
    else:
        raw = zlib.compress(np.ascontiguousarray(sheet).tobytes(), 6)
        image = (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
                 f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                 f"/Length {len(raw)} >>").encode(), raw
    # One graphics state per opacity used (to the hundredth).
    alphas = sorted({round(max(0.0, min(1.0, s.opacity)), 2) for s in layers.strokes})
    gs_name = {a: f"/G{i}" for i, a in enumerate(alphas)}
    r, g, b = (c / 255.0 for c in INK)
    ops = [f"q {pw:.3f} 0 0 {ph:.3f} 0 0 cm /Im0 Do Q",
           # Pixels, y down → points, y up.
           f"q {k:.6f} 0 0 {-k:.6f} 0 {ph:.3f} cm {r:.4f} {g:.4f} {b:.4f} rg"]
    current = None
    for s in layers.strokes:
        a = round(max(0.0, min(1.0, s.opacity)), 2)
        if a != current:
            ops.append(f"{gs_name[a]} gs")
            current = a
        pts = np.round(s.outline, 2)
        ops.append(f"{pts[0, 0]:g} {pts[0, 1]:g} m "
                   + " ".join(f"{x:g} {y:g} l" for x, y in pts[1:]) + " h f*")
    ops.append("Q")
    content = zlib.compress("\n".join(ops).encode("ascii"), 6)
    gs = " ".join(f"{gs_name[a]} << /Type /ExtGState /ca {a:g} >>"
                  for a in alphas)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pw:.3f} {ph:.3f}] "
         f"/Resources << /XObject << /Im0 4 0 R >> /ExtGState << {gs} >> >> "
         f"/Contents 5 0 R >>").encode(),
        image,
        (f"<< /Length {len(content)} /Filter /FlateDecode >>".encode(), content),
        f"<< /Title ({_pdf_text(title)}) /Producer (Croquis) >>".encode(),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode()
        if isinstance(obj, tuple):
            head, body = obj
            out += head + b"\nstream\n" + body + b"\nendstream"
        else:
            out += obj
        out += b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info "
            f"{len(objects)} 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def _pdf_text(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def save(layers, path: str, encode=None, dpi: int = 300,
         labels=("Paper", "Colour and shade", "Ink"), png=None) -> bool:
    """By the file's extension: .svg, .pdf, else PNG (``png(layers, path)``
    from the host, or written here)."""
    low = path.lower()
    try:
        if low.endswith(".svg"):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(svg_text(layers, encode, labels))
        elif low.endswith(".pdf"):
            with open(path, "wb") as fh:
                fh.write(pdf_bytes(layers, dpi, encode))
        elif png is not None:
            return bool(png(layers, path))
        else:
            with open(path, "wb") as fh:
                fh.write(png_bytes(layers.pixels()))
        return True
    except OSError:
        return False
