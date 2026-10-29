"""HD2 Dress engine cloth: one command from an armour mod + a settings file to installable cloth patches.

    blender -b -P tools/hd2dress_cloth.py -- build SETTINGS.toml [--install]
    blender -b -P tools/hd2dress_cloth.py -- archives UNITID [UNITID ...]

build:
  1. loads the armour patch named in the settings (the author's own HD2SDK patch) and reads each [[unit]]'s mesh
  2. picks the cloth vertices: a vertex group in the author's .blend (cloth.vertex_group) or a material slot
  3. builds the Havok cloth with the game's own stock cape cloth as template (read from the game install)
  4. finds every game archive holding each unit (the cloth must sit in a patch of the unit's OWN archive)
  5. writes one ARCHIVE.patch_0 per archive into dist/other/<cloth_name>/ (+ _debug/: manifest.txt, the settings, raw cloth)
  --install also copies them into the game's data folder, refusing to overwrite a patch_0 that is not ours.
  6. with a [look] section: also builds the cloth's MATERIAL (base archive patch, its own file):
       shader = "character" (default): a normal character shader (template: the Illuminate cultist loin cloth
       material) with the author's colour map (+ optional normal map). Switches on the cloth options this needs
       (texcoord15, render_root_skin, oct_normals). The unit's mesh must have 'root' in its bone palette (weight one
       cloth vertex 0.001 to a 'root' vertex group).
       shader = "cape": keep the cape shader (zone colours / decals, see docs/CLOTH_MATERIAL_RESEARCH.md); no material
       is built yet for this route.
Shipped mods have no Lua: players only install the armour patch and these cloth patches.
Settings: see examples/engine_cloth_testrig.toml (every key, with the tested defaults)."""
import bpy, sys, os, json, struct, time, shutil, addon_utils
try: import tomllib
except ModuleNotFoundError:                 # Python 3.10 (Blender 4.0/4.1): the same parser, bundled as tomli
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '_vendor')); import tomli as tomllib
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import gen_engine_cloth as gen

args = sys.argv[sys.argv.index('--') + 1:]
from hd2_paths import game_data
GAME = game_data()
CACHE = os.path.expanduser('~/.cache/hd2-dress/build'); os.makedirs(CACHE, exist_ok=True)
addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
m.Global_gamepath = GAME
SL = sys.modules['HD2SDK-CommunityEdition.utils.slim']; SL.slim_init(GAME)
TM = m.Global_TocManager


def plain(v):
    if hasattr(v, 'v') and not isinstance(v, (str, bytes)): return plain(v.v)
    if isinstance(v, dict): return {str(k): plain(x) for k, x in v.items()}
    if hasattr(v, '__len__') and not isinstance(v, (str, bytes)): return [plain(x) for x in v]
    if isinstance(v, (int, float, bool)) or v is None: return v
    if hasattr(v, '__dict__'): return {k: plain(x) for k, x in vars(v).items()}
    return str(v)


# ------------------------------------------------------------------ 1. unit export (same data as export_unit_mesh.py)
def export_unit(arc, uid, mesh_id=None, match=None):
    # HD2SDK's "Import materials" (on by default) would also import the unit's materials and convert their textures:
    # not needed here, slow, and on Windows the texture conversion can fail and abort the build (seen 2026-10-20)
    st = bpy.context.scene.Hd2ToolPanelSettings; keep = st.ImportMaterials
    st.ImportMaterials = False
    try:
        e = arc.TocDict[m.UnitID][uid]; e.Load(False, False)
    finally:
        st.ImportMaterials = keep
    md = e.LoadedData; ti = md.TransformInfo
    lod0 = [r for r in md.RawMeshes if r.LodIndex == 0] or list(md.RawMeshes)
    if mesh_id:
        raw = next(r for r in md.RawMeshes if r.MeshID == mesh_id)
    elif match:                             # the mesh that holds the cloth (a unit can have several LOD0 meshes)
        keys = {tuple(round(float(c), 4) for c in p[:3]) for p in match}
        def hits(r): return sum(1 for p in r.VertexPositions if tuple(round(float(c), 4) for c in list(p)[:3]) in keys)
        scored = sorted(((hits(r), r.MeshInfoIndex, r) for r in lod0), key=lambda x: (x[0], x[1]))
        raw = scored[-1][2]
        print(f'MESH unit {uid:016x}: LOD0 meshes ' + ', '.join(f'{r.MeshID:#x} ({h} cloth vertices)' for h, _, r in scored)
              + f' -> using {raw.MeshID:#x}')
    else:
        raw = max(lod0, key=lambda r: r.MeshInfoIndex)
    bi = raw.DEV_BoneInfo
    # the mesh's vertices are relative to its own node (the SDK's MeshInfo.TransformIndex); usually identity, but a
    # custom unit can move it (2026-10-22 user skirt: node at z 0.733), and the cloth must sit where the mesh is drawn
    tix = md.MeshInfoArray[raw.MeshInfoIndex].TransformIndex
    mats = [{k: plain(getattr(mt, k)) for k in dir(mt) if not k.startswith('_') and not callable(getattr(mt, k))} for mt in raw.Materials]
    return dict(nodes=dict(hashes=list(ti.NameHashes), world=[list(x.v) for x in ti.TransformMatrices],
                           parents=[t.ParentBone for t in ti.TransformEntries]),
                mesh=dict(id=raw.MeshID, positions=plain(raw.VertexPositions), normals=plain(raw.VertexNormals),
                          tangents=plain(raw.VertexTangents), bitangents=plain(raw.VertexBiTangents), uvs=plain(raw.VertexUVs),
                          bone_indices=plain(raw.VertexBoneIndices), weights=plain(raw.VertexWeights),
                          triangles=plain(raw.Indices), materials=mats,
                          transform=list(ti.TransformMatrices[tix].v), transform_node=tix),
                bone_info={k: plain(getattr(bi, k)) for k in dir(bi) if not k.startswith('_') and not callable(getattr(bi, k))})


