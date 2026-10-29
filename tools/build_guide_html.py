#!/usr/bin/env python3
"""docs/GUIDE.md -> docs/GUIDE.html (dark theme, pictures EMBEDDED so the one file shows them anywhere: from inside a
zip, sent alone in Discord, in a previewer): python3 tools/build_guide_html.py"""
import markdown, os, re, base64
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
md = open(os.path.join(ROOT, 'docs', 'GUIDE.md'), encoding='utf-8').read()
body = markdown.markdown(md, extensions=['tables', 'fenced_code'])
def embed(m):
    path = os.path.join(ROOT, 'docs', m.group(1))
    data = base64.b64encode(open(path, 'rb').read()).decode()
    return f'src="data:image/png;base64,{data}"'
body = re.sub(r'src="(img/[^"]+\.png)"', embed, body)
css = ('body{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;padding:0 1em;line-height:1.55;color:#ddd;'
       'background:#1e1f22}a{color:#8ab4f8}code{background:#2b2d31;padding:1px 4px;border-radius:3px}'
       'img{max-width:100%;border:1px solid #444;border-radius:6px;margin:.5em 0}table{border-collapse:collapse;margin:1em 0}'
       'td,th{border:1px solid #444;padding:6px 10px;vertical-align:top}th{background:#2b2d31}h1,h2,h3{color:#fff}'
       'hr{border:0;border-top:1px solid #444}')
open(os.path.join(ROOT, 'docs', 'GUIDE.html'), 'w', encoding='utf-8').write(
    f'<!doctype html><meta charset="utf-8"><title>HD2 Dress: guide for authors</title><style>{css}</style>\n{body}\n')
print('docs/GUIDE.html')
