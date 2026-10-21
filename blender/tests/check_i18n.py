"""Every text of the panel translated in Spanish and Portuguese:

    blender -b --factory-startup --python blender/tests/check_i18n.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "build" / "blender"))
import bpy
import croquis
croquis.register()
found = set()
rna = bpy.types.Scene.bl_rna.properties["croquis"].fixed_type
for p in rna.properties:
    if p.identifier == "rna_type": continue
    found |= {p.name, p.description}
    if p.type == "ENUM":
        for it in p.enum_items: found |= {it.name, it.description}
for it in __import__("croquis.props", fromlist=["x"])._papers_cached():
    found |= {it[1], it[2]}
for cls in bpy.types.Panel.__subclasses__():
    if cls.__name__.startswith("CROQUIS"): found.add(cls.bl_label)
for op in ("draw", "save"):
    o = getattr(bpy.ops.croquis, op).get_rna_type()
    found |= {o.name, o.description}
    for p in o.properties:
        if p.identifier in ("rna_type", "filepath", "filter_glob"): continue
        found |= {p.name, p.description}
        if p.type == "ENUM":
            for it in p.enum_items: found |= {it.name, it.description}
found -= {"", "Name", "Unique name used in the code and scripting, can be re-defined in Python sub-classes if needed"}
same_ok = {"Croquis", "S", "M", "L", "PNG", "PDF", "Kraft", "Diagonal", "Format", "Style", "Estilo"}
bad = False
prefs = bpy.context.preferences.view
prefs.use_translate_interface = True
for lang in ("es", "pt_BR"):
    prefs.language = lang
    miss = sorted(s for s in found if bpy.app.translations.pgettext_iface(s) == s and s not in same_ok)
    sample = {s: bpy.app.translations.pgettext_iface(s) for s in ("Hand", "Colour marker", "Draw the view", "This view", "Saved {path}")}
    print(lang, "untranslated:", miss)
    print(lang, "sample:", sample)
    print(lang, "report:", croquis.i18n.tr("Croquis: {w}×{h} in {s} s", w=1600, h=1000, s="2.1"))
    bad = bad or bool(miss)
print("FAILURES:", int(bad))
sys.exit(1 if bad else 0)
