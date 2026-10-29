import bpy, bmesh, sys, os, math, addon_utils, mathutils
W = os.path.expanduser('~/.cache/hd2-dress/ball/torso/'); os.makedirs(W, exist_ok=True)
addon_utils.enable('HD2SDK-CommunityEdition'); addon_utils.enable('hd2_dress')
import hd2_dress
m = sys.modules['HD2SDK-CommunityEdition']
P = hd2_dress.prep_mod(); props = bpy.context.scene.hd2dress
G = hd2_dress.game_dir(props); m.Global_gamepath = G; sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
def say(s): print('BT', s, flush=True)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
st = bpy.context.scene.Hd2ToolPanelSettings; st.ImportMaterials = False
TM = m.Global_TocManager
ARC = '08e906980c632592'; UNITS = (0x18902007139a6060, 0x2d9ce590011788ac)
TM.LoadArchive(G + ARC, SetActive=True, IsPatch=False)
TM.CreatePatchFromActive('torso_ball')
for u in UNITS: TM.Load(u, m.UnitID)
objs = [o for o in bpy.data.objects if o.type == 'MESH' and P._uid(o) in UNITS]
say(f'imported {[(o.name, o.get("MeshInfoIndex")) for o in objs]}')
lod0 = [o for o in objs if not P.is_lower_lod(o) and 'culling' not in o.name.lower()]
rest = P.load_rest() or P.diver_rest_from_game()
R, Y = 0.06, 0.20
for o in lod0:
    rig = P.rig_of(o)
    if 'hips' not in rig.data.bones:                 # the generator needs a hips bone (wind/motion only)
        bpy.context.view_layer.objects.active = rig; rig.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
        M, length = rest['hips']; eb = rig.data.edit_bones.new('hips'); eb.length = length
        eb.matrix = rig.matrix_world.inverted() @ mathutils.Matrix(M); eb.length = length
        eb.parent = rig.data.edit_bones.get('root'); bpy.ops.object.mode_set(mode='OBJECT'); say(f'{rig.name}: added hips')
    cb = rig.data.bones['chest']; c = rig.matrix_world @ cb.head_local
    centre = mathutils.Vector((0.0, c.y + Y, c.z))
    me = o.data; bm = bmesh.new(); bm.from_mesh(me)
    dl = bm.verts.layers.deform.verify()
    res = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=R, matrix=mathutils.Matrix.Translation(centre), calc_uvs=False)
    for name in ('chest', 'cloth_ball', 'pin'):
        if name not in o.vertex_groups: o.vertex_groups.new(name=name)
    gi = {n: o.vertex_groups[n].index for n in ('chest', 'cloth_ball', 'pin')}
    npin = 0
    for v in res['verts']:
        v[dl][gi['chest']] = 1.0; v[dl][gi['cloth_ball']] = 1.0
        if v.co.y < centre.y - R * 0.35: v[dl][gi['pin']] = 1.0; npin += 1
    for f in {f for v in res['verts'] for f in v.link_faces}:
        f.material_index = 0
        for lp in f.loops:
            d = (lp.vert.co - centre).normalized()
            for L in bm.loops.layers.uv.values():
                lp[L].uv = (0.5 + math.atan2(d.x, -d.y) / (2 * math.pi), 0.5 + math.asin(max(-1, min(1, d.z))) / math.pi)
    bm.to_mesh(me); bm.free(); me.update()
    say(f'{o.name}: ball at {tuple(round(x, 3) for x in centre)}, {len(res["verts"])} vertices, {npin} pinned')
bpy.ops.hd2dress.refresh()
for pc in props.pieces:
    pc.leash = 0.03; pc.stretch = 0.05; pc.bend = 1.0; pc.stiffness = 1.0; pc.mass = 0.004; pc.follow_legs = False
props.damping = 0.2; props.look_mode = 'CHARACTER'
cl = P.cloth_objects()
for o in cl: P.three_uvs(o, say); P.root_in_palette(o, say); P.fix_node_offset(o, say)
for lv, t in P.check_all(): say(f'CHECK {lv} {t}')
st.AutoSaveUnitMaterials = False
bpy.ops.object.select_all(action='DESELECT')
for o in cl: o.select_set(True)
bpy.context.view_layer.objects.active = cl[0]
say(f'export {bpy.ops.helldiver2.archive_unit_batchsave()}')
TM.ActivePatch.ToFile(W + f'{ARC}.patch_0')
props.color_map = os.path.expanduser('~/hd2-dress/tests/fixtures/tartan_color.png')
props.armour_patch = W + f'{ARC}.patch_0'
props.cloth_name = 'hd2dress_jiggle_torso'; props.mod_name = 'Jiggle ball on torso'
props.out_dir = os.path.expanduser('~/hd2-dress/dist/test-jiggle-ball-torso')
bpy.ops.wm.save_as_mainfile(filepath=W + 'ball_torso.blend')
hd2_dress.write_settings(props, W + 'ball_torso.toml', W + 'ball_torso.blend', cl)
say('saved')
