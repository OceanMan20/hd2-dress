"""Export Helldiver animations from the game files as joint positions per frame (read-only on the game).
   ~/apps/blender-5.2.2-linux-x64/blender -b -P sim/anim_export.py -- OUT.json [--layer N ...] [--anim ID ...] [--limit N] [--fps 30] [--all-bones]
Loads the player's own unit (archive 18235e0c9ec0e636, unit 4d1c334d294dfa97) and its animation
state machine through HD2SDK, turns each animation into a Blender action on that skeleton and samples
the world position (and rotation) of the joints a dress cares about. Additive animations (layered
on top of others) are skipped. Output: {bones, rest: {bone: [...]}, anims: [{id, layer, state, state_name, length, frames:
[{bone: [x,y,z, qw,qx,qy,qz]}]}]}; Helldiver frame: +X right, +Y forward, +Z up, metres."""
import bpy, sys, os, addon_utils, json, time
args = sys.argv[sys.argv.index('--') + 1:]
OUT = args[0]
def opt(name, conv=int, many=False):
    vals = [conv(args[i + 1]) for i, a in enumerate(args) if a == name]
    return vals if many else (vals[0] if vals else None)
LAYERS, ANIMS = opt('--layer', many=True), opt('--anim', many=True)
LIMIT, FPS = opt('--limit') or 10 ** 9, opt('--fps', float) or 30.0
BONES = ['root', 'boss', 'hips', 'spine1', 'spine2', 'chest', 'neck', 'l_shoulder', 'l_elbow', 'l_hand', 'r_shoulder', 'r_elbow', 'r_hand', 'l_thigh', 'l_knee', 'l_foot', 'l_toe', 'r_thigh', 'r_knee', 'r_foot', 'r_toe', 'head']

addon_utils.enable('HD2SDK-CommunityEdition'); m = sys.modules['HD2SDK-CommunityEdition']
G = os.path.expanduser('~/.local/share/Steam/steamapps/common/Helldivers 2/data/'); m.Global_gamepath = G
sys.modules['HD2SDK-CommunityEdition.utils.slim'].slim_init(G)
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
TM = m.Global_TocManager
TM.LoadArchive(G + '9ba626afa44a3aa3', True, False)
TM.LoadArchive(G + '18235e0c9ec0e636', True, False)
TM.Load(5556372446766824087, m.UnitID)
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
if arm.animation_data is None: arm.animation_data_create()
sm = TM.GetEntry(5556372446766824087, m.StateMachineID, SearchAll=True, IgnorePatch=False)
if not sm.IsLoaded: sm.Load()
where = {}
for li, L in enumerate(sm.LoadedData.layers):
    for si, s in enumerate(L.states):
        for a in s.animation_ids: where.setdefault(int(a), (li, si, s.name))
todo = [a for a in where if (not LAYERS or where[a][0] in LAYERS)] if not ANIMS else ANIMS
todo = todo[:LIMIT]
bones = [b for b in BONES if b in arm.pose.bones]
if '--all-bones' in args:   # every joint (for posing a whole outfit in sim/render_armor.py)
    bones = [b.name for b in arm.pose.bones]
print(f'EXPORT {len(todo)} animations, bones {bones}')
bpy.context.view_layer.objects.active = arm
def sample():
    row = {}
    for b in bones:
        mw = arm.matrix_world @ arm.pose.bones[b].matrix
        p, q = mw.translation, mw.to_quaternion()
        row[b] = [round(p.x, 5), round(p.y, 5), round(p.z, 5), round(q.w, 5), round(q.x, 5), round(q.y, 5), round(q.z, 5)]
    return row
arm.animation_data.action = None
for pb in arm.pose.bones: pb.matrix_basis.identity()
bpy.context.view_layer.update()
REST = sample()                      # the skeleton's rest pose (the frame the dress is built in)
out, t0, skipped = [], time.time(), {}
for n, aid in enumerate(todo):
    e = TM.GetEntry(aid, m.AnimationID, SearchAll=True, IgnorePatch=False)
    if e is None: skipped['missing'] = skipped.get('missing', 0) + 1; continue
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
        e.Load(Reload=True, MakeBlendObject=True)   # builds the action on the active armature
    except Exception as ex:
        k = type(ex).__name__; skipped[k] = skipped.get(k, 0) + 1; continue
    anim = e.LoadedData
    if getattr(anim, 'is_additive_animation', False): skipped['additive'] = skipped.get('additive', 0) + 1; continue
    act = arm.animation_data.action
    f0, f1 = act.frame_range
    fps_scene = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    length = float(anim.animation_length)
    frames = []
    nf = max(1, int(round(length * FPS)))
    for k in range(nf + 1):
        t = min(length, k / FPS)
        bpy.context.scene.frame_set(int(f0), subframe=0.0)
        fr = f0 + (f1 - f0) * (t / length if length > 0 else 0)
        bpy.context.scene.frame_set(int(fr), subframe=fr - int(fr))
        frames.append(sample())
    li, si, nm = where.get(int(aid), (-1, -1, 0))
    out.append({'id': str(aid), 'layer': li, 'state': si, 'state_name': str(nm), 'length': length, 'fps': FPS, 'frames': frames})
    bpy.data.actions.remove(act)
    e.LoadedData = None; e.IsLoaded = False
    if n % 25 == 0: print(f'EXPORT {n}/{len(todo)} {time.time() - t0:.0f}s', flush=True)
json.dump({'bones': bones, 'rest': REST, 'skipped': skipped, 'anims': out}, open(OUT, 'w'))
print(f'EXPORT wrote {len(out)} animations to {OUT} in {time.time() - t0:.0f}s; skipped {skipped}')
