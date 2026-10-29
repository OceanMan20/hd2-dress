#!/usr/bin/env python3
"""Build the installable Blender add-on: dist/other/HD2-Dress-Blender-<version>.zip (the add-on alone; what authors
   get is the author package in dist/for-authors/, see tools/pack_authors.py)
   python3 tools/build_addon.py
The zip holds one folder, hd2_dress/: the panel (Python files) and tools/ (the engine cloth tools it runs: build,
prep, preview, the Havok cloth generator). Install it in Blender: Edit > Preferences > Add-ons > (top right menu)
Install from Disk. Needs HD2SDK Community Edition. Engine cloth only (the old Lua physics is gone)."""
import os, re, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'blender', 'hd2_dress')
TOOLS = ['hd2dress_cloth.py', 'hd2dress_prep.py', 'hd2dress_preview.py', 'gen_engine_cloth.py', 'havok_model.py',
         'havok_cloth.py', 'havok_writer.py', 'havok_tagfile.py', 'hd2_paths.py', 'viewer_assets.py', 'align_patch.py']
init = open(os.path.join(SRC, '__init__.py')).read()
ver = '.'.join(re.search(r"'version':\s*\((\d+),\s*(\d+),\s*(\d+)\)", init).groups())
os.makedirs(os.path.join(ROOT, 'dist', 'other'), exist_ok=True)
out = os.path.join(ROOT, 'dist', 'other', f'HD2-Dress-Blender-{ver}.zip')
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(SRC)):
        if f.endswith('.py'): z.write(os.path.join(SRC, f), f'hd2_dress/{f}')
    for f in TOOLS: z.write(os.path.join(ROOT, 'tools', f), f'hd2_dress/tools/{f}')
    vend = os.path.join(ROOT, 'tools', '_vendor')          # tomli: tomllib for Python 3.10 (Blender 4.0/4.1)
    for d, _, fs in os.walk(vend):
        for f in fs:
            if f.endswith('.pyc'): continue
            full = os.path.join(d, f); z.write(full, 'hd2_dress/tools/_vendor/' + os.path.relpath(full, vend).replace(os.sep, '/'))
print(out)
for n in zipfile.ZipFile(out).namelist(): print('  ' + n)
