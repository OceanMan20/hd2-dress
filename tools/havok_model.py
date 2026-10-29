#!/usr/bin/env python3
"""Editable object model for Havok 2019 tagfiles (the "raw layer" of HD2 Dress engine cloth).

Every Havok object becomes plain Python values that can be read and changed, and written back:

    m = Model.load(cloth_bytes, tagfile_index)       # one tagfile of a cloth resource
    data = m.root                                      # hclClothData as a Struct
    sim = data['simClothDatas'][0]                     # follow pointers/arrays like lists
    sim['simulationInfo']['gravity'][2] = 9.81         # numbers are plain floats/ints
    data['name'] = 'my_skirt'                          # strings are plain str
    sim['fixedParticles'] = [1, 2, 3]                  # arrays can be replaced by Python lists
    new_bytes = m.save()                               # the tagfile bytes

Values: numbers (int/float/bool), str, Struct (dict-like, keeps its type), lists for fixed arrays,
Ref/ArrayRef for pointers and arrays (they behave like the object / the list they point at),
None for null. Assigning a plain list to an array field makes a new array object of the field's
element type; assigning a Struct to a pointer field links it.

Nothing is generated or hidden here: this is the layer the generator and pros both work on.
Self test: python3 tools/havok_model.py --selftest CLOTH.bin  (decode -> encode must be identical)."""
import struct, sys
from havok_tagfile import Tagfile, sections
from havok_writer import Doc, section, spans_of

STRUCT, ARRAY, POINTER, FIXED, STRING1, STRING2 = 7, 8, 6, 0x28, 3, 0x83


def kind(t): return t.kind & 0xFF


def fixed_info(t):
    n = (t.kind >> 8) & 0xFF
    et = t.ptr or (t.templates[0][1] if t.templates and not isinstance(t.templates[0][1], int) else None)
    return n, et


class Struct(dict):
    """A Havok struct/class value. Keys are member names; .type is the Havok type; ._raw keeps the
    original bytes so bytes not described by members (vtable slot, padding) survive."""
    def __init__(self, t, raw=None):
        super().__init__(); self.type = t; self._raw = raw
    def __repr__(self): return f'<{self.type.full()} {dict.__repr__(self)[:120]}>'


class Item:
    """One ITEM entry: a run of `len(elems)` elements of `type` in DATA."""
    def __init__(self, t, flags, elems):
        self.type, self.flags, self.elems = t, flags, elems
    def __repr__(self): return f'<Item {self.type.full() if self.type else None} x{len(self.elems)}>'


class Ref:
    """Pointer field value: the single object it points to (item with one element)."""
    def __init__(self, item): self.item = item
    @property
    def value(self): return self.item.elems[0]
    def __getitem__(self, k): return self.value[k]
    def __setitem__(self, k, v): self.value[k] = v
    def get(self, k, d=None): return self.value.get(k, d)
    def keys(self): return self.value.keys()
    def __repr__(self): return f'Ref({self.item!r})'


class ArrayRef:
    """Array field value: behaves like the list of elements it points to (resolving pointer elements)."""
    def __init__(self, item): self.item = item
    def __len__(self): return len(self.item.elems)
    def __getitem__(self, i):
        v = self.item.elems[i]
        return v.value if isinstance(v, Ref) and isinstance(i, int) else v
    def __setitem__(self, i, v): self.item.elems[i] = v
    def __iter__(self): return (self[i] for i in range(len(self)))
    def raw(self): return self.item.elems
    def __repr__(self): return f'ArrayRef({self.item!r})'


