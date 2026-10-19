"""The extension inside a real IngeTrazo (offscreen): its tab, the lines of
the view where the viewport draws them, outlines, and a drawing. Needs an
IngeTrazo checkout and its Python environment:

    INGETRAZO_SRC=~/src/ingetrazo QT_QPA_PLATFORM=offscreen \\
        <ingetrazo venv>/bin/python -m pytest tests
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

import numpy as np
import pytest

_SRC = os.environ.get("INGETRAZO_SRC")
if not _SRC or not (Path(_SRC) / "core" / "hlr.py").is_file():
    pytest.skip("set INGETRAZO_SRC to an IngeTrazo checkout", allow_module_level=True)
sys.path.insert(0, _SRC)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QVector3D as V  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import croquis  # noqa: E402
from croquis import drawing  # noqa: E402
from croquis import strokes as st  # noqa: E402

_app = QApplication.instance() or QApplication([])


@pytest.fixture
def window(monkeypatch):
    from core import extensions
    from core.paths import app_root
    from views.extension_api import ExtensionApp
    from views.main_window import MainWindow
    # Only IngeTrazo's own plugins: never a copy installed in the user's
    # plugins folder.
    monkeypatch.setattr(extensions, "plugin_dirs", lambda: [app_root() / "plugins"])
    # The panel's settings in a place of the tests' own, never the user's.
    from croquis import panel as croquis_panel
    from PySide6.QtCore import QSettings
    monkeypatch.setattr(croquis_panel, "_SETTINGS", ("ingetrazo-croquis-tests", "croquis"))
    QSettings("ingetrazo-croquis-tests", "croquis").clear()
    win = MainWindow()
    win.resize(1000, 700)
    win.show()
    _app.processEvents()
    m = win.viewport.scene.loose_mesh
    m.add_face([V(-4, -4, 0), V(6, -4, 0), V(6, 6, 0), V(-4, 6, 0)])
    b = [V(0, 0, 0), V(2, 0, 0), V(2, 2, 0), V(0, 2, 0)]
    t = [V(p.x(), p.y(), 3) for p in b]
    m.add_face(t)
    for i in range(4):
        m.add_face([b[i], b[(i + 1) % 4], t[(i + 1) % 4], t[i]])
    win.viewport.notify_scene_changed()
    cam = win.viewport.camera
    cam.target = V(1, 1, 1)
    cam.distance = 16
    cam.yaw = math.radians(-60)
    cam.pitch = math.radians(28)
    _app.processEvents()
    app = ExtensionApp(win, "croquis")
    croquis.setup(app)
    yield win, app
    win._saved_version = win.viewport.scene.version
    win.close()


def _panel(win):
    for dock in win._extension_docks:
        if type(dock.widget()).__name__ == "CroquisPanel":
            return dock.widget()
    raise AssertionError("no Croquis tab")


def _exact(vp, w, h):
    """IngeTrazo's exact hidden-line drawing of the view, in pixels."""
    from core import hlr
    cam = vp.camera
    geom = vp.hlr_geometry()
    if cam.perspective:
        segs = hlr.hlr_perspective(vp.scene, cam, geometry=geom)
        m = cam.projection_matrix() * cam.view_matrix()
        M = np.array(m.data(), dtype=np.float64).reshape(4, 4, order="F")
        t = cam.target
        depth = float(M[3, :3] @ np.array([t.x(), t.y(), t.z()]) + M[3, 3])
    else:
        segs = hlr.hlr_drawing(vp.scene, cam, geometry=geom, profiles=False,
                               fills=False).segs
        depth = cam.distance
    half_h = depth * math.tan(math.radians(cam.fov_deg) / 2.0)
    half_w = half_h * cam.aspect
    segs = np.asarray(segs, dtype=np.float64).reshape(-1, 4)
    out = np.empty_like(segs)
    out[:, 0::2] = (segs[:, 0::2] / half_w + 1.0) * 0.5 * w
    out[:, 1::2] = (1.0 - segs[:, 1::2] / half_h) * 0.5 * h
    return out


def _dist_to(points, segs):
    a, b = segs[None, :, :2], segs[None, :, 2:]
    p = points[:, None, :]
    d = b - a
    t = np.clip(((p - a) * d).sum(-1) / np.maximum((d * d).sum(-1), 1e-12), 0, 1)
    return np.hypot(*(p - (a + t[..., None] * d)).transpose(2, 0, 1)).min(axis=1)


