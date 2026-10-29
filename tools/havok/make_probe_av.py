"""Probe 2: same probe cloth, but in a patch of the AVATAR archive (18235e0c9ec0e636.patch_0), so it is part of
the package that holds the body unit 4d1c334d294dfa97 (and the capes)."""
import bpy, sys, os, addon_utils
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager; AV = '18235e0c9ec0e636'
OUT = os.path.expanduser('~/.cache/hd2-dress/havok_test/patch_probe_av'); os.makedirs(OUT, exist_ok=True)
av = TM.LoadArchive(G + AV, True, False)
TM.ActiveArchive = av; TM.CreatePatchFromActive('HD2 Dress: avatar cloth probe')
TM.ActivePatch.UpdatePath(os.path.join(OUT, AV + '.patch_0'))
src = av.TocDict[0xd7014a50477953e0][0x3c33cf10a26cbb3e]; src.Load(False, False)
d = bytearray(src.TocData); i = d.find(b'helldiver_cape\0')
while i >= 0: d[i:i + 14] = b'dress_probe_02'; i = d.find(b'helldiver_cape\0', i + 1)
e = TM.AddEntryToPatchID(src, 0x4d1c334d294dfa97, ReloadUI=False); e.TocData = bytes(d)
print('PROBE avatar patch with cloth 4d1c334d294dfa97')
TM.PatchActiveArchive()
