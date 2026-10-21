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
# Saving: PNG, SVG in layers, PDF.
for fmt in ("PNG", "SVG", "PDF"):
    path = out / f"blender-hatched.{fmt.lower()}"
    ok = ops.save_drawing(layers, str(path), fmt)
    check(ok and path.is_file() and path.stat().st_size > 1000, f"saved as {fmt}")
svg = (out / "blender-hatched.svg").read_text()
check(svg.count('inkscape:groupmode="layer"') == 2 + (layers.fill is not None),
      "the SVG has its layers")
check(svg.count("<path ") == len(layers.strokes), "every stroke a path in the SVG")
check("image/jpeg" in svg, "the SVG's paper encoded by Blender (JPEG)")
pdf = (out / "blender-hatched.pdf").read_bytes()
check(pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF"), "the PDF is whole")
check(b"/DCTDecode" in pdf, "the PDF's picture encoded by Blender (JPEG)")
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

# A picture on a sheet (an image's transparency, a few faces in a plane),
# even joined into another object, is left out; the solid next to it stays.
img = bpy.data.images.new("figure", 8, 8, alpha=True)
fig = bpy.data.materials.new("Figure")
fig.use_nodes = True
nt = fig.node_tree
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
nt.links.new(tex.outputs["Alpha"], nt.nodes["Principled BSDF"].inputs["Alpha"])
bpy.ops.mesh.primitive_cube_add(size=1, location=(-3, 0, 0.5))
solid = bpy.context.object
bpy.ops.mesh.primitive_plane_add(size=2, location=(-3, -2, 1), rotation=(math.radians(90), 0, 0))
sheet = bpy.context.object
sheet.data.materials.append(fig)
bpy.ops.object.select_all(action="DESELECT")
solid.select_set(True)
sheet.select_set(True)
bpy.context.view_layer.objects.active = solid
bpy.ops.object.join()
joined = bpy.context.object
check(sv.cutout_slots(joined, joined.data) == {len(joined.material_slots) - 1},
      "the picture's material is a cut-out")
t, _m, h, _s, _n = sv.mesh_parts(joined.data, joined.matrix_world,
                                 sv.cutout_slots(joined, joined.data))
check(len(t) == 12 and len(h) == 12, f"only the cube is drawn ({len(t)} triangles, {len(h)} edges)")

croquis.unregister()
print("FAILURES:", len(failures))
sys.exit(1 if failures else 0)