# ------------------------------------------------------------------ 2. cloth vertices from a vertex group in the .blend
_BLEND_CACHE = {}


def group_positions_from_blend(path, groups, objects=None, unit_id=None):
    """{group: positions (object space) of every vertex in it (weight > 0.5)}, over all mesh objects (or the named
    ones). Missing groups give empty lists."""
    key = (path, tuple(objects) if objects else None)
    if key not in _BLEND_CACHE:
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.objects = [n for n in src.objects if not objects or n in objects]
        _BLEND_CACHE[key] = [o for o in dst.objects if o is not None and o.type == 'MESH']
    out = {g: [] for g in groups}
    objs = _BLEND_CACHE[key]
    if unit_id is not None and not objects:    # HD2SDK marks each imported object with its unit id: use only that unit's
        own = [o for o in objs if str(o.get('Z_ObjectID', '')) == str(unit_id)]
        if own: objs = own
    for o in objs:
        for group in groups:
            if group not in o.vertex_groups: continue
            gi = o.vertex_groups[group].index; n0 = len(out[group])
            for v in o.data.vertices:
                if any(g.group == gi and g.weight > 0.5 for g in v.groups): out[group].append(list(v.co))
            print(f'CLOTH {o.name}: {len(out[group]) - n0} vertices in group "{group}"')
    return out


def cloth_positions_from_blend(path, group, objects=None, unit_id=None):
    pts = group_positions_from_blend(path, [group], objects, unit_id)[group]
    if not pts: raise SystemExit(f'no vertices in vertex group "{group}" in {path}')
    return pts


def mesh_name_for(data):
    """The mesh node's name from HD2SDK's name list (bonehash.txt), found by the mesh id (= murmur32 of the name)."""
    want = data['mesh']['id']
    f = os.path.join(os.path.dirname(m.__file__), 'hashlists', 'bonehash.txt')
    try:
        for line in open(f, encoding='utf-8', errors='ignore'):
            n = line.strip().split()[-1] if line.strip() else ''
            if n and gen.h32(n) == want: return n
    except OSError: pass
    raise SystemExit(f'mesh name unknown for mesh id {want:#x}: set mesh_name = "..." in this [[unit]]')


# ------------------------------------------------------------------ 4. which archives hold a unit (TOCs only)
def find_archives(ids):
    """{id: [archive, ...]} for every game archive whose TOC lists the id. Cached per game build."""
    exe = os.path.join(GAME, '..', 'bin', 'helldivers2.exe')            # changes with every game update
    stamp = str(int(os.path.getmtime(exe if os.path.exists(exe) else GAME)))
    cf = os.path.join(CACHE, 'archives.json')
    cache = json.load(open(cf)) if os.path.exists(cf) else {}
    if cache.get('_stamp') != stamp: cache = {'_stamp': stamp}
    todo = [i for i in ids if f'{i:016x}' not in cache]
    if todo:
        if not SL.package_contents: SL.init_bundle_mapping()
        pats = {struct.pack('<Q', w): w for w in todo}; found = {w: [] for w in todo}
        def toc(name):
            path = os.path.join(GAME, name)
            if os.path.exists(path):
                b = open(path, 'rb').read(4 << 20)
                return None if struct.unpack_from('<I', b)[0] == 1380012868 else b
            pkg = SL.package_contents.get(name)
            if not pkg or not pkg.entries: return None
            e = min(pkg.entries, key=lambda x: x.original_archive_offset)
            return SL.get_resource_from_bundle(os.path.join(GAME, f'bundles.{e.bundle_index:02d}.nxa'), e.start_offset)
        names = sorted(set([k for k in SL.package_contents if len(k) == 16 and '.' not in k] +
                           [f for f in os.listdir(GAME) if len(f) == 16 and '.' not in f]))
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
                    if (i - base) % 80 == 0 and struct.unpack_from('<Q', b, i + 8)[0] == m.UnitID:
                        found[w].append(n); break
                    i = b.find(p, i + 1, base + 80 * nfiles)
        print(f'ARCHIVES scanned {len(names)} archives in {time.time() - t0:.0f}s')
        for w, lst in found.items(): cache[f'{w:016x}'] = sorted(set(lst))
        json.dump(cache, open(cf, 'w'), indent=1)
    return {i: cache[f'{i:016x}'] for i in ids}


# ------------------------------------------------------------------ light archive access
# HD2SDK's TocManager.LoadArchive also loads every animation state machine of an archive (for its animation index):
# character archives made the build peak at 9-12 GB and an 8 GB Windows machine ran out of memory (2026-10-20).
# The build needs one entry from two template archives and only the HEADER of each archive it patches.
def read_archive(a):
    """The archive as a StreamToc (entries and their data), without TocManager's state machine loading."""
    toc = m.StreamToc(); toc.FromFile(GAME + a)
    return toc


