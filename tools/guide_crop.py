"""Cut the guide pictures out of tools/guide_shots.py's screenshots: the sidebar (panel) and/or the
3D view of each, into docs/img/guide_*.png.  python3 tools/guide_crop.py SHOTS_DIR OUT_DIR"""
import json, os, sys
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
meta = json.load(open(os.path.join(src, 'shots.json')))
WANT = {'01_loaded': ('UI',), '02_use_my_bones': ('UI', 'WINDOW'), '03_strips_side': ('WINDOW',), '04_edit_bones': ('WINDOW',),
        '05_preview_show_body': ('UI',), '05b_show_body_rest': ('WINDOW',), '06_test_blast': ('WINDOW',), '07_tune': ('UI',), '08_one_bone': ('UI',),
        '09_export': ('UI',)}
for name, kinds in WANT.items():
    if name not in meta: continue
    im = Image.open(os.path.join(src, name + '.png'))
    ww, wh = meta[name]['window']
    sx, sy = im.width / ww, im.height / wh
    for k in kinds:
        x, y, w, h = meta[name]['regions'][k]
        box = (int(x * sx), int((wh - y - h) * sy), int((x + w) * sx), int((wh - y) * sy))
        part = im.crop(box)
        if k == 'WINDOW':        # the model sits in the middle: keep the middle 60 %
            cw = part.width
            part = part.crop((int(cw * 0.2), 0, int(cw * 0.8), part.height))
            part.thumbnail((900, 900))
        out = os.path.join(dst, f'guide_{name}_{"panel" if k == "UI" else "view"}.png')
        part.save(out); print(out, part.size)
