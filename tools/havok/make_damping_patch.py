import bpy, sys, os, struct, addon_utils
sys.path.insert(0, os.path.expanduser('~/hd2-dress/tools'))
import havok_tagfile as H
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager
OUT = os.path.expanduser('~/.cache/hd2-dress/havok_test/patch_damp')
os.makedirs(OUT, exist_ok=True)
CLOTH = 0xd7014a50477953e0
base = TM.LoadArchive(G + m.BaseArchiveHexID, True, False)
av = TM.LoadArchive(G + '18235e0c9ec0e636', False, False)
TM.ActiveArchive = base
TM.CreatePatchFromActive('HD2 Dress: cape damping test')
TM.ActivePatch.UpdatePath(os.path.join(OUT, m.BaseArchiveHexID + '.patch_0'))
for fid, e in av.TocDict[CLOTH].items():
    e.Load(False, False)
    d = bytearray(e.TocData)
    tf = H.tagfiles(bytes(d))[4]; tf.offsets = True
    n = 0
    for s in tf.root(4)['simClothDatas']:
        at = s['simulationInfo']['@offsets']['gravity']
        x, y, z, w = struct.unpack_from("<4f", d, at); dat = s["simulationInfo"]["@offsets"]["globalDampingPerSecond"]; dv = struct.unpack_from("<f", d, dat)[0]; struct.pack_into("<f", d, dat, {0.7: 0.111, 0.8: 0.222, 0.88: 0.333}[round(dv, 2)])
        struct.pack_into('<4f', d, at, x, y, -z, w); n += 1
    e.TocData = bytes(d)
    TM.AddEntryToPatchID(e, fid, ReloadUI=False)
    print(f'DAMP {fid:016x}: flipped gravity in {n} simulations ({len(d)} bytes)')
TM.PatchActiveArchive()
print('DAMP patch', os.listdir(OUT))
