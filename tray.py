"""
Icone dans la zone de notification (a cote de l'horloge), sans dependance externe.

La fenetre cachee qui recoit les clics est creee dans le thread de Tk : la boucle de messages de
Tcl distribue aussi ses messages, donc les rappels s'executent dans le thread de l'interface.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", ctypes.c_uint),
                ("uFlags", ctypes.c_uint), ("uCallbackMessage", ctypes.c_uint), ("hIcon", wintypes.HICON),
                ("szTip", ctypes.c_wchar * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", ctypes.c_wchar * 256), ("uVersion", ctypes.c_uint),
                ("szInfoTitle", ctypes.c_wchar * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]


user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, ctypes.c_uint, ctypes.c_int,
                              ctypes.c_int, ctypes.c_uint]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.RegisterWindowMessageW.restype = ctypes.c_uint
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 0x1, 0x2, 0x4, 0x10, 0x80
NIIF_INFO, NIIF_WARNING, NIIF_USER, NIIF_LARGE_ICON = 0x1, 0x2, 0x4, 0x20
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
NOTIFYICON_VERSION_4 = 4
WM_APP = 0x8000
WM_CONTEXTMENU, WM_LBUTTONUP, WM_RBUTTONUP = 0x007B, 0x0202, 0x0205
NIN_SELECT, NIN_KEYSELECT = 0x0400, 0x0401
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
SM_CXSMICON, SM_CYSMICON = 49, 50
CALLBACK_MSG = WM_APP + 1
CLASS_NAME = "HATaskbarTray"


def cursor_pos():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


class TrayIcon:
    """on_left() : clic gauche ; on_menu(x, y) : clic droit (position du curseur, en pixels physiques)."""

    def __init__(self, icon_path, tip, on_left, on_menu, on_hotkey=None):
        self.on_left, self.on_menu, self.on_hotkey = on_left, on_menu, on_hotkey
        self.hotkeys = set()
        self.tip = tip
        self.added = False
        self.taskbar_created = 0   # des messages arrivent pendant CreateWindowExW
        self._proc = WNDPROC(self._wndproc)        # garde une reference : sinon le rappel est libere
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = CLASS_NAME
        user32.RegisterClassW(ctypes.byref(wc))     # echoue sans gravite si deja enregistree
        self.hwnd = user32.CreateWindowExW(0, CLASS_NAME, "HA Taskbar tray", 0, 0, 0, 0, 0,
                                           None, None, hinst, None)
        self.taskbar_created = user32.RegisterWindowMessageW("TaskbarCreated")
        self.hicon = user32.LoadImageW(None, icon_path, IMAGE_ICON, user32.GetSystemMetrics(SM_CXSMICON),
                                       user32.GetSystemMetrics(SM_CYSMICON), LR_LOADFROMFILE) if icon_path else None
        self.add()

    def _data(self):
        d = NOTIFYICONDATAW()
        d.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        d.hWnd = self.hwnd
        d.uID = 1
        d.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP
        d.uCallbackMessage = CALLBACK_MSG
        d.hIcon = self.hicon
        d.szTip = self.tip[:127]
        return d

    def add(self):
        if not self.hwnd:
            return
        d = self._data()
        self.added = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(d)))
        if self.added:
            d.uVersion = NOTIFYICON_VERSION_4
            shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(d))

    def set_tip(self, tip):
        if tip == self.tip:
            return
        self.tip = tip
        if self.added:
            d = self._data()
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(d))

    def notify(self, title, text, warning=False):
        """Notification Windows (bulle / centre de notifications) au nom de HA Taskbar."""
        if not self.added:
            return False
        d = self._data()
        d.uFlags |= NIF_INFO
        d.szInfoTitle = (title or "")[:63]
        d.szInfo = (text or " ")[:255]
        d.dwInfoFlags = NIIF_WARNING if warning else (NIIF_USER | NIIF_LARGE_ICON if self.hicon else NIIF_INFO)
        d.hBalloonIcon = self.hicon
        return bool(shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(d)))

    # ---------------- raccourcis clavier globaux (WM_HOTKEY recu par la fenetre cachee)
    def register_hotkey(self, hid, mods, vk):
        if not self.hwnd:
            return False
        ok = bool(user32.RegisterHotKey(self.hwnd, hid, mods | MOD_NOREPEAT, vk))
        if ok:
            self.hotkeys.add(hid)
        return ok

    def clear_hotkeys(self):
        for hid in list(self.hotkeys):
            user32.UnregisterHotKey(self.hwnd, hid)
        self.hotkeys.clear()

    def remove(self):
        self.clear_hotkeys()
        if self.added:
            d = self._data()
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(d))
            self.added = False
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = None
        if self.hicon:
            user32.DestroyIcon(self.hicon)
            self.hicon = None

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == CALLBACK_MSG:
            event = lparam & 0xFFFF          # NOTIFYICON_VERSION_4 : evenement dans le mot bas
            try:
                if event in (NIN_SELECT, NIN_KEYSELECT):   # (WM_LBUTTONUP arrive aussi : ignore)
                    self.on_left()
                elif event == WM_CONTEXTMENU:
                    self.on_menu(*cursor_pos())
            except Exception:
                pass
            return 0
        if msg == WM_HOTKEY:
            try:
                if self.on_hotkey:
                    self.on_hotkey(int(wparam))
            except Exception:
                pass
            return 0
        if msg == self.taskbar_created and self.taskbar_created:
            self.add()                        # l'Explorateur a redemarre : on remet l'icone
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
