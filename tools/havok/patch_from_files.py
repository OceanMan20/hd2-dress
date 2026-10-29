"""blender -b -P patch_from_files.py -- OUTDIR ARCHIVE TYPEHEX:IDHEX:FILE [...]
Writes ARCHIVE.patch_0 into OUTDIR holding the given resources (main data from FILE)."""
import bpy, sys, os, addon_utils
args = sys.argv[sys.argv.index('--') + 1:]
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager; out, arc = args[0], args[1]; os.makedirs(out, exist_ok=True)
a = TM.LoadArchive(G + arc, True, False)
for extra in os.environ.get('HD2_SRC', '18235e0c9ec0e636').split(','):
    if extra and extra != arc: TM.LoadArchive(G + extra, False, False)
TM.ActiveArchive = a
TM.CreatePatchFromActive('HD2 Dress test'); TM.ActivePatch.UpdatePath(os.path.join(out, arc + '.patch_0'))
for spec in args[2:]:
    t, i, f = spec.split(':', 2); t, i = int(t, 16), int(i, 16)
    src = None
    for aa in TM.LoadedArchives:
        src = aa.TocDict.get(t, {}).get(i) or src
    if src is None:  # not in the active archive: take any entry of that type as a carrier
        src = next(iter(next(aa for aa in TM.LoadedArchives if t in aa.TocDict).TocDict[t].values()))
    src.Load(False, False)
    e = TM.AddEntryToPatchID(src, i, ReloadUI=False); e.TocData = open(f, 'rb').read(); e.GpuData = b''; e.StreamData = b''
    print(f'PATCH {arc} type {t:016x} id {i:016x} <- {f} ({len(e.TocData)} bytes)')
TM.PatchActiveArchive()
