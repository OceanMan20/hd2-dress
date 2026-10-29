#!/usr/bin/env python3
"""The author package (the file to SEND): dist/for-authors/HD2-Dress-<version>-for-authors.zip = the add-on zip, GUIDE.html, reference docs, README.
   python3 tools/build_guide_html.py && python3 tools/build_addon.py && python3 tools/pack_authors.py"""
import os, re, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
init = open(os.path.join(ROOT, 'blender', 'hd2_dress', '__init__.py')).read()
ver = '.'.join(re.search(r"'version':\s*\((\d+),\s*(\d+),\s*(\d+)\)", init).groups())
addon = os.path.join(ROOT, 'dist', 'other', f'HD2-Dress-Blender-{ver}.zip')
if not os.path.exists(addon): raise SystemExit(f'build the add-on first: {addon} missing (tools/build_addon.py)')
os.makedirs(os.path.join(ROOT, 'dist', 'for-authors'), exist_ok=True)
out = os.path.join(ROOT, 'dist', 'for-authors', f'HD2-Dress-{ver}-for-authors.zip')
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(addon, os.path.basename(addon))
    z.write(os.path.join(ROOT, 'docs', 'GUIDE.html'), 'GUIDE.html')
    for f in ('ENGINE_CLOTH_GUIDE.md', 'ENGINE_CLOTH_VALUES.md'): z.write(os.path.join(ROOT, 'docs', f), 'reference/' + f)
    z.writestr('README.txt', open(os.path.join(ROOT, 'docs', 'AUTHOR_README.txt')).read().replace('{version}', ver))
print(out)
for n in zipfile.ZipFile(out).namelist(): print('  ' + n)
