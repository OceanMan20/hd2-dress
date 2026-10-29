# HD2 Dress Blender add-on

The author guide with pictures is **[GUIDE.md](GUIDE.md)** (also as GUIDE.html). This page holds developer notes.

- Engine cloth only (since 0.3.0, 2026-10-18). The old Lua route (bone chains + a Lua runtime) is no longer used; its
  panel code is in git history before commit 2aa2938.
- Code: `blender/hd2_dress/` (panel, `jobs.py` background Blender runner, `settings.py` panel <-> TOML). The engine tools
  in `tools/` are bundled into the zip (`hd2_dress/tools/`) by `python3 tools/build_addon.py` -> `dist/other/`.
- The slow steps (build, preview, reading the diver skeleton) run in a separate `blender -b` process, so the author's
  session and HD2SDK's open patch are never touched.
- Tests: `blender -b SCENE.blend -P tools/test_addon.py -- ARMOUR_PATCH COLOUR_MAP OUT_DIR` (every button, checked by
  its effect). Live GUI smoke tests: Blender inside Xephyr (`Xephyr :5`) driven with xdotool (Wayland blocks synthetic
  input into normal windows); see PROJECT_LOG.md.
- bongo dev setup: portable Blender `~/apps/blender-5.2.2-linux-x64/blender`, add-on folder symlinked to this repo.
