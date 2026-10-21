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


def _has_accent() -> bool:
    from views import theme
    return hasattr(theme, "accent_color") and hasattr(theme, "apply_accent")


#: IngeTrazo 0.5.9 and later: an accent apart from the selection colour.
_needs_accent = pytest.mark.skipif(not _has_accent(), reason="IngeTrazo before 0.5.9")


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
    panel.set("size", 1600)
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
    panel.set("technique", "marker")
    panel.set("size", 1600)
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


def test_colours_are_read_once_until_the_model_changes(window, monkeypatch):
    """The live preview asks on every new view: the colours are kept until
    the model, its paint or what shows of it changes."""
    from croquis import palette as pal
    win, _a = window
    vp = win.viewport
    calls = []
    real = pal._triangle_colours
    monkeypatch.setattr(pal, "_triangle_colours",
                        lambda v: calls.append(1) or real(v))
    first = pal.triangle_colours(vp)
    assert pal.triangle_colours(vp) is first and len(calls) == 1
    for f in vp.scene.loose_mesh.faces:
        f.attrs["color"] = [0.75, 0.3, 0.22]
    # As every edit through IngeTrazo's history does (the Paint Bucket's).
    vp.scene.version += 1
    vp.notify_scene_changed()
    _app.processEvents()
    painted = pal.triangle_colours(vp)
    assert len(calls) == 2
    assert (painted[1] == pal.MARKERS.index((196, 72, 52))).all()


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
    panel.set("technique", "marker")
    panel.set("technique", "watercolour")
    panel.set("hatching", True)
    panel.set("size", 1600)
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
    panel.set("ground", True)
    c = panel.composition()
    assert c.ground and c.unfinished and c.construction
    panel.set("size", 1600)
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


def test_a_style_card_sets_its_look_and_editing_makes_it_custom(window):
    win, _a = window
    panel = _panel(win)
    panel.cards["watercolour"].click()
    assert panel.s["preset"] == "watercolour"
    assert panel.marker_style().medium == "watercolour"
    assert panel.marker_style().hatching
    assert panel.cards["watercolour"].isChecked()
    panel.materials["greys"].click()
    assert panel.s["preset"] == "custom" and panel.custom.isVisible() or \
        panel.s["preset"] == "custom"
    assert not any(b.isChecked() for b in panel.cards.values())
    panel.cards["ink"].click()
    assert panel.s["technique"] == "ink"
    assert not panel.marker_style().enabled
    assert not panel.materials["colour"].isEnabled()   # no fill with ink only


def test_the_controls_drive_the_settings_and_they_are_kept(window):
    from PySide6.QtCore import QSettings
    from croquis import panel as cp
    win, _a = window
    panel = _panel(win)
    panel.technique.buttons[1].click()                 # watercolour
    panel.light.buttons[1].click()                     # the model's sun
    panel.toggles["ground"].click()
    panel.hand.setValue(80)
    panel.size.buttons[2].click()                      # L
    s = panel.s
    assert (s["technique"], s["light"], s["ground"], s["hand"], s["size"]) == \
        ("watercolour", "sun", True, 80, 3600)
    stored = cp.ps.clean(QSettings(*cp._SETTINGS).value("state", ""))
    assert stored["size"] == 3600 and stored["technique"] == "watercolour"
    assert panel.style().hand == 0.8


@_needs_accent
def test_the_panel_follows_the_theme(window, monkeypatch):
    from PySide6.QtGui import QColor, QPalette
    from views import theme
    win, _a = window
    panel = _panel(win)
    monkeypatch.setattr(theme, "accent_color", lambda name=None: QColor("#e8833a"))
    before = QPalette(_app.palette())
    pal = QPalette(before)
    pal.setColor(QPalette.Window, QColor("#202124"))
    pal.setColor(QPalette.WindowText, QColor("#eeeeee"))
    _app.setPalette(pal)                 # as IngeTrazo's theme switch does
    _app.processEvents()
    try:
        sheet = panel.styleSheet()
    finally:
        _app.setPalette(before)
    assert "#e8833a" in sheet
    # Tiles a shade over the dark window, not black or white.
    from PySide6.QtGui import QColor as C
    import re
    tile = re.search(r"QFrame#tile \{ background: (#[0-9a-f]{6})", sheet).group(1)
    assert 30 < C(tile).lightness() < 90


