"""Find the Helldivers 2 data folder on Windows or Linux. Order: the HD2_DATA environment variable, then every Steam
library (Windows registry SteamPath + libraryfolders.vdf; Linux default locations incl. Flatpak). Returns the path
with a trailing slash (HD2SDK appends file names straight onto it)."""
import os, sys, re


def steam_libraries():
    roots = []
    if sys.platform.startswith('win'):
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
                roots.append(winreg.QueryValueEx(k, 'SteamPath')[0])
        except Exception:
            pass
        roots += [r'C:\Program Files (x86)\Steam', r'C:\Program Files\Steam']
    else:
        roots += [os.path.expanduser('~/.local/share/Steam'), os.path.expanduser('~/.steam/steam'),
                  os.path.expanduser('~/.var/app/com.valvesoftware.Steam/.local/share/Steam')]
    libs = []
    for r in roots:
        if r not in libs: libs.append(r)
        try:
            txt = open(os.path.join(r, 'steamapps', 'libraryfolders.vdf'), encoding='utf-8', errors='ignore').read()
            for p in re.findall(r'"path"\s*"([^"]+)"', txt):
                p = p.replace('\\\\', '\\')
                if p not in libs: libs.append(p)
        except Exception:
            pass
    return libs


def is_game_data(d):
    """The game's data folder: today's slim install has bundle_database.data + bundles.*.nxa; older ones loose archives."""
    return bool(d) and any(os.path.exists(os.path.join(d, f)) for f in ('bundle_database.data', '9ba626afa44a3aa3', '18235e0c9ec0e636'))


def game_data():
    cands = [os.environ['HD2_DATA']] if os.environ.get('HD2_DATA') else []
    cands += [os.path.join(lib, 'steamapps', 'common', 'Helldivers 2', 'data') for lib in steam_libraries()]
    for d in cands:
        if is_game_data(d):
            d = d.replace('\\', '/')
            return d if d.endswith('/') else d + '/'
    raise SystemExit('Helldivers 2 data folder not found: set HD2_DATA to ...\\Helldivers 2\\data')
