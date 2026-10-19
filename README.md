# IngeTrazo Croquis

An extension for [IngeTrazo](https://github.com/ingelibre/ingetrazo) that
draws the current view of the model as a **freehand sketch on paper**, the
way an architect sketches: lines that run past the corners, bow and waver
with the hand, swell in the middle and thin at the ends, drawn twice now and
then, with the outlines heavier than the edges inside.

Light and shade go on in **grey marker**: each face white, light grey or
dark grey by how the light falls on it (a classic light from the upper left,
or the sun of IngeTrazo's Shadows panel), in broad parallel strokes up the
walls and across the roofs, darker where they overlap, ragged at the ends,
and a little off the ink lines. Cast shadows, colour markers, hatching and
watercolour washes come next.

## Install

1. In IngeTrazo, **Extensions ▸ Open plugins folder**.
2. Copy the `croquis` folder there.
3. Restart IngeTrazo. A **Croquis** tab appears in the side tray.

## Use

Frame the view in IngeTrazo, set the hand (from *Ruler* to *Loose*), the line
weight and the overshoot, and press **Draw the view**. The drawing opens in a
window of its own, to save as PNG or copy. Perspective, two-point and
parallel views all work. The settings are kept between sessions.

## How it works

- **Which lines:** the model's triangles go into a depth buffer at the
  drawing's resolution, and every edge is walked pixel by pixel; where
  nothing stands in front of it, it shows. Soft edges show only where the
  surface turns away from the eye. Pieces that continue each other in a
  straight line are joined, so a wall's edge is one stroke. (IngeTrazo's own
  hidden-line pass is exact, but takes minutes on a large model; a sketch
  does not need exact lines.)
- **Outlines:** a line with the background, or a surface well behind it, on
  one side is where a shape ends, and is drawn heavier.
- **The marker:** the same depth buffer says which face shows at every
  pixel; its normal against the light gives the value. The strokes run up
  a wall (the world's vertical, as drawn) or across a floor along its
  flatter axis, and are multiplied onto the paper, as a marker's ink is.
- **The hand:** each line overshoots at real corners only (never where it
  passes behind something), bows more the longer it is, wavers, swells and
  thins. Everything random is seeded by the line itself, so the same view
  always gives the same drawing.

## Tests

```bash
python -m pytest tests/test_strokes.py
INGETRAZO_SRC=/path/to/ingetrazo QT_QPA_PLATFORM=offscreen \
    /path/to/ingetrazo/venv/bin/python -m pytest tests
```

The second run checks the lines against IngeTrazo's exact hidden-line
drawing, in perspective, two-point and parallel.

## Credits

**Concept, UX/UI & Design:** [Victor Crespo](https://3dvic.com)

Independent extension, not affiliated with IngeTrazo's maintainers.
IngeTrazo is by Marco Sumari Tellez and contributors.

License: GPL-3.0-or-later.
