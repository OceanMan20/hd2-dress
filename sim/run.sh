#!/bin/sh
# Simulate a dress on the game's own animations and render a video (no game needed).
#   sim/run.sh NAME "ID:LOOPS ID:LOOPS ..." [KEY=value ...]   -> sim/videos/NAME.mp4
# Animation ids come from sim/anims/layer0.json (exported once from the game files by
# sim/anim_export.py; sim/classify.py lists them by motion). KEY=value overrides any run_sim.lua
# setting (physics, skirt shape, leg capsules), e.g. DAMPING=0.1 THIGH_R=0.09.
set -eu
cd "$(dirname "$0")"
B="${BLENDER:-$HOME/apps/blender-5.2.2-linux-x64/blender}"
NAME="$1"; SEQ="$2"; shift 2
mkdir -p anims videos work
[ -f anims/layer0.json ] || "$B" -b -P anim_export.py -- anims/layer0.json --layer 0 2>&1 | grep -E '^EXPORT wrote|Error'
python3 prepare.py anims/layer0.json "work/$NAME.lua" $SEQ --hold 1.5
luajit run_sim.lua "work/$NAME.lua" "work/$NAME.csv" "$@"
"$B" -b -P render.py -- "work/$NAME.csv" "videos/$NAME.mp4" --title "$NAME $*" 2>&1 | grep -E '^RENDER wrote|Error|Traceback'
