"""Background jobs: the slow steps (build, archive scan, preview render, reading the diver skeleton) run in a SEPARATE
Blender process, so the author's session stays responsive and HD2SDK's state in it (open archives, active patch) is
never touched. Output lines stream into the panel; one job at a time."""
import bpy, subprocess, threading, collections, os, sys, time

_job = None


class Job:
    def __init__(self, kind, cmd, on_done, env=None, log_path=None):
        self.kind, self.cmd, self.on_done = kind, cmd, on_done
        self.lines = collections.deque(maxlen=4000); self.rc = None; self.t0 = time.time()
        self.log_path = log_path; self.cancelled = False
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)       # Windows: no console window pops up
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                     encoding='utf-8', errors='replace', env=env, creationflags=flags)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout: self.lines.append(line.rstrip('\n'))
        self.rc = self.proc.wait()


def running(): return _job is not None and _job.rc is None


def current(): return _job


def blender_cmd(script, args, blend=None):
    cmd = [bpy.app.binary_path, '-b']
    if blend: cmd.append(blend)
    return cmd + ['--python', script, '--'] + list(args)


def start(kind, cmd, on_done, env_extra=None, log_path=None):
    """on_done(rc, lines) runs in Blender's main thread when the process ends."""
    global _job
    if running(): raise RuntimeError(f'another job is running ({_job.kind}): wait or press Cancel')
    env = dict(os.environ); env.update(env_extra or {})
    env['PYTHONIOENCODING'] = 'utf-8'
    _job = Job(kind, cmd, on_done, env, log_path)
    bpy.app.timers.register(_poll, first_interval=0.3)
    return _job


def cancel():
    if running():
        _job.cancelled = True; _job.proc.kill()


def interesting(lines, keys=('UNIT', 'BUILT', 'INSTALLED', 'ARCHIVES', 'PREP', 'PREVIEW', 'REST', 'WARNING', 'Error',
                             'error', 'refusing', 'VALIDATION', 'unknown', 'needs', 'no vertices', 'missing', 'SystemExit',
                             'not found', 'exists')):
    return [l for l in lines if any(k in l for k in keys) and not l.startswith('[HD2SDK')]


def _poll():
    j = _job
    if j is None: return None
    wm = bpy.context.window_manager
    sc = wm if hasattr(wm, 'hd2dress_ui') else None
    if sc is not None:
        p = wm.hd2dress_ui
        p.job_lines = '\n'.join(interesting(list(j.lines))[-6:])
        p.job_elapsed = time.time() - j.t0
    for w in bpy.context.window_manager.windows:
        for a in w.screen.areas:
            if a.type == 'VIEW_3D': a.tag_redraw()
    if j.rc is None: return 0.3
    if j.log_path:
        try: open(j.log_path, 'w', encoding='utf-8').write('\n'.join(j.lines))
        except OSError: pass
    try: j.on_done(j.rc, list(j.lines))
    except Exception as e:
        import traceback; traceback.print_exc()
        if sc is not None: wm.hd2dress_ui.status = f'{j.kind}: {e}'
    if sc is not None: wm.hd2dress_ui.job_kind = ''
    return None
