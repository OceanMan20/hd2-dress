"""Find which archives hold a resource id (any type), reading only TOCs. blender -b -P find_id.py -- ID [ID...]"""
import bpy, sys, os, struct, addon_utils, time
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/')
SL = sys.modules['HD2SDK-CommunityEdition.utils.slim']; SL.slim_init(G)
if not SL.package_contents: SL.init_bundle_mapping()
want = {int(x, 16) for x in sys.argv[sys.argv.index('--') + 1:]}
pats = {struct.pack('<Q', w): w for w in want}
def toc(name):
    path = os.path.join(G, name)
    if os.path.exists(path):
        b = open(path, 'rb').read(4 << 20)
        return None if struct.unpack_from('<I', b)[0] == 1380012868 else b
    pkg = SL.package_contents.get(name)
    if not pkg or not pkg.entries: return None
    e = min(pkg.entries, key=lambda x: x.original_archive_offset)
    return SL.get_resource_from_bundle(os.path.join(G, f'bundles.{e.bundle_index:02d}.nxa'), e.start_offset)
names = sorted(set([k for k in SL.package_contents if len(k) == 16 and '.' not in k] + [f for f in os.listdir(G) if len(f) == 16 and '.' not in f]))
t0 = time.time()
for n in names:
    try: b = toc(n)
    except Exception: continue
    if not b: continue
    magic, ntypes, nfiles = struct.unpack_from('<III', b, 0)
    if magic != 0xF0000011: continue
    base = 72 + 32 * ntypes
    for p, w in pats.items():
        i = b.find(p, base, base + 80 * nfiles)
        while i >= 0:
            if (i - base) % 80 == 0:
                print(f'FOUND {w:016x} in {n} type {struct.unpack_from("<Q", b, i + 8)[0]:016x}')
            i = b.find(p, i + 1, base + 80 * nfiles)
print(f'FIND done {len(names)} archives {time.time() - t0:.0f}s')
