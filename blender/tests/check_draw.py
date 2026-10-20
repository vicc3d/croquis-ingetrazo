"""Headless check of Croquis for Blender, on a scene made here:

    blender -b --factory-startup --python blender/tests/check_draw.py -- <out dir>

Builds a small scene (a painted cube, a smooth cylinder, a floor, a camera
and a sun), draws it in three styles, saves the drawings and checks they
have ink and colour. Exits non-zero on failure."""
import math
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "build" / "blender"))
import croquis  # noqa: E402  (the staged package: run blender/build.py first)
from croquis import ops  # noqa: E402

out = Path(sys.argv[sys.argv.index("--") + 1]) if "--" in sys.argv else Path(".")
out.mkdir(parents=True, exist_ok=True)
croquis.register()
failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def material(name, rgba):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = rgba
    return m


scene = bpy.context.scene
for o in list(scene.objects):
    bpy.data.objects.remove(o)
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
bpy.context.object.data.materials.append(material("Brick", (0.55, 0.12, 0.06, 1)))
bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.7, depth=3, location=(2.6, 0.4, 1.5))
bpy.ops.object.shade_smooth()
bpy.context.object.data.materials.append(material("Stone", (0.6, 0.58, 0.5, 1)))
bpy.ops.mesh.primitive_plane_add(size=12, location=(1, 0, 0))
bpy.ops.object.camera_add(location=(9, -9, 6))
cam = bpy.context.object
cam.rotation_euler = (math.radians(63), 0, math.radians(45))
scene.camera = cam
bpy.ops.object.light_add(type="SUN", rotation=(math.radians(40), math.radians(20), math.radians(-30)))
scene.render.resolution_x, scene.render.resolution_y = 1600, 1000

s = scene.croquis
for style in ("colour_marker", "watercolour", "hatched"):
    s.preset = style
    t = time.perf_counter()
    layers, secs = ops.draw(bpy.context, width=1600)
    img = ops.to_image(layers, f"croquis-{style}")
    img.filepath_raw = str(out / f"blender-{style}.png")
    img.file_format = "PNG"
    img.save()
    px = layers.pixels()
    ink = (px.sum(axis=2) < 200).mean()
    colour = (px.max(axis=2).astype(int) - px.min(axis=2) > 40).mean()
    print(f"{style}: {px.shape[1]}x{px.shape[0]} in {secs:.1f} s, ink {ink:.3%}, colour {colour:.3%}, strokes {len(layers.strokes)}")
    check(px.shape == (1000, 1600, 3), f"{style}: the render's shape")
    check(ink > 0.002, f"{style}: there is ink")
    if style != "hatched":
        check(colour > 0.01, f"{style}: there is colour")
check(s.preset == "hatched", "a style sets its choices")
s.hand = 10
check(s.preset == "hatched", "the hand is not a style's choice")
s.technique = "marker"
check(s.preset == "custom", "changing a style's choice makes it Custom")

# The sun: the drawing reads the Sun lamp's direction.
from croquis import scene_view as sv  # noqa: E402
cam_ = sv.camera_from_object(cam, bpy.context.evaluated_depsgraph_get(), scene)
v = sv.BlenderView(bpy.context, bpy.context.evaluated_depsgraph_get(), cam_)
sun = v.scene.croquis_sun()
check(sun is not None and abs(math.hypot(*sun) - 1) < 1e-6, "the Sun lamp is found")
tris, hard, soft, soft_n = v.hlr_geometry()
check(len(soft) > 0 and len(hard) >= 12, f"hard {len(hard)} and soft {len(soft)} edges")

croquis.unregister()
print("FAILURES:", len(failures))
sys.exit(1 if failures else 0)
