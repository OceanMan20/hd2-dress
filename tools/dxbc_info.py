#!/usr/bin/env python3
"""List the compiled DirectX shaders (DXBC) inside a file: type (vs/ps/...), input signature, resources.
   python3 dxbc_info.py FILE [--vs] [--res]
HD2 keeps material shader code in the PARENT material's GPU data (e.g. cape parent 15780315333863701079)."""
import struct, sys, re, collections
TYPES = {0: 'ps', 1: 'vs', 2: 'gs', 3: 'hs', 4: 'ds', 5: 'cs'}
def blobs(b):
    for mm in re.finditer(rb'DXBC', b):
        a = mm.start()
        if a + 32 > len(b): continue
        size, n = struct.unpack_from('<II', b, a + 24)
        if not (32 < size < 50 << 20) or n > 32: continue
        yield a, b[a:a + size]
def chunks(d):
    n = struct.unpack_from('<I', d, 28)[0]
    for i in range(n):
        o = struct.unpack_from('<I', d, 32 + 4 * i)[0]
        yield d[o:o + 4].decode('latin-1'), d[o + 8:o + 8 + struct.unpack_from('<I', d, o + 4)[0]]
def cstr(d, o):
    e = d.find(b'\0', o); return d[o:e].decode('latin-1')
def sig(c, kind):
    cnt, off = struct.unpack_from('<II', c, 0); out = []
    es = 32 if kind.endswith('1') else 24
    for i in range(cnt):
        p = off + i * es
        if kind.endswith('1'): _st, no, si, sv, ct, reg, mask = struct.unpack_from('<IIIIIIB', c, p)
        else: no, si, sv, ct, reg, mask = struct.unpack_from('<IIIIIB', c, p)
        out.append(f'{cstr(c, no)}{si if si else ""}:{"xyzw"[:bin(mask).count("1")] if mask else "-"}')
    return out
def info(d):
    r = {'type': '?', 'in': [], 'res': []}
    for t, c in chunks(d):
        if t in ('SHEX', 'SHDR'): r['type'] = TYPES.get(struct.unpack_from('<I', c, 0)[0] >> 16, '?')
        elif t in ('ISG1', 'ISGN'): r['in'] = sig(c, t)
        elif t == 'RDEF':
            nb, bo = struct.unpack_from('<II', c, 8)
            for i in range(nb): r['res'].append(cstr(c, struct.unpack_from('<I', c, bo + i * 40)[0]))
    return r
if __name__ == '__main__':
    b = open(sys.argv[1], 'rb').read(); seen = collections.Counter()
    for a, d in blobs(b):
        i = info(d)
        if '--vs' in sys.argv and i['type'] != 'vs': continue
        key = (i['type'], tuple(i['in']))
        seen[key] += 1
        if seen[key] > 1: continue
        print(f"{a:#09x} {i['type']} inputs: {' '.join(i['in'])}")
        if '--res' in sys.argv: print('    res:', ' '.join(x for x in i['res'] if not x.startswith('__samp')))
    print('distinct', len(seen))
