#!/usr/bin/env python3
"""Re-lay a patch's TOC file so every entry's data starts on a 16-byte boundary (contents unchanged).
   python3 tools/align_patch.py PATCH_FILE [OUT_FILE]
HD2SDK writes TOC data back to back without alignment: an entry with an odd size before the cloth (a tester (SA-7 cloak)'s patch,
2026-10-24: an unknown-type entry) put the cloth resource at an odd offset and the game ignored the WHOLE patch
(vanilla armour). Only the .patch_N (TOC) file changes; .gpu_resources and .stream are untouched."""
import struct, sys

HEADER = 72          # magic, numTypes, numFiles, unknown, unk4Data[56]
TYPE_SIZE = 32
ENTRY_SIZE = 80      # FileID u64, TypeID u64, TocDataOffset u64, StreamOffset u64, GpuResourceOffset u64, Unknown1 u64,
                     # Unknown2 u64, TocDataSize u32 (at 56), StreamSize u32, GpuResourceSize u32, Unknown3, Unknown4, EntryIndex (as HD2SDK)


def align_toc(data, align=16):
    b = bytearray(data)
    magic, ntypes, nfiles = struct.unpack_from('<III', b, 0)
    if magic != 0xF0000011: raise ValueError('not an HD2 patch/archive TOC')
    e0 = HEADER + TYPE_SIZE * ntypes
    ents = []
    for i in range(nfiles):
        o = e0 + ENTRY_SIZE * i
        off = struct.unpack_from('<Q', b, o + 16)[0]; size = struct.unpack_from('<I', b, o + 56)[0]
        ents.append((o, off, size))
    start = e0 + ENTRY_SIZE * nfiles
    out = bytearray(b[:start]); moved = 0
    for o, off, size in sorted(ents, key=lambda x: x[1]):
        while len(out) % align: out.append(0)
        if len(out) != off: moved += 1
        struct.pack_into('<Q', out, o + 16, len(out))
        out += b[off:off + size]
    end = max(off + size for _, off, size in ents) if ents else start
    out += b[end:]                                          # HD2SDK's trailing padding (256 bytes per entry minimum)
    return bytes(out), moved


def misaligned(data, align=16):
    b = data; magic, ntypes, nfiles = struct.unpack_from('<III', b, 0); e0 = HEADER + TYPE_SIZE * ntypes
    return [(struct.unpack_from('<QQ', b, e0 + ENTRY_SIZE * i)[::-1], struct.unpack_from('<Q', b, e0 + ENTRY_SIZE * i + 16)[0])
            for i in range(nfiles) if struct.unpack_from('<Q', b, e0 + ENTRY_SIZE * i + 16)[0] % align]


if __name__ == '__main__':
    src = sys.argv[1]; dst = sys.argv[2] if len(sys.argv) > 2 else src
    d = open(src, 'rb').read()
    bad = misaligned(d)
    print(f'{len(bad)} entries off a 16-byte boundary: ' + ', '.join(f'type {t:#x} file {f:#x} at {o}' for (t, f), o in bad[:8]))
    new, moved = align_toc(d)
    open(dst, 'wb').write(new)
    print(f'wrote {dst}: {moved} entries moved, {len(misaligned(new))} misaligned now')
