"""Probe: does the engine create cloth for an ARMOUR unit that has a cloth resource with its own id?
Adds the stock cape cloth (renamed 'dress_probe_01' so it is findable in memory) under the B-01 hip unit ids."""
import bpy, sys, os, struct, addon_utils
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager
OUT = os.path.expanduser('~/.cache/hd2-dress/havok_test/patch_probe'); os.makedirs(OUT, exist_ok=True)
base = TM.LoadArchive(G + m.BaseArchiveHexID, True, False)
av = TM.LoadArchive(G + '18235e0c9ec0e636', False, False)
TM.ActiveArchive = base; TM.CreatePatchFromActive('HD2 Dress: armour cloth probe')
TM.ActivePatch.UpdatePath(os.path.join(OUT, m.BaseArchiveHexID + '.patch_0'))
src = av.TocDict[0xd7014a50477953e0][0x3c33cf10a26cbb3e]; src.Load(False, False)
d = bytearray(src.TocData)
n = 0; i = d.find(b'helldiver_cape\0')
while i >= 0: d[i:i + 14] = b'dress_probe_01'; n += 1; i = d.find(b'helldiver_cape\0', i + 1)
for uid in (0x2f66b9373cb58485, 0x0387a158d04848f4, 0x4d1c334d294dfa97):
    e = TM.AddEntryToPatchID(src, uid, ReloadUI=False); e.TocData = bytes(d)
    print(f'PROBE cloth {uid:016x} ({n} names renamed)')
TM.PatchActiveArchive()
