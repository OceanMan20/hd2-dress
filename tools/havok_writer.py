#!/usr/bin/env python3
"""Writer for Havok 2019 tagfiles (TAG0), for HD2 Dress cloth authoring.

Design: the TYPE section is copied unchanged from a template file (the stock cape has every hcl class a
garment needs), so only the objects change. A file is a list of items (type, flags, raw bytes); the
writer lays them out in DATA, rebuilds ITEM and recomputes PTCH (the list of pointer/array/string
fields) from the type descriptions.

   python3 tools/havok_writer.py --selftest CLOTH.bin      # rebuild every tagfile, compare bytes

Pointers inside DATA hold ITEM indices, so items can move or grow freely as long as indices stay the
same; new items are appended."""
import struct, sys
from havok_tagfile import Tagfile, sections, tagfiles

PTR_KINDS = (3, 6, 8)      # string, pointer, array: the fields PTCH lists (only when non-null)


def section(tag, body, flags=0x40000000):
    return struct.pack('>I', (len(body) + 8) | flags) + tag.encode() + body


class Doc:
    """One tagfile as editable items. items[i] = [type, flags, bytes, count]; item 0 is the null item."""

    def __init__(self, b, start, end):
        self.tf = tf = Tagfile(b, start, end)
        self.raw = {tag: b[s - 8:e] for tag, s, e in sections(b, start, end)}
        self.items = [[None, 0, b'', 0]]
        for t, off, cnt, flags in tf.items[1:]:
            size = self.item_size(t, cnt)
            a = tf.data_start + off
            self.items.append([t, flags, bytes(b[a:a + size]), cnt])

    @staticmethod
    def item_size(t, cnt):
        return (t.size or 1) * cnt if t else 0

    # ------------------------------------------------------------------ layout
    def layout(self):
        """Items keep their original place when they still fit their old slot (Havok's own writer leaves
        gaps we do not need to reproduce: the loader only reads ITEM offsets); new or grown items go at
        the end, 16-aligned."""
        tf = self.tf
        if getattr(self, 'compact', False):          # generated files: every item packed in order, 16-aligned
            data = bytearray(); offs = [0]
            for t, flags, raw, cnt in self.items[1:]:
                while len(data) % 16: data.append(0)
                offs.append(len(data)); data += raw
            while len(data) % 16: data.append(0)
            return data, offs
        if not hasattr(self, 'slots'):
            end = tf.data_end - tf.data_start
            order = sorted(range(1, len(tf.items)), key=lambda k: tf.items[k][1])
            self.slots = {}
            for n, k in enumerate(order):
                nxt = tf.items[order[n + 1]][1] if n + 1 < len(order) else end
                self.slots[k] = (tf.items[k][1], nxt - tf.items[k][1])
            self.orig_len = end
        data = bytearray(self.orig_len); offs = [0]; tail = []
        for k, (t, flags, raw, cnt) in enumerate(self.items[1:], 1):
            slot = self.slots.get(k)
            if slot and len(raw) <= slot[1]:
                data[slot[0]:slot[0] + len(raw)] = raw; data[slot[0] + len(raw):slot[0] + slot[1]] = bytes(slot[1] - len(raw))
                offs.append(slot[0])
            else:
                offs.append(None); tail.append(k)
        for k in tail:
            while len(data) % 16: data.append(0)
            offs[k] = len(data); data += self.items[k][2]
        while len(data) % 16: data.append(0)
        return data, offs

    def ptch(self, offs, data):
        by_type = {}
        def walk(t, base):
            k = t.kind & 0xFF
            if (k & 0x7F) in PTR_KINDS:
                if struct.unpack_from('<Q', data, base)[0] & 0xFFFFFFFF:
                    by_type.setdefault(self.tf.types.index(t), []).append(base)
                return
            if k == 7:
                for mn, mf, mo, mt in t.all_members(): walk(mt, base + mo)
            elif k == 0x28:
                n = (t.kind >> 8) & 0xFF
                et = t.ptr or (t.templates[0][1] if t.templates else None)
                if et and et.size:
                    for i in range(n): walk(et, base + i * et.size)
        for (t, flags, raw, cnt), o in zip(self.items[1:], offs[1:]):
            if t is None: continue
            for i in range(cnt): walk(t, o + i * (t.size or 1))
        out = bytearray()
        for ti in sorted(by_type):
            v = sorted(by_type[ti])
            out += struct.pack('<II', ti, len(v)) + struct.pack(f'<{len(v)}I', *v)
        return bytes(out)

    def build(self):
        data, offs = self.layout()
        item = bytearray(struct.pack('<III', 0, 0, 0))
        for (t, flags, raw, cnt), o in zip(self.items[1:], offs[1:]):
            ti = self.tf.types.index(t) if t else 0
            item += struct.pack('<III', (flags << 24) | ti, o, cnt)
        indx = section('ITEM', bytes(item)) + section('PTCH', self.ptch(offs, data))
        body = self.raw['SDKV'] + section('DATA', bytes(data)) + self.raw['TYPE'] + section('INDX', indx, 0)
        return section('TAG0', body, 0)


