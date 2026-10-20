#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# The zip IngeTrazo's extension manager installs: one folder, croquis/,
# with its __init__.py, from git HEAD (what is committed, nothing else).
#   tools/make_release.sh            -> build/croquis-<version>.zip + sha256
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VER="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' croquis/__init__.py)"
mkdir -p build
OUT="build/croquis-$VER.zip"
rm -f "$OUT"
git archive --format=zip -9 -o "$OUT" HEAD croquis
sha256sum "$OUT" | tee "$OUT.sha256"
