"""Cut the guide pictures out of tools/guide_shots_engine.py's screenshots: the sidebar, down to the end of the panel.
   python3 tools/guide_crop_engine.py SHOTS_DIR docs/img/guide"""
import json, os, sys
import numpy as np
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
os.makedirs(dst, exist_ok=True)
meta = json.load(open(os.path.join(src, 'shots.json')))
for name, m in meta.items():
    im = Image.open(os.path.join(src, name + '.png')).convert('RGB')
    ww, wh = m['window']; sx, sy = im.width / ww, im.height / wh
    if 'area' in m:                                      # whole 3D view or window: no panel trimming
        x, y, w, h = m['area']
        part = im.crop((int(x * sx), int((wh - y - h) * sy), int((x + w) * sx), int((wh - y) * sy)))
        out = os.path.join(dst, name + '.png'); part.save(out); print(out, part.size); continue
    x, y, w, h = m['ui']
    part = im.crop((int(x * sx), int((wh - y - h) * sy), int((x + w - 22) * sx), int((wh - y) * sy)))   # minus the tab strip
    a = np.asarray(part).astype(int)
    edge = a[:, 6]                                       # the panel's left margin: panel colour until the panel ends
    ref = a[40, 6]
    inside = np.nonzero(np.abs(edge - ref).sum(axis=1) < 12)[0]
    bottom = int(inside.max()) + 8 if len(inside) else part.height
    part = part.crop((0, 0, part.width, min(part.height, bottom)))
    out = os.path.join(dst, name + '.png'); part.save(out); print(out, part.size)