class Model:
    def __init__(self): self.items = []

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, b, index=0):
        spans = spans_of(b)
        st, sz = spans[index]
        m = cls(); m.b = b; m.span = (st, sz)
        m.tf = tf = Tagfile(b, st + 8, st + sz)
        m.raw_sections = {tag: b[s - 8:e] for tag, s, e in sections(b, st + 8, st + sz)}
        m.types = tf.types
        m.items = [Item(None, 0, [])] + [Item(t, fl, None) for t, off, cnt, fl in tf.items[1:]]
        for k, (t, off, cnt, fl) in enumerate(tf.items[1:], 1):
            a = tf.data_start + off
            if t is None: m.items[k].elems = []; continue
            if kind(t) in (4, 5, 2) and t.size == 1 or t.name in ('char',):
                m.items[k].elems = list(b[a:a + cnt]); m.items[k].bytes_like = True
                continue
            m.items[k].elems = [m._dec(t, a + i * t.size) for i in range(cnt)]
        return m

    def _ref(self, idx, array):
        if not idx or idx >= len(self.items): return None
        return ArrayRef(self.items[idx]) if array else Ref(self.items[idx])

    def _dec(self, t, a):
        b = self.b; k = kind(t)
        if k == STRUCT:
            s = Struct(t, bytes(b[a:a + t.size]))
            for mn, mf, mo, mt in t.all_members(): s[mn] = self._dec(mt, a + mo)
            return s
        if k == FIXED:
            n, et = fixed_info(t)
            return [self._dec(et, a + i * et.size) for i in range(n)]
        if k == ARRAY: return self._ref(struct.unpack_from('<I', b, a)[0], True)
        if k == POINTER: return self._ref(struct.unpack_from('<I', b, a)[0], False)
        if k in (STRING1, STRING2):
            idx = struct.unpack_from('<I', b, a)[0]
            return self._ref(idx, True)
        if k == 2: return bool(b[a])
        if k == 4:
            fmt = {1: 'b', 2: 'h', 4: 'i', 8: 'q'}[t.size]
            return struct.unpack_from('<' + (fmt if t.kind & 0x200 else fmt.upper()), b, a)[0]
        if k == 5: return struct.unpack_from('<f' if t.size == 4 else '<d', b, a)[0]
        if k == 0: return None
        return bytes(b[a:a + (t.size or 0)])          # unknown kind: kept as raw bytes

    # ------------------------------------------------------------------ convenience
    @property
    def root(self): return self.items[1].elems[0]

    def text(self, v):
        """String field value (ArrayRef to a char item, or a str you assigned) -> str."""
        if v is None or isinstance(v, str): return v
        return bytes(v.item.elems).split(b'\0')[0].decode('latin-1')

    def type_named(self, name):
        for t in self.types[1:]:
            if t.full() == name or t.name == name: return t
        raise KeyError(name)

    # ------------------------------------------------------------------ save
    def _new_item(self, t, elems, flags=0x20):
        it = Item(t, flags, elems); self.items.append(it); return it

    def _enc(self, t, v, base=None):
        k = kind(t)
        if k == STRUCT:
            out = bytearray(base if base is not None else (v._raw if isinstance(v, Struct) and v._raw else bytes(t.size)))
            out = out[:t.size] + bytes(max(0, t.size - len(out)))
            for mn, mf, mo, mt in t.all_members():
                out[mo:mo + mt.size] = self._enc(mt, v[mn], bytes(out[mo:mo + mt.size]))
            return bytes(out)
        if k == FIXED:
            n, et = fixed_info(t)
            return b''.join(self._enc(et, v[i], (base or bytes(t.size))[i * et.size:(i + 1) * et.size]) for i in range(n))
        if k in (ARRAY, POINTER, STRING1, STRING2):
            idx = self._index_for(t, v)
            return struct.pack('<I', idx) + bytes(t.size - 4)
        if k == 2: return bytes([1 if v else 0]) + bytes(t.size - 1)
        if k == 4:
            fmt = {1: 'b', 2: 'h', 4: 'i', 8: 'q'}[t.size]
            return struct.pack('<' + (fmt if t.kind & 0x200 else fmt.upper()), int(v))
        if k == 5: return struct.pack('<f' if t.size == 4 else '<d', float(v))
        if k == 0: return b''
        return bytes(v) if v is not None else bytes(t.size or 0)

    def _elem_type(self, t):
        """Element type of an array/pointer/string field type."""
        if kind(t) in (STRING1, STRING2): return self.type_named('char')
        return t.ptr

    def _index_for(self, t, v):
        if v is None: return 0
        if isinstance(v, (Ref, ArrayRef)): return self.index[id(v.item)]
        if isinstance(v, Item): return self.index[id(v)]
        et = self._elem_type(t)
        if isinstance(v, str):
            it = self._new_item(et, list(v.encode('latin-1') + b'\0')); it.bytes_like = True
        elif isinstance(v, (bytes, bytearray)):
            it = self._new_item(et, list(v)); it.bytes_like = True
        elif kind(t) == POINTER:                     # a Struct (or value) to link: wrap in a 1-element item
            it = self._new_item(v.type if isinstance(v, Struct) else et, [v], 0x10)   # keep the subclass (e.g. a capsule behind hclShape*)
        else:                                        # a plain list: new array of the element type
            it = self._new_item(et, list(v))
            if kind(et) in (4, 5, 2) and et.size == 1: it.bytes_like = True
        self.index[id(it)] = len(self.items) - 1
        return self.index[id(it)]

    def prune(self):
        """Drop every item no longer reachable from the root (template leftovers). Returns bytes saved (approx)."""
        seen = set(); stack = [self.items[1]]; keep = [self.items[1]]
        seen.add(id(self.items[1]))
        def walk(v):
            if isinstance(v, (Ref, ArrayRef)):
                it = v.item
                if id(it) not in seen: seen.add(id(it)); keep.append(it); stack.append(it)
            elif isinstance(v, Item):
                if id(v) not in seen: seen.add(id(v)); keep.append(v); stack.append(v)
            elif isinstance(v, dict):
                for x in v.values(): walk(x)
            elif isinstance(v, list):
                for x in v: walk(x)
        while stack:
            it = stack.pop()
            if getattr(it, 'bytes_like', False): continue
            for e in it.elems: walk(e)
        order = {id(it): n for n, it in enumerate(self.items)}
        before = len(self.items)
        self.items = [self.items[0]] + sorted(keep, key=lambda it: order[id(it)])
        self.compact = True                          # template slots no longer apply: pack the data
        return before - len(self.items)

    def save(self):
        """Encode every item and write the tagfile (TYPE section reused from the template)."""
        self.index = {id(it): n for n, it in enumerate(self.items)}
        raws = {}
        n = 1
        while n < len(self.items):                   # items may be appended while encoding
            it = self.items[n]
            if it.type is None: raws[n] = b''
            elif getattr(it, 'bytes_like', False): raws[n] = bytes(it.elems)
            else: raws[n] = b''.join(self._enc(it.type, e) for e in it.elems)
            n += 1
        doc = Doc.__new__(Doc)
        doc.tf = self.tf; doc.raw = self.raw_sections; doc.compact = getattr(self, 'compact', False)
        doc.items = [[None, 0, b'', 0]] + [[it.type, it.flags, raws[k], len(it.elems)] for k, it in enumerate(self.items[1:], 1)]
        return doc.build()


def save_file(b, models):
    """Write a whole cloth resource where {tagfile index: Model} replaces those tagfiles."""
    from havok_writer import rebuild_file
    def edit(n, d):
        if n in models:
            new = models[n].save()
            d.build = (lambda nb=new: nb)
    return rebuild_file(b, edit)


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        b = open(sys.argv[-1], 'rb').read()
        for n, (st, sz) in enumerate(spans_of(b)):
            m = Model.load(b, n)
            new = m.save()
            print(f'tagfile {n}: {len(m.items) - 1} items: {"IDENTICAL" if new == b[st:st + sz] else "DIFFERENT"}')
