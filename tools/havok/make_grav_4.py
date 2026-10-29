import bpy, sys, os, struct, addon_utils
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager
OUT = os.path.expanduser('~/.cache/hd2-dress/havok_test/patch_grav4'); os.makedirs(OUT, exist_ok=True)
base = TM.LoadArchive(G + m.BaseArchiveHexID, True, False)
av = TM.LoadArchive(G + '18235e0c9ec0e636', False, False)
TM.ActiveArchive = base; TM.CreatePatchFromActive('HD2 Dress: cape gravity tagfile 4 only')
TM.ActivePatch.UpdatePath(os.path.join(OUT, m.BaseArchiveHexID + '.patch_0'))
NEW = {0.7: 0.444, 0.8: 0.555, 0.88: 0.666}
for fid, e in av.TocDict[0xd7014a50477953e0].items():
    e.Load(False, False); d = bytearray(e.TocData)
    spans, p = [], 0
    while True:
        i = d.find(b'TAG0', p)
        if i < 4: break
        size = struct.unpack_from('>I', d, i - 4)[0] & 0x3FFFFFFF; spans.append((i - 4, i - 4 + size)); p = i + 4
    n = 0
    g = struct.pack('<4f', 0.0, 0.0, -9.8100004196167, 0.0)
    for k in (4,):
        a, z = spans[k]
        for dv in (0.7, 0.8, 0.88):
            pat = g + struct.pack('<f', dv)
            i = d.find(pat, a)
            while 0 <= i < z:
                struct.pack_into('<f', d, i + 8, 9.81); n += 1; i = d.find(pat, i + 1)
    e.TocData = bytes(d); TM.AddEntryToPatchID(e, fid, ReloadUI=False)
    print(f'SETUP {fid:016x}: flipped gravity in {n} simulations (tagfile 4 only)')
TM.PatchActiveArchive()
