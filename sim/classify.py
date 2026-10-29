import json, math, sys
d = json.load(open(sys.argv[1]))
def stats(a):
    F = a['frames']; n = len(F)
    hz = [f['hips'][2] for f in F]; head = [f['head'][2] for f in F]
    lf = [f['l_foot'] for f in F]; rf = [f['r_foot'] for f in F]
    # horizontal foot travel relative to hips
    def rel(fs): return [math.hypot(fs[i][0]-F[i]['hips'][0], fs[i][1]-F[i]['hips'][1]) for i in range(n)]
    stride = max(max(p[1] for p in lf)-min(p[1] for p in lf), max(p[1] for p in rf)-min(p[1] for p in rf),
                 max(p[0] for p in lf)-min(p[0] for p in lf), max(p[0] for p in rf)-min(p[0] for p in rf))
    lift = max(max(p[2] for p in lf), max(p[2] for p in rf)) - min(min(p[2] for p in lf), min(p[2] for p in rf))
    cyc = math.dist(F[0]['l_foot'][:3], F[-1]['l_foot'][:3]) + math.dist(F[0]['r_foot'][:3], F[-1]['r_foot'][:3])
    # thigh swing: knee forward/back relative to hips (along hips' facing is unknown -> use range)
    return dict(n=n, L=a['length'], hips=sum(hz)/n, hipsmin=min(hz), head=sum(head)/n, stride=stride, lift=lift, cyc=cyc)
rows = []
for a in d['anims']:
    s = stats(a); s.update(id=a['id'], st=a['state']); rows.append(s)
rows.sort(key=lambda r: (r['st'], r['id']))
for r in rows:
    tag = []
    if r['head'] < 0.6: tag.append('PRONE?')
    elif r['hips'] < 0.7: tag.append('CROUCH?')
    if r['stride'] > 0.3 and r['cyc'] < 0.05 and r['L'] > 0.3: tag.append('CYCLE')
    if r['stride'] > 0.6: tag.append('BIG')
    print(f"st {r['st']:3} {r['id']:>20} L {r['L']:5.2f} hips {r['hips']:.2f} head {r['head']:.2f} stride {r['stride']:.2f} lift {r['lift']:.2f} cyc {r['cyc']:.3f} {' '.join(tag)}")
