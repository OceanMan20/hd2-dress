import bpy, sys, os, struct, addon_utils
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager
H = os.path.dirname(m.__file__) + '/hashlists/'
tname = {int(l.split()[0], 16): l.split()[1] for l in open(H + 'typehash.txt') if l.strip()}
pats = [struct.pack('<5f', 0.0, 0.0, -9.8100004196167, 0.0, d) for d in (0.699999988079071, 0.800000011920929, 0.8799999952316284)]
for aid in ('18235e0c9ec0e636', 'c40e3b3fa79052ec'):
    a = TM.LoadArchive(G + aid, False, False)
    for tid, ents in a.TocDict.items():
        for fid, e in ents.items():
            try: e.Load(False, False)
            except Exception: continue
            for part, data in (('main', e.TocData), ('gpu', e.GpuData), ('stream', e.StreamData)):
                if not data: continue
                d = bytes(data); n = sum(d.count(p) for p in pats)
                if n: print(f'SIM {aid} {tname.get(tid, hex(tid))} {fid:016x} {part}: {n} simulation settings')
            e.TocData = e.GpuData = e.StreamData = None; e.IsLoaded = False
