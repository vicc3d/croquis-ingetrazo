#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the Blender extension: croquis_blender with IngeTrazo Croquis's
drawing core copied in as ``core`` (one core for both programs), packed by
Blender's own ``extension build``.

    python3 blender/build.py [--blender /path/to/blender] [--stage-only]

Leaves build/blender/croquis/ (the staged package) and, unless
``--stage-only``, build/blender/croquis-<version>.zip next to it.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "blender" / "croquis_blender"
CORE = ROOT / "croquis"
#: The drawing, without IngeTrazo's panel, live preview or Qt export.
CORE_MODULES = ("compose", "drawing", "hatch", "ink", "marker", "palette",
                "paper", "presets", "raster", "shadow", "strokes",
                "texts", "vector", "visibility", "watercolour")


def stage(out: Path) -> Path:
    pkg = out / "croquis"
    if pkg.exists():
        shutil.rmtree(pkg)
    shutil.copytree(SRC, pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    core = pkg / "core"
    core.mkdir()
    (core / "__init__.py").write_text(
        '"""IngeTrazo Croquis\'s drawing core, copied in at build time."""\n',
        encoding="utf-8")
    for name in CORE_MODULES:
        shutil.copy2(CORE / f"{name}.py", core / f"{name}.py")
    return pkg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blender", default="blender")
    ap.add_argument("--stage-only", action="store_true")
    args = ap.parse_args()
    out = ROOT / "build" / "blender"
    out.mkdir(parents=True, exist_ok=True)
    pkg = stage(out)
    print("staged", pkg)
    if args.stage_only:
        return 0
    return subprocess.call([args.blender, "--command", "extension", "build",
                            "--source-dir", str(pkg), "--output-dir", str(out)])


if __name__ == "__main__":
    sys.exit(main())
