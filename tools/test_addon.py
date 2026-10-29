"""Every button of the HD2 Dress (engine cloth) Blender panel, clicked and CHECKED (the effect, not just 'no error').
   blender -b SCENE.blend -P tools/test_addon.py -- ARMOUR_PATCH COLOUR_MAP OUT_DIR
SCENE: HD2SDK armour scene with a "cloth_skirt" vertex group on its unit objects (a copy: the test edits it).
Prints PASS/FAIL per check and a summary line. Background jobs (build, preview) are waited for and finished by hand
(Blender's timers do not run in -b mode)."""
import bpy, addon_utils, sys, os, time
try: import tomllib
except ModuleNotFoundError:                 # Python 3.10 (Blender 4.0/4.1): the same parser, bundled as tomli
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '_vendor')); import tomli as tomllib
args = sys.argv[sys.argv.index('--') + 1:]
PATCH, COLOUR, OUT = (os.path.abspath(a) for a in args[:3])
addon_utils.enable('HD2SDK-CommunityEdition'); addon_utils.enable('hd2_dress')
import hd2_dress
from hd2_dress import jobs, settings
results = []
def check(name, ok, detail=''):
    results.append(ok); print(f'{"PASS" if ok else "FAIL"}  {name}: {detail}', flush=True)
def step(name, fn):
    try: fn()
    except Exception as e:
        import traceback; traceback.print_exc(); check(name, False, f'error: {e}')
sc = bpy.context.scene; props = sc.hd2dress; U = bpy.context.window_manager.hd2dress_ui
P = hd2_dress.prep_mod()
objs = P.cloth_objects()
slim = next(o for o in objs if 'Slim' in o.name)
def nverts(o, g): return len(P.group_verts(o, g))
def edit_on(o):
    if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    for x in bpy.context.selected_objects: x.select_set(False)
    bpy.context.view_layer.objects.active = o; o.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
def select_verts(o, idx):
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.object.mode_set(mode='OBJECT')
    for v in o.data.vertices: v.select = v.index in idx
    bpy.ops.object.mode_set(mode='EDIT')
def finish_job(timeout=900):
    j = jobs.current(); t0 = time.time()
    while j.rc is None and time.time() - t0 < timeout: time.sleep(0.5)
    while jobs._poll() is not None: time.sleep(0.3)
    return j

# ---- 1 pieces
def t_refresh():
    r = bpy.ops.hd2dress.refresh()
    p = hd2_dress.piece(props, 'cloth_skirt')
    check('Refresh', r == {'FINISHED'} and p is not None and p.counts == 'Slim 648, Stocky 648' and p.follow_legs,
          f'pieces {[x.name for x in props.pieces]}, counts {p.counts if p else None}, skirt follows legs {p.follow_legs if p else None}')
step('refresh', t_refresh)

def t_new_piece():
    edit_on(slim)
    sel = [v.index for v in slim.data.vertices if v.index not in P.cloth_verts(slim)][:40]
    select_verts(slim, set(sel))
    props.new_name = 'Hair Strand'
    r = bpy.ops.hd2dress.piece_new()
    check('New piece from selection', r == {'FINISHED'} and nverts(slim, 'cloth_hair_strand') == 40 and
          hd2_dress.piece(props, 'cloth_hair_strand') is not None and not hd2_dress.piece(props, 'cloth_hair_strand').follow_legs,
          f'group cloth_hair_strand with {nverts(slim, "cloth_hair_strand")} vertices (name cleaned), follow legs off; '
          f'list shows {[x.name for x in props.pieces]}; status "{U.status}"')
    poll_obj = slim; bpy.ops.object.mode_set(mode='OBJECT')
    check('New piece needs Edit Mode', not bpy.ops.hd2dress.piece_new.poll(), 'button greyed out in Object Mode')
step('new piece', t_new_piece)

