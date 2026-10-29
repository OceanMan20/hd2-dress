#!/bin/sh
# Build the gating test: tests, the Lua addon zip and the armour patch zip, into dist/.
#   ./build.sh VERSION          (needs ~/apps Blender + HD2SDK: ~/hd2-jaeger/tools/setup_blender_sdk.sh)
set -eu
cd "$(dirname "$0")"
V="${1:?version, e.g. 0.1.0}"
B="${BLENDER:-$HOME/apps/blender-5.2.2-linux-x64/blender}"
luajit tools/test_hd2dress.lua
luajit tools/test_chain.lua
luajit tools/test_skirt.lua
luajit tools/test_dress_runtime.lua
luajit tools/test_body.lua
luajit tools/test_blast.lua
python3 tools/pack.py selftest
python3 tools/pack.py addon mod/hd2dress.lua dist/other "$V"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
"$B" -b -P tools/build_gate_patch.py -- "$T/patch" 2>&1 | grep -E '^GATE|Error|Traceback' || true
[ -f "$T/patch/9ba626afa44a3aa3.patch_0" ] || { echo "armour patch build failed"; exit 1; }
python3 tools/pack.py armour "$T/patch" dist/other HD2-Dress-gate-armour "$V"
