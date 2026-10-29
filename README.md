# HD2 Dress

Real cloth physics for Helldivers 2 armour mods: skirts, capes, coat tails, cloaks, sleeves, hair and ribbons, simulated
by the game's own cloth engine (Havok Cloth, the system that moves the stock capes). No scripts and no loader: players
install the built patch files like any other armour mod.

HD2 Dress is a **Blender add-on** that works next to [HD2SDK Community Edition](https://github.com/Boxofbiscuits97/HD2SDK-CommunityEdition):
the author marks which faces are cloth, sets pins and physics, and presses Build. The add-on writes a Havok cloth
resource for the armour unit and the patch files to ship.

> **Status: looking for a new maintainer.** The original author has stepped back. The project works (version 0.6.24,
> tested in game with several community mods), and there is a list of known open problems in
> [docs/STATUS.md](docs/STATUS.md). Forks and takeovers are welcome. Everything learned so far is written down here.

## For mod authors

1. Download the latest **author package** from [Releases](../../releases) (`HD2-Dress-<version>-for-authors.zip`).
2. Install the add-on zip inside it in Blender 4.0 to 5.2 (*Edit > Preferences > Add-ons > Install from Disk*), next
   to HD2SDK Community Edition 3.11.
3. Follow **[docs/GUIDE.md](docs/GUIDE.md)** (step by step, with pictures; `GUIDE.html` in the package is the same).

The most important rules (Check in the panel tells you when one is broken):
- The cloth goes on **a unit of its own with one material** (the game draws a cloth mesh with its first material only).
- **One layer** of faces (no Solidify); use *Add back side* if the inside can be seen.
- Weight-paint the cloth normally; pin where it hangs from.

## For developers

- [docs/STATUS.md](docs/STATUS.md): **start here.** What works, what is known about the engine, the open problems.
- [docs/DEVELOPING.md](docs/DEVELOPING.md): setup, tests, release steps.
- [docs/ENGINE_CLOTH_GUIDE.md](docs/ENGINE_CLOTH_GUIDE.md): the command-line build and every setting.
- [docs/ENGINE_CLOTH_VALUES.md](docs/ENGINE_CLOTH_VALUES.md): every tested physics value and what it did in game.
- [docs/PROJECT_LOG.md](docs/PROJECT_LOG.md): the full history, including the failed approaches (long; newest at the top
  of the release list).

### Layout

| Path | What |
|---|---|
| `blender/hd2_dress/` | the Blender add-on (panel, settings, collider view, background jobs) |
| `tools/hd2dress_cloth.py` | the build: armour patch + settings TOML -> cloth patches (runs inside Blender) |
| `tools/gen_engine_cloth.py` | the Havok cloth generator (particles, constraints, colliders, render copy) |
| `tools/havok_model.py`, `havok_tagfile.py`, `havok_writer.py`, `havok_cloth.py` | Havok tagfile reader/writer |
| `tools/hd2dress_prep.py` | Check & Fix all, Fit to my model, mesh origin fix, back side |
| `tools/align_patch.py` | aligns patch TOC entries (the game ignores a patch with a misaligned cloth entry) |
| `tools/test_addon.py`, `tests/run_tests.sh` | the panel test (every button, checked by its effect) |
| `tools/build_addon.py`, `tools/pack_authors.py`, `tools/build_guide_html.py` | release packaging |
| `mod/`, `sim/` | **legacy**: the first version was a Lua addon (Bingus loader). Not used any more, kept as history |

The tests need a small HD2SDK test scene made from game assets, which is not in this repository: see
[tests/README.md](tests/README.md) for how to make your own.

## Credits

- Original author: OceanMan (with heavy help from Claude, Anthropic's AI assistant, which wrote most of the code).
- **thebf333**: UV tangents, bend-constraint guard, roughness map and more (0.6.12).
- The testers in the HD2 modding community who sent their mods and patch files.
- Built on HD2SDK Community Edition. Helldivers 2 is a game by Arrowhead Game Studios; this project is not affiliated
  with Arrowhead or Sony. No game files are included here.

## License

**Do whatever you like with it**: use it, change it, fork it, take it over, include it in your own tools or mods.
The one condition is **credit**: keep the license file with OceanMan's name in your copy, and mention HD2 Dress /
OceanMan as the origin when you share or release something built from it.

Formally this is the MIT license, see [LICENSE](LICENSE). `tools/_vendor/tomli` is MIT too (its own license file is next
to it).
