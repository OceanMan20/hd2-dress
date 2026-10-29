# dev/: personal test helpers

Not part of HD2 Dress. Nothing here is shipped (build.sh, dist/), and the author guides
(docs/AUTHORING.md, docs/BLENDER_ADDON.md) do not mention it. Quick conversion scripts for testing
on this machine only.

- `retarget.py`: copies an armour mod (and its HD2 Dress rig + registration) onto an armour you own,
  e.g. a dress mod for armour you don't have onto B-01, so it can be tried in game. Rough: matches
  pieces by slot/piece type/body type and hides unmatched target pieces as a 1 mm triangle.
  Usage: see the top of the file. Output goes to the folder you give it; it never writes into the
  game folder.