@pytest.mark.parametrize("mode", ["perspective", "parallel", "two_point"])
def test_the_lines_match_the_exact_drawing(window, mode):
    """Against IngeTrazo's exact hidden-line pass: every drawn point lies
    on an exact line, and the drawing covers the exact lines."""
    win, _app2 = window
    vp = win.viewport
    vp.camera.set_projection(mode)
    vp.update()
    _app.processEvents()
    w, h = drawing.drawing_size(vp.camera, 1200)
    segs = drawing.View(vp, w, h).segs
    exact = _exact(vp, w, h)
    assert len(segs) and len(exact)

    def sample(ss, k=12):
        t = np.linspace(0, 1, k)[None, :, None]
        return (ss[:, None, :2] + t * (ss[:, None, 2:] - ss[:, None, :2])).reshape(-1, 2)

    assert np.percentile(_dist_to(sample(segs), exact), 99) < 3.0
    # The exact drawing may run past the picture's edge: only what shows.
    ex = sample(exact)
    ex = ex[(ex[:, 0] >= 0) & (ex[:, 0] <= w) & (ex[:, 1] >= 0) & (ex[:, 1] <= h)]
    assert np.percentile(_dist_to(ex, segs), 97) < 3.0


def test_the_box_contour_is_an_outline_and_its_middle_edge_is_not(window):
    win, _a = window
    vp = win.viewport
    w, h = drawing.drawing_size(vp.camera, 1200)
    view = drawing.View(vp, w, h)
    segs, outline = view.segs, view.outline
    sx, sy = w / vp.width(), h / vp.height()
    # The front vertical edge of the box, between two lit faces: no outline.
    px, py, _f = vp.world_to_pixels(np.array([[2, 0, 0.5], [2, 0, 2.5]], dtype=float))
    a = np.array([px[0] * sx, py[0] * sy])
    b = np.array([px[1] * sx, py[1] * sy])
    mid = (segs[:, :2] + segs[:, 2:]) / 2
    e = b - a
    dist = np.abs(e[0] * (mid[:, 1] - a[1]) - e[1] * (mid[:, 0] - a[0])) / np.linalg.norm(e)
    k = int(np.argmin(dist))
    assert dist[k] < 2.0 and not outline[k]
    assert outline.sum() >= 6               # the box's contour, the slab's edge


def test_a_wall_split_at_its_vertices_is_one_stroke():
    from croquis import visibility as vis
    segs = np.array([[0, 0, 50, 0], [50, 0, 120, 0.2], [120, 0.2, 200, 0.3],
                     [200, 0.3, 200, 100]], dtype=float)
    merged, outline = vis.merge_collinear(segs, np.array([True, True, False, True]), tol=1.5)
    assert len(merged) == 2
    long = merged[np.argmax(np.hypot(merged[:, 2] - merged[:, 0], merged[:, 3] - merged[:, 1]))]
    assert sorted([long[0], long[2]]) == [0, 200]
    assert outline.all()


def test_the_tab_draws_the_view(window, monkeypatch):
    win, _a = window
    panel = _panel(win)
    panel.size.setCurrentIndex(0)
    panel.draw()
    img = panel._window._img
    assert img.width() == 1600
    arr = np.frombuffer(img.constBits(), dtype=np.uint8,
                        count=img.bytesPerLine() * img.height())
    # Some ink on the paper: pixels much darker than the sheet.
    assert (arr.reshape(img.height(), -1)[:, 0:img.width() * 4:4] < 120).sum() > 500
    panel._window.close()


def test_an_empty_view_says_so(window):
    win, _a = window
    vp = win.viewport
    vp.camera.target = V(500, 500, 500)
    vp.camera.distance = 2
    _app.processEvents()
    panel = _panel(win)
    panel.draw()
    assert panel._window is None
    assert panel.status.text()


def test_ingetrazo_loads_the_folder_as_an_extension(monkeypatch):
    """Dropped in the plugins folder as is, IngeTrazo loads it (a package
    with relative imports) and the tab appears."""
    from core import extensions
    from views.main_window import MainWindow
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(extensions, "plugin_dirs", lambda: [root])
    win = MainWindow()
    try:
        names = [type(d.widget()).__name__ for d in win._extension_docks]
        assert "CroquisPanel" in names
    finally:
        win._saved_version = win.viewport.scene.version
        win.close()


