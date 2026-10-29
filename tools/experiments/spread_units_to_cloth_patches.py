import sys, os, glob
sys.argv += ['--', 'probe']
sys.path.insert(0, os.path.expanduser('~/hd2-dress/tools'))
import hd2dress_cloth as H
m = H.m; TM = H.TM
OUT = os.path.expanduser('~/hd2-dress/dist/test-jiggle-ball-torso')
SRC = os.path.expanduser('~/.cache/hd2-dress/ball/torso/08e906980c632592.patch_0')   # the exported armour patch (units + bones)
UNITS = (0x18902007139a6060, 0x2d9ce590011788ac)
src = m.StreamToc(); src.FromFile(SRC)
entries = [(ty, uid, e) for ty, d in src.TocDict.items() for uid, e in d.items() if uid in UNITS]
for e in [x[2] for x in entries]: e.Load(False, False) if False else None
print('SP source entries', [(hex(ty), hex(u)) for ty, u, _ in entries], flush=True)
for p in sorted(glob.glob(os.path.join(OUT, '*.patch_0'))):
    a = os.path.basename(p).split('.')[0]
    if a in ('08e906980c632592', '9ba626afa44a3aa3'): continue
    arc = TM.LoadArchive(p, True, True)                # active patch
    for ty, uid, e in entries:
        pe = TM.AddEntryToPatchID(e, uid, ReloadUI=False)
    TM.PatchActiveArchive()
    if TM.ActivePatch in TM.Patches: TM.Patches.remove(TM.ActivePatch)
    TM.ActivePatch = None
    chk = m.StreamToc(); chk.FromFile(p)
    print('SP', a, {hex(ty): len(d) for ty, d in chk.TocDict.items()}, flush=True)