def t_piece_edit():
    edit_on(slim)
    first = sorted(P.group_verts(slim, 'cloth_hair_strand'))[:10]
    select_verts(slim, set(first))
    bpy.ops.hd2dress.piece_edit(piece='cloth_hair_strand', action='remove')
    a = nverts(slim, 'cloth_hair_strand')
    bpy.ops.hd2dress.piece_edit(piece='cloth_hair_strand', action='assign')
    b = nverts(slim, 'cloth_hair_strand')
    bpy.ops.mesh.select_all(action='DESELECT')
    bpy.ops.hd2dress.piece_edit(piece='cloth_hair_strand', action='select')
    slim.update_from_editmode(); s = sum(v.select for v in slim.data.vertices)
    check('Piece Remove / Add / Select', a == 30 and b == 40 and s == 40, f'remove 10 -> {a}, add back -> {b}, select -> {s} selected')
step('piece edit', t_piece_edit)

def t_pins():
    edit_on(slim)
    before = nverts(slim, 'pin')
    five = set(sorted(P.group_verts(slim, 'cloth_skirt') - P.group_verts(slim, 'pin'))[:5])
    select_verts(slim, five)
    bpy.ops.hd2dress.pin(action='assign'); a = nverts(slim, 'pin'); shown = U.pin_counts
    bpy.ops.hd2dress.pin(action='remove'); b = nverts(slim, 'pin')
    bpy.ops.mesh.select_all(action='DESELECT'); bpy.ops.hd2dress.pin(action='select')
    slim.update_from_editmode(); sel = sum(v.select for v in slim.data.vertices)
    check('Pin / Unpin / Select pins', a == before + 5 and b == before and sel == before,
          f'pins {before} -> pin 5 -> {a} (panel "{shown}") -> unpin -> {b}; select pins -> {sel} selected')
    bpy.ops.object.mode_set(mode='OBJECT')
step('pins', t_pins)

def t_delete():
    r = bpy.ops.hd2dress.piece_delete('EXEC_DEFAULT', piece='cloth_hair_strand')
    check('Delete piece', r == {'FINISHED'} and 'cloth_hair_strand' not in slim.vertex_groups and hd2_dress.piece(props, 'cloth_hair_strand') is None,
          f'group gone, list {[x.name for x in props.pieces]}')
step('delete', t_delete)

def t_copy():
    stocky = next(o for o in objs if 'Stocky' in o.name)
    for n in ('cloth_skirt', 'pin'):
        if n in stocky.vertex_groups: stocky.vertex_groups.remove(stocky.vertex_groups[n])
    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.mode != 'OBJECT' else None
    bpy.context.view_layer.objects.active = slim
    # another mesh of the same slot (an undergarment) is not 'the other body', and the note comes once
    under = stocky.copy(); under.data = stocky.data.copy(); under.name = 'Hip_Undergarment_Stocky_lod0'
    under['Z_CustomizationPieceType'] = 'HelldiverCustomizationPieceType_Undergarment'
    bpy.context.scene.collection.objects.link(under)
    bpy.ops.hd2dress.check()
    notes = [l for l in U.problems.split('\n') if 'no cloth.' in l]
    warned = len(notes) == 1 and 'only on Slim' in notes[0] and 'Stocky gets no cloth' in notes[0]
    r = bpy.ops.hd2dress.copy_pieces()
    copied_under = 'cloth_skirt' in under.vertex_groups
    bpy.data.objects.remove(under); warned = warned and not copied_under
    check('Copy pieces to the other body', r == {'FINISHED'} and warned and nverts(stocky, 'cloth_skirt') == 648 and nverts(stocky, 'pin') == 18,
          f'Check noted once (not the undergarment, not copied onto it): {warned} {notes}; Stocky skirt {nverts(stocky, "cloth_skirt")}, pins {nverts(stocky, "pin")}; status "{U.status}"')
step('copy', t_copy)

