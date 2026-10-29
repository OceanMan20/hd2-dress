"""Export what the engine-cloth generator needs from units in a patch (read-only).
   blender -b -P tools/export_unit_mesh.py -- PATCHFILE OUT.json UNITID[,UNITID] [MESHID]
Per unit: node name hashes, world matrices, parents; the LOD0 mesh (or MESHID) in GPU vertex order:
positions, normals, tangents, bitangents, uvs, bone indices (palette), weights, triangles, material
ranges, and the bone palette -> node index mapping."""
import bpy, sys, os, json, addon_utils
args = sys.argv[sys.argv.index('--') + 1:]
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
TM = m.Global_TocManager
arc = TM.LoadArchive(os.path.abspath(args[0]), True, False)
out = {}
def plain(v):
    if hasattr(v, 'v') and not isinstance(v, (str, bytes)): return plain(v.v)
    if isinstance(v, dict): return {str(k): plain(x) for k, x in v.items()}
    if hasattr(v, '__len__') and not isinstance(v, (str, bytes)): return [plain(x) for x in v]
    if isinstance(v, (int, float, bool)) or v is None: return v
    if hasattr(v, '__dict__'): return {k: plain(x) for k, x in vars(v).items()}
    return str(v)
for uid in [int(x, 16) for x in args[2].split(',')]:
    e = arc.TocDict[m.UnitID][uid]; e.Load(False, False); md = e.LoadedData; ti = md.TransformInfo
    want = int(args[3]) if len(args) > 3 else None
    raw = next(r for r in md.RawMeshes if (r.MeshID == want if want else r.LodIndex == 0 and r.MeshInfoIndex == max(x.MeshInfoIndex for x in md.RawMeshes if x.LodIndex == 0)))
    bi = raw.DEV_BoneInfo
    mats = [{k: plain(getattr(mt, k)) for k in dir(mt) if not k.startswith('_') and not callable(getattr(mt, k))} for mt in raw.Materials]
    out[hex(uid)] = dict(
        nodes=dict(hashes=list(ti.NameHashes), world=[list(x.v) for x in ti.TransformMatrices],
                   parents=[t.ParentBone for t in ti.TransformEntries]),
        mesh=dict(id=raw.MeshID, positions=plain(raw.VertexPositions), normals=plain(raw.VertexNormals),
                  tangents=plain(raw.VertexTangents), bitangents=plain(raw.VertexBiTangents), uvs=plain(raw.VertexUVs),
                  bone_indices=plain(raw.VertexBoneIndices), weights=plain(raw.VertexWeights), triangles=plain(raw.Indices),
                  materials=mats),
        bone_info={k: plain(getattr(bi, k)) for k in dir(bi) if not k.startswith('_') and not callable(getattr(bi, k))})
    print('EXPORT', hex(uid), len(raw.VertexPositions), 'verts', len(raw.Indices), 'tris', 'materials', mats)
json.dump(out, open(args[1], 'w'))
