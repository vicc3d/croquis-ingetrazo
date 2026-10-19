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