# ---- 2 check & fix
def t_check_fix():
    for o in objs:                      # make work for Fix all: drop the 3rd UV set and the root weight
        while len(o.data.uv_layers) > 1: o.data.uv_layers.remove(o.data.uv_layers[-1])
        if 'root' in o.vertex_groups: o.vertex_groups.remove(o.vertex_groups['root'])
    bpy.ops.hd2dress.check()
    lines = U.problems.split('\n')
    fixes = [l for l in lines if l.startswith('FIX')]
    check('Check finds fixable issues', len(fixes) >= 4, f'{len(fixes)} FIX lines, e.g. {fixes[:2]}')
    r = bpy.ops.hd2dress.fix()
    lines = U.problems.split('\n')
    check('Fix all', r == {'FINISHED'} and not any(l.startswith(('FIX', 'PROBLEM')) for l in lines) and
          all(len(o.data.uv_layers) == 3 and P.has_root_weight(o) for o in objs),
          f'after: {lines}; 3 UV sets + root weight on every unit; status "{U.status}"')
    bpy.ops.ed.undo_push(message='after fix')
step('check fix', t_check_fix)

def t_back_side():
    keep = {o.name: o.data.copy() for o in objs}; look = props.look_mode
    n0 = {o.name: len(P.cloth_faces(o)) for o in objs}
    props.look_mode = 'CHARACTER'
    r = bpy.ops.hd2dress.back_side()
    n1 = {o.name: len(P.cloth_faces(o)) for o in objs}
    twins = all(len(P.twin_faces(o, P.cloth_faces(o))) == n1[o.name] for o in objs)
    bpy.ops.hd2dress.check(); lines = U.problems.split('\n')
    ok_char = not any(l.startswith(('FIX', 'PROBLEM')) for l in lines) and all('back side on' in l for l in lines if l.startswith('OK'))
    again = bpy.ops.hd2dress.back_side() == {'FINISHED'} and all(len(P.cloth_faces(o)) == n1[o.name] for o in objs)
    props.look_mode = 'OWN'; bpy.ops.hd2dress.check(); cape = [l for l in U.problems.split('\n') if l.startswith('PROBLEM')]
    check('Add back side', r == {'FINISHED'} and all(n1[k] == 2 * n0[k] for k in n0) and twins and ok_char and again and len(cape) == len(objs),
          f'cloth faces {n0} -> {n1}, every face has a reversed twin {twins}; colour-map Check clean with "back side on" {ok_char}; '
          f'pressing again adds nothing {again}; cape look flags it {len(cape)}x')
    props.look_mode = look
    for o in objs: o.data = keep[o.name]
    bpy.ops.hd2dress.check()
step('back side', t_back_side)

def t_fit():
    keep = {f'fit_{k}_{f}': getattr(props, f'fit_{k}_{f}') for k, _, b in settings.BODY_PARTS for f in ('thick', 'fwd', 'up', 'side')}
    for k in keep: setattr(props, k, 0.0)
    r = bpy.ops.hd2dress.fit_body()
    if jobs.running(): finish_job()          # first run on this machine: colliders read from the game
    vals = {k: round(getattr(props, f'fit_{k}_thick'), 3) for k in ('hips', 'thighs')}
    summary = U.fit_summary.split('\n')
    check('Fit to my model', r == {'FINISHED'} and all(v != 0.0 and -0.25 <= v <= 0.3 for v in vals.values())
          and any(l.startswith('Hips') for l in summary), f'thickness {vals}; summary {summary[:3]}; status "{U.status}"')
    for k, v in keep.items(): setattr(props, k, v)
step('fit', t_fit)

