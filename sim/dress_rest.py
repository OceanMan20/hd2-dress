#!/usr/bin/env python3
"""hd2dress_register.json (tools/dress_autorig.py) -> a simulator dress file (Lua), one unit.
   python3 sim/dress_rest.py REGISTER.json OUT.lua [UNIT_NAME_PART]   (default: the Stocky one, else the first)"""
import json, sys
r = json.load(open(sys.argv[1]))
want = sys.argv[3] if len(sys.argv) > 3 else 'Stocky'
u = next((u for u in r['units'] if want in u['name']), r['units'][0])
with open(sys.argv[2], 'w') as f:
    f.write(f'-- {u["name"]} ({u["unit_id"]}): {u["chains"]} chains x {u["bones_per_chain"]} bones\nreturn {{\n')
    for ch in u['rest']:
        f.write('  {' + ', '.join('{%s}' % ','.join(str(x) for x in p) for p in ch) + '},\n')
    f.write('  tails = {\n')
    for t in u.get('tails', []):
        f.write('    {' + ', '.join('{%s}' % ','.join(str(x) for x in p) for p in t['rest']) + '},\n')
    f.write('  },\n}\n')
print('dress_rest:', u['name'], '->', sys.argv[2])
