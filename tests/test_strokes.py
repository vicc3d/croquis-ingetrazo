"""The freehand strokes, on their own (no Qt, no IngeTrazo)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from croquis import strokes as st  # noqa: E402

# A square, and a line ending against its side (a T, not a corner).
SQUARE = np.array([[100, 100, 300, 100], [300, 100, 300, 300],
                   [300, 300, 100, 300], [100, 300, 100, 100]], dtype=float)
T_LINE = np.array([[400, 200, 300, 200]], dtype=float)


def test_corners_and_tees():
    segs = np.vstack([SQUARE, T_LINE])
    c = st.corner_ends(segs, tol=2.0)
    assert c[:4].all()                     # every square end meets another
    assert not c[4].any()                  # the T's ends meet no end


def test_same_view_same_drawing():
    a = st.strokes_for(SQUARE, None, st.LineStyle(), 1000)
    b = st.strokes_for(SQUARE, None, st.LineStyle(), 1000)
    assert len(a) == len(b)
    assert all(np.array_equal(x.outline, y.outline) for x, y in zip(a, b))


def test_a_ruler_draws_straight_lines_without_overshoot():
    style = st.LineStyle(hand=0.0, double_stroke=False, breaks=False)
    out = st.strokes_for(SQUARE, None, style, 1000)
    assert len(out) == 4
    for seg, s in zip(SQUARE, out):
        a, b = seg[:2], seg[2:]
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        off = (s.outline - a) @ n
        along = (s.outline - a) @ d
        assert np.abs(off).max() <= style.width          # within the ink
        assert along.min() >= -1e-6 and along.max() <= np.linalg.norm(b - a) + 1e-6


def test_the_hand_overshoots_corners_but_not_tees():
    style = st.LineStyle(hand=1.0, double_stroke=False, breaks=False, overshoot=1.5)
    sq = st.strokes_for(SQUARE, None, style, 1000)
    a, b = SQUARE[0, :2], SQUARE[0, 2:]
    d = (b - a) / np.linalg.norm(b - a)
    along = (sq[0].outline - a) @ d
    assert along.min() < -2 and along.max() > 202        # past both corners
    tee = st.strokes_for(np.vstack([SQUARE, T_LINE]), None, style, 1000)[-1]
    a, b = T_LINE[0, :2], T_LINE[0, 2:]
    d = (b - a) / np.linalg.norm(b - a)
    along = (tee.outline - a) @ d
    assert along.max() <= 100 + 1.0                       # stops at the side


def test_outlines_are_heavier_and_size_scales():
    style = st.LineStyle(hand=0.0, double_stroke=False, breaks=False)
    thin = st.strokes_for(SQUARE[:1], np.array([False]), style, 1000)[0]
    heavy = st.strokes_for(SQUARE[:1], np.array([True]), style, 1000)[0]
    big = st.strokes_for(SQUARE[:1] * 2, np.array([False]), style, 2000)[0]

    def width(s):
        return np.ptp(s.outline[:, 1])
    assert width(heavy) > 1.8 * width(thin)
    assert abs(width(big) - 2 * width(thin)) < 0.05 * width(big)


def test_nothing_in_nothing_out():
    assert st.strokes_for(np.zeros((0, 4)), None, st.LineStyle(), 1000) == []
    assert st.strokes_for(np.array([[5, 5, 5.1, 5]]), None, st.LineStyle(), 1000) == []


def _circle(cx, cy, r, k):
    a = np.linspace(0, 2 * np.pi, k + 1)
    p = np.c_[cx + r * np.cos(a), cy + r * np.sin(a)]
    return np.c_[p[:-1], p[1:]]


def test_a_curve_in_short_pieces_has_no_corners():
    """A pipe or an arc drawn in many short pieces: each joint turns a few
    degrees, which a hand draws on, without the overshoot of a corner."""
    c = st.corner_ends(_circle(500, 500, 120, 36), tol=2.0)
    assert not c.any()
    # The square's corners still are.
    assert st.corner_ends(SQUARE, tol=2.0).all()


def test_a_cluster_of_fine_detail_has_no_corners():
    rng = np.random.default_rng(1)
    centre = np.array([200.0, 200.0])
    ends = centre + rng.uniform(-0.5, 0.5, (40, 2))
    far = ends + rng.uniform(-30, 30, (40, 2))
    segs = np.c_[ends, far]
    assert not st.corner_ends(segs, tol=2.0)[:, 0].any()


def test_a_curve_in_short_pieces_reads_unbroken():
    """Its pieces run a hair into each other, not short of each other
    (that drew a circle dashed)."""
    circle = _circle(500, 500, 120, 36)
    corner, goes_on, pairs = st.end_joins(circle, tol=2.0)
    assert goes_on.all() and not corner.any()
    assert len(set(st.chains(len(circle), pairs).tolist())) == 1
    style = st.LineStyle(hand=0.6, double_stroke=False, breaks=False)
    for seg, s in zip(circle, st.strokes_for(circle, None, style, 1000)):
        a, b = seg[:2], seg[2:]
        d = (b - a) / np.linalg.norm(b - a)
        along = (s.outline - a) @ d
        assert along.min() < 0.0 and along.max() > np.linalg.norm(b - a)


def test_simplify_thins_a_crowd_and_keeps_shapes():
    rng = np.random.default_rng(4)
    # A crowd of short lines (bolts, a railing's bars) ...
    p = rng.uniform(400, 460, (600, 2))
    crowd = np.c_[p, p + rng.uniform(-6, 6, (600, 2))]
    # ... an outline through it, and a small circle in it, in short pieces.
    edge = np.array([[300.0, 430.0, 560.0, 430.0]])
    ring = _circle(430, 430, 8, 24)
    segs = np.vstack([crowd, edge, ring])
    outline = np.r_[np.zeros(600, bool), True, np.zeros(24, bool)]
    out, kept_outline, weight = st.simplify(segs, outline, 1000)
    assert len(out) < 0.5 * len(segs)                 # the crowd thinned
    assert any(np.allclose(o, edge[0]) for o in out)  # the outline stays
    assert kept_outline.sum() == 1
    kept_ring = sum(any(np.allclose(o, r) for o in out) for r in ring)
    assert kept_ring in (0, 24)                       # the circle whole or not
    assert weight.min() < 1.0
    # A plain drawing is left as it is.
    out, _o, weight = st.simplify(SQUARE, None, 1000)
    assert len(out) == 4 and (weight == 1.0).all()