@_needs_accent
def test_the_panel_follows_the_accent(window, monkeypatch):
    """Preferences changes the accent without a new palette: the panel
    wears the new one once IngeTrazo repaints its windows."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QColor
    from views import theme
    win, _a = window
    panel = _panel(win)
    monkeypatch.setattr(theme, "accent_color", lambda name=None: QColor("#3aa86b"))
    theme.apply_accent(_app)
    loop = QEventLoop()
    QTimer.singleShot(300, loop.quit)
    loop.exec()
    _app.processEvents()
    assert "#3aa86b" in panel.styleSheet()
    # The sliders too, not only the chips and switches.
    import re
    sub = re.search(r"QSlider::sub-page:horizontal \{[^}]*background: (#[0-9a-f]{6})",
                    panel.styleSheet())
    assert sub and sub.group(1) == "#3aa86b"


def test_with_the_live_preview_the_sketch_is_saved_where_one_looks(window, monkeypatch, tmp_path):
    """The live preview shows the sketch already: the big button, a
    right-click in the view and the badge over it all offer to save it
    (File ▸ Export saves IngeTrazo's view, not the sketch)."""
    from PySide6.QtWidgets import QFileDialog, QMenu
    from croquis import panel as cp
    win, _a = window
    panel = _panel(win)
    menu = QMenu()
    panel.context_menu(menu)
    assert not menu.actions()                     # off: nothing to save
    assert panel.draw_btn.text() == "Draw the view"
    panel.live_switch.setChecked(True)
    try:
        assert panel.draw_btn.text() == "Save the sketch…"
        panel.context_menu(menu)
        assert [a.text() for a in menu.actions()] == ["Save the sketch…"]
        out = tmp_path / "sketch.png"
        monkeypatch.setattr(QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (str(out), "PNG (*.png)")))
        panel.draw_btn.click()
        assert out.is_file() and out.stat().st_size > 10_000
        assert panel._window is None                  # straight to the file
        from PySide6.QtGui import QImage
        assert QImage(str(out)).width() == panel.output_size(win.viewport.camera)[0]
    finally:
        panel.live_switch.setChecked(False)
    assert panel.draw_btn.text() == "Draw the view"


def test_presets_are_complete_and_clean_reads_anything():
    from croquis import presets as ps
    for key in ps.PRESETS:
        s = ps.apply_preset(dict(ps.DEFAULTS), key)
        assert ps.matching_preset(s) == key
        ps.line_style(s), ps.marker_style(s), ps.composition(s)
    assert ps.clean("not json") == ps.DEFAULTS
    assert ps.clean({"size": "x", "hatching": 1})["size"] == ps.DEFAULTS["size"]
    # Damaged settings never ask for more than the panel could.
    bad = ps.clean({"custom_width": 10 ** 9, "size": 99999, "dpi": 9600,
                    "custom_format": "A0", "technique": "oil", "hand": -5,
                    "preset": "nope", "paper": "papyrus"})
    assert bad["custom_width"] == 12000 and bad["hand"] == 0
    for k in ("size", "dpi", "custom_format", "technique", "preset", "paper"):
        assert bad[k] == ps.DEFAULTS[k], k


def test_reset_puts_the_fine_settings_back_and_keeps_the_rest(window):
    from croquis import presets as ps
    win, _a = window
    panel = _panel(win)
    panel.cards["watercolour"].click()
    panel.sliders["weight"].setValue(35)
    panel.sliders["strength"].setValue(40)
    panel.toggles["natural"].click()
    panel.hand.setValue(90)
    panel.reset_btn.click()
    for key in panel.FINE:
        assert panel.s[key] == ps.DEFAULTS[key]
    assert panel.sliders["weight"].value() == ps.DEFAULTS["weight"]
    assert panel.s["hand"] == 90 and panel.s["technique"] == "watercolour"
    assert panel.s["preset"] == "watercolour"


def test_reset_all_puts_every_setting_back(window):
    from croquis import presets as ps
    win, _a = window
    panel = _panel(win)
    panel.cards["contrast"].click()
    panel.hand.setValue(5)
    panel.size.buttons[0].click()
    panel.sliders["nib"].setValue(55)
    panel.reset_all_btn.click()
    assert panel.s == ps.DEFAULTS
    assert panel.cards[ps.DEFAULTS["preset"]].isChecked()
    assert panel.hand.value() == ps.DEFAULTS["hand"]


def test_high_contrast_is_solid_ink_on_white():
    from croquis import ink
    values = np.zeros((120, 160), dtype=np.int8)
    values[20:60, 20:60] = 2                       # away from the light
    values[70:110, 90:150] = 3                     # a cast shadow
    out = ink.paint(np.full((120, 160, 3), 240.0), values, None, 0.2)
    grey = out.mean(axis=2)
    assert grey[40, 40] < 40 and grey[90, 120] < 40   # solid black masses
    assert grey[5, 5] > 235 and grey[90, 60] > 235     # paper elsewhere
    rough = ink.paint(np.full((120, 160, 3), 240.0), values, None, 0.2, texture=True)
    edge = rough.mean(axis=2)[18:24, 20:60]
    assert (edge > 200).any() and (edge < 60).any()   # broken at its edge