def t_colliders():
    from hd2_dress import colliders_view as CV
    keep = (props.show_colliders, props.fit_hips_thick, props.fit_hips_fwd)
    props.show_colliders = True
    if jobs.running(): finish_job()
    rig = P.rig_of(slim); cols = P.load_colliders()
    props.fit_hips_thick = 0.0; props.fit_hips_fwd = 0.0
    a = CV.capsules(props, rig, cols); hip0 = next(c for c in a if c[0] == 'hips')
    props.fit_hips_thick = 0.05; props.fit_hips_fwd = -0.03
    b = CV.capsules(props, rig, cols); hip1 = next(c for c in b if c[0] == 'hips')
    grew = abs(hip1[3] - hip0[3] - 0.05) < 1e-6; moved = abs((hip1[1] - hip0[1]).y + 0.03) < 1e-6
    lines = len(CV.capsule_lines(hip1[1], hip1[2], hip1[3]))
    check('Show colliders', len(a) >= 15 and grew and moved and lines > 50 and CV._handle is not None,
          f'{len(a)} capsules (kneecaps included); hips +0.05 thick -> radius {hip0[3]:.3f} -> {hip1[3]:.3f}, '
          f'back 3 cm moved {moved}; {lines} line points; viewport drawing registered {CV._handle is not None}')
    props.show_colliders, props.fit_hips_thick, props.fit_hips_fwd = keep
step('colliders', t_colliders)

# ---- 3/4 values -> settings file -> back
VALUES = dict(fit_hips_thick=0.04, fit_thighs_thick=0.02, fit_hips_fwd=-0.03, fit_thighs_len=1.2, fit_thighs_side=0.01, fit_chest_thick=0.03, wind=1.5, gravity=12.5, damping=0.9, friction=0.4, radius=0.03, floor_gap=0.02, iterations=5, follow_thigh=0.5, follow_front=False,
              planes_on=True, planes_reach=0.12, planes_margin=0.01, kneecaps=True, kneecap_grow=0.025, link_passes=2, motion_min=0.7,
              motion_max=3.0, roughness=0.6, weave_on=False, cloth_name='hd2dress_guitest', mod_name='GUI test')
def t_settings():
    for k, v in VALUES.items(): setattr(props, k, v)
    sk = hd2_dress.piece(props, 'cloth_skirt'); sk.leash, sk.stretch, sk.bend, sk.mass, sk.stiffness = 0.8, 0.5, 0.3, 0.005, 0.9
    props.armour_patch = PATCH; props.color_map = COLOUR; props.out_dir = OUT
    props.settings_file = os.path.join(OUT, 'panel_settings.toml'); os.makedirs(OUT, exist_ok=True)
    r = bpy.ops.hd2dress.save_settings()
    st = tomllib.load(open(props.settings_file, 'rb'))
    ok = (st['sim']['gravity'] == 12.5 and st['sim']['wind'] == 1.5 and st['collision']['grow']['hips'] == 0.04 and st['collision']['grow']['r_thigh'] == 0.02 and st['collision']['offset']['hips'] == [0.0, -0.03, 0.0] and st['collision']['length']['l_thigh'] == 1.2 and st['collision']['offset']['l_thigh'][0] == -0.01 and st['collision']['offset']['r_thigh'][0] == 0.01 and st['collision']['chest']['grow'] == 0.03 and st['sim']['iterations'] == 5 and st['sim']['substeps'] == 1 and st['follow']['front'] is False
          and st['planes']['reach'] == 0.12 and st['collision']['extra']['l_knee']['grow'] == 0.025 and st['piece'][0]['leash'] == 0.8
          and st['piece'][0]['follow_legs'] is True and st['cloth']['pin_group'] == 'pin' and len(st['unit']) == 2
          and st['look']['roughness'] == 0.6 and st['cloth_name'] == 'hd2dress_guitest')
    check('Save settings (every slider written)', r == {'FINISHED'} and ok, f'{props.settings_file}: sim {st["sim"]}, piece {st["piece"][0]}')
    for k in VALUES:
        cur = getattr(props, k); setattr(props, k, (not cur) if isinstance(cur, bool) else (cur * 0 + 1 if not isinstance(cur, str) else 'x'))
    sk.leash = 0.1
    r = bpy.ops.hd2dress.load_settings('EXEC_DEFAULT', filepath=props.settings_file)
    bad = {k: getattr(props, k) for k, v in VALUES.items() if (abs(getattr(props, k) - v) > 1e-6 if isinstance(v, float) else getattr(props, k) != v)}
    check('Load settings (every slider restored)', r == {'FINISHED'} and not bad and abs(hd2_dress.piece(props, 'cloth_skirt').leash - 0.8) < 1e-6,
          f'mismatches {bad}; skirt leash {hd2_dress.piece(props, "cloth_skirt").leash:.2f}')
