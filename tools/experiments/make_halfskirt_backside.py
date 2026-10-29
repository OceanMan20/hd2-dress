import bpy, bmesh, sys, os, addon_utils
W = os.path.expanduser('~/.cache/hd2-dress/abtest/')
addon_utils.enable('HD2SDK-CommunityEdition'); addon_utils.enable('hd2_dress')
import hd2_dress
m = sys.modules['HD2SDK-CommunityEdition']
P = hd2_dress.prep_mod(); props = bpy.context.scene.hd2dress
G = hd2_dress.game_dir(props); m.Global_gamepath = G; sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
def say(s): print('AB', s, flush=True)
for o in P.cloth_objects():                       # back-only half skirt: drop the cloth faces in front (+Y = forward)
    cf = {f.index for f in P.cloth_faces(o) if f.center.y > 0.0}
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in cf], context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')
    bm.to_mesh(o.data); bm.free(); o.data.update()
    say(f'{o.name}: half skirt, {len(P.cloth_faces(o))} cloth faces, {len(P.group_verts(o, "pin"))} pins')
bpy.ops.hd2dress.refresh()
props.look_mode = 'CHARACTER'
bpy.ops.hd2dress.back_side(); say(hd2_dress.ui().status)
rest = P.load_rest() or P.diver_rest_from_game()
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
props.cloth_name = 'hd2dress_halfskirt_a'; props.mod_name = 'Half skirt A (Add back side)'
props.out_dir = os.path.expanduser('~/hd2-dress/dist/abtest-A-backside')
bpy.ops.wm.save_as_mainfile(filepath=W + 'halfskirt_a.blend')
hd2_dress.write_settings(props, W + 'a.toml', W + 'halfskirt_a.blend', P.cloth_objects())
say('saved')