def archive_header(a):
    """(magic, unknown, unk4Data) of an archive's TOC: what a patch of that archive must carry. Reads only the TOC."""
    path = GAME + a
    if os.path.exists(path):
        b = open(path, 'rb').read(72)
        if struct.unpack_from('<I', b)[0] == 1380012868: b = bytes(SL.load_package(path)[0][:72])   # compressed (DSAR)
    else:
        if not SL.package_contents: SL.init_bundle_mapping()
        b = bytes(SL.reconstruct_package_from_bundles(path)[:72])
    magic, _nt, _nf, unknown = struct.unpack_from('<IIII', b)
    if magic != 0xF0000011: raise SystemExit(f'archive {a}: unexpected TOC header')
    return magic, unknown, bytearray(b[16:72])


def new_patch(a, path, name):
    """An empty patch of archive a (its header, no entries) as HD2SDK's active patch."""
    patch = m.StreamToc()
    patch.magic, patch.unknown, patch.unk4Data = archive_header(a)
    patch.UpdatePath(path); patch.LocalName = name
    TM.Patches.append(patch); TM.SetActivePatch(patch)
    return patch


# ------------------------------------------------------------------ 3. template from the game
def template_bytes():
    e = read_archive(gen.TEMPLATE_ARCHIVE).GetEntry(gen.TEMPLATE_ID, gen.CLOTH_TYPE); e.Load(False, False)
    return bytes(e.TocData), e


# ------------------------------------------------------------------ 6. the cloth material (character shader route)
CHAR_TEMPLATE = (0x8ef061a6921be948, '9230ae99f0ee6c03')     # Illuminate cultist loin cloth material (Overseers archive)
BLANK_TEX = 17544421564454316850                              # the game's blank 1x1 placeholder texture
CHAR_BLANK = ('WoundNormal', 'WoundData', 'WoundDerivative', 'DetailNormalLeather', 'DetailNormalPorcelain',
              'IlluminateData', 'BloodTiler', 'WeatheringSpecial')


def dds_rgba(img):
    """uint8 HxWx4 (top row first) -> uncompressed DX10 R8G8B8A8 DDS with a full mip chain."""
    h, w = img.shape[:2]; mips = int(np.log2(max(w, h))) + 1
    hdr = bytearray(148); hdr[0:4] = b'DDS '
    struct.pack_into('<7I', hdr, 4, 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x20000, h, w, w * 4, 0, mips)
    struct.pack_into('<2I', hdr, 76, 32, 0x4); hdr[84:88] = b'DX10'
    struct.pack_into('<I', hdr, 108, 0x1000 | 0x400000 | 0x8); struct.pack_into('<5I', hdr, 128, 28, 3, 0, 1, 0)
    out = bytearray(hdr); m_ = img.astype(np.float32)
    for _ in range(mips):
        out += np.clip(np.round(m_), 0, 255).astype(np.uint8).tobytes()
        if m_.shape[0] > 1 and m_.shape[1] > 1: m_ = m_.reshape(m_.shape[0] // 2, 2, m_.shape[1] // 2, 2, 4).mean((1, 3))
        elif m_.shape[0] > 1: m_ = m_.reshape(m_.shape[0] // 2, 2, 1, 4).mean(1)
        elif m_.shape[1] > 1: m_ = m_.reshape(1, m_.shape[1] // 2, 2, 4).mean(2)
    return bytes(out)


def load_image(path, max_size=2048, size=None):
    """Any image Blender reads -> uint8 HxWx4, top row first, sides rounded down to powers of two (<= max_size)."""
    im = bpy.data.images.load(path, check_existing=False)
    w, h = im.size
    pw = lambda x: 1 << max(2, min(int(np.log2(max(x, 1))), int(np.log2(max_size))))
    if (w, h) != (pw(w), pw(h)): im.scale(pw(w), pw(h)); w, h = im.size
    if size and (w, h) != tuple(size): im.scale(*size); w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]          # Blender stores bottom row first
    if im.colorspace_settings.name.lower().startswith('srgb') or True:
        pass                                                                   # pixels are already display values
    bpy.data.images.remove(im)
    return np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)


def compress(dds, fmt):
    """Block-compress with HD2SDK's bundled texconv (BC1: colour, 8x smaller; BC3: 4 channels, 4x smaller).
    Falls back to the uncompressed DDS if texconv is missing or fails."""
    import subprocess, tempfile
    tc = getattr(m, 'Global_texconvpath', None)
    if not fmt or not tc or not os.path.exists(tc): return dds
    # call the real binary: HD2SDK's Linux wrapper adds -srgbo (right for PNG input, but it brightens our linear DDS:
    # measured mean 131 -> 173). On Windows texconv.exe is called directly anyway.
    env = dict(os.environ); cmd = [tc]
    d = os.path.dirname(tc)
    if os.path.exists(os.path.join(d, 'texconv.bin')):
        cmd = [os.path.join(d, 'texconv.bin')]; env['LD_LIBRARY_PATH'] = f"{d}/lib:{d}:" + env.get('LD_LIBRARY_PATH', '')
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, 'in.dds'); open(src, 'wb').write(dds); os.makedirs(os.path.join(td, 'out'))
        r = subprocess.run(cmd + ['-y', '-o', os.path.join(td, 'out'), '-ft', 'dds', '-dx10', '-f', fmt, '-m', '0', '--', src],
                           capture_output=True, env=env)
        out = os.path.join(td, 'out', 'in.dds')
        if r.returncode or not os.path.exists(out):
            code = r.returncode & 0xffffffff
            why = (' (DLL not found: install the Microsoft Visual C++ Redistributable x64, texconv needs it)'
                   if code == 0xC0000135 else f' (exit {code:#x})')
            print(f'WARNING texconv {fmt} failed{why}, texture left uncompressed (works, but larger)'); return dds
        return open(out, 'rb').read()


