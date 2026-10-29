#!/usr/bin/env python3
"""Install zips for HD2 Arsenal.
   python3 tools/pack.py addon LUAFILE OUTDIR VERSION          -> HD2-Dress-<VERSION>.zip (the Lua addon)
   python3 tools/pack.py armour PATCHDIR OUTDIR NAME VERSION    -> <NAME>-<VERSION>.zip (a built model patch)
   python3 tools/pack.py expand LUAFILE                        -> the single-file Lua (stdout), as shipped
   python3 tools/pack.py selftest
A line '--@include lib/x.lua' is replaced by that file (relative to the Lua file), so the mod can be
split into testable files and still ship as one addon.

A Bingus Shared Loader addon is a patch of the base archive (9ba626afa44a3aa3) holding one Lua
resource. Layout (same format hd2-vr ships, checked there byte for byte against published addons):
  0x00 header, 0x50 bytes: magic F0000011, 1 type, 1 file; u32 total size at 0x20
  0x50 type entry, 0x18: lua type hash (u64), count 1 (u64), 16, 16
  0x68 file entry, 0x50: name hash, type hash, data offset 0xC0 (u64s); u32 size at +0x38; 16, 16 at +0x44
  0xC0 data: u32 text length, u32 2 (= plain source), the Lua text; padded to 16
The name hash is murmur64a of the addon id from the first line ('-- HD2-Addon: mods/<author>/<name>')."""
import json, struct, sys, zipfile
from pathlib import Path

BASE = '9ba626afa44a3aa3'
LUA_TYPE = 0xA14E8DFA2CD117E2
GUID_ADDON = '4f1e804a-5799-4a96-abef-f509e15a2468'
GUID_ARMOUR = 'bb2f9111-9bc2-41bd-862e-877262913e8b'


def murmur64a(data: bytes, seed: int = 0) -> int:
    m, r, mask = 0xC6A4A7935BD1E995, 47, (1 << 64) - 1
    h = (seed ^ (len(data) * m)) & mask
    whole = len(data) // 8
    for i in range(whole):
        k = struct.unpack_from('<Q', data, i * 8)[0]
        k = (k * m) & mask; k ^= k >> r; k = (k * m) & mask
        h = ((h ^ k) * m) & mask
    rest = data[whole * 8:]
    if rest:
        h = ((h ^ int.from_bytes(rest, 'little')) * m) & mask
    h ^= h >> r; h = (h * m) & mask; h ^= h >> r
    return h


def expand(lua_file) -> bytes:
    path = Path(lua_file)
    out = []
    for line in path.read_text().splitlines(keepends=True):
        if line.strip().startswith('--@include '):
            inc = path.parent / line.strip().split(' ', 1)[1]
            out.append(f'-- begin {inc.name}\n' + inc.read_text().rstrip('\n') + f'\n-- end {inc.name}\n')
        else:
            out.append(line)
    return ''.join(out).encode()


def lua_patch(lua: bytes) -> bytes:
    first = lua.split(b'\n', 1)[0]
    assert first.startswith(b'-- HD2-Addon: mods/'), 'first line must be the HD2-Addon header'
    name_hash = murmur64a(first.split(b': ', 1)[1].strip())
    data = struct.pack('<II', len(lua), 2) + lua
    out = bytearray(0xC0)
    struct.pack_into('<III', out, 0, 0xF0000011, 1, 1)
    struct.pack_into('<QQII', out, 0x50, LUA_TYPE, 1, 16, 16)
    struct.pack_into('<QQQ', out, 0x68, name_hash, LUA_TYPE, 0xC0)
    struct.pack_into('<I', out, 0x68 + 0x38, len(data))
    struct.pack_into('<II', out, 0x68 + 0x44, 16, 16)
    out += data
    out += bytes(-len(out) % 16)
    struct.pack_into('<I', out, 0x20, len(out))
    return bytes(out)


def write_zip(path: Path, guid: str, name: str, desc: str, folder: str, files: dict):
    manifest = {'Version': 1, 'Guid': guid, 'Name': name, 'Description': desc,
                'Options': [{'Name': name, 'Description': desc, 'Include': [folder]}]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json', json.dumps(manifest, indent=2))
        for n, b in files.items():
            z.writestr(f'{folder}/{n}', b)
    return path


def addon(lua_file, outdir, version):
    patch = lua_patch(expand(lua_file))
    return write_zip(Path(outdir) / f'HD2-Dress-{version}.zip', GUID_ADDON, f'HD2 Dress {version}',
                     f'HD2 Dress {version} (Lua addon). Requires Bingus Shared Loader v18+.', 'Addon',
                     {f'{BASE}.patch_0': patch, f'{BASE}.patch_0.stream': b'', f'{BASE}.patch_0.gpu_resources': b''})


def lua_zip(lua_file, outdir, name, version, desc):
    """any single Lua addon (e.g. a dress registration) -> its own zip; GUID derived from the name"""
    import uuid
    patch = lua_patch(expand(lua_file))
    guid = str(uuid.uuid5(uuid.NAMESPACE_URL, 'hd2dress/' + name))
    return write_zip(Path(outdir) / f"{name.replace(' ', '-')}-{version}.zip", guid, f'{name} {version}', desc, 'Addon',
                     {f'{BASE}.patch_0': patch, f'{BASE}.patch_0.stream': b'', f'{BASE}.patch_0.gpu_resources': b''})


def model_zip(patchdir, outdir, name, version, desc):
    """a built model patch (3 files) -> its own zip; GUID derived from the name"""
    import uuid
    d = Path(patchdir)
    files = {f'{BASE}.patch_0{s}': (d / f'{BASE}.patch_0{s}').read_bytes() for s in ('', '.gpu_resources', '.stream')}
    guid = str(uuid.uuid5(uuid.NAMESPACE_URL, 'hd2dress/' + name))
    return write_zip(Path(outdir) / f"{name.replace(' ', '-')}-{version}.zip", guid, f'{name} {version}', desc, 'Patch', files)


def armour(patchdir, outdir, name, version):
    d = Path(patchdir)
    files = {f'{BASE}.patch_0{s}': (d / f'{BASE}.patch_0{s}').read_bytes() for s in ('', '.gpu_resources', '.stream')}
    return write_zip(Path(outdir) / f'{name}-{version}.zip', GUID_ARMOUR, f'{name} {version}',
                     f'{name} {version}: B-01 Tactical hip armour with the dress test bones.', 'Armour', files)


def selftest():
    assert murmur64a(b'lua') == LUA_TYPE   # the engine's own type hash for "lua"
    lua = b'-- HD2-Addon: mods/test/x\nprint(1)\n'
    p = lua_patch(lua)
    n, kind = struct.unpack_from('<II', p, 0xC0)
    assert kind == 2 and p[0xC8:0xC8 + n] == lua and len(p) % 16 == 0
    assert struct.unpack_from('<I', p, 0x20)[0] == len(p)
    assert struct.unpack_from('<Q', p, 0x68)[0] == murmur64a(b'mods/test/x')
    print('pack selftest ok')


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'addon': print(addon(*sys.argv[2:5]))
    elif cmd == 'armour': print(armour(*sys.argv[2:6]))
    elif cmd == 'expand': sys.stdout.write(expand(sys.argv[2]).decode())
    elif cmd == 'luazip': print(lua_zip(*sys.argv[2:7]))
    elif cmd == 'modelzip': print(model_zip(*sys.argv[2:7]))
    else: selftest()
