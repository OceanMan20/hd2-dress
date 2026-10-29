"""HD2 Dress for Blender on Windows, headless: blender.exe -b -P windows_check.py -- ADDON_ZIP SDK_ZIP RESULT_FILE
Installs both add-ons through Blender's own installer and checks the Windows-specific parts."""
import bpy, addon_utils, sys, os, json, traceback, tempfile
a = sys.argv[sys.argv.index('--') + 1:]
ADDON, SDK, RESULT = a[0], a[1], a[2]
lines, ok_all = [], True
def check(name, ok, detail=''):
    global ok_all
    ok_all = ok_all and bool(ok)
    line = f'{"PASS" if ok else "FAIL"}  {name}: {detail}'
    print(line, flush=True); lines.append(line)
def step(name, fn):
    try: fn()
    except Exception as e:
        check(name, False, 'error: ' + repr(e)); lines.append(traceback.format_exc())

check('Blender', True, f'{bpy.app.version_string} on {sys.platform}, python {sys.version.split()[0]}, user scripts {bpy.utils.user_resource("SCRIPTS")}')
def inst():
    r1 = bpy.ops.preferences.addon_install(filepath=SDK, overwrite=True)
    r2 = bpy.ops.preferences.addon_install(filepath=ADDON, overwrite=True)
    addon_utils.enable('HD2SDK-CommunityEdition', default_set=True)
    m = addon_utils.enable('hd2_dress', default_set=True)
    import hd2_dress
    check('Install from Disk (both zips)', r1 == {'FINISHED'} and r2 == {'FINISHED'} and m is not None,
          f'SDK {r1}, HD2 Dress {r2}, loaded from {hd2_dress.__file__}')
step('install', inst)
import hd2_dress
from hd2_dress import physics
step('lua', lambda: check('Bundled physics files', os.path.isfile(os.path.join(physics.LIB, 'chain.lua')), physics.LIB))
def steam():
    libs = hd2_dress._steam_libraries()
    check('Steam lookup (registry + library list)', isinstance(libs, list), f'{libs}')
    check('No game in this VM: game_dir is None', hd2_dress.game_dir(bpy.context.scene.hd2dress) is None, '')
    d = os.path.join(tempfile.mkdtemp(), 'Helldivers 2', 'data')
    os.makedirs(d); open(os.path.join(d, '18235e0c9ec0e636'), 'w').close()
    bpy.context.scene.hd2dress.game_path = d
    g = hd2_dress.game_dir(bpy.context.scene.hd2dress)
    check('A chosen game folder is accepted', g and g.endswith('/') and os.path.isdir(g), str(g))
    bpy.context.scene.hd2dress.game_path = ''
step('steam', steam)
def phys():
    before = physics.available()
    ok, msg = physics.install(print)
    check('Install physics (pip lupa, no admin)', ok and physics.available(), f'before: {before}; {msg}; into {physics.vendor_dir()}')
    J = {'l_thigh': (-0.09, 0, 0.94), 'l_knee': (-0.14, 0, 0.52), 'l_foot': (-0.19, 0, 0.1),
         'r_thigh': (0.09, 0, 0.94), 'r_knee': (0.14, 0, 0.52), 'r_foot': (0.19, 0, 0.1), 'spine1': (0, 0, 0.97), 'neck': (0, 0, 1.55), 'head': (0, 0, 1.69)}
    caps = physics.body_capsules(J, {'MARGIN': 0.03})
    check('The game physics runs (LuaJIT, body.lua)', len(caps) == 7, f'{len(caps)} colliders: {[c[0] for c in caps]}')
    w = physics.blast_wave(125, (10, 0, 0), 0.0, {})
    check('Shock waves (blast.lua)', w and w['name'] == 'Hellbomb', str(w and {k: w[k] for k in ('name', 'S', 'R')}))
    meta = {'parts': [{'name': 'skirt', 'names': [['a', 'b'], ['c', 'd'], ['e', 'f'], ['g', 'h']], 'type': 'RING', 'layer': 0, 'parents': ['hips'] * 4,
                       'lengths': [[0.2, 0.2]] * 4}], 'tails': []}
    sim = physics.Sim(meta)
    A = [(0.2, 0, 1), (0, 0.2, 1), (-0.2, 0, 1), (0, -0.2, 1)]
    T = [[(x, y, 0.8), (x, y, 0.6)] for x, y, _ in A]
    for f in range(30): out, _ = sim.step([(A, T)], [], J, 1 / 30, {'MARGIN': 0.03}, [None], [], (1, 0, 0), f / 30, 0.0, (0, 0, 0, 1))
    hem = [round(out[0][c][1][2], 3) for c in range(4)]
    check('A skirt simulates (same numbers as Linux)', hem == [0.92, 0.934, 0.923, 0.933], f'hem z {hem}')
step('physics', phys)
def pack():
    from hd2_dress import export
    pk = export.pack_module()
    d = tempfile.mkdtemp()
    reg = os.path.join(d, 'hd2dress_register.lua')
    open(reg, 'w').write('-- HD2-Addon: mods/hd2dress/reg_test\nHD2DRESS_REGISTRY = {}\n')
    z = pk.lua_zip(reg, d, 'Test - HD2 Dress registration', 'author', 'test')
    check('Export packing (pack.py) on Windows', os.path.isfile(str(z)), str(z))
step('pack', pack)
lines.append('ALL ' + ('PASS' if ok_all else 'FAIL'))
open(RESULT, 'w').write('\n'.join(lines) + '\n')
print('ALL', 'PASS' if ok_all else 'FAIL')
