import bpy, sys, os, struct, addon_utils
sys.path.insert(0, os.path.expanduser('~/hd2-dress/tools'))
import havok_tagfile as H
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager
p = TM.LoadArchive(os.path.expanduser('~/.cache/hd2-dress/havok_test/patch/9ba626afa44a3aa3.patch_0'), False, True)
for tid, ents in p.TocDict.items():
    for fid, e in ents.items():
        e.Load(False, False); d = bytes(e.TocData)
        tf = H.tagfiles(d)[4]; tf.offsets = True
        gs = [struct.unpack_from('<4f', d, s['simulationInfo']['@offsets']['gravity'])[2] for s in tf.root(4)['simClothDatas']]
        print(f'VER type {tid:016x} id {fid:016x} size {len(d)} gravity z per sim {gs}')
