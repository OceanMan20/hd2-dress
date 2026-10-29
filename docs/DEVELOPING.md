# Developing HD2 Dress

## One-time setup
1. `git clone https://github.com/OceanMan20/hd2-dress.git ~/hd2-dress` (or `git pull` if it is there).
2. Blender 4.0-5.2 with HD2SDK Community Edition 3.11.0 enabled.
3. Point Blender's add-on at the repo, so code changes are live (replace any installed copy):
   `ln -sfn ~/hd2-dress/blender/hd2_dress <blender>/portable/scripts/addons/hd2_dress`
   (the add-on finds the build tools in the repo's tools/ by itself when run from a checkout).
4. Helldivers 2 installed (the build reads the game files; found through Steam, or set HD2_DATA=.../Helldivers 2/data).

## Fixing a user's bug
1. `git pull`.
2. Read the user's build log (`<user folder>/.cache/hd2-dress/panel/<cloth name>/build.log`): the panel prints the path,
   and every build error is an `ERROR:` line (a crash also leaves a Python traceback above it).
3. Fix, then run `tests/run_tests.sh` (all buttons, checked by their effect; must stay all PASS).
   Also on the OLDEST supported Blender (4.0, Python 3.10: no tomllib, older API): `tests/run_tests.sh
   ~/apps/blender-4.0.2-linux-x64/blender`, with HD2SDK and the built add-on zip unpacked in that Blender's
   `4.0/scripts/addons/` (the runner picks the 4.x test scene by itself).
4. If you touched the generator, check normal builds are unchanged: build the same settings before and after and
   compare the cloth patch_0 files (`cmp`); only the base patch differs (a random texture id).
5. Bump `version` in blender/hd2_dress/__init__.py, `python3 tools/build_addon.py` (-> dist/other/), refresh the author
   package with tools/pack_authors.py (after build_guide_html.py and build_addon.py), log it in docs/PROJECT_LOG.md, commit, push.

## Notes
- tests/fixtures (not in this repository: made from game assets, see tests/README.md) hold a B-01 hip armour with a test skirt.
- The motion preview's assets are cached per machine in ~/.cache/hd2-dress/viewer (panel: "Load the Helldiver").
- Windows: the add-on runs on Windows too (last full check: 0.4.1); the build is platform-neutral Python.