def add_texture(img, fmt=None):
    TX = sys.modules['HD2SDK-CommunityEdition.stingray.texture']; MS = sys.modules['HD2SDK-CommunityEdition.utils.memoryStream']
    import random
    nt = TX.StingrayTexture(); nt.FromDDS(compress(dds_rgba(img), fmt))
    toc, gpu, stm = MS.MemoryStream(IOMode='write'), MS.MemoryStream(IOMode='write'), MS.MemoryStream(IOMode='write')
    nt.Serialize(toc, gpu, stm)
    e = m.TocEntry(); e.FileID = random.getrandbits(63); e.TypeID = m.TexID; e.IsCreated = True
    e.SetData(toc.Data, gpu.Data, stm.Data, False); TM.AddNewEntryToPatch(e, ReloadUI=False)
    return e.FileID


CHAR_PARENT = 17265463703140804126      # the character (armour) shader family of CHAR_TEMPLATE; HD2SDK-made armour materials too


def _slot_names(md):
    if hasattr(md, 'TextureTypes'): return [t.name for t in md.TextureTypes]
    matmod = sys.modules['HD2SDK-CommunityEdition.stingray.material']
    return [matmod.Global_ShaderVariables.get(h, str(h)) for h in md.TexUnks]


def author_material(mat_id):
    """The author's material entry (armour patch first, else the game), or None."""
    return TM.GetEntry(mat_id, m.MaterialID, IgnorePatch=False, SearchAll=True)


def keep_author_material(mat_id):
    """look.keep_material: the author's OWN material, kept: their textures and values on the full character template
    (HD2SDK-made materials carry only some of the shader's values: 42 of 77, without the IgnoreSkinning switch the cloth
    needs, 2026-10-24), plus IgnoreSkinning on. A material of another shader family is copied as it is."""
    MS = sys.modules['HD2SDK-CommunityEdition.utils.memoryStream']
    src = author_material(mat_id)
    if src is None:
        raise SystemExit(f'material {mat_id} (the cloth faces\' material) is not in your armour patch: export the patch with '
                         'HD2SDK including that material, or use the Colour map look')
    src.Load(False, False); A = src.LoadedData
    if getattr(A, 'ParentMaterialID', None) == CHAR_PARENT:
        tpl = read_archive(CHAR_TEMPLATE[1]).GetEntry(CHAR_TEMPLATE[0], m.MaterialID); tpl.Load(False, False)
        mat = TM.AddEntryToPatchID(tpl, mat_id, ReloadUI=False); mat.Load(False, False); md = mat.LoadedData
        an, tn = _slot_names(A), _slot_names(md)
        for k, nme in enumerate(tn):
            md.TexIDs[k] = A.TexIDs[an.index(nme)] if nme in an else BLANK_TEX
        av = {sv.name: list(sv.values) for sv in A.ShaderVariables if sv.name}
        for sv in md.ShaderVariables:
            if sv.name in av and len(av[sv.name]) == len(sv.values): sv.values = av[sv.name]
        kept = sum(1 for n in tn if n in an)
    else:
        mat = TM.AddEntryToPatchID(src, mat_id, ReloadUI=False); mat.Load(False, False); md = mat.LoadedData; kept = None
    n = 0
    for sv in md.ShaderVariables:
        if sv.name and sv.name.startswith('IgnoreSkinning'): sv.values = [1.0]; n += 1
    if not n: print(f'WARNING: material {mat_id} has no IgnoreSkinning switch (not a character shader?): the cloth may '
                    'move twice in game. Use the Colour map look if it does', flush=True)
    f = MS.MemoryStream(IOMode='write'); md.Serialize(f); mat.TocData = f.Data
    print(f'MATERIAL {mat_id} (your own material, kept' + (f': {kept} textures and your values on the full shader' if kept is not None else '')
          + '; cloth switch on)')