def test_marker_values_follow_the_light(window):
    """Classic light from the upper left: the box's top stays paper, one of
    its sides goes grey; the ground (lit from above) stays paper."""
    from croquis import marker as mk
    win, _a = window
    vp = win.viewport
    w, h = vp.width(), vp.height()
    view = drawing.View(vp, w, h)
    light = mk.light_direction(vp.camera, vp.scene, "classic")
    values, plane, _n, _p = mk.face_values(view.index, view.tris, vp.camera, light)

    def value_at(x, y, z):
        px, py, _f = vp.world_to_pixels(np.array([[x, y, z]], dtype=float))
        return int(values[int(py[0]), int(px[0])])

    assert value_at(1, 1, 3) == 0                     # the box's top
    assert {value_at(2, 1, 1.5), value_at(1, 0, 1.5)} & {1, 2}
    assert value_at(-2, 4, 0) == 0                    # the ground
    assert (values[view.index < 0] == -1).all()


def test_the_marker_greys_the_model_only_and_off_its_lines(window):
    from croquis import marker as mk
    win, _a = window
    vp = win.viewport
    w, h = drawing.drawing_size(vp.camera, 1000)
    view = drawing.View(vp, w, h)
    on = drawing.marker_layer(view, mk.MarkerStyle(offset=0)).mean(axis=2)
    assert on.min() < 0.9                             # some grey
    assert (on[view.index < 0] > 0.99).mean() > 0.97  # the sky stays paper
    moved = drawing.marker_layer(view, mk.MarkerStyle(offset=20)).mean(axis=2)
    ys, xs = np.nonzero(on < 0.95)
    ym, xm = np.nonzero(moved < 0.95)
    assert xm.mean() > xs.mean() + 5 and ym.mean() > ys.mean() + 3


def test_the_sun_light_and_its_night(window):
    from croquis import marker as mk
    from core.sun import ShadowSettings
    win, _a = window
    vp = win.viewport
    vp.scene.shadows = ShadowSettings(month=6, day=21, hour=12)
    sun = mk.light_direction(vp.camera, vp.scene, "sun")
    assert sun[2] > 0.3                              # noon: high
    vp.scene.shadows = ShadowSettings(month=6, day=21, hour=23)
    night = mk.light_direction(vp.camera, vp.scene, "sun")
    classic = mk.light_direction(vp.camera, vp.scene, "classic")
    assert np.allclose(night, classic)               # at night, the classic light


