# Contributing to HD2 Dress

The original author has stepped back, so this project lives on through forks and pull requests. Anything goes: fixes,
new features, a full takeover. The only ask is credit (see the README's License section).

## Before you start

1. Read [docs/STATUS.md](docs/STATUS.md): what works, what is known about the game's cloth engine, the open problems.
2. Set up Blender 4.0 to 5.2 with HD2SDK Community Edition 3.11 and link the add-on from your checkout
   ([docs/DEVELOPING.md](docs/DEVELOPING.md)).
3. Make your own test scene ([tests/README.md](tests/README.md)): game-derived files cannot be shared here.

## Making a change

- Run `tests/run_tests.sh` before and after; every check should PASS. If you change the generator
  (`tools/gen_engine_cloth.py`), build the same settings before and after and compare the cloth files.
- Test in game when the change affects what the game sees. Many earlier bugs only showed in game (the project log has
  the measurements).
- Write down what you found in [docs/PROJECT_LOG.md](docs/PROJECT_LOG.md): the next person needs the why, not just the
  code.
- Never commit game files, other people's mods or patch files (`.gitignore` blocks the usual ones).

## Good first problems

From docs/STATUS.md: cloned divers (loadout terminal, armour screen) draw the cloth as spikes; cloth meshes with more
than one material; wind tuning on large cloths.
