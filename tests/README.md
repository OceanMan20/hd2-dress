# Tests

`tests/run_tests.sh [path/to/blender]` clicks every button of the panel in a background Blender and checks the effect
(27 checks). It needs a test scene made from game assets, which cannot be published, so make your own once:

1. In Blender with HD2SDK, import the **B-01 Tactical** hip armour for both body types (Slim `2f66b9373cb58485`,
   Stocky `0387a158d04848f4`) and export them into a patch: `tests/fixtures/9ba626afa44a3aa3.patch_0` (+ `.gpu_resources`,
   `.stream`).
2. Model a simple skirt on both hip meshes (a cone, one layer, unwrapped) and put its vertices in a vertex group
   `cloth_skirt` and its top row in `pin`. Save as `tests/fixtures/skirt_test.blend` (for Blender 4.x also save a copy
   from Blender 4.5 as `skirt_test_b4.blend`).
3. Any colour image as `tests/fixtures/tartan_color.png`.

Some checks compare exact counts from the original fixture (648 cloth vertices per body, 18 pins). With your own scene,
adjust those numbers in `tools/test_addon.py` or match them.