def add_character_material(look, mat_id, rel):
    """Into the ACTIVE patch: a copy of the character template material under mat_id, with the author's maps."""
    if look.get('keep_material'): return keep_author_material(mat_id)
    MS = sys.modules['HD2SDK-CommunityEdition.utils.memoryStream']
    src = read_archive(CHAR_TEMPLATE[1]).GetEntry(CHAR_TEMPLATE[0], m.MaterialID); src.Load(False, False)
    mat = TM.AddEntryToPatchID(src, mat_id, ReloadUI=False); mat.Load(False, False); md = mat.LoadedData
    if hasattr(md, 'TextureTypes'):
        names = [t.name for t in md.TextureTypes]
    else:
        matmod = sys.modules['HD2SDK-CommunityEdition.stingray.material']
        names = [matmod.Global_ShaderVariables.get(h, str(h)) for h in md.TexUnks]
    for sl in CHAR_BLANK:
        if sl in names: md.TexIDs[names.index(sl)] = BLANK_TEX
    if 'color' not in look: raise SystemExit('[look] needs color = "your_colour_map.png"')
    col = load_image(rel(look['color'])); col[..., 3] = 255
    md.TexIDs[names.index('AlbedoEmissive')] = add_texture(col, 'BC1_UNORM')
    # 'Nar' = normal xy, AO, roughness (as HD2 armour NormalXyAoRoughMap). ALWAYS ours: the template's own Nar is laid out
    # for the loin cloth's UVs, and without a normal map it stayed: someone else's shine on the cloth and the Roughness
    # value ignored (user report 2026-10-24). No normal map = flat normal.
    if look.get('normal'):
        nrm = load_image(rel(look['normal']))
        if look.get('normal_flip_green'): nrm[..., 1] = 255 - nrm[..., 1]
    else:
        size = None
        for k in ('roughness_map', 'ao'):
            if look.get(k): size = load_image(rel(look[k])).shape[:2]; break
        h, w = size or (16, 16)
        nrm = np.full((h, w, 4), 128, dtype=np.uint8)
    nar = np.empty_like(nrm); nar[..., 0] = nrm[..., 0]; nar[..., 1] = nrm[..., 1]
    nar[..., 2] = load_image(rel(look['ao']), size=(nrm.shape[1], nrm.shape[0]))[..., 0] if look.get('ao') else 255
    nar[..., 3] = (load_image(rel(look['roughness_map']), size=(nrm.shape[1], nrm.shape[0]))[..., 0]
                     if look.get('roughness_map') else int(round(255 * float(look.get('roughness', 0.7)))))
    md.TexIDs[names.index('Nar')] = add_texture(nar, 'BC3_UNORM')
    if look.get('weave'):                       # fine detail normal, tiled independently of the colour map's resolution
        w_ = load_image(rel(look['weave']), max_size=1024)
        asp = float(look.get('weave_aspect', 1.0))     # UV units around vs down differ (a skirt: ~2 m around per U, 1 m per V):
        if asp != 1.0:                                 # repeat the tile across so one tiling value gives round threads
            reps = max(1, int(round(asp)))
            w_ = np.concatenate([w_] * reps, axis=1)
            if w_.shape[1] > 2048: w_ = w_[:, ::w_.shape[1] // 2048]
        if look.get('normal_flip_green'): w_[..., 1] = 255 - w_[..., 1]
        # HD2 packs detail normals like its other surface maps: R, G = normal xy, B = AO (255 = none), A = 105 in the
        # game's own default. A plain normal map's B (z) dips on every slope and reads as dark AO (dark bands/splotches).
        w_[..., 2] = 255; w_[..., 3] = int(look.get('weave_alpha', 105))
        wid = add_texture(w_, 'BC3_UNORM')
        for sl in ('DetailNormalLeather', 'DetailNormalPorcelain'):     # which one the shader uses is unknown: both
            if sl in names: md.TexIDs[names.index(sl)] = wid
    wt, ws = float(look.get('weave_tiling', 40.0)), float(look.get('weave_strength', 1.0))
    for sv in md.ShaderVariables:
        if sv.name and sv.name.startswith('IgnoreSkinning'): sv.values = [1.0]
        if look.get('weave') and sv.name in ('DetailNormTilerLeather', 'DetailNormTilerPorcelain'): sv.values = [wt]
        if look.get('weave') and sv.name in ('DetailNormIntensityLeather', 'DetailNormIntensityPorcelain'): sv.values = [ws]
    f = MS.MemoryStream(IOMode='write'); md.Serialize(f); mat.TocData = f.Data
    print(f'MATERIAL {mat_id} (character shader) colour {look["color"]}' + (f', normal {look["normal"]}' if look.get('normal') else ''))


def cloth_material_id(data, g):
    """The material id of the mesh range holding the most cloth triangles."""
    cv = set(g.cloth_verts); best = (0, None)
    T = np.array(data['mesh']['triangles']).reshape(-1, 3)
    for mt in data['mesh']['materials']:
        a, n = mt['StartIndex'] // 3, mt['NumIndices'] // 3
        k = sum(1 for t in T[a:a + n] if t[0] in cv and t[1] in cv and t[2] in cv)
        if k > best[0]: best = (k, mt.get('MatID'))
    try: return int(best[1])
    except (TypeError, ValueError):
        rows = []
        for mt in data['mesh']['materials']:
            a, n = mt['StartIndex'] // 3, mt['NumIndices'] // 3
            k = sum(1 for t in T[a:a + n] if t[0] in cv and t[1] in cv and t[2] in cv)
            rows.append(f"{mt.get('MatID')} (triangles {a}..{a + n}, cloth {k})")
        if not cv:
            raise SystemExit('the cloth in your .blend matches NO vertex of the mesh in the armour patch: the patch is older '
                             'than your mesh, or a different export. Export the armour patch with HD2SDK again from this .blend '
                             '(after Fix all) and choose that file as the Armour patch')
        why = (f'no material section of the mesh holds the cloth triangles ({len(T)} triangles, {len(cv)} cloth vertices; '
               f'sections: {"; ".join(rows) or "none"})' if best[1] is None else f'the cloth faces use material "{best[1]}"')
        raise SystemExit(f'{why}. Give the cloth faces a numbered HD2SDK material and export the patch again, or type the '
                         f'material id in 4 Look > Cloth material ID')


def build(path):
    st = tomllib.load(open(path, 'rb'))
    for k in ('cloth_name', 'armour_patch', 'unit'):
        if k not in st: raise SystemExit(f'settings: "{k}" is required')
    sdir = os.path.dirname(os.path.abspath(path))
    rel = lambda p: os.path.expanduser(p) if os.path.isabs(os.path.expanduser(p)) else os.path.join(sdir, p)
    gen.TEMPLATE_BYTES, carrier = template_bytes()
    ap_path = os.path.abspath(os.path.expanduser(rel(st['armour_patch'])))
    if not os.path.exists(ap_path): raise SystemExit(f'armour patch not found: {ap_path}')
    arc = TM.LoadArchive(ap_path, True, False)
    cloth = st.get('cloth', {})
    positions = None
    pieces = st.get('piece', [])
    if pieces:
        if 'blend' not in st: raise SystemExit('[[piece]] needs blend = "your.blend"')
    elif 'vertex_group' in cloth:
        if 'blend' not in st: raise SystemExit('cloth.vertex_group needs blend = "your.blend"')
    elif 'positions_file' in cloth:
        positions = json.load(open(rel(cloth['positions_file'])))['positions']
    elif 'material_slot' not in cloth:
        raise SystemExit('[cloth] needs vertex_group (with blend = "...") , material_slot, or positions_file')
    look = st.get('look')
    shader = (look or {}).get('shader', 'character') if look else None
    if shader not in (None, 'character', 'cape'): raise SystemExit('look.shader must be "character" or "cape"')
    mat_ids = set()
    blobs = {}
    for ue in st['unit']:
        uid = int(ue['id'], 16)
        objs0 = [ue['object']] if 'object' in ue else None
        early = None
        if pieces:
            g0 = group_positions_from_blend(rel(st['blend']), [pc['group'] for pc in pieces], objs0, uid)
            early = [p for v in g0.values() for p in v]
        elif 'vertex_group' in cloth:
            early = group_positions_from_blend(rel(st['blend']), [cloth['vertex_group']], objs0, uid)[cloth['vertex_group']]
        elif positions is not None:
            early = positions
        data = export_unit(arc, uid, ue.get('mesh_id'), match=early)
        if not ue.get('mesh_name'): ue['mesh_name'] = mesh_name_for(data)
        spec = gen.spec_from_settings(st, ue, data)
        objs = [ue['object']] if 'object' in ue else None
        if pieces:                         # named pieces: cloth = every piece's vertex group, each with its settings
            gp = group_positions_from_blend(rel(st['blend']), [pc['group'] for pc in pieces] +
                                            ([cloth['pin_group']] if cloth.get('pin_group') else []), objs, uid)
            for pc in spec['pieces']: pc['positions'] = gp[pc['group']]
            spec['cloth_positions'] = [p for pc in spec['pieces'] for p in pc['positions']]
            if not spec['cloth_positions']: raise SystemExit(f"unit {ue['id']}: no vertices in any piece's vertex group")
            if cloth.get('pin_group'): spec['pin_positions'] = gp[cloth['pin_group']]
        elif 'vertex_group' in cloth:       # the unit's own object in the .blend (or every object with the group)
            spec['cloth_positions'] = cloth_positions_from_blend(rel(st['blend']), cloth['vertex_group'], objs, uid)
            if cloth.get('pin_group'):
                spec['pin_positions'] = group_positions_from_blend(rel(st['blend']), [cloth['pin_group']], objs, uid)[cloth['pin_group']]
        elif positions is not None: spec['cloth_positions'] = positions
        if shader == 'character': spec.update(texcoord15=True, render_root_skin=True, oct_normals=True, uv_tangents=bool(look.get('normal') or look.get('keep_material')))   # own material: it has its normal map
        g = gen.Garment(data, spec)
        if len(g.pp) == 0:
            n_blend = len(spec.get('cloth_positions') or [])
            raise SystemExit(f"the cloth in your .blend ({n_blend} vertices) matches NO vertex of the mesh in the armour patch "
                             f"(unit {ue['id']}, {len(g.tris)} triangles). The patch is older than your mesh, or a different "
                             "export: export the armour patch with HD2SDK again from this .blend (after Fix all) and choose that "
                             "file as the Armour patch")
        if look: mat_ids.add(int(look['material_id']) if 'material_id' in look else cloth_material_id(data, g))
        else:                                    # 'My own cloth material' = a CAPE-shader material; an armour material crashes
            try: cm = cloth_material_id(data, g)
            except SystemExit: cm = None
            e_ = author_material(cm) if cm else None
            if e_ is not None:
                e_.Load(False, False)
                if getattr(e_.LoadedData, 'ParentMaterialID', None) == CHAR_PARENT:
                    raise SystemExit(f'the cloth\'s material {cm} is a normal armour material, but 4 Look is set to "My own '
                                     'cloth material" (a cape-shader material). Pick "Keep my material" (keeps your material '
                                     'and textures) or "Colour map" in 4 Look and build again (a cape-shader build with an armour material crashes the game)')
        # two coincident layers (a front and a reversed back copy) z-fight under the two-sided cape shader: blocky
        # light/dark squares that turn to static when the cloth moves. One layer is enough (capes are one layer).
        by_p = {}
        for v, p in g.vert_particle.items(): by_p.setdefault(p, []).append(v)
        doubled = sum(1 for vs in by_p.values() if any(np.dot(g.N[a], g.N[b]) < -0.5 for a in vs for b in vs))
        if doubled > len(by_p) * 0.2 and not cloth.get('allow_double_layer'):
            raise SystemExit(f"UNIT {ue['id']}: {doubled} of {len(by_p)} cloth points have a second, reversed layer on top of "
                             "them. The cloth shader already draws both sides; two layers z-fight (flickering squares). "
                             "Delete the back faces, or set cloth.allow_double_layer = true.")
        print(f"UNIT {ue['id']} ({ue['mesh_name']}): particles {len(g.pp)}, pinned {len(g.fixed)}, parts {g.n_islands}, "
              f"bones {len(g.bones)}" + (f", pieces {sorted(set(g.island_piece))}" if hasattr(g, 'island_piece') else '') +
              (f", {g.pinned_by_group} part(s) pinned by group" if getattr(g, 'pinned_by_group', 0) else ''))
        blob = gen.build_resource(g, uid)
        errs = gen.validate(blob, g)
        if errs: raise SystemExit(f"UNIT {ue['id']}: VALIDATION FAILED: " + ', '.join(errs))
        print(f"UNIT {ue['id']}: cloth {len(blob)} bytes, collision on {g.collidable_bones}" +
              (f", {g.n_wind} points follow the cape bones (cape_follow)" if getattr(g, 'n_wind', 0) else ''))
        for bone, r0, r1, n_in, left in getattr(g, 'auto_fit', []):
            print(f"FIT {ue['id']}: collider {bone} {r0:.3f} -> {r1:.3f} m ({n_in} cloth points started inside"
                  + (f", {left} still inside: press Fit to my model or Body fit" if left else "") + ")")
        blobs[uid] = blob
    arcs = st.get('archives') or None
    where = {u: arcs for u in blobs} if arcs else find_archives(list(blobs))
    per_arc = {}
    for u, lst in where.items():
        if not lst: raise SystemExit(f'unit {u:016x} is in no game archive (is it a new unit? cloth needs the unit\'s own archive)')
        for a in lst: per_arc.setdefault(a, []).append(u)
    # the author's armour patch carries the modded unit: the cloth must ALSO sit in that archive. Some views load only
    # that archive (the store preview froze waiting for a cloth it could not find, 2026-10-24: a tester (RS-100 skirt)'s RS-100 skirt
    # with the cloth only in the unit's original archive; with it in the armour patch the store loads). Same setup on
    # a tester (SA-7 cloak)'s torso (cloth in d895..., unit modded in 9ba626...) crashed.
    ap_arc0 = os.path.basename(os.path.abspath(os.path.expanduser(rel(st['armour_patch'])))).split('.patch_')[0]
    ap_units = set(arc.TocDict.get(m.UnitID, {})) if arc is not None else set()
    for u in blobs:
        if u in ap_units and u not in per_arc.get(ap_arc0, []): per_arc.setdefault(ap_arc0, []).append(u)
    out = os.path.abspath(os.path.expanduser(rel(st.get('out', f"dist/other/{st['cloth_name']}"))))
    if os.path.realpath(out).startswith(os.path.realpath(GAME)): raise SystemExit('refusing to build into the game folder')
    os.makedirs(out, exist_ok=True)
    dbg = os.path.join(out, '_debug'); os.makedirs(dbg, exist_ok=True)     # not shipped: raw cloth + the settings used
    for u, blob in blobs.items():          # the raw cloth too: for restorelinks.py and for inspecting
        open(os.path.join(dbg, f'cloth_{u:016x}.bin'), 'wb').write(blob)
        old = os.path.join(out, f'cloth_{u:016x}.bin')
        if os.path.exists(old): os.replace(old, os.path.join(dbg, os.path.basename(old)))
    base = m.BaseArchiveHexID
    material_in = None
    if shader == 'character' and base not in per_arc: per_arc_mat = {base: []}
    else: per_arc_mat = {}
    ap = os.path.abspath(os.path.expanduser(rel(st['armour_patch'])))
    ap_arc = os.path.basename(ap).split('.patch_')[0]
    merge = shader == 'character' and ap_arc == base
    merged_arc = None                              # the archive whose patch_0 also carries the author's armour patch
    for a, us in sorted(list(per_arc.items()) + list(per_arc_mat.items())):
        if a == ap_arc:
            # ONE patch per archive: the author's armour patch + this archive's cloth (and the material in the base
            # archive). Two files with the same name (armour patch + cloth patch) cannot both ship (2026-10-23: a cloth
            # piece on a unit whose own archive is the armour patch's archive, e.g. the B-01 torso in 08e906980c632592)
            merged_arc = a
            dst = os.path.join(out, a + '.patch_0')
            for ext in ('', '.gpu_resources', '.stream'):
                if os.path.exists(ap + ext): shutil.copy(ap + ext, dst + ext)
            TM.LoadArchive(dst, True, True)          # becomes the active patch; written back in place below
        else:
            new_patch(a, os.path.join(out, a + '.patch_0'), 'HD2 Dress cloth: ' + st['cloth_name'])
        for u in us:
            e = TM.AddEntryToPatchID(carrier, u, ReloadUI=False); e.TocData = blobs[u]
        if shader == 'character' and a == base:      # the material lives in the base archive (with its textures)
            for mid in sorted(mat_ids): add_character_material(look, mid, rel)
            material_in = a
        TM.PatchActiveArchive()
        if TM.ActivePatch in TM.Patches: TM.Patches.remove(TM.ActivePatch)     # written: free it
        TM.ActivePatch = None
    # HD2SDK writes TOC data back to back: an odd-sized entry before the cloth put it at an odd offset and the game
    # ignored the whole patch (a tester (SA-7 cloak), 2026-10-24: vanilla armour; aligned = loads, cloth moves). Align every entry.
    import align_patch
    for fn in sorted(os.listdir(out)):
        if fn.endswith('.patch_0'):
            pth = os.path.join(out, fn); d0 = open(pth, 'rb').read(); d1, moved = align_patch.align_toc(d0)
            if d1 != d0: open(pth, 'wb').write(d1)
    with open(os.path.join(dbg, 'manifest.txt'), 'w') as f:
        f.write(f"HD2 Dress engine cloth: {st.get('name', st['cloth_name'])}\ncloth_name {st['cloth_name']}\n")
        for a, us in sorted(per_arc.items()): f.write(f"{a}.patch_0  " + ("YOUR ARMOUR PATCH + " if a == merged_arc else "")
                                                       + f"units {' '.join(f'{u:016x}' for u in us)}"
                                                       + (": ship this instead of your original armour patch\n" if a == merged_arc else "\n"))
        if material_in: f.write(f"{material_in}.patch_0  " + ("YOUR ARMOUR PATCH + " if merge else "") +
                                f"material {' '.join(str(x) for x in sorted(mat_ids))} (character shader)"
                                + (": ship this instead of your original armour patch\n" if merge else "\n"))
    shutil.copy(path, os.path.join(dbg, 'settings.toml'))
    if os.path.exists(os.path.join(out, 'settings.toml')): os.replace(os.path.join(out, 'settings.toml'), os.path.join(dbg, 'settings_old.toml'))
    print(f'BUILT {len(per_arc)} archive patches' + (' + material patch' if material_in else '') + f' into {out}')
    if material_in: per_arc = dict(per_arc, **{material_in: per_arc.get(material_in, []) or ['material']})
    return out, per_arc


def install(out, per_arc):
    """Copy the cloth patches into the game folder. Refuses a patch_0 that exists and is not a previous HD2 Dress
    cloth build (another mod's patch would be destroyed)."""
    reg = os.path.join(CACHE, 'installed_cloth.json')
    mine = json.load(open(reg)) if os.path.exists(reg) else {}
    def slot(a):                                   # our recorded slot, else the next free one after a contiguous run
        if a in mine and isinstance(mine[a], dict): return mine[a]['slot']
        if a in mine: return 0
        n = 0
        while os.path.exists(os.path.join(GAME, f'{a}.patch_{n}')): n += 1
        return n
    for a in per_arc:
        if slot(a) == 0 and os.path.exists(os.path.join(GAME, a + '.patch_0')) and a not in mine:
            raise SystemExit(f'{a}.patch_0 exists and is not an HD2 Dress cloth patch: install by hand / with your mod manager')
    for a in per_arc:
        n = slot(a)
        for ext in ('', '.gpu_resources', '.stream'):
            s = os.path.join(out, a + '.patch_0' + ext)
            if os.path.exists(s): shutil.copy(s, os.path.join(GAME, f'{a}.patch_{n}{ext}'))
        mine[a] = {'out': out, 'slot': n}
        if n: print(f'  {a}: installed as patch_{n} (patch_0..{n - 1} belong to other mods)')
    json.dump(mine, open(reg, 'w'), indent=1)
    print(f'INSTALLED {len(per_arc)} cloth patches into {GAME}')


def dump_colliders(path):
    """The stock cape's capsules (the body colliders every build starts from) as JSON for the panel's Fit to my model:
    [{bone, start, end, radius, off}], start/end in the collider's local space, world = p @ off @ W_bone (row vectors)."""
    from havok_model import Model
    b, _ = template_bytes()
    m1 = Model.load(b, 1); names = [m1.text(x['name']) for x in m1.root['skeletons'][0]['bones']]
    m4 = Model.load(b, 4); sim = m4.root['simClothDatas'][0]; ctm = sim['collidableTransformMap']
    out = []
    for k, c in enumerate(sim['perInstanceCollidables'].item.elems):
        sh = c.value['shape'].value
        if sh.type.name != 'hclCapsuleShape': continue
        out.append(dict(bone=names[ctm['transformIndices'][k]], start=[float(x) for x in sh['start'][:3]],
                        end=[float(x) for x in sh['end'][:3]], radius=float(sh['radius']),
                        off=[float(x) for x in list(ctm['offsets'].item.elems[k])]))
    json.dump(out, open(path, 'w'), indent=1)
    print(f'COLLIDERS {len(out)} capsules -> {path}')


if __name__ == '__main__':
    if args and args[0] == 'colliders': dump_colliders(args[1]); raise SystemExit(0)
    if not args or args[0] not in ('build', 'archives'): raise SystemExit(__doc__)
    if args[0] == 'archives':
        for u, lst in find_archives([int(x, 16) for x in args[1:]]).items(): print(f'UNIT {u:016x}: {len(lst)} archives {lst}')
    else:
        try:
            out, per_arc = build(args[1])
            if '--install' in args: install(out, per_arc)
        except SystemExit as e:              # Blender swallows a script's exit message: print it so the panel can show it
            if e.code not in (None, 0):
                print(f'ERROR: {e.code}', flush=True); raise SystemExit(1)
            raise
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f'ERROR: {type(e).__name__}: {e} (an unexpected failure: please send the full build log)', flush=True)
            raise SystemExit(1)
