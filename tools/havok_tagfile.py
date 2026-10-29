#!/usr/bin/env python3
"""Generic reader for Havok 2015+ tagfiles (TAG0 / SDKV 2019.1 in Helldivers 2), written for HD2 Dress
research into Havok Cloth (hcl). Uses only the type descriptions stored IN the file (TYPE section), so
no class needs to be known in advance. Read-only.

   python3 tools/havok_tagfile.py FILE [--json OUT.json] [--depth N]

FILE may hold several tagfiles back to back (HD2 cloth resources hold 1-5); each is decoded.
Format notes (own reading of the format; soulstruct-havok used as a reference for the layout):
  section = u32 BE (top 2 bits flags, low 30 bits = size incl. 8-byte header) + 4-char tag
  TAG0 { SDKV, DATA, TYPE { TPTR?, TSTR|TST1, TNAM|TNA1, FSTR|FST1, TBOD|TBDY, THSH?, TPAD? }, INDX { ITEM, PTCH } }
  ITEM entries: u32 (flags<<24 | type index), u32 offset in DATA, u32 count. Pointers/arrays in DATA
  hold item indices."""
import json, struct, sys

SUBTYPE, POINTER, VERSION, BYTESIZE, ABSTRACT, MEMBERS, INTERFACES = 1, 2, 4, 8, 16, 32, 64


class R:
    def __init__(self, b, pos=0): self.b, self.p = b, pos
    def u8(self): v = self.b[self.p]; self.p += 1; return v
    def var(self):
        b1 = self.u8()
        if not b1 & 0x80: return b1 & 0x7F
        if b1 == 0xC3: b = self.b[self.p:self.p + 2]; self.p += 2; return (b[0] << 8) | b[1]
        m = b1 >> 3
        if 0x10 <= m < 0x18: b2 = self.u8(); return 0x3FFF & ((b1 << 8) | b2)
        if 0x18 <= m < 0x1C: b = self.b[self.p:self.p + 2]; self.p += 2; return 0x1FFFFF & ((b1 << 16) | (b[0] << 8) | b[1])
        if m == 0x1C: b = self.b[self.p:self.p + 3]; self.p += 3; return 0x7FFFFFF & ((b1 << 24) | (b[0] << 16) | (b[1] << 8) | b[2])
        if m == 0x1D: b = self.b[self.p:self.p + 4]; self.p += 4; return int.from_bytes(bytes([b1 & 7]) + b, 'big')
        if m == 0x1E: b = self.b[self.p:self.p + 7]; self.p += 7; return int.from_bytes(bytes([b1 & 7]) + b, 'big')
        raise ValueError(f'varint marker {b1:#x} at {self.p - 1}')


def sections(b, start, end):
    p = start
    while p + 8 <= end:
        size = struct.unpack_from('>I', b, p)[0] & 0x3FFFFFFF
        tag = b[p + 4:p + 8].decode('latin-1')
        yield tag, p + 8, p + size
        if size < 8: break
        p += size


class Type:
    def __init__(self, name): self.name, self.templates, self.parent, self.fmt, self.kind = name, [], None, 0, 0; self.ptr = None
    members = None; size = 0; align = 0; version = None; abstract = None
    def all_members(self):
        out = self.parent.all_members() if self.parent else []
        return out + (self.members or [])
    def __repr__(self): return self.full()
    def full(self):
        if not self.templates: return self.name
        ts = []
        for n, v in self.templates:
            ts.append(v.full() if isinstance(v, Type) else str(v))
        return f'{self.name}<{", ".join(ts)}>'