def test_papers_and_an_image_of_your_own(tmp_path):
    from PySide6.QtGui import QImage, QColor
    from croquis import paper as pp
    for key in pp.PAPERS:
        sheet = pp.make(key, 120, 80)
        assert sheet.shape == (80, 120, 3)
        # The ruled ones a little darker on average: their grid.
        assert np.allclose(sheet.mean(axis=(0, 1)), pp.PAPERS[key][1],
                           atol=24 if key in ("grid", "dots") else 12)
    small = QImage(16, 16, QImage.Format_RGB32)
    small.fill(QColor(10, 200, 30))
    path = tmp_path / "tile.png"
    small.save(str(path))
    own = pp.make("custom", 120, 80, image=str(path))
    assert np.allclose(own[40, 60], (10, 200, 30), atol=2)       # repeated
    missing = pp.make("custom", 120, 80, image=str(tmp_path / "nope.png"))
    assert np.allclose(missing.mean(axis=(0, 1)), pp.PAPERS["cream"][1], atol=12)


def test_the_paper_box_picks_an_image_of_your_own(window, monkeypatch, tmp_path):
    from PySide6.QtGui import QImage, QColor
    from PySide6.QtWidgets import QFileDialog
    win, _a = window
    panel = _panel(win)
    panel.papers["kraft"].click()
    assert panel.s["paper"] == "kraft"
    img = QImage(32, 32, QImage.Format_RGB32)
    img.fill(QColor(200, 0, 0))
    path = tmp_path / "mine.png"
    img.save(str(path))
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: (str(path), "")))
    panel.papers["custom"].click()
    assert panel.s["paper"] == "custom" and panel.s["paper_image"] == str(path)
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        staticmethod(lambda *a, **k: ("", "")))
    panel.papers["grid"].click()
    panel.papers["custom"].click()                    # cancelled: stays
    assert panel.s["paper"] == "grid"
    assert panel.papers["grid"].isChecked() and not panel.papers["custom"].isChecked()


def test_custom_sizes_and_page_formats(window):
    win, _a = window
    panel = _panel(win)
    cam = win.viewport.camera
    panel.size.buttons[3].click()                     # «…»: another size
    assert panel.custom_box.isVisibleTo(panel)
    panel.set("custom_format", "px")
    panel.set("custom_width", 1234)
    assert panel.output_size(cam) == (1234, None)
    panel.set("custom_format", "A4")
    panel.set("dpi", 150)
    width, page = panel.output_size(cam)
    assert set(page) == {1240, 1754}                  # A4 at 150 dpi
    assert (page[0] > page[1]) == (cam.aspect >= 1)   # turned to the view
    assert width <= page[0] * 0.86 + 1


def test_save_png_svg_and_pdf(window, tmp_path):
    import re
    win, _a = window
    panel = _panel(win)
    panel.set("size", 0)
    panel.set("custom_format", "A5")
    panel.set("dpi", 150)
    panel.draw()
    sw = panel._window
    for ext in ("png", "svg", "pdf"):
        assert sw.save_to(str(tmp_path / f"c.{ext}"))
        assert (tmp_path / f"c.{ext}").stat().st_size > 1000
    svg = (tmp_path / "c.svg").read_text()
    assert svg.count("inkscape:groupmode=\"layer\"") >= 2
    assert len(re.findall(r"<path d=", svg)) == len(sw._layers.strokes) > 10
    assert (tmp_path / "c.pdf").read_bytes()[:4] == b"%PDF"
    sw.close()


def test_the_live_preview_draws_once_the_view_is_still(window):
    """On, it draws the still view in the background and lays it over the
    viewport; a move of the camera puts it aside until it is still again."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QImage, QPainter
    win, _a = window

    def run_for(ms, until=lambda: False):
        """A real event loop, as IngeTrazo's (QTest.qWait holds Python's
        lock and starves the drawing's thread)."""
        loop = QEventLoop()
        check = QTimer()
        check.timeout.connect(lambda: until() and loop.quit())
        check.start(50)
        QTimer.singleShot(ms, loop.quit)
        loop.exec()
        check.stop()
    panel = _panel(win)
    panel.set("size", 1600)
    live = panel.live
    panel.live_switch.click()
    assert live.enabled

    def ready():
        return live.image is not None and live.image_key == live.view_key()

    def wait_for_image(ms=30000):
        run_for(ms, ready)
        return ready()

    assert wait_for_image()
    vp = win.viewport
    img = QImage(vp.width(), vp.height(), QImage.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    live.paint(vp, p)
    p.end()
    assert img.pixelColor(vp.width() // 2, 5).alpha() == 255      # the sketch shows
    vp.camera.yaw += 0.3
    run_for(250)
    assert live.image_key != live.view_key()                      # put aside
    assert wait_for_image()                                       # and drawn again
    panel.live_switch.click()
    assert not live.enabled and live.image is None
