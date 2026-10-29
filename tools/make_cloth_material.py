"""Make a solid-colour CLOTH-capable material for engine cloth meshes (writes a base-archive patch).
   blender -b -P tools/make_cloth_material.py -- OUTDIR R G B [NEW_MATERIAL_ID]
Copies the stock cape cloth material (8444775596724238472, cape shader 15780315333863701079, the only
kind of shader that draws a cloth-driven mesh), with its own copies of CapeLut and MaterialLut whose
colour columns are set to the given colour. Prints the new material id."""
import bpy, sys, os, struct, random, addon_utils
import numpy as np
args = sys.argv[sys.argv.index('--') + 1:]
OUT = os.path.abspath(args[0]); R, Gc, B = (float(x) for x in args[1:4])
NEW_ID = int(args[4]) if len(args) > 4 else random.getrandbits(63)
UNIFORM = os.environ.get('CLOTHMAT_UNIFORM') == '1'   # solid look: all LUT rows identical (no camo/metal squares)
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TX = sys.modules['HD2SDK-CommunityEdition.stingray.texture']; MS = sys.modules['HD2SDK-CommunityEdition.utils.memoryStream']
TM = m.Global_TocManager
TM.LoadArchive(G + m.BaseArchiveHexID, True, False)
TM.CreatePatchFromActive('HD2 Dress cloth material'); os.makedirs(OUT, exist_ok=True)
TM.ActivePatch.UpdatePath(os.path.join(OUT, m.BaseArchiveHexID + '.patch_0'))
TM.LoadArchive(G + '18235e0c9ec0e636', False, False)
SRC = 8444775596724238472
src = TM.GetEntry(SRC, m.MaterialID); src.Load(False, False)
mat = TM.AddEntryToPatchID(src, NEW_ID, ReloadUI=False); mat.Load(False, False)
md = mat.LoadedData
def recolour(tex_id, cols):
    e = TM.GetEntry(tex_id, m.TexID); e.Load(False, False); t = e.LoadedData
    dds = bytearray(t.ToDDS()); off = 128 + (20 if dds[84:88] == b'DX10' else 0)
    w, h = t.Width, t.Height
    for mip in range(t.NumMipMaps):
        mw, mh = max(1, w >> mip), max(1, h >> mip)
        a = np.frombuffer(bytes(dds[off:off + mw * mh * 8]), dtype=np.float16).reshape(mh, mw, 4).copy()
        for c in cols:
            if c < mw: a[:, c, 0], a[:, c, 1], a[:, c, 2] = R, Gc, B
        if UNIFORM: a[:] = a[0:1]       # every material slot (row) = row 0: the camo has nothing to alternate
        dds[off:off + mw * mh * 8] = a.tobytes(); off += mw * mh * 8
    nt = TX.StingrayTexture(); nt.FromDDS(bytes(dds))
    toc, gpu, stream = MS.MemoryStream(IOMode='write'), MS.MemoryStream(IOMode='write'), MS.MemoryStream(IOMode='write')
    nt.Serialize(toc, gpu, stream)
    new = m.TocEntry(); new.FileID = random.getrandbits(63); new.TypeID = m.TexID; new.IsCreated = True
    new.SetData(toc.Data, gpu.Data, stream.Data, False); TM.AddNewEntryToPatch(new, ReloadUI=False)
    return new.FileID
names = [t.name for t in md.TextureTypes]
CAPE = os.environ.get('CLOTHMAT_FROM_CAPE')        # 'ARCHIVE:TEXTUREID': use that cape's MaterialLut (its look)
if CAPE:
    arc, tid = CAPE.split(':'); TM.LoadArchive(G + arc, False, False)
    if UNIFORM:      # the cape's look, every row the same (no camo cells)
        md.TexIDs[names.index('MaterialLut')] = recolour(int(tid), ())
        i = names.index('CapeLut'); md.TexIDs[i] = recolour(md.TexIDs[i], ())
        print('MATERIAL MaterialLut <- cape texture', tid, 'flattened (uniform rows) as', md.TexIDs[names.index('MaterialLut')])
    else:
        e = TM.GetEntry(int(tid), m.TexID); e.Load(False, False)
        new = m.TocEntry(); new.FileID = random.getrandbits(63); new.TypeID = m.TexID; new.IsCreated = True
        new.SetData(e.TocData, e.GpuData, e.StreamData, False); TM.AddNewEntryToPatch(new, ReloadUI=False)
        md.TexIDs[names.index('MaterialLut')] = new.FileID
        print('MATERIAL MaterialLut <- cape texture', tid, 'copied as', new.FileID)
else:
    for name, cols in (('CapeLut', (0, 3)), ('MaterialLut', (0, 2, 5))):
        i = names.index(name); md.TexIDs[i] = recolour(md.TexIDs[i], cols)
        print('MATERIAL', name, '->', md.TexIDs[i])
f = MS.MemoryStream(IOMode='write'); md.Serialize(f); mat.TocData = f.Data
TM.PatchActiveArchive()
print('MATERIAL new cloth material id', NEW_ID)