def spans_of(b):
    out = []; p = 0
    while True:
        i = b.find(b'TAG0', p)
        if i < 4: return out
        st = i - 4; sz = struct.unpack_from('>I', b, st)[0] & 0x3FFFFFFF; out.append((st, sz)); p = st + sz


def rebuild_file(b, edit=None):
    """Rebuild a cloth resource. edit(n, doc) may change tagfile n before it is written. The resource header
    (before the first TAG0) lists every tagfile as (offset, size) plus the trailing native blob's offset;
    those and the two length fields (+16 = file length, +76 = file length - 8) are updated."""
    spans = spans_of(b); head = bytearray(b[:spans[0][0]])
    out = bytearray(head); new_spans = []
    for n, (st, sz) in enumerate(spans):
        while len(out) % 16: out.append(0)
        d = Doc(b, st + 8, st + sz)
        if edit: edit(n, d)
        t = d.build(); new_spans.append((len(out), len(t))); out += t
    old_tail = spans[-1][0] + spans[-1][1]
    tail = b[old_tail:]
    old_tail_off = old_tail + (-old_tail % 16) if tail else old_tail
    while len(out) % 16 and tail: out.append(0)
    new_tail_off = len(out); out += tail[old_tail_off - old_tail:] if tail else b''
    for o in range(80, len(head) - 3, 4):
        v = struct.unpack_from('<I', head, o)[0]; prev = struct.unpack_from('<I', head, o - 4)[0]
        for (st, sz), (nst, nsz) in zip(spans, new_spans):
            if v == st and v: struct.pack_into('<I', out, o, nst); break
            if v == sz and prev == st: struct.pack_into('<I', out, o, nsz); break
        else:
            if v == old_tail_off and tail: struct.pack_into('<I', out, o, new_tail_off)
    struct.pack_into('<I', out, 16, len(out)); struct.pack_into('<I', out, 76, len(out) - 8)
    return bytes(out)


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        b = open(sys.argv[-1], 'rb').read()
        p = 0; n = 0
        while True:
            i = b.find(b'TAG0', p)
            if i < 4: break
            start = i - 4; size = struct.unpack_from('>I', b, start)[0] & 0x3FFFFFFF
            orig = b[start:start + size]; new = Doc(b, i + 4, start + size).build()
            same = orig == new
            print(f'tagfile {n}: {size} bytes, rebuilt {len(new)}: {"IDENTICAL" if same else "DIFFERENT"}')
            if not same:
                for k in range(min(len(orig), len(new))):
                    if orig[k] != new[k]: print(f'   first difference at {k}: {orig[k:k+16].hex()} vs {new[k:k+16].hex()}'); break
            p = start + size; n += 1