step('settings', t_settings)

def t_errors():
    keep = props.color_map; props.color_map = ''
    r1 = None
    try: r1 = bpy.ops.hd2dress.build(install=False)
    except RuntimeError as e: r1 = str(e)
    props.color_map = keep
    try: r2 = bpy.ops.hd2dress.use_sdk_patch()
    except RuntimeError as e: r2 = str(e)
    check('Build refuses without a colour map', 'colour map' in str(r1), str(r1)[:120])
    check('Use HD2SDK\'s patch with none open', 'no patch open' in str(r2) or r2 == {'FINISHED'}, str(r2)[:120])
step('errors', t_errors)

# ---- 5 build (background job)
def t_build():
    r = bpy.ops.hd2dress.build(install=False)
    check('Build starts a background job', r == {'FINISHED'} and jobs.running(), f'status "{U.status}"')
    j = finish_job()
    os.makedirs(OUT, exist_ok=True); open(os.path.join(OUT, '_test_build.log'), 'w', encoding='utf-8').write('\n'.join(j.lines))
    log = [l for l in j.lines if l.startswith(('UNIT', 'BUILT', 'CLOTH'))]
    files = os.listdir(OUT) if os.path.isdir(OUT) else []
    pinned = [l for l in log if 'pinned' in l]
    check('Build result', j.rc == 0 and any(l.startswith('BUILT') for l in log) and sum(f.endswith('.patch_0') for f in files) >= 2,
          f'rc {j.rc}; {sum(f.endswith(".patch_0") for f in files)} patches; status "{U.status}"')
    check('Build used the pieces and pins', all('pieces' in l for l in pinned) and len(pinned) == 2, ' | '.join(pinned))
    st = tomllib.load(open(os.path.join(OUT, '_debug', 'settings.toml'), 'rb'))
    check('Build used the panel values', st['sim']['gravity'] == 12.5 and st['piece'][0]['leash'] == 0.8, f'copied settings: sim {st["sim"]}')
step('build', t_build)

def t_material():                   # the built material: our surface map (Nar), never the template's (2026-10-24 bug)
    m = sys.modules['HD2SDK-CommunityEdition']
    path = os.path.join(OUT, '9ba626afa44a3aa3.patch_0')
    t = m.StreamToc(); t.FromFile(path)
    mats = list(t.TocDict.get(m.MaterialID, {}).values())
    nar = []
    for e in mats:
        e.Load(False, False); md = e.LoadedData
        if hasattr(md, 'TextureTypes'): names = [x.name for x in md.TextureTypes]
        else:
            mm = sys.modules['HD2SDK-CommunityEdition.stingray.material']; names = [mm.Global_ShaderVariables.get(h, str(h)) for h in md.TexUnks]
        if 'Nar' in names: nar.append(md.TexIDs[names.index('Nar')])
    TEMPLATE_NAR = 11263944652919294967
    check('Material uses our surface map', bool(nar) and TEMPLATE_NAR not in nar and all(t.TocDict.get(m.TexID, {}).get(n) for n in nar),
          f'{len(mats)} material(s), Nar textures {nar} (template {TEMPLATE_NAR}), stored in the patch')
step('material', t_material)

def t_aligned():                    # every entry in every built patch starts on a 16-byte boundary (2026-10-24 bug)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    import align_patch
    bad = {f: len(align_patch.misaligned(open(os.path.join(OUT, f), 'rb').read())) for f in os.listdir(OUT) if f.endswith('.patch_0')}
    check('Built patches aligned', bad and not any(bad.values()), f'{len(bad)} patches, misaligned entries: {sum(bad.values())}')
