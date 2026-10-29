#!/usr/bin/env python3
"""Meaning-level helpers on top of havok_model: decode/encode the packed parts of Havok Cloth data.

- packed vectors (hkPackedVector3): pv_unpack / pv_pack
- object-space deformers (skinning and mesh-mesh deform): deformer_read -> per-vertex records,
  deformer_build <- per-vertex records (same block grouping as Havok's own tools)

Per-vertex record: dict(vertex=int, bones=[int..], weights=[0..255 ints, sum 255], pos=(x,y,z),
normal=(x,y,z)). bones index the operator's transform list (skin ops: transformSubset/boneFromSkinMesh,
mesh-mesh deform: input triangles).
Self test: python3 tools/havok_cloth.py --selftest CLOTH.bin"""
import math, struct, sys

BLEND_NAMES = {1: 'oneBlendEntries', 2: 'twoBlendEntries', 3: 'threeBlendEntries', 4: 'fourBlendEntries',
               5: 'fiveBlendEntries', 6: 'sixBlendEntries', 7: 'sevenBlendEntries', 8: 'eightBlendEntries'}
BLOCK_TYPES = {n: 'hclObjectSpaceDeformer::' + ('One Two Three Four Five Six Seven Eight'.split()[n - 1]) + 'BlendEntryBlock'
               for n in range(1, 9)}


def control_of(n):        # control byte for an n-bone block (verified for n=1..4 on the stock capes)
    return 4 - n if n <= 4 else 4 + (8 - n)


def blend_of(c):
    return 4 - c if c <= 3 else 8 - (c - 4)


# ------------------------------------------------------------------ packed vectors
def pv_unpack(v):
    sc = struct.unpack('<f', struct.pack('<I', (v[3] & 0xFFFF) << 16))[0]
    return tuple(x * 65536.0 * sc for x in v[:3])


def pv_pack(xyz):
    mx = max(abs(c) for c in xyz)
    if mx == 0: return [0, 0, 0, 0]
    e = math.floor(math.log2(mx)) + 1
    s = 2.0 ** (e - 15)
    word = struct.unpack('<I', struct.pack('<f', s / 65536.0))[0] >> 16
    return [max(-32768, min(32767, round(c / s))) for c in xyz] + [word]


# ------------------------------------------------------------------ deformers
def deformer_read(op, model):
    """Per-vertex records of an ObjectSpaceSkinPN / ObjectSpaceMeshMeshDeformPN operator, in block order."""
    d = op['objectSpaceDeformer']; pns = op['localPNs']
    nxt = {n: 0 for n in BLEND_NAMES}
    out = []
    for bi, c in enumerate(d['controlBytes']):
        n = blend_of(c); blk = d[BLEND_NAMES[n]][nxt[n]]; nxt[n] += 1
        pn = pns[bi]
        for i in range(16):
            rec = dict(vertex=blk['vertexIndices'][i], bones=list(blk['boneIndices'][i * n:(i + 1) * n]),
                       weights=list(blk['boneWeights'][i * n:(i + 1) * n]) if n > 1 else [255],
                       pos=pv_unpack(pn['localPosition'][i]['values']), normal=pv_unpack(pn['localNormal'][i]['values']),
                       packed=(list(pn['localPosition'][i]['values']), list(pn['localNormal'][i]['values'])), block=bi)
            out.append(rec)
    return out


def unique_vertices(recs):
    seen = {}; order = []
    for r in recs:
        if r['vertex'] not in seen: seen[r['vertex']] = r; order.append(r)
    return order


def deformer_build(recs, model, base_deformer=None):
    """Build (deformer Struct, localPNs list) from per-vertex records (any order of vertices).
    Grouping (same as Havok's tools, verified on the stock capes): vertices are taken in the given order into
    a pending 16-slot block per bone count; a block is emitted when full or when it received the last
    vertex of its bone count (then padded by repeating that vertex)."""
    from havok_model import Struct
    pending = {}; blocks = []
    last = {}
    for i, r in enumerate(recs): last[len(r['bones'])] = i
    for i, r in enumerate(recs):
        n = len(r['bones'])
        pending.setdefault(n, []).append(r)
        if len(pending[n]) == 16 or i == last[n]:      # full, or the last vertex of this bone count:
            p = pending.pop(n)                          # emit now, padded by repeating its last vertex
            blocks.append((n, p + [p[-1]] * (16 - len(p))))
    d = Struct(model.type_named('hclObjectSpaceDeformer'), base_deformer._raw if base_deformer is not None else None)
    lists = {n: [] for n in BLEND_NAMES}
    pns = []
    for n, rs in blocks:
        bt = model.type_named(BLOCK_TYPES[n]); blk = Struct(bt)
        blk['vertexIndices'] = [r['vertex'] for r in rs]
        blk['boneIndices'] = [b for r in rs for b in r['bones']]
        if n > 1: blk['boneWeights'] = [w for r in rs for w in r['weights']]
        lists[n].append(blk)
        pn = Struct(model.type_named('hclObjectSpaceDeformer::LocalBlockPN'))
        pt = model.type_named('hkPackedVector3')
        def pv(v, key):
            s = Struct(pt); s['values'] = list(v); return s
        pn['localPosition'] = [pv(r['packed'][0] if 'packed' in r else pv_pack(r['pos']), 0) for r in rs]
        pn['localNormal'] = [pv(r['packed'][1] if 'packed' in r else pv_pack(r['normal']), 0) for r in rs]
        pns.append(pn)
    for n, name in BLEND_NAMES.items(): d[name] = lists[n] if lists[n] else None
    d['controlBytes'] = [control_of(n) for n, _ in blocks]
    verts = [r['vertex'] for r in recs]
    d['startVertexIndex'] = min(verts); d['endVertexIndex'] = max(verts)
    d['partialWrite'] = base_deformer['partialWrite'] if base_deformer is not None else False
    return d, pns


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        from havok_model import Model
        b = open(sys.argv[-1], 'rb').read()
        m = Model.load(b, 4) if len(__import__('havok_writer').spans_of(b)) > 4 else Model.load(b, 3)
        for op in m.root['operators']:
            if 'objectSpaceDeformer' not in op.keys() or 'localPNs' not in op.keys(): continue
            name = m.text(op['name']); recs = deformer_read(op, m)
            uniq = unique_vertices(recs)
            d, pns = deformer_build(uniq, m, op['objectSpaceDeformer'])
            orig = op['objectSpaceDeformer']
            same_cb = list(d['controlBytes']) == list(orig['controlBytes'])
            def blocks_eq(n):
                a = d[BLEND_NAMES[n]] or []; o = orig[BLEND_NAMES[n]] or []
                return len(a) == len(o) and all(dict(x) == {k: list(v) if isinstance(v, list) else v for k, v in dict(y).items()} for x, y in zip(a, o))
            same_blocks = all(blocks_eq(n) for n in BLEND_NAMES)
            same_pn = all([s['values'] for s in p['localPosition']] == [list(s['values']) for s in q['localPosition']] for p, q in zip(pns, op['localPNs']))
            print(f'{name:40s} {len(uniq):5d} vertices  control {"OK" if same_cb else "DIFF"}  blocks {"OK" if same_blocks else "DIFF"}  positions {"OK" if same_pn else "DIFF"}')
