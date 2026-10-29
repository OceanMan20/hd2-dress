import bpy, sys, os, addon_utils
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager; OUT = os.path.expanduser('~/.cache/hd2-dress/units/')
for arc, ids in (('18235e0c9ec0e636', (0x3c33cf10a26cbb3e,)), ('c40e3b3fa79052ec', (0xb0f1b354ba1d38d8,))):
    a = TM.LoadArchive(G + arc, False, False)
    for tid, d in a.TocDict.items():
        for fid, e in d.items():
            if fid in ids:
                e.Load(False, False)
                for part, data in (('main', e.TocData), ('gpu', e.GpuData), ('stream', e.StreamData)):
                    if data: open(f'{OUT}{arc}_{fid:016x}_{tid:016x}_{part}.bin', 'wb').write(data)
                print(f'DUMP {arc} {fid:016x} type {tid:016x} main {len(e.TocData or b"")} gpu {len(e.GpuData or b"")}')