step('aligned', t_aligned)

def t_preview():
    r = bpy.ops.hd2dress.preview()
    j = finish_job(600)
    files = [l for l in j.lines if l.startswith('PREVIEW')]
    pngs = files[0].split()[1:] if files else []
    check('Preview look', r == {'FINISHED'} and j.rc == 0 and len(pngs) == 3 and all(os.path.exists(p) for p in pngs),
          f'{pngs}; status "{U.status}"')
step('preview', t_preview)

def t_cancel():
    r = bpy.ops.hd2dress.build(install=False)
    time.sleep(3); bpy.ops.hd2dress.cancel(); j = finish_job(60)
    check('Cancel stops the job', j.rc is not None and j.rc != 0 and 'cancelled' in U.status, f'rc {j.rc}; status "{U.status}"')
step('cancel', t_cancel)

def t_sdk_export():                 # HD2SDK's own export of a mesh with cloth + pin groups (it treats groups as bones)
    m = sys.modules['HD2SDK-CommunityEdition']; TM = m.Global_TocManager
    G = hd2_dress.game_dir(props); m.Global_gamepath = G; sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
    TM.LoadArchive(PATCH, SetActive=True, IsPatch=False); TM.CreatePatchFromActive('hd2dress_test')
    bpy.context.scene.Hd2ToolPanelSettings.AutoSaveUnitMaterials = False
    groups = {o.name: sorted(g.name for g in o.vertex_groups if P.is_cloth_group(g.name) or g.name == 'pin') for o in objs}
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    try: r = bpy.ops.helldiver2.archive_unit_batchsave()
    except Exception as e: r = str(e).strip().split('\n')[0][:120]
    after = {o.name: sorted(g.name for g in o.vertex_groups if P.is_cloth_group(g.name) or g.name == 'pin') for o in objs}
    check('HD2SDK export with cloth groups', r == {'FINISHED'} and after == groups and all(groups.values()),
          f'export {r}; groups kept on the objects {after}')
step('sdk export', t_sdk_export)

def t_draw():                       # the panel draws without errors in every state (fake layout)
    class Fake:
        def __getattr__(self, n): return lambda *a, **k: Fake()
        def __setattr__(self, n, v): pass
    pn = hd2_dress.HD2DRESS_PT_panel            # the section methods only use self for other section methods
    me = type('Sections', (), {k: getattr(pn, k) for k in dir(pn) if k.startswith('draw_')})()
    try:
        for weave, look in ((False, 'CHARACTER'), (True, 'OWN'), (False, 'KEEP')):
            props.weave_on = weave; props.show_advanced = weave; props.look_mode = look
            C = bpy.context
            me.draw_pieces(C, props, Fake()); me.draw_check(C, props, Fake()); me.draw_physics(C, props, Fake())
            me.draw_look(C, props, Fake()); me.draw_build(C, props, Fake())
        check('Panel draws (every section, both states)', True, 'no errors')
    except Exception as e:
        import traceback; traceback.print_exc(); check('Panel draws', False, str(e))
step('draw', t_draw)

def t_keep_settings():               # Keep my material: written as look.keep_material and read back
    keep = (props.look_mode, props.material_id)
    props.look_mode = 'KEEP'; props.material_id = '7200101010101010101'
    st = settings.to_settings(props, objs, OUT, bpy.data.filepath)
    props.look_mode = 'CHARACTER'; props.material_id = ''
    settings.from_settings(props, st, OUT, objs)
    lk = st.get('look', {})
    check('Keep my material (settings)', lk.get('keep_material') is True and lk.get('material_id') == 7200101010101010101
          and 'color' not in lk and props.look_mode == 'KEEP', f'look {lk}; panel after load: {props.look_mode}')
    props.look_mode, props.material_id = keep
step('keep settings', t_keep_settings)

print(f'SUMMARY {sum(results)}/{len(results)} passed', flush=True)
