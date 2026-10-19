"""Make the style cards' thumbnails: the same small scene drawn with each
ready-made style, saved in croquis/thumbs/<style>.png (128 × 88, shown at
half size). Run inside an IngeTrazo checkout's environment:

    INGETRAZO_SRC=~/src/ingetrazo QT_QPA_PLATFORM=offscreen \\
        <ingetrazo venv>/bin/python tools/make_thumbnails.py
"""
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ["INGETRAZO_SRC"])
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QVector3D as V  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from core.sun import ShadowSettings  # noqa: E402
from views.main_window import MainWindow  # noqa: E402

from croquis import drawing, presets  # noqa: E402

win = MainWindow()
win.resize(900, 640)
win.show()
app.processEvents()
vp = win.viewport
m = vp.scene.loose_mesh
g = m.add_face([V(-3, -3, 0), V(5, -3, 0), V(5, 5, 0), V(-3, 5, 0)])
g.attrs["color"] = [0.82, 0.74, 0.58]
b = [V(0, 0, 0), V(2, 0, 0), V(2, 2, 0), V(0, 2, 0)]
t = [V(p.x(), p.y(), 2.6) for p in b]
m.add_face(t).attrs["color"] = [0.75, 0.3, 0.22]
for i in range(4):
    m.add_face([b[i], b[(i + 1) % 4], t[(i + 1) % 4], t[i]]).attrs["color"] = [0.75, 0.3, 0.22]
vp.notify_scene_changed()
cam = vp.camera
cam.target = V(1, 1, 0.9)
cam.distance = 13
cam.yaw = math.radians(-60)
cam.pitch = math.radians(30)
vp.scene.shadows = ShadowSettings(month=6, day=21, hour=15)
app.processEvents()
out = ROOT / "croquis" / "thumbs"
out.mkdir(exist_ok=True)
for key in presets.PRESETS:
    s = presets.apply_preset(dict(presets.DEFAULTS), key)
    s["light"] = "sun"
    s["hand"] = 55
    img = drawing.sketch(vp, presets.line_style(s), 900,
                         marker=presets.marker_style(s),
                         composition=presets.composition(s))
    # A card's 128 × 88: the middle of the drawing.
    w, h = img.width(), img.height()
    cw = int(w * 0.95)
    ch = int(cw * 88 / 128)
    crop = img.copy((w - cw) // 2, (h - ch) // 2, cw, ch)
    crop.scaled(128, 88, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).save(str(out / f"{key}.png"))
    print(key)
win._saved_version = vp.scene.version
win.close()