class Tagfile:
    def __init__(self, b, start, end):
        self.b = b
        self.data_start = None
        for tag, s, e in sections(b, start, end):
            if tag == 'SDKV': self.sdk = b[s:e].decode()
            elif tag == 'DATA': self.data_start, self.data_end = s, e
            elif tag == 'TYPE': self.read_types(s, e)
            elif tag == 'INDX': self.read_index(s, e)

    def read_types(self, s, e):
        for tag, a, z in sections(self.b, s, e):
            if tag in ('TSTR', 'TST1'): tnames = self.b[a:z].decode('latin-1').split('\0')
            elif tag in ('FSTR', 'FST1'): fnames = self.b[a:z].decode('latin-1').split('\0')
            elif tag in ('TNAM', 'TNA1'): tna = (a, z)
            elif tag in ('TBOD', 'TBDY'): tbd = (a, z)
        r = R(self.b, tna[0])
        n = r.var()
        self.types = [None]
        raw_t = []
        for _ in range(n - 1):
            t = Type(tnames[r.var()])
            tc = r.var()
            tl = []
            for _ in range(tc):
                tn = tnames[r.var()]; tv = r.var(); tl.append((tn, tv))
            raw_t.append(tl); self.types.append(t)
        for t, tl in zip(self.types[1:], raw_t):
            t.templates = [(tn, self.types[tv] if tn.startswith('t') and tv < len(self.types) else tv) for tn, tv in tl]
        r = R(self.b, tbd[0])
        while r.p < tbd[1]:
            ti = r.var()
            if ti == 0: continue
            t = self.types[ti]
            pi = r.var(); t.parent = self.types[pi] if pi else None
            t.fmt = r.var()
            if t.fmt & SUBTYPE: t.kind = r.var()
            if t.fmt & POINTER and (t.kind & 0xF) >= 6: t.ptr = self.types[r.var()]
            if t.fmt & VERSION: t.version = r.var()
            if t.fmt & BYTESIZE: t.size = r.var(); t.align = r.var()
            if t.fmt & ABSTRACT: t.abstract = r.var()
            if t.fmt & MEMBERS:
                t.members = []
                for _ in range(r.var()):
                    mn = fnames[r.var()]; mf = r.var()
                    if mf & 0x80: r.var()        # 2019: member flag 0x80 = one extra value (seen: 3) before the offset
                    mo = r.var(); mt = self.types[r.var()]
                    t.members.append((mn, mf, mo, mt))
            if t.fmt & INTERFACES:
                for _ in range(r.var()): r.var(); r.var()
        # inherit kind/size for types that only have a parent
        for t in self.types[1:]:
            q = t
            while not q.fmt & SUBTYPE and q.parent: q = q.parent
            if not t.fmt & SUBTYPE: t.kind = q.kind; t.ptr = t.ptr or q.ptr
            q = t
            while not q.fmt & BYTESIZE and q.parent: q = q.parent
            if not t.fmt & BYTESIZE: t.size, t.align = q.size, q.align

    def read_index(self, s, e):
        self.items = []
        for tag, a, z in sections(self.b, s, e):
            if tag == 'ITEM':
                for p in range(a, z, 12):
                    info, off, cnt = struct.unpack_from('<III', self.b, p)
                    self.items.append((self.types[info & 0xFFFFFF] if info else None, off, cnt, info >> 24))

    # ---------------------------------------------------------------- values
    def value(self, t, off, depth, seen):
        k = t.kind & 0xFF
        b = self.b
        if k == 0: return None
        if k == 2: return bool(b[off])
        if k == 4:
            bits = {0x2000: 8, 0x4000: 16, 0x8000: 32, 0x10000: 64}.get(t.kind & 0x1E000, 8 * (t.size or 4))
            signed = bool(t.kind & 0x200)
            fmt = {8: 'b', 16: 'h', 32: 'i', 64: 'q'}[bits]
            return struct.unpack_from('<' + (fmt if signed else fmt.upper()), b, off)[0]
        if k == 5:
            return struct.unpack_from('<d' if t.size == 8 else '<f', b, off)[0] if t.size in (4, 8) else None
        if k == 3 or k == 0x83:   # strings: item index of a char array
            idx = struct.unpack_from('<Q', b, off)[0] & 0xFFFFFFFF
            return self.string(idx)
        if k == 6:   # pointer -> item
            idx = struct.unpack_from('<Q', b, off)[0] & 0xFFFFFFFF
            return self.item(idx, depth, seen)
        if k == 8:   # array: item index + count
            idx = struct.unpack_from('<Q', b, off)[0] & 0xFFFFFFFF
            return self.item(idx, depth, seen, as_array=True, elem=t.ptr)
        if k == 0x28:   # fixed array T[N]
            n = (t.kind >> 8) & 0xFF
            et = t.ptr or (t.templates[0][1] if t.templates and isinstance(t.templates[0][1], Type) else None)
            if not et or not et.size: return None
            return [self.value(et, off + i * et.size, depth, seen) for i in range(n)]
        if k == 7:
            if depth <= 0: return f'<{t.full()}>'
            out = {'@at': off} if getattr(self, 'offsets', False) else {}
            for mn, mf, mo, mt in t.all_members():
                try: out[mn] = self.value(mt, off + mo, depth - 1, seen)
                except Exception as ex: out[mn] = f'!{ex}'
                if getattr(self, 'offsets', False): out.setdefault('@offsets', {})[mn] = off + mo
            return out
        return f'?kind {t.kind:#x} {t.full()}'

    def string(self, idx):
        if not idx or idx >= len(self.items): return None
        t, o, c, _ = self.items[idx]
        a = self.data_start + o
        return self.b[a:a + c].split(b'\0')[0].decode('latin-1')

    def item(self, idx, depth, seen, as_array=False, elem=None):
        if not idx or idx >= len(self.items): return None
        t, o, c, flags = self.items[idx]
        if t is None: return None
        a = self.data_start + o
        if not as_array and c == 1:
            if (idx, 'o') in seen: return f'<ref #{idx} {t.full()}>'
            seen = seen | {(idx, 'o')}
            v = self.value(t, a, depth, seen)
            return {'#': idx, '@type': t.full(), **v} if isinstance(v, dict) else v
        if depth <= 0: return f'<{c} x {t.full()}>'
        cap = getattr(self, 'cap', 64)
        vals = [self.value(t, a + i * t.size, depth - 1, seen) for i in range(min(c, cap))]
        if c > cap: vals.append(f'... {c} in all')
        if (t.kind & 0xFF) in (4, 5) or t.name in ('char', 'hkUint8', 'hkInt8'): return vals
        return vals

    def root(self, depth=6):
        return self.item(1, depth, frozenset())


def tagfiles(b):
    out, p = [], 0
    while True:
        i = b.find(b'TAG0', p)
        if i < 4: break
        size = struct.unpack_from('>I', b, i - 4)[0] & 0x3FFFFFFF
        out.append(Tagfile(b, i + 4, i - 4 + size)); p = i - 4 + size
    return out


if __name__ == '__main__':
    a = sys.argv[1:]
    b = open(a[0], 'rb').read()
    depth = int(a[a.index('--depth') + 1]) if '--depth' in a else 6
    res = []
    for n, tf in enumerate(tagfiles(b)):
        print(f'== tagfile {n}: SDK {tf.sdk}, {len(tf.types) - 1} types, {len(tf.items)} items')
        res.append(tf.root(depth))
    if '--json' in a:
        json.dump(res, open(a[a.index('--json') + 1], 'w'), indent=1, default=str)
        print('wrote', a[a.index('--json') + 1])
