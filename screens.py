"""
Ecrans et barres des taches (multi-ecran).

La barre de l'ecran principal est la fenetre "Shell_TrayWnd" ; celle de chaque autre ecran est une
"Shell_SecondaryTrayWnd" (si Windows affiche la barre des taches sur tous les ecrans).
Un ecran est designe par son nom de peripherique (ex. "\\\\.\\DISPLAY2") ; "" = ecran principal.
"""
import ctypes
import re
from ctypes import wintypes

user32 = ctypes.windll.user32

MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", ctypes.c_wchar * 32)]


MONITORENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                     ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
_FindWindowW = ctypes.WINFUNCTYPE(wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR)(("FindWindowW", user32))
_FindWindowExW = ctypes.WINFUNCTYPE(wintypes.HWND, wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR,
                                    wintypes.LPCWSTR)(("FindWindowExW", user32))
_MonitorFromWindow = ctypes.WINFUNCTYPE(wintypes.HANDLE, wintypes.HWND, wintypes.DWORD)(
    ("MonitorFromWindow", user32))
_GetMonitorInfoW = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(MONITORINFOEXW))(
    ("GetMonitorInfoW", user32))
_EnumDisplayMonitors = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HDC, ctypes.c_void_p, MONITORENUMPROC,
                                          wintypes.LPARAM)(("EnumDisplayMonitors", user32))


def monitor_info(hmon):
    mi = MONITORINFOEXW()
    mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
    if not hmon or not _GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    return mi


def monitor_of(hwnd):
    return _MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST) if hwnd else None


def _taskbar_windows():
    main = _FindWindowW("Shell_TrayWnd", None)
    wins = [main] if main else []
    h = None
    while True:
        h = _FindWindowExW(None, h, "Shell_SecondaryTrayWnd", None)
        if not h:
            break
        wins.append(h)
    return wins


def monitors():
    """Tous les ecrans : liste de dicts device, primary, width, height, left, taskbar (hwnd ou None).
    Ecran principal d'abord, puis de gauche a droite."""
    bars = {}
    for tb in _taskbar_windows():
        mi = monitor_info(monitor_of(tb))
        if mi is not None:
            bars.setdefault(mi.szDevice, tb)
    found = []

    def cb(hmon, hdc, rect, data):
        mi = monitor_info(hmon)
        if mi is not None:
            r = mi.rcMonitor
            found.append({"device": mi.szDevice, "primary": bool(mi.dwFlags & MONITORINFOF_PRIMARY),
                          "width": r.right - r.left, "height": r.bottom - r.top, "left": r.left,
                          "top": r.top, "taskbar": bars.get(mi.szDevice)})
        return True
    _EnumDisplayMonitors(None, None, MONITORENUMPROC(cb), 0)
    found.sort(key=lambda m: (not m["primary"], m["left"], m["top"]))
    return found


def screen_number(device):
    m = re.search(r"(\d+)\s*$", device or "")
    return int(m.group(1)) if m else None


def monitor_label(m):
    n = screen_number(m["device"])
    text = "Écran %s — %d × %d" % (n if n is not None else "?", m["width"], m["height"])
    if m["primary"]:
        text += " (principal)"
    if not m["taskbar"]:
        text += " — sans barre des tâches"
    return text


def find_taskbar(device=""):
    """Barre des taches de l'ecran demande ; celle de l'ecran principal si absente."""
    wins = _taskbar_windows()
    if device:
        for tb in wins:
            mi = monitor_info(monitor_of(tb))
            if mi is not None and mi.szDevice == device:
                return tb
    return wins[0] if wins else None
