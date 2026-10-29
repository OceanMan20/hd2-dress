#!/bin/bash
# Run the HD2 Dress panel test (every button, checked by its effect) on any machine with Blender + HD2SDK + the game.
#   tests/run_tests.sh [path/to/blender]
# Blender: argument, else $BLENDER, else ~/apps/blender-*/blender, else `blender` on PATH.
# Uses only files in this repo (tests/fixtures) plus the game data (found automatically, or set HD2_DATA).
set -e
cd "$(dirname "$0")/.."
B="${1:-${BLENDER:-$(ls -d ~/apps/blender-*/blender 2>/dev/null | sort | tail -1)}}"
[ -x "$B" ] || B=$(command -v blender)
[ -x "$B" ] || { echo "Blender not found: tests/run_tests.sh /path/to/blender"; exit 1; }
W=$(mktemp -d /tmp/hd2dress-test.XXXX)
FX=tests/fixtures/skirt_test.blend
"$B" --version 2>/dev/null | head -1 | grep -q "Blender 4\." && FX=tests/fixtures/skirt_test_b4.blend   # 4.x cannot read 5.x files
cp "$FX" "$W/skirt_test.blend"
echo "Blender: $B   work folder: $W"
"$B" -b "$W/skirt_test.blend" -P tools/test_addon.py -- tests/fixtures/9ba626afa44a3aa3.patch_0 tests/fixtures/tartan_color.png "$W/out" 2>&1 \
  | grep -E "^(PASS|FAIL|SUMMARY)|Traceback" | cut -c1-200
