import numpy as np, collections, sys
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
rows=[l.split() for l in open('~/.cache/hd2-dress/poserec_thumbsup.txt') if not l.startswith('#')]
fr=collections.defaultdict(dict)
for r in rows: fr[int(r[0])][r[2]]=np.array(list(map(float,r[3:15])))
frames=[f for f in sorted(fr) if 'root' in fr[f] and 'hips' in fr[f]]
def local(f, n):
    R=fr[f]['root']; o=R[0:3]; X,Y,Z=R[3:6],R[6:9],R[9:12]
    p=fr[f][n][0:3]-o; return np.array([p@X, p@Y, p@Z])
hz=np.array([local(f,'hips')[2] for f in frames])
lk=np.array([local(f,'l_knee') for f in frames]); rk=np.array([local(f,'r_knee') for f in frames])
def thigh_fwd(side):
    return np.array([np.degrees(np.arctan2(*( (local(f,side+'_knee')-local(f,side+'_thigh'))[[1]].tolist() + [-(local(f,side+'_knee')-local(f,side+'_thigh'))[2]] ))) for f in frames])
lfw, rfw = thigh_fwd('l'), thigh_fwd('r')
dt=40.0/len(frames); t=np.arange(len(frames))*dt
base=np.median(hz[:60]); low=np.where(hz<base-0.10)[0]
print('standing hip height %.2f m; lowest %.2f m (drop %.2f m)'%(base,hz.min(),base-hz.min()))
if len(low): print('emote (hips >10 cm lower): %.1f-%.1f s'%(t[low[0]],t[low[-1]]))
print('left thigh forward swing max %.0f deg, right %.0f deg'%(lfw.max(), rfw.max()))
lv=np.linalg.norm(np.diff(lk,axis=0),axis=1)/dt; rv=np.linalg.norm(np.diff(rk,axis=0),axis=1)/dt
print('peak knee speed: left %.2f m/s, right %.2f m/s; per frame %.1f / %.1f cm'%(lv.max(), rv.max(), lv.max()*dt*100, rv.max()*dt*100))
# hips rotation: pitch of hips 'up' axis relative to root up, over the emote
def hip_axes(f):
    R=fr[f]['root']; X,Y,Z=R[3:6],R[6:9],R[9:12]; H=fr[f]['hips']
    return [np.array([a@X,a@Y,a@Z]) for a in (H[3:6],H[6:9],H[9:12])]
ax0=[hip_axes(f) for f in frames]
rest=ax0[0]
ang=[np.degrees(np.arccos(np.clip(sum(a[i]@rest[i] for i in range(3))/3*1.5-0.5,-1,1))) for a in ax0]
print('hips rotation away from standing, max %.0f deg'%max(ang))
fig,ax=plt.subplots(1,2,figsize=(15,5.5))
ax[0].plot(t,hz,label='hips height (m)',lw=2); ax[0].plot(t,lfw/100,label='left thigh forward (deg / 100)'); ax[0].plot(t,rfw/100,label='right thigh forward (deg / 100)')
ax[0].plot(t,np.array(ang)/100,label='hips rotation (deg / 100)',alpha=0.7)
ax[0].set_xlabel('seconds'); ax[0].legend(fontsize=8); ax[0].set_title('Thumbs-up emote: hips and thighs over time'); ax[0].grid(alpha=0.3)
pick=[0]+([low[0], low[len(low)//2], low[-1], min(low[-1]+90,len(frames)-1)] if len(low) else [])
cols=['k','b','r','g','m']
for ci,i in enumerate(pick):
    f=frames[i]; P=np.array([local(f,n) for n in ('l_foot','l_knee','l_thigh','hips','r_thigh','r_knee','r_foot')])
    ax[1].plot(P[:3,1],P[:3,2],'-o',color=cols[ci],label=f't={t[i]:.1f}s'); ax[1].plot(P[4:,1],P[4:,2],'--o',color=cols[ci],ms=3)
    ax[1].plot([P[2,1],P[3,1],P[4,1]],[P[2,2],P[3,2],P[4,2]],':',color=cols[ci])
ax[1].set_aspect('equal'); ax[1].set_xlabel('forward (m)'); ax[1].set_ylabel('up (m)'); ax[1].legend(fontsize=8); ax[1].grid(alpha=0.3)
ax[1].set_title('Side view (left leg solid, right dashed): standing, start, middle, end, after')
plt.tight_layout(); plt.savefig('/tmp/emote_plot.png',dpi=85)
