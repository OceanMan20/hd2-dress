import bpy, bmesh, sys, os, addon_utils, mathutils
W = os.path.expanduser('~/.cache/hd2-dress/ball/')
addon_utils.enable('HD2SDK-CommunityEdition'); addon_utils.enable('hd2_dress')
import hd2_dress
m = sys.modules['HD2SDK-CommunityEdition']
P = hd2_dress.prep_mod(); props = bpy.context.scene.hd2dress
G = hd2_dress.game_dir(props); m.Global_gamepath = G; sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
def say(s): print('BL', s, flush=True)
objs = P.cloth_objects()
rest = P.load_rest() or P.diver_rest_from_game()
for o in objs:                                     # collision bones first (adds 'chest' with the game's rest pose)
    rig = P.rig_of(o)
    if P.missing_bones(rig): P.add_bones(rig, rest, say)
R, Y = 0.06, 0.20                                  # ball radius; centre this far in front of the chest bone
for o in objs:
    rig = P.rig_of(o); cb = rig.data.bones['chest']
    c = rig.matrix_world @ cb.head_local
    centre = mathutils.Vector((0.0, c.y + Y, c.z))
    me = o.data
    skirt = o.vertex_groups['cloth_skirt']; mat = None
    bm = bmesh.new(); bm.from_mesh(me)
    dl = bm.verts.layers.deform.verify()
    sk = [v for v in bm.verts if skirt.index in v[dl]]
    mat = next((f.material_index for f in bm.faces if all(skirt.index in v[dl] for v in f.verts)), 0)
    bmesh.ops.delete(bm, geom=sk, context='VERTS')               # the test skirt goes: only the ball moves
    uvl = bm.loops.layers.uv.verify()
    res = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=R, matrix=mathutils.Matrix.Translation(centre), calc_uvs=True)
    for name in ('chest', 'cloth_ball', 'pin'):
        if name not in o.vertex_groups: o.vertex_groups.new(name=name)
    gi = {n: o.vertex_groups[n].index for n in ('chest', 'cloth_ball', 'pin')}
    for g in [g for g in o.vertex_groups if g.name == 'cloth_skirt']: pass
    nv = 0; npin = 0
    for v in res['verts']:
        v[dl][gi['chest']] = 1.0; v[dl][gi['cloth_ball']] = 1.0; nv += 1
        if v.co.y < centre.y - R * 0.35: v[dl][gi['pin']] = 1.0; npin += 1
    import math
    for f in {f for v in res['verts'] for f in v.link_faces}:
        f.material_index = mat
        for lp in f.loops:                         # spherical UVs on every UV set (the cloth reads UV0..2)
            d = (lp.vert.co - centre).normalized()
            for L in bm.loops.layers.uv.values():
                lp[L].uv = (0.5 + math.atan2(d.x, -d.y) / (2 * math.pi), 0.5 + math.asin(max(-1, min(1, d.z))) / math.pi)
    bm.to_mesh(me); bm.free(); me.update()
    o.vertex_groups.remove(o.vertex_groups['cloth_skirt'])
    say(f'{o.name}: ball r={R} at {tuple(round(x, 3) for x in centre)}, {nv} vertices, {npin} pinned (back third)')
bpy.ops.hd2dress.refresh()
for pc in props.pieces:
    pc.leash = 0.03; pc.stretch = 0.05; pc.bend = 1.0; pc.stiffness = 1.0; pc.mass = 0.004; pc.follow_legs = False
props.damping = 0.2
props.look_mode = 'CHARACTER'
P.fix_all(P.cloth_objects(), rest, say)
for lv, t in P.check_all(): say(f'CHECK {lv} {t}')
TM = m.Global_TocManager
bpy.context.scene.Hd2ToolPanelSettings.ImportMaterials = False
TM.LoadArchive(G + '9ba626afa44a3aa3', SetActive=True, IsPatch=False)
TM.LoadArchive(os.path.expanduser('~/hd2-dress/tests/fixtures/9ba626afa44a3aa3.patch_0'), SetActive=True, IsPatch=True)
bpy.context.scene.Hd2ToolPanelSettings.AutoSaveUnitMaterials = False
bpy.ops.object.select_all(action='DESELECT')
for o in P.cloth_objects(): o.select_set(True)
bpy.context.view_layer.objects.active = P.cloth_objects()[0]
say(f'export {bpy.ops.helldiver2.archive_unit_batchsave()}')
os.makedirs(W + 'patch', exist_ok=True); TM.ActivePatch.ToFile(W + 'patch/9ba626afa44a3aa3.patch_0')
props.color_map = os.path.expanduser('~/hd2-dress/tests/fixtures/tartan_color.png')
props.armour_patch = W + 'patch/9ba626afa44a3aa3.patch_0'
props.cloth_name = 'hd2dress_jiggle_ball'; props.mod_name = 'Jiggle ball test'
props.out_dir = os.path.expanduser('~/hd2-dress/dist/other/test-jiggle-ball')
bpy.ops.wm.save_as_mainfile(filepath=W + 'ball.blend')
hd2_dress.write_settings(props, W + 'ball.toml', W + 'ball.blend', P.cloth_objects())
say('saved')
