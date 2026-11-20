"""
Ou sont les boutons de Windows sur la barre des taches (Demarrer, recherche, applications, widgets,
zone de notification) ? Lu avec UI Automation (l'accessibilite de Windows), sans dependance externe,
dans un thread qui relit la barre toutes les 1,5 s. Sert a ne pas recouvrir ces boutons : les elements
de HA Taskbar qui n'ont plus la place passent dans un bouton « +N ».
"""
import ctypes
import threading
import time
from ctypes import POINTER, byref, c_void_p, wintypes

ole32 = ctypes.windll.ole32
oleaut32 = ctypes.windll.oleaut32

TREE_SCOPE_DESCENDANTS = 4
# Classes UI Automation des boutons de la barre des taches de Windows 11 (et de Windows 10)
BUTTON_CLASSES = ("ToggleButton", "Taskbar.TaskListButtonAutomationPeer", "TrayNotifyWnd", "Start",
                  "TrayButton", "MSTaskListWClass")
BUTTON_PREFIXES = ("SystemTray.",)


class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]


def _guid(s):
    g = _GUID()
    ole32.CLSIDFromString(ctypes.c_wchar_p(s), byref(g))
    return g


CLSID_CUIAutomation = _guid("{ff48dba4-60ef-4201-aa87-54103eef594e}")
IID_IUIAutomation = _guid("{30cbe57d-d9d0-452a-ab13-7ac5ac4825ee}")


def _vcall(obj, idx, *argtypes):
    """Methode n° idx de l'interface COM obj (table virtuelle)."""
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtbl[idx])
    return lambda *a: fn(obj, *a)


def _release(obj):
    if obj:
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
        ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vtbl[2])(obj)


def _bstr(el, idx):
    b = c_void_p()
    try:
        _vcall(el, idx, POINTER(c_void_p))(byref(b))
    except OSError:
        return ""
    if not b.value:
        return ""
    s = ctypes.wstring_at(b.value)
    oleaut32.SysFreeString(b)
    return s


class TaskbarButtons:
    """Thread : rectangles (gauche, droite) des boutons de Windows sur la barre des taches suivie."""

    def __init__(self, get_hwnd, interval=1.5):
        self.get_hwnd = get_hwnd          # fonction : barre des taches a lire (hwnd)
        self.interval = interval
        self.spans = None                 # [(gauche, droite)] en pixels ecran ; None = inconnu
        self.stop_ev = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.stop_ev.set()

    def _run(self):
        ole32.CoInitializeEx(None, 2)
        uia = c_void_p()
        if ole32.CoCreateInstance(byref(CLSID_CUIAutomation), None, 1, byref(IID_IUIAutomation), byref(uia)) != 0:
            return                         # UI Automation indisponible : pas d'evitement
        cond = c_void_p()
        _vcall(uia, 21, POINTER(c_void_p))(byref(cond))           # CreateTrueCondition
        while not self.stop_ev.is_set():
            try:
                self.spans = self._read(uia, cond)
            except Exception:
                self.spans = None
            self.stop_ev.wait(self.interval)

    def _read(self, uia, cond):
        hwnd = self.get_hwnd()
        if not hwnd:
            return None
        root, arr = c_void_p(), c_void_p()
        _vcall(uia, 6, wintypes.HWND, POINTER(c_void_p))(hwnd, byref(root))      # ElementFromHandle
        try:
            _vcall(root, 6, ctypes.c_int, c_void_p, POINTER(c_void_p))(TREE_SCOPE_DESCENDANTS, cond, byref(arr))
            n = ctypes.c_int()
            _vcall(arr, 3, POINTER(ctypes.c_int))(byref(n))                       # get_Length
            spans = []
            for i in range(n.value):
                el = c_void_p()
                _vcall(arr, 4, ctypes.c_int, POINTER(c_void_p))(i, byref(el))     # GetElement
                try:
                    cls = _bstr(el, 30)                                           # get_CurrentClassName
                    if cls in BUTTON_CLASSES or cls.startswith(BUTTON_PREFIXES):
                        r = wintypes.RECT()
                        _vcall(el, 43, POINTER(wintypes.RECT))(byref(r))          # get_CurrentBoundingRectangle
                        if r.right > r.left:
                            spans.append((r.left, r.right))
                finally:
                    _release(el)
            return spans
        finally:
            _release(arr)
            _release(root)


def free_width(spans, side, anchor, margin=6):
    """Largeur disponible pour une zone ancree a `anchor` (bord gauche de la zone gauche, bord droit de
    la zone droite) avant le premier bouton de Windows rencontre. None = pas de limite connue."""
    if not spans:
        return None
    for left, right in spans:
        if left < anchor < right:
            return None                    # la zone commence sur un bouton : on ne peut rien eviter
    if side == "left":
        ahead = [left for left, _r in spans if left >= anchor]
        return (min(ahead) - margin - anchor) if ahead else None
    ahead = [right for _l, right in spans if right <= anchor]
    return (anchor - max(ahead) - margin) if ahead else None


def wait_ready(tb, timeout=3.0):
    """Pour les tests : attend la premiere lecture."""
    t0 = time.time()
    while tb.spans is None and time.time() - t0 < timeout:
        time.sleep(0.05)
    return tb.spans