def test_the_tab_draws_with_the_marker(window):
    win, _a = window
    panel = _panel(win)
    panel.marker_on.setChecked(True)
    panel.size.setCurrentIndex(0)
    panel.draw()
    img = panel._window._img
    arr = np.frombuffer(img.constBits(), dtype=np.uint8,
                        count=img.bytesPerLine() * img.height())
    px = arr.reshape(img.height(), -1)[:, :img.width() * 4].reshape(img.height(), img.width(), 4)
    grey = (px[:, :, :3].astype(int).sum(axis=2) // 3)
    # Paper is ~240; marker greys sit between the paper and the ink.
    assert ((grey > 140) & (grey < 215)).sum() > 2000
    panel._window.close()


def test_the_box_casts_its_shadow_away_from_the_sun(window):
    """A sun from the +x side, low: the box's shadow falls on the ground on
    its -x side, and not on its +x side."""
    from croquis import marker as mk
    from croquis import shadow as sh
    win, _a = window
    vp = win.viewport
    vp.camera.pitch = math.radians(60)        # look down on the ground
    _app.processEvents()
    w, h = vp.width(), vp.height()
    view = drawing.View(vp, w, h)
    light = np.array([1.0, 0.0, 0.6])
    light /= np.linalg.norm(light)
    _v, _p, normals, _po = mk.face_values(view.index, view.tris, vp.camera, light)
    cast = sh.cast_shadow(view, normals, light)

    def at(x, y, z):
        px, py, _f = vp.world_to_pixels(np.array([[x, y, z]], dtype=float))
        return bool(cast[int(py[0]), int(px[0])])

    assert at(-1.5, 1, 0) and at(-3, 1, 0)       # behind the box, from the sun
    assert not at(4, 1, 0) and not at(1, 1, 3)   # in front, and its top


def test_colours_go_to_the_nearest_marker():
    from croquis import palette as pal
    brick = pal.MARKERS.index((196, 72, 52))
    assert pal.nearest_marker((0.75, 0.3, 0.22)) == brick
    assert pal.nearest_marker((0.96, 0.95, 0.925)) == -1     # the default face
    assert pal.nearest_marker((0.5, 0.5, 0.5)) == -1         # a grey
    assert pal.nearest_marker((0.2, 0.45, 0.85)) in (
        pal.MARKERS.index((80, 120, 180)), pal.MARKERS.index((130, 175, 215)))


def test_painted_faces_get_their_marker(window):
    from croquis import palette as pal
    win, _a = window
    vp = win.viewport
    for f in vp.scene.loose_mesh.faces:
        f.attrs["color"] = [0.75, 0.3, 0.22]
    vp.notify_scene_changed()
    _app.processEvents()
    tris, colour, tone = pal.triangle_colours(vp)
    assert len(tris) == len(colour) > 0
    assert (colour == pal.MARKERS.index((196, 72, 52))).all()
    assert np.allclose(tone, 0.2126 * 0.75 + 0.7152 * 0.3 + 0.0722 * 0.22, atol=0.01)


def test_hatching_runs_inside_the_shade():
    from croquis import hatch
    mask = np.zeros((200, 300), dtype=bool)
    mask[50:150, 100:200] = True
    segs = hatch.hatch_segments(mask, 58.0, 8.0, min_len=3)
    assert len(segs) > 10
    pts = np.r_[segs[:, :2], segs[:, 2:]]
    assert (pts[:, 0] >= 99).all() and (pts[:, 0] <= 201).all()
    assert (pts[:, 1] >= 49).all() and (pts[:, 1] <= 151).all()
    ang = np.degrees(np.arctan2(-(segs[:, 3] - segs[:, 1]), segs[:, 2] - segs[:, 0])) % 180
    assert np.allclose(ang, 58.0, atol=1.0)


def test_watercolour_stays_near_its_fill_and_has_a_rim():
    from croquis import marker as mk
    from croquis import watercolour as wc
    values = np.full((300, 400), -1, dtype=np.int8)
    values[100:200, 120:280] = 2
    out = wc.paint(np.full((300, 400, 3), 255.0), values, None,
                   mk.MarkerStyle(medium="watercolour", offset=0), 0.4)
    grey = out.mean(axis=2)
    assert grey[150, 200] < 235                       # the wash is there
    assert (grey[:40] > 254).all() and (grey[260:] > 254).all()   # no drops far off
    # Darker at its rim than in its middle, on average.
    rim = np.r_[grey[105, 130:270], grey[195, 130:270]].mean()
    assert rim < grey[140:160, 180:220].mean()


def test_the_tab_paints_in_watercolour_with_hatching(window):
    win, _a = window
    panel = _panel(win)
    panel.marker_on.setChecked(True)
    panel.medium.setCurrentIndex(panel.medium.findData("watercolour"))
    panel.hatching.setChecked(True)
    panel.size.setCurrentIndex(0)
    st_ = panel.marker_style()
    assert st_.medium == "watercolour" and st_.hatching
    panel.draw()
    assert panel._window._img.width() == 1600
    panel._window.close()


def test_the_ground_is_not_the_subject_and_the_colour_fades_round_it(window):
    from croquis import compose as cp
    win, _a = window
    vp = win.viewport
    w, h = vp.width(), vp.height()
    view = drawing.View(vp, w, h)
    subject = cp.subject_mask(view.index, view.tris)

    def pix(x, y, z):
        px, py, _f = vp.world_to_pixels(np.array([[x, y, z]], dtype=float))
        return int(py[0]), int(px[0])

    assert subject[pix(1, 0.01, 1.5)]                 # the box
    hh, ww = subject.shape
    ground = [pix(x, y, 0) for x in (-3, 1, 5) for y in (-3, 5)]
    from croquis.marker import triangle_normals
    level = np.abs(triangle_normals(view.tris)[:, 2]) > 0.97
    flat_z = view.tris[:, 0, 2]
    ground = [(r, c) for r, c in ground if 0 <= r < hh and 0 <= c < ww
              and view.index[r, c] >= 0 and level[view.index[r, c]]
              and abs(flat_z[view.index[r, c]]) < 1e-6]    # not hidden by the box
    assert ground and not any(subject[r, c] for r, c in ground)   # the slab
    fade = cp.fade_map(subject, 1.0)
    assert fade[pix(1, 1, 1.5)] == 1.0                # whole on the box
    assert fade.min() < 0.5                           # gone far from it


def test_construction_lines_run_past_the_long_lines():
    from croquis import compose as cp
    segs = np.array([[100, 500, 700, 500], [700, 500, 700, 120]], dtype=float)
    out = cp.construction_strokes(segs, 1000, 1000, 0.5)
    assert out
    pts = np.vstack([s.outline for s in out])
    beyond = (pts[:, 0] > 705) | (pts[:, 0] < 95) | (pts[:, 1] < 115)
    assert beyond.any()
    assert all(s.opacity < 0.5 for s in out)


def test_the_tab_draws_with_its_composition(window):
    win, _a = window
    panel = _panel(win)
    panel.ground.setChecked(True)
    c = panel.composition()
    assert c.ground and c.unfinished and c.construction
    panel.size.setCurrentIndex(0)
    panel.draw()
    assert panel._window._img.width() == 1600
    panel._window.close()


def test_a_model_without_a_floor_still_casts_on_the_ground(window):
    """Only the box (no slab): the sun's shadow falls on the ground under
    it, as in IngeTrazo's own view."""
    from croquis import marker as mk
    from croquis import shadow as sh
    win, _a = window
    vp = win.viewport
    m = vp.scene.loose_mesh
    slab = [f for f in m.faces if all(abs(v.position.z()) < 1e-9 for v in f.loop)
            and len(f.loop) == 4 and abs(f.loop[0].position.x() + 4) < 1e-9]
    for f in slab:
        m.remove_face(f) if hasattr(m, "remove_face") else m.faces.remove(f)
    vp.notify_scene_changed()
    vp.camera.pitch = math.radians(60)
    _app.processEvents()
    w, h = vp.width(), vp.height()
    view = drawing.View(vp, w, h)
    light = np.array([1.0, 0.0, 0.6])
    light /= np.linalg.norm(light)
    ground = sh.ground_shadow(view, light)
    px, py, _f = vp.world_to_pixels(np.array([[-1.5, 1, 0], [4, 1, 0]], dtype=float))
    assert ground[int(py[0]), int(px[0])]          # behind the box, from the sun
    assert not ground[int(py[1]), int(px[1])]      # in front of it
    assert not (ground & (view.index >= 0)).any()  # only where no model is


def test_long_narrow_areas_run_along_their_length():
    from croquis import marker as mk
    plane = np.full((100, 200), -1)
    plane[40:48, 20:180] = 0                       # a slat, lying flat
    plane[10:90, 100:110] = 1                      # a post, upright
    plane[60:90, 20:50] = 2                        # a square: unchanged
    out = mk.long_axis_angles(plane, np.array([1.0, 0.3, 0.7]))
    assert abs(math.sin(out[0])) < 0.05            # along the slat
    assert abs(math.cos(out[1])) < 0.05            # up the post
    assert out[2] == 0.7


def test_construction_lines_stop_where_the_model_begins():
    from croquis import compose as cp
    segs = np.array([[100, 500, 700, 500]], dtype=float)
    index = np.full((1000, 1000), -1)
    index[480:520, 760:900] = 0                    # something past the line's end
    out = cp.construction_strokes(segs, 1000, 1000, 0.0, index=index, seed=1)
    pts = np.vstack([s.outline for s in out]) if out else np.zeros((0, 2))
    assert not ((pts[:, 0] > 762) & (np.abs(pts[:, 1] - 500) < 15)).any()


def test_colour_modes_change_the_fill(window):
    from croquis import marker as mk
    win, _a = window
    vp = win.viewport
    for f in vp.scene.loose_mesh.faces:
        f.attrs["color"] = [0.2, 0.2, 0.22]          # a dark grey material
    vp.notify_scene_changed()
    _app.processEvents()
    w, h = drawing.drawing_size(vp.camera, 800)
    view = drawing.View(vp, w, h)
    model = view.index >= 0
    means = {}
    for mode in ("colour", "greys", "contrast", "none"):
        st_ = mk.MarkerStyle(colour_mode=mode, shadows=False, offset=0)
        f = drawing.fill_layer(view, st_)
        means[mode] = f.mean(axis=2)[model].mean()
    # A dark material reads dark in colour and greys, not in the others.
    assert means["colour"] < means["none"] - 0.05
    assert means["greys"] < means["none"] - 0.05


def test_ground_strokes_follow_the_perspective(window):
    """In a parallel view the pavement lines along one axis stay parallel;
    in perspective they converge."""
    from croquis import compose as cp
    win, _a = window
    vp = win.viewport
    out = {}
    for mode in ("parallel", "perspective"):
        vp.camera.set_projection(mode)
        _app.processEvents()
        w, h = drawing.drawing_size(vp.camera, 1000)
        view = drawing.View(vp, w, h)
        strokes = cp.ground_strokes(view, h, 0.0, seed=3)
        out[mode] = strokes
    assert out["parallel"] and out["perspective"]
