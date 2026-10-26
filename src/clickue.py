"""
Clickue for Windows
-------------------
Scheduled clicks (with optional random delays) and screen watchers that click when a
picture disappears or appears, multi-step jobs, active hours, limits, hotkeys, alerts.

Data (settings, jobs, logs, backups) lives in %APPDATA%\\Clickue, so it survives moving
or reinstalling the program. Data from the old "Scheduled AutoClicker" is moved over
automatically the first time Clickue starts.

Needs Python 3 + pillow, pystray, opencv-python-headless, numpy ("Start Clickue.bat"
installs them).  Run with:  pythonw clickue.py   (add --minimized to start hidden)
"""

import base64
import copy
import io
import ctypes
import json
import logging
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from datetime import timedelta
from logging.handlers import RotatingFileHandler

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog

try:
    from PIL import Image, ImageDraw, ImageTk, ImageGrab
    Image.MAX_IMAGE_PIXELS = 60_000_000      # refuse "decompression bomb" pictures in imports
    HAVE_PIL = True
except Exception:
    HAVE_PIL = False
try:
    import pystray
    HAVE_TRAY = HAVE_PIL
except Exception:
    HAVE_TRAY = False
try:
    import numpy as np
    import cv2
    HAVE_CV = HAVE_PIL
except Exception:
    HAVE_CV = False

APP_NAME = "Clickue"
APP_ID = "Clickue"
OLD_APP_ID = "ScheduledAutoClicker"      # previous name - data is migrated from here
VERSION = "4.6.1"
REPO_URL = "https://github.com/jnssylvest/clickue"
GUIDE_URL = REPO_URL + "/blob/main/docs/GUIDE.md"      # the complete guide (☰ Menu)
DISCLOSURE = ("Clickue is vibe-coded and was developed with substantial AI assistance. Caution "
              "was taken during development, but AI-assisted development does not guarantee "
              "bug-free or secure software. Review the source and use normal precautions. Test "
              "automations safely, protect notification credentials, and avoid unattended use "
              "for consequential actions.")

IS_WIN = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)
PROGRAM_PATH = sys.executable if FROZEN else os.path.abspath(__file__)
PROGRAM_DIR = os.path.dirname(PROGRAM_PATH)

# Portable mode: a file named "portable" or "portable.txt" next to the program keeps all
# data in a "ClickueData" folder beside it (run from a USB stick, leave nothing behind).
PORTABLE = any(os.path.exists(os.path.join(PROGRAM_DIR, n)) for n in ("portable", "portable.txt"))
if IS_WIN:
    _BASE = os.environ.get("APPDATA") or os.path.expanduser("~")
    DATA_DIR = os.path.join(_BASE, APP_ID)
    OLD_DATA_DIR = os.path.join(_BASE, OLD_APP_ID)
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"), "." + APP_ID)
    OLD_DATA_DIR = os.path.join(os.path.expanduser("~"), "." + OLD_APP_ID)
if PORTABLE:
    DATA_DIR = os.path.join(PROGRAM_DIR, "ClickueData")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
JOBS_PATH = os.path.join(DATA_DIR, "jobs.json")
LOG_PATH = os.path.join(DATA_DIR, "clickue.log")
TESTS_PATH = os.path.join(DATA_DIR, "test_history.json")
MAX_TEST_HISTORY = 200
OLD_CONFIG = os.path.join(PROGRAM_DIR, "autoclicker_config.json")   # v1 location

MAX_UI_LOG_LINES = 800
RUNTIME_KEYS = ("base_next", "next_run", "deadline", "test_at", "test_deadline",
                "next_check", "last_check", "last_seen", "miss_count", "watch_state",
                "armed", "pending_click_at", "pending_since", "watch_scale", "watch_note",
                "wtest_at", "wtest_deadline", "wtest_click", "once_logged", "run_clicks",
                "found_xy", "pointer_logged", "issue_count", "issue_since", "screen_sig",
                "settle_until", "first_miss_at", "click_planned_at",
                "planned_run")

# ---------------------------------------------------------------- Windows API
if IS_WIN:
    import ctypes.wintypes as wt
    import winreg

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    try:  # real pixel coordinates on scaled displays
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

    user32.OpenInputDesktop.restype = wt.HANDLE
    user32.OpenInputDesktop.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    user32.SwitchDesktop.argtypes = [wt.HANDLE]
    user32.CloseDesktop.argtypes = [wt.HANDLE]
    user32.GetParent.restype = wt.HWND
    user32.GetParent.argtypes = [wt.HWND]
    kernel32.GetTickCount.restype = wt.DWORD
    kernel32.CreateMutexW.restype = wt.HANDLE
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]

    user32.WindowFromPoint.restype = wt.HWND
    user32.WindowFromPoint.argtypes = [wt.POINT]
    user32.GetAncestor.restype = wt.HWND
    user32.GetAncestor.argtypes = [wt.HWND, wt.UINT]
    user32.GetWindowTextLengthW.argtypes = [wt.HWND]
    user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.ClientToScreen.argtypes = [wt.HWND, ctypes.POINTER(wt.POINT)]
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsIconic.argtypes = [wt.HWND]
    user32.IsWindow.argtypes = [wt.HWND]
    user32.GetWindowThreadProcessId.restype = wt.DWORD
    user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    user32.GetForegroundWindow.restype = wt.HWND
    user32.SetForegroundWindow.argtypes = [wt.HWND]
    user32.BringWindowToTop.argtypes = [wt.HWND]
    user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
    user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
    user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, ctypes.c_int, wt.UINT]
    EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.EnumWindows.argtypes = [EnumWindowsProc, wt.LPARAM]

MOUSE_FLAGS = {
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}


def get_cursor():
    if not IS_WIN:
        return (0, 0)
    pt = wt.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return (pt.x, pt.y)


CURSOR_LOCK = threading.Lock()   # grab_screen(move_cursor=True) and do_click never overlap
VK_ESCAPE = 0x1B


def key_down(vk):
    """Is this key held right now (anywhere, whichever window has focus)?"""
    if not IS_WIN:
        return False
    try:
        return bool(user32.GetAsyncKeyState(int(vk)) & 0x8000)
    except Exception:
        return False


def screen_available():
    """False when the session is locked, at the login screen, or RDP-disconnected."""
    if not IS_WIN:
        return False
    h = user32.OpenInputDesktop(0, False, 0x0100)  # DESKTOP_SWITCHDESKTOP
    if not h:
        return False
    ok = user32.SwitchDesktop(h)
    user32.CloseDesktop(h)
    return bool(ok)


def idle_seconds():
    """Seconds since the last real mouse/keyboard input in this session."""
    if not IS_WIN:
        return 9999.0
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(lii)
    if not user32.GetLastInputInfo(ctypes.byref(lii)):
        return 9999.0
    return ((kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


HUMAN_SPEEDS = {"slow": 1.6, "normal": 1.0, "fast": 0.55}   # 4.5.6: movement time factor


def human_path(x0, y0, x1, y1, speed="normal", rnd=None):
    """Points for moving the mouse like a person (4.5.6): a slightly curved path (Bézier with
    a random bend), quick in the middle and slow at both ends (ease in/out), sometimes a tiny
    overshoot that's corrected, with a little jitter. Returns [(t seconds, x, y)], ending
    exactly on (x1, y1). Pure, so it's tested without a mouse."""
    import math
    rnd = rnd or random.Random()
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 2:
        return [(0.0, int(x1), int(y1))]
    f = HUMAN_SPEEDS.get(speed, 1.0)
    # Fitts-like: longer moves take longer, but not proportionally (0.15 - 1.1 s)
    dur = f * min(1.1, 0.12 + 0.11 * math.log2(1 + dist / 12)) * rnd.uniform(0.85, 1.15)
    bend = rnd.uniform(-0.18, 0.18) * dist
    nx, ny = (-dy / dist, dx / dist)
    cx, cy = x0 + dx * 0.5 + nx * bend, y0 + dy * 0.5 + ny * bend
    over = rnd.random() < 0.3 and dist > 120
    ox, oy = (x1 + dx / dist * rnd.uniform(3, 9), y1 + dy / dist * rnd.uniform(3, 9)) \
        if over else (x1, y1)
    n = max(6, min(90, int(dur / 0.012)))
    pts = []
    for i in range(1, n + 1):
        u = i / n
        e = u * u * (3 - 2 * u)                       # ease in / out
        bx = (1 - e) ** 2 * x0 + 2 * (1 - e) * e * cx + e * e * ox
        by = (1 - e) ** 2 * y0 + 2 * (1 - e) * e * cy + e * e * oy
        j = 1.2 * (1 - abs(2 * u - 1))                # jitter, none at the ends
        pts.append((dur * u, round(bx + rnd.uniform(-j, j)), round(by + rnd.uniform(-j, j))))
    if over:
        t = dur
        for k in range(1, 6):
            t += 0.016
            pts.append((t, round(ox + (x1 - ox) * k / 5), round(oy + (y1 - oy) * k / 5)))
    pts[-1] = (pts[-1][0], int(x1), int(y1))
    return pts


def glide(x, y, speed="normal", stop=None):
    """Move the real mouse to (x, y) along human_path. Returns False if it couldn't move.
    Bounded (at most ~1.3 s x speed); `stop()` true ends it early."""
    if not IS_WIN:
        return False
    x0, y0 = get_cursor()
    start = time.time()
    for t, px, py in human_path(x0, y0, x, y, speed):
        if stop and stop():
            return False
        wait = start + t - time.time()
        if wait > 0:
            time.sleep(min(wait, 0.05))
        if not user32.SetCursorPos(int(px), int(py)):
            return False
    return True


def do_click(x, y, button="left", clicks=1, restore_cursor=True, human=None):
    """Click at (x, y). human = None (jump there, as always) or a speed ("slow" / "normal" /
    "fast") to move the mouse there like a person first (4.5.6)."""
    if not IS_WIN:
        return False, "this program only clicks on Windows"
    with CURSOR_LOCK:
        return _do_click(x, y, button, clicks, restore_cursor, human)


def _do_click(x, y, button, clicks, restore_cursor, human=None):
    old = get_cursor()
    if human:
        glide(x, y, human)
        time.sleep(random.uniform(0.04, 0.12))         # a person settles before clicking
    if not user32.SetCursorPos(int(x), int(y)):
        return False, "could not move the mouse (no active screen)"
    time.sleep(0.05)
    if get_cursor() != (int(x), int(y)):
        return False, "mouse did not reach the target position"
    down, up = MOUSE_FLAGS.get(button, MOUSE_FLAGS["left"])
    for i in range(max(1, int(clicks))):
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.03)
        user32.mouse_event(up, 0, 0, 0, 0)
        if i < clicks - 1:
            time.sleep(0.08)
    if restore_cursor:
        time.sleep(0.05)
        if human:
            glide(old[0], old[1], human)
        user32.SetCursorPos(*old)
    return True, "clicked"


def mouse_style(settings, job=None, step=None):
    """How to get the mouse to a click: None = jump (classic), or a speed for moving like a
    person. A step's own choice wins, then the job's, then Preferences → Clicking."""
    for src in (step, job):
        v = (src or {}).get("human_move")
        if v is True:
            return settings.get("human_speed", "normal")
        if v is False:
            return None
    return settings.get("human_speed", "normal") if settings.get("human_move") else None


# ---- window-anchored targets ------------------------------------------------
IGNORED_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def screen_size():
    if not IS_WIN:
        return (1920, 1080)
    return (user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def win_text(h):
    n = user32.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(h, buf, n + 1)
    return buf.value


def win_class(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(h, buf, 256)
    return buf.value


def is_own_window(h):
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value == os.getpid()


def window_at(x, y):
    """Top-level window under a screen point."""
    h = user32.WindowFromPoint(wt.POINT(int(x), int(y)))
    return user32.GetAncestor(h, 2) if h else None   # GA_ROOT


def own_on_top(x, y):
    """4.6.1: is one of Clickue's own windows the window actually seen at this screen point
    (in front of everything else there)? A Clickue window that is open but behind another
    window doesn't count."""
    try:
        h = window_at(x, y)
        return bool(h) and is_own_window(h)
    except Exception:
        return False


def same_window(a, b):
    if not a or not b:
        return False
    return a == b or user32.GetAncestor(a, 3) == user32.GetAncestor(b, 3)  # GA_ROOTOWNER


def client_origin(h):
    """(left, top, width, height) of a window's inside area, in screen pixels."""
    r = wt.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(pt))
    return pt.x, pt.y, r.right - r.left, r.bottom - r.top


def virtual_screen():
    """(left, top, width, height) of the whole desktop across all monitors."""
    if IS_WIN:
        try:
            return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
                    user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))
        except Exception:
            pass
    return 0, 0, 1920, 1080


def fit_geometry(geom, min_w=300, min_h=200):
    """Make a saved 'WxH+X+Y' fit on the current screen(s) - the screen size can differ
    between RDP and the console. Returns a geometry string, or '' if it can't be read."""
    import re
    m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", (geom or "").strip())
    if not m:
        return ""
    w, h, x, y = (int(v) for v in m.groups())
    vx, vy, vw, vh = virtual_screen()
    # 4.5.1: keep the size and position exactly as the user left them; only shrink or move
    # a window that no longer fits on the screen(s) (e.g. a smaller remote-desktop screen)
    w = max(min(min_w, vw), min(w, vw))
    h = max(min(min_h, vh), min(h, vh))
    x = min(max(x, vx), vx + vw - w)
    y = min(max(y, vy), vy + vh - h)
    return f"{w}x{h}+{x}+{y}"


def describe_point(x, y):
    """Info about the window under (x, y), or None for desktop/taskbar/nothing."""
    if not IS_WIN:
        return None
    h = window_at(x, y)
    if not h or is_own_window(h) or win_class(h) in IGNORED_CLASSES:
        return None
    title = win_text(h).strip()
    if not title:
        return None
    ox, oy, cw, ch = client_origin(h)
    return dict(window_title=title, window_class=win_class(h), rel_x=x - ox, rel_y=y - oy,
                client_w=cw, client_h=ch)


def find_window(title, cls=""):
    """Visible top-level window whose title matches exactly, or else contains the text."""
    if not IS_WIN or not title:
        return None
    found = []

    def cb(h, _):
        if user32.IsWindowVisible(h) and not is_own_window(h):
            t = win_text(h)
            if t:
                found.append((h, t, win_class(h)))
        return True
    user32.EnumWindows(EnumWindowsProc(cb), 0)
    tl = title.lower()
    for test in (lambda t, c: t == title and (not cls or c == cls),
                 lambda t, c: tl in t.lower() and (not cls or c == cls),
                 lambda t, c: tl in t.lower()):
        for h, t, c in found:
            if test(t, c):
                return h
    return None


def bring_to_front(h):
    if user32.IsIconic(h):
        user32.ShowWindow(h, 9)  # SW_RESTORE
    fg = user32.GetForegroundWindow()
    if fg == h:
        return
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True))
    user32.BringWindowToTop(h)
    user32.SetForegroundWindow(h)
    if attached:
        user32.AttachThreadInput(me, fg_thread, False)
    time.sleep(0.3)


def short_title(t, n=24):
    return t if len(t) <= n else t[:n - 1] + "…"


def resolve_target(job, activate=False, check_cover=True):
    """Where to click right now. Returns (ok, x, y, message)."""
    if job.get("target_mode") == "window" and job.get("window_title"):
        if not IS_WIN:
            return False, 0, 0, "window targets only work on Windows"
        name = short_title(job["window_title"])
        h = find_window(job["window_title"], job.get("window_class", ""))
        if not h:
            return False, 0, 0, f"window \u201c{name}\u201d isn't open"
        if activate and job.get("bring_to_front", True):
            bring_to_front(h)
        elif user32.IsIconic(h):
            return False, 0, 0, f"window \u201c{name}\u201d is minimized"
        ox, oy, cw, ch = client_origin(h)
        rx, ry = int(job.get("rel_x", 0)), int(job.get("rel_y", 0))
        if job.get("scale_with_window") and job.get("client_w") and job.get("client_h") and cw:
            rx = round(rx * cw / job["client_w"])
            ry = round(ry * ch / job["client_h"])
        x, y = ox + rx, oy + ry
        if check_cover:
            w = window_at(x, y)
            if w and is_own_window(w):
                return False, x, y, "the Clickue window is covering the spot"
            if w and not same_window(w, h):
                return False, x, y, (f"\u201c{short_title(win_text(w))}\u201d is covering "
                                     f"\u201c{name}\u201d")
        return True, x, y, ""
    x, y = int(job["x"]), int(job["y"])
    ps = job.get("pick_screen")
    if job.get("scale_with_screen") and ps:
        cw, ch = screen_size()
        if (cw, ch) != tuple(ps) and ps[0] and ps[1]:
            x, y = round(x * cw / ps[0]), round(y * ch / ps[1])
    if check_cover and IS_WIN:
        w = window_at(x, y)
        if w and is_own_window(w):
            return False, x, y, "the Clickue window is covering the spot"
    return True, x, y, ""


# ---- picture matching ------------------------------------------------------
SNAP_SIZES = {"Small": (90, 56), "Medium": (150, 90), "Large": (260, 150)}
MATCH_SCALES = (1.0, 1.25, 0.8, 1.5, 0.67, 1.1, 0.9, 1.75, 0.57, 2.0, 0.5)
STEP_POLL_S = 1.0           # "wait for a picture" steps look this often
STEP_MAX_WAIT_S = 3600      # longest a "wait for a picture" step may wait
MATCH_WHOLE_MIN = 0.65      # whole saved picture
MATCH_CLOSEUP_MIN = 0.62    # close-up around the spot itself


def img_to_b64(img):
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def b64_to_img(text):
    return Image.open(io.BytesIO(base64.b64decode(text))).convert("RGB")


def virtual_origin():
    if not IS_WIN:
        return 0, 0
    return user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)  # SM_X/YVIRTUALSCREEN


def grab_screen(move_cursor=True, _locked=False):
    """Screenshot of all monitors -> (image, (left, top) of the image in screen pixels).
    The mouse is moved out of the way first so hover highlights don't change the picture
    (never at the same time as a click: CURSOR_LOCK)."""
    if move_cursor and IS_WIN and not _locked:
        with CURSOR_LOCK:
            return grab_screen(True, _locked=True)
    vx, vy = virtual_origin()
    old = get_cursor()
    if move_cursor and IS_WIN:
        user32.SetCursorPos(vx, vy)
        time.sleep(0.3)
    try:
        img = ImageGrab.grab(all_screens=True)
    finally:
        if move_cursor and IS_WIN:
            user32.SetCursorPos(*old)
    return img.convert("RGB"), (vx, vy)


def capture_snapshot(x, y, size="Medium"):
    """Picture of the area around (x, y). Returns (image, (spot_x, spot_y) inside it, detail)."""
    w, h = SNAP_SIZES.get(size, SNAP_SIZES["Medium"])
    img, (vx, vy) = grab_screen()
    W, H = img.size
    w, h = min(w, W), min(h, H)
    left = min(max(x - vx - w // 2, 0), W - w)
    top = min(max(y - vy - h // 2, 0), H - h)
    crop = img.crop((left, top, left + w, top + h))
    detail = float(np.asarray(crop.convert("L"), dtype=np.float32).std()) if HAVE_CV else 99.0
    return crop, (x - vx - left, y - vy - top), detail


def _match(S, t):
    """Normalized picture match. Places much flatter (or much busier) than the picture
    are ruled out; otherwise empty areas give false "perfect" scores."""
    t = t.astype(np.float32)
    S = S.astype(np.float32)
    res = cv2.matchTemplate(S, t, cv2.TM_CCOEFF_NORMED)
    th, tw = t.shape
    m1 = cv2.boxFilter(S, -1, (tw, th), normalize=True, borderType=cv2.BORDER_CONSTANT)
    m2 = cv2.boxFilter(S * S, -1, (tw, th), normalize=True, borderType=cv2.BORDER_CONSTANT)
    sd = np.sqrt(np.maximum(m2 - m1 * m1, 0))
    oy, ox = th // 2, tw // 2
    sd = sd[oy:oy + res.shape[0], ox:ox + res.shape[1]]
    ts = float(t.std())
    res = np.nan_to_num(res, nan=-1.0, posinf=-1.0, neginf=-1.0)
    res[sd < 0.5 * ts] = -1.0
    busy = sd > 2.0 * ts
    res[busy] = np.minimum(res[busy], 0.0)
    return res


def picture_candidates(screen_gray, tmpl_gray, spot, scale_hint=None, limit=6, floor=0.5):
    """Every place on a screenshot that looks like the saved picture, at several sizes.
    Each candidate is checked twice: the whole picture, and a small close-up around the
    spot itself. Returns a list of (score, x, y, scale, whole, closeup) in screenshot
    pixels (x, y = the spot), best first, one per place."""
    H, W = screen_gray.shape[:2]
    th0, tw0 = tmpl_gray.shape[:2]
    cw, ch = min(tw0, 60), min(th0, 34)
    cx0 = int(min(max(spot[0] - cw // 2, 0), tw0 - cw))
    cy0 = int(min(max(spot[1] - ch // 2, 0), th0 - ch))
    core = tmpl_gray[cy0:cy0 + ch, cx0:cx0 + cw]
    # a plain close-up (almost one colour) can't be compared by shape: a little screen noise
    # made it score 0 and hid real matches (4.5.4); the whole picture decides then
    flat_core = float(core.std()) < 4.0
    scales = list(MATCH_SCALES)
    if scale_hint and abs(scale_hint - 1) > 0.02:
        scales = sorted(set(scales) | {round(scale_hint, 3)},
                        key=lambda v: abs(np.log(v / scale_hint)))
    cands = []
    for sc in scales:
        tw, th = round(tw0 * sc), round(th0 * sc)
        if tw < 6 or th < 6 or tw > W or th > H:
            continue
        interp = cv2.INTER_AREA if sc < 1 else cv2.INTER_LINEAR
        t = tmpl_gray if sc == 1 else cv2.resize(tmpl_gray, (tw, th), interpolation=interp)
        c = core if sc == 1 else cv2.resize(core, (max(8, round(cw * sc)), max(6, round(ch * sc))),
                                            interpolation=interp)
        res = _match(screen_gray, t)
        top = None
        for _ in range(limit):                   # a few best places at this size
            _, v, _, (lx, ly) = cv2.minMaxLoc(res)
            if top is None:
                top = v
            if v < max(floor, top - 0.15):
                break
            px, py = lx + cx0 * sc, ly + cy0 * sc
            x0, y0 = int(max(0, px - 4)), int(max(0, py - 4))
            win = screen_gray[y0:int(py) + c.shape[0] + 5, x0:int(px) + c.shape[1] + 5]
            cs = -1.0
            if flat_core:
                cs = float(v)
            elif win.shape[0] >= c.shape[0] and win.shape[1] >= c.shape[1]:
                cs = float(_match(win, c).max())
            cands.append((0.5 * float(v) + 0.5 * cs, lx + spot[0] * sc, ly + spot[1] * sc, sc,
                          float(v), cs))
            res[max(0, ly - th // 2):ly + th // 2 + 1, max(0, lx - tw // 2):lx + tw // 2 + 1] = -1
        if cands and max(cands)[0] >= 0.97:
            break                                # clear match, no need to try other sizes
        if sc == scales[0] and scale_hint and any(
                c[3] == sc and c[4] >= MATCH_WHOLE_MIN + 0.1 and c[5] >= MATCH_CLOSEUP_MIN + 0.1
                for c in cands):
            break                                # found at the size it was last seen
    # one candidate per place (the same place is often found at several sizes)
    out = []
    near = 0.4 * min(tw0, th0)
    for c in sorted(cands, key=lambda c: (is_match(c), c[0]), reverse=True):
        if all((c[1] - o[1]) ** 2 + (c[2] - o[2]) ** 2 > (near * max(c[3], o[3])) ** 2
               for o in out):
            out.append(c)
    return out


def find_picture(screen_gray, tmpl_gray, spot, expected=None, scale_hint=None):
    """The best place for the saved picture (tolerant matching: similar pictures count).
    Returns (score, x, y, scale, whole, closeup) in screenshot pixels, or None."""
    cands = picture_candidates(screen_gray, tmpl_gray, spot, scale_hint)
    if not cands:
        return None
    good = [c for c in cands if is_match(c)]
    if not good:
        return max(cands, key=lambda c: c[0])
    best = max(c[0] for c in good)
    near = [c for c in good if c[0] >= best - 0.02]
    if expected and len(near) > 1:               # look-alikes: take the one nearest the saved spot
        ex, ey = expected
        return min(near, key=lambda c: (c[1] - ex) ** 2 + (c[2] - ey) ** 2)
    return max(near, key=lambda c: c[0])


def is_match(r):
    return bool(r) and r[4] >= MATCH_WHOLE_MIN and r[5] >= MATCH_CLOSEUP_MIN


# Exact matching (4.5.1): the place must be the same picture, not just a similar one. At the
# size it was picked, the pixels must agree almost exactly; at another size (display scaling)
# the place is scaled back to the picture's size and compared again, close-up included.
EXACT_SAME_SIZE_MIN = 0.95   # whole picture and close-up, same size
EXACT_SCALED_WHOLE_MIN = 0.88
EXACT_SCALED_CLOSEUP_MIN = 0.85


def verify_exact(tmpl_gray, tmpl_rgb, spot, screen_gray, screen_rgb, cand):
    """Is the candidate place really the saved picture? Returns (ok, whole, closeup)."""
    _, cx, cy, sc, whole0, close0 = cand
    if abs(sc - 1) < 0.01:
        ok = whole0 >= EXACT_SAME_SIZE_MIN and close0 >= EXACT_SAME_SIZE_MIN
        whole, close = whole0, close0
    else:
        th, tw = tmpl_gray.shape[:2]
        pad = 3
        x0, y0 = cx - spot[0] * sc, cy - spot[1] * sc
        X0, Y0 = int(round(x0)) - pad, int(round(y0)) - pad
        X1, Y1 = int(round(x0 + tw * sc)) + pad, int(round(y0 + th * sc)) + pad
        if X0 < 0 or Y0 < 0 or X1 > screen_gray.shape[1] or Y1 > screen_gray.shape[0]:
            return False, 0.0, 0.0
        reg = screen_gray[Y0:Y1, X0:X1]
        reg = cv2.resize(reg, (max(1, round(reg.shape[1] / sc)), max(1, round(reg.shape[0] / sc))),
                         interpolation=cv2.INTER_AREA if sc > 1 else cv2.INTER_LINEAR)
        a = cv2.GaussianBlur(tmpl_gray, (3, 3), 0).astype(np.float32)
        b = cv2.GaussianBlur(reg, (3, 3), 0).astype(np.float32)
        if b.shape[0] < a.shape[0] or b.shape[1] < a.shape[1]:
            return False, 0.0, 0.0
        whole = float(np.nan_to_num(cv2.matchTemplate(b, a, cv2.TM_CCOEFF_NORMED)).max())
        cw, ch = min(tw, 60), min(th, 34)
        cx0 = int(min(max(spot[0] - cw // 2, 0), tw - cw))
        cy0 = int(min(max(spot[1] - ch // 2, 0), th - ch))
        core = a[cy0:cy0 + ch, cx0:cx0 + cw]
        win = b[cy0:cy0 + ch + 2 * pad, cx0:cx0 + cw + 2 * pad]
        close = -1.0
        if float(core.std()) < 4.0:              # a plain close-up: the whole picture decides
            close = whole
        elif win.shape[0] >= core.shape[0] and win.shape[1] >= core.shape[1]:
            close = float(np.nan_to_num(cv2.matchTemplate(win, core, cv2.TM_CCOEFF_NORMED)).max())
        ok = whole >= EXACT_SCALED_WHOLE_MIN and close >= EXACT_SCALED_CLOSEUP_MIN
    if ok:
        th, tw = tmpl_gray.shape[:2]
        mx = cx - spot[0] * sc + tw * sc / 2     # centre of the picture on screen
        my = cy - spot[1] * sc + th * sc / 2
        chroma, light = color_difference(tmpl_rgb, screen_rgb, mx, my, sc)
        ok = chroma <= WATCH_COLOR_MAX and light <= WATCH_LIGHT_MAX
    return ok, whole, close


def system_dpi():
    if not IS_WIN:
        return 96
    try:
        return int(user32.GetDpiForSystem())
    except Exception:
        return 96


def uses_picture(job):
    return bool(HAVE_CV and job.get("use_image") and job.get("snap_png"))


def locate_spot(job, activate=False, check_cover=True):
    """Where to click now. Returns (ok, x, y, message, how-it-was-found)."""
    return spot_report(job, activate=activate, check_cover=check_cover)["result"]


def spot_report(job, activate=False, check_cover=True):
    """Find the job's (or step's) click spot. Returns a dict:
    result   (ok, x, y, message, how) - what locate_spot returns
    similar  [(x, y, w, h, note, chosen?, exact?)] every place that looks like the picture,
             in screen pixels (x, y, w, h = the picture's box) - for "point out similar"
    With exact matching (the default) only the picture itself counts: similar pictures are
    never clicked, and if the exact picture is on screen more than once, the copy where the
    spot was picked is used, or nothing is clicked when that can't be told."""
    rep = {"similar": []}
    if not uses_picture(job):
        ok, x, y, msg = resolve_target(job, activate=activate, check_cover=check_cover)
        rep["result"] = (ok, x, y, msg, "saved position")
        return rep
    exact = bool(job.get("exact_match", True))
    region = None
    if job.get("target_mode") == "window" and job.get("window_title") and IS_WIN:
        h = find_window(job["window_title"], job.get("window_class", ""))
        if h:
            if activate and job.get("bring_to_front", True):
                bring_to_front(h)
            if not user32.IsIconic(h):
                region = client_origin(h)
    eok, ex, ey, _ = resolve_target(job, activate=False, check_cover=False)
    try:
        shot, (vx, vy) = grab_screen()
    except Exception as e:
        rep["result"] = (False, 0, 0, f"couldn't capture the screen ({e})", "")
        return rep
    t_rgb = np.ascontiguousarray(np.asarray(b64_to_img(job["snap_png"])))
    tmpl = cv2.cvtColor(t_rgb, cv2.COLOR_RGB2GRAY)
    th0, tw0 = tmpl.shape[:2]
    spot = job.get("snap_spot") or [tw0 // 2, th0 // 2]
    s_rgb = np.ascontiguousarray(np.asarray(shot))
    full = cv2.cvtColor(s_rgb, cv2.COLOR_RGB2GRAY)
    tries = []
    if region:                                   # look inside the window first
        l, t, w, h = region
        x0, y0 = max(0, l - vx), max(0, t - vy)
        sub = full[y0:y0 + h, x0:x0 + w]
        if sub.size:
            tries.append((sub, s_rgb[y0:y0 + h, x0:x0 + w], vx + x0, vy + y0))
    tries.append((full, s_rgb, vx, vy))
    ps_dpi, cur_dpi = job.get("pick_dpi"), system_dpi()
    hint = cur_dpi / ps_dpi if ps_dpi else None
    found, seen, note = None, [], ""
    for img, rgb, ox, oy in tries:
        cands = picture_candidates(img, tmpl, spot, hint)
        for c in cands:
            sx, sy = round(c[1] + ox), round(c[2] + oy)
            if any(abs(sx - o[0]) < 4 and abs(sy - o[1]) < 4 for o in seen):
                continue
            ok_exact, w_, c_ = (verify_exact(tmpl, t_rgb, spot, img, rgb, c) if exact and
                                is_match(c) else (False, c[4], c[5]))
            seen.append([sx, sy, c, ok_exact])
        if exact:
            good = [o for o in seen if o[3]]
            if len(good) > 1:
                # the same picture more than once: use the copy where the spot was picked
                tol = 0.5 * max(tw0, th0) * max(o[2][3] for o in good)
                at = [o for o in good if eok and (o[0] - ex) ** 2 + (o[1] - ey) ** 2 <= tol ** 2]
                if len(at) == 1:
                    found = at[0]
                else:
                    found = None
                    note = (f"the exact picture is on screen {len(good)} times and Clickue can't "
                            f"tell which one you picked")
            elif good:
                found = good[0]
        else:
            r = find_picture(img, tmpl, spot, (ex - ox, ey - oy) if eok else None, hint)
            if r and is_match(r):
                rx, ry = round(r[1] + ox), round(r[2] + oy)
                found = next((o for o in seen if abs(o[0] - rx) < 4 and abs(o[1] - ry) < 4),
                             [rx, ry, r, False])
        if found or note:
            break
    for o in seen:                               # what "point out similar pictures" shows
        sx, sy, c, ok_exact = o
        sc = c[3]
        bx, by = round(sx - spot[0] * sc), round(sy - spot[1] * sc)
        if not is_match(c) and max(c[4], c[5]) < 0.55:
            continue
        pct = f"{max(0.0, min(c[4], c[5])):.0%}"
        if exact:
            kind = "exact" if ok_exact else "similar"
        else:
            kind = "match" if is_match(c) else "similar"
        rep["similar"].append((bx, by, round(tw0 * sc), round(th0 * sc), f"{kind} {pct}",
                               o is found, ok_exact))
    if found:
        x, y, c = found[0], found[1], found[2]
        sc = c[3]
        if check_cover and IS_WIN:
            w = window_at(x, y)
            if w and is_own_window(w):
                rep["result"] = (False, x, y, "the Clickue window is covering the spot", "")
                return rep
        how = ("exact picture" if exact else "picture") + f" {min(c[4], c[5]):.0%}" + (
            "" if abs(sc - 1) < 0.01 else f" at {sc:.0%} size")
        rep["result"] = (True, x, y, "", how)
        return rep
    best = max((o[2] for o in seen), key=lambda c: min(c[4], c[5]), default=None)
    best_t = f"{max(0.0, min(best[4], best[5])):.0%}" if best else "none"
    if not note:
        n_sim = sum(1 for o in seen if is_match(o[2]))
        note = (f"couldn't find the exact picture on screen (best match {best_t}"
                + (f"; {n_sim} similar place{'s' if n_sim != 1 else ''} ignored" if exact and n_sim
                   else "") + ")") if exact else \
            f"couldn't find the saved picture on screen (best match {best_t})"
    if job.get("image_fallback") == "position":
        ok, x, y, msg = resolve_target(job, activate=False, check_cover=check_cover)
        rep["result"] = (ok, x, y, msg, f"saved position (picture not found, best {best_t})")
        return rep
    rep["result"] = (False, 0, 0, note, "")
    return rep


def color_difference(tmpl_rgb, screen_rgb, cx, cy, scale):
    """How different the colours are between the saved picture and the same-sized area of
    the screen centred on (cx, cy). Returns (colour, brightness) average differences."""
    th, tw = tmpl_rgb.shape[:2]
    w, h = max(1, round(tw * scale)), max(1, round(th * scale))
    x0, y0 = round(cx - w / 2), round(cy - h / 2)
    reg = screen_rgb[max(0, y0):y0 + h, max(0, x0):x0 + w]
    if x0 < 0 or y0 < 0 or reg.shape[0] < h or reg.shape[1] < w:
        return 999.0, 999.0
    if (w, h) != (tw, th):
        reg = cv2.resize(reg, (tw, th), interpolation=cv2.INTER_AREA)
    a = cv2.cvtColor(cv2.GaussianBlur(tmpl_rgb, (5, 5), 0), cv2.COLOR_RGB2LAB).astype(np.float32)
    b = cv2.cvtColor(cv2.GaussianBlur(np.ascontiguousarray(reg), (5, 5), 0),
                     cv2.COLOR_RGB2LAB).astype(np.float32)
    chroma = float(np.sqrt(((a[..., 1:] - b[..., 1:]) ** 2).sum(-1)).mean())
    light = float(np.abs(a[..., 0] - b[..., 0]).mean())
    return chroma, light


WATCH_SAME_SIZE_MIN = 0.93   # at the size it was drawn, the picture must match almost exactly
WATCH_COLOR_MAX = 15.0       # average colour difference allowed
WATCH_LIGHT_MAX = 25.0       # average brightness difference allowed


def job_area(job):
    """The watcher's search area on screen right now (scaled if the screen size changed),
    as (x, y, w, h), or None for the whole screen."""
    a = job.get("watch_area")
    if not a:
        return None
    x, y, w, h = (int(v) for v in a)
    ref = job.get("watch_area_screen")
    if ref:
        vx, vy, vw, vh = virtual_screen()
        if (vw, vh) != tuple(ref[:2]) and ref[0] and ref[1]:
            fx, fy = vw / ref[0], vh / ref[1]
            x, y, w, h = round(x * fx), round(y * fy), round(w * fx), round(h * fy)
    return x, y, w, h


# Partial matching (4.5.3, per watcher, off by default): the saved picture is split into
# small tiles and each tile is compared on its own (a few pixels of play, colour checked).
# The picture counts as there when at least `watch_partial_pct` % of the tiles match, so a
# changing number or an animation inside the box doesn't make the whole picture "gone".
PARTIAL_MIN_PCT, PARTIAL_MAX_PCT, PARTIAL_DEFAULT_PCT = 40, 95, 75
PARTIAL_TILE = 24            # tile size in picture pixels (2-10 tiles per side)
PARTIAL_TILE_MIN = 0.85      # a detailed tile matches when it correlates this well
PARTIAL_FLAT_LIGHT = 12.0    # a plain tile matches when its brightness differs less...
PARTIAL_TILE_COLOR = 18.0    # ...and its colour less than this (Lab units)
SPLIT_MIN, SPLIT_MAX = 0.08, 0.94   # job list share of the main window's lower part (4.5.4)
PICTURE_MIN_PX = 8           # smallest picture box (zoom in to draw small ones), 4.5.4
TRAY_DUE_S = 60              # a scheduled click this close turns the tray icon amber
SCREEN_SETTLE_S = 15         # after the screen changes size/scaling, wait before counting
POINTER_IDLE_S = 20          # a watcher may move the pointer aside after this much idle time
AREA_PAD_MIN = 24            # a drawn search area is searched with this much margin (px)


def search_box(area, tw, th, scale=1.0):
    """The drawn search area plus a margin, so a picture that touches the edge of the area
    (or moved a few pixels) is still found. The box is always at least the picture's size
    plus the margin. Returns (x, y, w, h) in screen pixels."""
    ax, ay, aw, ah = area
    pad = max(AREA_PAD_MIN, int(0.25 * max(tw, th) * max(1.0, scale)))
    need_w, need_h = int(tw * max(1.0, scale)) + 2 * pad, int(th * max(1.0, scale)) + 2 * pad
    w, h = max(aw + 2 * pad, need_w), max(ah + 2 * pad, need_h)
    cx, cy = ax + aw / 2, ay + ah / 2
    return int(round(cx - w / 2)), int(round(cy - h / 2)), int(w), int(h)


EXACT_TILE_DIFF = 14.0       # exact watcher match: average colour difference in any tile
EXACT_TILE_CORR = 0.90       # ... and every detailed tile must still correlate this well
EXACT_TILE_CORR_SCALED = 0.70  # (at another size; measured: same 0.79+, changed text < 0.1)


def exact_tiles(t_rgb, s_rgb, cand, spot):
    """Pixel-exact check for watchers (4.5.4): the picture is cut into the same small tiles
    as for partial matching and EVERY tile must agree with the screen (colour difference and,
    for detailed tiles, shape), so a single changed digit anywhere in the box counts as a
    difference. At the drawn size the place may sit 1 px off; at another size the place is
    scaled back first. Returns (ok, share of tiles that agree)."""
    _, cx, cy, sc = cand[:4]
    th, tw = t_rgb.shape[:2]
    x0, y0 = cx - spot[0] * sc, cy - spot[1] * sc
    H, W = s_rgb.shape[:2]
    if abs(sc - 1) < 0.01:
        X0, Y0 = int(round(x0)), int(round(y0))
        best, reg = None, None
        a16 = t_rgb.astype(np.int16)
        for dy in (0, -1, 1):
            for dx in (0, -1, 1):
                X, Y = X0 + dx, Y0 + dy
                if X < 0 or Y < 0 or Y + th > H or X + tw > W:
                    continue
                r = s_rgb[Y:Y + th, X:X + tw]
                d = float(np.abs(r.astype(np.int16) - a16).mean())
                if best is None or d < best:
                    best, reg = d, r
        if reg is None:
            return False, 0.0
    else:
        best, reg = None, None
        a16 = t_rgb.astype(np.int16)
        for dy in (0, -1, 1):                    # the scaled place may sit 1 px off
            for dx in (0, -1, 1):
                X0, Y0 = int(round(x0)) + dx, int(round(y0)) + dy
                X1, Y1 = X0 + int(round(tw * sc)), Y0 + int(round(th * sc))
                if X0 < 0 or Y0 < 0 or X1 > W or Y1 > H or X1 - X0 < 4 or Y1 - Y0 < 4:
                    continue
                r = cv2.resize(np.ascontiguousarray(s_rgb[Y0:Y1, X0:X1]), (tw, th),
                               interpolation=cv2.INTER_AREA if sc > 1 else cv2.INTER_LINEAR)
                d = float(np.abs(r.astype(np.int16) - a16).mean())
                if best is None or d < best:
                    best, reg = d, r
        if reg is None:
            return False, 0.0
    a = t_rgb.astype(np.float32)
    b = reg.astype(np.float32)
    if abs(sc - 1) >= 0.01:                   # resampling softens edges: compare blurred
        a = cv2.GaussianBlur(a, (3, 3), 0)
        b = cv2.GaussianBlur(b, (3, 3), 0)
    ga, gb = a.mean(axis=2), b.mean(axis=2)
    lim = EXACT_TILE_DIFF * (1.0 if abs(sc - 1) < 0.01 else 1.6)
    corr_min = EXACT_TILE_CORR if abs(sc - 1) < 0.01 else EXACT_TILE_CORR_SCALED
    tiles = _tile_grid(th, tw)
    good = 0
    for ty0, ty1, tx0, tx1 in tiles:
        d = float(np.abs(a[ty0:ty1, tx0:tx1] - b[ty0:ty1, tx0:tx1]).mean())
        same = d <= lim
        ta = ga[ty0:ty1, tx0:tx1]
        if same and float(ta.std()) >= 6.0:
            tb = gb[ty0:ty1, tx0:tx1]
            if float(tb.std()) < 1.0:
                same = False
            else:
                c = float(np.corrcoef(ta.ravel(), tb.ravel())[0, 1])
                same = np.isfinite(c) and c >= corr_min
        good += same
    n = len(tiles) or 1
    return good == len(tiles), good / n


def partial_fraction(t_rgb, t_gray, s_rgb, s_gray, cand, spot):
    """How much of the saved picture is at the candidate place: the fraction (0..1) of its
    tiles that match. Each tile may sit up to 4 px off; plain tiles are compared by
    brightness and colour, detailed tiles by shape and colour."""
    _, cx, cy, sc = cand[:4]
    th, tw = t_gray.shape[:2]
    pad = 4
    H, W = s_gray.shape[:2]
    x0, y0 = cx - spot[0] * sc, cy - spot[1] * sc
    X0, Y0 = int(round(x0)) - pad, int(round(y0)) - pad
    X1, Y1 = int(round(x0 + tw * sc)) + pad, int(round(y0 + th * sc)) + pad
    if X1 - X0 < 8 or Y1 - Y0 < 8:
        return 0.0
    reg = np.zeros((Y1 - Y0, X1 - X0, 3), np.uint8)
    valid = np.zeros((Y1 - Y0, X1 - X0), np.uint8)
    cx0, cy0, cx1, cy1 = max(0, X0), max(0, Y0), min(W, X1), min(H, Y1)
    if cx1 - cx0 < 8 or cy1 - cy0 < 8:
        return 0.0
    reg[cy0 - Y0:cy1 - Y0, cx0 - X0:cx1 - X0] = s_rgb[cy0:cy1, cx0:cx1]
    valid[cy0 - Y0:cy1 - Y0, cx0 - X0:cx1 - X0] = 1
    size = (tw + 2 * pad, th + 2 * pad)
    if abs(sc - 1) >= 0.01 or reg.shape[1::-1] != size:
        interp = cv2.INTER_AREA if sc > 1 else cv2.INTER_LINEAR
        reg = cv2.resize(reg, size, interpolation=interp)
        valid = cv2.resize(valid, size, interpolation=cv2.INTER_NEAREST)
    rg = cv2.cvtColor(reg, cv2.COLOR_RGB2GRAY).astype(np.float32)
    tg = t_gray.astype(np.float32)
    t_lab = cv2.cvtColor(t_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    r_lab = cv2.cvtColor(reg, cv2.COLOR_RGB2LAB).astype(np.float32)
    ny = int(min(10, max(2, round(th / PARTIAL_TILE))))
    nx = int(min(10, max(2, round(tw / PARTIAL_TILE))))
    ys = [round(k * th / ny) for k in range(ny + 1)]
    xs = [round(k * tw / nx) for k in range(nx + 1)]
    good = total = 0
    for a in range(ny):
        for b in range(nx):
            ty0, ty1, tx0, tx1 = ys[a], ys[a + 1], xs[b], xs[b + 1]
            if ty1 - ty0 < 3 or tx1 - tx0 < 3:
                continue
            total += 1
            if valid[ty0 + pad:ty1 + pad, tx0 + pad:tx1 + pad].min() == 0:
                continue                            # off the screen: doesn't match
            tile = tg[ty0:ty1, tx0:tx1]
            win = rg[ty0:ty1 + 2 * pad, tx0:tx1 + 2 * pad]
            if float(tile.std()) < 3.0:             # plain tile: same brightness and colour
                dx = dy = pad
                same = abs(float(win[dy:dy + ty1 - ty0, dx:dx + tx1 - tx0].mean())
                           - float(tile.mean())) <= PARTIAL_FLAT_LIGHT
            else:
                res = np.nan_to_num(cv2.matchTemplate(win, tile, cv2.TM_CCOEFF_NORMED),
                                    nan=-1.0, posinf=-1.0, neginf=-1.0)
                _, v, _, (dx, dy) = cv2.minMaxLoc(res)
                same = v >= PARTIAL_TILE_MIN
            if same:
                ta = t_lab[ty0:ty1, tx0:tx1]
                ra = r_lab[ty0 + dy:ty0 + dy + (ty1 - ty0), tx0 + dx:tx0 + dx + (tx1 - tx0)]
                if ra.shape != ta.shape:
                    continue
                chroma = float(np.sqrt(((ta[..., 1:] - ra[..., 1:]) ** 2).sum(-1)).mean())
                light = float(np.abs(ta[..., 0] - ra[..., 0]).mean())
                if chroma <= PARTIAL_TILE_COLOR and light <= PARTIAL_FLAT_LIGHT * 2:
                    good += 1
    return good / total if total else 0.0


PARTIAL_VOTE_TILES = 16      # most detailed tiles used to look for partial matches
PARTIAL_VOTE_MIN = 0.80      # a tile "hits" a place when it correlates this well
MAX_MATCHES = 24             # most places reported for one picture


def _tile_grid(th, tw):
    ny = int(min(10, max(2, round(th / PARTIAL_TILE))))
    nx = int(min(10, max(2, round(tw / PARTIAL_TILE))))
    ys = [round(k * th / ny) for k in range(ny + 1)]
    xs = [round(k * tw / nx) for k in range(nx + 1)]
    return [(ys[a], ys[a + 1], xs[b], xs[b + 1]) for a in range(ny) for b in range(nx)
            if ys[a + 1] - ys[a] >= 3 and xs[b + 1] - xs[b] >= 3]


def partial_candidates(tmpl_gray, screen_gray, spot, scale_hint=None, need=0.75,
                       limit=MAX_MATCHES):
    """Every place where a good share of the picture's detailed tiles is found (4.5.4).
    Each tile is searched on its own over the whole screenshot, and every hit votes for
    where the picture would start; places with enough votes are candidates. Unlike the
    whole-picture search, this finds every copy whose changed part differs, wherever it is.
    Returns [(votes share, x, y, scale, votes share, votes share)] with x, y = the spot."""
    H, W = screen_gray.shape[:2]
    th0, tw0 = tmpl_gray.shape[:2]
    scales = [1.0]
    if scale_hint and abs(scale_hint - 1) > 0.02:
        scales = [round(scale_hint, 3), 1.0]
    out = []
    S = screen_gray.astype(np.float32)
    for sc in scales:
        th, tw = round(th0 * sc), round(tw0 * sc)
        if tw < 6 or th < 6 or tw > W or th > H:
            continue
        t = tmpl_gray if sc == 1 else cv2.resize(
            tmpl_gray, (tw, th), interpolation=cv2.INTER_AREA if sc < 1 else cv2.INTER_LINEAR)
        t = t.astype(np.float32)
        tiles = [(float(t[a:b, c:d].std()), a, b, c, d) for a, b, c, d in _tile_grid(th, tw)]
        tex = sorted([x for x in tiles if x[0] >= 3.0], reverse=True)[:PARTIAL_VOTE_TILES]
        if len(tex) < 2:
            continue
        Ho, Wo = H - th + 1, W - tw + 1
        V = np.zeros((Ho, Wo), np.float32)
        kern = np.ones((5, 5), np.uint8)
        for _, a, b, c, d in tex:
            R = cv2.matchTemplate(S, t[a:b, c:d], cv2.TM_CCOEFF_NORMED)
            R = np.nan_to_num(R, nan=-1.0, posinf=-1.0, neginf=-1.0)
            hits = cv2.dilate((R >= PARTIAL_VOTE_MIN).astype(np.uint8), kern)
            V += hits[a:a + Ho, c:c + Wo]
        n = len(tex)
        thr = max(2.0, np.ceil(n * max(0.25, need - 0.4)))
        for _ in range(limit * 2):
            _, v, _, (ox, oy) = cv2.minMaxLoc(V)
            if v < thr:
                break
            share = float(v) / n
            out.append((share, ox + spot[0] * sc, oy + spot[1] * sc, sc, share, share))
            V[max(0, oy - th // 2):oy + th // 2 + 1, max(0, ox - tw // 2):ox + tw // 2 + 1] = 0
            if len(out) >= limit:
                break
        if out:
            break
    return out


def picture_on_screen(png_b64, scale_hint=None, shot=None, area=None, report=None,
                      partial=None, exclude=None):
    """Is this exact picture on the screen (or inside `area`) right now?
    Stricter than finding a click spot: shape, colour and (at the original size) fine
    detail must all agree, so a similar-looking replacement doesn't count as "still there".
    At another size the place is scaled back and compared again (4.5.1).
    `partial` (0.4-0.95, 4.5.3): instead, the picture counts as there when at least that
    share of it matches (see partial_fraction); the score is then that share.
    A search `area` is searched with a margin (search_box), so a picture at its edge counts.
    `exclude` = screen rectangles (Clickue's own windows, 4.6) where nothing counts as found.
    Returns (found, x, y, score, scale) - x, y is the picture's centre on screen.
    If `report` is a list, every similar place is added to it as
    (x, y, w, h, note, chosen?, exact?) in screen pixels."""
    if shot is None:
        shot = grab_screen(move_cursor=False)
    img, (vx, vy) = shot
    t_rgb = np.ascontiguousarray(np.asarray(b64_to_img(png_b64)))
    tmpl = cv2.cvtColor(t_rgb, cv2.COLOR_RGB2GRAY)
    th0, tw0 = tmpl.shape[:2]
    if area:
        ax, ay, aw, ah = search_box(area, tw0, th0, scale_hint or 1.0)
        l, t = max(0, ax - vx), max(0, ay - vy)
        r, b = min(img.width, ax - vx + aw), min(img.height, ay - vy + ah)
        if r - l >= 16 and b - t >= 16:
            img = img.crop((l, t, r, b))
            vx, vy = vx + l, vy + t
    s_rgb = np.ascontiguousarray(np.asarray(img))
    full = cv2.cvtColor(s_rgb, cv2.COLOR_RGB2GRAY)
    spot = (tw0 // 2, th0 // 2)
    if partial:
        partial = min(PARTIAL_MAX_PCT, max(PARTIAL_MIN_PCT, float(partial) * 100)) / 100
    cands = picture_candidates(full, tmpl, spot, scale_hint, floor=0.3 if partial else 0.5,
                               limit=MAX_MATCHES if report is not None else 6)
    if partial:
        # also every place where enough of its pieces are found (4.5.4): copies whose
        # changing part differs score low as a whole and were missed before
        near = 0.4 * min(tw0, th0)
        for c in partial_candidates(tmpl, full, spot, scale_hint, partial):
            if all((c[1] - o[1]) ** 2 + (c[2] - o[2]) ** 2 > (near * max(c[3], o[3])) ** 2
                   for o in cands):
                cands.append(c)
    if not cands:
        return False, 0, 0, 0.0, None
    if exclude:
        def outside(c):
            box = (c[1] - tw0 * c[3] / 2 + vx, c[2] - th0 * c[3] / 2 + vy, tw0 * c[3], th0 * c[3])
            if not any(rects_overlap(box, r) for r in exclude):
                return True
            if not IS_WIN:
                return False
            # 4.6.1: only where a Clickue window is really in front (not behind the browser)
            bx, by, bw, bh = box
            pts = ((bx + bw / 2, by + bh / 2), (bx + 1, by + 1), (bx + bw - 2, by + 1),
                   (bx + 1, by + bh - 2), (bx + bw - 2, by + bh - 2))
            return not any(own_on_top(px, py) for px, py in pts)
        cands = [c for c in cands if outside(c)]
        if not cands:
            return False, 0, 0, 0.0, None
    chosen, checked = None, []
    for c in cands:
        sc = c[3]
        if partial:
            frac = partial_fraction(t_rgb, tmpl, s_rgb, full, c, spot)
            ok = frac >= partial - 1e-9
            checked.append((c, ok, frac))
            if ok and (chosen is None or frac > chosen[1]):
                chosen = (c, frac)
            continue
        ok = is_match(c)
        vscore = None
        if ok and abs(sc - 1) < 0.01:
            ok = c[4] >= WATCH_SAME_SIZE_MIN - 0.03 and c[5] >= WATCH_SAME_SIZE_MIN
        elif ok:
            ok, vw_, vc_ = verify_exact(tmpl, t_rgb, spot, full, s_rgb, c)
            vscore = max(0.0, min(vw_, vc_))
        if ok:
            chroma, light = color_difference(t_rgb, s_rgb, c[1], c[2], sc)
            ok = chroma <= WATCH_COLOR_MAX and light <= WATCH_LIGHT_MAX
        val = max(0.0, min(c[4], c[5]))
        if ok and vscore is not None:
            val = max(val, vscore)      # 4.6: report the score of the size-corrected check
        if ok or is_match(c):
            # every part of the picture must agree, not just most of it (4.5.4)
            ok2, share = exact_tiles(t_rgb, s_rgb, c, spot)
            ok = ok and ok2
            if not ok2:
                val = min(val, share)
        checked.append((c, ok, val))
        if ok and chosen is None:
            chosen = (c, checked[-1][2])
    if report is not None:
        for c, ok, val in checked:
            if not partial and not is_match(c) and max(c[4], c[5]) < 0.55:
                continue
            if partial and val < 0.25:
                continue
            sc = c[3]
            kind = ("match" if ok else "part") if partial else ("exact" if ok else "similar")
            report.append((round(c[1] - tw0 * sc / 2 + vx), round(c[2] - th0 * sc / 2 + vy),
                           round(tw0 * sc), round(th0 * sc), f"{kind} {val:.0%}",
                           chosen is not None and c is chosen[0], ok))
    if chosen:
        r, score = chosen
        return True, round(r[1] + vx), round(r[2] + vy), score, r[3]
    if partial:
        r, _, score = max(checked, key=lambda k: k[2])
        return False, round(r[1] + vx), round(r[2] + vy), score, r[3]
    r, _, score = max(checked, key=lambda k: k[2])
    return False, round(r[1] + vx), round(r[2] + vy), score, r[3]


def watch_partial(job):
    """The share of the picture a watcher needs (0.4-0.95), or None for exact matching."""
    if job.get("watch_match") != "partial":
        return None
    try:
        pct = int(job.get("watch_partial_pct", PARTIAL_DEFAULT_PCT))
    except (TypeError, ValueError):
        pct = PARTIAL_DEFAULT_PCT
    return min(PARTIAL_MAX_PCT, max(PARTIAL_MIN_PCT, pct)) / 100


def current_pointer():
    """Where the mouse pointer is, or None where that can't be known (not Windows)."""
    return get_cursor() if IS_WIN else None


def pointer_near_watch(job, result, cursor=None):
    """Is the mouse pointer resting on (or right next to) the watched picture or its search
    area? Hovering can change how a button looks, so a watcher shouldn't call it "gone"."""
    if cursor is None:
        cursor = current_pointer()
        if cursor is None:
            return False
    px, py = cursor
    boxes = []
    try:
        img = b64_to_img(job["watch_png"])
        tw, th = img.size
    except Exception:
        tw, th = 100, 60
    if result and (result[1] or result[2]):
        sc = result[4] or 1.0
        boxes.append((result[1] - tw * sc / 2, result[2] - th * sc / 2, tw * sc, th * sc))
    if job.get("found_xy"):                       # where it was last seen
        fx, fy = job["found_xy"]
        sc = job.get("watch_scale") or 1.0
        boxes.append((fx - tw * sc / 2, fy - th * sc / 2, tw * sc, th * sc))
    area = job_area(job)
    if area:
        boxes.append(area)
    m = 30
    return any(x - m <= px <= x + w + m and y - m <= py <= y + h + m for x, y, w, h in boxes)


def picture_changes(crop, box, vx, vy):
    """Capture the same box again (pointer moved aside) and return the share of the picture
    that changed (0 = identical). Used right after drawing a watcher's box."""
    try:
        img, (ox, oy) = grab_screen(move_cursor=True)
        l, t = box[0] + vx - ox, box[1] + vy - oy
        again = img.crop((l, t, l + crop.width, t + crop.height))
        a = np.asarray(crop.convert("L"), dtype=np.int16)
        b = np.asarray(again.convert("L"), dtype=np.int16)
        if a.shape != b.shape:
            return 0.0
        diff = np.abs(a - b) > 24
        return float(diff.mean()) if diff.mean() > 0.01 else 0.0
    except Exception:
        return 0.0


def job_health(app, j, iid="", now=None):
    """Plain-language status of one job, for the job list's hover text (4.5.6): what it's
    doing, whether anything is wrong and what to do, and what comes next."""
    now = now or time.time()
    with app.lock:
        j = dict(j)
        waits = {k[1]: v for k, v in app.wait_msgs.items() if k[0] == j["id"]}
        paused_all = app.settings.get("paused")
    kind = "Screen watcher" if is_watch(j) else "Scheduled click"
    n_steps = len(j.get("steps") or [])
    head = f"{j['name']}  ·  {kind}" + (f"  ·  ☰ {n_steps} step{'s' if n_steps != 1 else ''}"
                                         if n_steps else "")
    lines = [head]
    if iid.startswith(("test:", "wtest:")):
        lines.append("A test that runs once. It doesn't change the job's schedule.")
    if iid.startswith("step:"):
        try:
            k = int(iid.rsplit(":", 1)[1])
            lines.append("Step {}: {}".format(k + 1, " - ".join(
                x for x in describe_step(j['steps'][k], private=True) if x)))
        except Exception:
            pass
    problems = []
    if not j.get("enabled"):
        lines.append("Stopped: it doesn't click or watch until you start it.")
    elif paused_all or j.get("paused"):
        lines.append("Paused" + (" (all jobs)" if paused_all else "") +
                     ": nothing is clicked until you resume.")
    elif is_watch(j):
        st, note = j.get("watch_state"), j.get("watch_note") or ""
        appears = j.get("watch_trigger") == "appears"
        seen = j.get("last_seen")
        where = (f" at ({j['found_xy'][0]}, {j['found_xy'][1]})" if j.get("found_xy") else "")
        if note == "outside active hours":
            lines.append(f"Outside its active hours ({describe_hours(j)}): not watching now.")
        elif st == "unknown":
            n = int(j.get("issue_count") or 0)
            since = j.get("issue_since")
            problems.append(f"PROBLEM: can't watch - {note}"
                            + (f" ({n} checks in a row, for {fmt_dur(now - since)})"
                               if since and n > 1 else ""))
            hint = issue_hint(note)
            if hint:
                problems.append("What to do: " + hint)
        elif st == "seen":
            lines.append(f"OK: picture seen {datetime.fromtimestamp(seen).strftime('%H:%M:%S') if seen else ''}"
                         f"{where}." + (" Waiting for it to go away." if appears else ""))
        elif st == "missing":
            lines.append(("Picture not showing" if appears else "Picture NOT found")
                         + (f" ({note})" if note else "") + "."
                         + (f" Last seen {datetime.fromtimestamp(seen).strftime('%H:%M:%S')}{where}."
                            if seen else ""))
        else:
            lines.append("Starting: the first check is coming up.")
        if j.get("pending_click_at"):
            lines.append(f"CLICKING in {fmt_dur(j['pending_click_at'] - now)} "
                         f"(at {fmt_time(j['pending_click_at'])}). Checks continue; the click is "
                         f"cancelled if the picture {'goes away' if appears else 'comes back'}.")
        if j.get("next_check"):
            lines.append(f"Next check in {fmt_dur(max(0, j['next_check'] - now))} "
                         f"(every {fmt_compact(j.get('watch_interval_s', 30))}, "
                         f"{int(j.get('watch_confirm', 2))} in a row to act).")
    else:
        if j.get("next_run"):
            lines.append(f"Next click {fmt_time(j['next_run'])} "
                         f"(in {fmt_dur(max(0, j['next_run'] - now))}).")
    for kind_, msg in waits.items():
        problems.append(f"PROBLEM: {'test ' if kind_ == 'test' else ''}click waiting - {msg}")
        hint = issue_hint(msg)
        if hint:
            problems.append("What to do: " + hint)
    last = j.get("last_result") or ""
    if last.startswith(("Missed", "Click FAILED", "Test FAILED")):
        problems.append(f"PROBLEM: last result: {last}. See Activity for the reason.")
    elif last:
        lines.append(f"Last result: {last}")
    lines.append(f"Clicks at: {target_text(j)}" if j.get("main_click", True)
                 else f"Runs {n_steps} step{'s' if n_steps != 1 else ''} (no click of its own)")
    if not problems and j.get("enabled") and not (paused_all or j.get("paused")):
        lines.insert(1, "✔ No problems.")
    return "\n".join(lines[:1] + problems + lines[1:])


def watch_window(job):
    """For a watcher that clicks inside a window (target_mode "window"): is that window there
    and visible? Returns (state, rect, title): state "ok" / "missing" / "minimized" /
    "none" (not a window watcher, or not on Windows); rect = the window's inside area."""
    title = (job.get("window_title") or "").strip()
    if job.get("target_mode") != "window" or not title or not IS_WIN:
        return "none", None, title
    try:
        h = find_window(title, job.get("window_class", ""))
        if not h:
            return "missing", None, title
        if user32.IsIconic(h):
            return "minimized", None, title
        return "ok", client_origin(h), title
    except Exception:
        return "none", None, title


def window_covering(job, xy):
    """Is another program's window on top of the watcher's window at xy? Returns its title
    (or "" if not)."""
    if not IS_WIN or not xy:
        return ""
    try:
        h = find_window(job.get("window_title", ""), job.get("window_class", ""))
        w = window_at(*xy)
        if h and w and not same_window(w, h) and not is_own_window(w):
            return win_text(w) or "another window"
    except Exception:
        pass
    return ""


def rects_overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def rect_intersection(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


def watch_scope(job):
    """Where a watcher looks (4.6): (job copy with its search rectangle, problem or "").
    A watcher that clicks inside a window only looks inside that window; a missing or
    minimized window is a problem, not a missing picture."""
    snap = dict(job)
    wstate, wrect, wtitle = watch_window(snap)
    wt_ = short_title(wtitle, 40)
    if wstate == "missing":
        return snap, (f"its window \u201c{wt_}\u201d isn't open (no window with that title - "
                      f"if the page or tab changed, so did its title)")
    if wstate == "minimized":
        return snap, f"its window \u201c{wt_}\u201d is minimized"
    if wstate == "ok":
        area = job_area(snap)
        search = rect_intersection(area, wrect) if area else wrect
        if not search:
            return snap, (f"its search area is outside its window \u201c{wt_}\u201d (the "
                          f"window moved or the area was drawn on another screen)")
        snap["_search_rect"] = search
    return snap, ""


def watch_area_note(job):
    """If a watcher's search area was drawn on a different screen size, say so (the area is
    scaled, which may not match how the window's content moved)."""
    a, ref = job.get("watch_area"), job.get("watch_area_screen")
    if not a:
        return ""
    vx, vy, vw, vh = virtual_screen()
    x, y, w, h = job_area(job)
    txt = f"searched only its area {w}×{h} at ({x}, {y})"
    if ref and tuple(ref[:2]) != (vw, vh):
        txt += (f"; that search area was drawn on a {ref[0]}×{ref[1]} screen and the screen is "
                f"{vw}×{vh} now, so it was scaled - if the picture is outside it, draw the "
                f"search area again on this screen")
    return txt


def watched_picture(job, report=None, move_ok=False):
    """Look for a watcher's picture with its own settings (search area, exact or partial).
    If it isn't found while the mouse pointer rests on it, hovering may have changed how it
    looks: with `move_ok` the screen is captured again with the pointer moved aside for a
    moment (tests, or when nobody is using the computer); otherwise `pointer` is True and
    the caller shouldn't count it as gone.
    Returns ((found, x, y, score, scale), note, pointer)."""
    kw = dict(area=job.get("_search_rect") or job_area(job), partial=watch_partial(job),
              exclude=job.get("_exclude") or None)
    rep = [] if report is not None else None
    shot = grab_screen(move_cursor=False)
    r = picture_on_screen(job["watch_png"], job.get("watch_scale"), shot=shot, report=rep, **kw)
    note, pointer = "", False
    if not r[0] and pointer_near_watch(job, r):
        if move_ok:
            rep = [] if report is not None else None
            shot = grab_screen(move_cursor=True)
            r = picture_on_screen(job["watch_png"], job.get("watch_scale"), shot=shot,
                                  report=rep, **kw)
            note = "checked again with the mouse pointer moved aside"
        else:
            pointer = True
            note = "the mouse pointer is on the picture"
    if report is not None:
        report.extend(rep)
    return r, note, pointer


def resolution_note(job):
    """Warning text when a fixed screen spot was picked at a different screen size."""
    if job.get("target_mode") == "window" or job.get("scale_with_screen") or uses_picture(job):
        return ""
    ps = job.get("pick_screen")
    cur = screen_size()
    if ps and tuple(ps) != cur:
        return (f"the screen is {cur[0]}×{cur[1]} now but this spot was picked on "
                f"{ps[0]}×{ps[1]}, so it may be off")
    return ""


# ---- job list columns (4.5.4): each view (All / Scheduled clicks / Screen watchers) shows
# the columns that matter for that kind of job; widths fit their text automatically
JOB_COLS = {          # id: (heading, minimum width, widest automatic width, anchor)
    "chk": ("☐", 38, 38, "center"),
    "status": ("Status", 90, 180, "w"),
    "kind": ("Type", 64, 110, "w"),
    "name": ("Name", 90, 320, "w"),
    "what": ("What it does", 140, 420, "w"),
    "target": ("Clicks at", 100, 300, "w"),
    "schedule": ("Schedule", 110, 260, "w"),
    "hours": ("Runs", 80, 260, "w"),
    "next": ("Next click", 100, 260, "w"),
    "countdown": ("Starts in", 80, 160, "w"),
    "watchfor": ("Watching for", 120, 340, "w"),
    "then": ("Then", 100, 300, "w"),
    "every": ("Checks", 90, 220, "w"),
    "seen": ("Picture", 110, 280, "w"),
    "nextcheck": ("Next check", 90, 170, "w"),
    "count": ("Clicks", 56, 90, "center"),
    "last": ("Last result", 110, 420, "w"),
}
JOB_VIEWS = {
    "all": ("chk", "status", "kind", "name", "what", "next", "countdown", "count", "last"),
    "click": ("chk", "status", "name", "target", "schedule", "hours", "next", "countdown",
              "count", "last"),
    "watch": ("chk", "status", "name", "watchfor", "then", "every", "seen", "nextcheck",
              "count", "last"),
}
VIEW_HEADINGS = {"all": {"next": "Next / last seen", "countdown": "In"}}
VIEW_DROP = {           # hidden first when the window is too narrow
    "all": ("count", "kind", "countdown", "what"),
    "click": ("count", "hours", "schedule", "countdown", "target"),
    "watch": ("count", "every", "then", "nextcheck", "watchfor"),
}


class RowVals(tuple):
    """A job-list row: the classic 9 values (status, name, target, button, schedule, next,
    countdown, count, last), plus `cells`, every column's text for the views."""


def step_row(job, k, st, groups=None):
    """A job-list row for one step of a job (shown when the job is expanded, 4.5.6)."""
    try:
        kind_, detail = describe_step(st, private=True, groups=groups)
    except Exception:
        kind_, detail = st.get("type", "step"), ""
    what = detail or kind_
    label = (st.get("label") or "").strip()
    name = f"      ↳ {k + 1}. {label or kind_}"
    r = RowVals(("", name, what, "", "", "", "", "", ""))
    r.cells = dict(status="   step", kind="  ↳ step", name=name, what=what, target=what,
                   schedule="", hours="", next="", countdown="", watchfor=what, then="",
                   every="", seen="", nextcheck="", count="", last="")
    return (f"step:{job['id']}:{k}", r, "step")


def test_vals(v):
    """Row values for a pending test row, in every view's columns."""
    status, name, pos, btn, sched, nxt, cd, count, last = v
    r = RowVals(v)
    r.cells = dict(status=status, kind="◆ Test", name=name, what=f"{sched} · {btn} · {pos}",
                   target=f"{btn} · {pos}", schedule=sched, hours="", next=nxt, countdown=cd,
                   watchfor="", then=f"{btn} · {pos}", every=sched, seen=nxt, nextcheck=cd,
                   count=count, last=last)
    return r


def watch_summary(j):
    """'Disappears · 120×40 · area · exact' - what a watcher looks for."""
    what = "Appears" if j.get("watch_trigger") == "appears" else "Disappears"
    size = ""
    try:
        if j.get("watch_png"):
            w, h = b64_to_img(j["watch_png"]).size
            size = f" · {w}×{h}"
    except Exception:
        pass
    where = " · area" if j.get("watch_area") else ""
    match = (f" · {int(j.get('watch_partial_pct', PARTIAL_DEFAULT_PCT))}% match"
             if j.get("watch_match") == "partial" else " · exact")
    return what + size + where + match


def watch_then(j):
    """What a watcher does when it fires."""
    n = len(j.get("steps") or [])
    steps = f" + {n} step{'s' if n != 1 else ''}" if n else ""
    if not j.get("main_click", True):
        return f"☰ {n} step{'s' if n != 1 else ''}"
    btn = j["button"].capitalize() + (" ×2" if j.get("clicks") == 2 else "")
    if j.get("watch_trigger") == "appears" and j.get("watch_click_picture"):
        return f"{btn} on the picture{steps}"
    return f"{btn} · {target_text(j)}{steps}"


def run_rules(j):
    """'Always', '08:00–22:00 Mon–Fri', plus limits - when a job may run."""
    parts = [describe_hours(j) if j.get("hours_on") else "Always"]
    if j.get("limit_clicks_on"):
        parts.append(f"max {j.get('limit_clicks')} clicks")
    if j.get("limit_until_on") and j.get("limit_until"):
        parts.append(f"until {j['limit_until']}")
    return " · ".join(parts)


def describe_watch(j):
    what = ("When picture appears" if j.get("watch_trigger") == "appears"
            else "If picture gone")
    area = " · area" if j.get("watch_area") else ""
    return f"{what} · every {fmt_compact(j.get('watch_interval_s', 30))}{area}"


def target_text(j):
    if not j.get("main_click", True):
        n = len(j.get("steps") or [])
        return f"☰ {n} step{'s' if n != 1 else ''} only"
    if uses_picture(j):
        where = (f" · {short_title(j['window_title'], 14)}"
                 if j.get("target_mode") == "window" and j.get("window_title") else "")
        return f"▣ Picture{where}"
    if j.get("target_mode") == "window" and j.get("window_title"):
        return f"⧉ {short_title(j['window_title'], 18)}  ({j.get('rel_x', 0)}, {j.get('rel_y', 0)})"
    return f"{j['x']}, {j['y']}"


def keep_awake(on):
    if not IS_WIN:
        return
    ES_CONTINUOUS, ES_SYSTEM, ES_DISPLAY = 0x80000000, 0x00000001, 0x00000002
    kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM | ES_DISPLAY if on else ES_CONTINUOUS)


def system_prefers_dark():
    if not IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except Exception:
        return False


def set_dark_titlebar(win, dark):
    if not IS_WIN:
        return
    try:
        win.update_idletasks()
        hwnd = user32.GetParent(win.winfo_id())
        val = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command():
    if FROZEN:
        return f'"{sys.executable}" --minimized'
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    return f'"{pyw}" "{PROGRAM_PATH}" --minimized'


def make_logo(size=64):
    """Clickue's logo: an eye whose pupil is a target, with a pointer - drawn in code so it's
    sharp at any size (header, title bar, tray, .exe icon)."""
    S = size * 4                                   # draw big, then shrink = smooth edges
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # rounded-square background with a blue -> violet diagonal gradient
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    c1, c2 = (37, 99, 235), (124, 58, 237)
    for i in range(2 * S):
        t = i / (2 * S - 1)
        col = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2)) + (255,)
        gd.line([(i, 0), (0, i)], fill=col, width=2)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=S // 4.2, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # eye (almond)
    import math
    cx, cy, w, h = S * 0.47, S * 0.47, S * 0.74, S * 0.36
    top = [(cx - w / 2 + w * k / 60, cy - h / 2 * math.sin(math.pi * k / 60)) for k in range(61)]
    bot = [(cx + w / 2 - w * k / 60, cy + h / 2 * math.sin(math.pi * k / 60)) for k in range(61)]
    d.polygon(top + bot, fill=(255, 255, 255, 255))
    # pupil = target
    r = S * 0.15
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(30, 41, 99, 255))
    r2 = S * 0.105
    d.ellipse((cx - r2, cy - r2, cx + r2, cy + r2), outline=(255, 255, 255, 255),
              width=max(2, S // 40))
    r3 = S * 0.035
    d.ellipse((cx - r3, cy - r3, cx + r3, cy + r3), fill=(255, 255, 255, 255))
    # pointer arrow (bottom right)
    ax, ay, k = S * 0.60, S * 0.56, S / 64
    arrow = [(0, 0), (0, 26), (7, 20), (12, 31), (17, 29), (12, 18), (21, 18)]
    pts = [(ax + x * k, ay + y * k) for x, y in arrow]
    d.polygon(pts, fill=(255, 255, 255, 255), outline=(30, 41, 99, 255))
    d.line(pts + [pts[0]], fill=(30, 41, 99, 255), width=max(2, S // 64), joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def write_icon_file(path):
    """Save the logo as a Windows .ico (used when building Clickue.exe)."""
    img = make_logo(256)
    img.save(path, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                        (128, 128), (256, 256)])


INSTALL_MARKER = os.path.join(PROGRAM_DIR, "install.ini")


def read_install_id():
    """The installer writes install.ini (a unique id per install) next to Clickue.exe.
    Returns that id, or '' when not installed with the installer (portable / source)."""
    try:
        import configparser
        cp = configparser.ConfigParser()
        cp.read(INSTALL_MARKER, encoding="utf-8")
        return cp.get("Install", "Id", fallback="").strip()
    except Exception:
        return ""


def data_folder_used():
    """Has Clickue's data folder ever been used (backups, history, log, tests)? Then old
    files from the very first versions must never be imported over it."""
    for n in ("backups", "clickue.log", "click_history.csv", "test_history.json", "run_history.csv",
              "jobs.json.corrupt", "settings.json.corrupt"):
        if os.path.exists(os.path.join(DATA_DIR, n)):
            return True
    return False


def count_saved_jobs(folder):
    """How many jobs are saved in a data folder (0 if none / unreadable)."""
    try:
        with open(os.path.join(folder, "jobs.json"), encoding="utf-8") as f:
            return len(json.load(f).get("jobs", []))
    except Exception:
        return 0


def migrate_old_data():
    """First start under the new name: copy the old data folder over (the old folder is
    left untouched as a backup). Returns True if something was copied."""
    try:
        if os.path.isdir(DATA_DIR) or not os.path.isdir(OLD_DATA_DIR):
            return False
        if count_saved_jobs(OLD_DATA_DIR) == 0:
            return False
        shutil.copytree(OLD_DATA_DIR, DATA_DIR)
        old_log = os.path.join(DATA_DIR, "autoclicker.log")
        if os.path.exists(old_log):
            try:
                os.replace(old_log, os.path.join(DATA_DIR, "previous-autoclicker.log"))
            except Exception:
                pass
        for n in ("autoclicker.log.1", "autoclicker.log.2"):
            try:
                os.remove(os.path.join(DATA_DIR, n))
            except Exception:
                pass
        if IS_WIN:
            try:   # the old start-with-Windows entry pointed at the old program
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, OLD_APP_ID)
            except Exception:
                pass
        return True
    except Exception:
        return False


def set_run_at_startup(enable):
    if not IS_WIN:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if enable:
                winreg.SetValueEx(k, APP_ID, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(k, APP_ID)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- popup helpers
# While one of our own message boxes / file pickers is open, popups must not treat the
# focus change as "clicked outside" and close themselves.
_UI_HOLD = [0, 0.0]   # [open message boxes, hold-until time]


def _held(fn):
    def wrapper(*a, **k):
        _UI_HOLD[0] += 1
        try:
            return fn(*a, **k)
        finally:
            _UI_HOLD[0] -= 1
            _UI_HOLD[1] = time.time() + 0.5
    return wrapper


for _n in ("showinfo", "showwarning", "showerror", "askyesno", "askyesnocancel",
           "askokcancel"):
    if hasattr(messagebox, _n):
        setattr(messagebox, _n, _held(getattr(messagebox, _n)))
for _n in ("asksaveasfilename", "askopenfilename", "askdirectory"):
    if hasattr(filedialog, _n):
        setattr(filedialog, _n, _held(getattr(filedialog, _n)))


def ui_held():
    return _UI_HOLD[0] > 0 or time.time() < _UI_HOLD[1]


def belongs_to(widget_top, win):
    """True if widget_top is win itself or one of its own child windows."""
    w = widget_top
    while w is not None:
        if w is win:
            return True
        w = getattr(w, "master", None)
    return False


def dropdown_open(win):
    """True if a dropdown list (combobox) inside win is currently showing."""
    stack = [win]
    while stack:
        w = stack.pop()
        try:
            if isinstance(w, ttk.Combobox):
                pd = str(w) + ".popdown"
                if int(w.tk.call("winfo", "exists", pd)) and \
                        int(w.tk.call("winfo", "ismapped", pd)):
                    return True
            stack.extend(w.winfo_children())
        except Exception:
            pass
    return False


def pointer_over(win):
    """True if the mouse is over win or one of its own child windows/dropdowns."""
    try:
        px, py = win.winfo_pointerxy()
        under = win.winfo_containing(px, py)
    except KeyError:
        return True          # over a Tk-internal window (e.g. a dropdown list) of ours
    except Exception:
        return False
    if under is None:
        return False
    try:
        return belongs_to(under.winfo_toplevel(), win)
    except Exception:
        return True


def close_on_click_outside(win, app, on_outside):
    """Close the popup when the user clicks somewhere else (the main window, another popup,
    another program, the desktop). Its own dropdowns, message boxes and child windows don't
    count as "outside"."""
    def check():
        try:
            if not win.winfo_exists() or not win.winfo_viewable():
                return
        except Exception:
            return
        if ui_held() or getattr(app, "_spot_busy", False) or getattr(win, "_hold", 0):
            return
        if dropdown_open(win) or pointer_over(win):
            return
        try:
            f = win.focus_get()
        except Exception:
            return          # focus is in something Tk can't name (e.g. a dropdown list)
        if f is not None and belongs_to(f.winfo_toplevel(), win):
            return
        on_outside()

    def focus_out(_e):
        try:
            win.after(180, check)
        except Exception:
            pass
    win.bind("<FocusOut>", focus_out, add="+")


# ---- 4.5.1: double-click a column border to fit the column (like a spreadsheet)
def column_fit_width(tree, col, pad=26, limit=900):
    """Width that shows the column's heading and every cell's text in full."""
    try:
        st = ttk.Style(tree)
        f_cell = tkfont.Font(font=st.lookup("Treeview", "font") or "TkDefaultFont")
        f_head = tkfont.Font(font=st.lookup("Treeview.Heading", "font") or "TkHeadingFont")
    except Exception:
        f_cell = f_head = tkfont.nametofont("TkDefaultFont")
    w = f_head.measure(str(tree.heading(col, "text") or ""))
    stack = list(tree.get_children(""))
    seen = 0
    while stack and seen < 5000:
        iid = stack.pop()
        seen += 1
        try:
            w = max(w, f_cell.measure(str(tree.set(iid, col))))
            stack.extend(tree.get_children(iid))
        except Exception:
            pass
    try:
        lo = int(tree.column(col, "minwidth"))
    except Exception:
        lo = 20
    return int(min(limit, max(lo, w + pad)))


def _display_cols(tree):
    dc = tree["displaycolumns"]
    if isinstance(dc, str):
        dc = (dc,)
    if not dc or dc[0] == "#all":
        dc = tree["columns"]
    return list(dc)


def _autofit_double(e):
    tree = e.widget
    try:
        region = tree.identify_region(e.x, e.y)
    except Exception:
        return None
    if region == "separator":
        try:
            n = int(str(tree.identify_column(e.x - 4)).lstrip("#")) - 1
            col = _display_cols(tree)[n]
        except Exception:
            return "break"
        # Let the table start a column drag as usual (a quick second click on a border is
        # often the start of a drag; swallowing it made dragging feel "sticky"), then fit.
        try:
            tree.tk.call("ttk::treeview::Press", str(tree), e.x, e.y)
        except Exception:
            pass
        tree._dragging_col = None

        def fit():
            try:
                w = column_fit_width(tree, col)
                tree.column(col, width=w, stretch=False)
            except Exception:
                return
            cb = getattr(tree, "_autofit_cb", None)
            if cb:
                try:
                    cb(col, w)
                except Exception:
                    pass
            try:
                tree.event_generate("<<ColumnFitted>>")
            except Exception:
                pass
        tree.after_idle(fit)
        return "break"
    if region == "heading":
        return "break"          # double-clicking a heading does nothing else
    return None


def _autofit_press(e):
    tree = e.widget
    try:
        if tree.identify_region(e.x, e.y) == "separator":
            n = int(str(tree.identify_column(e.x - 4)).lstrip("#")) - 1
            tree._dragging_col = _display_cols(tree)[n]
        else:
            tree._dragging_col = None
    except Exception:
        tree._dragging_col = None


def _autofit_release(e):
    tree = e.widget
    col = getattr(tree, "_dragging_col", None)
    tree._dragging_col = None
    cb = getattr(tree, "_autofit_cb", None)
    if col and cb:
        try:
            w = int(tree.column(col, "width"))
            tree.column(col, stretch=False)
            cb(col, w)
        except Exception:
            pass


def enable_column_fit(tree, on_change=None):
    """Double-click the border between two column headings to size the column on its left
    to its contents. `on_change(col, width)` is told about fitted or dragged widths."""
    tree._autofit_cb = on_change
    tags = tree.bindtags()
    if "ColumnFit" not in tags:
        tree.bindtags(("ColumnFit",) + tuple(tags))
    try:
        if not tree.bind_class("ColumnFit", "<Double-1>"):
            tree.bind_class("ColumnFit", "<Double-1>", _autofit_double)
            tree.bind_class("ColumnFit", "<ButtonPress-1>", _autofit_press)
            tree.bind_class("ColumnFit", "<ButtonRelease-1>", _autofit_release)
    except Exception:
        pass
    return tree


# ---------------------------------------------------------------- helpers
def fmt_dur(sec):
    sec = int(max(0, round(sec)))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def fmt_time(ts):
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%a %m/%d %H:%M:%S")


def stamp():
    return datetime.now().strftime("%m/%d %H:%M:%S")


def parse_hms_clock(text):
    """'08:00' or '8:00:00' -> next timestamp at that time of day (today or tomorrow)."""
    text = text.strip()
    if not text:
        return None
    parts = [int(p) for p in text.split(":")]
    while len(parts) < 3:
        parts.append(0)
    h, m, s = parts[:3]
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError
    now = datetime.now()
    t = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t.timestamp()


def read_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        try:
            shutil.copy2(path, path + ".corrupt")
        except Exception:
            pass
        messagebox.showwarning(APP_NAME, f"{os.path.basename(path)} could not be read and was "
                                         f"set aside as a .corrupt copy.\n\n{e}")
        return None


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ======================================================================== Clickue extras
# ---- active hours ---------------------------------------------------------------------
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def parse_hhmm(text):
    h, m = str(text).strip().split(":")[:2]
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return h * 60 + m


def in_active_hours(job, ts=None):
    """True if the job may run at this moment (always True when active hours are off)."""
    if not job.get("hours_on"):
        return True
    try:
        a, b = parse_hhmm(job.get("hours_from", "08:00")), parse_hhmm(job.get("hours_to", "22:00"))
    except Exception:
        return True
    days = set(job.get("hours_days") or range(7))
    dt = datetime.fromtimestamp(ts or time.time())
    mins, wd = dt.hour * 60 + dt.minute, dt.weekday()
    if a == b:                                   # whole day
        return wd in days
    if a < b:
        return wd in days and a <= mins < b
    if mins >= a:                                # overnight window, evening part
        return wd in days
    if mins < b:                                 # overnight window, after midnight
        return (wd - 1) % 7 in days
    return False


def next_active_start(job, ts=None):
    """When the job's next active period starts (timestamp)."""
    ts = ts or time.time()
    try:
        a = parse_hhmm(job.get("hours_from", "08:00"))
        b = parse_hhmm(job.get("hours_to", "22:00"))
    except Exception:
        return ts
    days = set(job.get("hours_days") or range(7))
    base = datetime.fromtimestamp(ts).replace(hour=0, minute=0, second=0, microsecond=0)
    for k in range(0, 9):
        d = base + timedelta(days=k)
        if d.weekday() not in days:
            continue
        start = d + timedelta(minutes=(0 if a == b else a))
        if start.timestamp() > ts:
            return start.timestamp()
    return ts + 3600


def describe_hours(job):
    if not job.get("hours_on"):
        return ""
    days = sorted(set(job.get("hours_days") or range(7)))
    if days == list(range(7)):
        dtxt = "every day"
    elif days == list(range(5)):
        dtxt = "Mon–Fri"
    elif days == [5, 6]:
        dtxt = "weekends"
    else:
        dtxt = ",".join(DAY_NAMES[d] for d in days)
    a, b = job.get("hours_from", "08:00"), job.get("hours_to", "22:00")
    return f"{dtxt}" if a == b else f"{a}–{b} {dtxt}"


# ---- keyboard input for multi-step jobs ----------------------------------------------------
VK_NAMES = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "printscreen": 0x2C, "pause": 0x13, "capslock": 0x14, "menu": 0x5D, "apps": 0x5D,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
    **{f"num{i}": 0x60 + i for i in range(10)},
}
EXTENDED_VKS = {0x2E, 0x2D, 0x24, 0x23, 0x21, 0x22, 0x26, 0x28, 0x25, 0x27}
MODIFIER_VKS = {0x11, 0x10, 0x12, 0x5B}


def parse_combo(text):
    """'Ctrl+Shift+S' -> [0x11, 0x10, 0x53]. Raises ValueError if a key isn't known."""
    keys = []
    for part in str(text).replace(" ", "").split("+"):
        if not part:
            continue
        p = part.lower()
        if p in VK_NAMES:
            keys.append(VK_NAMES[p])
        elif len(p) == 1 and (p.isascii() and (p.isalpha() or p.isdigit())):
            keys.append(ord(p.upper()))
        elif re.fullmatch(r"0x[0-9a-f]{2}", p) and 0 < int(p, 16) < 0xFF:
            keys.append(int(p, 16))
        else:
            raise ValueError(f"unknown key “{part}”")
    if not keys:
        raise ValueError("no key given")
    if len(keys) > 6:
        raise ValueError("too many keys at once")
    return keys


if IS_WIN:
    ULONG_PTR = ctypes.c_size_t

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wt.DWORD), ("wParamL", wt.WORD), ("wParamH", wt.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wt.DWORD), ("u", _INPUTUNION)]

    user32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    user32.SendInput.restype = wt.UINT

    def _key_input(vk=0, scan=0, flags=0):
        i = _INPUT()
        i.type = 1                                  # INPUT_KEYBOARD
        i.u.ki = _KEYBDINPUT(vk, scan, flags, 0, 0)
        return i

    def _send(inputs):
        arr = (_INPUT * len(inputs))(*inputs)
        return user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))


def send_text(text):
    """Type text into whatever has keyboard focus (any characters, via Unicode input)."""
    if not IS_WIN:
        return False, "typing only works on Windows"
    data = str(text).encode("utf-16-le")
    units = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
    for u in units:
        if u == 0x0A:                               # newline -> Enter
            _send([_key_input(0x0D), _key_input(0x0D, flags=0x0002)])
        else:
            _send([_key_input(0, u, 0x0004), _key_input(0, u, 0x0004 | 0x0002)])
        time.sleep(0.012)
    return True, "typed"


def press_keys(combo):
    """Press a key combination like 'Ctrl+S', 'Enter' or 'Alt+F4'."""
    if not IS_WIN:
        return False, "keys only work on Windows"
    try:
        keys = parse_combo(combo)
    except ValueError as e:
        return False, str(e)
    downs, ups = [], []
    for vk in keys:
        ext = 0x0001 if vk in EXTENDED_VKS else 0
        downs.append(_key_input(vk, flags=ext))
        ups.insert(0, _key_input(vk, flags=ext | 0x0002))
    _send(downs)
    time.sleep(0.03)
    _send(ups)
    return True, "pressed"


# ---- phone alerts (Discord / Telegram) ----------------------------------------------------
ALERT_EVENTS = (("watch", "A watcher clicked"), ("problem", "A click was missed or failed"),
                ("finished", "A job finished (limit reached)"),
                ("test", "Scheduled test results"))


# Security: alerts may only go to these hosts, over HTTPS with certificate checks, without
# following redirects, with short timeouts and a small response limit. There is no way to
# post to any other address.
DISCORD_HOSTS = ("discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com")
TELEGRAM_HOST = "api.telegram.org"
ALERT_TIMEOUT_S = 10
ALERT_MAX_RESPONSE = 64 * 1024
ALERT_MIN_GAP_S = 2.0               # per service, between two alerts
ALERT_MAX_PER_HOUR = 60             # per service; more are dropped (and logged once)
SECRET_KEYS = ("alert_discord", "alert_tg_token", "alert_tg_chat")
_DISCORD_PATH_RE = re.compile(r"^/api/webhooks/\d{5,25}/[A-Za-z0-9_\-]{20,120}$")
_TG_TOKEN_RE = re.compile(r"^\d{3,15}:[A-Za-z0-9_\-]{20,64}$")
_TG_CHAT_RE = re.compile(r"^(-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{3,63})$")
_ALERT_LOCK = threading.Lock()
_ALLOW_PLAIN_HTTP_FOR_TESTS = False       # only the tests' local redirect check sets this
_ALERT_SENT = {}                    # service -> list of send times (last hour)


def check_discord_url(url):
    """(ok, reason). Only https://discord.com/api/webhooks/<id>/<token> style URLs."""
    from urllib.parse import urlsplit
    try:
        u = urlsplit(url.strip())
    except Exception:
        return False, "not a valid web address"
    if u.scheme != "https":
        return False, "must start with https://"
    if (u.hostname or "").lower() not in DISCORD_HOSTS or u.port not in (None, 443):
        return False, "must be a discord.com webhook address"
    if u.username or u.password or u.fragment:
        return False, "must be a plain Discord webhook address"
    if not _DISCORD_PATH_RE.match(u.path):
        return False, "doesn't look like a Discord webhook (…/api/webhooks/…)"
    return True, ""


def check_telegram(token, chat):
    if not _TG_TOKEN_RE.match(token or ""):
        return False, "the bot token doesn't look right (it looks like 123456:ABC…)"
    if not _TG_CHAT_RE.match(chat or ""):
        return False, "the chat id must be a number (or @channelname)"
    return True, ""


def redact(text, secrets=()):
    """Remove secrets (webhook tokens, bot tokens, given values) from text for logs/errors."""
    text = str(text)
    for s in secrets:
        s = str(s or "").strip()
        if len(s) >= 6:
            text = text.replace(s, "[hidden]")
    text = re.sub(r"(api/webhooks/\d+/)[A-Za-z0-9_\-]+", r"\1[hidden]", text)
    text = re.sub(r"bot\d{3,15}:[A-Za-z0-9_\-]{20,64}", "bot[hidden]", text)
    text = re.sub(r"\b\d{3,15}:[A-Za-z0-9_\-]{30,64}\b", "[hidden]", text)
    return text


def tls_context():
    """4.6.1: an SSL context that checks certificates and host names. It trusts Windows'
    certificate store plus the bundled certifi list of trusted root certificates. Windows
    only adds some roots when something asks for them, so on some PCs GitHub's root isn't
    in the store yet and the check failed ("unable to get local issuer certificate").
    Checks are never turned off."""
    import ssl
    ctx = ssl.create_default_context()        # verifies certificates and host names
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass                                  # no certifi (source copy): Windows' store only
    return ctx


def friendly_net_error(e):
    """Short text for a network error; explains certificate failures in plain words."""
    t = str(e)
    if "CERTIFICATE_VERIFY_FAILED" in t:
        return ("the secure connection couldn't be checked (certificate not trusted). "
                "Something on this PC or network may be intercepting HTTPS - for example "
                "antivirus web scanning or a company proxy. Clickue won't connect without "
                "a valid certificate. Details: " + t)[:400]
    return t[:200]


def _http_post(url, body, content_type):
    """POST over HTTPS with certificate checks; no redirects; bounded time and response.
    Returns the HTTP status. Raises on errors. (Replaced by a fake in the tests.)"""
    import urllib.request
    if not (url.startswith("https://") or (_ALLOW_PLAIN_HTTP_FOR_TESTS and
                                           url.startswith("http://127.0.0.1:"))):
        raise ValueError("only https addresses are allowed")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None                       # a 3xx becomes an error instead of being followed

    ctx = tls_context()                       # verifies certificates and host names
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": content_type, "User-Agent": f"{APP_NAME}/{VERSION}"})
    with opener.open(req, timeout=ALERT_TIMEOUT_S) as r:
        r.read(ALERT_MAX_RESPONSE)
        return r.status


# ---- 4.6: updates (optional; Preferences → General). Only GitHub, only HTTPS, only when on.
UPDATE_REPO = "jnssylvest/clickue"
UPDATE_API = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
UPDATE_HOSTS = ("api.github.com", "github.com", "objects.githubusercontent.com",
                "release-assets.githubusercontent.com")
UPDATE_MAX_API = 512 * 1024              # the release description
UPDATE_MAX_FILE = 400 * 1024 * 1024      # installer / zip
UPDATE_TIMEOUT_S = 20
UPDATE_EVERY_S = 24 * 3600               # automatic check at most once a day
_HTTPS_GET = None                        # tests replace the network with a fake


def parse_version(text):
    """'v4.6.0' / '4.6' -> (4, 6, 0); None if it isn't a version."""
    m = re.match(r"^\s*v?(\d{1,4})\.(\d{1,4})(?:\.(\d{1,4}))?\s*$", str(text or ""))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)


def newer_version(remote, local=None):
    r, l_ = parse_version(remote), parse_version(local or VERSION)
    return bool(r and l_ and r > l_)


def https_get(url, max_bytes, dest=None, progress=None, stop=None):
    """GET over HTTPS from GitHub only (UPDATE_HOSTS), with certificate checks, at most 5
    redirects and only to those hosts, a time limit and a size limit. Returns the bytes, or
    with `dest` writes the file there (via .part) and returns its size. Raises on errors."""
    if _HTTPS_GET is not None:
        return _HTTPS_GET(url, max_bytes, dest, progress)
    import urllib.error
    import urllib.parse
    import urllib.request

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    ctx = tls_context()
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPSHandler(context=ctx))
    for _ in range(6):
        u = urllib.parse.urlsplit(url)
        if u.scheme != "https" or u.hostname not in UPDATE_HOSTS:
            raise ValueError(f"refused to connect to {u.hostname or url} (not GitHub)")
        req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{VERSION}",
                                                   "Accept": "*/*"})
        try:
            r = opener.open(req, timeout=UPDATE_TIMEOUT_S)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise
        with r:
            total = int(r.headers.get("Content-Length") or 0)
            if total > max_bytes:
                raise ValueError("the download is bigger than expected")
            if dest is None:
                data = r.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ValueError("the answer is bigger than expected")
                return data
            got = 0
            part = dest + ".part"
            with open(part, "wb") as fh:
                while True:
                    if stop and stop():
                        raise RuntimeError("cancelled")
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    got += len(chunk)
                    if got > max_bytes:
                        raise ValueError("the download is bigger than expected")
                    fh.write(chunk)
                    if progress:
                        progress(got, total)
            os.replace(part, dest)
            return got
    raise ValueError("too many redirects")


def fetch_latest_release():
    """What GitHub says is the newest release: dict(version, name, notes, page, assets)."""
    data = json.loads(https_get(UPDATE_API, UPDATE_MAX_API).decode("utf-8", "replace"))
    tag = str(data.get("tag_name", ""))
    ver = parse_version(tag)
    if not ver:
        raise ValueError(f"unexpected release name {tag[:40]!r}")
    assets = {}
    for a in data.get("assets") or []:
        n, u = str(a.get("name", "")), str(a.get("browser_download_url", ""))
        if re.match(r"^[\w.\-]{1,100}$", n) and u.startswith("https://github.com/"):
            assets[n] = u
    page = str(data.get("html_url", ""))
    if not page.startswith(f"https://github.com/{UPDATE_REPO}/"):
        page = f"https://github.com/{UPDATE_REPO}/releases"
    return dict(version="%d.%d.%d" % ver if ver[2] else "%d.%d" % ver[:2],
                name=str(data.get("name") or tag)[:120],
                notes=str(data.get("body") or "")[:20000], page=page, assets=assets)


def install_kind():
    """How this copy was installed: "installer", "portable" or "source"."""
    if not FROZEN or not IS_WIN:
        return "source"
    if read_install_id():
        return "installer"
    return "portable"


def update_asset_name(kind, version):
    return (f"Clickue-Setup-{version}.exe" if kind == "installer"
            else f"Clickue-Portable-{version}.zip" if kind == "portable" else "")


def expected_sha256(sums_text, name):
    """The SHA-256 for `name` in a SHA256SUMS.txt ("<hash>  <file>" lines), or ""."""
    for line in str(sums_text).splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.match(r"^[0-9a-fA-F]{64}$",
                                                                          parts[0]):
            return parts[0].lower()
    return ""


def file_sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download_update(info, kind, progress=None, stop=None):
    """Download this copy's package of the release into the data folder's "updates" folder
    and check it against the release's SHA256SUMS.txt. Returns the file's path."""
    name = update_asset_name(kind, info["version"])
    url = info["assets"].get(name)
    if not url:
        raise ValueError(f"the release has no {name}")
    sums_url = info["assets"].get("SHA256SUMS.txt")
    if not sums_url:
        raise ValueError("the release has no checksums (SHA256SUMS.txt), so it can't be checked")
    want = expected_sha256(https_get(sums_url, 64 * 1024).decode("ascii", "replace"), name)
    if not want:
        raise ValueError(f"{name} isn't listed in SHA256SUMS.txt")
    folder = data_path("updates")
    os.makedirs(folder, exist_ok=True)
    for old in os.listdir(folder):               # only our own old downloads
        if re.match(r"^Clickue-(Setup|Portable)-[\d.]+\.(exe|zip)(\.part)?$", old):
            try:
                os.remove(os.path.join(folder, old))
            except OSError:
                pass
    dest = os.path.join(folder, name)
    https_get(url, UPDATE_MAX_FILE, dest=dest, progress=progress, stop=stop)
    got = file_sha256(dest)
    if got != want:
        os.remove(dest)
        raise ValueError("the download doesn't match its checksum - it was deleted. Try again "
                         "later or download it from the release page.")
    return dest


def _try_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def extract_portable_exe(zip_path, folder):
    """Take Clickue.exe out of a downloaded portable zip (only that file, checked)."""
    import zipfile
    with zipfile.ZipFile(zip_path) as z:
        info = next((i for i in z.infolist() if i.filename == "Clickue.exe"), None)
        if info is None or info.file_size > UPDATE_MAX_FILE:
            raise ValueError("the zip has no usable Clickue.exe")
        out = os.path.join(folder, "Clickue.new.exe")
        with z.open(info) as src, open(out, "wb") as dst:
            shutil.copyfileobj(src, dst)
    return out


def _alert_allowed(service, now=None):
    now = now or time.time()
    with _ALERT_LOCK:
        sent = [t for t in _ALERT_SENT.get(service, []) if now - t < 3600]
        if sent and now - sent[-1] < ALERT_MIN_GAP_S:
            _ALERT_SENT[service] = sent
            return False, "too soon after the previous alert"
        if len(sent) >= ALERT_MAX_PER_HOUR:
            _ALERT_SENT[service] = sent
            return False, f"more than {ALERT_MAX_PER_HOUR} alerts in an hour"
        sent.append(now)
        _ALERT_SENT[service] = sent
        return True, ""


def send_alert(settings, text, limit=True):
    """Send text to the configured services. Returns a list of (service, ok, message).
    Messages never contain the webhook URL or bot token."""
    import urllib.parse
    results = []
    msg = f"{APP_NAME}: {text}"
    secrets = [settings.get(k) for k in SECRET_KEYS]
    url = (settings.get("alert_discord") or "").strip()
    if url:
        good, why = check_discord_url(url)
        allowed, why2 = _alert_allowed("Discord") if (good and limit) else (good, why)
        if not good:
            results.append(("Discord", False, why))
        elif not allowed:
            results.append(("Discord", False, "skipped: " + why2))
        else:
            try:
                _http_post(url, json.dumps({"content": msg[:1900],
                                            "allowed_mentions": {"parse": []}}).encode(),
                           "application/json")
                results.append(("Discord", True, "sent"))
            except Exception as e:
                results.append(("Discord", False, redact(str(e), secrets)[:200]))
    tok = (settings.get("alert_tg_token") or "").strip()
    chat = (settings.get("alert_tg_chat") or "").strip()
    if tok or chat:
        good, why = check_telegram(tok, chat)
        allowed, why2 = _alert_allowed("Telegram") if (good and limit) else (good, why)
        if not good:
            results.append(("Telegram", False, why))
        elif not allowed:
            results.append(("Telegram", False, "skipped: " + why2))
        else:
            try:
                body = urllib.parse.urlencode({"chat_id": chat, "text": msg[:3900]}).encode()
                _http_post(f"https://{TELEGRAM_HOST}/bot{tok}/sendMessage", body,
                           "application/x-www-form-urlencoded")
                results.append(("Telegram", True, "sent"))
            except Exception as e:
                results.append(("Telegram", False, redact(str(e), secrets)[:200]))
    if not results:
        results.append(("Alerts", False, "no service set up"))
    return results


# ---- click history (CSV) --------------------------------------------------------------------
HISTORY_PATH = os.path.join(DATA_DIR, "click_history.csv")
HISTORY_FIELDS = ("time", "job", "kind", "result", "x", "y", "how", "detail")
HISTORY_MAX_ROWS = 50000
_HIST_LOCK = threading.Lock()


def append_history(**row):
    import csv
    row.setdefault("time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        with _HIST_LOCK:
            new = not os.path.exists(HISTORY_PATH)
            with open(HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
                if new:
                    w.writeheader()
                w.writerow({k: row.get(k, "") for k in HISTORY_FIELDS})
    except Exception:
        pass


def read_history():
    import csv
    try:
        with _HIST_LOCK, open(HISTORY_PATH, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def trim_history():
    """Keep the history file from growing forever (keeps the newest rows)."""
    import csv
    rows = read_history()
    if len(rows) <= HISTORY_MAX_ROWS:
        return
    rows = rows[-HISTORY_MAX_ROWS:]
    try:
        with _HIST_LOCK:
            tmp = HISTORY_PATH + ".tmp"
            with open(tmp, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            os.replace(tmp, HISTORY_PATH)
    except Exception:
        pass


def rewrite_history(keep):
    """Delete click-history rows for good: keeps only rows where keep(row) is true (4.5.6).
    Returns how many rows were deleted."""
    import csv
    rows = read_history()
    kept = [r for r in rows if keep(r)]
    with _HIST_LOCK:
        tmp = HISTORY_PATH + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(kept)
        os.replace(tmp, HISTORY_PATH)
    return len(rows) - len(kept)


def job_stats(rows, name):
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    week = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    mine = [r for r in rows if r.get("job") == name]
    ok = [r for r in mine if r.get("result") == "ok"]
    bad = [r for r in mine if r.get("result") != "ok"]
    return dict(total=len(ok), today=sum(1 for r in ok if r["time"].startswith(today)),
                week=sum(1 for r in ok if r["time"] >= week), problems=len(bad),
                last=ok[-1]["time"] if ok else "never",
                last_problem=(bad[-1]["time"] + " - " + bad[-1].get("detail", "")) if bad else "none",
                kinds={k: sum(1 for r in ok if r.get("kind") == k)
                       for k in ("scheduled", "watcher", "test", "manual")})


# ---- backups --------------------------------------------------------------------------------
BACKUP_DIR = os.path.join(DATA_DIR, "backups")


def make_backup(jobs, settings, tag="auto", groups=None):
    """Save jobs (and settings, without alert credentials) to the backups folder."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    skip = set(RUNTIME_KEYS) | {"last_result", "last_run"}
    data = {"app": APP_ID, "version": VERSION, "schema": SCHEMA_VERSION, "kind": "backup",
            "tag": tag, "created": datetime.now().isoformat(timespec="seconds"),
            "jobs": [{k: v for k, v in j.items() if k not in skip} for j in jobs],
            "groups": list(groups or []),
            "settings": {k: v for k, v in settings.items()
                         if k not in ("main_geom", "tests_geom", "dlg_geom") + SECRET_KEYS}}
    path = os.path.join(BACKUP_DIR, f"{datetime.now():%Y-%m-%d_%H%M%S}_{tag}.json")
    write_json(path, data)
    return path


def list_backups():
    out = []
    try:
        for n in os.listdir(BACKUP_DIR):
            if n.endswith(".json"):
                p = os.path.join(BACKUP_DIR, n)
                try:
                    with open(p, encoding="utf-8") as f:
                        d = json.load(f)
                    out.append(dict(path=p, name=n, created=d.get("created", ""),
                                    jobs=len(d.get("jobs", [])), tag=d.get("tag", "")))
                except Exception:
                    pass
    except Exception:
        pass
    return sorted(out, key=lambda b: b["name"], reverse=True)


def prune_backups(keep):
    autos = [b for b in list_backups() if b["tag"] == "auto"]
    for b in autos[max(1, int(keep)):]:
        try:
            os.remove(b["path"])
        except Exception:
            pass


# ======================================================================== Clickue 4.5
# ---- data folder helpers --------------------------------------------------------------------
SCHEMA_VERSION = 2          # jobs.json / exports: 1 = up to 4.4, 2 = 4.5 (groups, new steps)


def data_path(*parts):
    """A path inside the data folder (computed when called, so tests can move DATA_DIR)."""
    return os.path.join(DATA_DIR, *parts)


def is_clickue_data_dir(path):
    """True only for a folder that is plainly Clickue's own data folder. Used before any
    recursive delete, so a wrong or tampered path can never remove something else."""
    try:
        p = os.path.abspath(path)
    except Exception:
        return False
    if os.path.basename(p) not in (APP_ID, "ClickueData", "." + APP_ID):
        return False
    home = os.path.abspath(os.path.expanduser("~"))
    drive_root = os.path.abspath(os.path.splitdrive(p)[0] + os.sep)
    if p in (home, drive_root, os.path.abspath(os.sep)) or len(p.rstrip("\\/")) < 6:
        return False
    if not os.path.isdir(p) or os.path.islink(p):
        return False
    try:
        names = set(os.listdir(p))
    except Exception:
        return False
    return not names or bool(names & {"settings.json", "jobs.json", "clickue.log", "backups",
                                     "test_history.json", "click_history.csv"})


# ---- protected secrets (Windows DPAPI, opt-in) ----------------------------------------------
if IS_WIN:
    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    try:
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), wt.LPCWSTR, ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p,
            ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_DATA_BLOB)]
        crypt32.CryptProtectData.restype = wt.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB), ctypes.c_void_p, ctypes.POINTER(_DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(_DATA_BLOB)]
        crypt32.CryptUnprotectData.restype = wt.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        HAVE_DPAPI = True
    except Exception:
        HAVE_DPAPI = False
else:
    HAVE_DPAPI = False

_DPAPI_ENTROPY = b"Clickue protected text v1"


def _blob(data):
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf


def protect_text(text):
    """Encrypt text for this Windows user account (DPAPI). Returns 'dpapi:<base64>'."""
    if not HAVE_DPAPI:
        raise RuntimeError("protected storage needs Windows")
    data_in, b1 = _blob(str(text).encode("utf-8"))
    ent, b2 = _blob(_DPAPI_ENTROPY)
    out = _DATA_BLOB()
    if not crypt32.CryptProtectData(ctypes.byref(data_in), "Clickue", ctypes.byref(ent), None,
                                    None, 0x1, ctypes.byref(out)):      # UI_FORBIDDEN
        raise RuntimeError("Windows couldn't protect the text")
    try:
        raw = ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))
    return "dpapi:" + base64.b64encode(raw).decode("ascii")


def unprotect_text(value):
    """Decrypt a 'dpapi:' value. Raises ValueError when it can't be read here (another
    Windows account or computer)."""
    if not str(value).startswith("dpapi:"):
        return str(value)
    if not HAVE_DPAPI:
        raise ValueError("protected text can only be read on Windows")
    try:
        raw = base64.b64decode(str(value)[6:])
    except Exception:
        raise ValueError("protected text is damaged")
    data_in, b1 = _blob(raw)
    ent, b2 = _blob(_DPAPI_ENTROPY)
    out = _DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(data_in), None, ctypes.byref(ent), None,
                                      None, 0x1, ctypes.byref(out)):
        raise ValueError("this text was protected by another Windows account or computer")
    try:
        return ctypes.string_at(out.pbData, out.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


# ---- limits and validation for saved / imported jobs -----------------------------------------
MAX_IMPORT_BYTES = 50 * 1024 * 1024
MAX_JOBS = 2000
MAX_STEPS = 2000
MAX_TYPE_CHARS = 20_000          # typing is ~80 characters a second
MAX_PASTE_CHARS = 200_000
MAX_PNG_B64 = 6 * 1024 * 1024
MAX_PNG_SIDE = 8000
MAX_PATH_POINTS = 2000
MAX_NAME = 200
MAX_REPEAT = 10_000
MAX_RUN_LIMIT_S = 24 * 3600
VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
STEP_TYPES = ("click", "wait", "waitpic", "type", "paste", "key", "move", "drag", "mouse",
              "scroll", "keyhold", "if", "else", "end", "repeat", "set", "group")
PASTE_KEYS = ("Ctrl+V", "Shift+Insert", "Ctrl+Shift+V")
COND_KINDS = ("picture", "window", "var")
VAR_OPS = ("==", "!=", "<", ">", "<=", ">=", "contains")


def _clamp_num(v, lo, hi, default, as_int=True):
    try:
        f = float(v)
        if f != f or f in (float("inf"), float("-inf")):
            raise ValueError
    except Exception:
        return default
    f = min(hi, max(lo, f))
    return int(round(f)) if as_int else round(f, 3)


def _clean_str(v, n, default=""):
    if v is None:
        return default
    if not isinstance(v, str):
        v = str(v)
    return v[:n]


def clean_png(value):
    """A saved picture (PNG, base64) if it is a reasonable, readable image, else ''."""
    if not isinstance(value, str) or not value:
        return ""
    if len(value) > MAX_PNG_B64:
        return ""
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:
        return ""
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ""
    if HAVE_PIL:
        try:
            with Image.open(io.BytesIO(raw)) as im:
                w, h = im.size
            if not (1 <= w <= MAX_PNG_SIDE and 1 <= h <= MAX_PNG_SIDE):
                return ""
        except Exception:
            return ""
    return value


def _clean_point(v):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return [_clamp_num(v[0], -100000, 100000, 0), _clamp_num(v[1], -100000, 100000, 0)]
    return None


def _clean_rect(v):
    if isinstance(v, (list, tuple)) and len(v) == 4:
        r = [_clamp_num(x, -100000, 100000, 0) for x in v]
        if r[2] >= 16 and r[3] >= 16:
            return r
    return None


def _clean_path(v):
    """[[t, x, y], ...] with increasing times."""
    out, last = [], -1.0
    for p in (v if isinstance(v, list) else [])[:MAX_PATH_POINTS]:
        if not (isinstance(p, (list, tuple)) and len(p) == 3):
            continue
        t = _clamp_num(p[0], 0, 3600, 0, as_int=False)
        t = max(t, last)
        last = t
        out.append([t, _clamp_num(p[1], -100000, 100000, 0), _clamp_num(p[2], -100000, 100000, 0)])
    return out


def clean_cond(c):
    c = c if isinstance(c, dict) else {}
    kind = c.get("kind") if c.get("kind") in COND_KINDS else "picture"
    out = {"kind": kind}
    if kind == "picture":
        out.update(png=clean_png(c.get("png")),
                   state="gone" if c.get("state") == "gone" else "shown",
                   area=_clean_rect(c.get("area")),
                   wait=_clamp_num(c.get("wait", 0), 0, STEP_MAX_WAIT_S, 0, as_int=False))
    elif kind == "window":
        out.update(title=_clean_str(c.get("title"), 300).strip(),
                   state="closed" if c.get("state") == "closed" else "open",
                   wait=_clamp_num(c.get("wait", 0), 0, STEP_MAX_WAIT_S, 0, as_int=False))
    else:
        var = _clean_str(c.get("var"), 32).strip()
        out.update(var=var if VAR_NAME_RE.match(var) else "",
                   op=c.get("op") if c.get("op") in VAR_OPS else "==",
                   value=_clean_str(c.get("value"), 1000))
    return out


def sanitize_step(st):
    """Validate one step. Returns (step, problem). A step that can't be made safe returns
    (None, why). Unknown fields are dropped; numbers are clamped to sensible ranges."""
    if not isinstance(st, dict):
        return None, "a step isn't readable"
    t = st.get("type")
    if t not in STEP_TYPES:
        return None, f"unknown step type “{_clean_str(t, 20)}”"
    s = {"type": t}
    if st.get("label"):
        s["label"] = _clean_str(st.get("label"), 120)
    if t not in ("else", "end"):
        s["retries"] = _clamp_num(st.get("retries", 0), 0, 10, 0)
        s["retry_wait"] = _clamp_num(st.get("retry_wait", 2), 0, 3600, 2, as_int=False)
        s["on_fail"] = "continue" if st.get("on_fail") == "continue" else "stop"
        s["careful"] = bool(st.get("careful", False))
    btn = st.get("button") if st.get("button") in ("left", "right", "middle") else "left"
    if t == "click":
        s.update(x=_clamp_num(st.get("x", 0), -100000, 100000, 0),
                 y=_clamp_num(st.get("y", 0), -100000, 100000, 0),
                 button=btn, clicks=_clamp_num(st.get("clicks", 1), 1, 3, 1),
                 use_image=bool(st.get("use_image", False)),
                 snap_png=clean_png(st.get("snap_png")), snap_spot=_clean_point(st.get("snap_spot")),
                 pick_dpi=_clamp_num(st.get("pick_dpi"), 48, 960, None) if st.get("pick_dpi") else None,
                 pick_screen=_clean_point(st.get("pick_screen")),
                 image_fallback="position" if st.get("image_fallback") == "position" else "wait",
                 exact_match=bool(st.get("exact_match", True)),
                 target_mode="window" if st.get("target_mode") == "window" else "screen",
                 window_title=_clean_str(st.get("window_title"), 300),
                 window_class=_clean_str(st.get("window_class"), 200),
                 rel_x=_clamp_num(st.get("rel_x", 0), -100000, 100000, 0),
                 rel_y=_clamp_num(st.get("rel_y", 0), -100000, 100000, 0),
                 client_w=_clamp_num(st.get("client_w", 0), 0, 100000, 0),
                 client_h=_clamp_num(st.get("client_h", 0), 0, 100000, 0),
                 bring_to_front=bool(st.get("bring_to_front", True)),
                 scale_with_window=bool(st.get("scale_with_window", False)),
                 scale_with_screen=bool(st.get("scale_with_screen", False)))
        if not s["snap_png"]:
            s["use_image"] = False
        if st.get("human_move") in (True, False):
            s["human_move"] = st["human_move"]          # 4.5.6; missing = follow the job
    elif t == "wait":
        lo = _clamp_num(st.get("min", 1), 0, 86400, 1, as_int=False)
        hi = _clamp_num(st.get("max", lo), 0, 86400, lo, as_int=False)
        s.update(min=min(lo, hi), max=max(lo, hi))
    elif t == "waitpic":
        png = clean_png(st.get("png"))
        if not png:
            return None, "a “wait for a picture” step has no usable picture"
        s.update(png=png, until="disappears" if st.get("until") == "disappears" else "appears",
                 click_it=bool(st.get("click_it", False)), button=btn,
                 clicks=_clamp_num(st.get("clicks", 1), 1, 3, 1),
                 timeout=_clamp_num(st.get("timeout", 60), 1, STEP_MAX_WAIT_S, 60),
                 on_timeout="continue" if st.get("on_timeout") == "continue" else "stop",
                 area=_clean_rect(st.get("area")))
        if st.get("human_move") in (True, False):
            s["human_move"] = st["human_move"]
    elif t in ("type", "paste"):
        limit = MAX_TYPE_CHARS if t == "type" else MAX_PASTE_CHARS
        text = st.get("text", "")
        if not isinstance(text, str):
            text = str(text)
        if len(text) > limit:
            return None, f"a “{t}” step has more than {limit:,} characters"
        s.update(text=text, use_vars=bool(st.get("use_vars", False)),
                 secret=bool(st.get("secret", False)))
        enc = st.get("text_enc")
        if s["secret"] and isinstance(enc, str) and enc.startswith("dpapi:") \
                and len(enc) < 4 * limit + 4096:
            s["text_enc"] = enc
            s["text"] = ""
        if t == "paste":
            s.update(restore_clipboard=bool(st.get("restore_clipboard", True)),
                     paste_keys=st.get("paste_keys") if st.get("paste_keys") in PASTE_KEYS
                     else "Ctrl+V",
                     settle=_clamp_num(st.get("settle", 0.3), 0.05, 5, 0.3, as_int=False))
    elif t == "key":
        keys = _clean_str(st.get("keys"), 60).strip()
        try:
            parse_combo(keys)
        except ValueError as e:
            return None, f"a “press keys” step is invalid ({e})"
        s.update(keys=keys, times=_clamp_num(st.get("times", 1), 1, 100, 1))
    elif t in ("move", "drag"):
        path = _clean_path(st.get("path"))
        if len(path) < (2 if t == "drag" else 1):
            return None, f"a “{t}” step has no usable path"
        s["path"] = path
        if t == "drag":
            s["button"] = btn
    elif t == "mouse":
        s.update(button=btn, action="up" if st.get("action") == "up" else "down",
                 x=_clamp_num(st.get("x"), -100000, 100000, None) if st.get("x") is not None else None,
                 y=_clamp_num(st.get("y"), -100000, 100000, None) if st.get("y") is not None else None)
    elif t == "scroll":
        s.update(x=_clamp_num(st.get("x"), -100000, 100000, None) if st.get("x") is not None else None,
                 y=_clamp_num(st.get("y"), -100000, 100000, None) if st.get("y") is not None else None,
                 amount=_clamp_num(st.get("amount", -3), -100, 100, -3),
                 horizontal=bool(st.get("horizontal", False)))
    elif t == "keyhold":
        keys = _clean_str(st.get("keys"), 30).strip()
        try:
            if len(parse_combo(keys)) != 1:
                raise ValueError("hold one key at a time")
        except ValueError as e:
            return None, f"a “hold key” step is invalid ({e})"
        s.update(keys=keys, action="up" if st.get("action") == "up" else "down")
    elif t == "if":
        s["cond"] = clean_cond(st.get("cond"))
    elif t == "repeat":
        s.update(mode="until" if st.get("mode") == "until" else "times",
                 times=_clamp_num(st.get("times", 3), 1, MAX_REPEAT, 3),
                 max_times=_clamp_num(st.get("max_times", 100), 1, MAX_REPEAT, 100),
                 max_seconds=_clamp_num(st.get("max_seconds", 600), 1, MAX_RUN_LIMIT_S, 600))
        if s["mode"] == "until":
            s["cond"] = clean_cond(st.get("cond"))
    elif t == "set":
        var = _clean_str(st.get("var"), 32).strip()
        if not VAR_NAME_RE.match(var):
            return None, "a “set variable” step has an invalid name"
        s.update(var=var, op=st.get("op") if st.get("op") in ("set", "add", "sub") else "set",
                 value=_clean_str(st.get("value"), 1000), persist=bool(st.get("persist", False)))
    elif t == "group":
        s["group_id"] = _clean_str(st.get("group_id"), 64)
    return s, ""


def sanitize_steps(steps):
    """Returns (clean steps, list of problems). Bad steps are left out (and reported)."""
    out, problems = [], []
    for st in (steps if isinstance(steps, list) else [])[:MAX_STEPS]:
        s, why = sanitize_step(st)
        if s is None:
            problems.append(why)
        else:
            out.append(s)
    if isinstance(steps, list) and len(steps) > MAX_STEPS:
        problems.append(f"only the first {MAX_STEPS} steps were kept")
    return out, problems


_JOB_ENUMS = {"button": ("left", "right", "middle"), "kind": ("click", "watch"),
              "target_mode": ("screen", "window"), "hours_outside": ("wait", "skip"),
              "watch_trigger": ("gone", "appears"), "image_fallback": ("wait", "position"),
              "snap_size": ("Small", "Medium", "Large"), "priority": ("high", "normal", "low"),
              "watch_match": ("exact", "partial")}
_JOB_RANGES = {"clicks": (1, 3), "interval_s": (1, 10 * 365 * 86400),
               "delay_min_s": (0, 365 * 86400), "delay_max_s": (0, 365 * 86400),
               "limit_clicks": (1, 10_000_000), "watch_interval_s": (1, 7 * 86400),
               "watch_confirm": (1, 100), "watch_delay_min_s": (0, 86400),
               "watch_delay_max_s": (0, 86400), "watch_cooldown_s": (0, 7 * 86400),
               "run_limit_s": (10, MAX_RUN_LIMIT_S),
               "watch_partial_pct": (PARTIAL_MIN_PCT, PARTIAL_MAX_PCT)}


def sanitize_job(j):
    """Validate an imported (untrusted) job. Returns (job, problems). Never runs anything:
    the result is a plain job dict with known fields, sane numbers and checked pictures."""
    base = new_job()
    problems = []
    if not isinstance(j, dict):
        return None, ["a job isn't readable"]
    for k, v in j.items():
        if k not in base or k in RUNTIME_KEYS or k in ("id", "steps"):
            continue
        d = base[k]
        if k in _JOB_ENUMS:
            if v in _JOB_ENUMS[k]:
                base[k] = v
        elif k in ("snap_png", "watch_png"):
            base[k] = clean_png(v)
            if v and not base[k]:
                problems.append(f"a picture in “{_clean_str(j.get('name'), 40)}” was unusable")
        elif k in ("snap_spot", "pick_screen"):
            base[k] = _clean_point(v)
        elif k in ("watch_area",):
            base[k] = _clean_rect(v)
        elif k == "watch_area_screen":
            base[k] = _clean_point(v[:2]) if isinstance(v, list) and len(v) >= 2 else None
        elif k == "pick_dpi":
            base[k] = _clamp_num(v, 48, 960, None) if v else None
        elif k == "human_move":
            base[k] = v if v in (True, False, None) else None
        elif k == "hours_days":
            base[k] = sorted({int(x) for x in v if isinstance(x, int) and 0 <= x <= 6}) \
                if isinstance(v, list) else d
        elif k == "saved_vars":
            base[k] = {str(a)[:32]: _clean_str(b, 1000) for a, b in v.items()
                       if VAR_NAME_RE.match(str(a))} if isinstance(v, dict) else {}
        elif isinstance(d, bool):
            base[k] = bool(v)
        elif isinstance(d, int):
            lo, hi = _JOB_RANGES.get(k, (-100000, 100000))
            base[k] = _clamp_num(v, lo, hi, d)
        elif isinstance(d, str):
            base[k] = _clean_str(v, MAX_NAME if k == "name" else 300)
    base["name"] = base["name"].strip() or "Imported job"
    base["steps"], sp = sanitize_steps(j.get("steps", []))
    problems += sp
    if base.get("first_time"):
        try:
            parse_hms_clock(base["first_time"])
        except Exception:
            base["first_time"] = ""
    for k in ("hours_from", "hours_to"):
        try:
            parse_hhmm(base[k])
        except Exception:
            base[k] = new_job()[k]
    return base, problems


# ---- 4.5.3: editing several jobs at once ("Edit together")
BATCH_LABELS = {
    "button": "mouse button", "clicks": "single/double click", "priority": "priority",
    "run_limit_s": "run time limit", "exact_match": "exact click-spot picture",
    "image_fallback": "if the picture isn't found", "hours_on": "active hours",
    "hours_from": "active hours", "hours_to": "active hours", "hours_days": "active hours",
    "hours_outside": "active hours", "let_others_run": "let others run",
    "record_video": "screen video", "fail_shot": "failure screenshot",
    "bring_to_front": "bring window to front",
    "interval_s": "schedule", "random_on": "random delay", "delay_min_s": "random delay",
    "delay_max_s": "random delay",
    "watch_interval_s": "check interval", "watch_confirm": "checks in a row",
    "watch_random_on": "random delay", "watch_delay_min_s": "random delay",
    "watch_delay_max_s": "random delay", "watch_cooldown_on": "wait after clicking",
    "watch_cooldown_s": "wait after clicking", "watch_once": "click only once",
    "watch_match": "match", "watch_partial_pct": "match"}
BATCH_CLICK_ONLY = ("interval_s", "random_on", "delay_min_s", "delay_max_s")


def batch_applies(key, job):
    """Does a batch-edited setting apply to this kind of job?"""
    if key in BATCH_CLICK_ONLY:
        return not is_watch(job)
    if key.startswith("watch_"):
        return is_watch(job)
    return key in BATCH_LABELS


def clean_batch_changes(changes):
    """Validate batch-edit values the same way as an import (unknown keys dropped, numbers
    clamped, choices checked)."""
    if not isinstance(changes, dict):
        return {}
    keep = {k: v for k, v in changes.items() if k in BATCH_LABELS}
    base, _ = sanitize_job(dict(keep, name="batch"))
    return {k: base[k] for k in keep}


def sanitize_groups(groups):
    out, problems = [], []
    for g in (groups if isinstance(groups, list) else [])[:200]:
        if not isinstance(g, dict):
            continue
        steps, sp = sanitize_steps(g.get("steps", []))
        problems += sp
        out.append({"id": _clean_str(g.get("id"), 64) or uuid.uuid4().hex,
                    "name": _clean_str(g.get("name"), MAX_NAME).strip() or "Group",
                    "steps": [s for s in steps if s["type"] != "group"]})   # no nesting
    return out, problems


def load_import_file(path):
    """Read a jobs file someone gave you. Returns (jobs, groups, problems).
    Raises ValueError with a readable reason for files that can't be used."""
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise ValueError(f"can't read the file ({e.strerror})")
    if size > MAX_IMPORT_BYTES:
        raise ValueError(f"the file is too large ({size // (1024 * 1024)} MB; the limit is "
                         f"{MAX_IMPORT_BYTES // (1024 * 1024)} MB)")
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception:
            raise ValueError("it isn't a Clickue jobs file (not valid JSON)")
    raw = data.get("jobs") if isinstance(data, dict) else data
    if not isinstance(raw, list):
        raise ValueError("no jobs found in that file")
    if isinstance(data, dict) and int(_clamp_num(data.get("schema", 1), 0, 999, 1)) > SCHEMA_VERSION:
        raise ValueError("it was made by a newer Clickue; update Clickue first")
    raw = [j for j in raw if isinstance(j, dict) and "x" in j and "y" in j][:MAX_JOBS]
    if not raw:
        raise ValueError("no jobs found in that file")
    groups, problems = sanitize_groups(data.get("groups", []) if isinstance(data, dict) else [])
    jobs = []
    for j in raw:
        b, p = sanitize_job(j)
        problems += p
        if b:
            jobs.append(b)
    return jobs, groups, problems


def strip_secret_text(steps):
    """Copies of the steps with secret text removed (for exports)."""
    out = []
    for st in steps or []:
        s = dict(st)
        if s.get("secret") and s.get("type") in ("type", "paste"):
            s.pop("text_enc", None)
            s["text"] = ""
            s["secret_missing"] = True
        out.append(s)
    return out


def risky_step_summary(jobs, groups=()):
    """Counts of steps that send keyboard input, for the import review message."""
    n = {"type": 0, "paste": 0, "key": 0, "keyhold": 0}
    for st in [s for j in jobs for s in j.get("steps", [])] + \
              [s for g in groups for s in g.get("steps", [])]:
        if st.get("type") in n:
            n[st["type"]] += 1
    return n


# ---- variables ({date}, {time}, values set earlier in the run) ------------------------------
_VAR_RE = re.compile(r"\{\{|\}\}|\{([A-Za-z_][A-Za-z0-9_]{0,31})\}")


def builtin_vars(now=None):
    d = datetime.fromtimestamp(now or time.time())
    return {"date": d.strftime("%Y-%m-%d"), "time": d.strftime("%H:%M:%S"),
            "datetime": d.strftime("%Y-%m-%d %H:%M:%S"), "year": d.strftime("%Y"),
            "month": d.strftime("%m"), "day": d.strftime("%d"), "hour": d.strftime("%H"),
            "minute": d.strftime("%M"), "weekday": DAY_NAMES[d.weekday()]}


def expand_vars(text, values, limit=MAX_PASTE_CHARS):
    """Replace {name} with its value. {{ and }} give literal braces; unknown names stay as
    they are. The result is capped at `limit` characters."""
    def sub(m):
        tok = m.group(0)
        if tok == "{{":
            return "{"
        if tok == "}}":
            return "}"
        name = m.group(1)
        if name in values:
            return str(values[name])
        return tok
    out = _VAR_RE.sub(sub, str(text))
    if len(out) > limit:
        raise ValueError(f"the text is longer than {limit:,} characters after filling in "
                         f"the variables")
    return out


def _as_number(v):
    try:
        f = float(str(v).strip())
        return int(f) if f.is_integer() else f
    except Exception:
        return None


def compare_values(a, op, b):
    if op == "contains":
        return str(b) in str(a)
    na, nb = _as_number(a), _as_number(b)
    if na is not None and nb is not None:
        a, b = na, nb
    else:
        a, b = str(a), str(b)
    try:
        return {"==": a == b, "!=": a != b, "<": a < b, ">": a > b, "<=": a <= b,
                ">=": a >= b}[op]
    except TypeError:
        return False


# ---- clipboard (for "Paste text") -------------------------------------------------------------
if IS_WIN:
    user32.OpenClipboard.argtypes = [wt.HWND]
    user32.OpenClipboard.restype = wt.BOOL
    user32.CloseClipboard.restype = wt.BOOL
    user32.EmptyClipboard.restype = wt.BOOL
    user32.EnumClipboardFormats.argtypes = [wt.UINT]
    user32.EnumClipboardFormats.restype = wt.UINT
    user32.GetClipboardData.argtypes = [wt.UINT]
    user32.GetClipboardData.restype = wt.HANDLE
    user32.SetClipboardData.argtypes = [wt.UINT, wt.HANDLE]
    user32.SetClipboardData.restype = wt.HANDLE
    user32.RegisterClipboardFormatW.argtypes = [wt.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wt.UINT
    user32.GetClipboardSequenceNumber.restype = wt.DWORD
    kernel32.GlobalAlloc.argtypes = [wt.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wt.HGLOBAL
    kernel32.GlobalLock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wt.HGLOBAL]
    kernel32.GlobalSize.argtypes = [wt.HGLOBAL]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalFree.argtypes = [wt.HGLOBAL]
    kernel32.GlobalFree.restype = wt.HGLOBAL

# formats whose data isn't a plain memory block (bitmaps, metafiles, palettes, owner-drawn):
# they can't be copied byte for byte, so a clipboard holding only these isn't restored
_CLIP_SKIP = {2, 3, 9, 14, 0x0080, 0x0082, 0x0083, 0x008E}
CLIP_MAX_BYTES = 64 * 1024 * 1024


def _clip_open():
    for _ in range(20):                     # another program may be holding it briefly
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def clipboard_snapshot():
    """Copy what's on the clipboard now. Returns (formats [(fmt, bytes)], complete), or
    (None, False) when the clipboard couldn't be opened (another program is holding it)."""
    if not IS_WIN:
        return [], True
    if not _clip_open():
        return None, False
    items, complete, total = [], True, 0
    try:
        fmt = user32.EnumClipboardFormats(0)
        while fmt:
            if fmt in _CLIP_SKIP:
                complete = False
            else:
                h = user32.GetClipboardData(fmt)
                if h:
                    size = kernel32.GlobalSize(h)
                    if total + size > CLIP_MAX_BYTES:
                        complete = False
                    elif size:
                        p = kernel32.GlobalLock(h)
                        if p:
                            try:
                                items.append((fmt, ctypes.string_at(p, size)))
                                total += size
                            finally:
                                kernel32.GlobalUnlock(h)
            fmt = user32.EnumClipboardFormats(fmt)
    finally:
        user32.CloseClipboard()
    return items, complete


def _clip_put(fmt, data):
    h = kernel32.GlobalAlloc(0x0002, max(1, len(data)))       # GMEM_MOVEABLE
    if not h:
        return False
    p = kernel32.GlobalLock(h)
    if not p:
        kernel32.GlobalFree(h)
        return False
    ctypes.memmove(p, data, len(data))
    kernel32.GlobalUnlock(h)
    if not user32.SetClipboardData(fmt, h):
        kernel32.GlobalFree(h)
        return False
    return True


def clipboard_set_text(text, private=True):
    """Put text on the clipboard. private=True asks Windows to keep it out of clipboard
    history (Win+V) and cloud clipboard sync."""
    if not IS_WIN:
        return False
    if not _clip_open():
        return False
    try:
        user32.EmptyClipboard()
        ok = _clip_put(13, (str(text) + "\0").encode("utf-16-le"))      # CF_UNICODETEXT
        if private:
            for name, val in (("ExcludeClipboardContentFromMonitorProcessing", b"\0\0\0\0"),
                              ("CanIncludeInClipboardHistory", b"\0\0\0\0"),
                              ("CanUploadToCloudClipboard", b"\0\0\0\0")):
                f = user32.RegisterClipboardFormatW(name)
                if f:
                    _clip_put(f, val)
        return ok
    finally:
        user32.CloseClipboard()


def clipboard_restore(items):
    if not IS_WIN:
        return False
    if not _clip_open():
        return False
    try:
        user32.EmptyClipboard()
        return all(_clip_put(f, d) for f, d in items)
    finally:
        user32.CloseClipboard()


def paste_text(text, keys="Ctrl+V", restore=True, settle=0.3):
    """Paste text into whatever has keyboard focus: put it on the clipboard, press Ctrl+V,
    then put the previous clipboard back. Returns (ok, message). The message never
    contains the text."""
    if not IS_WIN:
        return False, "pasting only works on Windows"
    saved, complete = clipboard_snapshot() if restore else ([], True)
    if saved is None:            # couldn't read it: don't touch it (the step can retry)
        return False, "couldn't read the clipboard (another program is holding it)"
    if not clipboard_set_text(text, private=True):
        return False, "couldn't use the clipboard (another program is holding it)"
    time.sleep(0.05)
    ok, msg = press_keys(keys)
    time.sleep(max(0.05, settle))              # let the program read the clipboard first
    note = ""
    if restore:
        if saved and complete:
            note = "" if clipboard_restore(saved) else " (couldn't put your clipboard back)"
        elif saved:
            clipboard_restore(saved)
            note = " (your clipboard was only partly put back: it held a format Clickue " \
                   "can't copy)"
        else:
            clipboard_restore([])           # leave it empty rather than holding the pasted text
            if not complete:
                note = " (your clipboard held a format Clickue can't copy, so it was cleared)"
    return ok, ("pasted" + note) if ok else msg


# ---- low-level input with guaranteed release -------------------------------------------------
MOUSE_WHEEL, MOUSE_HWHEEL = 0x0800, 0x01000


class InputGuard:
    """Remembers every mouse button and key Clickue is holding down, so they can always be
    released: when a run stops, fails, is cancelled, times out, or the app exits."""

    def __init__(self):
        self.lock = threading.Lock()
        self.buttons, self.keys = [], []

    def button(self, button, down):
        if not IS_WIN:
            return False, "the mouse only works on Windows"
        dn, up = MOUSE_FLAGS.get(button, MOUSE_FLAGS["left"])
        with self.lock:
            if down:
                if button not in self.buttons:
                    self.buttons.append(button)
            elif button in self.buttons:
                self.buttons.remove(button)
        user32.mouse_event(dn if down else up, 0, 0, 0, 0)
        return True, "pressed" if down else "released"

    def busy(self):
        """Is any mouse button or key being held down right now?"""
        with self.lock:
            return bool(self.buttons or self.keys)

    def key(self, vk, down):
        if not IS_WIN:
            return False, "keys only work on Windows"
        with self.lock:
            if down:
                if vk not in self.keys:
                    self.keys.append(vk)
            elif vk in self.keys:
                self.keys.remove(vk)
        ext = 0x0001 if vk in EXTENDED_VKS else 0
        _send([_key_input(vk, flags=ext | (0 if down else 0x0002))])
        return True, "pressed" if down else "released"

    def holding(self):
        with self.lock:
            return bool(self.buttons or self.keys)

    def release_all(self):
        """Let go of everything still held down. Safe to call any time."""
        with self.lock:
            buttons, keys = list(self.buttons), list(self.keys)
            self.buttons, self.keys = [], []
        if not IS_WIN:
            return
        for b in buttons:
            try:
                user32.mouse_event(MOUSE_FLAGS.get(b, MOUSE_FLAGS["left"])[1], 0, 0, 0, 0)
            except Exception:
                pass
        for vk in reversed(keys):
            try:
                ext = 0x0001 if vk in EXTENDED_VKS else 0
                _send([_key_input(vk, flags=ext | 0x0002)])
            except Exception:
                pass


HELD = InputGuard()
import atexit                                       # noqa: E402
atexit.register(HELD.release_all)


def move_mouse(x, y):
    if not IS_WIN:
        return False, "the mouse only works on Windows"
    if not user32.SetCursorPos(int(x), int(y)):
        return False, "could not move the mouse (no active screen)"
    return True, "moved"


def scroll_wheel(amount, horizontal=False):
    """Scroll by `amount` notches (negative = down / left)."""
    if not IS_WIN:
        return False, "the mouse only works on Windows"
    user32.mouse_event(MOUSE_HWHEEL if horizontal else MOUSE_WHEEL, 0, 0, int(amount) * 120, 0)
    return True, "scrolled"


# ---- step blocks: "if … else … end", "repeat … end" -----------------------------------------
MAX_NESTING = 8


def parse_blocks(steps):
    """Turn the flat step list into a tree. Returns (nodes, errors).
    A node is {"i": index, "st": step} plus "body"/"orelse" lists for if/repeat."""
    root = []
    stack = [("root", root, None)]
    errors = []
    for i, st in enumerate(steps or []):
        t = st.get("type")
        if t in ("if", "repeat"):
            node = {"i": i, "st": st, "body": [], "orelse": []}
            stack[-1][1].append(node)
            if len(stack) > MAX_NESTING:
                errors.append(f"step {i + 1}: blocks are nested too deeply (max {MAX_NESTING})")
            stack.append((t, node["body"], node))
        elif t == "else":
            kind, _, node = stack[-1]
            if kind != "if" or node.get("has_else"):
                errors.append(f"step {i + 1}: “Otherwise” without a matching “If”")
                continue
            node["has_else"] = True
            stack[-1] = ("else", node["orelse"], node)
        elif t == "end":
            if len(stack) == 1:
                errors.append(f"step {i + 1}: “End” without a matching “If” or “Repeat”")
                continue
            stack.pop()
        else:
            stack[-1][1].append({"i": i, "st": st})
    for kind, _, node in stack[1:]:
        errors.append(f"step {node['i'] + 1}: this “{'If' if kind in ('if', 'else') else 'Repeat'}"
                      f"” has no “End”")
    return root, errors


def step_depths(steps):
    """Indentation level of each step (for the timeline)."""
    out, d = [], 0
    for st in steps or []:
        t = st.get("type")
        if t in ("else", "end"):
            d = max(0, d - 1)
        out.append(d)
        if t in ("if", "repeat", "else"):
            d += 1
    return out


# ---- target adapters ------------------------------------------------------------------------
ADAPTER_API_VERSION = 1


class TargetAdapter:
    """How Clickue finds something on screen. To add support for another kind of target,
    subclass this in src/clickue.py and call register_adapter() - the workflow engine only
    talks to adapters through these methods (see docs/DEVELOPER_GUIDE.md, "Target
    adapters"). Adapters are part of the program: Clickue never loads adapter code from
    files or the internet.

    api        ADAPTER_API_VERSION it was written for
    id         short key stored in jobs ("picture", "window", "screen", ...)
    label      shown to the user
    needs      packages it needs (shown in About when missing)
    """
    api = ADAPTER_API_VERSION
    id = ""
    label = ""
    needs = ()

    def available(self):
        """(ok, why-not)."""
        return True, ""

    def handles(self, target):
        """True if this adapter is the one that finds `target` (a job or a click step)."""
        return False

    def describe(self, target):
        """One line: how the target will be found, and the fallback (if any)."""
        return self.label

    def locate(self, target, activate=False, check_cover=True):
        """Where to click now: (ok, x, y, message, how-it-was-found). Must not click."""
        return False, 0, 0, "not supported", ""

    def check(self, cond):
        """For conditions: (true?, short note). Must not click or type."""
        return False, "not supported"


ADAPTERS = []


def register_adapter(adapter):
    if getattr(adapter, "api", 0) != ADAPTER_API_VERSION or not adapter.id:
        raise ValueError(f"adapter {adapter!r} was written for another adapter API version")
    ADAPTERS[:] = [a for a in ADAPTERS if a.id != adapter.id] + [adapter]
    return adapter


class PictureAdapter(TargetAdapter):
    id, label, needs = "picture", "By picture", ("opencv-python-headless", "numpy", "pillow")

    def available(self):
        return (True, "") if HAVE_CV else (False, "picture matching isn't installed")

    def handles(self, target):
        return bool(target.get("use_image") and target.get("snap_png"))

    def describe(self, target):
        fb = ("then the saved position if the picture isn't found (you chose this)"
              if target.get("image_fallback") == "position"
              else "no fallback: if the picture isn't found, nothing is clicked")
        where = " inside the window" if target.get("target_mode") == "window" else ""
        what = ("the exact saved picture (similar ones are ignored)"
                if target.get("exact_match", True) else "the saved picture or a similar one")
        return f"Finds {what}{where}; {fb}"

    def locate(self, target, activate=False, check_cover=True):
        return locate_spot(target, activate=activate, check_cover=check_cover)

    def check(self, cond):
        if not HAVE_CV:
            return False, "picture matching isn't installed"
        if not cond.get("png"):
            return False, "no picture saved"
        if not screen_available():
            return False, "screen locked"
        found, x, y, score, sc = picture_on_screen(cond["png"], area=cond.get("area"))
        shown = cond.get("state", "shown") == "shown"
        return (found if shown else not found), (f"picture showing ({score:.0%})" if found
                                                  else f"picture not showing (best {score:.0%})")


class WindowAdapter(TargetAdapter):
    id, label = "window", "Inside a window"

    def available(self):
        return (True, "") if IS_WIN else (False, "window targets need Windows")

    def handles(self, target):
        return target.get("target_mode") == "window" and bool(target.get("window_title"))

    def describe(self, target):
        return (f"Spot inside the window “{short_title(target.get('window_title', ''), 40)}”; "
                f"nothing is clicked if the window isn't open or something covers it")

    def locate(self, target, activate=False, check_cover=True):
        ok, x, y, msg = resolve_target(target, activate=activate, check_cover=check_cover)
        return ok, x, y, msg, "window position"

    def check(self, cond):
        title = cond.get("title", "")
        if not title:
            return False, "no window title"
        h = find_window(title, "") if IS_WIN else None
        is_open = bool(h)
        want_open = cond.get("state", "open") == "open"
        return (is_open if want_open else not is_open), ("window is open" if is_open
                                                          else "window isn't open")


class ScreenPositionAdapter(TargetAdapter):
    id, label = "screen", "Fixed screen position"

    def handles(self, target):
        return True

    def describe(self, target):
        return (f"Fixed position ({target.get('x', 0)}, {target.get('y', 0)}): not verified - "
                f"only use it for things that never move")

    def locate(self, target, activate=False, check_cover=True):
        ok, x, y, msg = resolve_target(target, activate=activate, check_cover=check_cover)
        return ok, x, y, msg, "saved position"


for _a in (PictureAdapter(), WindowAdapter(), ScreenPositionAdapter()):
    register_adapter(_a)


def adapter_for(target):
    """The adapter that will find this job's or step's click target."""
    for a in ADAPTERS:
        if a.handles(target) and a.available()[0]:
            return a
    return ADAPTERS[-1]


PLANNED_ADAPTERS = (
    ("ocr", "Text on screen (OCR)", "planned for the next release"),
    ("uia", "Windows controls (UI Automation)", "planned"),
    ("browser", "Web page elements (browser integration)", "planned"),
)


def check_condition(cond):
    """Evaluate an If / Repeat-until condition once: (true?, note). Never sends input."""
    kind = cond.get("kind", "picture")
    if kind == "var":
        return False, "variables are checked by the run"
    for a in ADAPTERS:
        if a.id == kind:
            ok, why = a.available()
            if not ok:
                return False, why
            return a.check(cond)
    return False, f"unknown condition “{kind}”"


def describe_cond(c):
    c = c or {}
    k = c.get("kind", "picture")
    wait = c.get("wait", 0)
    w = f" (wait up to {fmt_dur(wait)})" if wait else ""
    if k == "picture":
        return ("the picture is showing" if c.get("state", "shown") == "shown"
                else "the picture is NOT showing") + w
    if k == "window":
        t = short_title(c.get("title", ""), 30)
        return (f"window “{t}” is open" if c.get("state", "open") == "open"
                else f"window “{t}” is NOT open") + w
    return f"{{{c.get('var', '?')}}} {c.get('op', '==')} “{short_title(str(c.get('value', '')), 20)}”"


def describe_step(st, private=False, groups=None):
    """(what, details) for the timeline. private=True never shows typed/pasted text
    (used for logs and the run history)."""
    t = st.get("type")
    label = st.get("label")
    if t == "click":
        how = ("by picture" if st.get("use_image") and st.get("snap_png") else
               f"in window “{short_title(st.get('window_title', ''), 20)}”"
               if st.get("target_mode") == "window" else "fixed spot")
        d = (f"{st.get('button', 'left')} {'double ' if st.get('clicks') == 2 else ''}"
             f"click at ({st.get('x')}, {st.get('y')}), {how}")
        w = "Click"
    elif t == "wait":
        lo, hi = st.get("min", 1), st.get("max", st.get("min", 1))
        w, d = "Wait", (f"{fmt_secs(lo)}" if lo == hi else
                        f"{fmt_secs(lo)} to {fmt_secs(hi)} (random)")
    elif t in ("type", "paste"):
        txt = st.get("text", "")
        w = "Type text" if t == "type" else "Paste text"
        if st.get("secret"):
            d = "•••• (secret, protected)" if st.get("text_enc") else "•••• (secret: enter it again)"
        elif private:
            d = f"{len(txt)} characters"
        else:
            d = (txt[:60] + "…") if len(txt) > 60 else txt
            d = d.replace("\n", " ⏎ ")
        if st.get("use_vars"):
            d += "  · fills in {variables}"
        if t == "paste" and not st.get("restore_clipboard", True):
            d += "  · leaves it on the clipboard"
    elif t == "key":
        w, d = "Press keys", st.get("keys", "") + (f" × {st['times']}" if st.get("times", 1) > 1 else "")
    elif t == "waitpic":
        what = ("until it appears, then click it" if st.get("until", "appears") == "appears"
                and st.get("click_it") else
                "until it appears" if st.get("until", "appears") == "appears"
                else "until it goes away")
        then = "stop the chain" if st.get("on_timeout", "stop") == "stop" else "continue"
        w, d = "Wait for picture", (f"{what} · up to {fmt_dur(int(st.get('timeout', 60)))}, "
                                    f"then {then}")
    elif t == "move":
        p = st.get("path") or [[0, 0, 0]]
        w, d = "Move mouse", (f"to ({p[-1][1]}, {p[-1][2]}) · {len(p)} points · "
                              f"{fmt_secs(p[-1][0])}")
    elif t == "drag":
        p = st.get("path") or [[0, 0, 0], [0, 0, 0]]
        w, d = "Drag", (f"{st.get('button', 'left')} from ({p[0][1]}, {p[0][2]}) to "
                        f"({p[-1][1]}, {p[-1][2]}) · {fmt_secs(p[-1][0])}")
    elif t == "mouse":
        at = f" at ({st.get('x')}, {st.get('y')})" if st.get("x") is not None else ""
        w, d = ("Mouse button down" if st.get("action") == "down" else "Mouse button up"), \
            f"{st.get('button', 'left')}{at}"
    elif t == "scroll":
        n = int(st.get("amount", 0))
        dirn = ("left" if n < 0 else "right") if st.get("horizontal") else ("down" if n < 0 else "up")
        at = f" at ({st.get('x')}, {st.get('y')})" if st.get("x") is not None else ""
        w, d = "Scroll", f"{abs(n)} notch{'es' if abs(n) != 1 else ''} {dirn}{at}"
    elif t == "keyhold":
        w, d = ("Hold key down" if st.get("action") == "down" else "Release key"), st.get("keys", "")
    elif t == "if":
        w, d = "If", describe_cond(st.get("cond"))
    elif t == "else":
        w, d = "Otherwise", ""
    elif t == "end":
        w, d = "End", ""
    elif t == "repeat":
        if st.get("mode") == "until":
            w, d = "Repeat until", (f"{describe_cond(st.get('cond'))} · at most "
                                    f"{st.get('max_times', 100)}× / {fmt_dur(st.get('max_seconds', 600))}")
        else:
            w, d = "Repeat", f"{st.get('times', 3)} times"
    elif t == "set":
        op = {"set": "=", "add": "+=", "sub": "-="}.get(st.get("op", "set"), "=")
        val = st.get("value", "")
        w, d = "Set variable", (f"{{{st.get('var', '')}}} {op} “{short_title(val, 30)}”"
                                + ("  · remembered between runs" if st.get("persist") else ""))
    elif t == "group":
        name = next((g["name"] for g in (groups or []) if g.get("id") == st.get("group_id")),
                    "(missing group)")
        w, d = "Use group", f"“{name}”"
    else:
        w, d = str(t), "(unknown step - it will stop the run)"
    extras = []
    if st.get("retries"):
        extras.append(f"retry {st['retries']}×")
    if st.get("on_fail") == "continue" and t not in ("else", "end"):
        extras.append("continue if it fails")
    if st.get("careful"):
        extras.append("⚠ careful")
    if extras:
        d = f"{d}  · {' · '.join(extras)}"
    if label:
        d = f"{label}: {d}"
    return w, d


def fmt_secs(v):
    """2 s, 0.4 s, 1 min 30 s (keeps tenths for recorded delays)."""
    try:
        v = float(v)
    except Exception:
        return str(v)
    if v < 60 and not float(v).is_integer():
        return f"{v:.1f}s"
    return fmt_dur(int(round(v)))


# ---- jobs that may get in each other's way -----------------------------------------------------
def job_targets(job):
    """What a job clicks or types into: window titles, and fixed spots (40-px cells)."""
    out = set()

    def add(t):
        if t.get("target_mode") == "window" and t.get("window_title"):
            out.add(("window", t["window_title"].strip().lower()))
        elif not (t.get("use_image") and t.get("snap_png")):
            out.add(("spot", int(t.get("x", 0)) // 40, int(t.get("y", 0)) // 40))

    if job.get("main_click", True) and not (is_watch(job) and job.get("watch_click_picture")):
        add(job)
    for st in job.get("steps") or []:
        if st.get("type") == "click":
            add(st)
    return out


def find_conflicts(jobs, job=None):
    """Pairs of running jobs that click the same window or spot: they take turns, but one
    may change what the other expects to see. Returns [(name_a, name_b, why)]."""
    act = [j for j in jobs if j.get("enabled") or j is job]
    out = []
    for i, a in enumerate(act):
        for b in act[i + 1:]:
            if job is not None and job not in (a, b):
                continue
            common = job_targets(a) & job_targets(b)
            if not common:
                continue
            kind = sorted(common)[0]
            why = (f"both use the window “{kind[1]}”" if kind[0] == "window"
                   else "both click the same spot on screen")
            out.append((a.get("name", "?"), b.get("name", "?"), why))
    return out


# ---- keyboard names for recorded keys ---------------------------------------------------------
_VK_CANON = {0x0D: "Enter", 0x09: "Tab", 0x1B: "Esc", 0x20: "Space", 0x08: "Backspace",
             0x2E: "Delete", 0x2D: "Insert", 0x24: "Home", 0x23: "End", 0x21: "PageUp",
             0x22: "PageDown", 0x26: "Up", 0x28: "Down", 0x25: "Left", 0x27: "Right",
             0x2C: "PrintScreen", 0x13: "Pause", 0x14: "CapsLock", 0x5D: "Menu",
             **{0x6F + i: f"F{i}" for i in range(1, 25)},
             **{0x60 + i: f"Num{i}" for i in range(10)}}
_MOD_OF_VK = {0x10: "shift", 0xA0: "shift", 0xA1: "shift", 0x11: "ctrl", 0xA2: "ctrl",
              0xA3: "ctrl", 0x12: "alt", 0xA4: "alt", 0xA5: "alt", 0x5B: "win", 0x5C: "win"}
_MOD_ORDER = ("ctrl", "alt", "shift", "win")
_MOD_NAME = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win"}


def vk_name(vk):
    if vk in _VK_CANON:
        return _VK_CANON[vk]
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    if 0 < vk < 256:
        return f"0x{vk:02X}"
    return None


_US_SHIFT = dict(zip("1234567890-=[]\\;',./`", "!@#$%^&*()_+{}|:\"<>?~"))
_US_OEM = {0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
           0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'"}


if IS_WIN:
    user32.GetKeyboardLayout.argtypes = [wt.DWORD]
    user32.GetKeyboardLayout.restype = ctypes.c_void_p
    user32.MapVirtualKeyW.argtypes = [wt.UINT, wt.UINT]
    user32.MapVirtualKeyW.restype = wt.UINT
    user32.ToUnicodeEx.argtypes = [wt.UINT, wt.UINT, ctypes.POINTER(ctypes.c_ubyte), wt.LPWSTR,
                                   ctypes.c_int, wt.UINT, ctypes.c_void_p]
    user32.ToUnicodeEx.restype = ctypes.c_int


def vk_char(vk, shift=False, caps=False):
    """The character a key makes with the current keyboard layout, or None for keys that
    don't type a character (or dead keys)."""
    if IS_WIN:
        try:
            state = (ctypes.c_ubyte * 256)()
            if shift:
                state[0x10] = state[0xA0] = 0x80
            if caps:
                state[0x14] = 0x01
            buf = ctypes.create_unicode_buffer(8)
            hkl = user32.GetKeyboardLayout(user32.GetWindowThreadProcessId(
                user32.GetForegroundWindow(), None))
            n = user32.ToUnicodeEx(vk, user32.MapVirtualKeyW(vk, 0), state, buf, 8, 0x4, hkl)
            if n == 1 and buf.value and buf.value.isprintable():
                return buf.value
            return None
        except Exception:
            pass
    if vk == 0x20:
        return " "
    if 0x41 <= vk <= 0x5A:
        c = chr(vk)
        return c if (shift != caps) else c.lower()
    base = chr(vk) if 0x30 <= vk <= 0x39 else _US_OEM.get(vk)
    if base is None:
        if 0x60 <= vk <= 0x69:
            return str(vk - 0x60)
        return None
    return _US_SHIFT.get(base, base) if shift else base


def rdp(points, eps):
    """Ramer-Douglas-Peucker: drop points that don't change the path's shape much."""
    if len(points) < 3:
        return list(points)
    (_, x0, y0), (_, x1, y1) = points[0], points[-1]
    dx, dy = x1 - x0, y1 - y0
    norm = (dx * dx + dy * dy) ** 0.5 or 1e-9
    best, idx = -1.0, 0
    for i in range(1, len(points) - 1):
        _, x, y = points[i]
        dist = abs(dy * x - dx * y + x1 * y0 - y1 * x0) / norm if (dx or dy) else \
            ((x - x0) ** 2 + (y - y0) ** 2) ** 0.5
        if dist > best:
            best, idx = dist, i
    if best > eps:
        return rdp(points[:idx + 1], eps)[:-1] + rdp(points[idx:], eps)
    return [points[0], points[-1]]


REC_DEFAULTS = dict(moves=True, timing=True, min_wait=0.25, pictures=True, click_px=4,
                    click_s=0.6, double_s=0.5, move_min_px=24, text_gap=1.5, eps=2.0)


def compress_recording(events, opts=None, char_fn=None, exclude=()):
    """Turn raw recorded input events into editable steps.

    events: ("move", t, x, y) · ("down"/"up", t, x, y, button) · ("wheel", t, x, y, notches,
    horizontal) · ("kdown", t, vk, shift, caps) · ("kup", t, vk) · ("snap", t, png, spot)
    (a picture taken at the mouse-down at time t). Times are seconds from the start.
    exclude: screen rectangles [x, y, w, h] whose mouse events are dropped (the recording
    indicator). Returns a list of steps; each has "rec_t" (seconds from the start)."""
    o = dict(REC_DEFAULTS, **(opts or {}))
    char_fn = char_fn or vk_char

    def outside(x, y):
        return not any(r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3] for r in exclude)

    evs, snaps, pending_down = [], {}, set()
    for e in sorted(events, key=lambda e: e[1]):
        k = e[0]
        if k == "snap":
            snaps[round(e[1], 4)] = (e[2], e[3])
        elif k in ("move", "down", "up", "wheel"):
            if k == "up" and e[4] in pending_down:
                pending_down.discard(e[4])
                evs.append(e)
            elif outside(e[2], e[3]):
                if k == "down":
                    pending_down.add(e[4])
                evs.append(e)
        else:
            evs.append(e)
    # keys released that weren't pressed during the recording (e.g. the start hotkey), and
    # keys still held at the end (the stop hotkey) are left out
    downs, keep = {}, [True] * len(evs)
    for i, e in enumerate(evs):
        if e[0] == "kdown":
            downs.setdefault(e[2], i)
        elif e[0] == "kup":
            if e[2] in downs:
                downs.pop(e[2])
            else:
                keep[i] = False
    for vk, i in downs.items():
        for j in range(i, len(evs)):
            if evs[j][0] == "kdown" and evs[j][2] == vk:
                keep[j] = False
    evs = [e for e, k in zip(evs, keep) if k]

    steps = []
    st = {"last_t": 0.0, "text": None, "moves": [], "gesture": None}
    mods = {}            # modifier -> {"t": pressed at, "used": bool}
    held_for_mouse = set()
    dpi, scr = system_dpi(), list(screen_size())

    def emit(step, t0, t1, force_wait=False):
        gap = t0 - st["last_t"]
        if (o["timing"] or force_wait) and gap >= o["min_wait"]:
            g = round(gap, 1)
            steps.append({"type": "wait", "min": g, "max": g, "rec_t": round(st["last_t"], 2)})
        step["rec_t"] = round(t0, 2)
        steps.append(step)
        st["last_t"] = max(st["last_t"], t1)

    def flush_moves():
        pts = st["moves"]
        st["moves"] = []
        if not o["moves"] or len(pts) < 2:
            return
        length = sum(((pts[i][1] - pts[i - 1][1]) ** 2 + (pts[i][2] - pts[i - 1][2]) ** 2) ** 0.5
                     for i in range(1, len(pts)))
        if length < o["move_min_px"]:
            return
        t0 = pts[0][0]
        path = [[round(t - t0, 3), x, y] for t, x, y in rdp(pts, o["eps"])][:MAX_PATH_POINTS]
        emit({"type": "move", "path": path}, t0, pts[-1][0])

    def flush_text():
        tx = st["text"]
        st["text"] = None
        if tx and tx["chars"]:
            emit({"type": "type", "text": "".join(tx["chars"])}, tx["t0"], tx["t1"])

    def emit_key(name, t):
        last = steps[-1] if steps else None
        if (last and last.get("type") == "key" and last.get("keys") == name
                and t - st["last_t"] <= 0.6):
            last["times"] = last.get("times", 1) + 1
            st["last_t"] = t
        else:
            emit({"type": "key", "keys": name, "times": 1}, t, t)

    def mod_combo(key_name):
        held = [m for m in _MOD_ORDER if m in mods]
        for m in held:
            mods[m]["used"] = True
        return "+".join([_MOD_NAME[m] for m in held] + [key_name])

    for e in evs:
        k, t = e[0], e[1]
        if k == "move":
            g = st["gesture"]
            if g:
                g["path"].append((t, e[2], e[3]))
            else:
                st["moves"].append((t, e[2], e[3]))
            continue
        flush_moves()
        if k == "kdown":
            vk = e[2]
            if vk in _MOD_OF_VK:
                m = _MOD_OF_VK[vk]
                if m not in mods:
                    mods[m] = {"t": t, "used": False}
                continue
            shift = "shift" in mods
            combo = [m for m in ("ctrl", "alt", "win") if m in mods]
            caps = bool(e[4]) if len(e) > 4 else False
            ch = None if combo else char_fn(vk, shift, caps)
            if ch and ch.isprintable():
                if shift:
                    mods["shift"]["used"] = True
                tx = st["text"]
                if tx and t - tx["t1"] > o["text_gap"] and o["timing"]:
                    flush_text()
                    tx = None
                if tx is None:
                    tx = st["text"] = {"t0": t, "t1": t, "chars": []}
                tx["chars"].append(ch)
                tx["t1"] = t
                continue
            if vk == 0x08 and st["text"] and st["text"]["chars"] and not combo:
                st["text"]["chars"].pop()             # backspace while typing: fix the text
                st["text"]["t1"] = t
                continue
            flush_text()
            name = vk_name(vk)
            if name:
                emit_key(mod_combo(name), t)
            continue
        if k == "kup":
            vk = e[2]
            if vk in _MOD_OF_VK:
                m = _MOD_OF_VK[vk]
                info = mods.pop(m, None)
                if m in held_for_mouse:
                    held_for_mouse.discard(m)
                    flush_text()
                    emit({"type": "keyhold", "keys": _MOD_NAME[m], "action": "up"}, t, t)
                elif info and not info["used"] and t - info["t"] < 1.0:
                    flush_text()
                    emit_key(_MOD_NAME[m], info["t"])   # a modifier tapped on its own (e.g. Win)
            continue
        flush_text()
        if k == "wheel":
            x, y, notches, horiz = e[2], e[3], e[4], bool(e[5])
            last = steps[-1] if steps else None
            if (last and last.get("type") == "scroll" and last.get("horizontal") == horiz
                    and abs(last.get("x", 0) - x) <= 10 and abs(last.get("y", 0) - y) <= 10
                    and t - st["last_t"] <= 0.4 and (last["_n"] > 0) == (notches > 0)):
                last["_n"] += notches
                last["amount"] = int(round(last["_n"])) or (1 if last["_n"] > 0 else -1)
                st["last_t"] = t
            else:
                emit({"type": "scroll", "x": x, "y": y, "_n": notches, "horizontal": horiz,
                      "amount": int(round(notches)) or (1 if notches > 0 else -1)}, t, t)
            continue
        if k == "down":
            x, y, btn = e[2], e[3], e[4]
            if st["gesture"]:                       # a second button while one is held
                g = st["gesture"]
                emit({"type": "mouse", "button": g["button"], "action": "down",
                      "x": g["x0"], "y": g["y0"]}, g["t0"], g["t0"])
                st["gesture"] = None
                emit({"type": "mouse", "button": btn, "action": "down", "x": x, "y": y}, t, t)
                continue
            for m in _MOD_ORDER:
                if m in mods and not mods[m]["used"] and m not in held_for_mouse:
                    held_for_mouse.add(m)
                    mods[m]["used"] = True
                    emit({"type": "keyhold", "keys": _MOD_NAME[m], "action": "down"}, t, t)
            st["gesture"] = {"button": btn, "t0": t, "x0": x, "y0": y, "path": [(t, x, y)],
                             "snap": snaps.get(round(t, 4))}
            continue
        if k == "up":
            x, y, btn = e[2], e[3], e[4]
            g = st["gesture"]
            if not g or g["button"] != btn:
                if not g:
                    emit({"type": "mouse", "button": btn, "action": "up", "x": x, "y": y}, t, t)
                continue
            st["gesture"] = None
            g["path"].append((t, x, y))
            dist = max(((px - g["x0"]) ** 2 + (py - g["y0"]) ** 2) ** 0.5 for _, px, py in g["path"])
            dur = t - g["t0"]
            if dist <= o["click_px"] and dur <= o["click_s"]:
                last = steps[-1] if steps else None
                if (last and last.get("type") == "click" and last.get("button") == btn
                        and last.get("clicks") == 1 and abs(last["x"] - g["x0"]) <= o["click_px"]
                        and abs(last["y"] - g["y0"]) <= o["click_px"]
                        and g["t0"] - st["last_t"] <= o["double_s"]):
                    last["clicks"] = 2
                    st["last_t"] = t
                    continue
                step = {"type": "click", "x": g["x0"], "y": g["y0"], "button": btn, "clicks": 1,
                        "use_image": False, "snap_png": "", "snap_spot": None,
                        "image_fallback": "wait", "target_mode": "screen",
                        "pick_dpi": dpi, "pick_screen": scr}
                if o["pictures"] and g["snap"]:
                    step.update(use_image=True, snap_png=g["snap"][0], snap_spot=list(g["snap"][1]))
                emit(step, g["t0"], t)
            elif dist <= o["click_px"]:
                emit({"type": "mouse", "button": btn, "action": "down", "x": g["x0"],
                      "y": g["y0"]}, g["t0"], g["t0"])
                emit({"type": "mouse", "button": btn, "action": "up", "x": x, "y": y}, t, t,
                     force_wait=True)
            else:
                t0 = g["t0"]
                path = [[round(pt - t0, 3), px, py] for pt, px, py in rdp(g["path"], o["eps"])]
                emit({"type": "drag", "button": btn, "path": path[:MAX_PATH_POINTS]}, t0, t)
    flush_moves()
    flush_text()
    end_t = max([e[1] for e in evs] + [st["last_t"]])
    g = st["gesture"]
    if g:
        emit({"type": "mouse", "button": g["button"], "action": "down", "x": g["x0"],
              "y": g["y0"]}, g["t0"], g["t0"])
        emit({"type": "mouse", "button": g["button"], "action": "up"}, end_t, end_t)
    for m in sorted(held_for_mouse):
        emit({"type": "keyhold", "keys": _MOD_NAME[m], "action": "up"}, end_t, end_t)
    for s in steps:
        s.pop("_n", None)
    return steps


# ---- run history (compact, searchable action log; never contains typed text) ----------------
RUNLOG_FIELDS = ("run", "time", "job", "elapsed", "video_pos", "step", "action", "result",
                 "video")
RUNLOG_MAX_ROWS = 50000
_RUNLOG_LOCK = threading.Lock()


def runlog_path():
    return data_path("run_history.csv")


def append_runlog(row):
    import csv
    try:
        with _RUNLOG_LOCK:
            p = runlog_path()
            new = not os.path.exists(p)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=RUNLOG_FIELDS, extrasaction="ignore")
                if new:
                    w.writeheader()
                w.writerow({k: row.get(k, "") for k in RUNLOG_FIELDS})
    except Exception:
        pass


def read_runlog():
    import csv
    try:
        with _RUNLOG_LOCK, open(runlog_path(), newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def rewrite_runlog(keep):
    """Delete run-history rows for good (keeps rows where keep(row) is true). Returns how
    many rows were deleted."""
    import csv
    rows = read_runlog()
    kept = [r for r in rows if keep(r)]
    with _RUNLOG_LOCK:
        p = runlog_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".tmp", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=RUNLOG_FIELDS, extrasaction="ignore")
            w.writeheader()
            w.writerows(kept)
        os.replace(p + ".tmp", p)
    return len(rows) - len(kept)


def trim_runlog():
    import csv
    rows = read_runlog()
    if len(rows) <= RUNLOG_MAX_ROWS:
        return
    rows = rows[-RUNLOG_MAX_ROWS:]
    try:
        with _RUNLOG_LOCK:
            p = runlog_path()
            with open(p + ".tmp", "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=RUNLOG_FIELDS, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
            os.replace(p + ".tmp", p)
    except Exception:
        pass


# ---- screen video of runs (optional, local only) -----------------------------------------------
VIDEO_PRESETS = {
    "compact": dict(fps=2, scale=0.5, label="Compact: 2 frames a second at half size. Small "
                                            "files (very roughly 10-40 MB an hour)."),
    "standard": dict(fps=5, scale=0.75, label="Standard: 5 frames a second at ¾ size "
                                              "(very roughly 40-150 MB an hour)."),
    "high": dict(fps=10, scale=1.0, label="High: 10 frames a second at full size. Large files "
                                          "(very roughly 150-600 MB an hour)."),
}
VIDEO_MIN_FREE_START = 1024 ** 3          # don't start with less than 1 GB free
VIDEO_MIN_FREE_RUN = 300 * 1024 ** 2      # stop recording below 300 MB free
VIDEO_FILE_RE = re.compile(r"^clickue_run_\d{8}_\d{6}_[A-Za-z0-9_-]{0,40}\.(mp4|avi)$")
DIAG_FILE_RE = re.compile(r"^clickue_fail_\d{8}_\d{6}_[A-Za-z0-9_-]{0,40}\.png$")


def safe_file_part(name, n=40):
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", str(name)).strip("-_")
    return s[:n] or "job"


def video_folder(settings):
    """The folder for videos: the user's choice, or <data folder>\\recordings."""
    d = (settings.get("video_dir") or "").strip()
    return os.path.abspath(d) if d else data_path("recordings")


def free_bytes(folder):
    try:
        return shutil.disk_usage(folder).free
    except Exception:
        return 0


def prune_files(folder, pattern, keep_days=None, max_bytes=None, keep_count=None):
    """Delete Clickue's own files (names matching `pattern`) in one folder, oldest first,
    until the limits hold. Never touches other files and never goes into subfolders.
    Returns the number of files removed."""
    try:
        names = [n for n in os.listdir(folder) if pattern.match(n)]
    except Exception:
        return 0
    files = []
    for n in names:
        p = os.path.join(folder, n)
        try:
            if os.path.isfile(p) and not os.path.islink(p):
                s = os.stat(p)
                files.append((s.st_mtime, s.st_size, p))
        except Exception:
            pass
    files.sort()
    removed, now = 0, time.time()
    total = sum(f[1] for f in files)
    for i, (mt, size, p) in enumerate(files):
        too_old = keep_days is not None and now - mt > keep_days * 86400
        too_big = max_bytes is not None and total > max_bytes
        too_many = keep_count is not None and len(files) - i > keep_count
        if not (too_old or too_big or too_many):
            continue
        try:
            os.remove(p)
            removed += 1
            total -= size
        except Exception:
            pass
    return removed


class RunVideo:
    """Records the screen while one run is going (only then), to a local file. Frames are
    taken on a background thread; the run never waits for it. Failures (no codec, disk
    full) stop the recording, never the run."""

    def __init__(self, folder, job_name, preset="standard", redact=(), hidden=None,
                 grab=None, now=None):
        p = VIDEO_PRESETS.get(preset, VIDEO_PRESETS["standard"])
        self.fps, self.scale = p["fps"], p["scale"]
        self.folder, self.redact = folder, [r for r in (redact or []) if _clean_rect(r)]
        self.hidden = hidden or (lambda: False)
        self.grab = grab or (lambda: grab_screen(move_cursor=False))
        stamp_ = datetime.fromtimestamp(now or time.time()).strftime("%Y%m%d_%H%M%S")
        self.base = f"clickue_run_{stamp_}_{safe_file_part(job_name)}"
        self.path, self.writer, self.size = "", None, None
        self.frames, self.status, self.error = 0, "starting", ""
        self.paused = False
        self._stop = threading.Event()
        self.thread = None
        self.origin = (0, 0)

    def position(self):
        """Seconds into the video (what a step logged now will be at)."""
        return round(self.frames / self.fps, 1)

    def _open(self, w, h):
        for fourcc, ext in (("mp4v", ".mp4"), ("MJPG", ".avi")):
            path = os.path.join(self.folder, self.base + ext)
            try:
                wr = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*fourcc), self.fps, (w, h))
                if wr.isOpened():
                    return wr, path
                wr.release()
            except Exception:
                pass
            try:
                if os.path.exists(path) and os.path.getsize(path) == 0:
                    os.remove(path)
            except Exception:
                pass
        return None, ""

    def start(self):
        if not HAVE_CV:
            self.status, self.error = "off", "video needs opencv (picture matching) installed"
            return False
        try:
            os.makedirs(self.folder, exist_ok=True)
        except Exception as e:
            self.status, self.error = "off", f"can't use the video folder ({e})"
            return False
        if free_bytes(self.folder) < VIDEO_MIN_FREE_START:
            self.status, self.error = "off", "less than 1 GB free on the video drive"
            return False
        try:
            img, self.origin = self.grab()
        except Exception as e:
            self.status, self.error = "off", f"can't capture the screen ({e})"
            return False
        w, h = max(2, int(img.width * self.scale) // 2 * 2), max(2, int(img.height * self.scale) // 2 * 2)
        self.size = (w, h)
        self.writer, self.path = self._open(w, h)
        if not self.writer:
            self.status, self.error = "off", "no video format is available on this computer"
            return False
        self.status = "recording"
        self._write(img)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return True

    def _frame(self, img):
        if self.hidden():
            frame = Image.new("RGB", self.size, (24, 24, 28))
            ImageDraw.Draw(frame).text((20, 20), "Hidden while Clickue enters text",
                                       fill=(200, 200, 200))
            return frame
        if self.redact:
            img = img.copy()
            d = ImageDraw.Draw(img)
            ox, oy = self.origin
            for x, y, w, h in self.redact:
                d.rectangle((x - ox, y - oy, x - ox + w, y - oy + h), fill=(0, 0, 0))
        if img.size != self.size:
            img = img.resize(self.size, Image.BILINEAR)
        return img

    def _write(self, img):
        frame = self._frame(img)
        self.writer.write(cv2.cvtColor(np.asarray(frame), cv2.COLOR_RGB2BGR))
        self.frames += 1

    def _loop(self):
        step = 1.0 / self.fps
        nxt, last_disk = time.time() + step, time.time()
        while not self._stop.is_set():
            delay = nxt - time.time()
            if delay > 0:
                self._stop.wait(delay)
                if self._stop.is_set():
                    break
            nxt += step
            if self.paused:
                nxt = time.time() + step
                continue
            try:
                if time.time() - last_disk > 5:
                    last_disk = time.time()
                    if free_bytes(self.folder) < VIDEO_MIN_FREE_RUN:
                        self.status, self.error = "stopped", "the disk is almost full"
                        break
                img, self.origin = self.grab()
                self._write(img)
                if nxt < time.time() - 1:          # fell behind: skip ahead, don't pile up
                    nxt = time.time() + step
            except Exception as e:
                self.status, self.error = "stopped", f"recording failed ({e})"
                break
        try:
            self.writer.release()
        except Exception:
            pass

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(5)
        elif self.writer:
            try:
                self.writer.release()
            except Exception:
                pass
        if self.status == "recording":
            self.status = "done"
        return self.path


# ---- running steps (the workflow engine) -------------------------------------------------------
class StopRun(Exception):
    """The run must end now (cancelled, Clickue closing, time limit)."""


class StepFailed(Exception):
    """A step failed and its "if it fails" choice is to stop."""


TEXT_STEPS = ("type", "paste")
INPUT_STEPS = ("click", "type", "paste", "key", "move", "drag", "mouse", "scroll", "keyhold")
MAX_EXECUTED_STEPS = 200_000
MAX_GROUP_DEPTH = 4
DEFAULT_RUN_LIMIT_S = 6 * 3600


class WorkflowRun:
    """Runs a job's steps. mode: "run" (for real), "dry" (look only: finds targets and checks
    conditions, never clicks or types) or "debug" (for real, but a debugger is asked before
    every step). Every loop, retry and wait has a limit, and Stop / Pause all / the emergency
    hotkey are checked between steps and during waits."""

    def __init__(self, app, job, mode="run", debugger=None, ctx=None, groups=None):
        self.app, self.job, self.mode = app, job, mode
        self.dry = mode == "dry"
        self.debugger, self.ctx = debugger, ctx or {}
        self.groups = list(groups if groups is not None else (getattr(app, "groups", None) or []))
        self.vars = builtin_vars()
        self.vars.update(job="" if job is None else job.get("name", ""),
                         run=str(int(job.get("count") or 0) + 1), loop="0")
        self.vars.update({k: str(v) for k, v in (job.get("saved_vars") or {}).items()})
        self.persist = {}
        self.report = []                  # dry run / debug lines (never typed text)
        self.executed = 0
        self.t0 = time.time()
        self.limit = _clamp_num(job.get("run_limit_s", DEFAULT_RUN_LIMIT_S), 10,
                                MAX_RUN_LIMIT_S, DEFAULT_RUN_LIMIT_S)
        self.group_names = []
        self.paused_logged = False
        self.current = None

    # ---- bookkeeping
    def num(self, i):
        if self.group_names:
            return f"{i + 1} of group “{self.group_names[-1]}”"
        return str(i + 1)

    def say(self, i, st, text):
        w, _ = describe_step(st, private=True, groups=self.groups)
        self.report.append((self.num(i), w, text))

    def log_action(self, i, st, result):
        run_id = self.ctx.get("run")
        if not run_id:
            return
        w, d = describe_step(st, private=True, groups=self.groups)
        video = self.ctx.get("video")
        append_runlog({"run": run_id, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                       "job": self.job.get("name", ""), "elapsed": round(time.time() - self.t0, 1),
                       "video_pos": video.position() if video and video.status == "recording" else "",
                       "step": self.num(i), "action": f"{w}: {d}"[:200], "result": result[:200],
                       "video": os.path.basename(video.path) if video and video.path else ""})

    def check_stop(self):
        app = self.app
        if app.stop.is_set():
            raise StopRun("Clickue is closing")
        if self.dry:
            return
        rc = getattr(app, "run_cancel", None)
        if rc is not None and rc.is_set():
            raise StopRun("stopped by you")
        if time.time() - self.t0 > self.limit:
            raise StopRun(f"stopped: the run went over its time limit ({fmt_dur(self.limit)})")
        if self.mode == "run" and app.settings.get("paused"):
            HELD.release_all()
            if not self.paused_logged:
                self.paused_logged = True
                app.log(f"[{self.job.get('name')}] paused between steps - it carries on when "
                        f"you resume")
            while app.settings.get("paused"):
                if app.stop.is_set() or (rc is not None and rc.is_set()):
                    raise StopRun("stopped by you" if not app.stop.is_set() else "Clickue is closing")
                time.sleep(0.3)
                self.t0 += 0.3            # paused time doesn't count towards the time limit

    def tick(self):
        """Called often during waits: stop checks, and letting other jobs run if allowed."""
        self.check_stop()
        if self.mode == "run" and self.job.get("let_others_run") and not HELD.holding():
            y = getattr(self.app, "yield_to_others", None)
            if y:
                y(self.job)

    def sleep(self, secs):
        end = time.time() + max(0.0, float(secs))
        while True:
            self.tick()
            left = end - time.time()
            if left <= 0:
                return
            time.sleep(min(0.2, left))

    def set_hidden(self, on):
        """Black out the run's video while text is being typed or pasted."""
        if on:
            self.app.video_hide_until = time.time() + 3600
        else:
            self.app.video_hide_until = time.time() + 1.0

    # ---- running
    def run(self, steps=None):
        """Returns (ok, message)."""
        steps = (self.job.get("steps") or []) if steps is None else steps
        nodes, errors = parse_blocks(steps)
        if errors:
            return False, "the steps aren't valid: " + errors[0]
        try:
            self.run_nodes(nodes)
            return True, ""
        except (StopRun, StepFailed) as e:
            return False, str(e)
        finally:
            if not self.dry:
                HELD.release_all()
                if getattr(self.app, "video_hide_until", 0) > time.time() + 2:
                    self.set_hidden(False)
                if self.persist:
                    self.save_persisted()

    def save_persisted(self):
        app, job = self.app, self.job
        target = next((j for j in getattr(app, "jobs", []) if j.get("id") == job.get("id")), None)
        with app.lock:
            for j in (job, target):
                if j is not None:
                    sv = dict(j.get("saved_vars") or {})
                    sv.update(self.persist)
                    j["saved_vars"] = sv

    def run_nodes(self, nodes):
        for n in nodes:
            t = n["st"].get("type")
            if t == "if":
                yes = self.condition_step(n)
                self.run_nodes(n["body"] if yes else n["orelse"])
            elif t == "repeat":
                self.repeat_step(n)
            else:
                self.run_step(n)

    def before(self, i, st):
        self.check_stop()
        self.executed += 1
        if self.executed > MAX_EXECUTED_STEPS:
            raise StopRun(f"stopped to be safe: more than {MAX_EXECUTED_STEPS:,} steps in one run")
        self.current = (self.num(i), st)
        prog = getattr(self.app, "run_progress", None)
        if prog:
            prog(self, i, st)
        if not self.dry:
            time.sleep(0.15)
        if self.debugger:
            self.debugger.before(self, i, st)

    def run_step(self, n):
        i, st = n["i"], n["st"]
        t = st.get("type")
        self.before(i, st)
        tries = 1 if self.dry else 1 + _clamp_num(st.get("retries", 0), 0, 10, 0)
        ok, msg = False, ""
        for k in range(tries):
            try:
                ok, msg = self.exec_step(st)
            except (StopRun, StepFailed):
                raise
            except Exception as e:                      # never let one step crash the run
                ok, msg = False, f"unexpected problem ({type(e).__name__}: {e})"[:200]
            if ok or self.dry:
                break
            if k < tries - 1:
                self.log_action(i, st, f"failed ({msg}); trying again")
                self.sleep(_clamp_num(st.get("retry_wait", 2), 0, 3600, 2, as_int=False))
        if self.debugger:
            self.debugger.after(self, i, st, ok, msg)
        if self.dry:
            self.say(i, st, msg)
            return
        self.log_action(i, st, "ok" if ok else f"failed: {msg}")
        name = self.job.get("name", "")
        if ok:
            if t == "waitpic":
                self.app.log(f"[{name}] step {self.num(i)}: picture {msg}")
            return
        if t == "waitpic" and msg.startswith("timeout") and st.get("on_timeout") == "continue":
            self.app.log(f"[{name}] step {self.num(i)}: {msg} - continuing")
            return
        if st.get("on_fail") == "continue":
            self.app.log(f"[{name}] step {self.num(i)} failed ({msg}) - continuing, as set "
                         f"for that step")
            return
        if msg.startswith("(click) "):
            raise StepFailed(f"step {self.num(i)} (click): {msg[8:]}")
        raise StepFailed(f"step {self.num(i)}: {msg}")

    # ---- conditions, loops, groups
    def eval_cond(self, cond):
        cond = cond or {}
        if cond.get("kind") == "var":
            try:
                want = expand_vars(cond.get("value", ""), self.vars, 1000)
            except ValueError:
                want = cond.get("value", "")
            have = self.vars.get(cond.get("var", ""), "")
            return compare_values(have, cond.get("op", "=="), want), f"{{{cond.get('var')}}} is “{short_title(str(have), 30)}”"
        wait = 0 if self.dry else float(cond.get("wait", 0) or 0)
        end = time.time() + wait
        while True:
            res, note = check_condition(cond)
            if res or time.time() >= end:
                return res, note
            self.sleep(min(STEP_POLL_S, max(0.05, end - time.time())))

    def condition_step(self, n):
        i, st = n["i"], n["st"]
        self.before(i, st)
        res, note = self.eval_cond(st.get("cond"))
        text = f"{'TRUE' if res else 'false'} ({note})"
        if self.dry:
            self.say(i, st, f"condition is {text} now → "
                            f"{'runs the steps under If' if res else 'runs the Otherwise steps' if n['orelse'] else 'skips the steps under If'}")
        else:
            self.log_action(i, st, f"condition {text}")
        if self.debugger:
            self.debugger.after(self, i, st, True, f"condition {text}")
        return res

    def repeat_step(self, n):
        i, st = n["i"], n["st"]
        self.before(i, st)
        until = st.get("mode") == "until"
        limit_n = _clamp_num(st.get("max_times" if until else "times", 3), 1, MAX_REPEAT, 3)
        limit_s = _clamp_num(st.get("max_seconds", 600), 1, MAX_RUN_LIMIT_S, 600)
        start, count = time.time(), 0
        if self.dry:
            self.say(i, st, "would repeat the steps inside; here they're shown once")
        while True:
            if until:
                res, note = self.eval_cond(st.get("cond"))
                if res:
                    self.log_action(i, st, f"done after {count} time(s): condition true")
                    return
                if count >= limit_n or time.time() - start > limit_s:
                    msg = (f"the condition didn't come true after {count} time(s) / "
                           f"{fmt_dur(time.time() - start)}")
                    self.log_action(i, st, "stopped repeating: " + msg)
                    if st.get("on_fail") == "continue":
                        self.app.log(f"[{self.job.get('name')}] step {self.num(i)}: {msg} - "
                                     f"continuing, as set for that step")
                        return
                    raise StepFailed(f"step {self.num(i)}: {msg}")
            elif count >= limit_n:
                return
            count += 1
            self.vars["loop"] = str(count)
            self.run_nodes(n["body"])
            if self.dry:
                return

    def run_group(self, st):
        g = next((g for g in self.groups if g.get("id") == st.get("group_id")), None)
        if not g:
            return False, "the step group it uses was deleted"
        if len(self.group_names) >= MAX_GROUP_DEPTH or g["name"] in self.group_names:
            return False, "a step group can't use itself"
        nodes, errors = parse_blocks(g.get("steps") or [])
        if errors:
            return False, f"group “{g['name']}”: {errors[0]}"
        self.group_names.append(g["name"])
        try:
            self.run_nodes(nodes)
        finally:
            self.group_names.pop()
        return True, f"ran group “{g['name']}”"

    # ---- single steps
    def text_of(self, st):
        limit = MAX_TYPE_CHARS if st.get("type") == "type" else MAX_PASTE_CHARS
        if st.get("secret"):
            enc = st.get("text_enc")
            if not enc:
                return None, "the secret text isn't set here - edit the step and enter it again"
            try:
                text = unprotect_text(enc)
            except ValueError as e:
                return None, f"{e} - edit the step and enter it again"
        else:
            text = st.get("text", "")
        if st.get("use_vars"):
            try:
                text = expand_vars(text, self.vars, limit)
            except ValueError as e:
                return None, str(e)
        if len(text) > limit:
            return None, f"the text is longer than {limit:,} characters"
        return text, ""

    def exec_step(self, st):
        """One step. Returns (ok, message). Never puts typed text in the message."""
        t = st.get("type")
        dry = self.dry
        rs = self.app.settings.get("restore_cursor", True)
        if t == "wait":
            lo, hi = st.get("min", 1), st.get("max", st.get("min", 1))
            if isinstance(lo, int) and isinstance(hi, int):
                secs = random.randint(min(lo, hi), max(lo, hi)) if hi != lo else lo
            else:
                lo, hi = float(lo), float(hi)
                secs = random.uniform(min(lo, hi), max(lo, hi)) if hi != lo else lo
            if dry:
                return True, f"would wait {fmt_secs(secs)}"
            self.sleep(secs)
            return True, "waited"
        if t == "waitpic":
            if dry:
                if not HAVE_CV:
                    return False, "picture matching isn't installed"
                found, x, y, score, sc = picture_on_screen(st["png"], area=st.get("area"))
                return True, (f"the picture is showing now ({score:.0%})" if found else
                              f"the picture isn't showing now (best {score:.0%}); it would wait "
                              f"up to {fmt_dur(int(st.get('timeout', 60)))}")
            return self.app.wait_for_picture(st, tick=self.tick, job=self.job)
        if t == "set":
            try:
                val = expand_vars(st.get("value", ""), self.vars, 1000)
            except ValueError as e:
                return False, str(e)
            name, op = st.get("var", ""), st.get("op", "set")
            if op in ("add", "sub"):
                cur, amt = _as_number(self.vars.get(name, "0")), _as_number(val)
                if cur is None or amt is None:
                    return False, f"{{{name}}} or the amount isn't a number"
                val = str(cur + amt if op == "add" else cur - amt)
            self.vars[name] = val
            if st.get("persist") and not dry:
                self.persist[name] = val
            return True, f"{{{name}}} is now “{short_title(val, 30)}”"
        if t == "group":
            return self.run_group(st)
        if t not in INPUT_STEPS:
            return False, f"unknown step type {t}"
        if not dry and not screen_available():
            return False, "screen locked or session disconnected"
        if t == "click":
            a = adapter_for(st)
            ok, x, y, msg, how = a.locate(st, activate=st.get("target_mode") == "window",
                                          check_cover=not dry)
            if not ok:
                return False, f"(click) {msg}"
            if dry:
                return True, f"would click at ({x}, {y}) - found {how}"
            return do_click(x, y, st.get("button", "left"), int(st.get("clicks", 1)), rs,
                            human=mouse_style(self.app.settings, self.job, st))
        if t in TEXT_STEPS:
            text, why = self.text_of(st)
            if text is None:
                return False, why
            if dry:
                return True, (f"would {t} {len(text)} character{'s' if len(text) != 1 else ''} "
                              f"into whatever has focus")
            self.set_hidden(True)
            try:
                if t == "type":
                    return send_text(text)
                return paste_text(text, st.get("paste_keys", "Ctrl+V"),
                                  st.get("restore_clipboard", True), st.get("settle", 0.3))
            finally:
                self.set_hidden(False)
        if t == "key":
            n = _clamp_num(st.get("times", 1), 1, 100, 1)
            if dry:
                return True, f"would press {st.get('keys', '')}" + (f" {n} times" if n > 1 else "")
            for k in range(n):
                ok, msg = press_keys(st.get("keys", ""))
                if not ok:
                    return ok, msg
                if k < n - 1:
                    self.sleep(0.05)
            return True, "pressed"
        if t in ("move", "drag"):
            path = st.get("path") or []
            if not path:
                return False, "no path"
            if dry:
                return True, (f"would {'drag' if t == 'drag' else 'move the mouse'} from "
                              f"({path[0][1]}, {path[0][2]}) to ({path[-1][1]}, {path[-1][2]})")
            ok, msg = move_mouse(path[0][1], path[0][2])
            if not ok:
                return ok, msg
            if t == "drag":
                time.sleep(0.05)
                HELD.button(st.get("button", "left"), True)
            base = time.time()
            try:
                for pt, x, y in path[1:]:
                    while time.time() - base < pt:
                        self.check_stop()
                        time.sleep(min(0.01, max(0.0, pt - (time.time() - base))))
                    ok, msg = move_mouse(x, y)
                    if not ok:
                        return ok, msg
            finally:
                if t == "drag":
                    time.sleep(0.05)
                    HELD.button(st.get("button", "left"), False)
            return True, "dragged" if t == "drag" else "moved"
        if t == "mouse":
            if dry:
                return True, f"would {'press' if st.get('action') == 'down' else 'release'} the " \
                             f"{st.get('button', 'left')} button"
            if st.get("x") is not None and st.get("y") is not None:
                ok, msg = move_mouse(st["x"], st["y"])
                if not ok:
                    return ok, msg
                time.sleep(0.03)
            return HELD.button(st.get("button", "left"), st.get("action") == "down")
        if t == "scroll":
            if dry:
                return True, "would scroll " + describe_step(st)[1]
            if st.get("x") is not None and st.get("y") is not None:
                ok, msg = move_mouse(st["x"], st["y"])
                if not ok:
                    return ok, msg
                time.sleep(0.03)
            return scroll_wheel(st.get("amount", -3), st.get("horizontal", False))
        if t == "keyhold":
            try:
                vk = parse_combo(st.get("keys", ""))[0]
            except ValueError as e:
                return False, str(e)
            if dry:
                return True, f"would {'hold down' if st.get('action') == 'down' else 'release'} " \
                             f"{st.get('keys')}"
            return HELD.key(vk, st.get("action") == "down")
        return False, f"unknown step type {t}"


# ---- one place where real input happens: the action queue ------------------------------------
PRIORITY_ORDER = {"high": 0, "normal": 1, "low": 2}


class ExecutionWorker:
    """Where actions are carried out. Version 1 has one worker: this Windows desktop, which
    has ONE mouse and ONE keyboard focus, so its actions run strictly one at a time.
    A future worker for a truly separate desktop (another VM or Windows session) would set
    isolated = True and own its own queue; only isolated workers may run at the same time
    as each other. Clickue never fakes several mice on one desktop."""
    api = 1
    name = ""
    isolated = False

    def describe(self):
        return self.name


class LocalDesktopWorker(ExecutionWorker):
    name = "This Windows desktop"
    isolated = False


class ActionQueue:
    """Clicks, key presses and runs from all jobs wait here and are carried out one at a
    time. Watchers keep looking at the screen meanwhile (looking doesn't need the mouse)."""

    def __init__(self, worker=None):
        self.worker = worker or LocalDesktopWorker()
        self.cv = threading.Condition()
        self.items = []
        self.seq = 0
        self.running = None
        self.active = False

    def put(self, job, kind, priority=None, fn=None, label=""):
        """Queue an action (one per job and kind). Returns the item, or None if that job
        already has the same action waiting or running."""
        with self.cv:
            jid = job.get("id") if job else None
            for it in self.items + ([self.running] if self.running else []):
                if jid and it["job_id"] == jid and it["kind"] == kind:
                    return None
            self.seq += 1
            pr = PRIORITY_ORDER.get(priority or (job or {}).get("priority", "normal"), 1)
            it = {"seq": self.seq, "prio": pr, "job": job, "job_id": jid, "kind": kind,
                  "fn": fn, "label": label or (job or {}).get("name", ""), "queued": time.time(),
                  "done": threading.Event(), "result": None, "warned": False}
            self.items.append(it)
            self.items.sort(key=lambda x: (x["prio"], x["seq"]))
            self.cv.notify_all()
            return it

    def take(self, timeout=0.5, exclude_job=None):
        with self.cv:
            if not self.items:
                self.cv.wait(timeout)
            for k, it in enumerate(self.items):
                if exclude_job is not None and it["job_id"] == exclude_job:
                    continue
                return self.items.pop(k)
            return None

    def waiting(self):
        with self.cv:
            return list(self.items)

    def remove_job(self, job_id):
        with self.cv:
            gone = [it for it in self.items if it["job_id"] == job_id]
            self.items = [it for it in self.items if it["job_id"] != job_id]
        for it in gone:
            it["done"].set()

    def clear(self):
        with self.cv:
            gone, self.items = self.items, []
        for it in gone:
            it["done"].set()
        return len(gone)


# ---- macro recorder (Windows low-level hooks) --------------------------------------------------
if IS_WIN:
    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
    user32.GetKeyState.argtypes = [ctypes.c_int]
    user32.GetKeyState.restype = ctypes.c_short
    kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wt.HMODULE

_MOUSE_MSGS = {0x201: ("down", "left"), 0x202: ("up", "left"), 0x204: ("down", "right"),
               0x205: ("up", "right"), 0x207: ("down", "middle"), 0x208: ("up", "middle")}


class MacroRecorder:
    """Records real mouse and keyboard input (not Clickue's own) until stopped.
    Input from Clickue itself is ignored (injected events are flagged by Windows).
    Nothing is sent anywhere; events stay in memory until you save the recording."""
    MAX_EVENTS = 300_000

    def __init__(self, opts=None, on_limit=None, snapper=None):
        self.opts = dict(REC_DEFAULTS, **(opts or {}))
        self.events = []
        self.lock = threading.Lock()
        self.state = "idle"
        self.t0 = 0.0
        self.paused_total = 0.0
        self.pause_start = None
        self.exclude = []
        self.on_limit = on_limit
        self.snapper = snapper or self._snap
        self.snap_q = queue.Queue()
        self._last_move = (-1.0, 0, 0)
        self.tid = None
        self.thread = None
        self.error = ""
        self.ready = threading.Event()
        self.counts = {"clicks": 0, "keys": 0}

    def now(self):
        return time.time() - self.t0 - self.paused_total

    def add(self, ev):
        with self.lock:
            if len(self.events) >= self.MAX_EVENTS:
                if self.state == "recording":
                    self.state = "full"
                    if self.on_limit:
                        self.on_limit()
                return
            self.events.append(ev)

    def mouse(self, msg, x, y, data):
        if self.state != "recording":
            return
        t = self.now()
        if msg == 0x200:
            lt, lx, ly = self._last_move
            if t - lt < 0.015 and abs(x - lx) < 4 and abs(y - ly) < 4:
                return
            self._last_move = (t, x, y)
            self.add(("move", t, x, y))
        elif msg in _MOUSE_MSGS:
            kind, btn = _MOUSE_MSGS[msg]
            self.add((kind, t, x, y, btn))
            if kind == "down":
                self.counts["clicks"] += 1
                if self.opts.get("pictures"):
                    self.snap_q.put((t, x, y))
        elif msg in (0x20A, 0x20E):
            delta = ctypes.c_short((data >> 16) & 0xFFFF).value
            self.add(("wheel", t, x, y, delta / 120.0, msg == 0x20E))

    def key(self, msg, vk):
        if self.state != "recording":
            return
        t = self.now()
        if msg in (0x100, 0x104):
            caps = bool(user32.GetKeyState(0x14) & 1) if IS_WIN else False
            self.counts["keys"] += 1
            self.add(("kdown", t, vk, False, caps))
        elif msg in (0x101, 0x105):
            self.add(("kup", t, vk))

    def _snap(self, x, y):
        """A small picture around (x, y), without moving the mouse."""
        img, (vx, vy) = grab_screen(move_cursor=False)
        w, h = SNAP_SIZES["Small"]
        W, H = img.size
        w, h = min(w, W), min(h, H)
        left = min(max(x - vx - w // 2, 0), W - w)
        top = min(max(y - vy - h // 2, 0), H - h)
        crop = img.crop((left, top, left + w, top + h))
        if HAVE_CV and float(np.asarray(crop.convert("L"), dtype=np.float32).std()) < 6:
            return None                       # a plain area can't be found again reliably
        return img_to_b64(crop), (x - vx - left, y - vy - top)

    def _snap_loop(self):
        while True:
            item = self.snap_q.get()
            if item is None:
                return
            t, x, y = item
            try:
                r = self.snapper(x, y)
                if r:
                    self.add(("snap", t, r[0], r[1]))
            except Exception:
                pass

    def _hook_loop(self):
        self.tid = kernel32.GetCurrentThreadId()

        def mproc(n, wp, lp):
            if n == 0:
                ms = ctypes.cast(lp, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                if not (ms.flags & 0x01):                  # LLMHF_INJECTED: our own input
                    try:
                        self.mouse(wp, ms.pt.x, ms.pt.y, ms.mouseData)
                    except Exception:
                        pass
            return user32.CallNextHookEx(None, n, wp, lp)

        def kproc(n, wp, lp):
            if n == 0:
                kb = ctypes.cast(lp, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not (kb.flags & 0x10):                  # LLKHF_INJECTED
                    try:
                        self.key(wp, kb.vkCode)
                    except Exception:
                        pass
            return user32.CallNextHookEx(None, n, wp, lp)

        self._procs = (HOOKPROC(mproc), HOOKPROC(kproc))   # keep references alive
        hmod = kernel32.GetModuleHandleW(None)
        hm = user32.SetWindowsHookExW(14, self._procs[0], hmod, 0)      # WH_MOUSE_LL
        hk = user32.SetWindowsHookExW(13, self._procs[1], hmod, 0)      # WH_KEYBOARD_LL
        if not hm or not hk:
            self.error = "Windows didn't allow recording (input hooks unavailable)"
            for h in (hm, hk):
                if h:
                    user32.UnhookWindowsHookEx(h)
            self.ready.set()
            return
        self.ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hm)
        user32.UnhookWindowsHookEx(hk)

    def start(self):
        if not IS_WIN:
            self.error = "recording only works on Windows"
            return False
        self.t0 = time.time()
        self.state = "recording"
        if self.opts.get("pictures") and HAVE_PIL:
            threading.Thread(target=self._snap_loop, daemon=True).start()
        self.thread = threading.Thread(target=self._hook_loop, daemon=True)
        self.thread.start()
        self.ready.wait(3)
        if self.error:
            self.state = "idle"
            self.snap_q.put(None)
            return False
        return True

    def pause(self):
        if self.state == "recording":
            self.state = "paused"
            self.pause_start = time.time()

    def resume(self):
        if self.state == "paused":
            self.paused_total += time.time() - (self.pause_start or time.time())
            self.pause_start = None
            self.state = "recording"

    def _unhook(self):
        if self.tid:
            user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)               # WM_QUIT
        if self.thread:
            self.thread.join(2)
        self.snap_q.put(None)

    def stop(self):
        """Stop and return the recorded steps."""
        if self.state == "paused":
            self.resume()
        self.state = "stopping"
        if IS_WIN:
            self._unhook()
        deadline = time.time() + 3                  # let pending pictures finish
        while not self.snap_q.empty() and time.time() < deadline:
            time.sleep(0.05)
        with self.lock:
            events = list(self.events)
        self.state = "idle"
        return finish_recording(compress_recording(events, self.opts, exclude=self.exclude))

    def cancel(self):
        self.state = "idle"
        if IS_WIN:
            self._unhook()
        with self.lock:
            self.events = []


def finish_recording(steps):
    """Drop trailing mouse movement and waits (moving to the Stop button)."""
    while steps and steps[-1].get("type") in ("move", "wait"):
        steps.pop()
    while steps and steps[0].get("type") == "wait":
        steps.pop(0)
    return steps


# ---- global hotkeys --------------------------------------------------------------------------
HOTKEY_MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}


def parse_hotkey(text):
    """'Ctrl+Alt+P' -> (modifiers, vk). Needs at least one modifier and one normal key."""
    mods, vk = 0, None
    for part in str(text).replace(" ", "").split("+"):
        p = part.lower()
        if not p:
            continue
        if p in HOTKEY_MODS:
            mods |= HOTKEY_MODS[p]
        elif p in VK_NAMES and VK_NAMES[p] not in MODIFIER_VKS:
            vk = VK_NAMES[p]
        elif len(p) == 1 and (p.isalpha() or p.isdigit()):
            vk = ord(p.upper())
        else:
            raise ValueError(f"unknown key “{part}”")
    if not mods or vk is None:
        raise ValueError("use at least one of Ctrl / Alt / Shift / Win plus a key")
    return mods, vk


class HotkeyThread(threading.Thread):
    """Listens for system-wide hotkeys (works while Clickue is hidden in the tray)."""

    def __init__(self, bindings, on_hotkey, on_error):
        super().__init__(daemon=True)
        self.bindings = bindings          # {id: (text, command)}
        self.on_hotkey, self.on_error = on_hotkey, on_error
        self.tid = None
        self.ready = threading.Event()

    def run(self):
        if not IS_WIN:
            self.ready.set()
            return
        self.tid = kernel32.GetCurrentThreadId()
        registered = []
        for hid, (text, cmd) in self.bindings.items():
            try:
                mods, vk = parse_hotkey(text)
                if user32.RegisterHotKey(None, hid, mods | 0x4000, vk):   # MOD_NOREPEAT
                    registered.append(hid)
                else:
                    self.on_error(f"{text} is already used by another program")
            except ValueError as e:
                self.on_error(f"{text}: {e}")
        self.ready.set()
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312 and msg.wParam in self.bindings:      # WM_HOTKEY
                self.on_hotkey(self.bindings[msg.wParam][1])
        for hid in registered:
            user32.UnregisterHotKey(None, hid)

    def stop(self):
        if IS_WIN and self.tid:
            user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)               # WM_QUIT


DEFAULT_SETTINGS = {
    "retry_minutes": 15,
    "idle_seconds": 5,
    "keep_awake": True,
    "restore_cursor": True,
    "log_max_mb": 1,
    "theme": "system",          # system / light / dark
    "minimize_to_tray": True,
    "close_to_tray": True,
    "notifications": True,
    "start_minimized": False,
    "start_with_windows": False,
    "paused": False,
    "tray_hint_shown": False,
    "stats_date": "",
    "view_filter": "all",
    "bottom_tab": "activity",
    "split": 0.45,
    "show_cards": True,
    "main_geom": "",
    "main_zoomed": False,
    "dlg_geom": {},
    "activity_filter": "all",
    "human_move": False,            # 4.5.6: default for jobs: move the mouse like a person
    "human_speed": "normal",        # slow / normal / fast
    "rec_human": False,             # recorded macros: move like a person when they play
    "custom_colors": {},            # 4.5.6: {"light": {key: "#rrggbb"}, "dark": {...}}
    "tray_colors": True,            # 4.5.6: tray icon dot: amber/green/red
    "update_check": True,           # 4.6: look for new versions (off = never go online for it)
    "update_last_check": 0,
    "update_skip": "",              # a version the user chose to skip
    "update_later_until": 0,        # "Later": don't show the bar again before this time
    "upgrade_pending": "",          # an in-app upgrade to this version is under way
    "upgrade_from": "",
    "update_known": None,           # the newest release found (version, page, assets, notes)
    "log_level": "normal",          # 4.5.6: "quiet" / "normal" / "detailed"
    "stats_clicks_watch": 0,        # 4.5.6: today's watcher clicks (for the watcher summary)
    "stats_missed_watch": 0,
    "log_order": {},                # 4.5.6: per log, "new" (newest first) or "old"
    "activity_clear_on_start": False,   # 4.5.5: off = Activity keeps earlier runs' lines
    "activity_cleared_at": "",          # 4.5.5: "Clear view" time; older lines stay hidden
    "tests_geom": "",
    "tests_split": 0.0,
    "tests_hist_filter": "job",
    "tests_section": "all",         # 4.5.4: Tests window section (all / click / watch)
    "tests_scopes": {},             # 4.5.4: this job / all jobs, per section
    "stats_clicks": 0,
    "stats_missed": 0,
    # ---- Clickue 4
    "hotkeys_on": True,
    "hk_pause": "Ctrl+Alt+P",       # pause / resume everything
    "hk_show": "Ctrl+Alt+K",        # show / hide the window
    "alerts_on": False,
    "alert_discord": "",
    "alert_tg_token": "",
    "alert_tg_chat": "",
    "alert_events": {"watch": True, "problem": True, "finished": True, "test": False},
    "backups_on": True,
    "backups_keep": 14,
    "last_backup": "",
    "history_on": True,
    "default_watch_interval": 30,
    "default_watch_confirm": 2,
    "prefs_tab": "general",
    "install_id": "",               # last install this user has answered "keep jobs?" for
    # ---- Clickue 4.5
    "hk_stop": "Ctrl+Alt+X",        # emergency stop: end the running job, release keys, pause all
    "hk_record": "Ctrl+Alt+R",      # start / stop recording a macro
    "hk_rec_pause": "Ctrl+Alt+U",   # pause / resume the recording
    "protect_secrets": False,       # keep alert settings encrypted with Windows (DPAPI)
    "rec_moves": True,              # recorder: keep mouse movement (simplified)
    "rec_pictures": True,           # recorder: save a picture of each clicked spot
    "rec_timing": True,             # recorder: keep the pauses between actions
    "run_log_on": True,             # keep the run history (steps, results; never typed text)
    "video_on": False,              # screen video of runs (only jobs that ask for it)
    "video_preset": "standard",
    "video_dir": "",                # "" = <data folder>\recordings
    "video_keep_days": 14,
    "video_max_gb": 5,
    "video_hide_text": True,        # black out the video while text is typed or pasted
    "video_redact": [],             # screen areas always blacked out in videos [[x, y, w, h]]
    "diag_keep": 30,                # failure screenshots kept
    "warn_conflicts": True,
    # ---- Clickue 4.5.1
    "marker_seconds": 5,            # how long Show spot / Check now marks what it found
    "show_similar": False,          # Show spot / Check now also outline every similar picture
    "tray_status": True,            # tray icon tooltip and menu show the jobs' status
    "col_widths": {},               # job list column widths the user set
}


def new_job(n=1):
    return {
        "id": uuid.uuid4().hex,
        "name": f"Click {n}",
        "x": 0,
        "y": 0,
        "button": "left",
        "clicks": 1,
        "interval_s": 8 * 3600,     # scheduled every 8 hours
        "delay_min_s": 10,          # random delay after scheduled time: 10 s ...
        "delay_max_s": 15 * 60,     # ... to 15 min
        "anchored": True,           # schedule stays fixed; delays don't add up
        "random_on": True,          # add the random delay at all
        "paused": False,            # this job alone is paused (schedule kept)
        # ---- active hours
        "hours_on": False,
        "hours_from": "08:00",
        "hours_to": "22:00",
        "hours_days": [0, 1, 2, 3, 4, 5, 6],
        "hours_outside": "wait",    # a click due outside the hours: "wait" for them, or "skip"
        # ---- limits
        "limit_clicks_on": False,
        "limit_clicks": 10,
        "limit_until_on": False,
        "limit_until": "",          # "YYYY-MM-DD HH:MM"
        "run_clicks": 0,            # clicks since the job was last started
        # ---- watcher extras
        "watch_trigger": "gone",    # "gone" = click when it disappears, "appears" = when it shows
        "watch_click_picture": False,   # appears-watchers: click the picture itself
        "watch_area": None,         # [x, y, w, h] on screen, or None = whole screen
        "watch_area_screen": None,  # screen size when the area was drawn
        "found_xy": None,
        "pointer_logged": False,
        "human_move": None,         # 4.5.6: move the mouse like a person (None = Preferences)
        "issue_count": 0,           # 4.5.6: checks in a row that couldn't tell (runtime)
        "issue_since": None,
        "screen_sig": None,         # screen size + scaling at the last check (runtime)
        "settle_until": None,
        "first_miss_at": None,      # 4.6: when the change was first seen (runtime)
        "click_planned_at": None,   # 4.6: when the click was scheduled for (runtime)
        "planned_run": None,        # 4.6: a scheduled click's planned time (runtime)
        # ---- extra steps after the click
        "steps": [],
        "watch_random_on": True,    # watcher: random delay before clicking
        "first_time": "",           # optional time of day for the first scheduled time
        "enabled": False,
        "base_next": None,          # scheduled time (before random delay)
        "next_run": None,           # actual click time (scheduled + random delay)
        "deadline": None,
        "test_at": None,            # one-off scheduled test click
        "test_deadline": None,
        "last_run": None,
        "last_result": "",
        "count": 0,
        # where to click
        "target_mode": "screen",    # "screen" (fixed spot) or "window" (follows a window)
        "window_title": "",
        "window_class": "",
        "rel_x": 0,                 # spot inside the window's area
        "rel_y": 0,
        "client_w": 0,              # window size when picked
        "client_h": 0,
        "bring_to_front": True,
        "scale_with_window": False,
        "scale_with_screen": False,
        "pick_screen": None,        # [w, h] of the screen when picked
        "use_image": True,          # find the spot by its picture
        "snap_png": "",             # saved picture around the spot (PNG, base64)
        "snap_spot": None,          # [x, y] of the spot inside that picture
        "snap_size": "Medium",
        "image_fallback": "wait",   # if not found: "wait" and retry, or click "position"
        "exact_match": True,        # 4.5.1: only the picture itself, never a similar one
        "pick_dpi": None,           # display scaling when picked (96 = 100%)
        # ---- screen watcher (kind == "watch")
        "kind": "click",            # "click" = on a schedule, "watch" = when a picture disappears
        "watch_png": "",            # the picture to watch for (PNG, base64)
        "watch_interval_s": 30,     # how often to look
        "watch_confirm": 2,         # missing this many checks in a row before clicking
        "watch_delay_min_s": 1,     # random delay before the click
        "watch_delay_max_s": 5,
        "watch_cooldown_s": 30,     # after clicking, wait this long before looking again
        "watch_once": True,         # don't click again until the picture has come back
        "watch_match": "exact",     # 4.5.3: "exact" = the whole picture must match;
                                    # "partial" = enough of it (watch_partial_pct) is enough
        "watch_partial_pct": PARTIAL_DEFAULT_PCT,
        "watch_cooldown_on": True,  # use the "after clicking, wait" time at all
        # watcher runtime
        "next_check": None,
        "last_check": None,
        "last_seen": None,
        "miss_count": 0,
        "watch_state": "",          # "seen" / "missing" / "unknown"
        "armed": True,
        "pending_click_at": None,
        "pending_since": None,
        "watch_scale": None,
        "watch_note": "",
        "wtest_at": None,           # scheduled watcher test
        "wtest_deadline": None,
        "wtest_click": False,       # watcher test: really click if the picture is missing
        # ---- Clickue 4.5
        "main_click": True,         # start with a click on the spot above (off = steps only)
        "priority": "normal",       # when several jobs are due: high / normal / low
        "let_others_run": False,    # while its steps wait, other jobs may click in between
        "record_video": False,      # record the screen while this job runs (if videos are on)
        "fail_shot": False,         # save a screenshot when its steps fail
        "saved_vars": {},           # variables remembered between runs
        "run_limit_s": DEFAULT_RUN_LIMIT_S,   # a run is stopped after this long
    }


def new_watch(n=1):
    j = new_job(n)
    j.update(kind="watch", name=f"Watcher {n}")
    return j


def is_watch(j):
    return j.get("kind") == "watch"


LIGHT = dict(bg="#f4f5f7", panel="#ffffff", panel_alt="#f7f8fa", head="#f0f1f4",
             fg="#1a1c20", muted="#6b7280", border="#e1e3e8", btn="#ffffff",
             btn_border="#d5d8de", btn_active="#eef0f3", accent="#2563eb",
             accent_active="#1d4ed8", sel="#dbe7ff", sel_fg="#0b1b3f", field="#ffffff",
             warn="#b45309", good="#15803d", bad="#c62828", test="#7c3aed", grid="#e2e5ea",
             tick="#e8f0fe", outline="#b8bec8", accent2="#0f766e", accent2_active="#115e59",
             accent3="#be123c", accent3_active="#9f1239")
DARK = dict(bg="#18191c", panel="#212226", panel_alt="#26282c", head="#1c1d21",
            fg="#e8e9ec", muted="#9097a1", border="#30333a", btn="#2a2c31",
            btn_border="#363940", btn_active="#34373d", accent="#3b82f6",
            accent_active="#2f6fe0", sel="#24406e", sel_fg="#ffffff", field="#26282c",
            warn="#f5a524", good="#4ade80", bad="#f87171", test="#c4a8ff", grid="#383b43",
            tick="#1f2f4d", outline="#4b505a", accent2="#0d9488", accent2_active="#0f766e",
            accent3="#e11d48", accent3_active="#be123c")


COLOR_NAMES = (   # palette key, what it colours (4.5.6: Preferences → Appearance → colours)
    ("bg", "Window background"), ("panel", "Tables, cards and panels"),
    ("panel_alt", "Every other table row"), ("head", "Table headings"),
    ("fg", "Text"), ("muted", "Labels and secondary text"), ("border", "Borders and frames"),
    ("grid", "Grid lines in the job list"), ("field", "Input fields"),
    ("btn", "Buttons"), ("btn_border", "Button borders"), ("btn_active", "Buttons under the mouse"),
    ("outline", "Outline of buttons you can't use right now"),
    ("accent", "New click, highlights and links"), ("accent_active", "New click under the mouse"),
    ("accent2", "New watcher and steps"), ("accent2_active", "New watcher under the mouse"),
    ("accent3", "Record"), ("accent3_active", "Record under the mouse"),
    ("sel", "Selected row"), ("sel_fg", "Selected row text"), ("tick", "Ticked rows"),
    ("good", "OK / good"), ("warn", "Attention / warning"), ("bad", "Problem / failed"),
    ("test", "Tests"),
)
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def theme_palette(settings, dark):
    """The colours in use: the light or dark palette with the user's own colours on top."""
    p = dict(DARK if dark else LIGHT)
    mine = (settings.get("custom_colors") or {}).get("dark" if dark else "light") or {}
    for k, v in mine.items():
        if k in p and isinstance(v, str) and HEX_RE.match(v):
            p[k] = v.lower()
    return p


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in (r, g, b))


def clock(ts):
    """08:54:58 (or "?" when unknown)."""
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return "?"


def fmt_compact(sec):
    """8h, 15m, 10s, 1h 30m - drops zero parts."""
    sec = int(max(0, round(sec)))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    parts = [f"{v}{u}" for v, u in ((h, "h"), (m, "m"), (s, "s")) if v]
    return " ".join(parts) or "0s"


# ---------------------------------------------------------------- app
class App:
    def __init__(self, root):
        # Activity lines in the log file older than this are from earlier runs (4.5.5)
        self.session_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.root = root
        self.lock = threading.RLock()
        self.checked = set()          # job ids ticked in the job list (4.5.3, not saved)
        self.expanded = set()         # jobs whose steps are shown in the list (4.5.6)
        self.retry_counts = {}        # (job id, kind) -> tries of a waiting click (4.5.6)
        self.logq = queue.Queue()
        self.cmdq = queue.Queue()
        self.stop = threading.Event()
        self.wait_msgs = {}
        self.res_warned = set()
        self.own_visible = True
        self.tests_win = None
        self.tests_dirty = True
        hist = read_json(TESTS_PATH) if os.path.exists(TESTS_PATH) else None
        self.test_history = hist if isinstance(hist, list) else []
        self.tray = None
        self.uninstalled = False
        self.pal = LIGHT

        self.renamed_from_old = False
        self.fresh_start = False
        asked_import = False
        n_old = count_saved_jobs(OLD_DATA_DIR) if not os.path.isdir(DATA_DIR) else 0
        if n_old and os.path.isdir(OLD_DATA_DIR):
            asked_import = True
            root.withdraw()
            if messagebox.askyesno(
                    APP_NAME, f"Welcome to Clickue!\n\nFound {n_old} job(s) from the previous "
                              f"version (Scheduled AutoClicker) on this computer.\n\n"
                              f"Import them into Clickue?\n\nYes = import my jobs and settings\n"
                              f"No = start with an empty list (the old jobs stay where they "
                              f"are)", parent=root):
                self.renamed_from_old = migrate_old_data()
        os.makedirs(DATA_DIR, exist_ok=True)

        def ask(question):
            root.withdraw()
            return messagebox.askyesno(APP_NAME, question, parent=root)
        self.settings, self.jobs, migrated = self.load(ask=ask)
        self.recovery_note = ""
        if self.jobs_file_state != "ok" and not self.jobs:
            # the jobs file is gone or damaged: offer the newest backup that has jobs
            try:
                found = self.offer_backup_recovery(ask)
            except Exception as e:
                found = False
                self.recovery_note = f"Couldn't look for a backup of your jobs: {e}"
            migrated = migrated or found
        install_id = read_install_id()
        if install_id and self.settings.get("install_id") != install_id:
            # freshly installed / reinstalled: offer a clean start if jobs are left over
            # (not after an in-app upgrade: that installs again on purpose, 4.6)
            if self.jobs and not asked_import and not self.settings.get("upgrade_pending"):
                root.withdraw()
                names = ", ".join(short_title(j.get("name", "?"), 30) for j in self.jobs[:6])
                keep = messagebox.askyesno(
                    APP_NAME, f"Clickue was just installed and found {len(self.jobs)} job(s) "
                              f"from before on this computer:\n{names}"
                              f"{' …' if len(self.jobs) > 6 else ''}\n\nKeep them?\n\n"
                              f"Yes = keep my jobs and settings\n"
                              f"No = start fresh (your old jobs are saved in a backup first, "
                              f"so you can bring them back from \u2630 Menu \u2192 Backups)",
                    parent=root)
                if not keep:
                    try:
                        make_backup(self.jobs, self.settings, "before-fresh-start", self.groups)
                    except Exception:
                        pass
                    self.jobs = []
                    self.fresh_start = True
                    try:
                        write_json(TESTS_PATH, [])
                    except Exception:
                        pass
            self.settings["install_id"] = install_id
            migrated = True
        root.deiconify()
        self.setup_logging()
        keep_awake(self.settings["keep_awake"])
        self.ensure_runtime()
        if self.jobs and (self.schema_upgrade or (getattr(self, "saved_version", "")
                                                   and self.saved_version != VERSION)):
            try:              # a new version: keep a copy of the jobs as they were (4.5.1)
                make_backup(self.jobs, self.settings, f"before-upgrade-{VERSION}", self.groups)
            except Exception:
                pass

        root.title(APP_NAME)
        g = fit_geometry(self.settings.get("main_geom"), 640, 600)
        root.geometry(g or "1280x800")
        root.minsize(640, 600)
        self._geom_job = None
        try:
            self.families = set(tkfont.families(root))
        except Exception:
            self.families = set()
        self.font_family = next((f for f in ("Segoe UI Variable Text", "Segoe UI")
                                 if f in self.families), "TkDefaultFont")
        self.style = ttk.Style()
        self.build_ui()
        self.apply_theme()

        if HAVE_PIL:
            self.icon_img = self.make_icon()
            try:
                self._tk_icons = [ImageTk.PhotoImage(make_logo(n)) for n in (64, 32, 16)]
                root.iconphoto(True, *self._tk_icons)
            except Exception:
                pass

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<Configure>", self.on_root_configure, add="+")
        if self.settings.get("main_zoomed") and not (
                self.settings.get("start_minimized") or "--minimized" in sys.argv):
            root.after(60, lambda: root.state("zoomed"))
        root.bind("<Unmap>", self.on_unmap)

        self.log(f"{APP_NAME} {VERSION} started. Data folder: {DATA_DIR}")
        if self.fresh_start:
            self.log("Started fresh - your previous jobs were saved in a backup "
                     "(\u2630 Menu \u2192 Backups to bring them back).")
        if self.renamed_from_old:
            self.log(f"Welcome to Clickue! Your jobs, settings and history were copied from "
                     f"Scheduled AutoClicker. The old folder was kept as a backup: {OLD_DATA_DIR}")
            if self.settings.get("start_with_windows"):
                set_run_at_startup(True)
        if migrated:
            self.save()
        if getattr(self, "old_config_imported", False):
            try:
                os.replace(OLD_CONFIG, OLD_CONFIG + ".migrated")
            except Exception:
                pass
            self.log("Imported your jobs and settings from the old config file "
                     "(you said Yes).")
        self.log(f"Loaded {len(self.jobs)} job(s) from {JOBS_PATH}"
                 + (f" ({self.jobs_file_info})" if getattr(self, "jobs_file_info", "") else "")
                 + (f": {', '.join(short_title(j.get('name', ''), 30) for j in self.jobs[:8])}"
                    + (" …" if len(self.jobs) > 8 else "") if self.jobs else ""))
        if getattr(self, "recovery_note", ""):
            self.log(self.recovery_note)
        if self.settings.get("paused"):
            self.log("All jobs are PAUSED (use Resume all).")
        if self.schema_upgrade:
            self.log(f"Your jobs were updated for Clickue {VERSION}. A copy of them as they were "
                     f"is in \u2630 Menu \u2192 Backups (\u201cbefore-upgrade-{VERSION}\u201d).")
            self.save()
        if self.secret_note:
            self.log(self.secret_note)

        self.refresh_tree(full=True)
        self.update_buttons()
        root.after(150, self.restore_split)
        self.paned.bind("<ButtonRelease-1>", lambda e: self.root.after(50, self.remember_split))
        self.undo_stack = []
        self.hk_thread = None
        self.start_hotkeys()
        threading.Thread(target=trim_history, daemon=True).start()
        self.after_upgrade()
        root.after(60 * 1000, self.auto_update_check)    # does nothing while checks are off
        threading.Thread(target=trim_runlog, daemon=True).start()
        threading.Thread(target=self.prune_media, daemon=True).start()
        self.root.after(3000, self.backup_check)
        self.start_tray()
        self.start_input_thread()
        threading.Thread(target=self.scheduler_loop, daemon=True).start()
        root.after(500, self.ui_tick)
        root.after(700, self.tray_tick)
        root.after(200, self.poll_cmds)
        if self.settings.get("start_minimized") or "--minimized" in sys.argv:
            root.after(300, self.hide_window)

    # ------------------------------------------------------------ persistence
    def load(self, ask=None):
        """Read settings and jobs. `ask(question) -> bool` is used for the rare questions
        (importing a very old config file); without it nothing is imported."""
        settings, jobs, migrated = dict(DEFAULT_SETTINGS), [], False
        s_exists, j_exists = os.path.exists(SETTINGS_PATH), os.path.exists(JOBS_PATH)
        s_data, j_data = read_json(SETTINGS_PATH), read_json(JOBS_PATH)
        # 4.5.1 (second fix): remember whether the jobs file was missing or unreadable, so the
        # start can offer the newest backup instead of quietly starting without your jobs
        self.jobs_file_state = ("missing" if not j_exists else
                                "unreadable" if not isinstance(j_data, dict) else "ok")
        self.jobs_file_info = ""
        if isinstance(j_data, dict):
            try:
                mt = datetime.fromtimestamp(os.path.getmtime(JOBS_PATH)).strftime("%m/%d %H:%M")
            except Exception:
                mt = "?"
            self.jobs_file_info = (f"saved by Clickue {str(j_data.get('version') or '?')[:12]} "
                                   f"on {mt}")
        self.saved_version = str(j_data.get("version") or "") if isinstance(j_data, dict) else ""
        self.old_config_imported = False
        # A config file from the very first versions (next to the program). Only offered when
        # the data folder has never been used, and only after asking: it once silently
        # brought back long-deleted jobs.
        if (not s_exists and not j_exists and os.path.exists(OLD_CONFIG)
                and not data_folder_used() and ask is not None):
            old = read_json(OLD_CONFIG) or {}
            old_jobs = old.get("jobs", []) if isinstance(old.get("jobs"), list) else []
            names = ", ".join(str(j.get("name", "?"))[:40] for j in old_jobs[:6]
                              if isinstance(j, dict))
            if old_jobs and ask(f"Found an old settings file from a very early version next to "
                                f"the program:\n{OLD_CONFIG}\n\nIt has {len(old_jobs)} job(s): "
                                f"{names}{' …' if len(old_jobs) > 6 else ''}\n\nImport them?\n\n"
                                f"Yes = import them\nNo = start with an empty list"):
                s_data, j_data, migrated = old.get("settings", {}), {"jobs": old_jobs}, True
                self.old_config_imported = True
        if isinstance(s_data, dict):
            settings.update({k: v for k, v in s_data.items() if k in DEFAULT_SETTINGS})
        self.secret_note = ""
        for k in SECRET_KEYS:                 # protected alert settings (opt-in)
            v = settings.get(k) or ""
            if isinstance(v, str) and v.startswith("dpapi:"):
                try:
                    settings[k] = unprotect_text(v)
                except ValueError as e:
                    settings[k] = ""
                    self.secret_note = (f"Your phone-alert settings couldn't be read ({e}). "
                                        f"Enter them again in Preferences → Phone alerts.")
        j_data = j_data if isinstance(j_data, dict) else {}
        for j in j_data.get("jobs", []):
            if not isinstance(j, dict):
                continue
            base = new_job()
            base.update(j)
            jobs.append(base)
        groups = j_data.get("groups", [])
        self.groups = [g for g in groups if isinstance(g, dict) and g.get("id")] \
            if isinstance(groups, list) else []
        # files from Clickue 4.4 and earlier: keep a backup before saving in the new format
        self.schema_upgrade = bool(jobs) and int(_clamp_num(j_data.get("schema", 1), 0, 999, 1)) \
            < SCHEMA_VERSION
        return settings, jobs, migrated

    def offer_backup_recovery(self, ask):
        """The jobs file was missing or unreadable at start: offer the newest backup that has
        jobs. Returns True if jobs were restored."""
        bks = [b for b in list_backups() if b.get("jobs")]
        if not bks:
            return False
        b = bks[0]
        try:
            with open(b["path"], encoding="utf-8") as f:
                names = [str(j.get("name", "?"))[:30] for j in json.load(f).get("jobs", [])
                         if isinstance(j, dict)]
        except Exception:
            names = []
        why = ("is missing" if self.jobs_file_state == "missing"
               else "couldn't be read (a copy was kept as jobs.json.corrupt)")
        if not ask(f"Your jobs file {why}.\n\nThe newest backup is from {(b['created'] or b['name']).replace('T', ' ')} "
                   f"and has {b['jobs']} job(s): {', '.join(names[:6])}"
                   f"{' …' if len(names) > 6 else ''}\n\nRestore it now?\n\nYes = restore "
                   f"these jobs\nNo = start with an empty list (☰ Menu → Backups can restore "
                   f"later)"):
            self.recovery_note = "Your jobs file was missing; you chose not to restore a backup."
            return False
        jobs, groups, _ = load_import_file(b["path"])
        for j in jobs:
            j["id"] = uuid.uuid4().hex
            for k in RUNTIME_KEYS:
                j[k] = new_job().get(k)
            j["enabled"] = False            # restored jobs start stopped; start them yourself
        self.jobs = jobs
        have = {g.get("id") for g in self.groups}
        self.groups.extend(g for g in groups if g.get("id") not in have)
        self.recovery_note = (f"Restored {len(jobs)} job(s) from the backup {b['name']} "
                              f"(your jobs file {why.split(' (')[0]}). They are stopped: start "
                              f"them when you're ready.")
        return True

    def save(self):
        if self.uninstalled:
            return
        with self.lock:
            s = dict(self.settings)
            if s.get("protect_secrets") and HAVE_DPAPI:
                for k in SECRET_KEYS:
                    if s.get(k):
                        try:
                            s[k] = protect_text(s[k])
                        except Exception:
                            s[k] = ""
            jobs_doc = {"app": APP_ID, "version": VERSION, "schema": SCHEMA_VERSION,
                        "jobs": self.jobs, "groups": getattr(self, "groups", [])}
            # the jobs first (they matter most), each file on its own, with one retry: on
            # Windows another program (antivirus, backup, sync) can hold a file for a moment
            for path, data in ((JOBS_PATH, jobs_doc), (SETTINGS_PATH, s)):
                for attempt in (1, 2):
                    try:
                        write_json(path, data)
                        break
                    except Exception as e:
                        if attempt == 1:
                            time.sleep(0.3)
                            continue
                        self.log(f"Could not save {os.path.basename(path)}: {e}")
                        self.save_error = f"{os.path.basename(path)}: {e}"

    def setup_logging(self):
        self.logger = logging.getLogger(APP_ID)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.close_logging()
        try:
            mb = max(1, int(self.settings.get("log_max_mb", 1)))
            h = RotatingFileHandler(LOG_PATH, maxBytes=mb * 1024 * 1024, backupCount=2,
                                    encoding="utf-8", delay=True)
            h.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%Y-%m-%d %H:%M:%S"))
            self.logger.addHandler(h)
        except Exception:
            self.logger.addHandler(logging.NullHandler())

    def close_logging(self):
        for h in list(self.logger.handlers):
            try:
                h.close()
            except Exception:
                pass
            self.logger.removeHandler(h)

    def record_test(self, job_name, test, result, level="ok"):
        """Add a line to the Tests history. level: ok / warn / bad / info."""
        entry = dict(t=time.time(), job=job_name, test=test, result=result, level=level)
        with self.lock:
            self.test_history.insert(0, entry)
            del self.test_history[MAX_TEST_HISTORY:]
            self.tests_dirty = True
            if not self.uninstalled:
                try:
                    write_json(TESTS_PATH, self.test_history)
                except Exception:
                    pass

    def log(self, msg, level="info"):
        """level: "detail" (only with Preferences → Log level: Detailed), "info" (Normal and
        Detailed; with Quiet only if it's a click or a problem) or "important" (always)."""
        settings = getattr(self, "settings", None) or {}
        if not log_wanted(settings.get("log_level", "normal"), level, msg):
            return
        msg = redact(msg, [settings.get(k) for k in SECRET_KEYS])
        self.logq.put(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}")
        try:
            self.logger.info(msg)
        except Exception:
            pass

    def notify(self, msg, kind="info"):
        if self.tray and self.settings.get("notifications"):
            try:
                self.tray.notify(msg, APP_NAME)
            except Exception:
                pass
        s = self.settings
        if s.get("alerts_on") and (s.get("alert_events") or {}).get(kind):
            self.send_alert_async(msg)

    def send_alert_async(self, msg, report=None):
        """Send a phone alert in the background (network calls never block the app)."""
        settings = dict(self.settings)

        def run():
            res = send_alert(settings, msg)
            for svc, ok, info in res:
                if not ok:
                    self.log(f"Alert via {svc} failed: {info}")
            if report:
                report(res)
        threading.Thread(target=run, daemon=True).start()

    def history(self, job_name, kind, result, x="", y="", how="", detail=""):
        if self.settings.get("history_on", True):
            append_history(job=job_name, kind=kind, result=result, x=x, y=y, how=how,
                           detail=detail)

    def count_click(self, job):
        """Count a successful click towards the job's limit; finish the job when reached."""
        job["run_clicks"] = int(job.get("run_clicks") or 0) + 1
        if job.get("limit_clicks_on") and job["run_clicks"] >= int(job.get("limit_clicks", 1)):
            self.finish_job(job, f"made {job['run_clicks']} clicks")

    def finish_job(self, job, why):
        self.stop_job(job)
        job["last_result"] = f"Finished {stamp()} ({why})"
        m = f"[{job['name']}] FINISHED - {why}. The job is now stopped."
        self.log(m)
        self.notify(f"{job['name']} finished: {why}", "finished")

    def find_job(self, job):
        return any(j is job for j in self.jobs)

    # ------------------------------------------------------------ runs, queue, safety (4.5)
    def ensure_runtime(self):
        """Create the run-time helpers if they don't exist yet (also used by the tests,
        which build the App without its window)."""
        if getattr(self, "_rt_ready", False):
            return
        self._rt_ready = True
        if not hasattr(self, "groups"):
            self.groups = []
        self.aq = ActionQueue()
        self.workers = [self.aq.worker]
        self.run_cancel = threading.Event()
        self.run_info = None                  # what's running now (for the status bar)
        self.run_stack = []
        self.video_hide_until = 0.0
        self.recorder = None
        self.rec_window = None
        self.last_video = None

    def start_input_thread(self):
        self.ensure_runtime()
        self.aq.active = True
        threading.Thread(target=self.input_loop, daemon=True).start()

    def input_loop(self):
        """The only thread that clicks and types while the app runs: one action at a time."""
        while not self.stop.is_set():
            it = self.aq.take(0.5)
            if it:
                self.run_item(it)

    def run_item(self, it):
        self.aq.running = it
        if not self.run_stack:
            self.run_cancel.clear()
        self.run_stack.append(it)
        it["started"] = time.time()
        try:
            job, kind = it["job"], it["kind"]
            if it["fn"]:
                it["result"] = it["fn"]()
            elif kind == "wtest":
                self.watch_test(job)
            elif kind == "watchclick":
                self.watch_click(job)
            else:
                self.execute(job, kind)
        except Exception as e:
            self.log(f"[{it['label']}] error: {e}")
        finally:
            HELD.release_all()
            self.run_stack.pop()
            self.aq.running = self.run_stack[-1] if self.run_stack else None
            if not self.run_stack:
                self.run_info = None
            it["done"].set()

    def queue_or_run(self, job, kind):
        """Due work from the scheduler: into the queue (real app) or straight away (tests)."""
        aq = getattr(self, "aq", None)
        if aq is not None and aq.active:
            aq.put(job, kind)
        elif kind == "wtest":
            self.watch_test(job)
        elif kind == "watchclick":
            self.watch_click(job)
        else:
            self.execute(job, kind)

    def yield_to_others(self, job):
        """Called while a job that allows it is waiting: run one queued action from another
        job in between (never while keys or buttons are held)."""
        aq = getattr(self, "aq", None)
        if aq is None or len(self.run_stack) > 1 or HELD.holding():
            return
        it = aq.take(0, exclude_job=job.get("id"))
        if it:
            self.log(f"[{job.get('name')}] lets “{it['label']}” go first while it waits")
            self.run_item(it)

    def run_progress(self, run, i, st):
        w, d = describe_step(st, private=True, groups=getattr(self, "groups", []))
        self.run_info = {"job": run.job.get("name", ""), "step": run.num(i),
                         "total": len(run.job.get("steps") or []), "what": f"{w}: {d}",
                         "since": getattr(run, "t0", time.time()), "mode": run.mode}

    def stop_current_run(self, why="stopped by you"):
        """End the running job at the next safe point (between steps, or during a wait)."""
        self.ensure_runtime()
        self.run_cancel.set()
        HELD.release_all()
        self.log(f"Stop requested: the running job ends ({why})")

    def emergency_stop(self):
        """Hotkey / tray: stop the running job, drop queued clicks, let go of held keys and
        buttons, stop recording, and pause everything."""
        self.ensure_runtime()
        self.run_cancel.set()
        n = self.aq.clear()
        HELD.release_all()
        if self.recorder is not None:
            try:
                self.recorder.cancel()
            except Exception:
                pass
            self.recorder = None
            if self.rec_window is not None:
                self.cmdq.put(lambda: self.rec_window.destroy() if self.rec_window else None)
        with self.lock:
            self.settings["paused"] = True
            for j in self.jobs:
                j["pending_click_at"] = None if is_watch(j) else j.get("pending_click_at")
        self.save()
        self.log(f"EMERGENCY STOP: running job stopped, {n} queued action(s) dropped, all held "
                 f"keys/buttons released, everything paused. Resume all to continue.")
        self.notify("Emergency stop: everything is paused.", "problem")

    def queue_status(self):
        """(running text, [waiting labels]) for the status line."""
        aq = getattr(self, "aq", None)
        if aq is None:
            return "", []
        info, running = self.run_info, aq.running
        txt = ""
        if running:
            txt = f"Running “{running['label']}”"
            if info and info.get("job") == running["label"]:
                txt += f" · step {info['step']}"
                if info.get("total"):
                    txt += f" of {info['total']}"
            txt += f" · {fmt_dur(time.time() - running.get('started', time.time()))}"
        return txt, [it["label"] for it in aq.waiting()]

    def log_retry(self, job, wkey, msg, when, test=False):
        """Log every try of a click that has to wait (4.5.6): the first one with the target and
        what to do; the following ones short. Waiting for an idle mouse is logged at most
        every 30 s."""
        name = job["name"]
        rc = self.__dict__.setdefault("retry_counts", {})
        tries = rc.get(wkey, 0) + 1 if self.wait_msgs.get(wkey) else 1
        rc[wkey] = tries
        what = "test click" if test else "click"
        if tries == 1 or self.wait_msgs.get(wkey) != msg:
            hint = issue_hint(msg)
            self.log(f"[{name}] {what} WAITING - {msg}. Target: {target_text(job)}; {when}."
                     + (f" What to do: {hint}" if hint else ""))
            rc[wkey] = 1
            return
        if "using the mouse" in msg and tries % 6:
            return
        self.log(f"[{name}] {what} still waiting (try {tries}) - {msg}; {when}")

    def note_waiting(self):
        """Log once when a queued action has waited a while for another job."""
        aq = getattr(self, "aq", None)
        if aq is None or not aq.running:
            return
        for it in aq.waiting():
            if not it["warned"] and time.time() - it["queued"] > 10:
                it["warned"] = True
                self.log(f"[{it['label']}] waiting its turn - “{aq.running['label']}” is "
                         f"using the mouse and keyboard")

    def begin_run(self, job):
        """Start bookkeeping for one run: run id, history row, optional screen video."""
        ctx = {"run": uuid.uuid4().hex[:10], "t0": time.time(), "video": None}
        s = self.settings
        if s.get("video_on") and job.get("record_video") and HAVE_CV:
            v = RunVideo(video_folder(s), job.get("name", "job"), s.get("video_preset", "standard"),
                         s.get("video_redact") or [],
                         hidden=lambda: (s.get("video_hide_text", True)
                                         and time.time() < getattr(self, "video_hide_until", 0)))
            if v.start():
                ctx["video"] = v
                self.last_video = v
                self.cmdq.put(lambda: self.show_video_bar(job.get("name", ""), v))
                self.log(f"[{job.get('name')}] recording the screen for this run "
                         f"({os.path.basename(v.path)})")
            else:
                self.log(f"[{job.get('name')}] screen video not recorded: {v.error}. The job "
                         f"runs normally.")
        if not s.get("run_log_on", True):
            ctx["run"] = ""
        if ctx["run"]:
            v = ctx["video"]
            append_runlog({"run": ctx["run"], "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "job": job.get("name", ""), "elapsed": 0, "video_pos": 0 if v else "",
                           "step": "", "action": "Run started", "result": "",
                           "video": os.path.basename(v.path) if v else ""})
        return ctx

    def end_run(self, ctx, job, ok, msg):
        v = ctx.get("video")
        if v is not None:
            pos = v.position()
            v.stop()
            self.cmdq.put(self.hide_video_bar)
            if v.status == "stopped":
                self.log(f"[{job.get('name')}] screen video stopped early: {v.error}")
                self.notify(f"{job.get('name')}: screen video stopped ({v.error})", "problem")
            self.cmdq.put(lambda: self.prune_media())
        else:
            pos = ""
        if ctx.get("run"):
            append_runlog({"run": ctx["run"], "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                           "job": job.get("name", ""), "elapsed": round(time.time() - ctx["t0"], 1),
                           "video_pos": pos, "step": "", "action": "Run finished",
                           "result": "ok" if ok else f"failed: {msg}"[:200],
                           "video": os.path.basename(v.path) if v and v.path else ""})
        if not ok and job.get("fail_shot"):
            self.failure_screenshot(job)

    def failure_screenshot(self, job):
        """Save what the screen looked like when a run failed (local only; areas you chose to
        hide are blacked out; skipped while text was just entered)."""
        s = self.settings
        if s.get("video_hide_text", True) and time.time() < getattr(self, "video_hide_until", 0) + 2:
            self.log(f"[{job.get('name')}] no failure screenshot: text was just being entered")
            return
        if not (HAVE_PIL and screen_available()):
            return
        try:
            img, (ox, oy) = grab_screen(move_cursor=False)
            d = ImageDraw.Draw(img)
            for r in s.get("video_redact") or []:
                if _clean_rect(r):
                    x, y, w, h = r
                    d.rectangle((x - ox, y - oy, x - ox + w, y - oy + h), fill=(0, 0, 0))
            folder = data_path("diagnostics")
            os.makedirs(folder, exist_ok=True)
            p = os.path.join(folder, f"clickue_fail_{datetime.now():%Y%m%d_%H%M%S}_"
                                     f"{safe_file_part(job.get('name'))}.png")
            img.save(p)
            prune_files(folder, DIAG_FILE_RE, keep_count=max(1, int(s.get("diag_keep", 30))))
            self.log(f"[{job.get('name')}] failure screenshot saved: {p}")
        except Exception as e:
            self.log(f"[{job.get('name')}] couldn't save a failure screenshot ({e})")

    def prune_media(self):
        s = self.settings
        try:
            n = prune_files(video_folder(s), VIDEO_FILE_RE,
                            keep_days=max(1, int(s.get("video_keep_days", 14))),
                            max_bytes=max(1, int(s.get("video_max_gb", 5))) * 1024 ** 3)
            if n:
                self.log(f"Deleted {n} old screen video(s) (keep {s.get('video_keep_days')} days / "
                         f"{s.get('video_max_gb')} GB)")
        except Exception:
            pass

    def run_workflow(self, job, mode="run", debugger=None, ctx=None):
        """Run a job's steps (no main click). Returns (ok, message, run)."""
        self.ensure_runtime()
        run = WorkflowRun(self, job, mode=mode, debugger=debugger, ctx=ctx,
                          groups=self.groups)
        ok, msg = run.run()
        return ok, msg, run

    def dry_run_steps(self, job):
        """Walk through a job's steps without clicking or typing: targets found? conditions
        true? Returns a list of report lines."""
        self.ensure_runtime()
        lines = []
        if job.get("main_click", True):
            if is_watch(job) and job.get("watch_trigger") == "appears" and job.get("watch_click_picture"):
                lines.append(("0", "Click", "clicks the watched picture itself when it appears"))
            else:
                ok, x, y, msg, how = adapter_for(job).locate(job, activate=False, check_cover=False)
                lines.append(("0", "Click", f"would click at ({x}, {y}) - found {how}" if ok
                              else f"target NOT found: {msg}"))
        ok, msg, run = self.run_workflow(job, mode="dry")
        lines += run.report
        if not ok:
            lines.append(("!", "Problem", msg))
        return lines

    # ------------------------------------------------------------ scheduling
    def schedule_first(self, job, now=None):
        now = now or time.time()
        first = None
        if job.get("first_time"):
            try:
                first = parse_hms_clock(job["first_time"])
            except Exception:
                first = None
        job["base_next"] = first if first else now + job["interval_s"]
        self._set_next_from_base(job)

    def schedule_after_run(self, job, now):
        if job.get("anchored", True) and job.get("base_next"):
            base = job["base_next"] + job["interval_s"]
            while base <= now:          # skip slots that have already passed
                base += job["interval_s"]
            job["base_next"] = base
        else:
            job["base_next"] = now + job["interval_s"]
        self._set_next_from_base(job)

    def _set_next_from_base(self, job):
        if job.get("random_on", True):
            lo, hi = int(job["delay_min_s"]), int(job["delay_max_s"])
            delay = random.randint(min(lo, hi), max(lo, hi))
            extra = f" + random {fmt_dur(delay)}"
        else:
            delay, extra = 0, " (no random delay)"
        job["next_run"] = job["base_next"] + delay
        job["planned_run"] = job["next_run"]       # 4.6: for the "due … clicked …" log
        job["deadline"] = None
        self.wait_msgs.pop((job["id"], "scheduled"), None)
        self.log(f"[{job['name']}] scheduled {fmt_time(job['base_next'])}{extra}"
                 f" -> clicks at {fmt_time(job['next_run'])}"
                 f" (in {fmt_dur(job['next_run'] - time.time())})")

    def scheduler_loop(self):
        while not self.stop.is_set():
            try:
                now = time.time()
                due = []
                with self.lock:
                    paused = self.settings.get("paused")
                    for j in self.jobs:
                        if j.get("test_at") and j["test_at"] <= now:
                            due.append((j, "test"))
                        if j.get("wtest_at") and j["wtest_at"] <= now:
                            due.append((j, "wtest"))
                        if j.get("enabled") and j.get("limit_until_on") and j.get("limit_until"):
                            try:
                                until = datetime.strptime(j["limit_until"], "%Y-%m-%d %H:%M")
                                if now >= until.timestamp():
                                    self.finish_job(j, f"reached its end time "
                                                       f"({j['limit_until']})")
                                    self.save()
                                    continue
                            except ValueError:
                                pass
                        if is_watch(j):
                            if paused or not j.get("enabled") or j.get("paused"):
                                continue
                            if not in_active_hours(j, now):
                                if j.get("watch_note") != "outside active hours":
                                    j["watch_state"] = "unknown"
                                    j["watch_note"] = "outside active hours"
                                    j["pending_click_at"] = j["pending_since"] = None
                                continue
                            if j.get("pending_click_at"):
                                if j["pending_click_at"] <= now:
                                    due.append((j, "watchclick"))
                                elif j.get("next_check") and j["next_check"] <= now:
                                    due.append((j, "watchcheck"))   # still wanted? (4.5.6)
                            elif j.get("next_check") is None:
                                j["next_check"] = now
                            elif j["next_check"] <= now:
                                due.append((j, "watchcheck"))
                            continue
                        if (not paused and j.get("enabled") and not j.get("paused")
                                and j.get("next_run")
                                and j["next_run"] <= now):
                            due.append((j, "scheduled"))
                for j, kind in due:
                    if self.stop.is_set():
                        break
                    if kind == "watchcheck":
                        self.watch_check(j)          # only looks: never waits for the mouse
                    else:
                        self.queue_or_run(j, kind)
                self.note_waiting()
            except Exception as e:
                self.log(f"Scheduler error: {e}")
            self.stop.wait(1.0)

    # ------------------------------------------------------------ screen watchers
    def start_job(self, job):
        """Begin running a job (schedule for clicks, first check for watchers)."""
        job["enabled"] = True
        job["paused"] = False
        job["run_clicks"] = 0
        if is_watch(job):
            job.update(next_check=time.time() + 1, miss_count=0, armed=True,
                       pending_click_at=None, pending_since=None, watch_state="",
                       watch_note="", next_run=None)
            self.wait_msgs.pop((job["id"], "watch"), None)
            self.log(f"[{job['name']}] watching for its picture every "
                     f"{fmt_dur(job['watch_interval_s'])}")
        else:
            self.schedule_first(job)

    def stop_job(self, job):
        job["enabled"] = False
        job["paused"] = False
        job["next_run"] = job["base_next"] = job["deadline"] = None
        job.update(next_check=None, pending_click_at=None, pending_since=None, miss_count=0,
                   watch_state="", watch_note="")
        self.wait_msgs.pop((job["id"], "watch"), None)

    def watch_issue(self, job, note, now, cancel_click=False):
        """A check that couldn't tell whether the picture is there (4.5.6): the job shows it
        as a problem, and every such check is logged - the first one with what to do.
        cancel_click (4.6): a click waiting for its random delay is cancelled (the window it
        would click in is gone or minimized)."""
        with self.lock:
            name = job["name"]
            if cancel_click and job.get("pending_click_at"):
                job["pending_click_at"] = job["pending_since"] = None
                job["armed"] = True
                job["miss_count"] = 0
                job["last_result"] = f"Click cancelled - {note}"
                self.log(f"[{name}] click CANCELLED - {note}; nothing clicked")
            n = int(job.get("issue_count") or 0) + 1
            job.update(watch_state="unknown", watch_note=note, issue_count=n)
            job["issue_since"] = job.get("issue_since") or now
        if n == 1:
            hint = issue_hint(note)
            self.log(f"[{name}] CAN'T WATCH: {note}." + (f" What to do: {hint}" if hint else "")
                     + " (The picture isn't counted as gone meanwhile.)")
        else:
            since = fmt_dur(now - (job.get("issue_since") or now))
            self.log(f"[{name}] check {n}: still can't watch - {note} (for {since})")

    def watch_ok_again(self, job):
        """After checks that couldn't tell, note that the watcher can see again."""
        if job.get("issue_count"):
            self.log(f"[{job['name']}] watching again - the problem is gone "
                     f"({job.get('watch_note') or 'checks work'})")
        job["issue_count"] = 0
        job["issue_since"] = None

    def own_covers(self, job):
        """4.6.1: is a Clickue window in front of where this watcher's picture is? Only a
        window that is really on top counts: Clickue open (even maximized) behind the
        browser doesn't. Looks where the picture was last seen, else the middle of its
        search area; with neither, only when Clickue is the window in front."""
        if not self.own_visible:
            return False
        if not IS_WIN:
            return True
        pts = []
        xy = job.get("found_xy")
        if xy:
            pts.append(tuple(xy))
        r = job.get("_search_rect") or job_area(job)
        if r:
            pts.append((r[0] + r[2] / 2, r[1] + r[3] / 2))
        if pts:
            return any(own_on_top(x, y) for x, y in pts)
        try:
            fg = user32.GetForegroundWindow()
            return bool(fg) and is_own_window(fg)
        except Exception:
            return True

    def watch_check(self, job):
        """Look for the watched picture once and decide whether to click (or, while a click
        is waiting for its random delay, whether it's still wanted)."""
        now = time.time()
        with self.lock:
            if not self.find_job(job) or not job.get("enabled"):
                return
            name, png = job["name"], job.get("watch_png")
            interval = max(1, int(job.get("watch_interval_s", 30)))
            job["next_check"] = now + interval
            job["last_check"] = now
            pending = bool(job.get("pending_click_at"))
        if not png:
            return self.watch_issue(job, "no picture saved", now)
        if not HAVE_CV:
            return self.watch_issue(job, "picture matching not installed", now)
        if not screen_available():
            return self.watch_issue(job, "screen locked or remote session disconnected", now)
        # the screen changed size or scaling (e.g. a remote session handed to the console):
        # give it a few seconds to settle before counting checks (4.5.6)
        sig = list(virtual_screen()) + [system_dpi()]
        with self.lock:
            prev = job.get("screen_sig")
            job["screen_sig"] = sig
            if prev and prev != sig:
                job["settle_until"] = now + SCREEN_SETTLE_S
                job["miss_count"] = 0
            settle = (job.get("settle_until") or 0) > now
        if settle:
            # 4.6.1: it still looks right away; only a change (a reason to click) waits
            with self.lock:
                job["next_check"] = min(job["next_check"], now + min(interval, 5))
            if prev and prev != sig:
                self.log(f"[{name}] the screen changed from {prev[2]}×{prev[3]} "
                         f"({prev[4] * 100 // 96}% scaling) to {sig[2]}×{sig[3]} "
                         f"({sig[4] * 100 // 96}%) - a missing picture isn't counted for "
                         f"{SCREEN_SETTLE_S} s")
        with self.lock:
            snap = dict(job)
        # 4.6: a watcher that clicks inside a window also watches that window
        wstate, wrect, wtitle = watch_window(snap)
        wt_ = short_title(wtitle, 40)
        if wstate == "missing":
            return self.watch_issue(job, f"its window \u201c{wt_}\u201d isn't open (no window "
                                         f"with that title - if the page or tab changed, so "
                                         f"did its title)", now, cancel_click=True)
        if wstate == "minimized":
            return self.watch_issue(job, f"its window \u201c{wt_}\u201d is minimized", now,
                                    cancel_click=True)
        if wstate == "ok":
            area = job_area(snap)
            search = rect_intersection(area, wrect) if area else wrect
            if not search:
                return self.watch_issue(job, f"its search area is outside its window "
                                             f"\u201c{wt_}\u201d (the window moved or the area "
                                             f"was drawn on another screen)", now)
            snap["_search_rect"] = search
        snap["_exclude"] = list(getattr(self, "own_rects", []) or [])
        try:
            (found, x, y, score, sc), wnote, pointer = watched_picture(
                snap, move_ok=self.may_move_pointer())
        except Exception as e:
            return self.watch_issue(job, f"couldn't look at the screen ({e})", now)
        appears = snap.get("watch_trigger") == "appears"
        if settle:
            if found == appears:              # a change right after the screen changed
                return self.watch_issue(job, "the screen size or scaling just changed", now)
            with self.lock:
                job["settle_until"] = None    # no change: it's settled, back to normal
        if not found and wstate == "ok" and not appears:
            cover = window_covering(snap, snap.get("found_xy"))
            if cover:
                return self.watch_issue(job, f"its window \u201c{wt_}\u201d is covered by "
                                             f"\u201c{short_title(cover, 30)}\u201d where the "
                                             f"picture was", now)
        if not found and not appears and self.own_covers(snap):
            # This app's own window is in front of the picture - don't count it
            return self.watch_issue(job, "Clickue window in front of the picture", now)
        if not found and pointer and not appears:
            # Hovering can change how the picture looks - don't count it (4.5.3)
            return self.watch_issue(job, "the mouse pointer is resting on the picture", now)
        part = watch_partial(snap)
        how = (f"{score:.0%} of it matches" if part else f"{score:.0%}") + (
            "" if not sc or abs(sc - 1) < 0.01 else f" at {sc:.0%} size")
        where = f"at ({x}, {y})"
        area_note = watch_area_note(snap) if not found else ""

        with self.lock:
            if not self.find_job(job) or not job.get("enabled"):
                return
            self.watch_ok_again(job)
            job["pointer_logged"] = False
            if found:
                job.update(last_seen=now, watch_scale=sc, found_xy=[x, y])
            hit = found if appears else not found
            seen_txt = (f"picture seen {where}, {how}" if found
                        else f"picture not on screen (best {how}, closest place {where})"
                        + (f"; {area_note}" if area_note else ""))
            if not hit:
                if pending:
                    # it changed back during the random delay: the click isn't wanted any more
                    job["pending_click_at"] = job["pending_since"] = None
                    job["armed"] = True
                    job["last_result"] = ("Click cancelled - picture went away again" if appears
                                          else "Click cancelled - picture came back")
                    self.log(f"[{name}] click CANCELLED - {seen_txt} before the click was due")
                # the condition isn't met: reset, and allow the next click
                prev_state = job.get("watch_state")
                if found and prev_state == "missing":
                    self.log(f"[{name}] picture is back - {seen_txt}")
                elif not found and prev_state == "seen" and appears:
                    self.log(f"[{name}] picture went away - {seen_txt}")
                else:
                    self.log(f"[{name}] check: {seen_txt}", "detail")
                job.update(miss_count=0, armed=True, once_logged=False,
                           watch_state="seen" if found else "missing",
                           watch_note=(f"seen {score:.0%}" if found
                                       else f"not showing (best {score:.0%})"))
                return
            if pending:
                # still the same during the random delay: keep waiting for the click
                job["watch_state"] = "seen" if found else "missing"
                self.log(f"[{name}] check during the click delay: {seen_txt} - still clicking "
                         f"in {fmt_dur(job['pending_click_at'] - now)}", "detail")
                return
            job["miss_count"] = int(job.get("miss_count", 0)) + 1
            if job["miss_count"] == 1:
                job["first_miss_at"] = now
            job["watch_state"] = "seen" if found else "missing"
            need = max(1, int(job.get("watch_confirm", 2)))
            what = "showing" if appears else "missing"
            job["watch_note"] = (f"{what} ({job['miss_count']} of {need} checks)"
                                 if job["miss_count"] < need else what)
            self.log(f"[{name}] {'picture appeared' if appears else 'picture NOT found'} "
                     f"(check {job['miss_count']} of {need}) - {seen_txt}"
                     + (" - confirming" if job["miss_count"] < need else ""))
            if job["miss_count"] < need:
                job["next_check"] = now + min(interval, 5)   # confirm quickly
                return
            if not job.get("armed", True) and job.get("watch_once", True):
                back = "go away" if appears else "come back"
                job["watch_note"] = f"{what} · already clicked, waiting for it to {back}"
                if not job.get("once_logged"):
                    job["once_logged"] = True
                    job["last_result"] = ("Still showing - waiting for it to go away" if appears
                                          else "Still gone - waiting for it to come back")
                    opt = ("Click only once each time it appears" if appears
                           else "Click only once each time it disappears")
                    self.log(f"[{name}] picture still {'showing' if appears else 'gone'} - not "
                             f"clicking again because \u201c{opt}\u201d is on. It will click "
                             f"again after the picture {'goes away and appears' if appears else 'comes back and disappears'} "
                             f"again (untick that option in Edit to keep clicking).")
                return
            lo, hi = int(job.get("watch_delay_min_s", 1)), int(job.get("watch_delay_max_s", 5))
            delay = (random.randint(min(lo, hi), max(lo, hi))
                     if job.get("watch_random_on", True) else 0)
            job["pending_click_at"] = now + delay
            job["click_planned_at"] = now + delay
            job["pending_since"] = now
            job["armed"] = False
            # keep looking during the delay, so a picture that comes back cancels the click
            job["next_check"] = now + min(interval, max(5, delay // 4 or 5))
            first = job.get("first_miss_at") or now
            self.log(f"[{name}] picture {'APPEARED' if appears else 'GONE'} - first seen "
                     f"{clock(first)}, confirmed {clock(now)} - click scheduled for "
                     f"{clock(now + delay)} ("
                     + (f"random delay {fmt_dur(delay)}; checks continue, and the click is "
                        f"cancelled if the picture {'goes away' if appears else 'comes back'})"
                        if delay else "no delay)"))
            self.save()

    def may_move_pointer(self):
        """May a scheduled watcher check move the mouse pointer aside for a moment? Only when
        nobody has used the computer for a while and nothing is clicking or holding input."""
        try:
            if idle_seconds() < POINTER_IDLE_S:
                return False
            aq = getattr(self, "aq", None)
            if aq is not None and aq.running is not None:
                return False
            return not HELD.busy()
        except Exception:
            return False

    def watcher_dry_run(self, job, report=None):
        """Look for the watched picture and the button, without clicking.
        Returns dict(picture=(found, x, y, score, scale) or None, button=(ok, x, y, msg, how),
        error=str)."""
        out = dict(picture=None, button=None, error="", note="", partial=watch_partial(job),
                   appears=job.get("watch_trigger") == "appears")
        if not job.get("watch_png"):
            out["error"] = "no picture saved"
            return out
        if not HAVE_CV:
            out["error"] = "picture matching not installed"
            return out
        if not screen_available():
            out["error"] = "screen locked or session disconnected"
            return out
        job, problem = watch_scope(job)
        if problem:
            out["error"] = problem + " - the picture wasn't looked for and nothing would be clicked"
            return out
        try:
            out["picture"], out["note"], _ = watched_picture(job, report=report, move_ok=True)
            if not job.get("main_click", True):
                out["button"] = (True, 0, 0, "", "steps only")
            elif job.get("watch_trigger") == "appears" and job.get("watch_click_picture"):
                f, px, py = out["picture"][:3]
                out["button"] = (f, px, py, "" if f else "the picture isn't showing",
                                 "the picture itself")
            else:
                out["button"] = locate_spot(job, activate=False, check_cover=False)
        except Exception as e:
            out["error"] = f"couldn't look ({e})"
        out["appears"] = job.get("watch_trigger") == "appears"
        return out

    @staticmethod
    def describe_dry_run(r, clicked=None):
        """(text, level) summary of a watcher dry run."""
        if r["error"]:
            return f"Couldn't test: {r['error']}", "bad"
        found, px, py, score, sc = r["picture"]
        bok, bx, by, bmsg, bhow = r["button"]
        appears = r.get("appears")
        would = found if appears else not found
        size = "" if not sc or abs(sc - 1) < 0.01 else f" at {sc:.0%} size"
        at = f" at ({px}, {py})" if (px or py) else ""
        if r.get("partial"):
            need = f"{r['partial']:.0%} needed"
            pic = (f"Picture found{at} ({score:.0%} of it matches, {need}{size})" if found
                   else f"Picture NOT on screen (best: {score:.0%} of it matches, {need}"
                        + (f", closest place{at}" if at else "") + ")")
        else:
            pic = (f"Picture found{at} ({score:.0%}{size})" if found
                   else f"Picture NOT on screen (best {score:.0%}"
                        + (f", closest place{at}" if at else "") + ")")
        if r.get("note"):
            pic += f" ({r['note']})"
        btn = ("no click of its own, runs its steps" if bhow == "steps only" else
               f"button found at ({bx}, {by}) by {bhow}" if bok
               else f"button NOT found: {bmsg}")
        if clicked is not None:
            act = "clicked the button" if clicked[0] else f"click failed: {clicked[1]}"
        else:
            act = ("WOULD click now" if bok else "would try to click, but can't find the button") \
                if would else "would NOT click"
        level = ("ok" if bok else "bad") if not would else ("warn" if bok else "bad")
        if not appears and found and bok:
            level = "ok"
        if clicked is not None:
            level = "ok" if clicked[0] else "bad"
        return f"{pic} · {btn} · {act}", level

    def watch_test(self, job):
        """Scheduled watcher test (runs in the background, e.g. while disconnected)."""
        retry_s = int(self.settings["retry_minutes"]) * 60
        now = time.time()
        with self.lock:
            if not self.find_job(job) or not job.get("wtest_at"):
                return
            if job.get("wtest_deadline") is None:
                job["wtest_deadline"] = job["wtest_at"] + retry_s
            snap, name = dict(job), job["name"]
        if not screen_available():
            with self.lock:
                if now > job["wtest_deadline"]:
                    job["wtest_at"] = job["wtest_deadline"] = None
                    job["last_result"] = "Watch test FAILED " + stamp()
                    self.log(f"[{name}] WATCH TEST FAILED - screen stayed locked/disconnected")
                    self.notify(f"{name}: watcher test failed (screen locked)", "test")
                    self.record_test(name, "Scheduled watcher test",
                                     "Failed: screen stayed locked or disconnected", "bad")
                    self.save()
                else:
                    job["wtest_at"] = now + 30
                    job["last_result"] = "Watch test: waiting for screen"
            return
        r = self.watcher_dry_run(snap)
        clicked = None
        if not r["error"]:
            would = r["picture"][0] if r.get("appears") else not r["picture"][0]
            if snap.get("wtest_click") and would and r["button"][0]:
                pt = r["button"][1:3] if r["button"][4] == "the picture itself" else None
                ok, msg, _, x, y, how = self.perform(snap, check_idle=False, point=pt)
                clicked = (ok, msg)
        text, level = self.describe_dry_run(r, clicked)
        if (not r["error"] and not r["picture"][0] and self.own_covers(snap)
                and not r.get("appears")):
            text += " (note: the Clickue window was open and may have covered it)"
            level = "warn" if level == "ok" else level
        with self.lock:
            if not self.find_job(job):
                return
            job["wtest_at"] = job["wtest_deadline"] = None
            job["last_result"] = ("Watch test OK " if level == "ok" else "Watch test: see Tests ") \
                + stamp()
            self.log(f"[{name}] WATCH TEST: {text}")
            self.notify(f"{name} watcher test: {text}", "test")
            self.record_test(name, "Scheduled watcher test", text, level)
            self.save()

    def watch_click(self, job):
        """Do the click a watcher decided on (retries like a scheduled click)."""
        retry_s = int(self.settings["retry_minutes"]) * 60
        with self.lock:
            if not self.find_job(job) or not job.get("enabled"):
                return
            snap, name = dict(job), job["name"]
        appears = snap.get("watch_trigger") == "appears"
        point = None
        if appears and snap.get("watch_click_picture"):
            try:
                f, px, py, score, sc = watched_picture(snap)[0]
            except Exception:
                f = False
            if not f:
                with self.lock:
                    job["pending_click_at"] = job["pending_since"] = None
                    job["armed"] = True
                    job["miss_count"] = 0
                    job["last_result"] = "Picture went away before the click"
                self.log(f"[{name}] picture went away before the click - nothing clicked")
                return
            point = (px, py)
        elif snap.get("watch_png") and HAVE_CV and screen_available():
            # look once more right before clicking: still gone (or still showing)? (4.5.6)
            wstate, wrect, wtitle = watch_window(snap)
            if wstate in ("missing", "minimized"):
                why = (f"its window \u201c{short_title(wtitle, 40)}\u201d "
                       + ("isn't open" if wstate == "missing" else "is minimized"))
                with self.lock:
                    job["pending_click_at"] = job["pending_since"] = None
                    job["armed"] = True
                    job["miss_count"] = 0
                    job["last_result"] = f"Click cancelled - {why}"
                self.log(f"[{name}] click CANCELLED - {why} right before the click was due; "
                         f"nothing clicked")
                return
            if wstate == "ok":
                area = job_area(snap)
                snap["_search_rect"] = rect_intersection(area, wrect) if area else wrect
            snap["_exclude"] = list(getattr(self, "own_rects", []) or [])
            try:
                (f, px, py, score, sc), _, _ = watched_picture(snap)
            except Exception:
                f = not appears
            if f != appears:
                with self.lock:
                    job["pending_click_at"] = job["pending_since"] = None
                    job["armed"] = True
                    job["miss_count"] = 0
                    job["last_result"] = ("Click cancelled - picture went away again" if appears
                                          else "Click cancelled - picture came back")
                self.log(f"[{name}] click CANCELLED - "
                         + (f"the picture is back at ({px}, {py}), {score:.0%}," if f else
                            "the picture went away")
                         + " right before the click was due - nothing clicked")
                return
        ok, msg, retry_in, x, y, how = self.perform(snap, check_idle=True, point=point)
        now = time.time()
        wkey = (job["id"], "watch")
        with self.lock:
            if not self.find_job(job):
                return
            if ok:
                self.wait_msgs.pop(wkey, None)
                job["count"] = int(job.get("count", 0)) + 1
                self.bump_stats("stats_clicks", watch=True)
                job["last_run"] = now
                planned = job.get("click_planned_at")
                first = job.get("first_miss_at")
                timing = (f"{'appeared' if appears else 'gone'} {clock(first)}" if first else "") \
                    + (f", click scheduled for {clock(planned)}" if planned else "") \
                    + f", clicked {clock(now)}"
                job["last_result"] = "Clicked " + stamp() + f" ({timing.lstrip(', ')})"
                job["pending_click_at"] = job["pending_since"] = None
                # already confirmed gone: if it's still gone after the wait, click again
                # straight away instead of re-confirming from scratch
                wait_s = (job.get("watch_cooldown_s", 30) if job.get("watch_cooldown_on", True)
                          else job.get("watch_interval_s", 30))
                job["next_check"] = now + max(1, int(wait_s))
                via = f" ({how})" if how else ""
                m = (f"[{name}] picture {'appeared' if appears else 'was gone'} - "
                     f"{job['button']} click at ({x}, {y}){via} - OK · {timing.lstrip(', ')}")
                job["first_miss_at"] = job["click_planned_at"] = None
                self.log(m)
                self.notify(f"{name}: picture {'appeared' if appears else 'was gone'}, clicked.",
                            "watch")
                self.history(name, "watcher", "ok", x, y, how, "appeared" if appears else "gone")
                self.count_click(job)
            elif now - (job.get("pending_since") or now) > retry_s:
                self.wait_msgs.pop(wkey, None)
                job["pending_click_at"] = job["pending_since"] = None
                job["armed"] = True          # allow another try on the next check
                job["next_check"] = now + max(1, int(job.get("watch_interval_s", 30)))
                job["last_result"] = "Click FAILED " + stamp()
                self.bump_stats("stats_missed", watch=True)
                m = f"[{name}] couldn't click within {retry_s // 60} min ({msg})."
                self.log(m)
                self.notify(m, "problem")
                self.history(name, "watcher", "failed", detail=msg)
            else:
                job["pending_click_at"] = now + retry_in
                job["last_result"] = "Click waiting: " + msg
                self.log_retry(job, wkey, msg, f"retrying in {fmt_dur(retry_in)}, giving up "
                               f"after {retry_s // 60} min")
                self.wait_msgs[wkey] = msg
            self.save()

    def perform(self, job, check_idle, point=None, debugger=None):
        """Click the job's spot (or `point`), then run its extra steps.
        Returns (ok, message, seconds-until-retry, x, y, how-it-was-found)."""
        if not screen_available():
            return False, "screen locked or session disconnected", 30, 0, 0, ""
        need = int(self.settings.get("idle_seconds", 0) or 0)
        if check_idle and need > 0 and idle_seconds() < need:
            return False, "you were using the mouse/keyboard", 5, 0, 0, ""
        main = job.get("main_click", True)
        if not main:
            x, y, how = 0, 0, "steps only"
        elif point:
            x, y, how = int(point[0]), int(point[1]), "the picture itself"
        else:
            ok, x, y, msg, how = locate_spot(job, activate=True)
            if not ok:
                return False, msg, 30, x, y, how
        self.ensure_runtime()
        ctx = self.begin_run(job)
        ok, msg, steps_ok = False, "", True
        try:
            if main:
                if debugger:
                    debugger.before_main(job, x, y, how)
                ok, msg = do_click(x, y, job["button"], job["clicks"],
                                   self.settings["restore_cursor"],
                                   human=mouse_style(self.settings, job))
                if ctx.get("run"):
                    append_runlog({"run": ctx["run"], "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   "job": job.get("name", ""),
                                   "elapsed": round(time.time() - ctx["t0"], 1),
                                   "video_pos": ctx["video"].position() if ctx.get("video") else "",
                                   "step": "0", "action": f"Click: {job['button']} at ({x}, {y}), {how}",
                                   "result": "ok" if ok else f"failed: {msg}"})
            else:
                ok, msg = True, ""
            if ok and job.get("steps"):
                sok, smsg = self.run_steps(job, debugger=debugger, ctx=ctx)
                msg, steps_ok = smsg, sok
                if not sok:
                    self.log(f"[{job['name']}] extra steps stopped: {smsg}")
                    self.notify(f"{job['name']}: extra steps stopped ({smsg})", "problem")
                    if not main:
                        ok = False
            elif ok and not main:
                msg = "nothing to do (no steps)"
        finally:
            self.end_run(ctx, job, ok and steps_ok, msg)
        return ok, msg, 30, x, y, how

    def run_steps(self, job, debugger=None, ctx=None):
        """Run a job's extra steps in order. Returns (ok, message)."""
        steps = job.get("steps") or []
        ok, msg, run = self.run_workflow(job, mode="debug" if debugger else "run",
                                         debugger=debugger, ctx=ctx)
        if not ok:
            return False, msg
        if not job.get("main_click", True):
            return True, f"ran {len(steps)} step{'s' if len(steps) != 1 else ''}"
        return True, f"clicked + {len(steps)} extra step{'s' if len(steps) != 1 else ''}"

    def wait_for_picture(self, st, tick=None, job=None):
        """A chain step: wait until a picture appears (optionally click it) or disappears.
        Returns (ok, message); a message starting with "timeout" means it didn't happen in time.
        tick() is called while waiting (stop checks; may raise StopRun)."""
        if not HAVE_CV:
            return False, "picture matching isn't installed"
        if not st.get("png"):
            return False, "no picture saved for this step"
        appear = st.get("until", "appears") == "appears"
        limit = max(1, min(STEP_MAX_WAIT_S, int(st.get("timeout", 60))))
        end = time.time() + limit
        hint = None
        while not self.stop.is_set():
            if screen_available():
                try:
                    found, x, y, score, sc = picture_on_screen(st["png"], hint, area=st.get("area"))
                except Exception as e:
                    return False, f"couldn't look at the screen ({e})"
                if found:
                    hint = sc
                if found == appear:
                    if appear and st.get("click_it"):
                        ok, m = do_click(x, y, st.get("button", "left"), int(st.get("clicks", 1)),
                                         self.settings["restore_cursor"],
                                         human=mouse_style(self.settings, job, st))
                        if not ok:
                            return False, f"couldn't click it ({m})"
                        return True, f"appeared ({score:.0%}) and was clicked at ({x}, {y})"
                    return True, f"appeared ({score:.0%})" if appear else "went away"
            if time.time() >= end:
                return False, (f"timeout - the picture didn't {'appear' if appear else 'go away'}"
                               f" within {fmt_dur(limit)}")
            nxt = time.time() + STEP_POLL_S
            while time.time() < nxt and not self.stop.is_set():
                if tick:
                    tick()
                time.sleep(min(0.2, STEP_POLL_S))
        return False, "Clickue is closing"

    def draw_capture(self, parent, prompt, on_done, with_rect=False):
        """Freeze the screen, let the user drag a box, call on_done(picture) (PIL image), or
        on_done(picture, [x, y, w, h] on screen) with with_rect=True.
        The whole app hides meanwhile."""
        if not (HAVE_PIL and HAVE_CV) or getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def start():
            try:
                shot, (vx, vy) = grab_screen(move_cursor=True)
            except Exception as e:
                restore()
                messagebox.showerror(APP_NAME, f"Couldn't capture the screen:\n{e}",
                                     parent=parent or self.root)
                return

            def done(b):
                crop = shot.crop(b)
                restore()
                if with_rect:
                    on_done(crop, [vx + b[0], vy + b[1], b[2] - b[0], b[3] - b[1]])
                else:
                    on_done(crop)

            self._drawer = BoxDrawer(self, shot, (vx, vy), prompt, done, restore,
                                     min_size=PICTURE_MIN_PX)
        self.root.after(450, start)

    def execute(self, job, kind):
        """kind: 'scheduled', 'test' (scheduled test click) or 'manual' (Test click now)."""
        retry_min = int(self.settings["retry_minutes"])
        retry_s = retry_min * 60
        keys = {"scheduled": ("next_run", "deadline"), "test": ("test_at", "test_deadline")}
        due_key, dl_key = keys.get(kind, (None, None))
        wkey = (job["id"], kind)
        now = time.time()

        with self.lock:
            if not self.find_job(job):
                return
            name = job["name"]
            if due_key:
                if job.get(dl_key) is None:
                    job[dl_key] = job[due_key] + retry_s
                attempted = wkey in self.wait_msgs
                overdue_long = now - job[due_key] > retry_s + 60   # e.g. app was closed
                if now > job[dl_key] and (attempted or overdue_long):
                    reason = self.wait_msgs.pop(wkey, "the program wasn't running or was paused")
                    if kind == "scheduled":
                        job["last_result"] = "Missed " + stamp()
                        self.bump_stats("stats_missed")
                        msg = (f"[{name}] MISSED - couldn't click within {retry_min} min "
                               f"({reason}). Moving on to the next scheduled time.")
                        self.log(msg)
                        self.schedule_after_run(job, now)
                    else:
                        job["test_at"] = job["test_deadline"] = None
                        job["last_result"] = "Test FAILED " + stamp()
                        msg = f"[{name}] TEST FAILED - couldn't click within {retry_min} min ({reason})."
                        self.log(msg)
                        self.record_test(name, "Scheduled test click",
                                         f"Failed: couldn't click within {retry_min} min "
                                         f"({reason})", "bad")
                    self.notify(msg, "problem" if kind == "scheduled" else "test")
                    self.history(name, "scheduled" if kind == "scheduled" else "test", "missed",
                                 detail=reason)
                    self.save()
                    return
            if kind == "scheduled" and not in_active_hours(job, now):
                if job.get("hours_outside") == "skip":
                    self.log(f"[{name}] click skipped - outside its active hours "
                             f"({describe_hours(job)})")
                    job["last_result"] = "Skipped " + stamp() + " (outside active hours)"
                    self.history(name, "scheduled", "skipped", detail="outside active hours")
                    self.schedule_after_run(job, now)
                else:
                    start = next_active_start(job, now)
                    lo, hi = int(job["delay_min_s"]), int(job["delay_max_s"])
                    extra = (random.randint(min(lo, hi), max(lo, hi))
                             if job.get("random_on", True) else 0)
                    job["next_run"] = start + extra
                    job["deadline"] = None
                    job["last_result"] = "Waiting for active hours"
                    self.log(f"[{name}] outside its active hours ({describe_hours(job)}) - "
                             f"will click at {fmt_time(job['next_run'])}")
                self.save()
                return
            snap = dict(job)
            button = job["button"]

        ok, msg, retry_in, x, y, how = self.perform(snap, check_idle=(kind != "manual"))
        via = f" ({how})" if how else ""
        note = resolution_note(snap)
        if ok and note and (job["id"], screen_size()) not in self.res_warned:
            self.res_warned.add((job["id"], screen_size()))
            self.log(f"[{name}] note: {note}. Re-pick it, or switch it to \u201cInside a "
                     f"window\u201d in Edit.")

        now = time.time()
        with self.lock:
            if not self.find_job(job):
                return
            if ok:
                self.wait_msgs.pop(wkey, None)
                if kind == "scheduled":
                    job["count"] = int(job.get("count", 0)) + 1
                    self.bump_stats("stats_clicks")
                    job["last_run"] = now
                    base, due = job.get("base_next"), job.get("planned_run") or job.get("next_run")
                    timing = (f"scheduled {clock(base)}" if base else "") + (
                        f" + random {fmt_dur(due - base)} = due {clock(due)}"
                        if base and due and due - base >= 1 else "") + f", clicked {clock(now)}" \
                        + (f" ({fmt_dur(now - due)} late: it had to wait)"
                           if due and now - due >= 5 else "")
                    job["last_result"] = "OK " + stamp() + (" · " + how if "picture" in how else "") \
                        + f" (due {clock(due)})" * bool(due)
                    self.log(f"[{name}] {button} click at ({x}, {y}){via} - OK · "
                             f"{timing.lstrip(', ')}")
                    self.history(name, "scheduled", "ok", x, y, how, msg if msg != "clicked" else "")
                    self.schedule_after_run(job, now)
                    self.count_click(job)
                elif kind == "test":
                    job["test_at"] = job["test_deadline"] = None
                    job["last_result"] = "Test OK " + stamp()
                    m = f"[{name}] TEST click at ({x}, {y}){via} worked."
                    self.log(m)
                    self.notify(m, "test")
                    self.history(name, "test", "ok", x, y, how)
                    self.record_test(name, "Scheduled test click",
                                     f"Clicked at ({x}, {y}){via}", "ok")
                else:
                    job["last_result"] = "Manual OK " + stamp()
                    self.log(f"[{name}] manual test click at ({x}, {y}){via} - OK")
                    self.record_test(name, "Test click now", f"Clicked at ({x}, {y}){via}", "ok")
                    self.history(name, "manual", "ok", x, y, how)
            elif due_key:
                job[due_key] = now + retry_in
                short = ("waiting for idle" if retry_in == 5 else
                         "waiting for screen" if msg.startswith("screen locked") else
                         "waiting: picture not found" if "saved picture" in msg else
                         "waiting: " + msg)
                job["last_result"] = ("Test: " if kind == "test" else "") + short
                self.log_retry(job, wkey, msg, f"retrying until {fmt_time(job[dl_key])}",
                               test=kind == "test")
                self.wait_msgs[wkey] = msg
            else:
                job["last_result"] = "Manual failed " + stamp()
                self.log(f"[{name}] manual test click failed: {msg}")
                self.record_test(name, "Test click now", f"Failed: {msg}", "bad")
            self.save()

    # ------------------------------------------------------------ UI
    def build_ui(self):
        F = self.font_family
        main = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        main.pack(fill="both", expand=True)
        self.main = main

        # ---- header
        hdr = ttk.Frame(main)
        hdr.pack(fill="x")
        self.menu_btn = ttk.Button(hdr, text="☰  Menu", command=self.show_main_menu)
        self.menu_btn.pack(side="right", anchor="n")
        self.main_menu = tk.Menu(self.root, tearoff=0)
        self.theme_btn = ttk.Button(hdr, text="", command=self.toggle_theme)
        self.theme_btn.pack(side="right", padx=6, anchor="n")
        self.cards_btn = ttk.Button(hdr, text="", command=self.toggle_cards,
                                    style="Summary.TButton")
        self.cards_btn.pack(side="right", anchor="n")
        self.hdr = hdr
        tbox = ttk.Frame(hdr)
        tbox.pack(side="left", fill="x", expand=True)
        trow = ttk.Frame(tbox)
        trow.pack(anchor="w")
        if HAVE_PIL:
            try:
                self._hdr_logo = ImageTk.PhotoImage(make_logo(40))
                ttk.Label(trow, image=self._hdr_logo).pack(side="left", padx=(0, 10))
            except Exception:
                pass
        ttk.Label(trow, text=APP_NAME, style="Title.TLabel").pack(side="left")
        self.subtitle = ttk.Label(tbox, text="Scheduled clicks and screen watchers that click "
                                             "for you.", style="Muted.TLabel")
        self.subtitle.pack(anchor="w", fill="x")
        hdr.bind("<Configure>", self.on_header_resize)

        # ---- summary cards
        cards = ttk.Frame(main)
        cards.pack(fill="x", pady=(12, 12))
        self.cards = cards
        self.card_frames = []
        self._cards_cols = None
        self.card_vals = {}
        self.card_titles = {}
        self.cards_caption = ttk.Label(cards, style="Section.TLabel")
        for i, (key, title) in enumerate((("next", "NEXT CLICK"), ("active", "ACTIVE JOBS"),
                                          ("today", "CLICKS TODAY"), ("screen", "SCREEN"))):
            c = ttk.Frame(cards, style="Card.TFrame", padding=(14, 10))
            self.card_frames.append(c)
            self.card_titles[key] = ttk.Label(c, text=title, style="CardTitle.TLabel")
            self.card_titles[key].pack(anchor="w")
            v = ttk.Label(c, text="—", style="CardValue.TLabel")
            v.pack(anchor="w", pady=(2, 0))
            sub = ttk.Label(c, text="", style="CardSub.TLabel")
            sub.pack(anchor="w")
            self.card_vals[key] = (v, sub)
        cards.bind("<Configure>", lambda e: self.layout_cards())
        if not self.settings.get("show_cards", True):
            cards.pack_forget()
        self.cards_btn.configure(text=self.summary_btn_text(self.settings.get("show_cards",
                                                                               True)))

        # ---- toolbar: one row; buttons that don't fit move into the "More" menu
        bar = ttk.Frame(main, height=36)
        bar.pack(fill="x", pady=(0, 10))
        self.bar = bar
        self.sel_buttons = []
        self.tool_items = []
        self.hidden_tools = []
        self._bar_sig = None

        def tool(text, cmd, group, prio, style="TButton", needs_sel=False, right=False):
            b = ttk.Button(bar, text=text, command=cmd, style=style)
            self.tool_items.append(dict(w=b, cmd=cmd, group=group, prio=prio,
                                        needs_sel=needs_sel, right=right))
            if needs_sel:
                self.sel_buttons.append(b)
            return b

        # prio: higher stays visible longer (New click always stays)
        tool("＋  New click", self.add_job, 0, 100, "Accent.TButton")
        tool("👁  New watcher", self.add_watcher, 0, 95, "Accent2.TButton")
        tool("⏺  Record", lambda: self.toggle_recording(from_hotkey=False), 0, 92,
             "Accent3.TButton")
        tool("Edit", self.edit_job, 0, 85, needs_sel=True)
        tool("Duplicate", self.duplicate_job, 0, 30, needs_sel=True)
        tool("Delete", self.delete_job, 0, 40, needs_sel=True)
        self.start_btn = tool("▶  Start", self.toggle_job, 1, 90, needs_sel=True)
        self.jpause_btn = tool("⏸  Pause", self.toggle_pause_job, 1, 80, needs_sel=True)
        self.pause_btn = tool("⏸  Pause all", self.toggle_pause_all, 1, 75)
        tool("🧪  Tests", self.open_tests, 2, 70)
        tool("↓  Import", self.import_jobs, 3, 20, right=True)
        tool("↑  Export", self.export_jobs, 3, 25, right=True)
        self.more_btn = ttk.Button(bar, text="More  ▾", command=self.show_more_menu)
        self.more_menu = tk.Menu(self.root, tearoff=0)
        bar.bind("<Configure>", lambda e: self.layout_toolbar())

        # ---- what's running now, and what's waiting its turn
        self.run_bar = ttk.Frame(main, style="Card.TFrame", padding=(10, 4))
        self.run_lbl = ttk.Label(self.run_bar, style="CardSub.TLabel")
        self.run_lbl.pack(side="left", fill="x", expand=True)
        ttk.Button(self.run_bar, text="■  Stop this run", style="Small.TButton",
                   command=lambda: self.stop_current_run()).pack(side="right")

        # ---- status bar (packed first so it always keeps its place at the bottom)
        self.status = ttk.Label(main, text="", style="Status.TLabel", padding=(0, 6, 0, 0))
        self.status.pack(side="bottom", fill="x")

        # ---- filter: All / Scheduled clicks / Screen watchers
        fl = ttk.Frame(main)
        fl.pack(fill="x", pady=(0, 6))
        self.v_filter = tk.StringVar(value=self.settings.get("view_filter", "all"))
        self.filter_btns = {}
        for val, text in (("all", "All"), ("click", "Scheduled clicks"),
                          ("watch", "Screen watchers")):
            rb = ttk.Radiobutton(fl, text=text, value=val, variable=self.v_filter,
                                 style="Seg.TRadiobutton", command=self.filter_changed)
            rb.pack(side="left", padx=(0, 2))
            self.filter_btns[val] = (rb, text)
        ttk.Button(fl, text="⟳ Refresh", style="Small.TButton",
                   command=self.refresh_all).pack(side="right")

        # ---- job table
        self.undo_bar = ttk.Frame(main, style="Card.TFrame", padding=(10, 4))
        self.undo_lbl = ttk.Label(self.undo_bar, style="CardSub.TLabel")
        self.undo_lbl.pack(side="left")
        ttk.Button(self.undo_bar, text="↶  Undo", style="Small.TButton",
                   command=self.undo_delete).pack(side="left", padx=10)
        ttk.Button(self.undo_bar, text="✕", style="Small.TButton",
                   command=lambda: self.undo_bar.pack_forget()).pack(side="right")
        self.build_batch_bar(main)
        # 4.6: "a new version is available" (dismissible)
        self.update_bar = ttk.Frame(main, style="Card.TFrame", padding=(10, 6))
        self.update_lbl = ttk.Label(self.update_bar, style="CardSub.TLabel")
        self.update_lbl.pack(side="left")
        ttk.Button(self.update_bar, text="✕", style="Small.TButton",
                   command=lambda: self.update_later(hours=24)).pack(side="right")
        ttk.Button(self.update_bar, text="Skip this version", style="Small.TButton",
                   command=self.update_skip).pack(side="right", padx=(4, 0))
        ttk.Button(self.update_bar, text="Later", style="Small.TButton",
                   command=lambda: self.update_later(hours=24)).pack(side="right", padx=(4, 0))
        ttk.Button(self.update_bar, text="What's new", style="Small.TButton",
                   command=lambda: self.open_url((self.update_info or {}).get("page"))).pack(
            side="right", padx=(4, 0))
        ttk.Button(self.update_bar, text="⬆  Upgrade now…", style="Accent.TButton",
                   command=self.upgrade_now).pack(side="right", padx=(4, 0))
        self.update_info = None
        self.root.bind("<Control-z>", self.undo_delete)
        self.root.bind("<Control-comma>", lambda e: self.open_settings())

        self.paned = ttk.PanedWindow(main, orient="vertical")
        self.paned.pack(fill="both", expand=True)
        top_pane = ttk.Frame(self.paned)
        self.bottom_pane = ttk.Frame(self.paned)
        self.paned.add(top_pane, weight=3)
        self.paned.add(self.bottom_pane, weight=2)
        tf = ttk.Frame(top_pane, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(0, 4))
        cols = tuple(JOB_COLS)
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=4,
                                 selectmode="browse")
        enable_column_fit(self.tree, self.col_width_changed)
        self.col_base = {c: JOB_COLS[c][1] for c in cols}
        self._shown_cols = None
        self._auto_w = {}               # automatic (fit-to-text) widths, per column
        self._fit_sig = None
        for c in cols:
            h, minw, _, anchor = JOB_COLS[c]
            self.tree.heading(c, text=h, anchor=anchor)
            self.tree.column(c, width=minw, minwidth=min(minw, 56) if c != "chk" else 38,
                             stretch=False, anchor=anchor)
        self.tree.heading("chk", command=self.toggle_check_all)
        tsb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.grid_lines, self.grid_geom = [], []

        def on_yscroll(*args):
            tsb.set(*args)
            self.draw_grid()
        self.tree.configure(yscrollcommand=on_yscroll)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.empty_lbl = ttk.Label(self.tree, style="Empty.TLabel", justify="center",
                                   text="No clicks yet\nClick  ＋ New click  to add one.")
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.row_tip = HoverTip(self, self.tree, self.row_tip_text)
        self.tree.bind("<Double-1>", self.on_double)
        self.tree.bind("<Return>", self.on_double)
        self.tree.bind("<Delete>", lambda e: self.delete_job())
        self.tree.bind("<space>", lambda e: self.toggle_job())
        self.tree.bind("<Button-3>", self.on_right_click)
        self.tree.bind("<Configure>", lambda e: self.root.after_idle(self.on_tree_resize))
        self.tree.bind("<B1-Motion>", lambda e: self.draw_grid(), add="+")
        self.tree.bind("<ButtonRelease-1>", lambda e: self.root.after_idle(self.draw_grid),
                       add="+")
        self.tree.bind("<<TreeviewSelect>>", lambda e: (self.refresh_tree(),
                                                         self.update_buttons()))
        self.root.bind("<Control-n>", lambda e: self.add_job())
        self.root.bind("<Control-N>", lambda e: self.add_watcher())
        self.root.bind("<Control-t>", lambda e: self.open_tests())
        self.root.bind("<Control-p>", lambda e: self.toggle_pause_all())
        self.root.bind("<F5>", lambda e: self.refresh_all())
        self.root.bind("<Control-Up>", lambda e: self.nudge_split(-0.12))
        self.root.bind("<Control-Down>", lambda e: self.nudge_split(0.12))
        self.tree.bind("<p>", lambda e: self.toggle_pause_job())
        self.tree.bind("<Control-a>", lambda e: (self.set_checks(self.visible_job_ids()),
                                                 "break")[1])
        self.tree.bind("<x>", lambda e: self.toggle_check_selected())
        for key, show in (("<Right>", True), ("<Left>", False)):
            self.tree.bind(key, lambda e, show=show: (
                [self.toggle_steps(i, show) for i in self.tree.selection() if ":" not in i
                 and (self._job_for_iid(i) or {}).get("steps")], None)[1])

        # ---- activity (with a filter: everything / clicks only / problems only)
        ah = ttk.Frame(self.bottom_pane)
        ah.pack(fill="x", pady=(8, 4))
        ttk.Label(ah, text="Activity", style="Section.TLabel").pack(side="left", padx=(0, 10))
        self.v_actf = tk.StringVar(value=self.settings.get("activity_filter", "all"))
        for val, text in (("all", "Everything"), ("clicks", "Clicks"),
                          ("problems", "Problems")):
            ttk.Radiobutton(ah, text=text, value=val, variable=self.v_actf,
                            style="Seg.TRadiobutton", command=self.activity_filter_changed).pack(
                side="left", padx=(0, 2))
        self.act_filter = FilterBox(ah, self.render_activity, width=20)
        self.act_filter.pack(side="left", padx=(12, 0))
        # 4.5.4: make the job list or Activity taller (or drag the divider above "Activity")
        sz = ttk.Frame(ah)
        sz.pack(side="right", padx=(8, 0))
        ttk.Button(sz, text="▲", width=3, style="Small.TButton",
                   command=lambda: self.nudge_split(-0.12)).pack(side="left")
        ttk.Button(sz, text="▼", width=3, style="Small.TButton",
                   command=lambda: self.nudge_split(0.12)).pack(side="left", padx=(2, 0))
        self.size_btns = sz
        self.act_tools = ttk.Frame(ah)
        self.act_tools.pack(side="right")
        ttk.Button(self.act_tools, text="Delete log…", style="Small.TButton",
                   command=self.delete_activity_log).pack(side="right")
        ttk.Button(self.act_tools, text="Clear view", style="Small.TButton",
                   command=self.clear_activity).pack(side="right", padx=(4, 4))
        self.act_order_btn = ttk.Button(self.act_tools, text="", style="Small.TButton",
                                        command=self.toggle_activity_order)
        self.act_order_btn.pack(side="right")
        ttk.Button(self.act_tools, text="⟳ Refresh", style="Small.TButton",
                   command=self.refresh_activity).pack(side="right", padx=(0, 4))
        ttk.Button(self.act_tools, text="Open log file", style="Small.TButton",
                   command=self.open_log).pack(side="right", padx=(0, 4))
        self.set_activity_order_text()
        ah.bind("<Configure>", lambda e: self.act_tools.pack_forget() if e.width < 760
                else (self.act_tools.winfo_ismapped() or self.act_tools.pack(side="right")))

        self.bottom = ttk.Frame(self.bottom_pane)
        self.bottom.pack(fill="both", expand=True)
        lf = ttk.Frame(self.bottom, style="Card.TFrame", padding=1)
        lf.pack(fill="both", expand=True)
        self.act_frame = lf
        self.logbox = tk.Text(lf, height=6, state="disabled", wrap="word",
                              font=("Cascadia Mono", 9) if "Cascadia Mono" in self.families
                              else ("Consolas", 9), borderwidth=0, padx=10, pady=6)
        lsb = ttk.Scrollbar(lf, orient="vertical", command=self.logbox.yview)
        self.logbox.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.logbox.pack(side="left", fill="both", expand=True)
        self.act_lines = []
        # 4.5.5: places in a line are links; right-click for copy and more
        lb = self.logbox
        lb.tag_bind("loc", "<Enter>", lambda e: lb.configure(cursor="hand2"))
        lb.tag_bind("loc", "<Leave>", lambda e: lb.configure(cursor=""))
        lb.tag_bind("loc", "<Button-1>", self.activity_loc_click)
        lb.bind("<Button-3>", self.activity_menu)
        lb.bind("<Control-c>", lambda e: (self.activity_copy(), "break")[1])
        lb.bind("<Control-a>", lambda e: (lb.tag_add("sel", "1.0", "end-1c"), "break")[1])
        lb.bind("<Control-f>", lambda e: (self.act_filter.focus(), "break")[1])
        lb.bind("<Button-1>", lambda e: lb.focus_set(), add="+")
        self.act_menu = tk.Menu(self.root, tearoff=0)
        self.load_activity_history()


        self.ctx = tk.Menu(self.root, tearoff=0)

    def layout_toolbar(self, force=False):
        """Lay the buttons out on one row. Lowest-priority buttons that don't fit are
        hidden and offered in the "More" menu instead."""
        bar = self.bar
        W = bar.winfo_width()
        if W <= 1:
            return
        items = self.tool_items
        widths = [it["w"].winfo_reqwidth() for it in items]
        height = max([it["w"].winfo_reqheight() for it in items] +
                     [self.more_btn.winfo_reqheight()])
        more_w = self.more_btn.winfo_reqwidth()
        sig = (W, tuple(widths))
        if sig == self._bar_sig and not force:
            return
        self._bar_sig = sig
        gap_in, gap_grp = 4, 16

        def row_width(idxs):
            w, prev = 0, None
            for i in idxs:
                if prev is not None:
                    w += gap_in if items[i]["group"] == items[prev]["group"] else gap_grp
                w += widths[i]
                prev = i
            return w

        visible = set(range(len(items)))
        while True:
            left = [i for i in range(len(items)) if i in visible and not items[i]["right"]]
            right = [i for i in range(len(items)) if i in visible and items[i]["right"]]
            hidden = len(visible) < len(items)
            need = row_width(left)
            if right:
                need += gap_grp + row_width(right)
            if hidden:
                need += gap_grp + more_w
            if need <= W:
                break
            candidates = [i for i in visible if items[i]["prio"] < 100]
            if not candidates:
                break
            visible.discard(min(candidates, key=lambda i: items[i]["prio"]))

        x, prev = 0, None
        for i in left:
            if prev is not None:
                x += gap_in if items[i]["group"] == items[prev]["group"] else gap_grp
            items[i]["w"].place(x=x, y=0, height=height)
            x += widths[i]
            prev = i
        rx = W - (more_w + gap_grp if hidden else 0)
        for n, i in enumerate(reversed(right)):
            if n:
                rx -= gap_in
            rx -= widths[i]
            items[i]["w"].place(x=rx, y=0, height=height)
        for i, it in enumerate(items):
            if i not in visible:
                it["w"].place_forget()
        self.hidden_tools = [it for i, it in enumerate(items) if i not in visible]
        if self.hidden_tools:
            self.more_btn.place(x=W - more_w, y=0, height=height)
        else:
            self.more_btn.place_forget()
        if int(str(bar.cget("height")) or 0) != height:
            bar.configure(height=height)

    def show_more_menu(self):
        m = self.more_menu
        m.delete(0, "end")
        has_sel = bool(self.tree.selection())
        prev = None
        for it in self.hidden_tools:
            if prev is not None and it["group"] != prev:
                m.add_separator()
            label = str(it["w"].cget("text")).replace("  ", " ").strip()
            m.add_command(label=label, command=it["cmd"],
                          state="normal" if has_sel or not it["needs_sel"] else "disabled")
            prev = it["group"]
        b = self.more_btn
        m.tk_popup(b.winfo_rootx() + b.winfo_width() - 180, b.winfo_rooty() + b.winfo_height() + 2)

    @staticmethod
    def summary_btn_text(shown):
        return "📊  Hide summary  ▴" if shown else "📊  Show summary  ▾"

    def toggle_cards(self):
        show = not self.settings.get("show_cards", True)
        self.settings["show_cards"] = show
        if show:
            self.cards.pack(fill="x", pady=(12, 12), after=self.hdr)
        else:
            self.cards.pack_forget()
        self.cards_btn.configure(text=self.summary_btn_text(show))
        self.save()

    def on_header_resize(self, e):
        # hide the subtitle on narrow windows; keep the title and buttons
        narrow = e.width < 760
        if narrow and self.subtitle.winfo_ismapped():
            self.subtitle.pack_forget()
        elif not narrow and not self.subtitle.winfo_ismapped():
            self.subtitle.pack(anchor="w", fill="x")

    def layout_cards(self):
        W = self.cards.winfo_width()
        if W <= 1:
            return
        ncols = 4 if W >= 860 else (2 if W >= 420 else 1)
        if ncols == self._cards_cols:
            return
        self._cards_cols = ncols
        for c in self.card_frames:
            c.grid_forget()
        for i in range(4):
            self.cards.columnconfigure(i, weight=1 if i < ncols else 0,
                                       uniform="cards" if i < ncols else "")
        self.cards_caption.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        for i, c in enumerate(self.card_frames):
            r, col = divmod(i, ncols)
            c.grid(row=r + 1, column=col, sticky="nsew",
                   padx=(0 if col == 0 else 10, 0), pady=(0 if r == 0 else 10, 0))

    def set_text(self, widget, text):
        """Change a button's text and re-flow the toolbar if its width changed."""
        if str(widget.cget("text")) != text:
            widget.configure(text=text)
            self.root.after_idle(self.layout_toolbar)

    def is_dark(self):
        t = self.settings.get("theme", "system")
        return t == "dark" or (t == "system" and system_prefers_dark())

    def toggle_theme(self):
        self.settings["theme"] = "light" if self.is_dark() else "dark"
        self.apply_theme()
        self.save()

    def apply_theme(self):
        dark = self.is_dark()
        p = self.pal = theme_palette(self.settings, dark)
        F = self.font_family
        s = self.style
        s.theme_use("clam")
        s.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["field"],
                    bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"],
                    troughcolor=p["panel"], selectbackground=p["sel"],
                    selectforeground=p["sel_fg"], insertcolor=p["fg"], arrowcolor=p["fg"],
                    focuscolor=p["accent"], font=(F, 10))
        s.configure("TButton", background=p["btn"], foreground=p["fg"], padding=(12, 6),
                    bordercolor=p["btn_border"], lightcolor=p["btn"], darkcolor=p["btn"],
                    focusthickness=0, relief="flat")
        # 4.5.4: a button that can't be used right now is only an outline (no fill); usable
        # buttons are filled
        s.map("TButton",
              background=[("disabled", p["bg"]), ("pressed", p["btn_active"]),
                          ("active", p["btn_active"])],
              foreground=[("disabled", p["muted"])],
              bordercolor=[("disabled", p["outline"])],
              relief=[("disabled", "solid")],
              lightcolor=[("disabled", p["bg"]), ("pressed", p["btn_active"]),
                          ("active", p["btn_active"])],
              darkcolor=[("disabled", p["bg"]), ("pressed", p["btn_active"]),
                         ("active", p["btn_active"])])
        s.configure("Small.TButton", padding=(8, 2), font=(F, 9))
        s.configure("Accent.TButton", background=p["accent"], foreground="#ffffff",
                    bordercolor=p["accent"], lightcolor=p["accent"], darkcolor=p["accent"],
                    font=(F, 10, "bold"))
        s.map("Accent.TButton",
              background=[("disabled", p["bg"]), ("pressed", p["accent_active"]),
                          ("active", p["accent_active"])],
              foreground=[("disabled", p["muted"])],
              bordercolor=[("disabled", p["outline"])],
              relief=[("disabled", "solid")],
              lightcolor=[("disabled", p["bg"]), ("active", p["accent_active"])],
              darkcolor=[("disabled", p["bg"]), ("active", p["accent_active"])])
        # 4.5.5: a second primary colour (teal) for "New watcher", next to the blue "New click"
        s.configure("Accent2.TButton", background=p["accent2"], foreground="#ffffff",
                    bordercolor=p["accent2"], lightcolor=p["accent2"], darkcolor=p["accent2"],
                    font=(F, 10, "bold"))
        s.map("Accent2.TButton",
              background=[("disabled", p["bg"]), ("pressed", p["accent2_active"]),
                          ("active", p["accent2_active"])],
              foreground=[("disabled", p["muted"])],
              bordercolor=[("disabled", p["outline"])],
              relief=[("disabled", "solid")],
              lightcolor=[("disabled", p["bg"]), ("active", p["accent2_active"])],
              darkcolor=[("disabled", p["bg"]), ("active", p["accent2_active"])])
        # 4.5.6: the Summary toggle stands out (accent outline and text)
        s.configure("Summary.TButton", background=p["btn"], foreground=p["accent"],
                    bordercolor=p["accent"], lightcolor=p["btn"], darkcolor=p["btn"],
                    relief="solid", font=(F, 10, "bold"))
        s.map("Summary.TButton", background=[("pressed", p["btn_active"]),
                                             ("active", p["btn_active"])])
        # 4.5.6: Record is a primary task too (rose)
        s.configure("Accent3.TButton", background=p["accent3"], foreground="#ffffff",
                    bordercolor=p["accent3"], lightcolor=p["accent3"], darkcolor=p["accent3"],
                    font=(F, 10, "bold"))
        s.map("Accent3.TButton",
              background=[("disabled", p["bg"]), ("pressed", p["accent3_active"]),
                          ("active", p["accent3_active"])],
              foreground=[("disabled", p["muted"])],
              bordercolor=[("disabled", p["outline"])],
              relief=[("disabled", "solid")],
              lightcolor=[("disabled", p["bg"]), ("active", p["accent3_active"])],
              darkcolor=[("disabled", p["bg"]), ("active", p["accent3_active"])])
        s.configure("Card.TFrame", background=p["panel"], bordercolor=p["border"],
                    relief="solid", borderwidth=1, lightcolor=p["border"],
                    darkcolor=p["border"])
        s.configure("CardTitle.TLabel", background=p["panel"], foreground=p["muted"],
                    font=(F, 8, "bold"))
        s.configure("CardValue.TLabel", background=p["panel"], foreground=p["fg"],
                    font=(F, 17, "bold"))
        s.configure("CardGood.TLabel", background=p["panel"], foreground=p["good"],
                    font=(F, 17, "bold"))
        s.configure("CardBad.TLabel", background=p["panel"], foreground=p["bad"],
                    font=(F, 17, "bold"))
        s.configure("CardWarn.TLabel", background=p["panel"], foreground=p["warn"],
                    font=(F, 17, "bold"))
        s.configure("CardSub.TLabel", background=p["panel"], foreground=p["muted"],
                    font=(F, 9))
        s.configure("Title.TLabel", font=(F, 18, "bold"))
        s.configure("Thumb.TLabel", background=p["panel"], foreground=p["muted"],
                    relief="solid", borderwidth=1, padding=4)
        s.configure("Section.TLabel", font=(F, 11, "bold"))
        s.configure("Empty.TLabel", background=p["panel"], foreground=p["muted"],
                    font=(F, 11))
        s.configure("Treeview", background=p["panel"], fieldbackground=p["panel"],
                    foreground=p["fg"], rowheight=32, bordercolor=p["panel"],
                    lightcolor=p["panel"], darkcolor=p["panel"], borderwidth=0,
                    font=(F, 10))
        s.map("Treeview", background=[("selected", p["sel"])],
              foreground=[("selected", p["sel_fg"])])
        s.configure("Treeview.Heading", background=p["head"], foreground=p["muted"],
                    relief="flat", padding=(8, 7), bordercolor=p["border"],
                    lightcolor=p["head"], darkcolor=p["head"], font=(F, 9, "bold"))
        s.map("Treeview.Heading", background=[("active", p["head"])])
        s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        for w in ("TEntry", "TSpinbox", "TCombobox"):
            s.configure(w, fieldbackground=p["field"], foreground=p["fg"],
                        bordercolor=p["border"], arrowcolor=p["fg"], insertcolor=p["fg"],
                        background=p["btn"], lightcolor=p["field"], darkcolor=p["field"],
                        padding=4)
        s.map("TEntry", bordercolor=[("focus", p["accent"])])
        s.map("TSpinbox", bordercolor=[("focus", p["accent"])],
              background=[("active", p["btn_active"])],
              fieldbackground=[("disabled", p["bg"])],
              foreground=[("disabled", p["muted"])])
        s.map("TCombobox", fieldbackground=[("readonly", p["field"])],
              foreground=[("readonly", p["fg"])], selectbackground=[("readonly", p["field"])],
              selectforeground=[("readonly", p["fg"])], background=[("active", p["btn_active"])],
              bordercolor=[("focus", p["accent"])])
        s.configure("TCheckbutton", background=p["bg"], foreground=p["fg"],
                    indicatorbackground=p["field"], indicatorforeground="#ffffff",
                    focusthickness=0)
        s.configure("Seg.TRadiobutton", background=p["bg"], foreground=p["muted"],
                    padding=(12, 5), relief="flat", borderwidth=1, font=(F, 9, "bold"),
                    indicatorsize=0, indicatormargin=0, bordercolor=p["bg"])
        s.layout("Seg.TRadiobutton", [("Radiobutton.padding", {"sticky": "nswe", "children": [
            ("Radiobutton.label", {"sticky": "nswe"})]})])
        s.map("Seg.TRadiobutton",
              background=[("selected", p["sel"]), ("active", p["btn_active"])],
              foreground=[("selected", p["sel_fg"]), ("active", p["fg"])])
        s.configure("TRadiobutton", background=p["bg"], foreground=p["fg"],
                    indicatorbackground=p["field"], indicatorforeground="#ffffff",
                    focusthickness=0)
        s.map("TRadiobutton", background=[("active", p["bg"])],
              indicatorbackground=[("selected", p["accent"]), ("active", p["field"])],
              foreground=[("disabled", p["muted"])])
        s.map("TCheckbutton", background=[("active", p["bg"])],
              indicatorbackground=[("selected", p["accent"]), ("active", p["field"])],
              foreground=[("disabled", p["muted"])])
        s.configure("TLabelframe", background=p["bg"], bordercolor=p["border"],
                    lightcolor=p["bg"], darkcolor=p["bg"])
        s.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"],
                    font=(F, 10, "bold"))
        s.map("TLabel", foreground=[("disabled", p["muted"])],
              background=[("disabled", p["bg"])])
        s.configure("Muted.TLabel", foreground=p["muted"])
        s.configure("Status.TLabel", foreground=p["muted"], font=(F, 9))
        s.configure("Warn.TLabel", foreground=p["warn"])
        s.configure("TScrollbar", background=p["panel"], troughcolor=p["panel"],
                    bordercolor=p["panel"], arrowcolor=p["muted"], lightcolor=p["panel"],
                    darkcolor=p["panel"], gripcount=0, arrowsize=12)
        s.map("TScrollbar", background=[("active", p["btn_active"])])
        s.configure("TSeparator", background=p["border"])
        s.configure("TSizegrip", background=p["bg"])
        s.configure("TPanedwindow", background=p["bg"])
        # 4.5.4: a visible, easy-to-grab divider between the job list and Activity
        s.configure("Sash", sashthickness=12, gripcount=24, background=p["bg"],
                    lightcolor=p["outline"], darkcolor=p["outline"], bordercolor=p["bg"])
        s.map("Sash", background=[("active", p["sel"])])

        self.root.option_add("*TCombobox*Listbox.background", p["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["sel"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["sel_fg"])
        for menu in (self.ctx, self.more_menu, self.main_menu):
            self.theme_menu(menu)

        self.logbox.configure(bg=p["panel"], fg=p["fg"], insertbackground=p["fg"],
                              selectbackground=p["sel"], selectforeground=p["sel_fg"],
                              highlightthickness=0)
        self.logbox.tag_configure("ok", foreground=p["good"])
        self.logbox.tag_configure("bad", foreground=p["bad"])
        self.logbox.tag_configure("warn", foreground=p["warn"])
        self.logbox.tag_configure("test", foreground=p["test"])
        self.logbox.tag_configure("time", foreground=p["muted"])
        self.logbox.tag_configure("loc", foreground=p["accent"], underline=True)
        self.logbox.tag_configure("step", foreground=p["accent2"])
        self.logbox.tag_raise("loc")

        self.tree.tag_configure("even", background=p["panel"])
        self.tree.tag_configure("odd", background=p["panel_alt"])
        self.tree.tag_configure("ticked", background=p["tick"])
        self.tree.tag_configure("running", foreground=p["fg"])
        self.tree.tag_configure("stopped", foreground=p["muted"])
        self.tree.tag_configure("paused", foreground=p["muted"])
        self.tree.tag_configure("warn", foreground=p["warn"])
        self.tree.tag_configure("bad", foreground=p["bad"])
        self.tree.tag_configure("test", foreground=p["test"])
        self.tree.tag_configure("step", foreground=p["accent2"])
        for f in self.grid_lines:
            f.configure(bg=p["grid"])
        if self.tests_win is not None:
            try:
                self.tests_win.retheme()
            except Exception:
                pass

        self.theme_btn.configure(text="☀  Light" if dark else "☾  Dark")
        self.root.after_idle(lambda: self.layout_toolbar(force=True))
        self.theme_window(self.root)
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):
                self.theme_window(w)

    def theme_menu(self, menu):
        p, F = self.pal, self.font_family
        menu.configure(bg=p["panel"], fg=p["fg"], activebackground=p["sel"],
                       activeforeground=p["sel_fg"], disabledforeground=p["muted"],
                       borderwidth=1, font=(F, 10))

    def flash_status(self, text, seconds=3):
        """A short confirmation in the status bar (e.g. "Copied 3 rows")."""
        self._flash = (text, time.time() + seconds)
        try:
            self.status.configure(text=f"✔  {text}")
        except Exception:
            pass

    def show_places(self, text, parent=None, job_name=None):
        """Hide the app and mark every place a log line mentions, e.g. "(878, 243)" (4.5.5).
        Where the line says a watched picture was found there, the picture's outline is
        drawn at its size (and scale); other places get the crosshair."""
        pts = [(int(m.group(1)), int(m.group(2)), m.start()) for m in LOC_RE.finditer(text)]
        if not pts:
            return
        if getattr(self, "_spot_busy", False):
            return
        job = None
        if job_name:
            with self.lock:
                job = next((j for j in self.jobs if j["name"] == job_name), None)
        size = None
        if job and job.get("watch_png") and HAVE_PIL:
            try:
                size = b64_to_img(job["watch_png"]).size
            except Exception:
                size = None
        m = re.search(r"at (\d{2,3})% size", text)
        sc = int(m.group(1)) / 100 if m else 1.0
        boxes, cross = [], None
        for x, y, pos in pts:
            before = text[max(0, pos - 40):pos].lower()
            is_pic = "picture" in before and "button" not in before and "spot" not in before
            if is_pic and size:
                w, h = size[0] * sc, size[1] * sc
                closest = "closest" in before
                boxes.append((round(x - w / 2), round(y - h / 2), round(w), round(h),
                              "closest place (not a match)" if closest else "picture was here",
                              cross is None and not boxes and not closest, not closest))
                if cross is None and len(pts) == 1:
                    cross = (x, y)
            elif cross is None:
                cross = (x, y)
            else:
                boxes.append((x - 14, y - 14, 28, 28, f"({x}, {y})", False, True))
        if cross is None:
            cross = (pts[0][0], pts[0][1])
        where = ", ".join(f"({x}, {y})" for x, y, _ in pts)
        self._spot_busy = True
        restore = self.hide_app(parent)
        cap = (f"{job_name}  ·  " if job_name else "") + f"logged at {where}"
        self.root.after(400, lambda: self.flash_marker(cross[0], cross[1], cap, restore,
                                                       others=boxes or None))

    def theme_window(self, w):
        try:
            w.configure(bg=self.pal["bg"])
        except Exception:
            pass
        set_dark_titlebar(w, self.is_dark())

    def describe_schedule(self, j):
        if is_watch(j):
            return describe_watch(j)
        if not j.get("random_on", True):
            return f"Every {fmt_compact(j['interval_s'])}, exact"
        return (f"Every {fmt_compact(j['interval_s'])}, +{fmt_compact(j['delay_min_s'])}"
                f"–{fmt_compact(j['delay_max_s'])}")

    def watch_row(self, j, now, paused):
        """(status, schedule, next, countdown, state) for a screen watcher."""
        sched = describe_watch(j)
        note = j.get("watch_note") or ""
        if not j.get("enabled"):
            return "○  Stopped", sched, "—", "—", "stopped"
        if paused or j.get("paused"):
            return ("⏸  Paused", sched, "Paused" if paused else "Paused (this job)", "—",
                    "paused")
        appears = j.get("watch_trigger") == "appears"
        if j.get("pending_click_at"):
            w = self.wait_msgs.get((j["id"], "watch"))
            if w:
                return "●  Waiting", sched, "Click waiting", "retrying…", "warn"
            return ("⚡  Clicking", sched, "Picture appeared" if appears else "Picture gone",
                    "click in " + fmt_dur(j["pending_click_at"] - now), "bad")
        nc = j.get("next_check")
        cd = ("check in " + fmt_dur(nc - now)) if nc and nc > now else "checking…"
        st = j.get("watch_state")
        seen = j.get("last_seen")
        seen_t = datetime.fromtimestamp(seen).strftime("%H:%M:%S") if seen else ""
        if note == "outside active hours":
            return "🌙  Off hours", sched, f"Active {describe_hours(j)}", "—", "paused"
        if st == "unknown":
            # it can't see the picture right now: that's a problem, not "fine" (4.5.6)
            n = int(j.get("issue_count") or 0)
            return ("⚠  Can't watch", sched, f"Can't tell: {note}"
                    + (f" ({n} checks)" if n > 1 else ""), cd, "warn")
        if appears:
            if st == "seen":
                return "⚠  Showing", sched, note or "Picture showing", cd, "warn"
            if st == "missing":
                return ("👁  Watching", sched, "Not showing" + (f" (last seen {seen_t})"
                                                               if seen_t else ""), cd, "running")
        else:
            if st == "missing":
                return "⚠  Missing", sched, note or "Picture missing", cd, "warn"
            if st == "seen":
                return "👁  Watching", sched, "Seen " + seen_t, cd, "running"
        return "👁  Watching", sched, "Starting…", cd, "running"

    def build_rows(self, now, flt=None):
        """Rows for the job list. Jobs with steps get ▸ / ▾ in front of their name, and
        their steps as indented ↳ rows when expanded (4.5.6)."""
        rows = self._build_rows(now, flt)
        out = []
        exp = getattr(self, "expanded", set())
        by_id = {j["id"]: j for j in self.jobs}
        for iid, vals, state in rows:
            j = by_id.get(iid)
            steps = (j.get("steps") or []) if j else []
            if steps and hasattr(vals, "cells"):
                arrow = "▾" if iid in exp else "▸"
                vals.cells["name"] = f"{arrow} {vals.cells['name']}"
                vals.cells["kind"] = vals.cells.get("kind", "") + " ☰"
            out.append((iid, vals, state))
            if steps and iid in exp:
                for k, st in enumerate(steps[:200]):
                    out.append(step_row(j, k, st, self.groups if hasattr(self, "groups")
                                        else None))
        return out

    def _build_rows(self, now, flt=None):
        rows = []
        paused = self.settings.get("paused")
        if flt is None:
            flt = self.v_filter.get() if hasattr(self, "v_filter") else "all"
        for j in self.jobs:
            if flt == "watch" and not is_watch(j) or flt == "click" and is_watch(j):
                continue
            pos = target_text(j)
            btn = j["button"].capitalize() + (" ×2" if j["clicks"] == 2 else "")
            last = j.get("last_result") or "—"
            if is_watch(j):
                status, sched, nxt, cd, state = self.watch_row(j, now, paused)
                if state == "running" and last.startswith("Click FAILED"):
                    state = "bad"
                vals = RowVals((status, j["name"], pos, btn, sched, nxt, cd,
                                j.get("count", 0), last))
                vals.cells = dict(status=status, kind="👁 Watcher", name=j["name"],
                                  what=f"{watch_summary(j)} → {watch_then(j)}",
                                  watchfor=watch_summary(j), then=watch_then(j),
                                  every=f"every {fmt_compact(j.get('watch_interval_s', 30))} · "
                                        f"{int(j.get('watch_confirm', 2))} in a row"
                                        + (" · once" if j.get("watch_once", True) else ""),
                                  seen=nxt, nextcheck=cd, next=nxt, countdown=cd,
                                  count=j.get("count", 0), last=last)
                rows.append((j["id"], vals, state))
                if j.get("test_at"):
                    rows.append(self.test_row(j, now, pos, btn))
                if j.get("wtest_at"):
                    rows.append(self.wtest_row(j, now, pos, btn))
                continue
            waiting = self.wait_msgs.get((j["id"], "scheduled"))
            if not j.get("enabled") or not j.get("next_run"):
                status, nxt, cd, state = "○  Stopped", "—", "—", "stopped"
            elif paused or j.get("paused"):
                status, state, cd = "⏸  Paused", "paused", "—"
                nxt = "Paused" if paused else f"Paused (was {fmt_time(j['next_run'])})"
            elif j.get("hours_on") and not in_active_hours(j, now) and \
                    not in_active_hours(j, j["next_run"]):
                status, state = "🌙  Off hours", "paused"
                nxt, cd = fmt_time(j["next_run"]), fmt_dur(j["next_run"] - now)
            elif waiting:
                status, state = "●  Waiting", "warn"
                nxt, cd = f"until {fmt_time(j.get('deadline'))}", "retrying…"
            else:
                status, state = "●  Running", "running"
                nxt, cd = fmt_time(j["next_run"]), fmt_dur(j["next_run"] - now)
                if last.startswith(("Missed", "Test FAILED")):
                    state = "bad"
            sched = self.describe_schedule(j)
            vals = RowVals((status, j["name"], pos, btn, sched, nxt, cd, j.get("count", 0),
                            last))
            vals.cells = dict(status=status, kind="⏱ Click", name=j["name"],
                              what=f"{sched} → {btn} · {pos}", target=f"{btn} · {pos}",
                              schedule=sched, hours=run_rules(j), next=nxt, countdown=cd,
                              count=j.get("count", 0), last=last)
            rows.append((j["id"], vals, state))
            if j.get("test_at"):
                rows.append(self.test_row(j, now, pos, btn))
        return rows

    def wtest_row(self, j, now, pos, btn):
        at = j["wtest_at"]
        waiting = j.get("wtest_deadline") and at > now and at - now <= 31
        cd = "retrying…" if waiting else fmt_dur(at - now)
        what = ("checks, clicks if missing" if j.get("wtest_click")
                else "checks only, no click")
        return ("wtest:" + j["id"], test_vals(("◆  Watch test",
                                                f"   ↳ {j['name']} (watch test)", pos, btn,
                                                "One time only", fmt_time(at), cd, "",
                                                f"Temporary — {what}")), "test")

    def test_row(self, j, now, pos, btn):
        tw = self.wait_msgs.get((j["id"], "test"))
        if tw:
            t_nxt = f"until {fmt_time(j.get('test_deadline'))}"
            t_cd, t_last = "retrying…", f"Waiting: {tw}"
        else:
            t_nxt, t_cd = fmt_time(j["test_at"]), fmt_dur(j["test_at"] - now)
            t_last = "Temporary — doesn't change the schedule"
        return ("test:" + j["id"], test_vals(("◆  Test", f"   ↳ {j['name']} (test)", pos, btn,
                                              "One time only", t_nxt, t_cd, "", t_last)),
                "test")

    def refresh_tree(self, full=False):
        now = time.time()
        with self.lock:
            rows = self.build_rows(now)
        want = [r[0] for r in rows]
        for iid in self.tree.get_children():
            if full or iid not in want:
                self.tree.delete(iid)
        sel = set(self.tree.selection())
        self.checked &= {j["id"] for j in self.jobs}
        for idx, (iid, row, state) in enumerate(rows):
            cells = getattr(row, "cells", {})
            vals = tuple(
                (("☑" if iid in self.checked else "☐") if ":" not in iid else "") if c == "chk"
                else (str(cells.get(c, "")) if c == "count" else f"  {cells.get(c, '')}")
                for c in JOB_COLS)
            tags = [state]
            if iid not in sel:
                tags.insert(0, "ticked" if iid in self.checked else ("odd" if idx % 2 else "even"))
            if self.tree.exists(iid):
                self.tree.item(iid, values=vals, tags=tags)
                if self.tree.index(iid) != idx:
                    self.tree.move(iid, "", idx)
            else:
                self.tree.insert("", idx, iid=iid, values=vals, tags=tags)
        if rows:
            self.empty_lbl.place_forget()
        else:
            flt = self.v_filter.get()
            self.empty_lbl.configure(text={
                "watch": "No screen watchers yet\nClick  👁 New watcher  to watch for a "
                         "picture and click when it disappears.",
                "click": "No scheduled clicks yet\nClick  ＋ New click  to add one."}.get(
                flt, "Nothing here yet\nClick  ＋ New click  or  👁 New watcher  to start."))
            self.empty_lbl.place(relx=0.5, rely=0.55, anchor="center")
        counts = {"all": len(self.jobs), "watch": sum(1 for j in self.jobs if is_watch(j))}
        counts["click"] = counts["all"] - counts["watch"]
        for val, (rb, text) in self.filter_btns.items():
            want_text = f"{text}  {counts[val]}"
            if str(rb.cget("text")) != want_text:
                rb.configure(text=want_text)
        self.update_batch_bar()
        self.apply_view(force=full)
        self.draw_grid()

    def view_key(self):
        v = self.v_filter.get() if hasattr(self, "v_filter") else "all"
        return v if v in JOB_VIEWS else "all"

    def apply_view(self, force=False):
        """Show the current view's columns, sized to their text (4.5.4). Columns you sized
        yourself keep their width; the others fit their longest text up to a sensible
        maximum, and Last result takes the rest of the row. While the list is just ticking
        (countdowns), columns only grow, so nothing jumps around."""
        view = self.view_key()
        t = self.tree
        W = t.winfo_width()
        n_rows = len(t.get_children())
        sig = (view, W, n_rows)
        now = time.time()
        full = force or sig != self._fit_sig
        if not full and now - getattr(self, "_fit_at", 0) < 3:
            return
        self._fit_at = now
        self._fit_sig = sig
        heads = VIEW_HEADINGS.get(view, {})
        for c in JOB_VIEWS[view]:
            want = heads.get(c, JOB_COLS[c][0])
            if c != "chk" and t.heading(c, "text") != want:
                t.heading(c, text=want)
        fixed = self.settings.get("col_widths") or {}
        widths = {}
        for c in JOB_VIEWS[view]:
            h, minw, maxw, _ = JOB_COLS[c]
            if c == "chk":
                widths[c] = 38
            elif c in fixed:
                widths[c] = max(30, min(1200, int(fixed[c])))
            else:
                fit = column_fit_width(t, c, limit=maxw)
                fit = max(minw, fit)
                old = self._auto_w.get(c)
                if old and not full and fit < old:
                    fit = old                       # grow only while ticking
                widths[c] = fit
        self._auto_w.update({c: w for c, w in widths.items() if c not in fixed})
        shown = list(JOB_VIEWS[view])
        if W > 1:
            drop = list(VIEW_DROP[view])
            while drop and sum(max(JOB_COLS[c][1], min(widths[c], 160)) for c in shown) > W:
                shown.remove(drop.pop(0))
            total = sum(widths[c] for c in shown)
            if total < W - 4:                      # Last result takes the free room
                widths["last"] = widths["last"] + (W - 4 - total)
            elif total > W:                        # squeeze the widest automatic columns
                over = total - W
                for c in sorted((c for c in shown if c not in fixed and c != "chk"),
                                key=lambda c: -widths[c]):
                    if over <= 0:
                        break
                    give = min(over, widths[c] - JOB_COLS[c][1])
                    if give > 0:
                        widths[c] -= give
                        over -= give
        for c in shown:
            if int(t.column(c, "width")) != widths[c]:
                t.column(c, width=widths[c], stretch=(c == "last" and "last" not in fixed))
        if tuple(shown) != self._shown_cols:
            self._shown_cols = tuple(shown)
            t["displaycolumns"] = shown
        self.root.after_idle(self.draw_grid)

    def col_width_changed(self, col, width):
        """A job-list column was fitted (double-click on its border) or dragged: keep it."""
        cw = dict(self.settings.get("col_widths") or {})
        cw[col] = int(width)
        self.settings["col_widths"] = cw
        self.save()
        self.root.after_idle(self.draw_grid)

    def reset_col_widths(self):
        self.settings["col_widths"] = {}
        self._auto_w = {}
        self.save()
        self.apply_view(force=True)

    def on_tree_resize(self):
        """Fit the columns again when the table changes size (hides the least important
        ones when the window gets narrow)."""
        self.apply_view()
        self.draw_grid()

    def draw_grid(self):
        """Draws thin column and row divider lines over the job table."""
        t = self.tree
        lines = []
        try:
            boxes = [b for b in (t.bbox(i) for i in t.get_children()) if b]
            if boxes:
                head_h = min(b[1] for b in boxes)          # top of first visible row
                bottom = max(b[1] + b[3] for b in boxes)    # bottom of last visible row
                xs, x = [], 0
                dc = t["displaycolumns"]
                if isinstance(dc, str):
                    dc = (dc,)
                if not dc or dc[0] == "#all":
                    dc = t["columns"]
                for c in dc:
                    x += int(t.column(c, "width"))
                    xs.append(x)
                right = min(xs[-1], t.winfo_width())
                for x in xs[:-1]:
                    if x < right:
                        lines.append((x, 8, 1, max(1, head_h - 16)))     # header divider
                        lines.append((x, head_h, 1, bottom - head_h))    # body divider
                lines.append((0, head_h - 1, right, 1))                   # under header
                for b in boxes:
                    lines.append((0, b[1] + b[3] - 1, right, 1))          # under each row
        except Exception:
            lines = []
        while len(self.grid_lines) < len(lines):
            f = tk.Frame(t, bg=self.pal["grid"], bd=0, highlightthickness=0)
            # the thin lines sit on top of the table: pass clicks and drags through to it,
            # so a column border can be grabbed even right on its line (4.5.1)
            for seq, kind in (("<ButtonPress-1>", "press"), ("<B1-Motion>", "motion"),
                              ("<ButtonRelease-1>", "release"), ("<Double-Button-1>", "double"),
                              ("<Button-3>", "right")):
                f.bind(seq, lambda e, f=f, k=kind: self._grid_forward(f, e, k))
            self.grid_lines.append(f)
            self.grid_geom.append(None)
        for i, f in enumerate(self.grid_lines):
            g = lines[i] if i < len(lines) else None
            if g == self.grid_geom[i]:
                continue
            if g:
                f.place(x=g[0], y=g[1], width=g[2], height=g[3])
                try:
                    f.configure(cursor="sb_h_double_arrow" if g[2] == 1 and g[1] < 30 else "")
                except Exception:
                    pass
            else:
                f.place_forget()
            self.grid_geom[i] = g

    def _grid_forward(self, f, e, kind):
        """Hand a click on a grid line to the table underneath."""
        t = self.tree
        try:
            x, y = e.x + f.winfo_x(), e.y + f.winfo_y()
            if kind == "press":
                t.event_generate("<ButtonPress-1>", x=x, y=y)
            elif kind == "motion":
                t.event_generate("<Motion>", x=x, y=y, state=0x100)
            elif kind == "release":
                t.event_generate("<ButtonRelease-1>", x=x, y=y)
            elif kind == "right":
                t.event_generate("<Button-3>", x=x, y=y, rootx=e.x_root, rooty=e.y_root)
            elif kind == "double":
                ev = type("E", (), {"widget": t, "x": x, "y": y})()
                if _autofit_double(ev) is None:
                    self.on_double()
        except Exception:
            pass

    def update_buttons(self):
        if self.tests_win is not None:
            try:
                self.tests_win.refresh()
            except Exception:
                pass
        sel = self.tree.selection()
        for b in self.sel_buttons:
            b.state(["!disabled"] if sel else ["disabled"])
        job = self._job_for_iid(sel[0]) if sel else None
        self.set_text(self.start_btn, "■  Stop" if job and job.get("enabled") else "▶  Start")
        self.set_text(self.jpause_btn, "▶  Resume" if job and job.get("paused") else "⏸  Pause")
        if not (job and job.get("enabled")):
            self.jpause_btn.state(["disabled"])

    def update_cards(self, now):
        """The summary at the top. It follows the job-list filter (4.5.6): All shows every
        job, Scheduled clicks only clicks, Screen watchers only what watchers are doing."""
        view = self.view_key() if hasattr(self, "tree") else "all"
        with self.lock:
            paused = self.settings.get("paused")
            jobs = [j for j in self.jobs if view == "all"
                    or (view == "watch") == is_watch(j)]
            total = len(jobs)
            enabled = [j for j in jobs
                       if j.get("enabled") and not j.get("paused")
                       and (j.get("next_run") or is_watch(j))]
            n_jpaused = sum(1 for j in jobs if j.get("enabled") and j.get("paused"))
            upcoming = [] if paused else [
                (j["next_run"], j["name"], False) for j in enabled if j.get("next_run")]
            upcoming += [] if paused else [
                (j["pending_click_at"], j["name"], False) for j in enabled
                if is_watch(j) and j.get("pending_click_at")]
            n_watch = sum(1 for j in enabled if is_watch(j))
            upcoming += [(j["test_at"], j["name"], True) for j in jobs if j.get("test_at")]
            upcoming += [(j["wtest_at"], j["name"], True) for j in jobs if j.get("wtest_at")]
            st = self.settings
            if st.get("stats_date") == datetime.now().strftime("%Y-%m-%d"):
                today, missed = st.get("stats_clicks", 0), st.get("stats_missed", 0)
                w_today, w_missed = st.get("stats_clicks_watch", 0), st.get("stats_missed_watch", 0)
            else:
                today = missed = w_today = w_missed = 0
            watchers = [dict(j) for j in enabled if is_watch(j)]
        if view == "click":
            today, missed = max(0, today - w_today), max(0, missed - w_missed)
        avail = screen_available()
        caption = {"all": "Summary · all jobs", "click": "Summary · scheduled clicks",
                   "watch": "Summary · screen watchers"}[view]
        if self.cards_caption.cget("text") != caption:
            self.cards_caption.configure(text=caption)

        def card(key, title, value, sub, style="CardValue.TLabel"):
            t = self.card_titles[key]
            if t.cget("text") != title:
                t.configure(text=title)
            v, s_ = self.card_vals[key]
            v.configure(text=value, style=style)
            s_.configure(text=sub)

        if view == "watch":
            nxt = [(j["next_check"], j["name"]) for j in watchers if j.get("next_check")]
            pend = [(j["pending_click_at"], j["name"]) for j in watchers
                    if j.get("pending_click_at")]
            if paused:
                card("next", "NEXT CHECK", "—", "All jobs paused", "CardWarn.TLabel")
            elif nxt:
                t, name = min(nxt)
                card("next", "NEXT CHECK", fmt_dur(max(0, t - now)),
                     f"{name}" + (f" · CLICK in {fmt_dur(min(pend)[0] - now)} ({min(pend)[1]})"
                                  if pend else ""),
                     "CardWarn.TLabel" if pend else "CardValue.TLabel")
            else:
                card("next", "NEXT CHECK", "—", "No watcher running")
            issues = [j for j in watchers if j.get("watch_state") == "unknown"
                      and j.get("watch_note") != "outside active hours"]
            seen = sum(1 for j in watchers if j.get("watch_state") == "seen")
            gone = sum(1 for j in watchers if j.get("watch_state") == "missing")
            if issues:
                card("active", "WATCHERS", f"{len(issues)} can't watch",
                     f"{issues[0]['name']}: {issues[0].get('watch_note')}"
                     + (f" (+{len(issues) - 1} more)" if len(issues) > 1 else ""),
                     "CardBad.TLabel")
            else:
                card("active", "WATCHERS",
                     f"{len(watchers)} of {total} watching" if watchers else "none watching",
                     f"picture seen: {seen} · not showing: {gone}"
                     + (f" · {n_jpaused} paused" if n_jpaused else ""),
                     "CardGood.TLabel" if watchers else "CardValue.TLabel")
            card("today", "WATCHER CLICKS TODAY", str(w_today),
                 f"{w_missed} failed" if w_missed else "no failed clicks",
                 "CardBad.TLabel" if w_missed else "CardValue.TLabel")
        else:
            label = "NEXT CLICK"
            if upcoming:
                t, name, is_test = min(upcoming)
                card("next", label, fmt_dur(t - now) if t > now else "now",
                     f"{name}{' (test)' if is_test else ''} · {fmt_time(t)}")
            else:
                card("next", label, "—",
                     "All paused" if paused and enabled else
                     ("Watchers only click when their picture changes" if enabled
                      else "Nothing scheduled"))
            if view == "click":
                waiting = [j for j in jobs if (j["id"], "scheduled") in self.wait_msgs]
                card("active", "SCHEDULED CLICKS", f"{len(enabled)} of {total} running",
                     (f"{len(waiting)} waiting: {self.wait_msgs.get((waiting[0]['id'], 'scheduled'))}"
                      if waiting else "All paused" if paused else
                      (f"{n_jpaused} paused" if n_jpaused else "none paused")),
                     "CardWarn.TLabel" if waiting or paused else "CardValue.TLabel")
                card("today", "CLICKS TODAY", str(today),
                     f"{missed} missed" if missed else "no missed clicks",
                     "CardBad.TLabel" if missed else "CardValue.TLabel")
            else:
                card("active", "ACTIVE JOBS", f"{len(enabled)} of {total}",
                     "All jobs paused" if paused else
                     (f"{len(enabled) - n_watch} scheduled · {n_watch} watching"
                      + (f" · {n_jpaused} paused" if n_jpaused else "") if enabled
                      else (f"{n_jpaused} paused" if n_jpaused else "none running")),
                     "CardWarn.TLabel" if paused else "CardValue.TLabel")
                card("today", "CLICKS TODAY", str(today),
                     f"{missed} missed" if missed else "no missed clicks")
        x, y = get_cursor()
        card("screen", "SCREEN", "Available" if avail else "Locked",
             (f"Idle {fmt_dur(idle_seconds())} · Mouse {x}, {y}" if avail
              else ("Watchers can't look while it's locked" if view == "watch"
                    else "Clicks will wait for the screen")),
             "CardGood.TLabel" if avail else "CardBad.TLabel")

    def ui_tick(self):
        added = False
        while True:
            try:
                line = self.logq.get_nowait()
            except queue.Empty:
                break
            if not added:
                self.logbox.configure(state="normal")
                added = True
            ts, _, msg = line.partition("  ")
            tag, is_click, is_problem = self.classify(msg)
            item = (ts, msg, tag, is_click, is_problem)
            self.act_lines.append(item)
            if len(self.act_lines) > MAX_UI_LOG_LINES * 2:
                del self.act_lines[:MAX_UI_LOG_LINES]
            if self.activity_shows(item):
                self.insert_activity(item, top=self.activity_newest_first())
        if added:
            lines = int(self.logbox.index("end-1c").split(".")[0])
            if lines > MAX_UI_LOG_LINES:
                if self.activity_newest_first():
                    self.logbox.delete(f"{MAX_UI_LOG_LINES + 1}.0", "end-1c")
                else:
                    self.logbox.delete("1.0", f"{lines - MAX_UI_LOG_LINES}.0")
            self.logbox.see("1.0" if self.activity_newest_first() else "end")
            self.logbox.configure(state="disabled")

        now = time.time()
        try:
            rects = []
            for w in [self.root] + [w for w in self.root.winfo_children()
                                    if isinstance(w, tk.Toplevel)]:
                if w.winfo_viewable():
                    # where Clickue's own windows are (title bar included): a watched picture
                    # is never "found" there (4.6)
                    rects.append((w.winfo_rootx() - 8, w.winfo_rooty() - 40,
                                  w.winfo_width() + 16, w.winfo_height() + 48))
            self.own_rects = rects
        except Exception:
            self.own_rects = []
        try:
            self.own_visible = self.root.winfo_viewable() or any(
                w.winfo_viewable() for w in self.root.winfo_children()
                if isinstance(w, tk.Toplevel))
        except Exception:
            self.own_visible = True
        self.refresh_tree()
        self.update_cards(now)
        self.update_buttons()
        paused = self.settings.get("paused")
        self.set_text(self.pause_btn, "▶  Resume all" if paused else "⏸  Pause all")
        tray = "tray on" if self.tray else "tray off"
        stop_hk = self.settings.get("hk_stop")
        flash = getattr(self, "_flash", None)
        if flash and flash[1] > now:
            self.status.configure(text=f"✔  {flash[0]}")
        else:
            self.status.configure(text=f"v{VERSION}   ·   {tray}   ·   "
                                   + (f"Emergency stop: {stop_hk}   ·   " if stop_hk else "")
                                   + f"Data: {DATA_DIR}   ·   Shortcuts: Ctrl+N new · Enter edit · "
                                     f"Space start/stop · P pause · Ctrl+T test · Del delete")
        self.update_run_bar()
        err = getattr(self, "save_error", "")
        if err and not getattr(self, "_save_warned", False):
            self._save_warned = True
            messagebox.showwarning(APP_NAME, f"Clickue couldn't save your changes:\n{err}\n\n"
                                             f"Another program may be blocking the data folder. "
                                             f"Clickue keeps trying with every change; check "
                                             f"the Activity log.", parent=self.root)
        # run each second on the second, so countdowns don't skip a second now and then
        self.root.after(1000 - int(time.time() * 1000) % 1000 + 15, self.ui_tick)

    def update_run_bar(self):
        """Show what's running and what's waiting its turn (hidden when idle)."""
        bar = getattr(self, "run_bar", None)
        if bar is None:
            return
        txt, waiting = self.queue_status()
        rec = getattr(self, "recorder", None)
        if rec is not None and rec.state in ("recording", "paused"):
            txt = ("● Recording a macro" if rec.state == "recording" else "Recording paused") + \
                  (f" · {txt}" if txt else "")
        if waiting:
            txt += (" · " if txt else "") + "Waiting their turn: " + ", ".join(waiting[:4]) + \
                   (f" +{len(waiting) - 4}" if len(waiting) > 4 else "")
        if txt:
            self.run_lbl.configure(text=("▶ " if not txt.startswith("●") else "") + txt)
            if not bar.winfo_ismapped():
                bar.pack(fill="x", pady=(0, 6), before=self.paned)
        elif bar.winfo_ismapped():
            bar.pack_forget()

    # ------------------------------------------------------------ tests window
    def open_tests(self, job=None):
        """Open (or bring forward) the Tests window. The main window steps aside."""
        if job is None:
            sel = self.tree.selection()
            job = self._job_for_iid(sel[0]) if sel else None
        if self.tests_win is not None and self.tests_win.winfo_exists():
            self.tests_win.select_job(job)
            self.tests_win.deiconify()
            self.tests_win.lift()
            self.tests_win.focus_force()
        else:
            self.tests_win = TestsWindow(self, job)

    def tests_closed(self):
        self.tests_win = None
        if self.main_visible():
            self.root.lift()
            self.root.focus_force()

    def restore_split(self):
        try:
            self.root.update_idletasks()
            h = self.paned.winfo_height()
            if h > 50:
                frac = min(SPLIT_MAX, max(SPLIT_MIN, float(self.settings.get("split", 0.45))))
                self.paned.sashpos(0, int(h * frac))
        except Exception:
            pass

    def refresh_all(self):
        """⟳ Refresh / F5 (4.5.6): every running watcher looks at the screen right away,
        and the job list, its columns and the summary are rebuilt."""
        now = time.time()
        n = 0
        with self.lock:
            for j in self.jobs:
                if is_watch(j) and j.get("enabled") and not j.get("paused"):
                    j["next_check"] = now
                    n += 1
        self._auto_w = {}
        self.refresh_tree(full=True)
        self.apply_view(force=True)
        self.update_buttons()
        self.flash_status("Refreshed" + (f" - {n} watcher{'s' if n != 1 else ''} checking now"
                                         if n else ""))

    def nudge_split(self, delta):
        """▲ / ▼ next to Activity (and Ctrl+Up / Ctrl+Down): give the job list or the
        Activity panel more room. The divider can also be dragged; it's remembered."""
        try:
            h = self.paned.winfo_height()
            if h <= 50:
                return
            frac = self.paned.sashpos(0) / h + delta
            frac = min(SPLIT_MAX, max(SPLIT_MIN, frac))
            self.paned.sashpos(0, int(h * frac))
            self.root.after_idle(self.draw_grid)
            self.remember_split()
        except Exception:
            pass

    def remember_split(self):
        try:
            h = self.paned.winfo_height()
            if h > 50:
                self.settings["split"] = round(self.paned.sashpos(0) / h, 3)
                self.save()
        except Exception:
            pass

    def clear_test_history(self, parent=None):
        if not self.test_history or not messagebox.askyesno(
                APP_NAME, "Clear the whole test history?", parent=parent or self.root):
            return
        with self.lock:
            self.test_history = []
            self.tests_dirty = True
            try:
                write_json(TESTS_PATH, self.test_history)
            except Exception:
                pass

    def selected_watcher(self):
        j = self.selected_job()
        if j and not is_watch(j):
            messagebox.showinfo(APP_NAME, "Select a screen watcher for this test.",
                                parent=self.root)
            return None
        return j

    def check_picture_selected(self):
        j = self.selected_watcher()
        if j:
            self.show_watch_for(j)

    def dry_run_selected(self):
        j = self.selected_watcher()
        if j:
            self.dry_run_for(j)

    def schedule_watch_test(self):
        j = self.selected_watcher()
        if j:
            WatchTestDialog(self, j)

    def activity_filter_changed(self):
        self.settings["activity_filter"] = self.v_actf.get()
        self.save()
        self.render_activity()

    @staticmethod
    def classify(msg):
        """(colour tag, is_click, is_problem) for an activity line."""
        tag = ()
        if ("MISSED" in msg or "FAILED" in msg or "failed" in msg or "NOT" in msg
                or "stopped:" in msg):
            tag = ("bad",)
        elif "FINISHED" in msg or "skipped" in msg or "outside its active hours" in msg:
            tag = ("warn",)
        elif "waiting" in msg or "GONE" in msg or "not found" in msg:
            tag = ("warn",)
        elif "TEST" in msg or "test click" in msg or "DRY RUN" in msg:
            tag = ("test",)
        elif " - OK" in msg or "worked" in msg:
            tag = ("ok",)
        is_click = (" click at " in msg and (" - OK" in msg or "worked" in msg)) or \
            "picture was gone" in msg or "picture appeared -" in msg
        return tag, is_click, bool(tag) and tag[0] in ("bad", "warn")

    def activity_shows(self, item):
        f = self.v_actf.get()
        ok = f == "all" or (f == "clicks" and item[3]) or (f == "problems" and item[4])
        fb = getattr(self, "act_filter", None)
        return ok and (fb is None or fb.matches(item[0], item[1]))

    def insert_activity(self, item, top=False):
        """One Activity line; places like (878, 243) become links (4.5.5); lines about a
        step of a job are marked with ↳ (4.5.6). top=True puts it first (newest first)."""
        ts, msg, tag = item[0], item[1], item[2]
        lb = self.logbox
        if top:
            lb.mark_set("ins", "1.0")
            lb.mark_gravity("ins", "right")
            at = "ins"
        else:
            at = "end"
        lb.insert(at, ts + "  ", ("time",))
        if STEP_LINE_RE.search(msg):
            lb.insert(at, "↳ ", ("step",))
            tag = tuple(tag) + ("step",) if not tag else tuple(tag)
        pos = 0
        for m in LOC_RE.finditer(msg):
            if m.start() > pos:
                lb.insert(at, msg[pos:m.start()], tag)
            lb.insert(at, m.group(0), tuple(tag) + ("loc",))
            pos = m.end()
        lb.insert(at, msg[pos:] + "\n", tag)

    def activity_line_at(self, x, y):
        idx = self.logbox.index(f"@{x},{y}")
        return self.logbox.get(f"{idx} linestart", f"{idx} lineend")

    @staticmethod
    def job_in_line(line):
        m = re.search(r"\[([^\]]{1,200})\]", line)
        return m.group(1) if m else None

    def activity_loc_click(self, e):
        line = self.activity_line_at(e.x, e.y)
        self.show_places(line, job_name=self.job_in_line(line))
        return "break"

    def activity_copy(self):
        lb = self.logbox
        try:
            text = lb.get("sel.first", "sel.last")
        except tk.TclError:
            idx = lb.index("insert")
            text = lb.get(f"{idx} linestart", f"{idx} lineend")
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.flash_status("Copied")

    def activity_menu(self, e):
        lb = self.logbox
        line = self.activity_line_at(e.x, e.y).strip()
        idx = lb.index(f"@{e.x},{e.y}")
        m = self.act_menu
        m.delete(0, "end")
        try:
            has_sel = bool(lb.get("sel.first", "sel.last"))
        except tk.TclError:
            has_sel = False

        def copy(text, what):
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.flash_status(f"Copied {what}")
        if has_sel:
            m.add_command(label="Copy selection\tCtrl+C", command=self.activity_copy)
        if line:
            m.add_command(label="Copy this line", command=lambda: copy(line, "the line"))
        m.add_command(label="Copy everything shown",
                      command=lambda: copy(lb.get("1.0", "end-1c"), "everything shown"))
        m.add_command(label="Select all\tCtrl+A",
                      command=lambda: lb.tag_add("sel", "1.0", "end-1c"))
        job = self.job_in_line(line) if line else None
        if line and LOC_RE.search(line):
            m.add_separator()
            m.add_command(label="📍  Show this place on screen",
                          command=lambda: self.show_places(line, job_name=job))
        if job:
            m.add_separator()
            m.add_command(label=f"Filter to \u201c{short_title(job, 30)}\u201d",
                          command=lambda: self.act_filter.var.set(f"[{job}]"))
            j = next((x for x in self.jobs if x["name"] == job), None)
            if j:
                m.add_command(label="Edit this job…",
                              command=lambda: JobEditor(self, j, is_new=False))
                m.add_command(label="Select it in the job list",
                              command=lambda: self.select_job_row(j))
        m.add_separator()
        m.add_command(label="Filter…\tCtrl+F", command=self.act_filter.focus)
        if self.act_filter.query():
            m.add_command(label="Clear the filter", command=self.act_filter.clear)
        m.add_command(label="⟳ Refresh", command=self.refresh_activity)
        m.add_command(label="Show oldest first" if self.activity_newest_first() else
                      "Show newest first", command=self.toggle_activity_order)
        m.add_command(label="Save what's shown as a text file…", command=self.save_activity)
        m.add_command(label="Open the log file", command=self.open_log)
        m.add_command(label="Clear view (hide what's shown, for now)",
                      command=self.clear_activity)
        m.add_command(label="Delete the log file (for good)…",
                      command=self.delete_activity_log)
        self.theme_menu(m)
        lb.mark_set("insert", idx)
        m.tk_popup(e.x_root, e.y_root)
        return "break"

    def select_job_row(self, job):
        if self.v_filter.get() not in ("all", "watch" if is_watch(job) else "click"):
            self.v_filter.set("all")
            self.filter_changed()
        try:
            self.tree.selection_set(job["id"])
            self.tree.see(job["id"])
        except Exception:
            pass

    def save_activity(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".txt",
                                            filetypes=[("Text", "*.txt")],
                                            initialfile="clickue-activity.txt")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.logbox.get("1.0", "end-1c"))
            self.flash_status(f"Saved {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't save the file:\n{e}", parent=self.root)

    def load_activity_history(self):
        """Bring back the Activity of earlier runs from the log file (4.5.5): Activity is
        only emptied by Clear view, or at every start when Preferences → General → "Clear
        Activity when Clickue starts" is on."""
        if self.settings.get("activity_clear_on_start"):
            self.settings["activity_cleared_at"] = self.session_start
            return
        since = str(self.settings.get("activity_cleared_at") or "")
        lines = read_log_tail(MAX_UI_LOG_LINES)
        items = []
        for ts, msg in lines:
            if ts >= self.session_start or (since and ts <= since):
                continue
            tag, is_click, is_problem = self.classify(msg)
            items.append((ts, msg, tag, is_click, is_problem))
        if items:
            self.act_lines = items + self.act_lines
            self.render_activity()

    def render_activity(self):
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        newest = self.activity_newest_first()
        for item in (reversed(self.act_lines) if newest else self.act_lines):
            if self.activity_shows(item):
                self.insert_activity(item)
        self.logbox.see("1.0" if newest else "end")
        self.logbox.configure(state="disabled")

    def activity_newest_first(self):
        return (self.settings.get("log_order") or {}).get("activity") == "new"

    def set_activity_order_text(self):
        btn = getattr(self, "act_order_btn", None)
        if btn is not None:
            btn.configure(text="↓ Newest first" if self.activity_newest_first()
                          else "↑ Oldest first")

    def toggle_activity_order(self):
        orders = dict(self.settings.get("log_order") or {})
        orders["activity"] = "old" if self.activity_newest_first() else "new"
        self.settings["log_order"] = orders
        self.save()
        self.set_activity_order_text()
        self.render_activity()

    def refresh_activity(self):
        """Read Activity again from the log file (this run and earlier ones)."""
        since = str(self.settings.get("activity_cleared_at") or "")
        hide = getattr(self, "act_hidden_before", "")
        items = []
        for ts, msg in read_log_tail(MAX_UI_LOG_LINES):
            if (since and ts <= since) or (hide and ts <= hide):
                continue
            tag, is_click, is_problem = self.classify(msg)
            items.append((ts, msg, tag, is_click, is_problem))
        self.act_lines = items
        self.render_activity()
        self.flash_status("Activity refreshed")

    def delete_activity_log(self, confirm=True):
        """Delete the log file (and its older copies) for good, and empty Activity."""
        if confirm and not messagebox.askyesno(APP_NAME, "Delete the log file for good?\n\nActivity and "
                                             "every line in the log file (and its older "
                                             "copies) are removed. This can't be undone.",
                                   parent=self.root):
            return
        try:
            for h in list(self.logger.handlers):
                try:
                    h.acquire()
                    if getattr(h, "stream", None):
                        h.stream.seek(0)
                        h.stream.truncate()
                finally:
                    h.release()
            for k in (1, 2, 3):
                pth = f"{LOG_PATH}.{k}"
                if os.path.exists(pth):
                    os.remove(pth)
            if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH):
                with open(LOG_PATH, "w", encoding="utf-8"):
                    pass
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't delete the log file:\n{e}",
                                 parent=self.root)
            return
        self.act_lines = []
        self.act_hidden_before = ""
        self.render_activity()
        self.log("Log file deleted (by you)")

    def cancel_wtest(self, job):
        with self.lock:
            job["wtest_at"] = job["wtest_deadline"] = None
        self.log(f"[{job['name']}] pending watcher test cancelled")
        self.save()
        self.refresh_tree()

    def dry_run_for(self, job, parent=None):
        """Hide this app, then show the watched picture and the button it would click."""
        owner = parent or self.root
        if not job.get("watch_png"):
            messagebox.showinfo(APP_NAME, "Draw a box around the picture to watch first.",
                                parent=owner)
            return
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def run():
            similar = []
            r = self.watcher_dry_run(job, report=similar)
            text, level = self.describe_dry_run(r)
            self.log(f"[{job['name']}] DRY RUN: {text}")
            self.record_test(job["name"], "Dry run (no click)", text, level)
            if r["error"]:
                restore()
                messagebox.showwarning(APP_NAME, text, parent=owner)
                return
            found, px, py, score, sc = r["picture"]
            bok, bx, by, bmsg, bhow = r["button"]

            def step_button():
                if not bok:
                    restore()
                    messagebox.showwarning(APP_NAME, f"Dry run: {text.replace(' · ', chr(10))}",
                                           parent=owner)
                    return
                if IS_WIN:
                    user32.SetCursorPos(int(bx), int(by))
                cap = ("Would click here when the picture disappears" if found
                       else "Picture is missing - would click HERE now")
                self.flash_marker(bx, by, f"Step 2 of 2  ·  {cap}  ({bhow})", restore)

            how = "of it matches" if r.get("partial") else "match"
            if found:
                size = "" if not sc or abs(sc - 1) < 0.01 else f" at {sc:.0%} size"
                self.flash_marker(px, py, f"Step 1 of 2  ·  Watched picture found "
                                          f"({score:.0%} {how}{size}) - no click needed",
                                  step_button, seconds=4,
                                  others=similar if self.settings.get("show_similar") else None)
            elif similar:
                # show where the closest places were, so it's clear why it didn't count
                self.flash_marker(None, None, f"Step 1 of 2  ·  Watched picture NOT found - "
                                              f"closest places outlined (best {score:.0%} "
                                              f"{how})", step_button, seconds=4,
                                  others=similar)
            else:
                step_button()
        self.root.after(400, run)

    def filter_changed(self):
        self.settings["view_filter"] = self.v_filter.get()
        self.save()
        self._auto_w = {}
        self.refresh_tree(full=True)
        self.update_buttons()
        self.update_cards(time.time())

    def clear_activity(self):
        """Empty the Activity view for now (4.5.6: nothing is deleted; ⟳ Refresh and the next
        start bring the lines back; Delete log… removes them for good)."""
        self.act_hidden_before = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.act_lines = []
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        self.logbox.configure(state="disabled")

    def open_log(self):
        try:
            if IS_WIN and os.path.exists(LOG_PATH):
                os.startfile(LOG_PATH)
            elif IS_WIN:
                os.startfile(DATA_DIR)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e), parent=self.root)

    def _job_for_iid(self, iid):
        jid = iid.split(":")[1] if ":" in iid else iid
        with self.lock:
            return next((j for j in self.jobs if j["id"] == jid), None)

    # ------------------------------------------------------------ 4.5.3: tick boxes, batches
    def visible_job_ids(self):
        return [iid for iid in self.tree.get_children() if ":" not in iid]

    def checked_jobs(self):
        with self.lock:
            return [j for j in self.jobs if j["id"] in self.checked]

    def set_checks(self, ids):
        self.checked = set(ids)
        self.refresh_tree()

    def toggle_check(self, jid):
        if jid in self.checked:
            self.checked.discard(jid)
        else:
            self.checked.add(jid)
        self.refresh_tree()

    def toggle_check_all(self):
        vis = self.visible_job_ids()
        if vis and all(i in self.checked for i in vis):
            self.checked -= set(vis)
        else:
            self.checked |= set(vis)
        self.refresh_tree()

    def toggle_check_selected(self):
        sel = [i for i in self.tree.selection() if ":" not in i]
        for i in sel:
            self.toggle_check(i)

    def toggle_steps(self, jid, show=None):
        """Show or hide a job's steps as rows under it."""
        show = (jid not in self.expanded) if show is None else show
        if show:
            self.expanded.add(jid)
        else:
            self.expanded.discard(jid)
        self.refresh_tree()
        self.apply_view(force=True)

    def row_tip_text(self, x, y):
        """Hover text for a job-list row: everything about how the job is doing (4.5.6)."""
        iid = self.tree.identify_row(y)
        if not iid:
            return ""
        job = self._job_for_iid(iid)
        if not job:
            return ""
        return job_health(self, job, iid)

    def on_tree_click(self, event):
        """A click in the tick-box column ticks or unticks that job (or all, on the heading)."""
        try:
            col = self.tree.identify_column(event.x)
            region = self.tree.identify_region(event.x, event.y)
        except Exception:
            return None
        if region == "nothing" or (region in ("cell", "tree")
                                   and not self.tree.identify_row(event.y)):
            # a click on the empty part of the list: nothing selected any more (4.5.5)
            if self.tree.selection():
                self.tree.selection_remove(*self.tree.selection())
                self.tree.focus("")
                self.refresh_tree()
                self.update_buttons()
            return "break"
        iid0 = self.tree.identify_row(event.y)
        if iid0 and ":" not in iid0 and region == "cell":
            try:
                cols = list(self.tree["displaycolumns"])
                cname = cols[int(col.lstrip("#")) - 1]
            except Exception:
                cname = ""
            if cname == "name":
                bx = self.tree.bbox(iid0, "name")
                job = self._job_for_iid(iid0)
                if bx and job and job.get("steps") and event.x - bx[0] < 28:
                    self.toggle_steps(iid0)
                    return "break"
        if col != "#1" or region not in ("cell", "tree"):
            return None
        iid = self.tree.identify_row(event.y)
        if iid and ":" not in iid:
            self.toggle_check(iid)
            return "break"
        return None

    def build_batch_bar(self, main):
        """The bar that appears above the job list when jobs are ticked."""
        bar = ttk.Frame(main, style="Card.TFrame", padding=(10, 6))
        self.batch_bar = bar
        self.batch_lbl = ttk.Label(bar, style="CardSub.TLabel")
        self.batch_items = [self.batch_lbl]
        for text, cmd, style in (
                ("▶  Start", lambda: self.batch_action("start"), "Small.TButton"),
                ("■  Stop", lambda: self.batch_action("stop"), "Small.TButton"),
                ("⏸  Pause", lambda: self.batch_action("pause"), "Small.TButton"),
                ("▶  Resume", lambda: self.batch_action("resume"), "Small.TButton"),
                ("✎  Edit together…", self.batch_edit, "Small.TButton"),
                ("⧉  Duplicate", lambda: self.batch_action("duplicate"), "Small.TButton"),
                ("🗑  Delete…", self.batch_delete, "Small.TButton"),
                ("Tick all", lambda: self.set_checks(self.visible_job_ids()), "Small.TButton"),
                ("Clear", lambda: self.set_checks([]), "Small.TButton")):
            self.batch_items.append(ttk.Button(bar, text=text, style=style, command=cmd))
        bar.bind("<Configure>", lambda e: self.flow_batch_bar())
        self._batch_sig = None

    def flow_batch_bar(self, force=False):
        """Lay the batch bar out in rows: everything wraps instead of being cut off."""
        bar = self.batch_bar
        W = bar.winfo_width() - 20
        if W <= 1:
            return
        widths = [w.winfo_reqwidth() for w in self.batch_items]
        sig = (W, tuple(widths))
        if sig == self._batch_sig and not force:
            return
        self._batch_sig = sig
        rh = max(w.winfo_reqheight() for w in self.batch_items)
        x = y = 0
        for w, ww in zip(self.batch_items, widths):
            gap = 14 if w is self.batch_items[1] else 4
            if x and x + ww > W:
                x, y = 0, y + rh + 4
            elif x:
                x += gap
            w.place(x=x, y=y, height=rh)
            x += ww
        h = y + rh
        if int(str(bar.cget("height")) or 0) != h + 12:
            bar.configure(height=h + 12)

    def update_batch_bar(self):
        bar = getattr(self, "batch_bar", None)
        if bar is None:
            return
        vis = self.visible_job_ids()
        head = "☑" if vis and all(i in self.checked for i in vis) else "☐"
        if self.tree.heading("chk", "text") != head:
            self.tree.heading("chk", text=head)
        jobs = self.checked_jobs()
        if not jobs:
            if bar.winfo_ismapped():
                bar.pack_forget()
            return
        n = len(jobs)
        txt = f"{n} job{'s' if n != 1 else ''} ticked"
        if str(self.batch_lbl.cget("text")) != txt:
            self.batch_lbl.configure(text=txt)
            self._batch_sig = None
        if not bar.winfo_ismapped():
            bar.pack(fill="x", pady=(0, 6), before=self.paned)
            self.root.after_idle(lambda: self.flow_batch_bar(force=True))

    def batch_action(self, what, jobs=None):
        """Start / stop / pause / resume / duplicate every ticked job. Returns how many
        jobs changed."""
        jobs = self.checked_jobs() if jobs is None else jobs
        if not jobs:
            return 0
        now = time.time()
        done = 0
        new_ids = []
        with self.lock:
            for j in jobs:
                if what == "start" and not j.get("enabled"):
                    self.start_job(j)
                elif what == "stop" and j.get("enabled"):
                    self.stop_job(j)
                elif what == "pause" and j.get("enabled") and not j.get("paused"):
                    j["paused"] = True
                    j["pending_click_at"] = j["pending_since"] = None
                    self.wait_msgs.pop((j["id"], "watch"), None)
                    self.wait_msgs.pop((j["id"], "scheduled"), None)
                elif what == "resume" and j.get("enabled") and j.get("paused"):
                    j["paused"] = False
                    if is_watch(j):
                        j.update(next_check=now + 1, miss_count=0, watch_state="",
                                 watch_note="")
                    elif j.get("next_run") and j["next_run"] < now:
                        self.schedule_after_run(j, now)
                elif what == "duplicate":
                    d = self.copy_of(j)
                    self.jobs.append(d)
                    new_ids.append(d["id"])
                else:
                    continue
                done += 1
        verb = {"start": "started", "stop": "stopped", "pause": "paused",
                "resume": "resumed", "duplicate": "duplicated"}[what]
        skipped = len(jobs) - done
        why = {"start": "already running", "stop": "already stopped",
               "pause": "stopped or already paused", "resume": "not paused",
               "duplicate": ""}[what]
        self.log(f"Batch: {done} job{'s' if done != 1 else ''} {verb}"
                 + (f" ({skipped} skipped: {why})" if skipped and why else "")
                 + (": " + ", ".join(j["name"] for j in jobs[:8])
                    + ("…" if len(jobs) > 8 else "") if done else ""))
        if what == "duplicate" and new_ids:
            self.checked = set(new_ids)          # tick the copies, ready to edit together
        self.save()
        self.refresh_tree(full=what == "duplicate")
        self.update_buttons()
        return done

    def copy_of(self, j):
        """A stopped copy of a job with a new id (same as Duplicate)."""
        c = copy.deepcopy(j)
        c.update(id=uuid.uuid4().hex, name=(j["name"] + " (copy)")[:MAX_NAME], enabled=False,
                 paused=False, count=0, last_result="", last_run=None)
        for k in RUNTIME_KEYS:
            c[k] = None
        return c

    def batch_delete(self):
        jobs = self.checked_jobs()
        if not jobs:
            return
        names = "\n".join(f"  • {j['name']}" for j in jobs[:12]) + (
            f"\n  … and {len(jobs) - 12} more" if len(jobs) > 12 else "")
        if not messagebox.askyesno(APP_NAME, f"Delete these {len(jobs)} job"
                                             f"{'s' if len(jobs) != 1 else ''}?\n\n{names}"
                                             f"\n\n(You can undo this right after, with Undo "
                                             f"or Ctrl+Z.)", parent=self.root):
            return
        self.delete_jobs(jobs)

    def delete_jobs(self, jobs):
        """Delete several jobs at once; one Undo brings them all back."""
        entry = []
        with self.lock:
            for j in jobs:
                idx = next((i for i, x in enumerate(self.jobs) if x is j), None)
                if idx is None:
                    continue
                entry.append((j, idx, bool(j.get("enabled"))))
            ids = {id(j) for j, _, _ in entry}
            self.jobs = [x for x in self.jobs if id(x) not in ids]
            for j, _, _ in entry:
                self.stop_job(j)
        if not entry:
            return 0
        self.undo_stack.append(entry)
        del self.undo_stack[:-10]
        self.checked -= {j["id"] for j, _, _ in entry}
        self.log(f"Batch: deleted {len(entry)} job{'s' if len(entry) != 1 else ''}: "
                 + ", ".join(j["name"] for j, _, _ in entry[:8])
                 + ("…" if len(entry) > 8 else "") + " (Ctrl+Z to undo)")
        self.save()
        self.refresh_tree(full=True)
        self.show_undo_bar()
        self.update_buttons()
        return len(entry)

    def batch_edit(self):
        jobs = self.checked_jobs()
        if jobs:
            BatchEditDialog(self, jobs)

    def apply_batch_edit(self, jobs, changes):
        """Apply the same settings to several jobs. `changes` = {job key: value}; values are
        validated like an import. Settings that don't apply to a kind of job (a watcher's
        check interval for a scheduled click, say) are left alone. Running jobs pick up new
        timing straight away; paused jobs stay paused. Returns {job name: [keys changed]}."""
        clean = clean_batch_changes(changes)
        report = {}
        with self.lock:
            for j in jobs:
                if not self.find_job(j):
                    continue
                keys = [k for k in clean if batch_applies(k, j)]
                if not keys:
                    continue
                before = {k: j.get(k) for k in keys}
                for k in keys:
                    j[k] = copy.deepcopy(clean[k])
                for lo, hi in (("delay_min_s", "delay_max_s"),
                               ("watch_delay_min_s", "watch_delay_max_s")):
                    if lo in keys or hi in keys:
                        if int(j.get(lo, 0)) > int(j.get(hi, 0)):
                            if hi in keys and lo not in keys:
                                j[lo] = j[hi]
                            else:
                                j[hi] = j[lo]
                changed = [k for k in keys if before[k] != j.get(k)]
                if not changed:
                    continue
                report[j["name"]] = changed
                if j.get("enabled"):
                    paused = bool(j.get("paused"))
                    if is_watch(j) and any(k.startswith("watch_") for k in changed):
                        self.start_job(j)
                        j["paused"] = paused
                    elif not is_watch(j) and any(k in ("interval_s", "random_on", "delay_min_s",
                                                       "delay_max_s") for k in changed):
                        self.schedule_first(j)
        if report:
            self.log(f"Batch edit: changed {len(report)} job{'s' if len(report) != 1 else ''} "
                     f"({', '.join(sorted({BATCH_LABELS.get(k, k) for v in report.values() for k in v}))})")
        self.save()
        self.refresh_tree()
        self.update_buttons()
        return report

    def on_double(self, event=None):
        if event is not None and getattr(event, "num", None) == 1 and \
                getattr(event, "widget", None) is self.tree and \
                not self.tree.identify_row(event.y):
            return "break"            # double-click on the empty area: don't edit (4.5.5)
        if event is not None and getattr(event, "x", None) is not None and \
                self.tree.identify_column(event.x) == "#1" and \
                self.tree.identify_region(event.x, event.y) in ("cell", "tree"):
            return self.on_tree_click(event)      # a quick second click on a tick box
        sel = self.tree.selection()
        if not sel:
            return
        job = self._job_for_iid(sel[0])
        if job and sel[0].startswith("wtest:"):
            WatchTestDialog(self, job)
        elif job and sel[0].startswith("test:"):
            TestDialog(self, job)
        elif job:
            JobEditor(self, job, is_new=False)

    def on_right_click(self, event):
        iid = self.tree.identify_row(event.y)
        m = self.ctx
        m.delete(0, "end")
        if not iid:
            m.add_command(label="New click…", command=self.add_job)
            m.tk_popup(event.x_root, event.y_root)
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        job = self._job_for_iid(iid)
        if not job:
            return
        if job.get("steps") and not iid.startswith(("test:", "wtest:")):
            jid = job["id"]
            m.add_command(label="Hide its steps" if jid in self.expanded else
                          f"Show its {len(job['steps'])} steps",
                          command=lambda: self.toggle_steps(jid))
            m.add_separator()
        if iid.startswith("wtest:"):
            m.add_command(label="Change test time…",
                          command=lambda: WatchTestDialog(self, job))
            m.add_command(label="Cancel this test", command=lambda: self.cancel_wtest(job))
        elif iid.startswith("test:"):
            m.add_command(label="Change test time…", command=lambda: TestDialog(self, job))
            m.add_command(label="Cancel this test", command=lambda: self.cancel_test(job))
        else:
            m.add_command(label="Edit…", command=lambda: JobEditor(self, job, is_new=False))
            m.add_command(label="Stop" if job.get("enabled") else "Start",
                          command=self.toggle_job)
            if job.get("enabled"):
                m.add_command(label="Resume" if job.get("paused") else "Pause",
                              command=lambda: self.toggle_pause_job(job))
            m.add_separator()
            m.add_command(label="Test click now", command=self.test_click)
            m.add_command(label="Schedule test click…", command=lambda: TestDialog(self, job))
            m.add_command(label="Show spot on screen", command=self.show_position)
            if is_watch(job):
                m.add_command(label="Check watched picture now",
                              command=lambda: self.show_watch_for(job))
                m.add_command(label="Dry run (no click)", command=lambda: self.dry_run_for(job))
                m.add_command(label="Schedule watcher test…",
                              command=lambda: WatchTestDialog(self, job))
            m.add_command(label="Open Tests…", command=lambda: self.open_tests(job))
            m.add_command(label="Stats & click history…", command=lambda: StatsDialog(self, job))
            m.add_command(label="Run history…", command=lambda: self.open_run_history(job["name"]))
            if job.get("steps"):
                m.add_command(label="Dry run of its steps (no clicks)",
                              command=lambda: DryRunDialog(self, copy.deepcopy(job)))
            m.add_separator()
            m.add_command(label="Untick" if job["id"] in self.checked else "Tick (for batch "
                          "actions)", command=lambda: self.toggle_check(job["id"]))
            m.add_command(label="Duplicate", command=self.duplicate_job)
            m.add_command(label="Delete…", command=self.delete_job)
        m.tk_popup(event.x_root, event.y_root)

    def cancel_test(self, job):
        with self.lock:
            job["test_at"] = job["test_deadline"] = None
            self.wait_msgs.pop((job["id"], "test"), None)
        self.log(f"[{job['name']}] pending test click cancelled")
        self.save()
        self.refresh_tree()

    # ------------------------------------------------------------ tray / window
    # ---- 4.5.1: job status on the tray icon
    TRAY_TIP_MAX = 127          # Windows shows at most 127 characters in a tray tooltip
    TRAY_TIP_WIDTH = 36         # 4.6.1: and cuts lines wider than ~45 characters, so wrap
                                # (the first line, at most 38 characters, stays whole)

    def tray_wrap(self, text, width=None):
        """Wrap one tooltip entry onto lines of at most TRAY_TIP_WIDTH characters; follow-on
        lines are indented. Words longer than a line are split."""
        import textwrap
        return "\n".join(textwrap.wrap(text, width or self.TRAY_TIP_WIDTH, subsequent_indent="   ",
                                        break_long_words=True, break_on_hyphens=False)) or text

    def tray_status(self, now=None):
        """What the tray icon tells you when you hover over it.
        Returns (tooltip, lines): a short tooltip (fits Windows' 127-character limit), and
        one full line per active job for the tray menu's "Job status"."""
        now = now or time.time()
        with self.lock:
            rows = self.build_rows(now, flt="all")
            names = {j["id"]: j["name"] for j in self.jobs}
        try:
            running, waiting = self.queue_status()
        except Exception:
            running, waiting = "", []
        sev = {"bad": 0, "warn": 1, "running": 2, "paused": 3}
        icon = {"bad": "✖", "warn": "⚠", "running": "✓", "paused": "⏸"}
        items = []
        for iid, vals, state in rows:
            if iid.startswith(("test:", "wtest:", "step:")) or state == "stopped":
                continue
            status, name, _pos, _btn, _sched, nxt, cd, _count, last = vals
            word = status.split(maxsplit=1)[-1] if " " in status else status
            watcher_note = str(nxt).startswith(("Seen", "Not showing", "Picture", "Can't"))
            if state == "running" and str(cd) not in ("—", "") and not watcher_note:
                detail = f"next in {cd}"                 # live countdown (tooltip)
                at = f"next at {str(nxt)[-8:]}"          # clock time (menu: never goes stale)
            else:
                detail = at = str(nxt) if nxt not in ("—", "") else ""
                if watcher_note and str(cd).startswith("check in"):
                    detail = f"{nxt} · next {cd}"        # live countdown to the next check
            if status.startswith("⚡"):
                detail = at = f"{nxt} · {cd}"            # "Picture gone · click in 4m 59s"
            elif state == "bad" and last and last != "—":
                detail = at = str(last)
            items.append((sev.get(state, 2), names.get(iid, name), word, detail, state, at))
        items.sort(key=lambda t: t[0])
        paused = self.settings.get("paused")
        n = len(items)
        n_bad = sum(1 for t in items if t[4] in ("bad", "warn"))
        if not n:
            head = f"{APP_NAME}: no jobs running"
        elif paused:
            head = f"{APP_NAME}: ALL PAUSED ({n} job{'s' if n != 1 else ''})"
        else:
            head = (f"{APP_NAME}: {n} active · " +
                    ("all OK" if not n_bad else f"{n_bad} need{'s' if n_bad == 1 else ''} attention"))
        def say(word, det):
            if det and word.lower() in det.lower():
                return det                     # "Missing" + "Picture missing" -> one of them
            return f"{word} · {det}" if det else word
        lines = [f"{icon.get(st, '•')} {name}: {say(word, at)}"
                 for _, name, word, det, st, at in items]
        tip = self.tray_wrap(head, 40)    # at most 38 characters: kept on one line
        if running:
            tip += "\n▶ " + short_title(running, self.TRAY_TIP_WIDTH - 2)
        wrap = self.tray_wrap
        shown = 0
        for _, name, word, det, st, _at in items:
            text = say(word, det if st in ("bad", "warn", "running") else "")
            more = n - shown - 1
            tail = f"\n+{more} more (right-click → Job status)" if more else ""
            # 4.6.1: Windows cuts a tooltip line that is too wide (not only the whole text at
            # 127 characters), so each job is wrapped onto short lines that always fit.
            line = "\n" + wrap(f"{icon.get(st, '•')} {short_title(name, 24)}: {text}")
            if len(tip) + len(line) + len(tail) > self.TRAY_TIP_MAX:
                line = "\n" + wrap(f"{icon.get(st, '•')} {short_title(name, 16)}: "
                                   + short_title(text.replace("next check in", "check in"), 34))
            if len(tip) + len(line) + len(tail) > self.TRAY_TIP_MAX:
                rest = n - shown
                end = f"\n+{rest} more (right-click → Job status)"
                if len(tip) + len(end) <= self.TRAY_TIP_MAX:
                    tip += end
                break
            tip += line
            shown += 1
        if waiting:
            lines.append("Waiting their turn: " + ", ".join(waiting[:6]))
        if running:
            lines.insert(0, "▶ " + running)
        return tip[:self.TRAY_TIP_MAX], lines

    def tray_tick(self):
        """Keeps the tray tooltip's countdowns live: looks 4 times a second and changes the
        tooltip only when its text changes (so each second shows as it happens)."""
        try:
            self.update_tray_status()
        finally:
            try:
                self.root.after(250, self.tray_tick)
            except Exception:
                pass

    def update_tray_status(self):
        """Refresh the tray tooltip (live) and the Job status menu (at most every 5 s; its
        lines use clock times, so they don't go stale)."""
        if not self.tray:
            return
        now = time.time()
        try:
            if self.settings.get("tray_status", True):
                tip, lines = self.tray_status(now)
            else:
                tip, lines = APP_NAME, []
        except Exception:
            return
        try:
            badge = self.tray_badge(now) if self.settings.get("tray_colors", True) else None
            if badge != getattr(self, "_tray_badge", "x"):
                self._tray_badge = badge
                self.tray.icon = self.make_icon(badge)
        except Exception:
            pass
        try:
            if tip != getattr(self, "_tray_tip", None):
                self._tray_tip = tip
                self.tray.title = tip
            if lines != getattr(self, "_tray_lines", None) and \
                    now - getattr(self, "_tray_menu_upd", 0) >= 5:
                self._tray_lines = lines
                self._tray_menu_upd = now
                self.tray.update_menu()
        except Exception:
            pass

    def make_icon(self, badge=None):
        """The tray icon; `badge` adds a coloured dot (4.5.6): amber = a click is coming up,
        green = clicking right now, red = a job has a problem."""
        img = make_logo(64)
        if badge and HAVE_PIL:
            img = img.copy().convert("RGBA")
            col = {"due": (245, 165, 36), "clicking": (34, 197, 94), "issue": (239, 68, 68)}[badge]
            d = ImageDraw.Draw(img)
            d.ellipse((34, 34, 63, 63), fill=(255, 255, 255, 255))
            d.ellipse((38, 38, 59, 59), fill=col + (255,))
        return img

    def tray_badge(self, now=None):
        """Which colour the tray icon shows: "clicking" while a job is using the mouse,
        "due" while a click is counting down (a watcher's delay, or a scheduled click less
        than TRAY_DUE_S away), "issue" when a job has a problem, else None."""
        now = now or time.time()
        aq = getattr(self, "aq", None)
        if aq is not None and getattr(aq, "running", None):
            return "clicking"
        with self.lock:
            paused = self.settings.get("paused")
            jobs = [j for j in self.jobs if j.get("enabled") and not j.get("paused")]
            due = not paused and any(
                (j.get("pending_click_at") and j["pending_click_at"] - now < 3600) or
                (not is_watch(j) and j.get("next_run") and 0 <= j["next_run"] - now <= TRAY_DUE_S)
                for j in jobs)
            issue = any(j.get("watch_state") == "unknown" and
                        j.get("watch_note") != "outside active hours" for j in jobs if is_watch(j)) \
                or any(k[0] == j["id"] for k in self.wait_msgs for j in jobs) \
                or any(str(j.get("last_result", "")).startswith(("Missed", "Click FAILED",
                                                                  "Test FAILED"))
                       for j in jobs)
        return "due" if due else "issue" if issue else None

    def start_tray(self):
        if not HAVE_TRAY:
            return

        def status_items():
            lines = getattr(self, "_tray_lines", None) or ["No jobs running"]
            return [pystray.MenuItem(t, lambda icon, item: self.cmdq.put("show"))
                    for t in lines[:25]]

        def build(with_status):
            items = [pystray.MenuItem("Show window", lambda icon, item: self.cmdq.put("show"),
                                      default=True)]
            if with_status:
                items.append(pystray.MenuItem(
                    "Job status", pystray.Menu(status_items),
                    visible=lambda item: bool(self.settings.get("tray_status", True))))
            items += [pystray.MenuItem(
                          lambda item: "Resume all" if self.settings.get("paused") else "Pause all",
                          lambda icon, item: self.cmdq.put("pause")),
                      pystray.MenuItem("Stop everything now",
                                       lambda icon, item: self.emergency_stop()),
                      pystray.Menu.SEPARATOR,
                      pystray.MenuItem("Exit", lambda icon, item: self.cmdq.put("exit"))]
            return pystray.Menu(*items)

        for with_status in (True, False):       # never lose the tray icon over the status menu
            try:
                self.tray = pystray.Icon(APP_ID, self.icon_img, APP_NAME, build(with_status))
                self.tray.run_detached()
                return
            except Exception as e:
                try:
                    if self.tray:
                        self.tray.stop()
                except Exception:
                    pass
                self.tray = None
                err = e
        self.log(f"Tray icon unavailable: {err}")

    # ------------------------------------------------------------ hotkeys
    def start_hotkeys(self):
        self.stop_hotkeys()
        s = self.settings
        if not (IS_WIN and s.get("hotkeys_on")):
            return
        bindings = {}
        if s.get("hk_pause"):
            bindings[1] = (s["hk_pause"], "pause")
        if s.get("hk_show"):
            bindings[2] = (s["hk_show"], "toggle_window")
        if s.get("hk_stop"):
            bindings[3] = (s["hk_stop"], "stop_all")
        if s.get("hk_record"):
            bindings[4] = (s["hk_record"], "record")
        if s.get("hk_rec_pause"):
            bindings[5] = (s["hk_rec_pause"], "rec_pause")
        if not bindings:
            return
        self.hk_thread = HotkeyThread(bindings, self.cmdq.put,
                                      lambda m: self.log(f"Hotkey not available: {m}"))
        self.hk_thread.start()
        self.hk_thread.ready.wait(1.0)

    def stop_hotkeys(self):
        t = getattr(self, "hk_thread", None)
        if t is not None:
            try:
                t.stop()
                t.join(1.0)
            except Exception:
                pass
        self.hk_thread = None

    # ------------------------------------------------------------ backups
    def backup_check(self):
        """Once a day: save a backup of all jobs and settings (keeps the newest N)."""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            if self.settings.get("backups_on", True) and self.settings.get("last_backup") != today:
                with self.lock:
                    jobs, settings = copy.deepcopy(self.jobs), dict(self.settings)
                    groups = copy.deepcopy(getattr(self, "groups", []))
                make_backup(jobs, settings, "auto", groups)
                prune_backups(self.settings.get("backups_keep", 14))
                self.settings["last_backup"] = today
                self.save()
                self.log("Daily backup saved")
        except Exception as e:
            self.log(f"Backup failed: {e}")
        if not self.stop.is_set():
            self.root.after(15 * 60 * 1000, self.backup_check)

    def backup_now(self, tag="manual"):
        with self.lock:
            jobs, settings = copy.deepcopy(self.jobs), dict(self.settings)
            groups = copy.deepcopy(getattr(self, "groups", []))
        path = make_backup(jobs, settings, tag, groups)
        self.log(f"Backup saved: {os.path.basename(path)}")
        return path

    def restore_backup(self, path, replace=True):
        jobs, groups, problems = load_import_file(path)
        self.backup_now("before-restore")
        new = []
        for b in jobs:
            b["id"] = uuid.uuid4().hex
            for k in RUNTIME_KEYS:
                b[k] = new_job().get(k)
            new.append(b)
        with self.lock:
            have = {g.get("id") for g in self.groups}
            self.groups.extend(g for g in groups if g["id"] not in have)
            if replace:
                for j in self.jobs:
                    self.stop_job(j)
                self.jobs = new
            else:
                self.jobs.extend(new)
            for b in new:
                if b.get("enabled"):
                    self.start_job(b)
        self.save()
        self.refresh_tree(full=True)
        self.log(f"Restored {len(new)} job(s) from {os.path.basename(path)}"
                 + (f" ({len(problems)} problem(s) fixed or left out)" if problems else ""))
        return len(new)

    # ------------------------------------------------------------ undo delete
    def undo_delete(self, event=None):
        if not self.undo_stack:
            return
        entry = self.undo_stack.pop()
        items = entry if isinstance(entry, list) else [entry]
        with self.lock:
            for job, idx, was_on in sorted(items, key=lambda t: t[1]):
                self.jobs.insert(min(idx, len(self.jobs)), job)
                if was_on:
                    self.start_job(job)
        for job, _, _ in items:
            self.log(f"[{job['name']}] restored (undo)")
        self.save()
        self.refresh_tree(full=True)
        try:
            self.tree.selection_set(job["id"])
        except Exception:
            pass
        self.show_undo_bar()

    def show_undo_bar(self):
        bar = getattr(self, "undo_bar", None)
        if bar is None:
            return
        if self.undo_stack:
            last = self.undo_stack[-1]
            if isinstance(last, list) and len(last) > 1:
                self.undo_lbl.configure(text=f"Deleted {len(last)} jobs.")
            else:
                job = (last[0] if isinstance(last, list) else last)[0]
                self.undo_lbl.configure(text=f"Deleted \u201c{job['name']}\u201d.")
            if not bar.winfo_ismapped():
                bar.pack(fill="x", pady=(0, 6), before=self.paned)
            if getattr(self, "_undo_job", None):
                self.root.after_cancel(self._undo_job)
            self._undo_job = self.root.after(20000, lambda: bar.pack_forget())
        else:
            bar.pack_forget()

    def poll_cmds(self):
        while True:
            try:
                cmd = self.cmdq.get_nowait()
            except queue.Empty:
                break
            if callable(cmd):
                try:
                    cmd()
                except Exception as e:
                    self.log(f"UI error: {e}")
                continue
            if cmd == "show":
                self.show_window()
            elif cmd == "stop_all":
                self.emergency_stop()
            elif cmd == "record":
                self.toggle_recording()
            elif cmd == "rec_pause":
                self.toggle_recording_pause()
            elif cmd == "pause":
                self.toggle_pause_all()
            elif cmd == "toggle_window":
                if self.main_visible():
                    self.hide_window()
                else:
                    self.show_window()
            elif cmd == "exit":
                self.quit_app()
                return
        self.root.after(200, self.poll_cmds)

    def main_visible(self):
        try:
            return self.root.state() in ("normal", "zoomed")
        except Exception:
            return False

    def restore_main(self):
        """Bring the main window back exactly as it was (size, position, maximized)."""
        self.root.deiconify()
        if self.settings.get("main_zoomed"):
            self.root.state("zoomed")
        else:
            self.root.state("normal")
            g = fit_geometry(self.settings.get("main_geom"), 640, 600)
            if g:
                self.root.geometry(g)

    def show_window(self):
        self.restore_main()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def on_root_configure(self, event):
        if event.widget is not self.root:
            return
        if self._geom_job:
            self.root.after_cancel(self._geom_job)
        self._geom_job = self.root.after(400, self.remember_geometry)

    def remember_geometry(self):
        """Save the main window's size/position (only while it's a normal window)."""
        self._geom_job = None
        try:
            st = self.root.state()
        except Exception:
            return
        changed = False
        if st == "zoomed" and not self.settings.get("main_zoomed"):
            self.settings["main_zoomed"] = changed = True
        elif st == "normal":
            g = self.root.geometry()
            if self.settings.get("main_zoomed") or g != self.settings.get("main_geom"):
                self.settings["main_zoomed"] = False
                self.settings["main_geom"] = g
                changed = True
        if changed:
            self.save()

    def hide_window(self):
        if self.tray and self.settings.get("minimize_to_tray"):
            self.root.withdraw()
        else:
            self.root.iconify()

    def on_unmap(self, event):
        if (event.widget is self.root and self.tray and self.settings.get("minimize_to_tray")
                and self.root.state() == "iconic"):
            self.root.after(0, self.root.withdraw)

    def on_close(self):
        if self.tray and self.settings.get("close_to_tray"):
            self.root.withdraw()
            if not self.settings.get("tray_hint_shown"):
                self.settings["tray_hint_shown"] = True
                self.save()
                self.notify("Still running in the tray. Right-click the icon to exit.")
            return
        with self.lock:
            running = any(j.get("enabled") for j in self.jobs)
        if running and not messagebox.askyesno(
                APP_NAME, "Exiting stops all scheduled clicks until you open this again.\n"
                          "(Minimize instead to keep it running.)\n\nExit anyway?"):
            return
        self.quit_app()

    # ------------------------------------------------------------ 4.6: updates
    def open_url(self, url):
        if url and url.startswith(("https://github.com/", REPO_URL)):
            import webbrowser
            webbrowser.open(url)

    def auto_update_check(self):
        """Look for a new version at most once a day, in the background, only while
        Preferences → General → "Check for new versions" is on."""
        try:
            if self.settings.get("update_check", True) and \
                    time.time() - float(self.settings.get("update_last_check") or 0) >= UPDATE_EVERY_S:
                self.check_for_updates(manual=False)
            elif self.settings.get("update_check", True) and self.settings.get("update_known"):
                self.show_update_bar(self.settings["update_known"])
        finally:
            self.root.after(3600 * 1000, self.auto_update_check)

    def check_for_updates(self, manual=True, parent=None):
        """Ask GitHub for the newest release (in the background). With checks turned off,
        nothing is sent anywhere."""
        if not self.settings.get("update_check", True):
            if manual:
                if messagebox.askyesno(APP_NAME, "Checking for new versions is turned off, so "
                                                 "Clickue doesn't connect to the internet for "
                                                 "it.\n\nOpen Preferences to turn it on?",
                                       parent=parent or self.root):
                    self.open_settings()
            return
        if getattr(self, "_update_busy", False):
            return
        self._update_busy = True
        if manual:
            self.flash_status("Looking for a new version…")

        def work():
            try:
                info, err = fetch_latest_release(), ""
            except Exception as e:
                info, err = None, friendly_net_error(e)
            self.cmdq.put(lambda: done(info, err))

        def done(info, err):
            self._update_busy = False
            self.settings["update_last_check"] = time.time()
            if err:
                self.log(f"Couldn't check for a new version: {err}")
                if manual:
                    messagebox.showwarning(APP_NAME, f"Couldn't check for a new version:\n{err}",
                                           parent=parent or self.root)
                self.save()
                return
            if newer_version(info["version"]):
                self.settings["update_known"] = {k: info[k] for k in
                                                 ("version", "name", "page", "assets", "notes")}
                self.log(f"Clickue {info['version']} is available (you have {VERSION})")
                self.save()
                self.show_update_bar(info, force=manual)
                if manual:
                    self.upgrade_now()
            else:
                self.settings["update_known"] = None
                self.save()
                if manual:
                    messagebox.showinfo(APP_NAME, f"You have the newest version ({VERSION}).",
                                        parent=parent or self.root)
        threading.Thread(target=work, daemon=True).start()

    def show_update_bar(self, info, force=False):
        if not info or not newer_version(info.get("version")):
            return
        self.update_info = info
        v = info["version"]
        if not force and (self.settings.get("update_skip") == v or
                          time.time() < float(self.settings.get("update_later_until") or 0)):
            return
        self.update_lbl.configure(text=f"⬆  Clickue {v} is available (you have {VERSION}). "
                                       f"Upgrading keeps your jobs and settings.")
        if not self.update_bar.winfo_ismapped():
            self.update_bar.pack(fill="x", pady=(0, 6), before=self.paned)
        if getattr(self, "_update_notified", "") != v:
            self._update_notified = v
            self.notify(f"Clickue {v} is available. Open Clickue to upgrade.", "info")

    def update_later(self, hours=24):
        self.settings["update_later_until"] = time.time() + hours * 3600
        self.save()
        self.update_bar.pack_forget()

    def update_skip(self):
        if self.update_info:
            self.settings["update_skip"] = self.update_info["version"]
            self.save()
            self.log(f"Version {self.update_info['version']} skipped (no reminders for it)")
        self.update_bar.pack_forget()

    def upgrade_now(self):
        info = self.update_info or self.settings.get("update_known")
        if not info:
            self.check_for_updates(manual=True)
            return
        UpgradeDialog(self, info)

    def finish_upgrade(self, info, kind, path):
        """Downloaded and checked: back up, remember the upgrade, start the new version, exit.
        Jobs and settings stay in the data folder, which the new version uses as is."""
        v = info["version"]
        self.save()
        try:
            make_backup(self.jobs, self.settings, f"before-upgrade-{v}", self.groups)
        except Exception as e:
            self.log(f"Backup before the upgrade failed: {e}")
        self.settings["upgrade_pending"] = v
        self.settings["upgrade_from"] = VERSION
        self.save()
        self.log(f"Upgrading to Clickue {v} ({kind}) - Clickue closes and starts again")
        import subprocess
        try:
            if kind == "installer":
                args = [path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                        "/CLOSEAPPLICATIONS", "/RELAUNCH"]
                pf = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)")]
                args.append("/ALLUSERS" if any(p_ and os.path.normcase(PROGRAM_DIR).startswith(
                    os.path.normcase(p_)) for p_ in pf) else "/CURRENTUSER")
                subprocess.Popen(args, close_fds=True)  # noqa: S603 - fixed arguments
            else:
                new = extract_portable_exe(path, PROGRAM_DIR)
                cur = PROGRAM_PATH
                old = os.path.join(PROGRAM_DIR, "Clickue.old.exe")
                if os.path.exists(old):
                    os.remove(old)
                os.replace(cur, old)                    # a running exe can be renamed
                os.replace(new, cur)
                subprocess.Popen([cur], close_fds=True)  # noqa: S603 - our own new exe
        except Exception as e:
            self.settings["upgrade_pending"] = ""
            self.save()
            messagebox.showerror(APP_NAME, f"The upgrade couldn't start:\n{e}\n\nNothing was "
                                           f"changed; Clickue keeps running.", parent=self.root)
            return
        self.root.after(800, self.quit_app)

    def after_upgrade(self):
        """At start: finish an in-app upgrade (note it, tidy up the old program file)."""
        want = self.settings.get("upgrade_pending")
        old = os.path.join(PROGRAM_DIR, "Clickue.old.exe")
        if FROZEN and os.path.exists(old):
            self.root.after(5000, lambda: os.path.exists(old) and _try_remove(old))
        if not want:
            return
        if parse_version(VERSION) and parse_version(VERSION) >= (parse_version(want) or (0,)):
            self.log(f"Upgraded from Clickue {self.settings.get('upgrade_from') or '?'} to "
                     f"{VERSION}. Your jobs and settings were kept (backup "
                     f"before-upgrade-{want} in ☰ Menu → Backups).")
            self.settings["update_known"] = None
            self.update_bar.pack_forget()
        else:
            self.log(f"The upgrade to {want} didn't finish; still running {VERSION}. Try "
                     f"again from ☰ Menu → Check for updates, or install it from the release "
                     f"page.")
        self.settings["upgrade_pending"] = ""
        self.save()

    def quit_app(self):
        try:
            self.remember_geometry()
        except Exception:
            pass
        self.emergency_stop_quiet()
        self.stop_hotkeys()
        self.stop.set()
        keep_awake(False)
        self.save()
        self.log("Exited.")
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.close_logging()
        self.root.destroy()

    # ------------------------------------------------------------ job actions
    def bump_stats(self, key, watch=False):
        """Count today's clicks / missed clicks (all jobs, and watchers separately, 4.5.6)."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.settings.get("stats_date") != today:
            self.settings.update(stats_date=today, stats_clicks=0, stats_missed=0,
                                 stats_clicks_watch=0, stats_missed_watch=0)
        self.settings[key] = int(self.settings.get(key, 0)) + 1
        if watch:
            self.settings[key + "_watch"] = int(self.settings.get(key + "_watch", 0)) + 1

    def selected_job(self):
        """The selected job (a test row counts as its job)."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a click job in the list first.",
                                parent=self.root)
            return None
        return self._job_for_iid(sel[0])

    def selected_is_test(self):
        sel = self.tree.selection()
        return bool(sel) and sel[0].startswith(("test:", "wtest:"))

    def add_job(self):
        with self.lock:
            n = len(self.jobs) + 1
        JobEditor(self, new_job(n), is_new=True)

    def add_watcher(self):
        with self.lock:
            n = sum(1 for j in self.jobs if is_watch(j)) + 1
        w = new_watch(n)
        w["watch_interval_s"] = int(self.settings.get("default_watch_interval", 30))
        w["watch_confirm"] = int(self.settings.get("default_watch_confirm", 2))
        JobEditor(self, w, is_new=True)

    # ------------------------------------------------------------ 4.5: windows, recording, debug
    def hide_all_windows(self, keep=None):
        """Hide every visible Clickue window (except `keep`). Returns restore()."""
        tops = [self.root] + [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)
                              and w is not keep]
        try:
            front = self.root.focus_get()
            front = front.winfo_toplevel() if front is not None else None
        except Exception:
            front = None
        saved = self.hide_windows(tops)
        self._spot_busy = True
        if front is None or front is self.root or front is keep:
            front = next((w for w, _, _ in reversed(saved) if w is not self.root), None)

        def restore():
            self.show_windows(saved, focus=front)
            self.root.after(900, lambda: setattr(self, "_spot_busy", False))
        return restore

    def warn_conflicts(self, job):
        if not (self.settings.get("warn_conflicts", True) and job.get("enabled")):
            return
        with self.lock:
            found = find_conflicts(self.jobs, job)
        if not found:
            return
        a, b, why = found[0]
        more = f" (and {len(found) - 1} more)" if len(found) > 1 else ""
        msg = (f"Heads-up: “{a}” and “{b}” {why}{more}.\n\nThey never click at the same "
               f"time (one job uses the mouse at a time), but one may change what the other "
               f"expects to see. If that's a problem, give them different times, or combine "
               f"them into one job with steps.")
        self.log(f"Note: “{a}” and “{b}” {why} - they take turns")
        messagebox.showinfo(APP_NAME, msg, parent=self.root)

    # ---- step through (debugger)
    def start_debug(self, job, parent=None):
        self.ensure_runtime()
        if not self.aq.active:
            return
        restore = self.hide_all_windows()
        win = DebugWindow(self, job, on_close=restore)
        dbg = StepDebugger(self, win)
        win.dbg = dbg
        snap = copy.deepcopy(job)

        def run():
            ok, msg, *_ = self.perform(snap, check_idle=False, debugger=dbg)
            self.cmdq.put(lambda: win.finished(ok, msg))
            return ok
        it = self.aq.put(snap, "debug", priority="high", fn=run,
                         label=f"{job.get('name', '')} (step through)")
        if it is None:
            win.finished(False, "this job is already running or waiting")

    # ---- recording macros
    def toggle_recording(self, from_hotkey=True):
        if getattr(self, "recorder", None) is not None:
            self.stop_recording()
        elif from_hotkey:
            s = self.settings
            self.start_recording(dict(moves=s.get("rec_moves", True),
                                      pictures=s.get("rec_pictures", True),
                                      timing=s.get("rec_timing", True)),
                                 "", pause_jobs=True, countdown=0)
        else:
            RecordDialog(self)

    def toggle_recording_pause(self):
        rec = getattr(self, "recorder", None)
        if rec is None:
            return
        if rec.state == "paused":
            rec.resume()
            self.log("Recording resumed")
        else:
            rec.pause()
            self.log("Recording paused")

    def start_recording(self, opts, name, pause_jobs=True, countdown=0):
        self.ensure_runtime()
        if self.recorder is not None:
            return
        if not IS_WIN:
            messagebox.showinfo(APP_NAME, "Recording macros only works on Windows.",
                                parent=self.root)
            return
        if self.aq.running:
            messagebox.showinfo(APP_NAME, f"“{self.aq.running['label']}” is running right now. "
                                          f"Wait for it to finish (or stop it), then record.",
                                parent=self.root)
            return
        self._rec_name = name
        self._rec_unpause = pause_jobs and not self.settings.get("paused")
        if self._rec_unpause:
            self.settings["paused"] = True
        rec = MacroRecorder(opts, on_limit=lambda: self.cmdq.put(self.stop_recording))
        self._rec_restore = self.hide_all_windows()
        ind = RecordingIndicator(self)
        self.rec_window = ind
        self.recorder = rec

        def begin(n):
            if self.recorder is not rec:
                return
            if n > 0:
                ind.lbl.configure(text=f"Recording starts in {n}…")
                self.root.after(1000, lambda: begin(n - 1))
                return
            rec.exclude.append(ind.rect())
            if not rec.start():
                err = rec.error
                self.recorder = None
                self._end_recording_ui()
                messagebox.showerror(APP_NAME, f"Couldn't start recording:\n{err}",
                                     parent=self.root)
                return
            self.log("Recording a macro (Clickue's own windows and clicks are not recorded)")
        begin(countdown)

    def _end_recording_ui(self):
        if self.rec_window is not None:
            try:
                self.rec_window.destroy()
            except Exception:
                pass
            self.rec_window = None
        if getattr(self, "_rec_unpause", False):
            self.settings["paused"] = False
            self._rec_unpause = False
        restore = getattr(self, "_rec_restore", None)
        self._rec_restore = None
        if restore:
            restore()

    def stop_recording(self, save=True):
        rec = getattr(self, "recorder", None)
        if rec is None:
            return
        self.recorder = None
        if not save:
            rec.cancel()
            self._end_recording_ui()
            self.log("Recording thrown away")
            return
        try:
            steps = rec.stop() if rec.state != "idle" else []
        except Exception as e:
            steps = []
            self.log(f"Recording failed: {e}")
        self._end_recording_ui()
        if not steps:
            messagebox.showinfo(APP_NAME, "Nothing was recorded.", parent=self.root)
            return
        with self.lock:
            n = sum(1 for j in self.jobs if j.get("name", "").startswith("Recorded macro")) + 1
        job = new_job(n)
        job.update(name=self._rec_name or f"Recorded macro {n}", main_click=False, steps=steps,
                   use_image=False, interval_s=8 * 3600,
                   human_move=True if self.settings.get("rec_human") else None)
        self.log(f"Recorded {len(steps)} steps. Check them, then save the job.")
        self.show_window()
        JobEditor(self, job, is_new=True, start_on=False)

    def show_video_bar(self, name, video):
        """A small red bar at the top of the screen while a run's video is recorded."""
        self.hide_video_bar()
        bar = tk.Toplevel(self.root)
        bar.overrideredirect(True)
        bar.attributes("-topmost", True)
        bg = "#7f1d1d"
        bar.configure(bg=bg)
        lbl = tk.Label(bar, text=f"● Recording the screen: {short_title(name, 30)}", bg=bg,
                       fg="#ffffff", font=(self.font_family, 9, "bold"), padx=8, pady=3)
        lbl.pack(side="left")

        def toggle():
            video.paused = not video.paused
            pb.configure(text="Resume video" if video.paused else "Pause video")
            lbl.configure(text=("⏸ Video paused: " if video.paused else "● Recording the screen: ")
                          + short_title(name, 30))
        pb = tk.Button(bar, text="Pause video", command=toggle, relief="flat", bg="#991b1b",
                       fg="#ffffff", bd=0, padx=6, font=(self.font_family, 8))
        pb.pack(side="left", padx=2, pady=2)
        tk.Button(bar, text="Stop video", command=lambda: (video.stop(), self.hide_video_bar()),
                  relief="flat", bg="#991b1b", fg="#ffffff", bd=0, padx=6,
                  font=(self.font_family, 8)).pack(side="left", padx=(2, 4), pady=2)
        bar.update_idletasks()
        sw = bar.winfo_screenwidth()
        bar.geometry(f"+{max(0, (sw - bar.winfo_reqwidth()) // 2)}+0")
        self.video_bar = bar

    def hide_video_bar(self):
        b = getattr(self, "video_bar", None)
        self.video_bar = None
        if b is not None:
            try:
                b.destroy()
            except Exception:
                pass

    def open_run_history(self, job_name=None):
        RunHistoryDialog(self, job_name)

    def open_groups(self):
        GroupsDialog(self)

    # ------------------------------------------------------------ ☰ menu
    def show_main_menu(self):
        m = self.main_menu
        m.delete(0, "end")
        m.add_command(label="New click…", accelerator="Ctrl+N", command=self.add_job)
        m.add_command(label="New watcher…", accelerator="Ctrl+Shift+N", command=self.add_watcher)
        m.add_command(label="Tests…", accelerator="Ctrl+T", command=self.open_tests)
        m.add_command(label="Record a macro…", accelerator=self.settings.get("hk_record") or "",
                      command=lambda: self.toggle_recording(from_hotkey=False))
        m.add_command(label="Step groups…", command=self.open_groups)
        m.add_command(label="Run history & videos…", command=self.open_run_history)
        m.add_command(label="Stop everything now", accelerator=self.settings.get("hk_stop") or "",
                      command=self.emergency_stop)
        m.add_separator()
        m.add_command(label="Undo delete", accelerator="Ctrl+Z", command=self.undo_delete,
                      state="normal" if self.undo_stack else "disabled")
        m.add_command(label="Import jobs…", command=self.import_jobs)
        m.add_command(label="Export jobs…", command=self.export_jobs)
        m.add_command(label="Backups…", command=lambda: BackupsDialog(self))
        m.add_command(label="Export click history (CSV)…", command=self.export_history)
        m.add_separator()
        m.add_command(label="Reset column widths", command=self.reset_col_widths,
                      state="normal" if self.settings.get("col_widths") else "disabled")
        m.add_command(label="Preferences…", accelerator="Ctrl+,", command=self.open_settings)
        m.add_command(label="Open data folder", command=self.open_data_folder)
        m.add_command(label="Open log file", command=self.open_log)
        m.add_command(label="Delete logs and history…", command=lambda: DeleteLogsDialog(self))
        m.add_separator()
        m.add_command(label="Check for updates…", command=lambda: self.check_for_updates(True))
        m.add_command(label="Complete guide (online)", command=self.open_guide)
        m.add_command(label="Help & shortcuts", command=lambda: HelpDialog(self))
        m.add_command(label=f"About {APP_NAME}", command=lambda: AboutDialog(self))
        m.add_separator()
        m.add_command(label="Uninstall…", command=lambda: self.uninstall(self.root))
        m.add_command(label="Exit", command=self.quit_app)
        b = self.menu_btn
        m.tk_popup(b.winfo_rootx() + b.winfo_width() - 240, b.winfo_rooty() + b.winfo_height() + 2)

    def open_guide(self):
        """Open the complete guide on GitHub in the default browser."""
        try:
            webbrowser.open(GUIDE_URL, new=2)
            self.log("Opened the complete guide in your browser")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't open the browser:\n{e}\n\n"
                                           f"The guide is at:\n{GUIDE_URL}", parent=self.root)

    def open_data_folder(self):
        try:
            if IS_WIN:
                os.startfile(DATA_DIR)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e), parent=self.root)

    def export_history(self, job_name=None, parent=None):
        rows = read_history()
        if job_name:
            rows = [r for r in rows if r.get("job") == job_name]
        if not rows:
            messagebox.showinfo(APP_NAME, "There's no click history yet.", parent=parent or self.root)
            return
        safe = "".join(c for c in (job_name or "all jobs") if c.isalnum() or c in " -_")
        path = filedialog.asksaveasfilename(
            parent=parent or self.root, title="Export click history",
            defaultextension=".csv",
            initialfile=f"Clickue history {safe} {datetime.now():%Y-%m-%d}.csv",
            filetypes=[("CSV (Excel, Google Sheets)", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        import csv
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't save:\n{e}", parent=parent or self.root)
            return
        self.log(f"Exported {len(rows)} history rows to {path}")
        messagebox.showinfo(APP_NAME, f"Saved {len(rows)} rows to:\n{path}",
                            parent=parent or self.root)

    def pick_countdown(self, on_point, on_cancel=None, seconds=5):
        """The "Point at the spot" countdown box. After `seconds`, calls on_point(x, y) with
        the mouse position. Esc (from any window) or the box's Cancel button calls
        on_cancel() instead. The box moves aside when the mouse rests near it, can be
        dragged, and never moves away while the mouse is on its Cancel button."""
        bg, fg, mute = "#1f2937", "#ffffff", "#9ca3af"
        cd = tk.Toplevel(self.root, bg=bg, highlightthickness=1,
                         highlightbackground="#3b82f6", highlightcolor="#3b82f6")
        cd.overrideredirect(True)
        cd.attributes("-topmost", True)
        top = tk.Frame(cd, bg=bg)
        top.pack(fill="x")
        lbl = tk.Label(top, font=(self.font_family, 13, "bold"), bg=bg, fg=fg, padx=20,
                       pady=10, justify="left", anchor="w", cursor="fleur", bd=0)
        lbl.pack(side="left", fill="x", expand=True)
        cancel = tk.Label(top, text="✕  Cancel (Esc)", font=(self.font_family, 10, "bold"),
                          bg="#374151", fg=fg, padx=12, pady=6, cursor="hand2", bd=0)
        cancel.pack(side="right", padx=(0, 12), pady=8)
        tip = tk.Label(cd, font=(self.font_family, 9), bg=bg, fg=mute, padx=20,
                       justify="left", anchor="w", cursor="fleur", bd=0,
                       text="Drag this box to move it (the countdown waits while you drag).\n"
                            "It moves aside if your mouse rests near it. Esc cancels.")
        tip.pack(fill="x", pady=(0, 10))
        st = {"drag": None, "moved": False, "done": False, "near_since": None}
        vx, vy, vw, vh = virtual_screen()
        cd.geometry(f"+{vx + 20}+{vy + 20}")

        def over_cancel():
            try:
                mx, my = get_cursor() if IS_WIN else cd.winfo_pointerxy()
                return (cancel.winfo_rootx() <= mx <= cancel.winfo_rootx() + cancel.winfo_width()
                        and cancel.winfo_rooty() <= my <= cancel.winfo_rooty()
                        + cancel.winfo_height())
            except Exception:
                return False

        def finish(kind, x=0, y=0):
            if st["done"]:
                return
            st["done"] = True
            try:
                cd.destroy()
            except Exception:
                pass
            if kind == "cancel":
                self.log("Pick cancelled")
                if on_cancel:
                    self.root.after(50, on_cancel)
            else:
                self.root.after(250, lambda: on_point(x, y))

        cancel.bind("<Button-1>", lambda e: finish("cancel"))
        cancel.bind("<Enter>", lambda e: cancel.configure(bg="#dc2626"))
        cancel.bind("<Leave>", lambda e: cancel.configure(bg="#374151"))
        cd.bind("<Escape>", lambda e: finish("cancel"))
        cd.bind("<Button-3>", lambda e: finish("cancel"))

        def press(e):
            st["drag"] = (e.x_root - cd.winfo_rootx(), e.y_root - cd.winfo_rooty())

        def motion(e):
            if st["drag"]:
                cd.geometry(f"+{e.x_root - st['drag'][0]}+{e.y_root - st['drag'][1]}")

        def release(e):
            st["drag"], st["moved"] = None, True

        for wdg in (lbl, tip, top):
            wdg.bind("<ButtonPress-1>", press)
            wdg.bind("<B1-Motion>", motion)
            wdg.bind("<ButtonRelease-1>", release)

        def watch():
            """Esc from anywhere; move aside when the mouse rests near the box."""
            if st["done"]:
                return
            if key_down(VK_ESCAPE):
                finish("cancel")
                return
            if not st["drag"] and not st["moved"] and not over_cancel():
                try:
                    mx, my = get_cursor()
                    bx, by, bw, bh = cd.winfo_rootx(), cd.winfo_rooty(), cd.winfo_width(), \
                        cd.winfo_height()
                    if bx - 30 <= mx <= bx + bw + 30 and by - 30 <= my <= by + bh + 30:
                        st["near_since"] = st["near_since"] or time.time()
                        if time.time() - st["near_since"] >= 0.6:
                            corners = [(vx + 20, vy + 20), (vx + vw - bw - 20, vy + 20),
                                       (vx + 20, vy + vh - bh - 60),
                                       (vx + vw - bw - 20, vy + vh - bh - 60)]
                            c = max(corners, key=lambda c: (c[0] + bw / 2 - mx) ** 2 +
                                    (c[1] + bh / 2 - my) ** 2)
                            cd.geometry(f"+{int(c[0])}+{int(c[1])}")
                            st["near_since"] = None
                    else:
                        st["near_since"] = None
                except Exception:
                    pass
            cd.after(80, watch)

        def step(n):
            if st["done"]:
                return
            if st["drag"] or over_cancel():     # wait while dragging or about to cancel
                cd.after(200, step, n)
                return
            if n > 0:
                x, y = get_cursor()
                lbl.configure(text=f"Point at the spot to click…\nCapturing in {n}    ({x}, {y})")
                cd.after(1000, step, n - 1)
                return
            x, y = get_cursor()
            finish("point", x, y)

        try:
            cd.focus_force()
        except Exception:
            pass
        watch()
        step(seconds)
        return cd

    def pick_point(self, parent, on_done):
        """Countdown, then capture the mouse position and a picture around it.
        Calls on_done(x, y, snap_png, snap_spot). The whole app hides meanwhile; Esc or
        Cancel brings it back without changing anything."""
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def got(x, y):
            snap_png, spot = "", None
            if HAVE_CV:
                try:
                    snap, spot, _ = capture_snapshot(x, y, "Medium")
                    snap_png, spot = img_to_b64(snap), list(spot)
                except Exception:
                    pass
            restore()
            on_done(x, y, snap_png, spot)
        self.pick_countdown(got, restore)

    def edit_job(self):
        j = self.selected_job()
        if j:
            JobEditor(self, j, is_new=False)

    def duplicate_job(self):
        j = self.selected_job()
        if not j:
            return
        with self.lock:
            c = copy.deepcopy(j)
            c.update(id=uuid.uuid4().hex, name=j["name"] + " (copy)", enabled=False, count=0,
                     last_result="", last_run=None)
            for k in RUNTIME_KEYS:
                c[k] = None
            self.jobs.append(c)
        self.log(f"[{c['name']}] created (stopped). Edit it, then Start it.")
        self.save()
        self.refresh_tree(full=True)
        self.tree.selection_set(c["id"])

    def delete_job(self):
        j = self.selected_job()
        if j and self.selected_is_test():
            wt_row = self.tree.selection()[0].startswith("wtest:")
            if messagebox.askyesno(APP_NAME, f"Cancel the pending "
                                             f"{'watcher test' if wt_row else 'test click'} for "
                                             f"'{j['name']}'?", parent=self.root):
                (self.cancel_wtest if wt_row else self.cancel_test)(j)
            return
        if j and messagebox.askyesno(APP_NAME, f"Delete '{j['name']}'?\n\n(You can undo this "
                                               f"right after, with Undo or Ctrl+Z.)",
                                     parent=self.root):
            with self.lock:
                idx = next(i for i, x in enumerate(self.jobs) if x is j)
                was_on = bool(j.get("enabled"))
                self.jobs = [x for x in self.jobs if x is not j]
                self.stop_job(j)
            self.undo_stack.append((j, idx, was_on))
            del self.undo_stack[:-10]
            self.log(f"[{j['name']}] deleted (Ctrl+Z to undo)")
            self.save()
            self.refresh_tree(full=True)
            self.show_undo_bar()

    def toggle_job(self):
        j = self.selected_job()
        if not j:
            return
        with self.lock:
            if j.get("enabled"):
                self.stop_job(j)
                self.log(f"[{j['name']}] stopped")
            else:
                self.log(f"[{j['name']}] started")
                self.start_job(j)
        self.save()
        self.refresh_tree()

    def toggle_pause_job(self, job=None):
        j = job or self.selected_job()
        if not j:
            return
        if not j.get("enabled"):
            messagebox.showinfo(APP_NAME, f"'{j['name']}' is stopped. Start it first; pause is "
                                          f"for a running job.", parent=self.root)
            return
        now = time.time()
        with self.lock:
            if j.get("paused"):
                j["paused"] = False
                if is_watch(j):
                    j.update(next_check=now + 1, miss_count=0, watch_state="", watch_note="")
                    self.log(f"[{j['name']}] resumed - watching again")
                else:
                    self.log(f"[{j['name']}] resumed")
                    if j.get("next_run") and j["next_run"] < now:
                        # don't fire a click that came due while paused; go to the next one
                        self.schedule_after_run(j, now)
            else:
                j["paused"] = True
                j["pending_click_at"] = j["pending_since"] = None
                self.wait_msgs.pop((j["id"], "watch"), None)
                self.wait_msgs.pop((j["id"], "scheduled"), None)
                self.log(f"[{j['name']}] paused - no clicks until you resume it "
                         f"(its schedule is kept)")
        self.save()
        self.refresh_tree()
        self.update_buttons()

    def toggle_pause_all(self):
        with self.lock:
            self.settings["paused"] = not self.settings.get("paused")
            paused = self.settings["paused"]
        self.log("ALL JOBS PAUSED" if paused else "All jobs resumed")
        self.save()
        self.refresh_tree()
        if self.tray:
            try:
                self.tray.update_menu()
            except Exception:
                pass

    def show_position(self):
        j = self.selected_job()
        if j:
            self.show_spot_for(j)

    # ---- 4.5.1: hide windows and bring them back exactly as they were
    @staticmethod
    def release_popdowns(win):
        """Detach the dropdown lists of every combobox in `win` from it. On Windows a used
        dropdown list stays an "owned" window of the dialog, and hiding and showing the
        dialog with it attached could leave the dialog hidden behind the main window."""
        stack = [win]
        while stack:
            w = stack.pop()
            try:
                kids = w.winfo_children()
            except Exception:
                continue
            for k in kids:
                stack.append(k)
                if isinstance(k, ttk.Combobox):
                    pd = str(k) + ".popdown"
                    try:
                        if int(k.tk.call("winfo", "exists", pd)):
                            k.tk.call("wm", "withdraw", pd)
                            k.tk.call("wm", "transient", pd, "")
                    except Exception:
                        pass

    def hide_windows(self, wins):
        """Hide these windows. Returns what's needed to bring them back exactly: each
        window's state (normal / maximized) and its size and position."""
        saved = []
        for w in wins:
            try:
                if w is None or not w.winfo_exists() or not w.winfo_viewable():
                    continue
                st, g = w.state(), w.geometry()
                self.release_popdowns(w)
                w.withdraw()
                saved.append((w, st, g))
            except Exception:
                pass
        return saved

    def show_windows(self, saved, focus=None):
        """Bring back windows hidden by hide_windows(), at the same size, position and state,
        main window first, then `focus` (or the last dialog) on top with the keyboard focus."""
        order = sorted(saved, key=lambda t: t[0] is not self.root)
        for w, st, g in order:
            try:
                if not w.winfo_exists():
                    continue
                w.deiconify()
                if st == "zoomed":
                    w.state("zoomed")
                else:
                    if w is self.root:
                        w.state("normal")
                    w.geometry(g)
            except Exception:
                pass
        if focus is None:
            others = [w for w, _, _ in saved if w is not self.root]
            focus = others[0] if others else None
        if focus is not None:
            self.bring_to_front(focus)

    def bring_to_front(self, win, _again=2):
        """Show `win` on top of Clickue's other windows with the keyboard focus, and check
        again shortly after (Windows sometimes re-orders windows after a restore)."""
        try:
            if not win.winfo_exists():
                return
            if win.state() in ("withdrawn", "iconic"):
                win.deiconify()
            if win is not self.root:
                try:
                    if self.main_visible() and not win.transient():
                        win.transient(win.master)
                except Exception:
                    pass
            win.lift()
            win.attributes("-topmost", True)
            win.after(150, lambda: win.winfo_exists() and win.attributes("-topmost", False))
            win.focus_force()
        except Exception:
            return
        if _again:
            try:
                win.after(350, lambda: self.bring_to_front(win, _again - 1))
            except Exception:
                pass

    def hide_app(self, parent=None):
        """Hide every visible window of this app (so it's out of the way while testing).
        Returns a function that brings them back exactly the way they were."""
        wins = [w for w in (parent, self.tests_win) if w is not None]
        try:
            # the window a dialog sits on (e.g. the job editor under a step editor)
            m = getattr(parent, "master", None)
            while m is not None and m is not self.root:
                if isinstance(m, tk.Toplevel):
                    wins.append(m)
                m = getattr(m, "master", None)
        except Exception:
            pass
        wins.append(self.root)
        saved = self.hide_windows(wins)
        top = parent if parent is not None else self.tests_win

        def restore():
            self.show_windows(saved, focus=top)
            # let focus settle before popups may close on "click outside" again
            self.root.after(900, lambda: setattr(self, "_spot_busy", False))
        return restore

    def show_spot_for(self, job, parent=None):
        """Hide this app, find the spot, mark it for a few seconds, then come back."""
        activate = job.get("target_mode") == "window" and job.get("bring_to_front", True)
        owner = parent or self.root
        if not job.get("main_click", True):
            messagebox.showinfo(APP_NAME, "This job has no click of its own: it only runs its "
                                          "steps. Use Dry run or Step through (in Edit) to "
                                          "check them.", parent=owner)
            return
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def run():
            try:
                rep = spot_report(job, activate=activate, check_cover=False)
            except Exception as e:
                rep = {"result": (False, 0, 0, f"error while looking ({e})", ""), "similar": []}
            ok, x, y, msg, how = rep["result"]
            others = rep.get("similar") if self.settings.get("show_similar") else []
            if not ok and others:
                # nothing to click, but show the look-alikes that were ignored
                self.log(f"[{job['name']}] Show spot: {msg}")
                self.record_test(job["name"], "Show spot", f"Not found: {msg}", "bad")

                def after_marks():
                    restore()
                    messagebox.showwarning(APP_NAME, f"Can't show the spot: {msg}.\n\nThe "
                                                     f"outlines showed the similar pictures it "
                                                     f"found; none of them would be clicked.",
                                           parent=owner)
                self.flash_marker(None, None, f"{job['name']}  ·  not found: {msg}",
                                  after_marks, others=others)
                return
            if not ok:
                restore()
                self.log(f"[{job['name']}] Show spot: {msg}")
                self.record_test(job["name"], "Show spot", f"Not found: {msg}", "bad")
                messagebox.showwarning(APP_NAME, f"Can't show the spot: {msg}.", parent=owner)
                return
            if IS_WIN:
                user32.SetCursorPos(int(x), int(y))
            self.log(f"[{job['name']}] spot found at ({x}, {y}) by {how} - no click")
            self.record_test(job["name"], "Show spot", f"Found at ({x}, {y}) by {how}", "ok")
            note = resolution_note(job)

            def done():
                restore()
                if note:
                    self.log(f"[{job['name']}] note: {note}.")
                    messagebox.showinfo(APP_NAME, f"Heads up: {note}.\n\nFix: re-pick the spot "
                                                  f"so a picture of it is saved.", parent=owner)
            self.flash_marker(x, y, f"{job['name']}  ·  found by {how}", done, others=others)
        self.root.after(400, run)

    def show_watch_for(self, job, parent=None):
        """Hide this app, look for the watched picture, and mark where it was found."""
        owner = parent or self.root
        if not job.get("watch_png"):
            messagebox.showinfo(APP_NAME, "Draw a box around the picture to watch first.",
                                parent=owner)
            return
        if not HAVE_CV:
            messagebox.showwarning(APP_NAME, "Picture matching isn't installed. Start "
                                             "Clickue.bat installs it.", parent=owner)
            return
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def run():
            every = []
            scoped, problem = watch_scope(job)
            if problem:
                self.log(f"[{job['name']}] check: can't look - {problem}")
                self.record_test(job["name"], "Check picture now", f"Not checked: {problem}",
                                 "bad")
                restore()
                messagebox.showwarning(APP_NAME, f"The picture wasn't looked for: {problem}.",
                                       parent=owner)
                return
            try:
                (found, x, y, score, sc), wnote, _ = watched_picture(scoped, report=every,
                                                                     move_ok=True)
            except Exception as e:
                restore()
                messagebox.showerror(APP_NAME, f"Couldn't check the screen:\n{e}", parent=owner)
                return
            # every place that counts is always outlined (4.5.4); look-alikes that don't
            # count only with "point out every similar picture" on
            similar = every if self.settings.get("show_similar") else [m for m in every if m[6]]
            n_found = sum(1 for m in every if m[6])
            part = watch_partial(job)
            best = (f"best: {score:.0%} of it matches, {part:.0%} needed" if part
                    else f"best {score:.0%}") + (f", closest place at ({x}, {y})"
                                                 if (x or y) else "") + \
                (f"; {wnote}" if wnote else "") + \
                (f"; {watch_area_note(job)}" if job.get("watch_area") else "")
            if not found:
                self.log(f"[{job['name']}] check: watched picture NOT on screen ({best})")
                appears = job.get("watch_trigger") == "appears"
                where = "in its search area" if job.get("watch_area") else "on the screen"
                self.record_test(job["name"], "Check picture now",
                                 f"Picture NOT {where} ({best}) - the watcher "
                                 f"would {'not ' if appears else ''}click",
                                 "ok" if appears else "warn")

                def tell():
                    restore()
                    messagebox.showwarning(
                        APP_NAME, f"The watched picture is NOT {where} right now "
                                  f"({best})."
                                  + ("" if part else "\n\nIf part of the picture changes "
                                     "(a number, a time, an animation), turn on \u201cPart of "
                                     "the picture is enough\u201d in the watcher, or draw a "
                                     "smaller box around a part that stays the same.")
                                  + ("\n\nThe outlines showed similar pictures; none of them "
                                     "counts as the watched picture." if similar else "")
                                  + f"\n\nIf this watcher were running, it would "
                                  f"{'NOT click (it waits for the picture to appear)' if appears else 'click'}.",
                        parent=owner)
                if similar:
                    self.flash_marker(None, None, f"{job['name']}  ·  watched picture NOT found "
                                                  f"(similar places outlined)", tell,
                                      others=similar)
                else:
                    tell()
                return
            size = "" if not sc or abs(sc - 1) < 0.01 else f" at {sc:.0%} size"
            got = (f"{score:.0%} of it matches" if part else f"{score:.0%}") + size + \
                (f"; on screen {n_found} times, all outlined" if n_found > 1 else "") + \
                (f"; {wnote}" if wnote else "")
            self.log(f"[{job['name']}] check: watched picture found at ({x}, {y}), {got}")
            self.record_test(job["name"], "Check picture now",
                             f"Picture found at ({x}, {y}), {got}", "ok")
            self.flash_marker(x, y, f"{job['name']}  ·  watched picture found "
                                    f"({got})", restore, others=similar)
        self.root.after(400, run)

    def marker_seconds(self):
        """How long Show spot / Check now keep their marks on screen (Preferences)."""
        try:
            return int(min(120, max(1, int(self.settings.get("marker_seconds", 5)))))
        except Exception:
            return 5

    def flash_marker(self, x, y, caption="", on_done=None, seconds=None, others=None):
        """Red crosshair on (x, y) plus a small caption bar, for `seconds` (default: the
        Preferences setting). `others` = [(x, y, w, h, note, chosen?, exact?)] boxes to
        outline at the same time (similar pictures): green = what would be used, orange =
        exact copies not used, grey = similar but ignored. x may be None (outlines only).
        Click any of them, or press Esc, to close early."""
        if seconds is None:
            seconds = self.marker_seconds()
        size, key = 64, "#ff00fe"
        wins = []
        finished = []

        def close(_e=None):
            if finished:
                return
            finished.append(1)
            for w in wins:
                try:
                    w.destroy()
                except Exception:
                    pass
            if on_done:
                on_done()

        def place_exact(w, px, py):
            # Position with the same Windows call/pixels the mouse uses, so it's exact
            if not IS_WIN:
                return
            try:
                w.update_idletasks()
                hwnd = user32.GetParent(w.winfo_id()) or w.winfo_id()
                user32.SetWindowPos(hwnd, wt.HWND(-1), int(px), int(py), 0, 0,
                                    0x0001 | 0x0010)  # NOSIZE | NOACTIVATE
            except Exception:
                pass

        for (bx, by, bw, bh, note, chosen, exact) in (others or [])[:20]:
            color = "#22c55e" if chosen else ("#f59e0b" if exact else "#9ca3af")
            o = tk.Toplevel(self.root)
            wins.append(o)
            o.overrideredirect(True)
            o.attributes("-topmost", True)
            lh = 18
            # the label is as wide as its text, even over a tiny picture (4.5.6: it was cut off)
            try:
                tw_ = tkfont.Font(family=self.font_family, size=8, weight="bold").measure(note)
            except Exception:
                tw_ = 7 * len(note)
            W, H = max(bw + 4, tw_ + 14), bh + lh + 4
            oc = tk.Canvas(o, width=W, height=H, bg=key, highlightthickness=0)
            oc.pack()
            if IS_WIN:
                o.attributes("-transparentcolor", key)
            oc.create_rectangle(1, lh + 1, bw + 2, lh + bh + 2, outline=color, width=2)
            oc.create_rectangle(1, 0, min(W - 1, tw_ + 12), lh, fill=color, outline="")
            oc.create_text(5, lh // 2, text=note, anchor="w", fill="#111827",
                           font=(self.font_family, 8, "bold"))
            o.geometry(f"{W}x{H}+{bx - 2}+{by - lh - 2}")
            place_exact(o, bx - 2, by - lh - 2)
            oc.bind("<Button-1>", close)

        m = c = ring = None
        if x is not None:
            m = tk.Toplevel(self.root)
            wins.append(m)
            m.overrideredirect(True)
            m.attributes("-topmost", True)
            c = tk.Canvas(m, width=size, height=size, bg=key, highlightthickness=0)
            c.pack()
            if IS_WIN:
                m.attributes("-transparentcolor", key)
            h = size / 2
            ring = c.create_oval(6, 6, size - 6, size - 6, outline="#ff2d2d", width=3)
            c.create_oval(h - 3, h - 3, h + 3, h + 3, fill="#ff2d2d", outline="")
            for a, b in ((0, h - 10), (h + 10, size)):
                c.create_line(h, a, h, b, fill="#ff2d2d", width=2)
                c.create_line(a, h, b, h, fill="#ff2d2d", width=2)
            m.geometry(f"{size}x{size}+{x - size // 2}+{y - size // 2}")
            place_exact(m, x - size // 2, y - size // 2)
            c.bind("<Button-1>", close)

        left = [seconds]
        lbl = None
        if caption:
            cap = tk.Toplevel(self.root, bg="#111827")
            wins.append(cap)
            cap.overrideredirect(True)
            cap.attributes("-topmost", True)
            lbl = tk.Label(cap, bg="#111827", fg="#ffffff", padx=12, pady=6,
                           font=(self.font_family, 10), justify="left")
            lbl.pack()
            lbl.bind("<Button-1>", close)
            legend = ("\nGreen = what would be used · orange = same picture, not used · "
                      "grey = similar, ignored" if others else "")

            def cap_text():
                return (f"{caption}{legend}\nClick here or press Esc to close  ({left[0]}s)")
            lbl.configure(text=cap_text())
            cap.update_idletasks()
            cw, chh = cap.winfo_reqwidth(), cap.winfo_reqheight()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            if x is None:
                cx, cy = max(0, (sw - cw) // 2), 40
            else:
                cx = min(max(0, x - cw // 2), max(0, sw - cw))
                cy = y + size // 2 + 8
                if cy + chh > sh - 40:
                    cy = y - size // 2 - 8 - chh
            cap.geometry(f"+{cx}+{cy}")
            place_exact(cap, cx, cy)
        for w in wins:
            w.bind("<Escape>", close)
        try:
            (wins[0] if wins else self.root).focus_force()
        except Exception:
            pass
        if not wins:
            self.root.after(10, close)
            return

        def tick(n=0):
            if finished:
                return
            if IS_WIN and key_down(VK_ESCAPE):
                close()
                return
            if n and n % 3 == 0:
                left[0] -= 1
                if lbl is not None:
                    try:
                        lbl.configure(text=cap_text())
                    except Exception:
                        pass
            if left[0] <= 0:
                close()
                return
            if c is not None:
                try:
                    c.itemconfigure(ring, width=3 if n % 2 == 0 else 5)
                except Exception:
                    return
            wins[0].after(333, tick, n + 1)
        tick()

    def test_click(self, job=None, parent=None):
        j = job or self.selected_job()
        if not j:
            return
        owner = parent or self.root
        if not messagebox.askyesno(
                APP_NAME, (f"The app will hide and '{j['name']}' will click once at "
                           f"{target_text(j)}" if j.get("main_click", True) else
                           f"The app will hide and '{j['name']}' will run its steps once")
                          + (" (then run its steps)" if j.get("steps") and j.get("main_click", True)
                             else "") + ".\nThe schedule is not changed. Continue?",
                parent=owner):
            return
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def go():
            self.ensure_runtime()
            it = self.aq.put(j, "manual", priority="high") if self.aq.active else None
            if it is None and self.aq.active:
                self.root.after(600, restore)       # already queued or running
                return
            if it is None:
                th = threading.Thread(target=self.execute, args=(j, "manual"), daemon=True)
                th.start()
                done = lambda: not th.is_alive()
            else:
                done = it["done"].is_set

            def wait():
                if not done():
                    self.root.after(200, wait)
                else:
                    self.root.after(600, restore)
            wait()
        self.root.after(700, go)

    def schedule_test(self):
        j = self.selected_job()
        if j:
            TestDialog(self, j)

    def open_settings(self):
        SettingsDialog(self)

    # ------------------------------------------------------------ import / export
    def export_to(self, path, jobs=None):
        """Write jobs (all, or the given ones) and the step groups they use to a file.
        Secret text is never exported."""
        with self.lock:
            skip = set(RUNTIME_KEYS) | {"last_result", "last_run", "count", "saved_vars"}
            src = self.jobs if jobs is None else jobs
            out = []
            for j in src:
                d = {k: v for k, v in j.items() if k not in skip}
                d["steps"] = strip_secret_text(j.get("steps"))
                out.append(d)
            used = {st.get("group_id") for j in src for st in j.get("steps") or []
                    if st.get("type") == "group"}
            groups = [dict(g, steps=strip_secret_text(g.get("steps")))
                      for g in getattr(self, "groups", []) if g.get("id") in used]
        write_json(path, {"app": APP_ID, "version": VERSION, "schema": SCHEMA_VERSION,
                          "exported": datetime.now().isoformat(timespec="seconds"),
                          "jobs": out, "groups": groups})

    def export_jobs(self):
        with self.lock:
            if not self.jobs:
                messagebox.showinfo(APP_NAME, "There are no jobs to export yet.", parent=self.root)
                return
        path = filedialog.asksaveasfilename(
            parent=self.root, title="Export jobs", defaultextension=".json",
            initialfile=f"Clickue jobs {datetime.now():%Y-%m-%d}.json",
            filetypes=[("Clickue jobs", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.export_to(path)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not export:\n{e}", parent=self.root)
            return
        self.log(f"Exported {len(self.jobs)} job(s) to {path}")
        messagebox.showinfo(APP_NAME, f"Saved your jobs to:\n{path}\n\n"
                                      f"Use Import… to load them again.", parent=self.root)

    def import_jobs(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="Import jobs",
            filetypes=[("Clickue jobs", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            raw, groups, problems = load_import_file(path)
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not import:\n{e}", parent=self.root)
            return
        with self.lock:
            have = len(self.jobs)
        risky = risky_step_summary(raw, groups)
        names = {"type": "type text", "paste": "paste text", "key": "press keys",
                 "keyhold": "hold keys down"}
        rtxt = ", ".join(f"{names[k]} ({n})" for k, n in risky.items() if n)
        review = ("\n\nSome steps send keyboard input: " + rtxt + "." if rtxt else "") + \
            ("\n\n" + str(len(problems)) + " problem(s) were fixed or left out, e.g.: "
             + problems[0] if problems else "")
        choice = True
        if have:
            choice = messagebox.askyesnocancel(
                APP_NAME, f"Found {len(raw)} job(s) in the file.{review}\n\n"
                          f"Imported jobs start STOPPED so you can check them first.\n\n"
                          f"Yes  =  add them to your {have} current job(s)\n"
                          f"No   =  replace your current jobs (a backup is saved first)\n"
                          f"Cancel  =  do nothing", parent=self.root)
            if choice is None:
                return
        elif not messagebox.askokcancel(
                APP_NAME, f"Import {len(raw)} job(s)?{review}\n\nImported jobs start STOPPED "
                          f"so you can check them first (Edit, Tests → Dry run).",
                parent=self.root):
            return
        if choice is False:
            try:
                self.backup_now("before-import")
            except Exception:
                pass
        new = []
        id_map = {}
        with self.lock:
            existing = {g["id"] for g in self.groups}
            for g in groups:
                gid = g["id"]
                if gid in existing:
                    id_map[gid] = uuid.uuid4().hex
                    g = dict(g, id=id_map[gid], name=g["name"] + " (imported)")
                self.groups.append(g)
        for b in raw:
            b.update(id=uuid.uuid4().hex, count=0, last_run=None, last_result="Imported - check, "
                     "then start", enabled=False, paused=False)
            for st in b.get("steps", []):
                if st.get("type") == "group" and st.get("group_id") in id_map:
                    st["group_id"] = id_map[st["group_id"]]
            for k in RUNTIME_KEYS:
                b[k] = None
            b["run_clicks"], b["miss_count"], b["armed"] = 0, 0, True
            new.append(b)
        with self.lock:
            if choice is False:
                for j in self.jobs:
                    self.stop_job(j)
                self.jobs = new
            else:
                self.jobs.extend(new)
        self.log(f"Imported {len(new)} job(s) from {path}. They are stopped until you start "
                 f"them." + (f" {len(problems)} problem(s) fixed or left out." if problems else ""))
        self.save()
        self.refresh_tree(full=True)

    # ------------------------------------------------------------ uninstall
    def uninstall(self, parent):
        installed = bool(read_install_id()) and IS_WIN and FROZEN
        unins = os.path.join(PROGRAM_DIR, "unins000.exe")
        items = ["• Clickue stops: no more clicks, hotkeys or tray icon",
                 "• the start-with-Windows entry"]
        if installed and os.path.exists(unins):
            items.append("• the program and its shortcuts (Windows' uninstaller opens next)")
        elif FROZEN:
            items.append("• Clickue.exe itself")
        if not messagebox.askyesno(APP_NAME, f"Uninstall {APP_NAME}?\n\nThis removes:\n"
                                             + "\n".join(items) + "\n\nNext you can choose to "
                                             "keep or delete your jobs and other data.",
                                   icon="warning", parent=parent):
            return
        vdir = video_folder(self.settings)
        custom_videos = os.path.normcase(os.path.abspath(vdir)) != \
            os.path.normcase(os.path.abspath(data_path("recordings")))
        extra = (f"\n\nScreen videos in your own folder ({vdir}): only Clickue's video files "
                 f"there are deleted, nothing else." if custom_videos else "")
        delete_data = messagebox.askyesnocancel(
            APP_NAME, f"Also delete your Clickue data?\n\n{DATA_DIR}\n(jobs, settings, step "
                      f"groups, click and run history, logs, backups, failure screenshots and "
                      f"screen videos kept there){extra}\n\nYes = delete my data\n"
                      f"No = keep it (installing Clickue again picks it up)\n"
                      f"Cancel = don't uninstall", icon="warning", parent=parent)
        if delete_data is None:
            return
        backup_path = None
        with self.lock:
            has_jobs = bool(self.jobs)
        if delete_data and has_jobs and messagebox.askyesno(
                APP_NAME, "Save a copy of your jobs to your Documents folder first?\n"
                          "(You can load it later with Import…)", parent=parent):
            try:
                docs = os.path.join(os.path.expanduser("~"), "Documents")
                backup_path = os.path.join(
                    docs, f"Clickue jobs backup {datetime.now():%Y-%m-%d %H%M}.json")
                self.export_to(backup_path)
            except Exception as e:
                if not messagebox.askyesno(APP_NAME, f"Saving the copy failed:\n{e}\n\n"
                                                     f"Uninstall anyway?", parent=parent):
                    return
                backup_path = None

        self.ensure_runtime()
        self.emergency_stop_quiet()
        self.uninstalled = True
        self.stop_hotkeys()
        self.stop.set()
        keep_awake(False)
        set_run_at_startup(False)
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.close_logging()
        self.logger.addHandler(logging.NullHandler())
        time.sleep(0.3)
        notes = []
        if delete_data:
            if custom_videos:
                prune_files(vdir, VIDEO_FILE_RE, keep_count=0)
            if is_clickue_data_dir(DATA_DIR):
                shutil.rmtree(DATA_DIR, ignore_errors=True)
                notes.append("Your data was deleted.")
            else:
                notes.append(f"Your data was NOT deleted, because this folder doesn't look like "
                             f"Clickue's own data folder:\n{DATA_DIR}")
        else:
            notes.append(f"Your data was kept in:\n{DATA_DIR}")
        if backup_path:
            notes.append(f"A copy of your jobs was saved to:\n{backup_path}")
        exe = sys.executable
        if installed and os.path.exists(unins):
            try:
                subprocess.Popen([unins] + ([] if delete_data else ["/KEEPDATA"]))
                notes.append("Windows' uninstaller opens next to remove the program.")
            except Exception:
                notes.append("Finish in Windows Settings → Apps → Clickue → Uninstall.")
        elif FROZEN and IS_WIN and os.path.basename(exe).lower() == "clickue.exe" \
                and '"' not in exe:
            try:
                subprocess.Popen(
                    f'cmd /c ping 127.0.0.1 -n 4 > nul & del /f /q "{exe}"',
                    creationflags=0x08000000)  # CREATE_NO_WINDOW
                notes.append("Clickue.exe will delete itself in a few seconds."
                             + (f" Then you can delete its folder:\n{PROGRAM_DIR}" if PORTABLE
                                else ""))
            except Exception:
                notes.append(f"Please delete this file yourself:\n{exe}")
        else:
            notes.append(f"To finish, delete the program folder:\n{PROGRAM_DIR}")
        messagebox.showinfo(APP_NAME, f"{APP_NAME} has been uninstalled.\n\n" + "\n\n".join(notes),
                            parent=parent)
        self.root.destroy()

    def emergency_stop_quiet(self):
        """Stop everything without pausing or saving (exit / uninstall)."""
        try:
            self.run_cancel.set()
            self.aq.clear()
            HELD.release_all()
            if self.recorder is not None:
                self.recorder.cancel()
                self.recorder = None
        except Exception:
            pass


# ---------------------------------------------------------------- dialogs
UNIT_GAP = 4      # px between a number field and its unit (h, m, s, seconds, ...)
UNIT_AFTER = 12   # px after a unit, before the next field


def spin_unit(parent, var, lo, hi, unit, width=5, command=None, lead=0, increment=None,
              unit_style=None):
    """A number field with its unit right next to it, packed left into `parent`. Every
    duration and count field in the app uses this so the spacing is the same everywhere.
    Returns (spinbox, unit label)."""
    kw = {"command": command} if command else {}
    if increment:
        kw["increment"] = increment
    sp = ttk.Spinbox(parent, from_=lo, to=hi, width=width, textvariable=var, **kw)
    sp.pack(side="left", padx=(lead, UNIT_GAP))
    ul = ttk.Label(parent, text=unit, **({"style": unit_style} if unit_style else {}))
    ul.pack(side="left", padx=(0, UNIT_AFTER))
    return sp, ul


LOG_LEVELS = ("quiet", "normal", "detailed")


def log_wanted(setting, level, msg):
    """Should a log line of this level be written with the chosen log level? (4.5.6)"""
    if level == "important":
        return True
    if level == "detail":
        return setting == "detailed"
    if setting != "quiet":
        return True
    m = msg.upper()
    return any(w in m for w in ("FAILED", "MISSED", "CAN'T", "COULDN'T", "NOT ", "ERROR",
                                "PROBLEM", " - OK", "CLICKED", "GONE", "APPEARED", "WAITING",
                                "STARTED", "STOPPED", "PAUSED", "RESUMED", "WARNING"))


ISSUE_HINTS = (    # (words in the message, what to do) - shown in logs and tooltips (4.5.6)
    ("screen locked", "Windows blocks screenshots and clicks while the screen is locked or a "
                      "remote session is disconnected. Unlock it; when leaving a remote "
                      "session, hand it to the console instead of disconnecting."),
    ("using the mouse", "Clickue waits until the mouse and keyboard have been idle for the time "
                        "set in Preferences → Clicking."),
    ("Clickue window in front", "A missing picture isn't counted while a Clickue window is in "
                                "front of it (covering it). Minimize Clickue, send it to the "
                                "tray, or bring the watched window to the front."),
    ("Clickue window open", "A missing picture isn't counted while a Clickue window is in "
                            "front of it (covering it). Minimize Clickue, send it to the tray, "
                            "or bring the watched window to the front."),
    ("covering the spot", "Minimize Clickue or move its window away from the spot."),
    ("mouse pointer", "Move the mouse away from the watched picture (hovering can change how "
                      "it looks)."),
    ("no picture saved", "Edit the watcher and click Draw box around picture."),
    ("not installed", "Run Start Clickue.bat (or pip install -r requirements.txt)."),
    ("screen size or scaling", "The screen changed (e.g. switching between a remote session "
                               "and the console). It still looks: a picture that's there shows "
                               "as seen right away; only a missing picture isn't counted for "
                               "15 s, so the switch can't cause a click."),
    ("on screen", "The same picture is on screen several times. Re-pick with a Large picture, "
                  "or use Inside a window."),
    ("exact picture", "Run Show spot to see what Clickue finds. Is the spot visible (not scrolled "
                      "away, covered or minimized)? If the page looks different now, pick the "
                      "spot again."),
    ("saved picture", "Run Show spot. Is the spot visible? Pick it again if the page changed."),
    ("search area", "Draw the search area again on this screen, or search the whole screen."),
    ("couldn't look", "Clickue couldn't take a screenshot; see the message. If it repeats, "
                      "restart Clickue."),
    ("window", "Is the window open and not minimized?"),
)


def issue_hint(msg):
    """What to do about a problem message (or "" if there's no advice)."""
    m = (msg or "").lower()
    for words, hint in ISSUE_HINTS:
        if words.lower() in m:
            return hint
    return ""


def read_log_tail(n):
    """The last n lines of the log file (and its previous file) as [(time, message)];
    continuation lines are joined to their message."""
    out = []
    for path in (LOG_PATH + ".1", LOG_PATH):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for raw in fh.read().splitlines():
                    if re.match(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d  ", raw):
                        out.append([raw[:19], raw[21:]])
                    elif out and raw.strip():
                        out[-1][1] += " " + raw.strip()
        except OSError:
            pass
    return [tuple(x) for x in out[-n:]]


# ---- 4.5.5: tools for every log table (copy, filter, show on screen, side scrolling)
STEP_LINE_RE = re.compile(r"\bstep \d+\b|\bsteps?\b.*\b(ran|failed|done)\b", re.I)
LOC_RE = re.compile(r"\((-?\d{1,6}), (-?\d{1,6})\)")


class HoverTip:
    """A tooltip that follows rows of a table (4.5.6): text_for(x, y) returns the text for
    what's under the pointer (or "" for nothing). Shows after a short pause, updates while
    the pointer rests on the same row, hides on leave, click or scroll."""

    def __init__(self, app, widget, text_for, delay=450):
        self.app, self.w, self.text_for, self.delay = app, widget, text_for, delay
        self.tip = None
        self.job = None
        self.key = None
        self.pos = (0, 0)
        widget.bind("<Motion>", self.motion, add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")
        widget.bind("<ButtonPress>", lambda e: self.hide(), add="+")
        widget.bind("<MouseWheel>", lambda e: self.hide(), add="+")

    def motion(self, e):
        self.pos = (e.x, e.y, e.x_root, e.y_root)
        key = self.w.identify_row(e.y) if hasattr(self.w, "identify_row") else None
        if key != self.key:
            self.key = key
            self.hide()
            if self.job:
                self.w.after_cancel(self.job)
            self.job = self.w.after(self.delay, self.show) if key else None

    def show(self, refresh=False):
        self.job = None
        x, y, xr, yr = self.pos
        try:
            text = self.text_for(x, y)
        except Exception:
            text = ""
        if not text:
            self.hide()
            return
        p = self.app.pal
        if self.tip is None:
            t = tk.Toplevel(self.w)
            t.overrideredirect(True)
            t.attributes("-topmost", True)
            self.lbl = tk.Label(t, justify="left", anchor="w", bg=p["panel"], fg=p["fg"],
                                bd=1, relief="solid", padx=10, pady=7, wraplength=520,
                                font=(self.app.font_family, 9),
                                highlightbackground=p["border"])
            self.lbl.pack()
            self.tip = t
        self.lbl.configure(text=text)
        if not refresh:
            sw = self.w.winfo_screenwidth()
            self.tip.update_idletasks()
            tw = self.tip.winfo_reqwidth()
            self.tip.geometry(f"+{min(xr + 16, max(0, sw - tw - 8))}+{yr + 20}")
        # live while the pointer stays on the row (countdowns)
        self.job = self.w.after(1000, lambda: self.show(refresh=True))

    def hide(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except Exception:
                pass
            self.job = None
        if self.tip is not None:
            try:
                self.tip.destroy()
            except Exception:
                pass
            self.tip = None


class FilterBox(ttk.Frame):
    """A small search field: typing filters a log (case doesn't matter); ✕ clears it."""

    def __init__(self, parent, on_change, width=22, hint="Filter…"):
        super().__init__(parent)
        self.var = tk.StringVar()
        self._hint = hint
        self._job = None
        ttk.Label(self, text="🔍").pack(side="left", padx=(0, 4))
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side="left")
        self.clear_btn = ttk.Button(self, text="✕", width=3, style="Small.TButton",
                                    command=self.clear)
        self.clear_btn.pack(side="left", padx=(2, 0))
        self.on_change = on_change
        self.var.trace_add("write", lambda *a: self._changed())
        self.entry.bind("<Escape>", lambda e: (self.clear(), "break")[1])

    def _changed(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(180, self._fire)

    def _fire(self):
        self._job = None
        self.on_change()

    def query(self):
        return self.var.get().strip().lower()

    def matches(self, *texts):
        q = self.query()
        if not q:
            return True
        hay = " ".join(str(t) for t in texts).lower()
        return q in hay

    def clear(self):
        self.var.set("")

    def focus(self):
        self.entry.focus_set()
        self.entry.select_range(0, "end")


class LogGrid:
    """Right-click menu and shortcuts for a log table (4.5.5): copy the selected rows, one
    cell or everything shown (tab-separated, ready for a spreadsheet), select all, save as
    CSV, and "Show on screen" for rows that mention a place like (878, 243). Also gives the
    table a horizontal scrollbar that appears when its text is wider than the window."""

    def __init__(self, app, tree, frame=None, owner=None, job_of=None, extra=None,
                 locate=True, fit_col=None, filterbox=None, name="log", natural="new",
                 refresh=None, delete=None, delete_label="Delete…"):
        self.app, self.tree, self.owner = app, tree, owner
        self.natural = natural            # the order fill() produces: "new" or "old" first
        self.refresh = refresh
        self.delete = delete
        self.delete_label = delete_label
        self.order_btn = None
        self.job_of = job_of or (lambda iid: None)
        self.extra = extra
        self.locate = locate
        self.fit_col = fit_col
        self.filterbox = filterbox
        self.name = name
        try:
            if str(tree.cget("selectmode")) == "browse":
                tree.configure(selectmode="extended")
        except Exception:
            pass
        self.menu = tk.Menu(tree, tearoff=0)
        tree.bind("<Button-3>", self.popup, add="+")
        tree.bind("<Control-c>", lambda e: (self.copy_selected(), "break")[1])
        tree.bind("<Control-a>", lambda e: (self.select_all(), "break")[1])
        if filterbox is not None:
            tree.bind("<Control-f>", lambda e: (filterbox.focus(), "break")[1])
        if frame is not None:
            self.hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
            tree.configure(xscrollcommand=self._xset)
            self._hsb_shown = False
        else:
            self.hsb = None
        if fit_col:
            tree.bind("<Configure>", lambda e: tree.after_idle(self.fit), add="+")

    # ---- order, clear view, refresh (4.5.6)
    def order(self):
        o = (self.app.settings.get("log_order") or {}).get(self.name)
        return o if o in ("new", "old") else self.natural

    def toggle_order(self):
        orders = dict(self.app.settings.get("log_order") or {})
        orders[self.name] = "old" if self.order() == "new" else "new"
        self.app.settings["log_order"] = orders
        self.app.save()
        self.done_filling(refilled=False)

    def hidden(self):
        return self.app.__dict__.setdefault("log_hidden", {}).setdefault(self.name, set())

    def row_key(self, iid):
        return tuple(str(v) for v in self.tree.item(iid, "values"))

    def clear_view(self):
        """Hide everything shown now, for this session only (nothing is deleted)."""
        h = self.hidden()
        for iid in self.tree.get_children():
            h.add(self.row_key(iid))
        self.done_filling(refilled=False)
        self.app.flash_status("View cleared (nothing deleted; Show all again brings it back)")

    def show_all_again(self):
        self.hidden().clear()
        if self.refresh:
            self.refresh()

    def done_filling(self, refilled=True):
        """Call after (re)filling the table: hides rows cleared from view, puts the rows in
        the chosen order, sizes the long column."""
        t = self.tree
        h = self.hidden()
        if h:
            for iid in t.get_children():
                if self.row_key(iid) in h:
                    t.delete(iid)
        if refilled:
            self._rev = False
        want_rev = self.order() != self.natural
        if want_rev != getattr(self, "_rev", False):
            for k, iid in enumerate(reversed(t.get_children())):
                t.move(iid, "", k)
            self._rev = want_rev
        if self.order_btn is not None:
            self.order_btn.configure(text="↓ Newest first" if self.order() == "new"
                                     else "↑ Oldest first")
        self.fit()

    def toolbar(self, parent, side="right"):
        """Small buttons: ⟳ Refresh, order, Clear view, Delete… (as far as this log has them)."""
        box = ttk.Frame(parent)
        if self.delete:
            ttk.Button(box, text=self.delete_label, style="Small.TButton",
                       command=self.delete).pack(side="right", padx=(4, 0))
        ttk.Button(box, text="Clear view", style="Small.TButton",
                   command=self.clear_view).pack(side="right", padx=(4, 0))
        self.order_btn = ttk.Button(box, text="", style="Small.TButton",
                                    command=self.toggle_order)
        self.order_btn.pack(side="right", padx=(4, 0))
        if self.refresh:
            ttk.Button(box, text="⟳ Refresh", style="Small.TButton",
                       command=self.refresh).pack(side="right", padx=(4, 0))
        self.order_btn.configure(text="↓ Newest first" if self.order() == "new"
                                 else "↑ Oldest first")
        box.pack(side=side)
        return box

    # ---- side scrolling
    def _xset(self, first, last):
        self.hsb.set(first, last)
        need = float(first) > 0.0 or float(last) < 1.0
        if need != self._hsb_shown:
            self._hsb_shown = need
            if need:
                self.hsb.pack(side="bottom", fill="x", before=self.tree)
            else:
                self.hsb.pack_forget()

    def fit(self):
        """Make the long text column wide enough for its longest text, so the table can be
        scrolled sideways instead of cutting the text off."""
        t, col = self.tree, self.fit_col
        try:
            cols = t["displaycolumns"]
            if isinstance(cols, str):
                cols = (cols,)
            if not cols or cols[0] == "#all":
                cols = t["columns"]
            if col not in cols:
                return
            others = sum(int(t.column(c, "width")) for c in cols if c != col)
            want = max(column_fit_width(t, col, limit=4000), t.winfo_width() - others - 2, 80)
            if abs(int(t.column(col, "width")) - want) > 2:
                t.column(col, width=want, stretch=False)
        except Exception:
            pass

    # ---- copying
    def columns(self):
        t = self.tree
        cols = t["displaycolumns"]
        if isinstance(cols, str):
            cols = (cols,)
        if not cols or cols[0] == "#all":
            cols = t["columns"]
        return list(cols)

    def row_text(self, iid):
        return "\t".join(str(self.tree.set(iid, c)).strip() for c in self.columns())

    def header(self):
        return "\t".join(str(self.tree.heading(c, "text")) for c in self.columns())

    def to_clipboard(self, text, what):
        try:
            w = self.tree
            w.clipboard_clear()
            w.clipboard_append(text)
            w.update()
            self.app.flash_status(f"Copied {what}")
        except Exception:
            pass

    def copy_selected(self):
        sel = [i for i in self.tree.selection()]
        if not sel:
            return
        order = {iid: n for n, iid in enumerate(self.tree.get_children())}
        sel.sort(key=lambda i: order.get(i, 0))
        self.to_clipboard("\n".join(self.row_text(i) for i in sel),
                          f"{len(sel)} row{'s' if len(sel) != 1 else ''}")

    def copy_all(self):
        kids = self.tree.get_children()
        self.to_clipboard("\n".join([self.header()] + [self.row_text(i) for i in kids]),
                          f"{len(kids)} rows with headings")

    def copy_cell(self, iid, col):
        self.to_clipboard(str(self.tree.set(iid, col)).strip(), "the cell")

    def select_all(self):
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids)

    def save_csv(self):
        path = filedialog.asksaveasfilename(
            parent=self.owner or self.tree.winfo_toplevel(), defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Text", "*.txt")],
            initialfile=f"clickue-{self.name}.csv")
        if not path:
            return
        try:
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                w.writerow([self.tree.heading(c, "text") for c in self.columns()])
                for i in self.tree.get_children():
                    w.writerow([str(self.tree.set(i, c)).strip() for c in self.columns()])
            self.app.flash_status(f"Saved {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't save the file:\n{e}",
                                 parent=self.owner or self.tree.winfo_toplevel())

    # ---- menu
    def popup(self, e):
        t = self.tree
        iid = t.identify_row(e.y)
        col_id = t.identify_column(e.x)
        col = None
        try:
            cols = self.columns()
            k = int(col_id.lstrip("#")) - 1
            col = cols[k] if 0 <= k < len(cols) else None
        except Exception:
            col = None
        if iid and iid not in t.selection():
            t.selection_set(iid)
            t.focus(iid)
        m = self.menu
        m.delete(0, "end")
        n_sel = len(t.selection())
        m.add_command(label=("Copy" if n_sel <= 1 else f"Copy {n_sel} rows") + "\tCtrl+C",
                      command=self.copy_selected,
                      state="normal" if n_sel else "disabled")
        if iid and col:
            m.add_command(label=f"Copy \u201c{t.heading(col, 'text')}\u201d only",
                          command=lambda: self.copy_cell(iid, col))
        m.add_command(label="Copy everything shown (with headings)", command=self.copy_all)
        m.add_command(label="Select all\tCtrl+A", command=self.select_all)
        if iid and self.locate:
            text = " ".join(str(v) for v in t.item(iid, "values"))
            if LOC_RE.search(text):
                m.add_separator()
                m.add_command(label="📍  Show this place on screen",
                              command=lambda: self.app.show_places(
                                  text, parent=self.owner, job_name=self.job_of(iid)))
        if iid and self.extra:
            items = self.extra(iid) or []
            if items:
                m.add_separator()
                for label, cmd in items:
                    m.add_command(label=label, command=cmd)
        m.add_separator()
        if self.refresh:
            m.add_command(label="⟳ Refresh", command=self.refresh)
        m.add_command(label="Show oldest first" if self.order() == "new" else
                      "Show newest first", command=self.toggle_order)
        m.add_command(label="Clear view (hide what's shown, for now)", command=self.clear_view)
        if self.hidden():
            m.add_command(label="Show all again", command=self.show_all_again)
        if self.delete:
            m.add_command(label=self.delete_label.replace("…", "") + " (for good)…",
                          command=self.delete)
        if self.filterbox is not None:
            m.add_command(label="Filter…\tCtrl+F", command=self.filterbox.focus)
            if self.filterbox.query():
                m.add_command(label="Clear the filter", command=self.filterbox.clear)
        m.add_command(label="Save what's shown as CSV…", command=self.save_csv)
        try:
            self.app.theme_menu(m)
        except Exception:
            pass
        m.tk_popup(e.x_root, e.y_root)
        return "break"


class BoxDrawer:
    """The frozen, dimmed screenshot on which a box is dragged (4.5.4: zoom and magnifier).
    Mouse wheel or + / - zooms (up to 24x, pixel-exact, with a pixel grid from 8x), the
    middle button or the arrow keys move the view, 0 shows the whole screen again. A
    magnifier next to the pointer shows the exact pixels, their position and colour.
    The box is kept in screenshot pixels, so zooming and moving never change what's saved.
    on_done((x0, y0, x1, y1)) gets the box in screenshot pixels; on_cancel() on Esc."""
    ZOOMS = (1, 2, 3, 4, 6, 8, 12, 16, 24)
    LOUPE_PX = 15          # pixels shown in the magnifier (odd: one in the middle)
    LOUPE_SIZE = 165       # its size on screen

    def __init__(self, app, shot, origin, prompt, on_done, on_cancel, min_size=8):
        self.app, self.shot = app, shot
        self.vx, self.vy = origin
        self.W, self.H = W, H = shot.size
        self.on_done, self.on_cancel = on_done, on_cancel
        self.min_size = min_size
        self.z, self.ox, self.oy = 1, 0, 0
        self.anchor = self.sel = None
        self.pan = None
        self.done = False
        self._pend = {}
        self.dim = Image.blend(shot, Image.new("RGB", shot.size, (0, 0, 0)), 0.5)
        self.imgs = {}
        F = app.font_family
        ov = tk.Toplevel(app.root)
        self.ov = ov
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.geometry(f"{W}x{H}+{self.vx}+{self.vy}")
        cv = tk.Canvas(ov, width=W, height=H, highlightthickness=0, bd=0, cursor="crosshair",
                       bg="#000000")
        self.cv = cv
        cv.pack()
        self.base = cv.create_image(0, 0, anchor="nw")
        self.bright = cv.create_image(0, 0, anchor="nw")
        self.rect = cv.create_rectangle(0, 0, 0, 0, outline="#3b82f6", width=2)
        self.size_txt = cv.create_text(0, 0, anchor="sw", fill="#ffffff", font=(F, 10, "bold"))
        self.prompt_txt = cv.create_text(W // 2, 34, text=prompt, fill="#ffffff",
                                         font=(F, 13, "bold"))
        bx = cv.bbox(self.prompt_txt)
        self.prompt_bg = cv.create_rectangle(bx[0] - 18, bx[1] - 10, bx[2] + 18, bx[3] + 10,
                                             fill="#1f2937", outline="#3b82f6")
        cv.tag_raise(self.prompt_txt, self.prompt_bg)
        cbtn = tk.Label(cv, text="✕  Cancel (Esc)", font=(F, 10, "bold"), bg="#374151",
                        fg="#ffffff", padx=12, pady=6, cursor="hand2", bd=0)
        cbtn.bind("<Button-1>", lambda e: self.cancel())
        cbtn.bind("<Enter>", lambda e: cbtn.configure(bg="#dc2626"))
        cbtn.bind("<Leave>", lambda e: cbtn.configure(bg="#374151"))
        self.cancel_win = cv.create_window(bx[2] + 30, 34, window=cbtn, anchor="w")
        # help / zoom line at the bottom
        self.help_bg = cv.create_rectangle(0, 0, 0, 0, fill="#1f2937", outline="#374151")
        self.help_txt = cv.create_text(16, H - 18, anchor="w", fill="#e5e7eb", font=(F, 10))
        # magnifier
        self.loupe_img = cv.create_image(0, 0, anchor="nw", state="hidden")
        self.loupe_box = cv.create_rectangle(0, 0, 0, 0, outline="#3b82f6", width=2,
                                             state="hidden")
        self.loupe_bg = cv.create_rectangle(0, 0, 0, 0, fill="#111827", outline="#3b82f6",
                                            state="hidden")
        self.loupe_txt = cv.create_text(0, 0, anchor="nw", fill="#ffffff", font=(F, 9),
                                        state="hidden")
        if IS_WIN:
            try:
                ov.update_idletasks()
                hwnd = user32.GetParent(ov.winfo_id()) or ov.winfo_id()
                user32.SetWindowPos(hwnd, wt.HWND(-1), self.vx, self.vy, W, H, 0x0040)
            except Exception:
                pass
        cv.bind("<ButtonPress-1>", self.down)
        cv.bind("<B1-Motion>", self.move)
        cv.bind("<ButtonRelease-1>", self.up)
        cv.bind("<Motion>", self.hover)
        cv.bind("<Leave>", lambda e: self.hide_loupe())
        cv.bind("<Button-3>", lambda e: self.cancel())
        cv.bind("<ButtonPress-2>", self.pan_start)
        cv.bind("<B2-Motion>", self.pan_move)
        cv.bind("<ButtonRelease-2>", lambda e: setattr(self, "pan", None))
        ov.bind("<MouseWheel>", self.wheel)
        ov.bind("<Shift-MouseWheel>", self.wheel_pan)
        cv.bind("<Button-4>", lambda e: self.zoom_at(e.x, e.y, +1))   # Linux
        cv.bind("<Button-5>", lambda e: self.zoom_at(e.x, e.y, -1))
        ov.bind("<Escape>", lambda e: self.cancel())
        for k in ("<plus>", "<equal>", "<KP_Add>"):
            ov.bind(k, lambda e: self.zoom_key(+1))
        for k in ("<minus>", "<KP_Subtract>"):
            ov.bind(k, lambda e: self.zoom_key(-1))
        ov.bind("<Key-0>", lambda e: self.set_view(1, 0, 0))
        for k, d in (("<Left>", (-1, 0)), ("<Right>", (1, 0)), ("<Up>", (0, -1)),
                     ("<Down>", (0, 1))):
            ov.bind(k, lambda e, d=d: self.pan_keys(*d, fine=False))
            ov.bind("<Shift-" + k[1:], lambda e, d=d: self.pan_keys(*d, fine=True))
        self.render_base()
        self._esc_watch()
        ov.focus_force()

    # ---- coordinates
    def to_px(self, x, y):
        """Canvas point -> screenshot pixel corner (rounded), clamped to the screenshot."""
        px = int(round(self.ox + x / self.z))
        py = int(round(self.oy + y / self.z))
        return min(max(px, 0), self.W), min(max(py, 0), self.H)

    def pixel_at(self, x, y):
        """Canvas point -> the screenshot pixel under it."""
        return (min(max(int(self.ox + x / self.z), 0), self.W - 1),
                min(max(int(self.oy + y / self.z), 0), self.H - 1))

    def to_canvas(self, px, py):
        return (px - self.ox) * self.z, (py - self.oy) * self.z

    def clamp_view(self):
        vw, vh = self.W / self.z, self.H / self.z
        self.ox = int(min(max(self.ox, 0), max(0, self.W - vw)))
        self.oy = int(min(max(self.oy, 0), max(0, self.H - vh)))

    # ---- drawing
    def later(self, key, fn, ms=25):
        if self._pend.get(key):
            return
        self._pend[key] = True

        def run():
            self._pend[key] = False
            if not self.done:
                fn()
        self.ov.after(ms, run)

    def render_base(self):
        z, W, H = self.z, self.W, self.H
        if z == 1:
            img = self.dim
        else:
            vw, vh = -(-W // z) + 1, -(-H // z) + 1
            reg = self.dim.crop((self.ox, self.oy, self.ox + vw, self.oy + vh))
            img = reg.resize((reg.width * z, reg.height * z), Image.NEAREST).crop((0, 0, W, H))
            if z >= 8:                               # pixel grid
                d = ImageDraw.Draw(img)
                for x in range(0, W, z):
                    d.line([(x, 0), (x, H)], fill=(40, 40, 40))
                for y in range(0, H, z):
                    d.line([(0, y), (W, y)], fill=(40, 40, 40))
        self.imgs["base"] = ImageTk.PhotoImage(img)
        self.cv.itemconfigure(self.base, image=self.imgs["base"])
        self.render_sel()
        self.render_help()

    def render_sel(self):
        cv = self.cv
        if not self.sel:
            cv.coords(self.rect, 0, 0, 0, 0)
            cv.itemconfigure(self.bright, image="")
            cv.itemconfigure(self.size_txt, text="")
            return
        x0, y0, x1, y1 = self.sel
        c0, c1 = self.to_canvas(x0, y0), self.to_canvas(x1, y1)
        cv.coords(self.rect, c0[0], c0[1], c1[0], c1[1])
        cv.coords(self.size_txt, max(0, c0[0]), max(14, c0[1] - 4))
        cv.itemconfigure(self.size_txt, text=f"{x1 - x0} × {y1 - y0} px")
        # the selected part, undimmed, only what is in view
        z = self.z
        vx0, vy0 = max(x0, self.ox), max(y0, self.oy)
        vx1 = min(x1, self.ox + -(-self.W // z) + 1)
        vy1 = min(y1, self.oy + -(-self.H // z) + 1)
        if vx1 - vx0 < 1 or vy1 - vy0 < 1:
            cv.itemconfigure(self.bright, image="")
            return
        part = self.shot.crop((vx0, vy0, vx1, vy1))
        if z > 1:
            part = part.resize((part.width * z, part.height * z), Image.NEAREST)
        self.imgs["bright"] = ImageTk.PhotoImage(part)
        cv.itemconfigure(self.bright, image=self.imgs["bright"])
        cv.coords(self.bright, *self.to_canvas(vx0, vy0))
        cv.tag_raise(self.rect)
        cv.tag_raise(self.size_txt)

    def render_help(self):
        t = (f"Zoom {self.z}×   ·   mouse wheel or + / − to zoom   ·   middle-drag or arrow keys "
             f"to move   ·   0 = whole screen   ·   Esc to cancel")
        cv = self.cv
        cv.itemconfigure(self.help_txt, text=t)
        b = cv.bbox(self.help_txt)
        if b:
            cv.coords(self.help_bg, b[0] - 10, b[1] - 6, b[2] + 10, b[3] + 6)
        cv.tag_raise(self.help_bg)
        cv.tag_raise(self.help_txt)

    def hide_loupe(self):
        for it in (self.loupe_img, self.loupe_box, self.loupe_bg, self.loupe_txt):
            self.cv.itemconfigure(it, state="hidden")

    def show_loupe(self, x, y):
        """Magnifier next to the pointer: the exact pixels around it, with a grid, the pixel
        under the pointer outlined, and its position and colour."""
        n, size = self.LOUPE_PX, self.LOUPE_SIZE
        px, py = self.pixel_at(x, y)
        h = n // 2
        reg = Image.new("RGB", (n, n), (0, 0, 0))
        src = self.shot.crop((max(0, px - h), max(0, py - h),
                              min(self.W, px + h + 1), min(self.H, py + h + 1)))
        reg.paste(src, (max(0, h - px), max(0, h - py)))
        cell = size // n
        big = reg.resize((cell * n, cell * n), Image.NEAREST)
        d = ImageDraw.Draw(big)
        for k in range(n + 1):
            d.line([(k * cell, 0), (k * cell, n * cell)], fill=(70, 70, 70))
            d.line([(0, k * cell), (n * cell, k * cell)], fill=(70, 70, 70))
        d.rectangle((h * cell, h * cell, (h + 1) * cell, (h + 1) * cell), outline=(255, 0, 254),
                    width=2)
        self.imgs["loupe"] = ImageTk.PhotoImage(big)
        r, g, b = self.shot.getpixel((px, py))[:3]
        sx, sy = px + self.vx, py + self.vy
        sel = ""
        if self.anchor is not None and self.sel:
            sel = f"\nbox {self.sel[2] - self.sel[0]} × {self.sel[3] - self.sel[1]} px"
        txt = f"{sx}, {sy}   #{r:02x}{g:02x}{b:02x}\nzoom {self.z}×{sel}"
        L = cell * n
        lx, ly = x + 28, y + 28
        if lx + L + 4 > self.W:
            lx = x - 28 - L
        if ly + L + 52 > self.H:
            ly = y - 28 - L - 52
        cv = self.cv
        cv.itemconfigure(self.loupe_img, image=self.imgs["loupe"], state="normal")
        cv.coords(self.loupe_img, lx, ly)
        cv.coords(self.loupe_box, lx, ly, lx + L, ly + L)
        cv.coords(self.loupe_bg, lx, ly + L, lx + L, ly + L + 48)
        cv.coords(self.loupe_txt, lx + 8, ly + L + 6)
        cv.itemconfigure(self.loupe_txt, text=txt, state="normal")
        for it in (self.loupe_box, self.loupe_bg):
            cv.itemconfigure(it, state="normal")
        for it in (self.loupe_img, self.loupe_box, self.loupe_bg, self.loupe_txt):
            cv.tag_raise(it)

    # ---- view
    def set_view(self, z, ox, oy):
        self.z, self.ox, self.oy = z, ox, oy
        self.clamp_view()
        self.render_base()

    def zoom_at(self, x, y, step):
        zs = self.ZOOMS
        i = zs.index(self.z) if self.z in zs else 0
        i = min(max(i + step, 0), len(zs) - 1)
        nz = zs[i]
        if nz == self.z:
            return
        fx, fy = self.ox + x / self.z, self.oy + y / self.z      # keep this point in place
        self.set_view(nz, int(round(fx - x / nz)), int(round(fy - y / nz)))
        self.show_loupe(x, y)

    def zoom_key(self, step):
        try:
            x = self.ov.winfo_pointerx() - self.ov.winfo_rootx()
            y = self.ov.winfo_pointery() - self.ov.winfo_rooty()
        except Exception:
            x, y = self.W // 2, self.H // 2
        self.zoom_at(x, y, step)

    def wheel(self, e):
        x = e.x_root - self.ov.winfo_rootx()
        y = e.y_root - self.ov.winfo_rooty()
        self.zoom_at(x, y, 1 if e.delta > 0 else -1)

    def wheel_pan(self, e):
        self.ox -= (1 if e.delta > 0 else -1) * max(1, self.W // (8 * self.z))
        self.clamp_view()
        self.later("base", self.render_base, 15)

    def pan_keys(self, dx, dy, fine=False):
        step = 1 if fine else max(1, self.W // (8 * self.z))
        self.ox += dx * step
        self.oy += dy * step
        self.clamp_view()
        self.render_base()

    def pan_start(self, e):
        self.pan = (e.x, e.y, self.ox, self.oy)

    def pan_move(self, e):
        if not self.pan:
            return
        x0, y0, ox, oy = self.pan
        self.ox, self.oy = ox - (e.x - x0) / self.z, oy - (e.y - y0) / self.z
        self.clamp_view()
        self.later("base", self.render_base, 15)

    # ---- the box
    def hover(self, e):
        self.later("loupe", lambda: self.show_loupe(e.x, e.y), 15)

    def down(self, e):
        self.anchor = self.to_px(e.x, e.y)
        self.sel = None
        for it in (self.prompt_bg, self.prompt_txt, self.cancel_win):
            self.cv.itemconfigure(it, state="hidden")
        self.render_sel()

    def norm(self, a, b):
        return (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))

    def move(self, e):
        if self.anchor is None:
            return
        # dragging near an edge while zoomed in moves the view along
        if self.z > 1:
            m, step = 24, max(1, 16 // self.z)
            dx = -step if e.x < m else step if e.x > self.W - m else 0
            dy = -step if e.y < m else step if e.y > self.H - m else 0
            if dx or dy:
                self.ox += dx
                self.oy += dy
                self.clamp_view()
                self.later("base", self.render_base, 30)
        self.sel = self.norm(self.anchor, self.to_px(e.x, e.y))
        self.later("sel", self.render_sel, 25)
        self.later("loupe", lambda: self.show_loupe(e.x, e.y), 15)

    def up(self, e):
        if self.anchor is None:
            return
        b = self.norm(self.anchor, self.to_px(e.x, e.y))
        self.anchor = None
        m = self.min_size
        if b[2] - b[0] < m or b[3] - b[1] < m:
            self.sel = None
            self.render_sel()
            self.cv.itemconfigure(self.prompt_txt, state="normal",
                                  text=f"That box is too small (at least {m} × {m} pixels). Zoom "
                                       f"in with the mouse wheel for small pictures, then drag "
                                       f"again, or press Esc to cancel")
            bx = self.cv.bbox(self.prompt_txt)
            self.cv.coords(self.prompt_bg, bx[0] - 18, bx[1] - 10, bx[2] + 18, bx[3] + 10)
            for it in (self.prompt_bg, self.cancel_win):
                self.cv.itemconfigure(it, state="normal")
            self.cv.coords(self.cancel_win, bx[2] + 30, 34)
            return
        self.close()
        self.on_done(b)

    def close(self):
        self.done = True
        try:
            self.ov.destroy()
        except Exception:
            pass
        self.imgs = {}

    def cancel(self):
        if self.done:
            return
        self.close()
        self.on_cancel()

    def _esc_watch(self):
        if self.done:
            return
        try:
            if not self.ov.winfo_exists():
                return
        except Exception:
            return
        if key_down(VK_ESCAPE):
            self.cancel()
            return
        self.ov.after(80, self._esc_watch)


HUMAN_CHOICES = (("default", "Mouse movement: as in Preferences"),
                 ("human", "Move the mouse there like a person"),
                 ("jump", "Jump straight to the spot"))


def human_choice(v):
    return "human" if v is True else "jump" if v is False else "default"


def human_value(choice):
    return True if choice == "human" else False if choice == "jump" else None


class Dialog(tk.Toplevel):
    """Resizable dialog. Content goes in self.body (scrolls when the window is too
    short); buttons go in self.footer, which always stays visible at the bottom."""

    def __init__(self, app, title, parent=None):
        master = parent if parent is not None else app.root
        super().__init__(master)
        self.app = app
        self.withdraw()
        self.title(title)
        self.resizable(True, True)
        try:
            if master.winfo_viewable():
                self.transient(master)       # stays on top of the window it came from
        except Exception:
            pass
        self._hold = 0
        self._initial = None
        self.bind("<Escape>", lambda e: self.destroy())
        close_on_click_outside(self, app, self.outside_click)
        p = app.pal

        self.footer = ttk.Frame(self, padding=(14, 10, 14, 12))
        self.footer.pack(side="bottom", fill="x")
        ttk.Separator(self).pack(side="bottom", fill="x")
        grip = ttk.Sizegrip(self.footer)
        grip.pack(side="right", anchor="se", padx=(8, 0))

        wrap = ttk.Frame(self)
        wrap.pack(side="top", fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, highlightthickness=0, bd=0, bg=p["bg"])
        self.vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.body = ttk.Frame(self.canvas, padding=14)
        self._win = self.canvas.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self._sync_scroll())
        self.canvas.bind("<Configure>", lambda e: self._sync_scroll())
        self.bind("<MouseWheel>", self._on_wheel)          # Windows / macOS
        self.bind("<Button-4>", lambda e: self._scroll(-3))  # Linux
        self.bind("<Button-5>", lambda e: self._scroll(3))

    def geom_key(self):
        return type(self).__name__

    def destroy(self):
        """Remember this dialog's size and position for next time."""
        try:
            if self.winfo_viewable() and self.state() == "normal":
                saved = dict(self.app.settings.get("dlg_geom") or {})
                saved[self.geom_key()] = self.geometry()
                self.app.settings["dlg_geom"] = saved
                self.app.save()
        except Exception:
            pass
        super().destroy()

    def _sync_scroll(self):
        c = self.canvas
        need_h = self.body.winfo_reqheight()
        c.itemconfigure(self._win, width=max(c.winfo_width(), self.body.winfo_reqwidth()))
        c.configure(scrollregion=(0, 0, self.body.winfo_reqwidth(), need_h))
        if need_h > c.winfo_height() + 1:
            if not self.vsb.winfo_ismapped():
                self.vsb.pack(side="right", fill="y", before=c)
        elif self.vsb.winfo_ismapped():
            self.vsb.pack_forget()
            c.yview_moveto(0)

    def _scroll(self, units):
        if self.vsb.winfo_ismapped():
            self.canvas.yview_scroll(units, "units")

    def _on_wheel(self, e):
        w = e.widget
        if isinstance(w, (ttk.Combobox, ttk.Spinbox)) and str(w.cget("state")) != "disabled":
            return  # let the wheel change the value in a spin box
        self._scroll(-1 if e.delta > 0 else 1)

    def finish(self):
        self.app.theme_window(self)
        self.canvas.configure(bg=self.app.pal["bg"])
        self.update_idletasks()
        bw = self.body.winfo_reqwidth() + 20
        bh = self.body.winfo_reqheight() + self.footer.winfo_reqheight() + 4
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w = min(bw, sw - 40)
        h = min(bh, sh - 120)                 # leave room for the taskbar and title bar
        self.minsize(min(w, 420), min(h, 260))
        r = self.app.root
        if self.app.main_visible():
            x = r.winfo_rootx() + (r.winfo_width() - w) // 2
            y = r.winfo_rooty() + (r.winfo_height() - h) // 3
        else:
            x, y = (sw - w) // 2, (sh - h) // 3
        x = min(max(0, x), max(0, sw - w))
        y = min(max(0, y), max(0, sh - h - 60))
        saved = fit_geometry((self.app.settings.get("dlg_geom") or {}).get(self.geom_key()),
                             min(w, 420), min(h, 260))
        self.geometry(saved or f"{w}x{h}+{x}+{y}")
        self.deiconify()
        self.lift()
        self.focus_force()
        self.after(50, self._sync_scroll)
        self.after(100, self._take_snapshot)

    # ---- unsaved-change protection for click-outside
    def _snapshot(self):
        vals = {}
        for k, v in vars(self).items():
            try:
                if isinstance(v, tk.Variable):
                    vals[k] = str(v.get())
                elif isinstance(v, list) and v and all(isinstance(x, tk.Variable) for x in v):
                    vals[k] = tuple(str(x.get()) for x in v)
            except Exception:
                vals[k] = "?"
        for k in ("snap_png", "watch_png", "snap_spot", "watch_area", "steps", "step"):
            if hasattr(self, k):
                vals[k] = str(getattr(self, k))
        return vals

    def _take_snapshot(self):
        try:
            self._initial = self._snapshot()
        except Exception:
            self._initial = None

    def has_unsaved(self):
        return self._initial is not None and self._snapshot() != self._initial

    def outside_click(self):
        if self.has_unsaved():
            # Don't throw away edits - stay open and point at Save / Cancel
            self.bell()
            self.lift()
            self.focus_force()
            if not getattr(self, "_unsaved_lbl", None):
                self._unsaved_lbl = ttk.Label(self.footer, style="Warn.TLabel",
                                              text="Unsaved changes: Save or Cancel")
            if not self._unsaved_lbl.winfo_ismapped():
                self._unsaved_lbl.pack(side="left")
            return
        self.destroy()


class StepsEditor:
    """The editable timeline of steps, used by the job editor and the step-group editor.
    Blocks (If / Otherwise / End, Repeat / End) are indented; recorded steps show when they
    happened in the recording."""
    ADD_MENU = (("click", "Click a spot"), ("wait", "Wait"), ("waitpic", "Wait for a picture"),
                ("type", "Type text"), ("paste", "Paste text"), ("key", "Press keys"), None,
                ("if", "If … (then End)"), ("else", "Otherwise (inside an If)"),
                ("repeat", "Repeat … (then End)"), ("set", "Set a variable"),
                ("group", "Use a step group"), None,
                ("scroll", "Scroll"), ("drag", "Drag"), ("move", "Move the mouse"),
                ("mouse", "Mouse button down / up"), ("keyhold", "Hold a key down / let go"))

    def __init__(self, app, window, parent, steps, title, intro, allow_groups=True):
        self.app, self.window, self.steps = app, window, steps
        self.allow_groups = allow_groups
        self.insert_at = None
        g = ttk.LabelFrame(parent, text=title, padding=(12, 8))
        g.pack(fill="x", pady=(12, 0))
        self.frame = g
        ttk.Label(g, style="Muted.TLabel", wraplength=600, justify="left", text=intro).pack(
            anchor="w")
        tf = ttk.Frame(g, style="Card.TFrame", padding=1)
        tf.pack(fill="x", pady=(6, 6))
        self.tree = ttk.Treeview(tf, columns=("n", "at", "what", "detail"), show="headings",
                                 height=7, selectmode="extended")
        enable_column_fit(self.tree)
        for c, h, w, st in (("n", "#", 40, False), ("at", "At", 56, False),
                            ("what", "Step", 150, False), ("detail", "Details", 380, True)):
            self.tree.heading(c, text=h, anchor="w")
            self.tree.column(c, width=w, minwidth=30, stretch=st, anchor="w")
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="x", side="left", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.tree.bind("<Delete>", lambda e: self.remove())
        br = ttk.Frame(g)
        br.pack(fill="x")
        self.add_btn = ttk.Button(br, text="＋ Add step  ▾", style="Small.TButton",
                                  command=self.show_add_menu)
        self.add_btn.pack(side="left")
        self.add_menu = tk.Menu(window, tearoff=0)
        for item in self.ADD_MENU:
            if item is None:
                self.add_menu.add_separator()
            elif item[0] != "group" or allow_groups:
                self.add_menu.add_command(label=item[1], command=lambda k=item[0]: self.add(k))
        for text, cmd in (("Edit", self.edit), ("Duplicate", self.duplicate),
                          ("Remove", self.remove), ("▲", lambda: self.move(-1)),
                          ("▼", lambda: self.move(1))):
            ttk.Button(br, text=text, style="Small.TButton", command=cmd).pack(side="left",
                                                                              padx=(4, 0))
        self.tools_btn = ttk.Button(br, text="More  ▾", style="Small.TButton",
                                    command=self.show_tools_menu)
        self.tools_btn.pack(side="right")
        self.tools_menu = tk.Menu(window, tearoff=0)
        self.problem = ttk.Label(g, style="Warn.TLabel", wraplength=600, justify="left")
        self.refresh()

    # ---- menus
    def show_add_menu(self):
        b = self.add_btn
        self.add_menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + 2)

    def show_tools_menu(self):
        m = self.tools_menu
        m.delete(0, "end")
        m.add_command(label="Make all waits shorter (× 0.5)", command=lambda: self.scale_waits(0.5))
        m.add_command(label="Make all waits longer (× 2)", command=lambda: self.scale_waits(2))
        m.add_command(label="Remove waits shorter than 0.5 s", command=self.drop_short_waits)
        m.add_command(label="Remove mouse movements", command=self.drop_moves)
        if self.allow_groups:
            m.add_separator()
            m.add_command(label="Save selected steps as a group…", command=self.save_as_group)
        b = self.tools_btn
        m.tk_popup(b.winfo_rootx() + b.winfo_width() - 240, b.winfo_rooty() + b.winfo_height() + 2)

    # ---- list
    def refresh(self, select=None):
        tr = self.tree
        tr.delete(*tr.get_children())
        depths = step_depths(self.steps)
        groups = getattr(self.app, "groups", [])
        for i, st in enumerate(self.steps):
            what, det = describe_step(st, groups=groups)
            at = st.get("rec_t")
            at = f"{at:.1f}s" if isinstance(at, (int, float)) else ""
            tr.insert("", "end", iid=str(i), values=(i + 1, at, "    " * depths[i] + what, det))
        _, errors = parse_blocks(self.steps)
        if errors:
            self.problem.configure(text="⚠ " + errors[0])
            if not self.problem.winfo_ismapped():
                self.problem.pack(anchor="w", pady=(6, 0))
        elif self.problem.winfo_ismapped():
            self.problem.pack_forget()
        if select is not None and 0 <= select < len(self.steps):
            tr.selection_set(str(select))
            tr.see(str(select))

    def selected(self):
        return sorted(int(i) for i in self.tree.selection())

    def first_selected(self):
        sel = self.selected()
        return sel[0] if sel else None

    def errors(self):
        return parse_blocks(self.steps)[1]

    # ---- editing
    def add(self, kind):
        i = self.first_selected()
        sel = self.selected()
        self.insert_at = (sel[-1] + 1) if sel else len(self.steps)
        if kind in ("else", "end"):
            self.steps.insert(self.insert_at, {"type": kind})
            self.refresh(self.insert_at)
            return
        if kind == "group" and not getattr(self.app, "groups", []):
            messagebox.showinfo(APP_NAME, "There are no step groups yet. Select some steps and "
                                          "use More → Save selected steps as a group…",
                                parent=self.window)
            return
        StepDialog(self.app, self, {"type": kind})
        del i

    def step_saved(self, step, index=None):
        if index is None:
            at = self.insert_at if self.insert_at is not None else len(self.steps)
            at = min(max(0, at), len(self.steps))
            self.steps.insert(at, step)
            if step.get("type") in ("if", "repeat"):
                self.steps.insert(at + 1, {"type": "end"})
            index = at
            self.insert_at = None
        else:
            self.steps[index] = step
        self.refresh(index)

    def edit(self):
        i = self.first_selected()
        if i is None:
            return
        if self.steps[i].get("type") in ("else", "end"):
            return
        StepDialog(self.app, self, copy.deepcopy(self.steps[i]), i)

    def duplicate(self):
        sel = self.selected()
        if not sel:
            return
        block = [copy.deepcopy(self.steps[i]) for i in sel]
        at = sel[-1] + 1
        self.steps[at:at] = block
        self.refresh(at)

    def remove(self):
        sel = self.selected()
        if not sel:
            return
        for i in reversed(sel):
            del self.steps[i]
        self.refresh(min(sel[0], len(self.steps) - 1))

    def move(self, d):
        sel = self.selected()
        if not sel:
            return
        lo, hi = sel[0], sel[-1]
        if lo + d < 0 or hi + d >= len(self.steps):
            return
        block = self.steps[lo:hi + 1]
        del self.steps[lo:hi + 1]
        self.steps[lo + d:lo + d] = block
        self.refresh()
        for k in range(lo + d, hi + d + 1):
            self.tree.selection_add(str(k))
        self.tree.see(str(lo + d))

    def scale_waits(self, f):
        for st in self.steps:
            if st.get("type") == "wait":
                st["min"] = round(st.get("min", 1) * f, 1)
                st["max"] = round(st.get("max", st.get("min", 1)) * f, 1)
            elif st.get("type") in ("move", "drag"):
                st["path"] = [[round(p[0] * f, 3), p[1], p[2]] for p in st.get("path", [])]
        self.refresh()

    def drop_short_waits(self):
        self.steps[:] = [s for s in self.steps
                         if not (s.get("type") == "wait" and s.get("max", 1) < 0.5)]
        self.refresh()

    def drop_moves(self):
        self.steps[:] = [s for s in self.steps if s.get("type") != "move"]
        self.refresh()

    def save_as_group(self):
        sel = self.selected()
        chosen = [self.steps[i] for i in sel] if sel else list(self.steps)
        if not chosen:
            return
        if any(s.get("type") == "group" for s in chosen):
            messagebox.showerror(APP_NAME, "A step group can't contain “Use a step group” steps.",
                                 parent=self.window)
            return
        if parse_blocks(chosen)[1]:
            messagebox.showerror(APP_NAME, "Select whole blocks (an If or Repeat together with "
                                           "its End).", parent=self.window)
            return

        def done(name):
            g = {"id": uuid.uuid4().hex, "name": name, "steps": copy.deepcopy(chosen)}
            with self.app.lock:
                self.app.groups.append(g)
            self.app.save()
            if sel and messagebox.askyesno(
                    APP_NAME, f"Saved the group “{name}”. Replace the selected steps here with "
                              f"one “Use group” step?", parent=self.window):
                lo = sel[0]
                for i in reversed(sel):
                    del self.steps[i]
                self.steps.insert(lo, {"type": "group", "group_id": g["id"], "retries": 0,
                                       "retry_wait": 2, "on_fail": "stop", "careful": False})
                self.refresh(lo)
        TextPrompt(self.app, self.window, "Save as a step group",
                   "Name for this group of steps (you can reuse it in other jobs):",
                   f"Group {len(getattr(self.app, 'groups', [])) + 1}", done)


class TextPrompt(Dialog):
    """Ask for one line of text."""

    def __init__(self, app, parent, title, prompt, initial, on_ok):
        super().__init__(app, title, parent)
        self.on_ok = on_ok
        ttk.Label(self.body, text=prompt, wraplength=420, justify="left").pack(anchor="w")
        self.v = tk.StringVar(value=initial)
        e = ttk.Entry(self.body, textvariable=self.v, width=44)
        e.pack(anchor="w", pady=(8, 0), fill="x")
        e.bind("<Return>", lambda ev: self.ok())
        ttk.Button(self.footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(self.footer, text="OK", style="Accent.TButton", command=self.ok).pack(
            side="right", padx=6)
        self.finish()
        e.focus_set()
        e.select_range(0, "end")

    def ok(self):
        v = self.v.get().strip()[:MAX_NAME]
        if not v:
            self.bell()
            return
        self.destroy()
        self.on_ok(v)


class JobEditor(Dialog):
    def __init__(self, app, job, is_new, start_on=None):
        self.kind = "watch" if is_watch(job) else "click"
        title = ("New screen watcher" if self.kind == "watch" else "New click") if is_new \
            else f"Edit - {job['name']}"
        super().__init__(app, title)
        self.job, self.is_new = job, is_new
        self.watch_png = job.get("watch_png", "")
        self.watch_area = copy.deepcopy(job.get("watch_area"))
        self.watch_area_screen = copy.deepcopy(job.get("watch_area_screen"))
        self.steps = copy.deepcopy(job.get("steps") or [])
        self._wthumb = None
        self.window_class = job.get("window_class", "")
        self.client_size = (job.get("client_w", 0), job.get("client_h", 0))
        self.pick_screen = job.get("pick_screen")
        self.snap_png = job.get("snap_png", "")
        self.snap_spot = job.get("snap_spot")
        self.pick_dpi = job.get("pick_dpi")
        self._thumb = None
        f = self.body

        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Name", width=8).pack(side="left")
        self.v_name = tk.StringVar(value=job["name"])
        ttk.Entry(row, textvariable=self.v_name, width=40).pack(side="left")

        if self.kind == "watch":
            self.build_watch_section(f, job)

        # ---------------- where to click
        g = ttk.LabelFrame(f, text="Button to click when the picture disappears"
                           if self.kind == "watch" else "Where to click", padding=(12, 8))
        self.where_frame = g
        g.pack(fill="x", pady=(12, 0))
        self.v_main = tk.BooleanVar(value=bool(job.get("main_click", True)))
        ttk.Checkbutton(g, variable=self.v_main, command=self.main_toggled, text=(
            "Click a button when this happens (off: only run the steps below)"
            if self.kind == "watch" else
            "Start with a click on this spot (off: only run the steps below)")).pack(
            anchor="w", pady=(0, 6))
        top = ttk.Frame(g)
        top.pack(fill="x")
        ttk.Button(top, text="◎  Pick on screen…", style="Accent.TButton",
                   command=self.pick).pack(side="left")
        ttk.Button(top, text="Show spot", command=self.preview_spot).pack(side="left", padx=6)
        self.pick_info = ttk.Label(g, style="Muted.TLabel", wraplength=520, justify="left")
        self.pick_info.pack(anchor="w", pady=(8, 6))

        pic = ttk.Frame(g)
        pic.pack(fill="x", pady=(0, 8))
        self.thumb_lbl = ttk.Label(pic, style="Thumb.TLabel", anchor="center", width=26)
        self.thumb_lbl.pack(side="left", anchor="n")
        opts = ttk.Frame(pic, padding=(12, 0, 0, 0))
        opts.pack(side="left", fill="x", expand=True, anchor="n")
        self.v_use_img = tk.BooleanVar(value=bool(job.get("use_image", True)) and HAVE_CV)
        cb = ttk.Checkbutton(opts, text="Find the spot by its picture  (scans the screen for "
                                        "it before each click)", variable=self.v_use_img,
                             command=self.update_info)
        cb.pack(anchor="w")
        if not HAVE_CV:
            cb.state(["disabled"])
            ttk.Label(opts, style="Warn.TLabel", wraplength=330, text=(
                "Picture matching needs opencv-python-headless and numpy. Start "
                "Clickue.bat installs them.")).pack(anchor="w", pady=(4, 0))
        r = ttk.Frame(opts)
        r.pack(anchor="w", pady=(6, 0))
        ttk.Label(r, text="Picture size").pack(side="left")
        self.v_snap_size = tk.StringVar(value=job.get("snap_size", "Medium"))
        ttk.Combobox(r, values=tuple(SNAP_SIZES), state="readonly", width=8,
                     textvariable=self.v_snap_size).pack(side="left", padx=6)
        ttk.Label(r, text="(used the next time you pick)", style="Muted.TLabel").pack(side="left")
        self.v_exact = tk.BooleanVar(value=bool(job.get("exact_match", True)))
        ttk.Checkbutton(opts, text="Only the exact picture  (never click a similar-looking "
                                   "one; recommended)", variable=self.v_exact).pack(
            anchor="w", pady=(6, 0))
        r = ttk.Frame(opts)
        r.pack(anchor="w", pady=(6, 0))
        ttk.Label(r, text="If the picture can't be found").pack(side="left")
        self.v_fallback = tk.StringVar(value="Click the saved position"
                                       if job.get("image_fallback") == "position"
                                       else "Wait and retry")
        ttk.Combobox(r, values=("Wait and retry", "Click the saved position"), state="readonly",
                     width=22, textvariable=self.v_fallback).pack(side="left", padx=6)
        ttk.Label(opts, style="Muted.TLabel", wraplength=330, justify="left", text=(
            "Tip: pick a spot with some text or an icon nearby. Plain empty areas look the "
            "same everywhere and can't be found reliably.")).pack(anchor="w", pady=(6, 0))

        ttk.Label(g, text="Saved position  (helps choose between look-alikes, and is the "
                          "fallback)", style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        self.v_mode = tk.StringVar(value=job.get("target_mode", "screen"))
        self.rb_win = ttk.Radiobutton(
            g, text="Inside a window  (recommended: follows the window if it moves or the "
                    "screen size changes)", variable=self.v_mode, value="window",
            command=self.mode_changed)
        self.rb_win.pack(anchor="w", pady=(2, 0))
        self.win_box = ttk.Frame(g, padding=(24, 4, 0, 6))
        r1 = ttk.Frame(self.win_box)
        r1.pack(anchor="w", pady=2)
        ttk.Label(r1, text="Window title contains").pack(side="left")
        self.v_title = tk.StringVar(value=job.get("window_title", ""))
        ttk.Entry(r1, textvariable=self.v_title, width=34).pack(side="left", padx=6)
        r2 = ttk.Frame(self.win_box)
        r2.pack(anchor="w", pady=2)
        ttk.Label(r2, text="Spot inside the window   X").pack(side="left")
        self.v_rx = tk.IntVar(value=job.get("rel_x", 0))
        self.v_ry = tk.IntVar(value=job.get("rel_y", 0))
        ttk.Spinbox(r2, from_=-10000, to=20000, width=7, textvariable=self.v_rx).pack(
            side="left", padx=6)
        ttk.Label(r2, text="Y").pack(side="left")
        ttk.Spinbox(r2, from_=-10000, to=20000, width=7, textvariable=self.v_ry).pack(
            side="left", padx=6)
        self.v_front = tk.BooleanVar(value=job.get("bring_to_front", True))
        ttk.Checkbutton(self.win_box, text="Bring the window to the front before clicking",
                        variable=self.v_front).pack(anchor="w", pady=2)
        self.v_scale_w = tk.BooleanVar(value=job.get("scale_with_window", False))
        ttk.Checkbutton(self.win_box, text="Adjust the spot if the window changes size",
                        variable=self.v_scale_w).pack(anchor="w", pady=2)

        self.rb_scr = ttk.Radiobutton(g, text="Fixed screen position", variable=self.v_mode,
                                      value="screen", command=self.mode_changed)
        self.rb_scr.pack(anchor="w", pady=(4, 0))
        self.scr_box = ttk.Frame(g, padding=(24, 4, 0, 2))
        r3 = ttk.Frame(self.scr_box)
        r3.pack(anchor="w", pady=2)
        ttk.Label(r3, text="Screen   X").pack(side="left")
        self.v_x = tk.IntVar(value=job["x"])
        self.v_y = tk.IntVar(value=job["y"])
        ttk.Spinbox(r3, from_=-10000, to=20000, width=7, textvariable=self.v_x).pack(
            side="left", padx=6)
        ttk.Label(r3, text="Y").pack(side="left")
        ttk.Spinbox(r3, from_=-10000, to=20000, width=7, textvariable=self.v_y).pack(
            side="left", padx=6)
        self.v_scale_s = tk.BooleanVar(value=job.get("scale_with_screen", False))
        ttk.Checkbutton(self.scr_box, text="Adjust the spot if the screen resolution changes",
                        variable=self.v_scale_s).pack(anchor="w", pady=2)

        # ---------------- click
        g2 = ttk.LabelFrame(f, text="Click", padding=(12, 8))
        self.click_frame = g2
        g2.pack(fill="x", pady=(12, 0))
        self.v_button = tk.StringVar(value=job["button"])
        ttk.Combobox(g2, values=("left", "right", "middle"), state="readonly", width=8,
                     textvariable=self.v_button).pack(side="left")
        self.v_clicks = tk.StringVar(value="double" if job["clicks"] == 2 else "single")
        ttk.Combobox(g2, values=("single", "double"), state="readonly", width=8,
                     textvariable=self.v_clicks).pack(side="left", padx=6)
        # 4.5.6: move the mouse like a person (for this job's click and its click steps)
        labels = dict(HUMAN_CHOICES)
        self.v_human = tk.StringVar(value=labels[human_choice(job.get("human_move"))])
        ttk.Combobox(g2, values=[t for _, t in HUMAN_CHOICES], state="readonly", width=36,
                     textvariable=self.v_human).pack(side="left", padx=(6, 0))

        # ---------------- schedule (scheduled clicks only)
        g3 = ttk.LabelFrame(f, text="Schedule", padding=(12, 8))
        if self.kind == "click":
            g3.pack(fill="x", pady=(12, 0))
        sg1 = ttk.Frame(g3)
        sg1.pack(fill="x")
        self.interval = self.hms_row(sg1, 0, "Scheduled every", job["interval_s"])
        self.v_random = tk.BooleanVar(value=job.get("random_on", True))
        ttk.Checkbutton(g3, text="Add a random delay after each scheduled time",
                        variable=self.v_random, command=self.random_toggled).pack(
            anchor="w", pady=(8, 2))
        sg2 = ttk.Frame(g3)
        sg2.pack(fill="x")
        self.dmin = self.hms_row(sg2, 0, "Random delay from", job["delay_min_s"])
        self.dmax = self.hms_row(sg2, 1, "Random delay up to", job["delay_max_s"])
        sg3 = ttk.Frame(g3)
        sg3.pack(fill="x", pady=(6, 0))
        sg3.columnconfigure(0, minsize=190)
        ttk.Label(sg3, text="First scheduled time").grid(row=0, column=0, sticky="w", pady=3,
                                                         padx=(0, 10))
        self.v_first = tk.StringVar(value=job.get("first_time", ""))
        ttk.Entry(sg3, textvariable=self.v_first, width=8).grid(row=0, column=1, sticky="w")
        ttk.Label(sg3, text="HH:MM (24h), or blank = one interval from now",
                  style="Muted.TLabel").grid(row=0, column=2, sticky="w", padx=8)
        self.v_anchor = tk.BooleanVar(value=job.get("anchored", True))
        self.anchor_cb = ttk.Checkbutton(g3, text="Keep a fixed schedule (random delays don't "
                                                  "push later clicks later)",
                                         variable=self.v_anchor)
        self.anchor_cb.pack(anchor="w", pady=(6, 0))
        self.preview = ttk.Label(g3, style="Muted.TLabel", wraplength=520, justify="left")
        self.preview.pack(anchor="w", fill="x", pady=(6, 0))
        g3.bind("<Configure>", lambda e: self.preview.configure(
            wraplength=max(300, e.width - 30)))

        self.build_hours_section(f, job)
        self.build_steps_section(f, job)

        self.build_run_options(f, job)
        self.v_enabled = tk.BooleanVar(value=(job.get("enabled", False) or is_new)
                                       if start_on is None else start_on)
        ttk.Checkbutton(f, text="Start watching when I save" if self.kind == "watch"
                        else "Start this schedule when I save",
                        variable=self.v_enabled).pack(anchor="w", pady=(10, 0))

        b = self.footer
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Save", style="Accent.TButton", command=self.on_save).pack(
            side="right", padx=6)
        ttk.Button(b, text="Dry run", command=self.dry_run_steps).pack(side="left")
        ttk.Button(b, text="Step through…", command=self.step_through).pack(side="left", padx=6)

        self.mode_changed()
        self.main_toggled()
        self.update_info()
        self.update_thumb()
        self.random_toggled()
        if self.kind == "watch":
            self.update_watch_thumb()
            self.watch_random_toggled()
            self.watch_cool_toggled()
            self.trigger_changed()
            self.update_area_info()
        self.hours_toggled()
        self.refresh_steps()
        self.finish()

    # ---- when it may run
    def build_hours_section(self, f, job):
        g = ttk.LabelFrame(f, text="When it may run", padding=(12, 8))
        g.pack(fill="x", pady=(12, 0))
        self.v_hours = tk.BooleanVar(value=bool(job.get("hours_on")))
        ttk.Checkbutton(g, text="Only run during set hours and days", variable=self.v_hours,
                        command=self.hours_toggled).pack(anchor="w")
        self.hours_widgets = []
        r1 = ttk.Frame(g, padding=(24, 4, 0, 0))
        r1.pack(anchor="w")
        lbl = ttk.Label(r1, text="From")
        lbl.pack(side="left")
        self.v_hfrom = tk.StringVar(value=job.get("hours_from", "08:00"))
        e1 = ttk.Entry(r1, textvariable=self.v_hfrom, width=6)
        e1.pack(side="left", padx=6)
        lbl2 = ttk.Label(r1, text="to")
        lbl2.pack(side="left")
        self.v_hto = tk.StringVar(value=job.get("hours_to", "22:00"))
        e2 = ttk.Entry(r1, textvariable=self.v_hto, width=6)
        e2.pack(side="left", padx=6)
        lbl3 = ttk.Label(r1, text="24h, e.g. 08:00 to 22:00 (22:00 to 06:00 runs overnight; "
                                  "same time = all day)", style="Muted.TLabel")
        lbl3.pack(side="left", padx=6)
        r2 = ttk.Frame(g, padding=(24, 4, 0, 0))
        r2.pack(anchor="w")
        days = set(job.get("hours_days") or range(7))
        self.v_days = []
        for i, dn in enumerate(DAY_NAMES):
            v = tk.BooleanVar(value=i in days)
            cb = ttk.Checkbutton(r2, text=dn, variable=v)
            cb.pack(side="left", padx=(0, 8))
            self.v_days.append(v)
            self.hours_widgets.append(cb)
        self.hours_widgets += [lbl, e1, lbl2, e2, lbl3]
        self.v_outside = tk.StringVar(value="Skip that click" if job.get("hours_outside") == "skip"
                                      else "Wait until the hours start, then click")
        if self.kind == "click":
            r3 = ttk.Frame(g, padding=(24, 4, 0, 0))
            r3.pack(anchor="w")
            l4 = ttk.Label(r3, text="If a click comes due outside these hours")
            l4.pack(side="left")
            cbx = ttk.Combobox(r3, textvariable=self.v_outside, state="readonly", width=34,
                               values=("Wait until the hours start, then click",
                                       "Skip that click"))
            cbx.pack(side="left", padx=6)
            self.hours_widgets += [l4, cbx]
        else:
            ttk.Label(g, style="Muted.TLabel", padding=(24, 2, 0, 0),
                      text="Outside these hours the watcher doesn't look or click.").pack(
                anchor="w")
        ttk.Separator(g).pack(fill="x", pady=8)
        r4 = ttk.Frame(g)
        r4.pack(anchor="w")
        self.v_lim_on = tk.BooleanVar(value=bool(job.get("limit_clicks_on")))
        ttk.Checkbutton(r4, text="Stop after", variable=self.v_lim_on).pack(side="left")
        self.v_lim_n = tk.IntVar(value=int(job.get("limit_clicks", 10)))
        ttk.Spinbox(r4, from_=1, to=100000, width=7, textvariable=self.v_lim_n).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r4, text="clicks (counted from when the job is started)",
                  style="Muted.TLabel").pack(side="left")
        r5 = ttk.Frame(g)
        r5.pack(anchor="w", pady=(4, 0))
        self.v_until_on = tk.BooleanVar(value=bool(job.get("limit_until_on")))
        ttk.Checkbutton(r5, text="Stop at", variable=self.v_until_on).pack(side="left")
        default_until = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        self.v_until = tk.StringVar(value=job.get("limit_until") or default_until)
        ttk.Entry(r5, textvariable=self.v_until, width=17).pack(side="left", padx=6)
        ttk.Label(r5, text="YYYY-MM-DD HH:MM", style="Muted.TLabel").pack(side="left")

    def hours_toggled(self):
        on = bool(self.v_hours.get())
        for w in self.hours_widgets:
            try:
                w.state(["!disabled"] if on else ["disabled"])
            except Exception:
                pass
        for w in self.hours_widgets:
            if isinstance(w, ttk.Combobox) and on:
                w.state(["readonly"])

    # ---- extra steps (the timeline)
    def build_steps_section(self, f, job):
        self.stepsed = StepsEditor(
            self.app, self, f, self.steps, "Steps (optional)",
            "Run in order after the click above (or on their own if that click is off): click "
            "other spots, wait, wait for a picture, type or paste text, press keys, scroll or "
            "drag, branch with If, repeat with Repeat, or reuse a saved step group. Recorded "
            "macros appear here too, ready to edit.")

    @staticmethod
    def describe_step(st):
        return describe_step(st)

    def refresh_steps(self):
        self.stepsed.refresh()

    def main_toggled(self):
        on = bool(self.v_main.get())

        def walk(w):
            for c in w.winfo_children():
                if isinstance(c, ttk.Checkbutton) and str(c.cget("variable")) == str(self.v_main):
                    continue
                try:
                    if isinstance(c, ttk.Combobox):
                        c.state(["!disabled", "readonly"] if on else ["disabled"])
                    else:
                        c.state(["!disabled"] if on else ["disabled"])
                except Exception:
                    pass
                walk(c)
        for fr in (self.where_frame, self.click_frame):
            walk(fr)
        if on:
            self.mode_changed()

    def build_run_options(self, f, job):
        g = ttk.LabelFrame(f, text="Run options", padding=(12, 8))
        g.pack(fill="x", pady=(12, 0))
        r = ttk.Frame(g)
        r.pack(anchor="w")
        ttk.Label(r, text="Priority when several jobs are due").pack(side="left")
        self.v_prio = tk.StringVar(value={"high": "High", "low": "Low"}.get(
            job.get("priority"), "Normal"))
        ttk.Combobox(r, values=("High", "Normal", "Low"), state="readonly", width=8,
                     textvariable=self.v_prio).pack(side="left", padx=6)
        ttk.Label(r, text="(only one job uses the mouse and keyboard at a time)",
                  style="Muted.TLabel").pack(side="left")
        self.v_yield = tk.BooleanVar(value=bool(job.get("let_others_run")))
        ttk.Checkbutton(g, variable=self.v_yield, text=(
            "While its steps are waiting, let other jobs click in between (only if they "
            "can't disturb this job)")).pack(anchor="w", pady=(6, 0))
        self.v_video = tk.BooleanVar(value=bool(job.get("record_video")))
        ttk.Checkbutton(g, variable=self.v_video, text=(
            "Record the screen while it runs (turn on screen videos in Preferences → "
            "Recording & video)")).pack(anchor="w", pady=(2, 0))
        self.v_failshot = tk.BooleanVar(value=bool(job.get("fail_shot")))
        ttk.Checkbutton(g, variable=self.v_failshot, text=(
            "Save a screenshot on this computer if its steps fail (may show what's on "
            "screen)")).pack(anchor="w", pady=(2, 0))
        r = ttk.Frame(g)
        r.pack(anchor="w", pady=(6, 0))
        self.run_limit = self.hms_row(r, 0, "Stop a run that takes longer than",
                                      int(job.get("run_limit_s", DEFAULT_RUN_LIMIT_S)))

    def editor_job(self):
        """The job as it is in the form right now (for dry runs and stepping through)."""
        d = self.collect()
        if not d:
            return None
        temp = copy.deepcopy(self.job)
        temp.update(d)
        if temp["kind"] == "watch" and not temp.get("main_click", True):
            pass
        return temp

    def dry_run_steps(self):
        job = self.editor_job()
        if job is None:
            return
        errs = parse_blocks(job.get("steps") or [])[1]
        if errs:
            messagebox.showerror(APP_NAME, f"Fix the steps first: {errs[0]}", parent=self)
            return
        DryRunDialog(self.app, job, self)

    def step_through(self):
        job = self.editor_job()
        if job is None:
            return
        errs = parse_blocks(job.get("steps") or [])[1]
        if errs:
            messagebox.showerror(APP_NAME, f"Fix the steps first: {errs[0]}", parent=self)
            return
        if not messagebox.askyesno(
                APP_NAME, "Step through this job for real?\n\nIt clicks and types like a "
                          "normal run, but stops before every step so you can see what it "
                          "will do and why. Clickue's other windows hide meanwhile.",
                parent=self):
            return
        self.app.start_debug(job, self)

    def geom_key(self):
        return f"JobEditor-{self.kind}"

    # ---- screen watcher section
    def build_watch_section(self, f, job):
        g = ttk.LabelFrame(f, text="Picture to watch for", padding=(12, 8))
        g.pack(fill="x", pady=(12, 0))
        trow = ttk.Frame(g)
        trow.pack(fill="x", pady=(0, 8))
        ttk.Label(trow, text="Click").pack(side="left", padx=(0, 8))
        self.v_trigger = tk.StringVar(value=job.get("watch_trigger", "gone"))
        ttk.Radiobutton(trow, text="when the picture disappears", value="gone",
                        variable=self.v_trigger, command=self.trigger_changed).pack(side="left")
        ttk.Radiobutton(trow, text="when the picture appears", value="appears",
                        variable=self.v_trigger, command=self.trigger_changed).pack(
            side="left", padx=(12, 0))
        self.v_click_pic = tk.BooleanVar(value=bool(job.get("watch_click_picture")))
        self.click_pic_cb = ttk.Checkbutton(g, text="Click the picture itself (where it's found) "
                                                    "instead of a separate button",
                                            variable=self.v_click_pic,
                                            command=self.trigger_changed)
        self.click_pic_cb.pack(anchor="w", pady=(0, 8))
        top = ttk.Frame(g)
        top.pack(fill="x")
        self.wthumb_lbl = ttk.Label(top, style="Thumb.TLabel", anchor="center", width=26)
        self.wthumb_lbl.pack(side="left", anchor="n")
        right = ttk.Frame(top, padding=(12, 0, 0, 0))
        right.pack(side="left", fill="x", expand=True, anchor="n")
        brow = ttk.Frame(right)
        brow.pack(anchor="w")
        ttk.Button(brow, text="▢  Draw box around picture…", style="Accent.TButton",
                   command=self.draw_box).pack(side="left")
        ttk.Button(brow, text="Check now", command=self.check_watch_now).pack(side="left",
                                                                            padx=6)
        ttk.Button(brow, text="Dry run", command=self.dry_run_now).pack(side="left")
        self.watch_info = ttk.Label(right, style="Muted.TLabel", wraplength=330,
                                    justify="left")
        self.watch_info.pack(anchor="w", pady=(8, 0))
        arow = ttk.Frame(g)
        arow.pack(fill="x", pady=(10, 0))
        ttk.Label(arow, text="Search").pack(side="left", padx=(0, 8))
        self.v_area = tk.StringVar(value="area" if job.get("watch_area") else "screen")
        ttk.Radiobutton(arow, text="the whole screen", value="screen", variable=self.v_area,
                        command=self.update_area_info).pack(side="left")
        ttk.Radiobutton(arow, text="only an area:", value="area", variable=self.v_area,
                        command=self.area_choice).pack(side="left", padx=(12, 6))
        ttk.Button(arow, text="Draw area…", style="Small.TButton",
                   command=lambda: self.draw_box("area")).pack(side="left")
        self.area_info = ttk.Label(g, style="Muted.TLabel")
        self.area_info.pack(anchor="w", pady=(4, 0))
        # 4.5.3: exact (default) or partial matching
        mrow = ttk.Frame(g)
        mrow.pack(fill="x", pady=(10, 0))
        ttk.Label(mrow, text="Match").pack(side="left", padx=(0, 8))
        self.v_wpartial = tk.BooleanVar(value=job.get("watch_match") == "partial")
        ttk.Radiobutton(mrow, text="the exact picture", value=False, variable=self.v_wpartial,
                        command=self.match_changed).pack(side="left")
        ttk.Radiobutton(mrow, text="part of the picture is enough:", value=True,
                        variable=self.v_wpartial, command=self.match_changed).pack(
            side="left", padx=(12, 0))
        self.v_wpct = tk.IntVar(value=int(job.get("watch_partial_pct", PARTIAL_DEFAULT_PCT)))
        self.wpct_spin, self.wpct_unit = spin_unit(
            mrow, self.v_wpct, PARTIAL_MIN_PCT, PARTIAL_MAX_PCT, "% of it", width=4, lead=6,
            increment=5)
        self.match_info = ttk.Label(g, style="Muted.TLabel", wraplength=520, justify="left")
        self.match_info.pack(anchor="w", pady=(4, 0))
        self.match_changed()
        if not HAVE_CV:
            ttk.Label(right, style="Warn.TLabel", wraplength=330, text=(
                "Watching needs opencv-python-headless and numpy. Start Clickue.bat "
                "installs them.")).pack(anchor="w", pady=(6, 0))

        grid = ttk.Frame(g)
        grid.pack(fill="x", pady=(10, 0))
        r = 0
        self.w_interval = self.hms_row(grid, r, "Check every", job.get("watch_interval_s", 30))
        r += 1
        self.confirm_lbl = ttk.Label(grid, text="Click when missing for")
        self.confirm_lbl.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
        self.v_confirm = tk.IntVar(value=int(job.get("watch_confirm", 2)))
        cbox = ttk.Frame(grid)
        cbox.grid(row=r, column=1, columnspan=8, sticky="w")
        spin_unit(cbox, self.v_confirm, 1, 20, "checks in a row  (ignores brief flickers; "
                                               "repeat checks are quick)", width=5,
                  unit_style="Muted.TLabel")
        r += 1
        self.v_wrandom = tk.BooleanVar(value=job.get("watch_random_on", True))
        ttk.Checkbutton(grid, text="Wait a random delay before clicking",
                        variable=self.v_wrandom, command=self.watch_random_toggled).grid(
            row=r, column=0, columnspan=8, sticky="w", pady=(6, 2))
        r += 1
        self.w_dmin = self.hms_row(grid, r, "Random delay from", job.get("watch_delay_min_s", 1))
        r += 1
        self.w_dmax = self.hms_row(grid, r, "Random delay up to",
                                   job.get("watch_delay_max_s", 5))
        r += 1
        self.v_wcool = tk.BooleanVar(value=job.get("watch_cooldown_on", True))
        ttk.Checkbutton(grid, text="Wait a while after each click before looking again",
                        variable=self.v_wcool, command=self.watch_cool_toggled).grid(
            row=r, column=0, columnspan=8, sticky="w", pady=(6, 2))
        r += 1
        self.w_cool = self.hms_row(grid, r, "After clicking, wait",
                                   job.get("watch_cooldown_s", 30), suffix="then look again")
        r += 1
        self.v_once = tk.BooleanVar(value=job.get("watch_once", True))
        self.once_cb = ttk.Checkbutton(grid, text="", variable=self.v_once)
        self.once_cb.grid(row=r, column=0, columnspan=8, sticky="w", pady=(6, 0))
        r += 1
        self.watch_note = ttk.Label(grid, style="Muted.TLabel", wraplength=520, justify="left")
        self.watch_note.grid(row=r, column=0, columnspan=8, sticky="w", pady=(6, 0))

    def trigger_changed(self):
        appears = self.v_trigger.get() == "appears"
        self.click_pic_cb.state(["!disabled"] if appears else ["disabled"])
        self.confirm_lbl.configure(text="Click when showing for" if appears
                                   else "Click when missing for")
        self.once_cb.configure(text=(
            "Click only once each time it appears (wait for the picture to go away before "
            "clicking again)" if appears else
            "Click only once each time it disappears (wait for the picture to come back "
            "before clicking again)"))
        self.watch_note.configure(text=(
            "The picture is searched for at any size. When it shows up, Clickue clicks."
            if appears else
            "The picture is searched for at any size. While the Clickue window is open on "
            "screen, a missing picture isn't counted (the window might be covering it), so "
            "minimize it or send it to the tray."))
        own = appears and self.v_click_pic.get()
        if hasattr(self, "where_frame"):
            self.where_frame.configure(text=(
                "Button to click - not needed: the picture itself is clicked" if own else
                ("Button to click when the picture appears" if appears
                 else "Button to click when the picture disappears")))

    def area_choice(self):
        if self.v_area.get() == "area" and not self.watch_area:
            self.draw_box("area")
        self.update_area_info()

    def match_changed(self):
        part = bool(self.v_wpartial.get())
        for w in (self.wpct_spin, self.wpct_unit):
            try:
                w.state(["!disabled"] if part else ["disabled"])
            except Exception:
                pass
        self.match_info.configure(text=(
            "Counts as showing when at least this much of the picture matches (checked in "
            "small pieces), so a number or animation changing inside the box doesn't make it "
            "\u201cgone\u201d. Lower = more forgiving, but a look-alike may count."
            if part else
            "Shape, colour and fine detail must all match, so a similar-looking replacement "
            "doesn't count. Draw the box around something that doesn't change."))

    def update_area_info(self):
        if self.v_area.get() == "area" and self.watch_area:
            x, y, w, h = self.watch_area
            self.area_info.configure(text=f"Searching only a {w}×{h} area at ({x}, {y}) - "
                                          f"faster, and look-alikes elsewhere are ignored.")
        elif self.v_area.get() == "area":
            self.area_info.configure(text="Click \u201cDraw area\u201d to choose the area.")
        else:
            self.area_info.configure(text="Searching the whole screen.")

    def update_watch_thumb(self):
        if not (HAVE_PIL and self.watch_png):
            self.wthumb_lbl.configure(image="", text="No picture yet")
            self.watch_info.configure(text="Click \u201cDraw box around picture\u201d, then drag "
                                           "a box around the picture that should stay on "
                                           "screen. When it disappears, the button below gets "
                                           "clicked.")
            return
        try:
            img = b64_to_img(self.watch_png)
            w0, h0 = img.size
            f = min(220 / img.width, 130 / img.height, 3.0)
            if abs(f - 1) > 0.05:
                img = img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))))
            self._wthumb = ImageTk.PhotoImage(img)
            self.wthumb_lbl.configure(image=self._wthumb, text="")
            self.watch_info.configure(text=f"Watching for this {w0}×{h0} picture. Use "
                                           f"\u201cCheck now\u201d to make sure it can be "
                                           f"found on screen.")
        except Exception:
            self.wthumb_lbl.configure(image="", text="(picture unreadable)")

    def dry_run_now(self):
        d = self.collect()
        if not d:
            return
        temp = dict(self.job)
        temp.update(d)
        temp["watch_png"] = self.watch_png
        self.app.dry_run_for(temp, parent=self)

    def check_watch_now(self):
        temp = dict(self.job)
        temp["watch_png"] = self.watch_png
        temp["watch_trigger"] = self.v_trigger.get()
        temp["watch_area"] = self.watch_area if self.v_area.get() == "area" else None
        temp["watch_area_screen"] = self.watch_area_screen
        self.app.show_watch_for(temp, parent=self)

    def draw_box(self, mode="picture"):
        if not (HAVE_PIL and HAVE_CV):
            messagebox.showwarning(APP_NAME, "Drawing a box needs pillow, opencv and numpy. "
                                             "Start Clickue.bat installs them.", parent=self)
            return
        self._hold += 1
        saved = self.app.hide_windows([self, self.app.tests_win, self.app.root])
        self.after(450, lambda: self._draw_overlay(saved, mode))

    def _draw_overlay(self, saved, mode="picture"):
        app = self.app

        def restore():
            app.show_windows(saved, focus=self)
            self.after(900, lambda: setattr(self, "_hold", max(0, self._hold - 1)))

        try:
            # the pointer is moved aside for a moment so hover effects aren't saved (4.5.3)
            shot, (vx, vy) = grab_screen(move_cursor=True)
        except Exception as e:
            restore()
            messagebox.showerror(APP_NAME, f"Couldn't capture the screen:\n{e}", parent=self)
            return
        msg = ("Drag a box around the picture to watch   ·   release to save") \
            if mode == "picture" else "Drag a box around the AREA to search in   ·   release to save"

        def done(b):
            if mode == "area":
                vx2, vy2, vw2, vh2 = virtual_screen()
                self.watch_area = [b[0] + vx, b[1] + vy, b[2] - b[0], b[3] - b[1]]
                self.watch_area_screen = [vw2, vh2]
                self.v_area.set("area")
                self.update_area_info()
                restore()
                app.log(f"Search area saved: {self.watch_area[2]}×{self.watch_area[3]} at "
                        f"({self.watch_area[0]}, {self.watch_area[1]})")
                return
            crop = shot.crop(b)
            self.watch_png = img_to_b64(crop)        # full screen resolution, lossless
            self.update_watch_thumb()
            # look once more a moment later: does anything inside the box change?
            self.after(600, lambda: finish(crop, b))

        def finish(crop, b):
            changed = picture_changes(crop, b, vx, vy)
            restore()
            gray = np.asarray(crop.convert("L"), dtype=np.float32)
            app.log(f"Watch picture saved: {crop.width}×{crop.height} at "
                    f"({b[0] + vx}, {b[1] + vy}), full screen resolution"
                    + (f"; {changed:.0%} of it changed within a second" if changed else ""))
            if changed and not self.v_wpartial.get():
                messagebox.showwarning(
                    APP_NAME, f"Part of that picture changed within a second ({changed:.0%} "
                              f"of it), e.g. a number, a clock or an animation.\n\nWith "
                              f"\u201cthe exact picture\u201d the watcher would think it's "
                              f"gone whenever that part changes. Draw a smaller box around a "
                              f"part that stays the same, or choose \u201cpart of the picture "
                              f"is enough\u201d under Match.", parent=self)
            elif float(gray.std()) < 6:
                messagebox.showwarning(APP_NAME, "That area is very plain (almost one "
                                                 "colour), so it can't be told apart from "
                                                 "other plain areas. Try a box around text, "
                                                 "an icon or a logo.", parent=self)
            elif crop.width * crop.height > 500 * 400:
                messagebox.showinfo(APP_NAME, "That's a big picture. It works, but each check "
                                              "takes longer. A smaller box around the most "
                                              "distinctive part is faster.", parent=self)

        self._drawer = BoxDrawer(app, shot, (vx, vy), msg, done, restore,
                                 min_size=PICTURE_MIN_PX if mode == "picture" else 16)

    # ---- helpers
    def mode_changed(self):
        if self.v_mode.get() == "window":
            self.scr_box.pack_forget()
            self.win_box.pack(anchor="w", fill="x", after=self.rb_win)
        else:
            self.win_box.pack_forget()
            self.scr_box.pack(anchor="w", fill="x", after=self.rb_scr)

    def update_info(self, x=None, y=None):
        ps = self.pick_screen
        scr = f" on a {ps[0]}×{ps[1]} screen" if ps else ""
        title = self.v_title.get().strip()
        if x is not None:
            if title and self.v_mode.get() == "window":
                txt = (f"Picked ({x}, {y}){scr}, inside “{short_title(title, 40)}” at "
                       f"({self.v_rx.get()}, {self.v_ry.get()}).")
            else:
                txt = (f"Picked ({x}, {y}){scr}. No window there to follow "
                       f"(desktop or taskbar), so it's a fixed screen position.")
        elif title:
            txt = f"Follows the window “{short_title(title, 40)}”{scr and ' (picked' + scr + ')'}."
        else:
            txt = ("Click “Pick on screen”, then point at the spot within 5 seconds."
                   if self.is_new else f"Fixed screen position{scr and ' (picked' + scr + ')'}.")
        cur = screen_size()
        picture_on = self.snap_png and self.v_use_img.get() and HAVE_CV
        if picture_on:
            txt += "  A picture of the spot is saved, so it will be found even if things move."
        elif ps and tuple(ps) != cur and self.v_mode.get() == "screen":
            txt += f"  The screen is {cur[0]}×{cur[1]} now, so this spot may be off."
        if self.v_use_img.get() and not self.snap_png and HAVE_CV:
            txt += "  Pick the spot again to save its picture."
        self.pick_info.configure(text=txt)

    def update_thumb(self):
        if not (HAVE_PIL and self.snap_png):
            self.thumb_lbl.configure(image="", text="No picture yet")
            return
        try:
            img = b64_to_img(self.snap_png)
            sx, sy = self.snap_spot or (img.width // 2, img.height // 2)
            d = ImageDraw.Draw(img)
            d.ellipse((sx - 7, sy - 7, sx + 7, sy + 7), outline=(255, 45, 45), width=2)
            d.line((sx - 12, sy, sx - 4, sy), fill=(255, 45, 45), width=2)
            d.line((sx + 4, sy, sx + 12, sy), fill=(255, 45, 45), width=2)
            d.line((sx, sy - 12, sx, sy - 4), fill=(255, 45, 45), width=2)
            d.line((sx, sy + 4, sx, sy + 12), fill=(255, 45, 45), width=2)
            f = min(220 / img.width, 130 / img.height, 2.0)
            if abs(f - 1) > 0.05:
                img = img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))))
            self._thumb = ImageTk.PhotoImage(img)
            self.thumb_lbl.configure(image=self._thumb, text="")
        except Exception:
            self.thumb_lbl.configure(image="", text="(picture unreadable)")

    def hms_row(self, f, r, label, seconds, suffix=None):
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        lbl = ttk.Label(f, text=label)
        lbl.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
        # fixed label column so the fields line up from row to row; the fields and their
        # h / m / s units sit together in one compact row (4.5.3: units right next to fields)
        f.columnconfigure(0, minsize=190)
        box = ttk.Frame(f)
        box.grid(row=r, column=1, columnspan=8, sticky="w")
        vs = []
        widgets = [lbl]
        for val, top, unit in ((h, 999, "h"), (m, 59, "m"), (s, 59, "s")):
            v = tk.IntVar(value=val)
            sp, ul = spin_unit(box, v, 0, top, unit, width=5, command=self.update_preview)
            sp.bind("<KeyRelease>", lambda e: self.update_preview())
            vs.append(v)
            widgets += [sp, ul]
        if suffix:
            sl = ttk.Label(box, text=suffix, style="Muted.TLabel")
            sl.pack(side="left", padx=(4, 0))
            widgets.append(sl)
        if not hasattr(self, "_row_widgets"):
            self._row_widgets = {}
        self._row_widgets[id(vs)] = widgets
        return vs

    def set_rows_enabled(self, rows, on):
        for vs in rows:
            for w in self._row_widgets.get(id(vs), []):
                try:
                    w.state(["!disabled"] if on else ["disabled"])
                except Exception:
                    pass

    @staticmethod
    def hms_value(vs):
        h, m, s = (int(v.get()) for v in vs)
        return h * 3600 + m * 60 + s

    def update_preview(self):
        try:
            iv = self.hms_value(self.interval)
            if not self.v_random.get():
                txt = f"Clicks exactly every {fmt_dur(iv)} (no random delay)."
            else:
                lo, hi = self.hms_value(self.dmin), self.hms_value(self.dmax)
                txt = (f"Clicks every {fmt_dur(iv)}, each one {fmt_dur(lo)} to {fmt_dur(hi)} "
                       f"after its scheduled time (random, to the second).")
            self.preview.configure(text=txt)
        except Exception:
            pass

    def random_toggled(self):
        on = bool(self.v_random.get())
        self.set_rows_enabled((self.dmin, self.dmax), on)
        self.anchor_cb.state(["!disabled"] if on else ["disabled"])
        self.update_preview()

    def watch_random_toggled(self):
        self.set_rows_enabled((self.w_dmin, self.w_dmax), bool(self.v_wrandom.get()))

    def watch_cool_toggled(self):
        self.set_rows_enabled((self.w_cool,), bool(self.v_wcool.get()))

    def pick(self):
        if getattr(self.app, "_spot_busy", False):
            return
        self._hold += 1
        saved = self.app.hide_windows([self, self.app.tests_win, self.app.root])

        def back():
            self.app.show_windows(saved, focus=self)
            self.after(900, lambda: setattr(self, "_hold", max(0, self._hold - 1)))

        def finish(x, y):
            info = describe_point(x, y)
            warn = ""
            if HAVE_CV:
                try:
                    snap, spot, detail = capture_snapshot(x, y, self.v_snap_size.get())
                    self.snap_png, self.snap_spot = img_to_b64(snap), list(spot)
                    self.pick_dpi = system_dpi()
                    if detail < 6:
                        warn = ("That spot is a plain, empty-looking area, so its picture "
                                "isn't distinctive. Try the Large picture size, or pick a spot "
                                "with text or an icon nearby.")
                except Exception as e:
                    self.snap_png, self.snap_spot = "", None
                    warn = f"Couldn't save a picture of the spot ({e})."
            self.v_x.set(x)
            self.v_y.set(y)
            self.pick_screen = list(screen_size())
            if info:
                self.v_title.set(info["window_title"])
                self.window_class = info["window_class"]
                self.v_rx.set(info["rel_x"])
                self.v_ry.set(info["rel_y"])
                self.client_size = (info["client_w"], info["client_h"])
                self.v_mode.set("window")
            else:
                self.v_title.set("")
                self.window_class = ""
                self.v_mode.set("screen")
            self.mode_changed()
            self.update_info(x, y)
            self.update_thumb()
            back()
            if warn:
                messagebox.showwarning(APP_NAME, warn, parent=self)
            self.app.log(f"Picked ({x}, {y})" + (f" inside “{short_title(info['window_title'])}”"
                                                 if info else ""))
        self.app.pick_countdown(finish, back)

    def collect(self):
        """Read the form; returns a dict of job fields, or None after showing an error."""
        try:
            d = dict(
                name=self.v_name.get().strip() or "Click",
                x=int(self.v_x.get()), y=int(self.v_y.get()),
                target_mode=self.v_mode.get(),
                window_title=self.v_title.get().strip(),
                rel_x=int(self.v_rx.get()), rel_y=int(self.v_ry.get()),
                bring_to_front=bool(self.v_front.get()),
                scale_with_window=bool(self.v_scale_w.get()),
                scale_with_screen=bool(self.v_scale_s.get()),
                button=self.v_button.get(),
                clicks=2 if self.v_clicks.get() == "double" else 1,
                human_move=human_value({t: k for k, t in HUMAN_CHOICES}.get(
                    self.v_human.get(), "default")),
                interval_s=self.hms_value(self.interval),
                delay_min_s=self.hms_value(self.dmin),
                delay_max_s=self.hms_value(self.dmax),
                first_time=self.v_first.get().strip(),
                anchored=bool(self.v_anchor.get()),
                random_on=bool(self.v_random.get()),
            )
            if d["first_time"] and self.kind == "click":
                parse_hms_clock(d["first_time"])
            d.update(hours_on=bool(self.v_hours.get()), hours_from=self.v_hfrom.get().strip(),
                     hours_to=self.v_hto.get().strip(),
                     hours_days=[i for i, v in enumerate(self.v_days) if v.get()],
                     hours_outside="skip" if self.v_outside.get().startswith("Skip") else "wait",
                     limit_clicks_on=bool(self.v_lim_on.get()),
                     limit_clicks=max(1, int(self.v_lim_n.get())),
                     limit_until_on=bool(self.v_until_on.get()),
                     limit_until=self.v_until.get().strip(),
                     steps=copy.deepcopy(self.steps),
                     main_click=bool(self.v_main.get()),
                     priority=self.v_prio.get().lower(),
                     let_others_run=bool(self.v_yield.get()),
                     record_video=bool(self.v_video.get()),
                     fail_shot=bool(self.v_failshot.get()),
                     run_limit_s=max(10, min(MAX_RUN_LIMIT_S, self.hms_value(self.run_limit)))
                     if self.hms_value(self.run_limit) else DEFAULT_RUN_LIMIT_S)
            if self.kind == "watch":
                d.update(kind="watch", watch_png=self.watch_png,
                         watch_interval_s=self.hms_value(self.w_interval),
                         watch_confirm=max(1, int(self.v_confirm.get())),
                         watch_delay_min_s=self.hms_value(self.w_dmin),
                         watch_delay_max_s=self.hms_value(self.w_dmax),
                         watch_cooldown_s=self.hms_value(self.w_cool),
                         watch_once=bool(self.v_once.get()),
                         watch_random_on=bool(self.v_wrandom.get()),
                         watch_cooldown_on=bool(self.v_wcool.get()),
                         watch_trigger=self.v_trigger.get(),
                         watch_click_picture=bool(self.v_click_pic.get())
                         and self.v_trigger.get() == "appears",
                         watch_area=(copy.deepcopy(self.watch_area)
                                     if self.v_area.get() == "area" else None),
                         watch_area_screen=copy.deepcopy(self.watch_area_screen),
                         watch_match="partial" if self.v_wpartial.get() else "exact",
                         watch_partial_pct=min(PARTIAL_MAX_PCT, max(
                             PARTIAL_MIN_PCT, int(self.v_wpct.get()))))
        except Exception:
            messagebox.showerror(APP_NAME, "Please check the numbers and the time (HH:MM).",
                                 parent=self)
            return None
        if d["hours_on"]:
            try:
                d["hours_from"] = "%02d:%02d" % divmod(parse_hhmm(d["hours_from"]), 60)
                d["hours_to"] = "%02d:%02d" % divmod(parse_hhmm(d["hours_to"]), 60)
            except Exception:
                messagebox.showerror(APP_NAME, "Active hours must look like 08:00 and 22:00.",
                                     parent=self)
                return None
            if not d["hours_days"]:
                messagebox.showerror(APP_NAME, "Tick at least one day for the active hours.",
                                     parent=self)
                return None
        if d["limit_until_on"]:
            try:
                datetime.strptime(d["limit_until"], "%Y-%m-%d %H:%M")
            except ValueError:
                messagebox.showerror(APP_NAME, "\u201cStop at\u201d must look like "
                                               "2026-12-31 18:00.", parent=self)
                return None
        if d["target_mode"] == "window" and not d["window_title"] and d["main_click"]:
            messagebox.showerror(APP_NAME, "Enter the window title to follow, or pick the spot "
                                           "again, or choose “Fixed screen position”.",
                                 parent=self)
            return None
        if not d["main_click"] and not d["steps"]:
            messagebox.showerror(APP_NAME, "Add at least one step, or turn the click on.",
                                 parent=self)
            return None
        errs = parse_blocks(d["steps"])[1]
        if errs:
            messagebox.showerror(APP_NAME, f"Please fix the steps: {errs[0]}", parent=self)
            return None
        # keep window details from the pick only if the title wasn't changed by hand
        same_title = d["window_title"] == self.job.get("window_title") or self.window_class
        d["window_class"] = self.window_class if same_title else ""
        d["client_w"], d["client_h"] = self.client_size
        d["pick_screen"] = self.pick_screen
        d["use_image"] = bool(self.v_use_img.get())
        d["exact_match"] = bool(self.v_exact.get())
        d["snap_png"] = self.snap_png
        d["snap_spot"] = self.snap_spot
        d["pick_dpi"] = self.pick_dpi
        d["snap_size"] = self.v_snap_size.get()
        d["image_fallback"] = ("position" if self.v_fallback.get().startswith("Click")
                               else "wait")
        return d

    def preview_spot(self):
        d = self.collect()
        if d:
            temp = dict(self.job)
            temp.update(d)
            self.app.show_spot_for(temp, parent=self)

    def on_save(self):
        d = self.collect()
        if not d:
            return
        if self.kind == "watch":
            self.save_watcher(d)
            return
        iv, lo, hi = d["interval_s"], d["delay_min_s"], d["delay_max_s"]
        if iv < 1:
            messagebox.showerror(APP_NAME, "The schedule interval must be at least 1 second.",
                                 parent=self)
            return
        if not d["random_on"]:
            lo = hi = 0
        if hi < lo:
            messagebox.showerror(APP_NAME, "'Random delay up to' must be at least "
                                           "'Random delay from'.", parent=self)
            return
        if hi >= iv and not messagebox.askyesno(
                APP_NAME, "The maximum random delay is as long as the interval itself, "
                          "so clicks could bunch up. Save anyway?", parent=self):
            return

        app, j = self.app, self.job
        with app.lock:
            timing_changed = (j["interval_s"], j["delay_min_s"], j["delay_max_s"],
                              j.get("first_time", ""), j.get("random_on", True)) != (
                d["interval_s"], d["delay_min_s"], d["delay_max_s"], d["first_time"],
                d["random_on"])
            was_enabled = j.get("enabled", False) and not self.is_new
            j.update(d)
            j["enabled"] = bool(self.v_enabled.get())
            if self.is_new:
                app.jobs.append(j)
                app.log(f"[{j['name']}] added")
            if j["enabled"]:
                if not was_enabled or timing_changed or not j.get("next_run"):
                    app.schedule_first(j)
            else:
                j["next_run"] = j["base_next"] = j["deadline"] = None
        app.save()
        app.refresh_tree(full=True)
        self.destroy()
        app.warn_conflicts(j)


    def save_watcher(self, d):
        if not d["watch_png"]:
            messagebox.showerror(APP_NAME, "Draw a box around the picture to watch for first.",
                                 parent=self)
            return
        if d["watch_interval_s"] < 1:
            messagebox.showerror(APP_NAME, "Check at least every 1 second.", parent=self)
            return
        if d["watch_random_on"] and d["watch_delay_max_s"] < d["watch_delay_min_s"]:
            messagebox.showerror(APP_NAME, "'Random delay up to' must be at least "
                                           "'Random delay from'.", parent=self)
            return
        if d.get("watch_area") is None and self.v_area.get() == "area":
            messagebox.showerror(APP_NAME, "Draw the area to search in, or choose "
                                           "\u201cthe whole screen\u201d.", parent=self)
            return
        if (d["main_click"] and not d["watch_click_picture"] and not d["snap_png"]
                and d["target_mode"] == "screen" and d["x"] == 0 and d["y"] == 0):
            messagebox.showerror(APP_NAME, "Pick the button to click (\u201cPick on "
                                           "screen\u201d).", parent=self)
            return
        app, j = self.app, self.job
        with app.lock:
            changed = any(j.get(k) != d.get(k) for k in (
                "watch_png", "watch_interval_s", "watch_confirm", "watch_trigger",
                "watch_area", "watch_match", "watch_partial_pct"))
            was_enabled = j.get("enabled", False) and not self.is_new
            j.update(d)
            if self.is_new:
                app.jobs.append(j)
                app.log(f"[{j['name']}] screen watcher added")
            if self.v_enabled.get():
                if not was_enabled or changed:
                    app.start_job(j)
            else:
                app.stop_job(j)
        app.save()
        if app.v_filter.get() == "click":
            app.v_filter.set("all")
        app.refresh_tree(full=True)
        self.destroy()
        app.warn_conflicts(j)


class BatchEditDialog(Dialog):
    """Change the same settings on several ticked jobs at once (4.5.3). Only the settings
    whose "Change" box is ticked are touched; everything else stays as it is per job."""

    def __init__(self, app, jobs):
        super().__init__(app, f"Edit {len(jobs)} jobs - {APP_NAME}")
        self.jobs = list(jobs)
        self.rows = []          # (flag var, [widgets], getter)
        n_watch = sum(1 for j in self.jobs if is_watch(j))
        n_click = len(self.jobs) - n_watch
        f = self.body
        ttk.Label(f, text=f"Edit {len(self.jobs)} jobs together", style="Title.TLabel").pack(
            anchor="w")
        names = ", ".join(j["name"] for j in self.jobs[:6]) + (
            f" and {len(self.jobs) - 6} more" if len(self.jobs) > 6 else "")
        ttk.Label(f, style="Muted.TLabel", wraplength=560, justify="left", text=(
            f"{names}.\nTick each setting you want to set on all of them; everything else "
            f"stays as it is in each job. Running jobs pick up the new timing right away; "
            f"paused jobs stay paused.")).pack(anchor="w", pady=(4, 8))
        first = self.jobs[0]
        clicks = [j for j in self.jobs if not is_watch(j)]
        watches = [j for j in self.jobs if is_watch(j)]

        g = self.section(f, "Every ticked job")
        self.combo_row(g, "Mouse button", "button", ("left", "right", "middle"),
                       first.get("button", "left"))
        self.choice_row(g, "Click", "clicks", ((1, "single"), (2, "double")),
                        int(first.get("clicks", 1)))
        self.combo_row(g, "Priority when several are due", "priority",
                       ("high", "normal", "low"), first.get("priority", "normal"))
        self.choice_row(g, "Click-spot picture", "exact_match",
                        ((True, "the exact picture only"), (False, "similar pictures count")),
                        bool(first.get("exact_match", True)))
        self.choice_row(g, "If the picture isn't found", "image_fallback",
                        (("wait", "wait and try again"), ("position", "click the saved spot")),
                        first.get("image_fallback", "wait"))
        self.hours_row(g, first)
        self.hms_field(g, "Stop a run that takes longer than", "run_limit_s",
                       int(first.get("run_limit_s", DEFAULT_RUN_LIMIT_S)))
        for key, label in (("bring_to_front", "Bring its window to the front"),
                           ("let_others_run", "Let other jobs run while its steps wait"),
                           ("record_video", "Record the screen while it runs"),
                           ("fail_shot", "Save a screenshot if its steps fail")):
            self.bool_row(g, label, key, bool(first.get(key)))

        if clicks:
            c0 = clicks[0]
            g = self.section(f, f"Scheduled clicks only ({n_click})")
            self.hms_field(g, "Scheduled every", "interval_s", int(c0.get("interval_s", 3600)))
            self.delay_row(g, "Random delay after each time", ("random_on", "delay_min_s",
                                                               "delay_max_s"), c0)
        if watches:
            w0 = watches[0]
            g = self.section(f, f"Screen watchers only ({n_watch})")
            self.hms_field(g, "Check every", "watch_interval_s",
                           int(w0.get("watch_interval_s", 30)))
            self.spin_row(g, "Act after", "watch_confirm", 1, 100, "checks in a row",
                          int(w0.get("watch_confirm", 2)))
            self.delay_row(g, "Random delay before clicking",
                           ("watch_random_on", "watch_delay_min_s", "watch_delay_max_s"), w0)
            self.cool_row(g, w0)
            self.bool_row(g, "Click only once until the picture changes back", "watch_once",
                          bool(w0.get("watch_once", True)))
            self.match_row(g, w0)
        if not watches or not clicks:
            ttk.Label(f, style="Muted.TLabel", text=(
                "Only settings that fit the ticked jobs are shown.")).pack(anchor="w",
                                                                          pady=(8, 0))
        ttk.Button(self.footer, text="Apply to all", style="Accent.TButton",
                   command=self.apply).pack(side="right")
        ttk.Button(self.footer, text="Cancel", command=self.destroy).pack(side="right",
                                                                          padx=(0, 6))
        self.status = ttk.Label(self.footer, style="Muted.TLabel")
        self.status.pack(side="left")
        for flag, ws, _ in self.rows:
            self._enable(ws, False)
        self.finish()

    # ---- building blocks
    def section(self, f, title):
        g = ttk.LabelFrame(f, text=title, padding=(12, 8))
        g.pack(fill="x", pady=(8, 0))
        g.columnconfigure(1, weight=1)
        return g

    def add_row(self, g, label, build, getter):
        r = len(g.grid_slaves(column=0))
        flag = tk.BooleanVar(value=False)
        box = ttk.Frame(g)
        ws = build(box) or []
        cb = ttk.Checkbutton(g, text=label, variable=flag,
                             command=lambda: (self._enable(ws, flag.get()), self.count()))
        cb.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 12))
        box.grid(row=r, column=1, sticky="w", pady=3)
        self.rows.append((flag, ws, getter))
        return flag

    @staticmethod
    def _enable(ws, on):
        for w in ws:
            try:
                w.state(["!disabled"] if on else ["disabled"])
            except Exception:
                try:
                    w.configure(state="normal" if on else "disabled")
                except Exception:
                    pass

    def count(self):
        n = sum(1 for flag, _, _ in self.rows if flag.get())
        self.status.configure(text=f"{n} setting{'s' if n != 1 else ''} to change" if n
                              else "Nothing ticked yet")

    def hms_box(self, box, seconds):
        h, rem = divmod(int(seconds), 3600)
        m, sec = divmod(rem, 60)
        vs, ws = [], []
        for val, top, unit in ((h, 999, "h"), (m, 59, "m"), (sec, 59, "s")):
            v = tk.IntVar(value=val)
            ws += list(spin_unit(box, v, 0, top, unit, width=5))
            vs.append(v)
        return vs, ws

    @staticmethod
    def hms_get(vs):
        h, m, sec = (int(v.get()) for v in vs)
        return h * 3600 + m * 60 + sec

    def combo_row(self, g, label, key, values, cur):
        v = tk.StringVar(value=cur if cur in values else values[0])

        def build(box):
            cb = ttk.Combobox(box, textvariable=v, values=values, state="readonly", width=10)
            cb.pack(side="left")
            return [cb]
        self.add_row(g, label, build, lambda: {key: v.get()})

    def choice_row(self, g, label, key, options, cur):
        v = tk.StringVar(value=str(cur))
        by_text = {str(o): o for o, _ in options}

        def build(box):
            ws = []
            for o, text in options:
                rb = ttk.Radiobutton(box, text=text, value=str(o), variable=v)
                rb.pack(side="left", padx=(0, 12))
                ws.append(rb)
            return ws
        self.add_row(g, label, build, lambda: {key: by_text[v.get()]})

    def bool_row(self, g, label, key, cur):
        v = tk.BooleanVar(value=cur)

        def build(box):
            ws = []
            for val, text in ((True, "on"), (False, "off")):
                rb = ttk.Radiobutton(box, text=text, value=val, variable=v)
                rb.pack(side="left", padx=(0, 12))
                ws.append(rb)
            return ws
        self.add_row(g, label, build, lambda: {key: bool(v.get())})

    def spin_row(self, g, label, key, lo, hi, unit, cur):
        v = tk.IntVar(value=cur)
        self.add_row(g, label, lambda box: list(spin_unit(box, v, lo, hi, unit, width=5)),
                     lambda: {key: int(v.get())})

    def hms_field(self, g, label, key, seconds):
        holder = {}

        def build(box):
            holder["vs"], ws = self.hms_box(box, seconds)
            return ws
        self.add_row(g, label, build, lambda: {key: self.hms_get(holder["vs"])})

    def delay_row(self, g, label, keys, job):
        on_k, lo_k, hi_k = keys
        on = tk.BooleanVar(value=bool(job.get(on_k, True)))
        holder = {}

        def build(box):
            r1, r2 = ttk.Frame(box), ttk.Frame(box)
            r1.pack(anchor="w")
            r2.pack(anchor="w", pady=(4, 0))
            cb = ttk.Checkbutton(r1, text="on, from", variable=on, width=8)
            cb.pack(side="left", padx=(0, 8))
            holder["lo"], ws1 = self.hms_box(r1, int(job.get(lo_k, 0)))
            ttk.Label(r2, text="up to", width=8).pack(side="left", padx=(0, 8))
            holder["hi"], ws2 = self.hms_box(r2, int(job.get(hi_k, 0)))
            return [cb] + ws1 + ws2
        self.add_row(g, label, build, lambda: {on_k: bool(on.get()),
                                               lo_k: self.hms_get(holder["lo"]),
                                               hi_k: self.hms_get(holder["hi"])})

    def cool_row(self, g, job):
        on = tk.BooleanVar(value=bool(job.get("watch_cooldown_on", True)))
        holder = {}

        def build(box):
            cb = ttk.Checkbutton(box, text="on, wait", variable=on, width=8)
            cb.pack(side="left", padx=(0, 8))
            holder["vs"], ws = self.hms_box(box, int(job.get("watch_cooldown_s", 30)))
            return [cb] + ws
        self.add_row(g, "Wait after each click", build,
                     lambda: {"watch_cooldown_on": bool(on.get()),
                              "watch_cooldown_s": self.hms_get(holder["vs"])})

    def match_row(self, g, job):
        part = tk.BooleanVar(value=job.get("watch_match") == "partial")
        pct = tk.IntVar(value=int(job.get("watch_partial_pct", PARTIAL_DEFAULT_PCT)))

        def build(box):
            a = ttk.Radiobutton(box, text="the exact picture", value=False, variable=part)
            a.pack(side="left", padx=(0, 12))
            b = ttk.Radiobutton(box, text="part is enough:", value=True, variable=part)
            b.pack(side="left")
            return [a, b] + list(spin_unit(box, pct, PARTIAL_MIN_PCT, PARTIAL_MAX_PCT,
                                           "% of it", width=4, lead=6, increment=5))
        self.add_row(g, "Match the watched picture", build,
                     lambda: {"watch_match": "partial" if part.get() else "exact",
                              "watch_partial_pct": int(pct.get())})

    def hours_row(self, g, job):
        on = tk.BooleanVar(value=bool(job.get("hours_on")))
        fr = tk.StringVar(value=job.get("hours_from", "08:00"))
        to = tk.StringVar(value=job.get("hours_to", "22:00"))
        outside = tk.StringVar(value=job.get("hours_outside", "wait"))
        days = [tk.BooleanVar(value=d in (job.get("hours_days") or [])) for d in range(7)]

        def build(box):
            top = ttk.Frame(box)
            top.pack(anchor="w")
            cb = ttk.Checkbutton(top, text="only from", variable=on)
            cb.pack(side="left", padx=(0, 6))
            e1 = ttk.Entry(top, textvariable=fr, width=6)
            e1.pack(side="left")
            ttk.Label(top, text="to").pack(side="left", padx=6)
            e2 = ttk.Entry(top, textvariable=to, width=6)
            e2.pack(side="left")
            row2 = ttk.Frame(box)
            row2.pack(anchor="w", pady=(4, 0))
            ws = [cb, e1, e2]
            for d, name in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
                c = ttk.Checkbutton(row2, text=name, variable=days[d])
                c.pack(side="left", padx=(0, 6))
                ws.append(c)
            row3 = ttk.Frame(box)
            row3.pack(anchor="w", pady=(4, 0))
            ttk.Label(row3, text="Outside them:").pack(side="left", padx=(0, 6))
            for val, text in (("wait", "wait for them"), ("skip", "skip that click")):
                rb = ttk.Radiobutton(row3, text=text, value=val, variable=outside)
                rb.pack(side="left", padx=(0, 10))
                ws.append(rb)
            return ws

        def get():
            for t in (fr.get(), to.get()):
                parse_hhmm(t.strip())
            return {"hours_on": bool(on.get()), "hours_from": fr.get().strip(),
                    "hours_to": to.get().strip(), "hours_outside": outside.get(),
                    "hours_days": [d for d in range(7) if days[d].get()]}
        self.add_row(g, "Active hours", build, get)

    # ---- apply
    def apply(self):
        changes = {}
        try:
            for flag, _, getter in self.rows:
                if flag.get():
                    changes.update(getter())
        except Exception:
            messagebox.showerror(APP_NAME, "Please check the numbers and the times (HH:MM).",
                                 parent=self)
            return
        if not changes:
            messagebox.showinfo(APP_NAME, "Tick at least one setting to change.",
                                 parent=self)
            return
        for lo, hi in (("delay_min_s", "delay_max_s"), ("watch_delay_min_s",
                                                       "watch_delay_max_s")):
            if lo in changes and changes[lo] > changes[hi]:
                messagebox.showerror(APP_NAME, "The random delay's \u201cto\u201d must be at "
                                               "least its \u201cfrom\u201d.", parent=self)
                return
        if changes.get("hours_on") and not changes.get("hours_days"):
            messagebox.showerror(APP_NAME, "Choose at least one day for the active hours.",
                                 parent=self)
            return
        if "interval_s" in changes and changes["interval_s"] < 1 or \
                "watch_interval_s" in changes and changes["watch_interval_s"] < 1:
            messagebox.showerror(APP_NAME, "The interval must be at least 1 second.",
                                 parent=self)
            return
        report = self.app.apply_batch_edit(self.jobs, changes)
        self._initial = None
        self.destroy()
        n = len(report)
        messagebox.showinfo(APP_NAME, f"Changed {n} of {len(self.jobs)} job"
                                      f"{'s' if len(self.jobs) != 1 else ''}."
                            + ("" if n == len(self.jobs) else
                               " The others already had these settings, or they don't apply "
                               "to that kind of job."), parent=self.app.root)


class TestDialog(Dialog):
    def __init__(self, app, job, parent=None):
        super().__init__(app, "Schedule a test click", parent)
        self.job = job
        f = self.body
        ttk.Label(f, text=f"Schedule one test click for “{job['name']}” at "
                          f"{target_text(job)}.", wraplength=420).pack(anchor="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=420, justify="left", text=(
            "Use this to check that clicks still work after you disconnect from RDP or hand "
            "the session to the console. It follows the same rules as a real click (waits "
            "for the screen, retries, then reports). The result shows in the Last result "
            "column, the activity log, and a tray notification. Your normal schedule isn't "
            "changed.")).pack(anchor="w", pady=(6, 10))

        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Label(row, text="Click in").pack(side="left")
        self.v_m = tk.IntVar(value=2)
        self.v_s = tk.IntVar(value=0)
        spin_unit(row, self.v_m, 0, 1440, "min", width=5, lead=6)
        spin_unit(row, self.v_s, 0, 59, "sec", width=4)

        b = self.footer
        if job.get("test_at"):
            ttk.Label(f, style="Warn.TLabel",
                      text=f"A test is already pending for {fmt_time(job['test_at'])}.").pack(
                anchor="w", pady=(10, 0))
            ttk.Button(b, text="Cancel pending test", command=self.cancel_test).pack(
                side="left")
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Schedule", style="Accent.TButton", command=self.on_schedule).pack(
            side="right", padx=6)
        self.finish()

    def on_schedule(self):
        try:
            secs = int(self.v_m.get()) * 60 + int(self.v_s.get())
        except Exception:
            secs = -1
        if secs < 5:
            messagebox.showerror(APP_NAME, "Pick a time at least 5 seconds away.", parent=self)
            return
        app, j = self.app, self.job
        with app.lock:
            j["test_at"] = time.time() + secs
            j["test_deadline"] = None
            app.wait_msgs.pop((j["id"], "test"), None)
            when = j["test_at"]
        app.log(f"[{j['name']}] TEST click scheduled for {fmt_time(when)} (in {fmt_dur(secs)}). "
                f"You can disconnect now.")
        app.save()
        app.refresh_tree()
        self.destroy()

    def cancel_test(self):
        app, j = self.app, self.job
        with app.lock:
            j["test_at"] = j["test_deadline"] = None
            app.wait_msgs.pop((j["id"], "test"), None)
        app.log(f"[{j['name']}] pending test click cancelled")
        app.save()
        self.destroy()


TEST_LEVELS = {   # what a test result's colour means (4.5.5): icon, word, explanation
    "ok": ("✔", "OK", "as expected"),
    "warn": ("⚠", "Attention", "worth a look, e.g. the watcher would click now"),
    "bad": ("✖", "Failed", "the test couldn't do its job"),
    "info": ("•", "Info", ""),
}
WATCH_TEST_NAMES = ("Check picture now", "Dry run (no click)", "Scheduled watcher test")


def test_kind(name):
    """'watch' for watcher tests, 'click' for click tests (the Tests window's sections)."""
    return "watch" if name in WATCH_TEST_NAMES or "watcher" in name.lower() else "click"


class TestsWindow(tk.Toplevel):
    """Floating, resizable window with every test action and the test history.
    The main window steps aside while it's open; this window hides itself during each test."""

    def __init__(self, app, job=None):
        super().__init__(app.root)
        self.app = app
        self.withdraw()
        self.title(f"Tests - {APP_NAME}")
        if app.main_visible():
            self.transient(app.root)        # always on top of the main window
        self._hold = 0
        self.minsize(380, 420)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda e: self.close())
        self.job_ids = []
        self.job_id = job["id"] if job else None
        self._last_names = None
        self._hist_sig = None
        self._narrow = None

        main = ttk.Frame(self, padding=(14, 12, 14, 10))
        main.pack(fill="both", expand=True)

        # ---- footer (packed first so it always stays visible)
        foot = ttk.Frame(main)
        foot.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Sizegrip(foot).pack(side="right", anchor="se", padx=(8, 0))
        ttk.Button(foot, text="Close", command=self.close).pack(side="right")

        # ---- job picker
        top = ttk.Frame(main)
        top.pack(fill="x")
        ttk.Label(top, text="Tests", style="Title.TLabel").pack(side="left", padx=(0, 14))
        pick = ttk.Frame(top)
        pick.pack(side="left", fill="x", expand=True)
        ttk.Label(pick, text="Job").pack(side="left", padx=(0, 6))
        self.v_job = tk.StringVar()
        self.job_box = ttk.Combobox(pick, textvariable=self.v_job, state="readonly")
        self.job_box.pack(side="left", fill="x", expand=True)
        self.job_box.bind("<<ComboboxSelected>>", self.job_picked)
        self.kind_lbl = ttk.Label(main, style="Muted.TLabel")
        self.kind_lbl.pack(anchor="w", pady=(6, 0))

        # ---- sections (4.5.4): All tests / Click tests / Watcher tests. Each shows its own
        # buttons and its own history, for this job or for all jobs (remembered per section)
        secrow = ttk.Frame(main)
        secrow.pack(fill="x", pady=(10, 0))
        self.v_sec = tk.StringVar(value=app.settings.get("tests_section", "all"))
        if self.v_sec.get() not in ("all", "click", "watch"):
            self.v_sec.set("all")
        for val, text in (("all", "All tests"), ("click", "Click tests"),
                          ("watch", "Watcher tests")):
            ttk.Radiobutton(secrow, text=text, value=val, variable=self.v_sec,
                            style="Seg.TRadiobutton", command=self.section_changed).pack(
                side="left", padx=(0, 2))
        ctl = ttk.Frame(main)
        ctl.pack(fill="x", pady=(8, 0))
        self.ctl = ctl
        self.groups = ttk.Frame(ctl)
        self.groups.pack(fill="x")
        self.btns_any, self.btns_watch = [], []
        default_hint = "Hover over a test to see what it does."
        self.group_frames = []

        def group(title, items, bucket):
            g = ttk.LabelFrame(self.groups, text=title, padding=(8, 6))
            btns = []
            for text, cmd, tip in items:
                b = ttk.Button(g, text=text, command=cmd)
                b.bind("<Enter>", lambda e, t=f"{text}: {tip}": self.hint.configure(text=t))
                b.bind("<Leave>", lambda e: self.hint.configure(text=default_hint))
                bucket.append(b)
                btns.append(b)
            # lay the buttons out right away (one row): on Windows a frame that has nothing
            # in it yet may never get a <Configure> event (4.5.3)
            for i, b in enumerate(btns):
                b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))
                g.columnconfigure(i, weight=1, uniform="b")
            g._flow = "row"
            g.bind("<Configure>", lambda e, g=g, btns=btns: self.flow_buttons(g, btns))
            self.group_frames.append((g, btns))

        group("Click tests", (
            ("Show spot", lambda: self.run("spot"), "shows where it would click right now "
                                                     "(no click)"),
            ("Test click now", lambda: self.run("click"), "clicks once right away"),
            ("Schedule test click…", lambda: self.run("sched"), "clicks once later, e.g. "
                                                                 "after you disconnect"),
        ), self.btns_any)
        group("Watcher tests", (
            ("Check picture", lambda: self.run("check"), "is the watched picture on screen "
                                                         "right now? (every copy is outlined)"),
            ("Dry run", lambda: self.run("dry"), "marks the watched picture, then the button "
                                                 "it would click (no click)"),
            ("Schedule watcher test…", lambda: self.run("wsched"), "runs the check later, in "
                                                                   "the background"),
        ), self.btns_watch)
        self._narrow = None
        self.groups.bind("<Configure>", lambda e: self.flow_groups())
        self.hint = ttk.Label(ctl, text=default_hint, style="Muted.TLabel")
        self.hint.pack(anchor="w", pady=(4, 0))
        self.pending_lbl = ttk.Label(ctl, style="Warn.TLabel")
        self.pending_row = ttk.Frame(ctl)
        self.pending_lbl.pack(in_=self.pending_row, side="left")
        self.cancel_btn = ttk.Button(self.pending_row, text="Cancel pending tests",
                                     style="Small.TButton", command=self.cancel_pending)

        # ---- history, right under the buttons, taking the rest of the window
        hist = ttk.Frame(main)
        hist.pack(fill="both", expand=True, pady=(8, 0))
        hh = ttk.Frame(hist)
        hh.pack(fill="x", pady=(0, 4))
        self.hist_title = ttk.Label(hh, text="Test history", style="Section.TLabel")
        self.hist_title.pack(side="left", padx=(0, 10))
        self.v_hf = tk.StringVar(value=self.scope_for(self.v_sec.get()))
        for val, text in (("job", "This job"), ("all", "All jobs")):
            ttk.Radiobutton(hh, text=text, value=val, variable=self.v_hf,
                            style="Seg.TRadiobutton", command=self.hist_filter_changed).pack(
                side="left", padx=(0, 2))
        self.hist_bar = ttk.Frame(hh)                  # filled in once the table exists
        self.hist_bar.pack(side="right")
        self.hist_filter = FilterBox(hh, lambda: self.refresh(force=True), width=18)
        self.hist_filter.pack(side="right", padx=(0, 8))

        hf = ttk.Frame(hist, style="Card.TFrame", padding=1)
        hf.pack(fill="both", expand=True)
        cols = ("time", "job", "test", "meaning", "result")
        self.hist = ttk.Treeview(hf, columns=cols, show="headings", height=6,
                                 selectmode="extended")
        enable_column_fit(self.hist)
        self.hist_base = {"time": 120, "job": 130, "test": 150, "meaning": 105, "result": 320}
        for c, h in (("time", "Time"), ("job", "Job"), ("test", "Test"), ("meaning", "Meaning"),
                     ("result", "Result")):
            self.hist.heading(c, text=h, anchor="w")
            self.hist.column(c, width=self.hist_base[c], minwidth=60, stretch=False,
                             anchor="w")
        sb = ttk.Scrollbar(hf, orient="vertical", command=self.hist.yview)
        self.hist.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.hist.pack(side="left", fill="both", expand=True)
        self.hist_tools = LogGrid(app, self.hist, frame=hf, owner=self, fit_col="result",
                                  job_of=self.hist_job, filterbox=self.hist_filter,
                                  extra=self.hist_extra, name="tests", natural="new",
                                  refresh=lambda: self.refresh(force=True),
                                  delete=self.delete_hist)
        self.hist_tools.toolbar(self.hist_bar)
        self.hist.bind("<Double-1>", self.hist_double)
        self.hist.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.hist.bind("<Configure>", lambda e: self.flow_columns(e.width), add="+")
        self.hist_empty = ttk.Label(self.hist, style="Empty.TLabel", text="No tests yet")
        # what the colours mean (4.5.5)
        self.legend = ttk.Frame(hist)
        self.legend.pack(fill="x", pady=(6, 0))
        self.legend_lbls = []
        for lvl in ("ok", "warn", "bad"):
            icon, word, why = TEST_LEVELS[lvl]
            lb = ttk.Label(self.legend, text=f"{icon} {word}: {why}")
            lb.pack(side="left", padx=(0, 14))
            self.legend_lbls.append((lb, lvl))
        self._legend_stacked = False
        hist.bind("<Configure>", lambda e: self.flow_legend(e.width), add="+")
        self.detail = ttk.Label(hist, style="Muted.TLabel", justify="left",
                                text="Select a result to see all the details. Double-click a "
                                     "result with a place in it to show that place on screen.")
        self.detail.pack(fill="x", pady=(4, 0))
        hist.bind("<Configure>", lambda e: self.detail.configure(wraplength=max(200, e.width)), add="+")
        self.hist_rows = []
        self.show_section()

        self.retheme()
        g = fit_geometry(app.settings.get("tests_geom"), 380, 420)
        if g:
            self.geometry(g)
        else:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            w, h = min(820, sw - 80), min(640, sh - 120)
            self.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 3)}")
        self.refresh(force=True)
        self.deiconify()
        self.lift()
        self.focus_force()
        for ms in (60, 250, 700):                   # re-flow once the window has its size
            self.after(ms, self.relayout)
        self._gjob = None
        self.bind("<Configure>", self.on_configure, add="+")
        close_on_click_outside(self, app, self.close)

    def on_configure(self, event):
        if event.widget is not self:
            return
        if self._gjob:
            self.after_cancel(self._gjob)
        self._gjob = self.after(500, self.remember_geometry)

    def remember_geometry(self):
        self._gjob = None
        try:
            if self.state() == "normal" and self.winfo_viewable():
                g = self.geometry()
                if g != self.app.settings.get("tests_geom"):
                    self.app.settings["tests_geom"] = g
                    self.app.save()
        except Exception:
            pass

    # ---------------------------------------------------------------- layout
    def visible_groups(self):
        sec = self.v_sec.get() if hasattr(self, "v_sec") else "all"
        want = {"all": (0, 1), "click": (0,), "watch": (1,)}.get(sec, (0, 1))
        return [gb for i, gb in enumerate(self.group_frames) if i in want]

    def flow_groups(self):
        """Side by side when there's room, stacked when narrow (only this section's)."""
        W = self.groups.winfo_width()
        if W <= 1:
            W = self.winfo_width() - 28
        if W <= 1:
            return
        vis = self.visible_groups()
        need = sum(sum(b.winfo_reqwidth() for b in btns) + 40 for _, btns in vis)
        narrow = W < need + 10
        sig = (narrow, tuple(id(g) for g, _ in vis))
        if sig == self._narrow:
            return
        self._narrow = sig
        for g, _ in self.group_frames:
            g.grid_forget()
        for i, (g, _) in enumerate(vis):
            if narrow:
                g.grid(row=i, column=0, sticky="ew", pady=(0 if i == 0 else 8, 0))
            else:
                g.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
        single = len(vis) == 1
        self.groups.columnconfigure(0, weight=1, uniform="" if (narrow or single) else "tg")
        self.groups.columnconfigure(1, weight=0 if (narrow or single) else 1,
                                    uniform="" if (narrow or single) else "tg")

    def relayout(self):
        """Re-flow the test buttons for the window's real size (doesn't rely on <Configure>
        events, which Windows doesn't always send for these frames when the window opens)."""
        try:
            if not self.winfo_exists():
                return
            self.update_idletasks()
            self.flow_groups()
            for g, btns in self.group_frames:
                self.flow_buttons(g, btns)
            self.update_idletasks()
            self.keep_buttons_visible()
        except Exception:
            pass

    def flow_buttons(self, g, btns):
        """One row of buttons if they fit, otherwise one per line."""
        W = g.winfo_width()
        if W <= 1:
            W = (self.groups.winfo_width() if (self._narrow and self._narrow[0])
                 else self.groups.winfo_width() // max(1, len(self.visible_groups()))) - 20
        if W <= 1:
            return
        one_row = sum(b.winfo_reqwidth() for b in btns) + 8 * len(btns) <= W
        key = "row" if one_row else "col"
        if getattr(g, "_flow", None) == key:
            return
        g._flow = key
        for i, b in enumerate(btns):
            b.grid_forget()
            if one_row:
                b.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 4, 0))
            else:
                b.grid(row=i, column=0, sticky="ew", pady=(0 if i == 0 else 4, 0))
        for i in range(len(btns)):
            g.columnconfigure(i, weight=1 if (one_row or i == 0) else 0,
                              uniform="b" if one_row else "")

    def flow_columns(self, width):
        # 4.5.5: columns aren't hidden any more when the window is narrow; the table scrolls
        # sideways instead, so every bit of text can be reached
        shown = ["time", "job", "test", "meaning", "result"]
        if self.v_hf.get() == "job":
            shown.remove("job")
        if tuple(shown) != tuple(self.hist["displaycolumns"]):
            self.hist["displaycolumns"] = shown
            self.hist_tools.fit()

    def keep_buttons_visible(self):
        """(4.5.3) Kept for callers; the buttons and the history no longer share a split."""

    def scope_for(self, sec):
        scopes = self.app.settings.get("tests_scopes") or {}
        v = scopes.get(sec) or "job"
        return v if v in ("job", "all") else "job"

    def section_changed(self):
        sec = self.v_sec.get()
        self.app.settings["tests_section"] = sec
        self.v_hf.set(self.scope_for(sec))
        self.app.save()
        self.show_section()
        self.flow_columns(self.hist.winfo_width())
        self.refresh(force=True)

    def show_section(self):
        """Show the buttons of the chosen section: both groups, or only one."""
        sec = self.v_sec.get()
        want = {"all": (0, 1), "click": (0,), "watch": (1,)}[sec]
        for i, (g, _) in enumerate(self.group_frames):
            if i not in want:
                g.grid_remove()
        self._narrow = None
        self.flow_groups()
        self.hist_title.configure(text={"all": "Test history", "click": "Click test history",
                                        "watch": "Watcher test history"}[sec])

    def retheme(self):
        p = self.app.pal
        self.app.theme_window(self)
        for tag, col in (("ok", p["good"]), ("warn", p["warn"]), ("bad", p["bad"]),
                         ("info", p["fg"])):
            self.hist.tag_configure(tag, foreground=col)
        self.hist.tag_configure("even", background=p["panel"])
        self.hist.tag_configure("odd", background=p["panel_alt"])
        for lb, lvl in getattr(self, "legend_lbls", []):
            lb.configure(foreground={"ok": p["good"], "warn": p["warn"], "bad": p["bad"]}[lvl])

    # ---------------------------------------------------------------- data
    def current_job(self):
        app = self.app
        with app.lock:
            return next((j for j in app.jobs if j["id"] == self.job_id), None)

    def select_job(self, job):
        if job:
            self.job_id = job["id"]
        self.refresh(force=True)

    def job_picked(self, event=None):
        i = self.job_box.current()
        if 0 <= i < len(self.job_ids):
            self.job_id = self.job_ids[i]
            try:
                self.app.tree.selection_set(self.job_id)
            except Exception:
                pass
        self.refresh(force=True)

    def hist_filter_changed(self):
        self.app.settings["tests_hist_filter"] = self.v_hf.get()
        scopes = dict(self.app.settings.get("tests_scopes") or {})
        scopes[self.v_sec.get()] = self.v_hf.get()
        self.app.settings["tests_scopes"] = scopes
        self.app.save()
        self.flow_columns(self.hist.winfo_width())
        self.refresh(force=True)

    def refresh(self, force=False):
        app = self.app
        with app.lock:
            jobs = [(j["id"], j["name"], is_watch(j)) for j in app.jobs]
            pending = []
            for j in app.jobs:
                if j.get("test_at"):
                    pending.append((j["test_at"], j["name"], "test click"))
                if j.get("wtest_at"):
                    pending.append((j["wtest_at"], j["name"], "watcher test"))
            dirty = app.tests_dirty
            hist = list(app.test_history)
        names = [f"{n}   ·   {'screen watcher' if w else 'scheduled click'}"
                 for _, n, w in jobs]
        if force or names != self._last_names:
            self._last_names = names
            self.job_ids = [i for i, _, _ in jobs]
            self.job_box.configure(values=names)
        if self.job_id not in self.job_ids:
            self.job_id = self.job_ids[0] if self.job_ids else None
        if self.job_id:
            idx = self.job_ids.index(self.job_id)
            if self.job_box.current() != idx:
                self.job_box.current(idx)
        else:
            self.v_job.set("")
        job = self.current_job()
        watch = bool(job and is_watch(job))
        if not job:
            self.kind_lbl.configure(text="No jobs yet. Add a click or a watcher in the main "
                                         "window first.")
        elif watch:
            self.kind_lbl.configure(text="Screen watcher: all tests are available. Tests never "
                                         "change the watcher.")
        else:
            self.kind_lbl.configure(text="Scheduled click: watcher tests need a screen watcher. "
                                         "Tests never change the schedule.")
        for b in self.btns_any:
            b.state(["!disabled"] if job else ["disabled"])
        for b in self.btns_watch:
            b.state(["!disabled"] if watch else ["disabled"])

        now = time.time()
        if pending:
            pending.sort()
            parts = [f"{n}: {what} in {fmt_dur(t - now)}" for t, n, what in pending[:3]]
            more = f"  (+{len(pending) - 3} more)" if len(pending) > 3 else ""
            self.pending_lbl.configure(text="⏱  Pending: " + "   ·   ".join(parts) + more)
            if not self.cancel_btn.winfo_ismapped():
                self.cancel_btn.pack(side="right")
        else:
            self.pending_lbl.configure(text="")
            self.cancel_btn.pack_forget()

        flt = self.v_hf.get()
        sec = self.v_sec.get()
        fb = self.hist_filter
        rows = [e for e in hist if (flt == "all" or not job or e["job"] == job["name"])
                and (sec == "all" or test_kind(e.get("test", "")) == sec)
                and fb.matches(e.get("job"), e.get("test"), e.get("result"),
                               TEST_LEVELS.get(e.get("level"), ("", ""))[1],
                               datetime.fromtimestamp(e["t"]).strftime("%m/%d %H:%M:%S"))]
        sig = (len(hist), hist[0]["t"] if hist else 0, flt, sec, job["name"] if job else "",
               fb.query())
        if force or dirty or sig != self._hist_sig:
            self._hist_sig = sig
            app.tests_dirty = False
            self.hist.delete(*self.hist.get_children())
            self.hist_rows = rows
            for i, e in enumerate(rows):
                when = datetime.fromtimestamp(e["t"]).strftime("%m/%d %H:%M:%S")
                icon, word, _ = TEST_LEVELS.get(e.get("level"), TEST_LEVELS["info"])
                self.hist.insert("", "end", iid=str(i), values=(
                    when, e["job"], e["test"], f"{icon}  {word}", e["result"]),
                    tags=(e.get("level", "info"), "odd" if i % 2 else "even"))
            self.hist_tools.done_filling()
            if rows:
                self.hist_empty.place_forget()
            else:
                what = {"all": "tests", "click": "click tests", "watch": "watcher tests"}[sec]
                self.hist_empty.configure(
                    text="Nothing matches the filter" if fb.query() else
                    f"No {what} for this job yet" if flt == "job" else f"No {what} yet")
                self.hist_empty.place(relx=0.5, rely=0.5, anchor="center")
            self.detail.configure(text="Select a result to see all the details.")

    def flow_legend(self, width):
        """The colour legend: one line when there's room, one per line when narrow."""
        need = sum(lb.winfo_reqwidth() + 14 for lb, _ in self.legend_lbls)
        stacked = width < need
        if stacked == self._legend_stacked:
            return
        self._legend_stacked = stacked
        for lb, _ in self.legend_lbls:
            lb.pack_forget()
            if stacked:
                lb.pack(side="top", anchor="w")
            else:
                lb.pack(side="left", padx=(0, 14))

    def delete_hist(self):
        """Delete test results for good: the selected ones, or the whole history."""
        sel = self.hist.selection()
        app = self.app
        if sel:
            n = len(sel)
            if not messagebox.askyesno(APP_NAME, f"Delete the {n} selected test result"
                                                 f"{'s' if n != 1 else ''} for good?",
                                       parent=self):
                return
            gone = {id(self.hist_rows[int(i)]) for i in sel if i.isdigit()
                    and int(i) < len(self.hist_rows)}
            with app.lock:
                app.test_history = [e for e in app.test_history if id(e) not in gone]
                app.tests_dirty = True
                try:
                    write_json(TESTS_PATH, app.test_history)
                except Exception:
                    pass
            app.log(f"Deleted {n} test result{'s' if n != 1 else ''}")
            self.refresh(force=True)
        else:
            app.clear_test_history(self)
            self.refresh(force=True)

    def hist_job(self, iid):
        try:
            return self.hist_rows[int(iid)]["job"]
        except Exception:
            return None

    def hist_extra(self, iid):
        try:
            e = self.hist_rows[int(iid)]
        except Exception:
            return []
        items = [("Filter to this job", lambda: self.hist_filter.var.set(e["job"])),
                 ("Filter to this test", lambda: self.hist_filter.var.set(e["test"]))]
        job = next((j for j in self.app.jobs if j["name"] == e["job"]), None)
        if job:
            items.append(("Edit this job…", lambda: JobEditor(self.app, job, is_new=False)))
        return items

    def hist_double(self, e):
        iid = self.hist.identify_row(e.y)
        if not iid:
            return
        try:
            row = self.hist_rows[int(iid)]
        except Exception:
            return
        if LOC_RE.search(row["result"]):
            self.app.show_places(row["result"], parent=self, job_name=row["job"])
            return "break"

    def show_detail(self):
        sel = self.hist.selection()
        if not sel:
            return
        try:
            e = self.hist_rows[int(sel[0])]
        except Exception:
            return
        when = datetime.fromtimestamp(e["t"]).strftime("%a %m/%d/%Y %H:%M:%S")
        self.detail.configure(text=f"{e['test']} · {e['job']} · {when}\n"
                                   + e["result"].replace(" · ", "\n"))

    # ---------------------------------------------------------------- actions
    def run(self, what):
        job = self.current_job()
        if not job:
            return
        app = self.app
        if what == "spot":
            app.show_spot_for(job, parent=self)
        elif what == "click":
            app.test_click(job, parent=self)
        elif what == "sched":
            TestDialog(app, job, parent=self)
        elif what == "check":
            app.show_watch_for(job, parent=self)
        elif what == "dry":
            app.dry_run_for(job, parent=self)
        elif what == "wsched":
            WatchTestDialog(app, job, parent=self)

    def cancel_pending(self):
        if not messagebox.askyesno(APP_NAME, "Cancel all pending scheduled tests?",
                                   parent=self):
            return
        app = self.app
        with app.lock:
            jobs = [j for j in app.jobs if j.get("test_at") or j.get("wtest_at")]
        for j in jobs:
            if j.get("test_at"):
                app.cancel_test(j)
            if j.get("wtest_at"):
                app.cancel_wtest(j)
        self.refresh(force=True)

    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
        self.remember_geometry()
        self.destroy()
        self.app.tests_closed()


class WatchTestDialog(Dialog):
    def __init__(self, app, job, parent=None):
        super().__init__(app, "Schedule a watcher test", parent)
        self.job = job
        f = self.body
        ttk.Label(f, text=f"Schedule one watcher test for \u201c{job['name']}\u201d.",
                  wraplength=440).pack(anchor="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=440, justify="left", text=(
            "At the chosen time it looks for the watched picture and for the button, "
            "exactly like the watcher does, and records what it found in the Tests history "
            "(and a tray notification). Schedule it, disconnect from RDP or hand the session "
            "to the console, and check the result when you're back. The watcher itself "
            "isn't changed.")).pack(anchor="w", pady=(6, 10))
        row = ttk.Frame(f)
        row.pack(anchor="w")
        ttk.Label(row, text="Run in").pack(side="left")
        self.v_m = tk.IntVar(value=2)
        self.v_s = tk.IntVar(value=0)
        spin_unit(row, self.v_m, 0, 1440, "min", width=5, lead=6)
        spin_unit(row, self.v_s, 0, 59, "sec", width=4)
        self.v_click = tk.BooleanVar(value=bool(job.get("wtest_click", False)))
        ttk.Checkbutton(f, text="If the picture is missing, really click the button",
                        variable=self.v_click).pack(anchor="w", pady=(10, 0))
        ttk.Label(f, text="Leave this off to only check (nothing is clicked).",
                  style="Muted.TLabel").pack(anchor="w", padx=(24, 0))
        b = self.footer
        if job.get("wtest_at"):
            ttk.Label(f, style="Warn.TLabel",
                      text=f"A watcher test is already pending for "
                           f"{fmt_time(job['wtest_at'])}.").pack(anchor="w", pady=(10, 0))
            ttk.Button(b, text="Cancel pending test", command=self.cancel).pack(side="left")
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Schedule", style="Accent.TButton", command=self.on_schedule).pack(
            side="right", padx=6)
        self.finish()

    def on_schedule(self):
        try:
            secs = int(self.v_m.get()) * 60 + int(self.v_s.get())
        except Exception:
            secs = -1
        if secs < 5:
            messagebox.showerror(APP_NAME, "Pick a time at least 5 seconds away.", parent=self)
            return
        app, j = self.app, self.job
        with app.lock:
            j["wtest_at"] = time.time() + secs
            j["wtest_deadline"] = None
            j["wtest_click"] = bool(self.v_click.get())
            when = j["wtest_at"]
        app.log(f"[{j['name']}] WATCHER TEST scheduled for {fmt_time(when)} "
                f"(in {fmt_dur(secs)}){' - will click if missing' if j['wtest_click'] else ''}. "
                f"You can disconnect now.")
        app.save()
        app.refresh_tree()
        self.destroy()

    def cancel(self):
        self.app.cancel_wtest(self.job)
        self.destroy()


class StepDialog(Dialog):
    """Add or edit one step of a job or step group."""
    TYPES = (("click", "Click a spot"), ("wait", "Wait"), ("waitpic", "Wait for a picture"),
             ("type", "Type text"), ("paste", "Paste text"), ("key", "Press keys"),
             ("if", "If (condition)"), ("repeat", "Repeat"), ("set", "Set a variable"),
             ("group", "Use a step group"), ("scroll", "Scroll"), ("drag", "Drag"),
             ("move", "Move the mouse"), ("mouse", "Mouse button down / up"),
             ("keyhold", "Hold a key down / let go"))
    COND_CHOICES = (("picture", "shown", "a picture is showing"),
                    ("picture", "gone", "a picture is NOT showing"),
                    ("window", "open", "a window is open"),
                    ("window", "closed", "a window is NOT open"),
                    ("var", "", "a variable has a value"))

    def __init__(self, app, editor, step, index=None):
        super().__init__(app, "Edit step" if index is not None else "Add a step",
                         getattr(editor, "window", editor))
        self.editor, self.index = editor, index
        self.step = dict(step)
        self.groups = list(getattr(app, "groups", []))
        f = self.body
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Step").pack(side="left", padx=(0, 8))
        names = [n for k, n in self.TYPES if k != "group" or self.groups]
        self.v_type = tk.StringVar(value=dict(self.TYPES).get(self.step.get("type", "click")))
        cb = ttk.Combobox(row, values=names, state="readonly", width=24, textvariable=self.v_type)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.show_type())
        self.frames = {}
        P = app.pal

        # ---- click
        fr = self.new_frame("click")
        br = ttk.Frame(fr)
        br.pack(anchor="w")
        ttk.Button(br, text="◎  Pick on screen…", style="Accent.TButton",
                   command=self.pick).pack(side="left")
        ttk.Button(br, text="Picture of this spot now", command=self.snap_now).pack(
            side="left", padx=6)
        self.click_info = ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left")
        self.click_info.pack(anchor="w", pady=(8, 4))
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="X").pack(side="left")
        self.v_x = tk.IntVar(value=int(self.step.get("x", 0)))
        ttk.Spinbox(r, from_=-100000, to=100000, width=7, textvariable=self.v_x).pack(side="left", padx=6)
        ttk.Label(r, text="Y").pack(side="left")
        self.v_y = tk.IntVar(value=int(self.step.get("y", 0)))
        ttk.Spinbox(r, from_=-100000, to=100000, width=7, textvariable=self.v_y).pack(side="left", padx=6)
        r2 = ttk.Frame(fr)
        r2.pack(anchor="w", pady=(6, 0))
        self.v_btn = tk.StringVar(value=self.step.get("button", "left"))
        ttk.Combobox(r2, values=("left", "right", "middle"), state="readonly", width=8,
                     textvariable=self.v_btn).pack(side="left")
        self.v_clicks = tk.StringVar(value="double" if self.step.get("clicks") == 2 else "single")
        ttk.Combobox(r2, values=("single", "double"), state="readonly", width=8,
                     textvariable=self.v_clicks).pack(side="left", padx=6)
        step_moves = (("default", "Mouse movement: as the job"),) + HUMAN_CHOICES[1:]
        self._step_moves = step_moves
        self.v_human = tk.StringVar(value=dict(step_moves)[human_choice(
            self.step.get("human_move"))])
        ttk.Combobox(r2, values=[t for _, t in step_moves], state="readonly", width=34,
                     textvariable=self.v_human).pack(side="left", padx=(6, 0))
        ttk.Label(fr, text="How to find the spot").pack(anchor="w", pady=(8, 2))
        mode = ("picture" if self.step.get("use_image", True) and self.step.get("snap_png")
                else "window" if self.step.get("target_mode") == "window" else "screen")
        if not self.step.get("snap_png") and "use_image" not in self.step:
            mode = "picture"
        self.v_find = tk.StringVar(value=mode)
        for val, text in (("picture", "By its picture (recommended: checked before clicking)"),
                          ("window", "Inside a window (follows the window)"),
                          ("screen", "Fixed screen position (not checked: only for things that "
                                     "never move)")):
            ttk.Radiobutton(fr, text=text, value=val, variable=self.v_find,
                            command=self.update_click_info).pack(anchor="w", padx=(12, 0))
            if val == "picture":
                self.v_step_exact = tk.BooleanVar(value=bool(self.step.get("exact_match", True)))
                ttk.Checkbutton(fr, text="Only the exact picture (never a similar-looking one)",
                                variable=self.v_step_exact,
                                command=self.update_click_info).pack(anchor="w", padx=(36, 0))
            if val == "window":
                wr = ttk.Frame(fr, padding=(36, 2, 0, 2))
                wr.pack(anchor="w")
                ttk.Label(wr, text="Title contains").pack(side="left")
                self.v_wtitle = tk.StringVar(value=self.step.get("window_title", ""))
                ttk.Entry(wr, textvariable=self.v_wtitle, width=26).pack(side="left", padx=6)
                ttk.Button(wr, text="Use the window at this spot", style="Small.TButton",
                           command=self.window_here).pack(side="left")
        self.target_note = ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left")
        self.target_note.pack(anchor="w", pady=(6, 0))

        # ---- wait
        fr = self.new_frame("wait")
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="Wait").pack(side="left")
        self.v_wmin = tk.DoubleVar(value=float(self.step.get("min", 2)))
        ttk.Spinbox(r, from_=0, to=86400, increment=0.5, width=7, textvariable=self.v_wmin).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="to").pack(side="left")
        self.v_wmax = tk.DoubleVar(value=float(self.step.get("max", self.step.get("min", 2))))
        ttk.Spinbox(r, from_=0, to=86400, increment=0.5, width=7, textvariable=self.v_wmax).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="seconds (the same number twice = exactly that long)",
                  style="Muted.TLabel").pack(side="left")

        # ---- type / paste (one text box, shown for both)
        self.text_frame = ttk.Frame(f, padding=(0, 10, 0, 0))
        tf = self.text_frame
        self.text_hint = ttk.Label(tf, style="Muted.TLabel", wraplength=460, justify="left")
        self.text_hint.pack(anchor="w")
        self.txt = tk.Text(tf, height=7, width=54, wrap="word", bd=0, padx=8, pady=6,
                           undo=True, bg=P["field"], fg=P["fg"], insertbackground=P["fg"],
                           highlightthickness=1, highlightbackground=P["border"],
                           highlightcolor=P["accent"])
        self.txt.pack(fill="both", expand=True, pady=(6, 0))
        self.secret_loaded = False
        text = self.step.get("text", "")
        if self.step.get("secret") and self.step.get("text_enc"):
            try:
                text = unprotect_text(self.step["text_enc"])
                self.secret_loaded = True
            except ValueError:
                text = ""
        self.txt.insert("1.0", text)
        self.txt.bind("<KeyRelease>", lambda e: self.update_count())
        self.count_lbl = ttk.Label(tf, style="Muted.TLabel")
        self.count_lbl.pack(anchor="e")
        self.v_vars = tk.BooleanVar(value=bool(self.step.get("use_vars", False))
                                    if "text" in self.step or "text_enc" in self.step else False)
        ttk.Checkbutton(tf, variable=self.v_vars, text=(
            "Fill in {variables}: {date} {time} {datetime} {job} {run} {loop} and any set by "
            "earlier steps ({{ and }} give a brace)")).pack(anchor="w", pady=(4, 0))
        self.v_secret = tk.BooleanVar(value=bool(self.step.get("secret", False)))
        sc = ttk.Checkbutton(tf, variable=self.v_secret, command=self.secret_toggled, text=(
            "Secret: protect it with your Windows account, hide it in the list, never export "
            "it"))
        sc.pack(anchor="w", pady=(2, 0))
        if not HAVE_DPAPI:
            sc.state(["disabled"])
        self.paste_opts = ttk.Frame(tf)
        r = ttk.Frame(self.paste_opts)
        r.pack(anchor="w", pady=(6, 0))
        ttk.Label(r, text="Paste with").pack(side="left")
        self.v_pkeys = tk.StringVar(value=self.step.get("paste_keys", "Ctrl+V"))
        ttk.Combobox(r, values=PASTE_KEYS, state="readonly", width=13,
                     textvariable=self.v_pkeys).pack(side="left", padx=6)
        ttk.Label(r, text="(Shift+Insert works in most terminals)", style="Muted.TLabel").pack(
            side="left")
        self.v_restore = tk.BooleanVar(value=bool(self.step.get("restore_clipboard", True)))
        ttk.Checkbutton(self.paste_opts, variable=self.v_restore, text=(
            "Put back what was on the clipboard afterwards")).pack(anchor="w", pady=(4, 0))
        r = ttk.Frame(self.paste_opts)
        r.pack(anchor="w", pady=(4, 0))
        ttk.Label(r, text="Wait after pasting").pack(side="left")
        self.v_settle = tk.DoubleVar(value=float(self.step.get("settle", 0.3)))
        ttk.Spinbox(r, from_=0.05, to=5, increment=0.05, width=6,
                    textvariable=self.v_settle).pack(side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="s before the clipboard is put back (slow programs may need more)",
                  style="Muted.TLabel").pack(side="left")

        # ---- wait for a picture
        fr = self.new_frame("waitpic")
        top = ttk.Frame(fr)
        top.pack(fill="x")
        self.pic_lbl = ttk.Label(top, style="Thumb.TLabel", anchor="center", width=24)
        self.pic_lbl.pack(side="left", anchor="n")
        rc = ttk.Frame(top, padding=(12, 0, 0, 0))
        rc.pack(side="left", fill="x", expand=True, anchor="n")
        ttk.Button(rc, text="▢  Draw box around picture…", style="Accent.TButton",
                   command=lambda: self.draw_pic("png")).pack(anchor="w")
        ttk.Label(rc, style="Muted.TLabel", wraplength=280, justify="left", text=(
            "Draw a box around what the previous step should make appear (or disappear), "
            "e.g. the next button or a “Done” message.")).pack(anchor="w", pady=(6, 0))
        self.v_until = tk.StringVar(value=self.step.get("until", "appears"))
        r = ttk.Frame(fr)
        r.pack(anchor="w", pady=(10, 0))
        ttk.Label(r, text="Wait until it").pack(side="left", padx=(0, 6))
        ttk.Radiobutton(r, text="appears", value="appears", variable=self.v_until,
                        command=self.until_changed).pack(side="left")
        ttk.Radiobutton(r, text="goes away", value="disappears", variable=self.v_until,
                        command=self.until_changed).pack(side="left", padx=(10, 0))
        r = ttk.Frame(fr)
        r.pack(anchor="w", pady=(6, 0))
        self.v_click_it = tk.BooleanVar(value=bool(self.step.get("click_it", True)))
        self.click_it_cb = ttk.Checkbutton(r, text="then click it (where it appeared) with",
                                           variable=self.v_click_it)
        self.click_it_cb.pack(side="left")
        self.v_pbtn = tk.StringVar(value=self.step.get("button", "left"))
        self.pbtn_cb = ttk.Combobox(r, values=("left", "right", "middle"), state="readonly",
                                    width=7, textvariable=self.v_pbtn)
        self.pbtn_cb.pack(side="left", padx=6)
        self.v_pclicks = tk.StringVar(value="double" if self.step.get("clicks") == 2 else "single")
        self.pclk_cb = ttk.Combobox(r, values=("single", "double"), state="readonly", width=7,
                                    textvariable=self.v_pclicks)
        self.pclk_cb.pack(side="left")
        r = ttk.Frame(fr)
        r.pack(anchor="w", pady=(8, 0))
        ttk.Label(r, text="Wait up to").pack(side="left")
        self.v_ptimeout = tk.IntVar(value=int(self.step.get("timeout", 60)))
        ttk.Spinbox(r, from_=1, to=STEP_MAX_WAIT_S, width=6, textvariable=self.v_ptimeout).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="seconds; if it doesn't happen,").pack(side="left")
        self.v_ponto = tk.StringVar(value="continue anyway" if self.step.get("on_timeout") ==
                                    "continue" else "stop the chain")
        ttk.Combobox(r, values=("stop the chain", "continue anyway"), state="readonly", width=15,
                     textvariable=self.v_ponto).pack(side="left", padx=6)
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "It looks about once a second. Other jobs wait their turn meanwhile (the mouse can "
            "only do one thing at a time), unless the job lets others go first in Run "
            "options. Watchers keep watching.")).pack(anchor="w", pady=(8, 0))
        self._pic_thumb = None

        # ---- keys
        fr = self.new_frame("key")
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="Keys").pack(side="left")
        self.v_keys = tk.StringVar(value=self.step.get("keys", "Enter"))
        ttk.Entry(r, textvariable=self.v_keys, width=22).pack(side="left", padx=6)
        ttk.Label(r, text="times").pack(side="left")
        self.v_times = tk.IntVar(value=int(self.step.get("times", 1)))
        ttk.Spinbox(r, from_=1, to=100, width=4, textvariable=self.v_times).pack(side="left", padx=(6, UNIT_GAP))
        qr = ttk.Frame(fr)
        qr.pack(anchor="w", pady=(6, 0))
        for k in ("Enter", "Tab", "Esc", "Ctrl+S", "Ctrl+A", "Ctrl+V", "F5", "Alt+Tab"):
            ttk.Button(qr, text=k, style="Small.TButton",
                       command=lambda k=k: self.v_keys.set(k)).pack(side="left", padx=(0, 4))
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "Combine with +, e.g. Ctrl+Shift+S. Names: Ctrl, Alt, Shift, Win, Enter, Tab, Esc, "
            "Space, Backspace, Delete, Insert, Up, Down, Left, Right, Home, End, PageUp, "
            "PageDown, F1-F24, Num0-Num9, letters and digits, or a key code like 0xBA.")).pack(
            anchor="w", pady=(6, 0))

        # ---- condition (shared by If and Repeat until)
        self.cond = dict(self.step.get("cond") or {"kind": "picture", "state": "shown"})
        self.cond_frame = ttk.Frame(f, padding=(0, 10, 0, 0))
        cf = self.cond_frame
        r = ttk.Frame(cf)
        r.pack(anchor="w")
        self.cond_lbl = ttk.Label(r, text="If")
        self.cond_lbl.pack(side="left")
        cur = next((t for k, st_, t in self.COND_CHOICES if k == self.cond.get("kind")
                    and (k == "var" or st_ == self.cond.get("state", "shown" if k == "picture"
                                                            else "open"))),
                   self.COND_CHOICES[0][2])
        self.v_cond = tk.StringVar(value=cur)
        cc = ttk.Combobox(r, values=[t for _, _, t in self.COND_CHOICES], state="readonly",
                          width=26, textvariable=self.v_cond)
        cc.pack(side="left", padx=6)
        cc.bind("<<ComboboxSelected>>", lambda e: self.cond_changed())
        self.cond_pic = ttk.Frame(cf)
        self.cpic_lbl = ttk.Label(self.cond_pic, style="Thumb.TLabel", anchor="center", width=24)
        self.cpic_lbl.pack(side="left", anchor="n", pady=(6, 0))
        ttk.Button(self.cond_pic, text="▢  Draw box around picture…",
                   command=lambda: self.draw_pic("cond")).pack(side="left", anchor="n",
                                                               padx=10, pady=(6, 0))
        self.cond_win = ttk.Frame(cf)
        ttk.Label(self.cond_win, text="Window title contains").pack(side="left", pady=(6, 0))
        self.v_ctitle = tk.StringVar(value=self.cond.get("title", ""))
        ttk.Entry(self.cond_win, textvariable=self.v_ctitle, width=30).pack(side="left", padx=6,
                                                                           pady=(6, 0))
        self.cond_var = ttk.Frame(cf)
        ttk.Label(self.cond_var, text="{").pack(side="left", pady=(6, 0))
        self.v_cvar = tk.StringVar(value=self.cond.get("var", "count"))
        ttk.Entry(self.cond_var, textvariable=self.v_cvar, width=12).pack(side="left", pady=(6, 0))
        ttk.Label(self.cond_var, text="}").pack(side="left", pady=(6, 0))
        self.v_cop = tk.StringVar(value=self.cond.get("op", "=="))
        ttk.Combobox(self.cond_var, values=VAR_OPS, state="readonly", width=8,
                     textvariable=self.v_cop).pack(side="left", padx=6, pady=(6, 0))
        self.v_cval = tk.StringVar(value=self.cond.get("value", ""))
        ttk.Entry(self.cond_var, textvariable=self.v_cval, width=16).pack(side="left", pady=(6, 0))
        self.cond_wait = ttk.Frame(cf)
        ttk.Label(self.cond_wait, text="Wait up to").pack(side="left", pady=(6, 0))
        self.v_cwait = tk.DoubleVar(value=float(self.cond.get("wait", 0)))
        ttk.Spinbox(self.cond_wait, from_=0, to=STEP_MAX_WAIT_S, increment=1, width=6,
                    textvariable=self.v_cwait).pack(side="left", padx=(6, UNIT_GAP), pady=(6, 0))
        ttk.Label(self.cond_wait, text="seconds for it to become true (0 = check once)",
                  style="Muted.TLabel").pack(side="left", pady=(6, 0))
        self._cthumb = None

        # ---- if
        fr = self.new_frame("if")
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "The steps between If and End run only when the condition is true. Add an "
            "“Otherwise” step inside to run other steps when it isn't. An End is added for "
            "you; move steps between them with ▲ ▼.")).pack(anchor="w")

        # ---- repeat
        fr = self.new_frame("repeat")
        self.v_rmode = tk.StringVar(value=self.step.get("mode", "times"))
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Radiobutton(r, text="Repeat", value="times", variable=self.v_rmode,
                        command=self.show_type).pack(side="left")
        self.v_rtimes = tk.IntVar(value=int(self.step.get("times", 3)))
        ttk.Spinbox(r, from_=1, to=MAX_REPEAT, width=6, textvariable=self.v_rtimes).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="times").pack(side="left")
        r = ttk.Frame(fr)
        r.pack(anchor="w", pady=(4, 0))
        ttk.Radiobutton(r, text="Repeat until the condition below is true, at most",
                        value="until", variable=self.v_rmode, command=self.show_type).pack(
            side="left")
        self.v_rmax = tk.IntVar(value=int(self.step.get("max_times", 100)))
        ttk.Spinbox(r, from_=1, to=MAX_REPEAT, width=6, textvariable=self.v_rmax).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="times and").pack(side="left")
        self.v_rsecs = tk.IntVar(value=int(self.step.get("max_seconds", 600)))
        ttk.Spinbox(r, from_=1, to=MAX_RUN_LIMIT_S, width=7, textvariable=self.v_rsecs).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="seconds").pack(side="left")
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "The steps between Repeat and End run again and again. {loop} is the pass number "
            "(1, 2, 3…). The limits always apply, so a loop can't run forever.")).pack(
            anchor="w", pady=(6, 0))

        # ---- set a variable
        fr = self.new_frame("set")
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="{").pack(side="left")
        self.v_var = tk.StringVar(value=self.step.get("var", "count"))
        ttk.Entry(r, textvariable=self.v_var, width=14).pack(side="left")
        ttk.Label(r, text="}").pack(side="left")
        self.v_op = tk.StringVar(value={"add": "add", "sub": "subtract"}.get(
            self.step.get("op"), "set to"))
        ttk.Combobox(r, values=("set to", "add", "subtract"), state="readonly", width=9,
                     textvariable=self.v_op).pack(side="left", padx=6)
        self.v_val = tk.StringVar(value=self.step.get("value", "1"))
        ttk.Entry(r, textvariable=self.v_val, width=24).pack(side="left")
        self.v_persist = tk.BooleanVar(value=bool(self.step.get("persist", False)))
        ttk.Checkbutton(fr, variable=self.v_persist, text="Remember it for the next run (e.g. a "
                                                         "counter that keeps going up)").pack(
            anchor="w", pady=(6, 0))
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "Names: letters, digits and _. The value may use other variables, e.g. "
            "“{date}-{count}”. Use them in Type/Paste text (tick “Fill in {variables}”) and "
            "in conditions.")).pack(anchor="w", pady=(6, 0))

        # ---- use a group
        fr = self.new_frame("group")
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="Run the steps of").pack(side="left")
        gname = next((g["name"] for g in self.groups if g["id"] == self.step.get("group_id")),
                     self.groups[0]["name"] if self.groups else "")
        self.v_group = tk.StringVar(value=gname)
        ttk.Combobox(r, values=[g["name"] for g in self.groups], state="readonly", width=28,
                     textvariable=self.v_group).pack(side="left", padx=6)
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "Change a group once in ☰ Menu → Step groups and every job that uses it gets the "
            "change.")).pack(anchor="w", pady=(6, 0))

        # ---- scroll
        fr = self.new_frame("scroll")
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="Scroll").pack(side="left")
        amt = int(self.step.get("amount", -3))
        self.v_samt = tk.IntVar(value=abs(amt) or 3)
        ttk.Spinbox(r, from_=1, to=100, width=5, textvariable=self.v_samt).pack(side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="notches").pack(side="left")
        self.v_sdir = tk.StringVar(value=("left" if amt < 0 else "right")
                                   if self.step.get("horizontal") else
                                   ("down" if amt < 0 else "up"))
        ttk.Combobox(r, values=("down", "up", "left", "right"), state="readonly", width=7,
                     textvariable=self.v_sdir).pack(side="left", padx=6)
        self.pos_rows = {}
        self.pos_row(fr, "scroll", "Point at this spot first")

        # ---- mouse button down / up
        fr = self.new_frame("mouse")
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        self.v_maction = tk.StringVar(value="Press and hold" if self.step.get("action", "down")
                                      == "down" else "Let go of")
        ttk.Combobox(r, values=("Press and hold", "Let go of"), state="readonly", width=14,
                     textvariable=self.v_maction).pack(side="left")
        ttk.Label(r, text="the").pack(side="left", padx=6)
        self.v_mbtn = tk.StringVar(value=self.step.get("button", "left"))
        ttk.Combobox(r, values=("left", "right", "middle"), state="readonly", width=8,
                     textvariable=self.v_mbtn).pack(side="left")
        ttk.Label(r, text="mouse button").pack(side="left", padx=6)
        self.pos_row(fr, "mouse", "Move to this spot first")
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "Clickue always lets go of held buttons when a run ends, fails or is stopped.")).pack(
            anchor="w", pady=(6, 0))

        # ---- move / drag
        for kind in ("move", "drag"):
            fr = self.new_frame(kind)
            path = self.step.get("path") or []
            if kind == "drag":
                r = ttk.Frame(fr)
                r.pack(anchor="w", pady=(0, 6))
                ttk.Label(r, text="Drag with the").pack(side="left")
                self.v_dbtn = tk.StringVar(value=self.step.get("button", "left"))
                ttk.Combobox(r, values=("left", "right", "middle"), state="readonly", width=8,
                             textvariable=self.v_dbtn).pack(side="left", padx=6)
                ttk.Label(r, text="button").pack(side="left")
            ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
                f"Recorded path: {len(path)} points over {fmt_secs(path[-1][0])}. Changing the "
                f"points below replaces it with a straight line." if len(path) > 2 else
                "A straight line from the start to the end, over the time below.")).pack(anchor="w")
        self.path_vars = {}
        for kind in ("move", "drag"):
            path = self.step.get("path") or [[0, 0, 0], [1.0, 0, 0]]
            fr = self.frames[kind]
            vs = {}
            for which, pt in (("start", path[0]), ("end", path[-1])):
                r = ttk.Frame(fr)
                r.pack(anchor="w", pady=(6, 0))
                ttk.Label(r, text=f"{which.capitalize():6}  X").pack(side="left")
                vs[which + "x"] = tk.IntVar(value=int(pt[1]))
                ttk.Spinbox(r, from_=-100000, to=100000, width=7,
                            textvariable=vs[which + "x"]).pack(side="left", padx=4)
                ttk.Label(r, text="Y").pack(side="left")
                vs[which + "y"] = tk.IntVar(value=int(pt[2]))
                ttk.Spinbox(r, from_=-100000, to=100000, width=7,
                            textvariable=vs[which + "y"]).pack(side="left", padx=4)
                ttk.Button(r, text="Pick…", style="Small.TButton",
                           command=lambda vs=vs, w=which: self.pick_xy(vs[w + "x"], vs[w + "y"])).pack(
                    side="left", padx=4)
            r = ttk.Frame(fr)
            r.pack(anchor="w", pady=(6, 0))
            ttk.Label(r, text="Takes").pack(side="left")
            vs["dur"] = tk.DoubleVar(value=float(path[-1][0] or 0.5))
            ttk.Spinbox(r, from_=0, to=3600, increment=0.1, width=6,
                        textvariable=vs["dur"]).pack(side="left", padx=(6, UNIT_GAP))
            ttk.Label(r, text="seconds").pack(side="left")
            vs["orig"] = (path[0][1], path[0][2], path[-1][1], path[-1][2], path[-1][0])
            self.path_vars[kind] = vs

        # ---- hold a key
        fr = self.new_frame("keyhold")
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        self.v_haction = tk.StringVar(value="Hold down" if self.step.get("action", "down")
                                      == "down" else "Let go of")
        ttk.Combobox(r, values=("Hold down", "Let go of"), state="readonly", width=11,
                     textvariable=self.v_haction).pack(side="left")
        self.v_hkey = tk.StringVar(value=self.step.get("keys", "Shift"))
        ttk.Entry(r, textvariable=self.v_hkey, width=12).pack(side="left", padx=6)
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "For Shift+click or Ctrl+drag: hold the key, do the clicks, then let it go. "
            "Clickue always lets go of held keys when a run ends, fails or is stopped.")).pack(
            anchor="w", pady=(6, 0))

        # ---- common options
        self.common = ttk.LabelFrame(f, text="This step", padding=(10, 6))
        r = ttk.Frame(self.common)
        r.pack(anchor="w")
        ttk.Label(r, text="Name (optional)").pack(side="left")
        self.v_label = tk.StringVar(value=self.step.get("label", ""))
        ttk.Entry(r, textvariable=self.v_label, width=30).pack(side="left", padx=6)
        r = ttk.Frame(self.common)
        r.pack(anchor="w", pady=(6, 0))
        ttk.Label(r, text="If it fails, try again").pack(side="left")
        self.v_retries = tk.IntVar(value=int(self.step.get("retries", 0)))
        ttk.Spinbox(r, from_=0, to=10, width=4, textvariable=self.v_retries).pack(side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="more times, waiting").pack(side="left")
        self.v_rwait = tk.DoubleVar(value=float(self.step.get("retry_wait", 2)))
        ttk.Spinbox(r, from_=0, to=3600, increment=1, width=5, textvariable=self.v_rwait).pack(
            side="left", padx=(6, UNIT_GAP))
        ttk.Label(r, text="s in between").pack(side="left")
        r = ttk.Frame(self.common)
        r.pack(anchor="w", pady=(6, 0))
        ttk.Label(r, text="If it still fails").pack(side="left")
        self.v_onfail = tk.StringVar(value="continue with the next step"
                                     if self.step.get("on_fail") == "continue"
                                     else "stop the job's run")
        ttk.Combobox(r, values=("stop the job's run", "continue with the next step"),
                     state="readonly", width=26, textvariable=self.v_onfail).pack(side="left",
                                                                                 padx=6)
        self.v_careful = tk.BooleanVar(value=bool(self.step.get("careful", False)))
        ttk.Checkbutton(self.common, variable=self.v_careful, text=(
            "⚠ Careful step (sends, deletes, buys…): Step through stops here even when "
            "running to the end")).pack(anchor="w", pady=(6, 0))

        b = self.footer
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Save step", style="Accent.TButton", command=self.on_save).pack(
            side="right", padx=6)
        self.update_click_info()
        self.update_pic_thumb()
        self.update_cond_thumb()
        self.until_changed()
        self.cond_changed()
        self.update_count()
        self.show_type()
        self.finish()

    def geom_key(self):
        return f"StepDialog-{self.step.get('type', 'click')}"

    # ---- layout helpers
    def new_frame(self, kind):
        fr = ttk.Frame(self.body, padding=(0, 10, 0, 0))
        self.frames[kind] = fr
        return fr

    def pos_row(self, fr, kind, text):
        on = self.step.get("x") is not None and self.step.get("type") == kind
        v_on = tk.BooleanVar(value=on)
        vx = tk.IntVar(value=int(self.step.get("x") or 0))
        vy = tk.IntVar(value=int(self.step.get("y") or 0))
        r = ttk.Frame(fr)
        r.pack(anchor="w", pady=(6, 0))
        ttk.Checkbutton(r, text=text, variable=v_on).pack(side="left")
        ttk.Label(r, text=" X").pack(side="left")
        ttk.Spinbox(r, from_=-100000, to=100000, width=7, textvariable=vx).pack(side="left", padx=4)
        ttk.Label(r, text="Y").pack(side="left")
        ttk.Spinbox(r, from_=-100000, to=100000, width=7, textvariable=vy).pack(side="left", padx=4)
        ttk.Button(r, text="Pick…", style="Small.TButton",
                   command=lambda: (v_on.set(True), self.pick_xy(vx, vy))).pack(side="left", padx=4)
        self.pos_rows[kind] = (v_on, vx, vy)

    def kind(self):
        return {n: k for k, n in self.TYPES}.get(self.v_type.get(), "click")

    def show_type(self):
        k = self.kind()
        for fr in list(self.frames.values()) + [self.text_frame, self.cond_frame, self.common]:
            fr.pack_forget()
        if k in TEXT_STEPS:
            self.text_frame.pack(fill="both", expand=True)
            if k == "paste":
                self.paste_opts.pack(anchor="w", fill="x")
                self.text_hint.configure(text=(
                    "Text to paste into whatever has focus (add a Click on the field first). It "
                    "is pasted exactly as written: several lines, any language, symbols. "
                    f"Up to {MAX_PASTE_CHARS:,} characters. Faster than typing, and the clipboard "
                    "is put back afterwards."))
            else:
                self.paste_opts.pack_forget()
                self.text_hint.configure(text=(
                    "Text to type into whatever has focus (add a Click on the field first). Each "
                    "character is typed like on a keyboard; a new line presses Enter. "
                    f"Up to {MAX_TYPE_CHARS:,} characters. Use Paste for long text."))
            self.update_count()
        else:
            self.frames[k].pack(fill="x")
        if k == "if" or (k == "repeat" and self.v_rmode.get() == "until"):
            self.cond_lbl.configure(text="If" if k == "if" else "Until")
            self.cond_frame.pack(fill="x")
        self.common.pack(fill="x", pady=(12, 0))
        self.after(30, self._sync_scroll)

    def update_count(self):
        n = len(self.txt.get("1.0", "end-1c"))
        lim = MAX_TYPE_CHARS if self.kind() == "type" else MAX_PASTE_CHARS
        self.count_lbl.configure(text=f"{n:,} / {lim:,} characters",
                                 style="Warn.TLabel" if n > lim else "Muted.TLabel")

    def secret_toggled(self):
        if self.v_secret.get():
            self.v_vars.set(False)

    def until_changed(self):
        on = self.v_until.get() == "appears"
        for w in (self.click_it_cb, self.pbtn_cb, self.pclk_cb):
            w.state(["!disabled"] if on else ["disabled"])
            if on and isinstance(w, ttk.Combobox):
                w.state(["readonly"])

    def cond_changed(self):
        choice = next((c for c in self.COND_CHOICES if c[2] == self.v_cond.get()),
                      self.COND_CHOICES[0])
        for fr in (self.cond_pic, self.cond_win, self.cond_var, self.cond_wait):
            fr.pack_forget()
        {"picture": self.cond_pic, "window": self.cond_win, "var": self.cond_var}[choice[0]].pack(
            anchor="w")
        if choice[0] != "var":
            self.cond_wait.pack(anchor="w")

    def thumb(self, label, png, attr):
        if not (HAVE_PIL and png):
            label.configure(image="", text="No picture yet")
            return
        try:
            img = b64_to_img(png)
            f = min(200 / img.width, 110 / img.height, 3.0)
            if abs(f - 1) > 0.05:
                img = img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))))
            setattr(self, attr, ImageTk.PhotoImage(img))
            label.configure(image=getattr(self, attr), text="")
        except Exception:
            label.configure(image="", text="(picture unreadable)")

    def update_pic_thumb(self):
        self.thumb(self.pic_lbl, self.step.get("png"), "_pic_thumb")

    def update_cond_thumb(self):
        self.thumb(self.cpic_lbl, self.cond.get("png"), "_cthumb")

    def draw_pic(self, which):
        def done(img):
            if which == "png":
                self.step["png"] = img_to_b64(img)
                self.update_pic_thumb()
            else:
                self.cond["png"] = img_to_b64(img)
                self.update_cond_thumb()
        self.app.draw_capture(self, "Drag a box around the picture", done)

    def update_click_info(self):
        mode = self.v_find.get()
        if self.step.get("snap_png"):
            self.click_info.configure(text="A picture of the spot is saved.")
        else:
            self.click_info.configure(text="Click “Pick on screen”, then point at the spot "
                                           "within 5 seconds (a picture of it is saved too).")
        tgt = {"use_image": mode == "picture" and bool(self.step.get("snap_png")),
               "exact_match": bool(self.v_step_exact.get()) if hasattr(self, "v_step_exact")
               else True,
               "snap_png": self.step.get("snap_png", ""), "target_mode": mode,
               "window_title": self.v_wtitle.get(), "x": self.v_x.get(), "y": self.v_y.get()}
        if mode == "picture" and not self.step.get("snap_png"):
            note = "No picture saved yet: pick the spot, or take a picture of it now."
        else:
            note = adapter_for(tgt).describe(tgt)
        self.target_note.configure(text="Targeting: " + note)

    def pick(self):
        def done(x, y, png, spot):
            self.v_x.set(x)
            self.v_y.set(y)
            self.step.update(snap_png=png, snap_spot=spot, pick_dpi=system_dpi(),
                             pick_screen=list(screen_size()))
            if png and self.v_find.get() == "screen":
                self.v_find.set("picture")
            self.update_click_info()
        self.app.pick_point(self, done)

    def pick_xy(self, vx, vy):
        self.app.pick_point(self, lambda x, y, png, spot: (vx.set(x), vy.set(y)))

    def snap_now(self):
        """Save a picture of the spot at X, Y as it looks now (e.g. for recorded clicks)."""
        if not (HAVE_PIL and HAVE_CV):
            messagebox.showwarning(APP_NAME, "Pictures need pillow, opencv and numpy.", parent=self)
            return
        try:
            x, y = int(self.v_x.get()), int(self.v_y.get())
        except Exception:
            return
        restore = self.app.hide_all_windows()

        def go():
            try:
                img, spot, detail = capture_snapshot(x, y, "Medium")
                ok = detail >= 6
                if ok:
                    self.step.update(snap_png=img_to_b64(img), snap_spot=list(spot),
                                     pick_dpi=system_dpi(), pick_screen=list(screen_size()))
                    self.v_find.set("picture")
            except Exception as e:
                ok = False
                detail = str(e)
            restore()
            self.update_click_info()
            if not ok:
                messagebox.showwarning(APP_NAME, "That spot is very plain (or couldn't be "
                                                 "captured), so it can't be found by its picture. "
                                                 "Use a window or fixed position instead.",
                                       parent=self)
        self.after(500, go)

    def window_here(self):
        if not IS_WIN:
            return
        try:
            info = describe_point(int(self.v_x.get()), int(self.v_y.get()))
        except Exception:
            info = None
        h = window_at(int(self.v_x.get()), int(self.v_y.get())) if IS_WIN else None
        title = win_text(h) if h else ""
        if not title or is_own_window(h):
            messagebox.showinfo(APP_NAME, "No window was found at that spot right now. Open the "
                                          "window, then try again.", parent=self)
            return
        ox, oy, cw, ch = client_origin(h)
        self.step.update(rel_x=int(self.v_x.get()) - ox, rel_y=int(self.v_y.get()) - oy,
                         client_w=cw, client_h=ch, window_class=win_class(h))
        self.v_wtitle.set(title[:300])
        self.v_find.set("window")
        self.update_click_info()
        del info

    # ---- saving
    def text_value(self):
        return self.txt.get("1.0", "end-1c")

    def cond_value(self):
        choice = next((c for c in self.COND_CHOICES if c[2] == self.v_cond.get()),
                      self.COND_CHOICES[0])
        k = choice[0]
        if k == "picture":
            if not self.cond.get("png"):
                raise ValueError("draw a box around the picture for the condition")
            c = {"kind": "picture", "png": self.cond["png"], "state": choice[1],
                 "area": self.cond.get("area"), "wait": max(0.0, float(self.v_cwait.get()))}
        elif k == "window":
            if not self.v_ctitle.get().strip():
                raise ValueError("enter the window title for the condition")
            c = {"kind": "window", "title": self.v_ctitle.get().strip(), "state": choice[1],
                 "wait": max(0.0, float(self.v_cwait.get()))}
        else:
            var = self.v_cvar.get().strip()
            if not VAR_NAME_RE.match(var):
                raise ValueError("the variable name may only use letters, digits and _")
            c = {"kind": "var", "var": var, "op": self.v_cop.get(), "value": self.v_cval.get()}
        return clean_cond(c)

    def on_save(self):
        k = self.kind()
        st = {"type": k}
        try:
            if k == "click":
                mode = self.v_find.get()
                st.update(x=int(self.v_x.get()), y=int(self.v_y.get()), button=self.v_btn.get(),
                          clicks=2 if self.v_clicks.get() == "double" else 1,
                          human_move=human_value({t: k for k, t in self._step_moves}.get(
                              self.v_human.get(), "default")),
                          use_image=mode == "picture" and bool(self.step.get("snap_png")),
                          snap_png=self.step.get("snap_png", ""),
                          snap_spot=self.step.get("snap_spot"),
                          pick_dpi=self.step.get("pick_dpi"),
                          pick_screen=self.step.get("pick_screen"),
                          image_fallback="wait",
                          exact_match=bool(self.v_step_exact.get()),
                          target_mode="window" if mode == "window" else "screen",
                          window_title=self.v_wtitle.get().strip() if mode == "window" else "",
                          window_class=self.step.get("window_class", "") if mode == "window" else "",
                          rel_x=self.step.get("rel_x", 0), rel_y=self.step.get("rel_y", 0),
                          client_w=self.step.get("client_w", 0),
                          client_h=self.step.get("client_h", 0),
                          bring_to_front=True)
                if mode == "picture" and not st["snap_png"]:
                    raise ValueError("pick the spot (or take a picture of it) to find it by its "
                                     "picture")
                if mode == "window" and not st["window_title"]:
                    raise ValueError("enter the window title, or use the window at this spot")
                if mode == "window" and not (st["rel_x"] or st["rel_y"]):
                    raise ValueError("use “Use the window at this spot” so Clickue knows where "
                                     "inside the window to click")
                if st["x"] == 0 and st["y"] == 0 and not st["snap_png"] and mode == "screen":
                    raise ValueError("pick the spot to click first")
            elif k == "wait":
                lo, hi = float(self.v_wmin.get()), float(self.v_wmax.get())
                if hi < lo:
                    lo, hi = hi, lo
                lo, hi = max(0.0, lo), max(0.0, hi)
                st.update(min=int(lo) if lo.is_integer() else round(lo, 2),
                          max=int(hi) if hi.is_integer() else round(hi, 2))
            elif k == "waitpic":
                if not self.step.get("png"):
                    raise ValueError("draw a box around the picture to wait for first")
                st.update(png=self.step["png"], until=self.v_until.get(),
                          click_it=bool(self.v_click_it.get()) and self.v_until.get() == "appears",
                          button=self.v_pbtn.get(),
                          clicks=2 if self.v_pclicks.get() == "double" else 1,
                          timeout=max(1, min(STEP_MAX_WAIT_S, int(self.v_ptimeout.get()))),
                          on_timeout="continue" if self.v_ponto.get().startswith("continue")
                          else "stop", area=self.step.get("area"))
            elif k in TEXT_STEPS:
                text = self.text_value()
                lim = MAX_TYPE_CHARS if k == "type" else MAX_PASTE_CHARS
                if not text:
                    raise ValueError("enter the text")
                if len(text) > lim:
                    raise ValueError(f"the text has {len(text):,} characters; the limit is "
                                     f"{lim:,}" + (" (use Paste text for long text)" if k == "type"
                                                   else ""))
                st.update(use_vars=bool(self.v_vars.get()), secret=bool(self.v_secret.get()))
                if st["secret"]:
                    try:
                        st["text_enc"] = protect_text(text)
                    except Exception as e:
                        raise ValueError(f"couldn't protect the secret text ({e})")
                    st["text"] = ""
                    st["use_vars"] = False
                else:
                    st["text"] = text
                if k == "paste":
                    st.update(paste_keys=self.v_pkeys.get(),
                              restore_clipboard=bool(self.v_restore.get()),
                              settle=max(0.05, min(5.0, float(self.v_settle.get()))))
            elif k == "key":
                parse_combo(self.v_keys.get())
                st.update(keys=self.v_keys.get().strip(),
                          times=max(1, min(100, int(self.v_times.get()))))
            elif k == "if":
                st["cond"] = self.cond_value()
            elif k == "repeat":
                st.update(mode=self.v_rmode.get(),
                          times=max(1, min(MAX_REPEAT, int(self.v_rtimes.get()))),
                          max_times=max(1, min(MAX_REPEAT, int(self.v_rmax.get()))),
                          max_seconds=max(1, min(MAX_RUN_LIMIT_S, int(self.v_rsecs.get()))))
                if st["mode"] == "until":
                    st["cond"] = self.cond_value()
            elif k == "set":
                var = self.v_var.get().strip()
                if not VAR_NAME_RE.match(var):
                    raise ValueError("the variable name may only use letters, digits and _ "
                                     "(and not start with a digit)")
                op = {"add": "add", "subtract": "sub"}.get(self.v_op.get(), "set")
                if op != "set" and _as_number(self.v_val.get()) is None and \
                        "{" not in self.v_val.get():
                    raise ValueError("to add or subtract, the value must be a number")
                st.update(var=var, op=op, value=self.v_val.get()[:1000],
                          persist=bool(self.v_persist.get()))
            elif k == "group":
                g = next((g for g in self.groups if g["name"] == self.v_group.get()), None)
                if not g:
                    raise ValueError("choose a step group")
                st["group_id"] = g["id"]
            elif k == "scroll":
                n = max(1, min(100, int(self.v_samt.get())))
                d = self.v_sdir.get()
                on, vx, vy = self.pos_rows["scroll"]
                st.update(amount=-n if d in ("down", "left") else n,
                          horizontal=d in ("left", "right"),
                          x=int(vx.get()) if on.get() else None,
                          y=int(vy.get()) if on.get() else None)
            elif k == "mouse":
                on, vx, vy = self.pos_rows["mouse"]
                st.update(button=self.v_mbtn.get(),
                          action="down" if self.v_maction.get().startswith("Press") else "up",
                          x=int(vx.get()) if on.get() else None,
                          y=int(vy.get()) if on.get() else None)
            elif k in ("move", "drag"):
                vs = self.path_vars[k]
                cur = (int(vs["startx"].get()), int(vs["starty"].get()), int(vs["endx"].get()),
                       int(vs["endy"].get()), float(vs["dur"].get()))
                path = self.step.get("path") if self.step.get("type") == k else None
                if not path or cur[:4] != tuple(vs["orig"][:4]):
                    n = 12
                    path = [[round(cur[4] * i / n, 3), round(cur[0] + (cur[2] - cur[0]) * i / n),
                             round(cur[1] + (cur[3] - cur[1]) * i / n)] for i in range(n + 1)]
                elif cur[4] != vs["orig"][4] and path[-1][0]:
                    f = cur[4] / path[-1][0]
                    path = [[round(p[0] * f, 3), p[1], p[2]] for p in path]
                st["path"] = path
                if k == "drag":
                    st["button"] = self.v_dbtn.get()
            elif k == "keyhold":
                keys = self.v_hkey.get().strip()
                if len(parse_combo(keys)) != 1:
                    raise ValueError("hold one key at a time (e.g. Shift)")
                st.update(keys=keys, action="down" if self.v_haction.get().startswith("Hold")
                          else "up")
            st.update(retries=max(0, min(10, int(self.v_retries.get()))),
                      retry_wait=max(0.0, min(3600.0, float(self.v_rwait.get()))),
                      on_fail="continue" if self.v_onfail.get().startswith("continue") else "stop",
                      careful=bool(self.v_careful.get()))
            if self.v_label.get().strip():
                st["label"] = self.v_label.get().strip()[:120]
            if "rec_t" in self.step:
                st["rec_t"] = self.step["rec_t"]
        except ValueError as e:
            messagebox.showerror(APP_NAME, f"Please check this step: {e}", parent=self)
            return
        except Exception:
            messagebox.showerror(APP_NAME, "Please check the numbers.", parent=self)
            return
        clean, why = sanitize_step(st)
        if clean is None:
            messagebox.showerror(APP_NAME, f"Please check this step: {why}", parent=self)
            return
        if "rec_t" in st:
            clean["rec_t"] = st["rec_t"]
        self.editor.step_saved(clean, self.index)
        self.destroy()


class DryRunDialog(Dialog):
    """What a job would do right now, step by step, without clicking or typing."""

    def __init__(self, app, job, parent=None):
        super().__init__(app, f"Dry run - {job.get('name', '')}", parent)
        f = self.body
        ttk.Label(f, style="Muted.TLabel", wraplength=640, justify="left", text=(
            "Nothing was clicked or typed. Each step was checked against the screen as it is "
            "now: are the targets there, are the conditions true? Loops are shown once; waits "
            "are not waited. Typed or pasted text is only counted, never shown.")).pack(
            anchor="w")
        self.dr_filter = FilterBox(f, self.fill)
        self.dr_filter.pack(anchor="e", pady=(8, 0))
        tf = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(4, 0))
        tr = ttk.Treeview(tf, columns=("n", "what", "result"), show="headings", height=12)
        enable_column_fit(tr)
        for c, h, w, st in (("n", "#", 70, False), ("what", "Step", 150, False),
                            ("result", "What would happen", 470, False)):
            tr.heading(c, text=h, anchor="w")
            tr.column(c, width=w, minwidth=40, stretch=st, anchor="w")
        tr.pack(fill="both", expand=True)
        self.tree = tr
        self.lines = []
        self.tools = LogGrid(app, tr, frame=tf, owner=self, fit_col="result",
                             job_of=lambda iid: job.get("name"), filterbox=self.dr_filter,
                             name="dry-run", natural="old")
        self.status = ttk.Label(f, style="Muted.TLabel", text="Checking the screen…")
        self.status.pack(anchor="w", pady=(6, 0))
        ttk.Button(self.footer, text="Close", command=self.destroy).pack(side="right")
        self.finish()
        restore = app.hide_all_windows(keep=None)

        def work():
            try:
                lines = app.dry_run_steps(job)
            except Exception as e:
                lines = [("!", "Problem", f"couldn't finish the dry run ({e})")]
            app.cmdq.put(lambda: done(lines))

        def done(lines):
            restore()
            if not self.winfo_exists():
                return
            self.lines = lines
            self.fill()
            bad = sum(1 for _, _, r in lines if "NOT" in r or r.startswith(("couldn't", "the ")))
            self.status.configure(text=f"{len(lines)} step(s) checked." +
                                  (f" {bad} may need attention." if bad else ""))
        self.after(500, lambda: threading.Thread(target=work, daemon=True).start())


    def fill(self):
        self.tree.delete(*self.tree.get_children())
        for n, w, r in self.lines:
            if self.dr_filter.matches(n, w, r):
                self.tree.insert("", "end", values=(n, w, r))
        self.tools.done_filling()


class StepDebugger:
    """Asks the step-through window before each step (runs on the input thread)."""

    def __init__(self, app, win):
        self.app, self.win = app, win
        self.ev = threading.Event()
        self.cmd = None
        self.only_careful = False

    def _ask(self, num, what, why, xy=None, careful=False):
        if self.only_careful and not careful:
            self.app.cmdq.put(lambda: self.win.show_running(num, what))
            return
        self.ev.clear()
        self.cmd = None
        self.app.cmdq.put(lambda: self.win.show_next(num, what, why, xy, careful))
        while not self.ev.wait(0.2):
            if self.app.stop.is_set() or self.app.run_cancel.is_set():
                raise StopRun("stopped by you")
        if self.cmd == "stop":
            raise StopRun("stopped while stepping through")
        if self.cmd == "run":
            self.only_careful = True

    def answer(self, cmd):
        self.cmd = cmd
        self.ev.set()

    def before_main(self, job, x, y, how):
        tgt = adapter_for(job)
        self._ask("0", f"Click: {job.get('button', 'left')} at ({x}, {y})",
                  f"Found {how}. {tgt.describe(job)}", (x, y))

    def before(self, run, i, st):
        w, d = describe_step(st, private=True, groups=run.groups)
        t = st.get("type")
        why, xy = "", None
        try:
            if t == "click":
                a = adapter_for(st)
                ok, x, y, msg, how = a.locate(st, activate=False, check_cover=False)
                why = (f"Will click at ({x}, {y}), found {how}. " if ok else
                       f"The target is NOT there right now ({msg}); the step will fail unless "
                       f"it appears. ") + a.describe(st)
                xy = (x, y) if ok else None
            elif t in ("if", "repeat") and st.get("cond"):
                if st["cond"].get("kind") == "var":
                    res, note = run.eval_cond(dict(st["cond"], wait=0))
                else:
                    res, note = check_condition(st["cond"])
                why = f"The condition is {'TRUE' if res else 'false'} right now ({note})."
            elif t == "waitpic":
                found, x, y, score, sc = picture_on_screen(st["png"], area=st.get("area"))
                why = (f"The picture is showing now ({score:.0%})." if found else
                       f"The picture isn't showing now; it waits up to "
                       f"{fmt_dur(int(st.get('timeout', 60)))}.")
            elif t in TEXT_STEPS:
                fg = win_text(user32.GetForegroundWindow()) if IS_WIN else ""
                why = ("The text goes to whatever has keyboard focus now"
                       + (f": “{short_title(fg, 40)}”." if fg else ".") +
                       " Check that it's the right field.")
            elif t == "key":
                why = "Keys go to whatever has keyboard focus now."
        except Exception as e:
            why = f"(couldn't check: {e})"
        self._ask(run.num(i), f"{w}: {d}", why, xy, bool(st.get("careful")))

    def after(self, run, i, st, ok, msg):
        w, _ = describe_step(st, private=True, groups=run.groups)
        self.app.cmdq.put(lambda: self.win.show_result(run.num(i), w, ok, msg))


class DebugWindow(tk.Toplevel):
    """Step through a job: see the next action, why its target was chosen, then run it."""

    def __init__(self, app, job, on_close):
        super().__init__(app.root)
        self.app, self.job, self.on_close = app, job, on_close
        self.dbg = None
        self.title(f"Step through - {job.get('name', '')}")
        self.attributes("-topmost", True)
        self.resizable(True, True)
        P = app.pal
        self.configure(bg=P["bg"])
        f = ttk.Frame(self, padding=12)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"Stepping through “{job.get('name', '')}”",
                  style="Section.TLabel").pack(anchor="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "Clickue stops before each step. Drag this window aside if it covers what Clickue "
            "needs to click (it never clicks through its own windows).")).pack(anchor="w")
        self.next_lbl = ttk.Label(f, text="Getting ready…", wraplength=460, justify="left",
                                  style="Section.TLabel")
        self.next_lbl.pack(anchor="w", pady=(10, 0))
        self.why_lbl = ttk.Label(f, text="", wraplength=460, justify="left", style="Muted.TLabel")
        self.why_lbl.pack(anchor="w", pady=(4, 0))
        self.log = tk.Text(f, height=8, width=60, wrap="word", bd=0, padx=8, pady=6,
                           bg=P["field"], fg=P["fg"], state="disabled")
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        br = ttk.Frame(f)
        br.pack(fill="x", pady=(10, 0))
        self.next_btn = ttk.Button(br, text="▶  Run this step", style="Accent.TButton",
                                   command=lambda: self.answer("next"))
        self.next_btn.pack(side="left")
        self.run_btn = ttk.Button(br, text="Run to the end", command=lambda: self.answer("run"))
        self.run_btn.pack(side="left", padx=6)
        ttk.Button(br, text="■  Stop", command=lambda: self.answer("stop")).pack(side="right")
        ttk.Label(f, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "“Run to the end” still stops before steps marked ⚠ careful. The emergency stop "
            f"hotkey ({app.settings.get('hk_stop') or 'off'}) works too.")).pack(anchor="w",
                                                                                 pady=(6, 0))
        self.protocol("WM_DELETE_WINDOW", lambda: self.answer("stop", close=True))
        app.theme_window(self)
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = 520, 440
        self.geometry(f"{w}x{h}+{max(0, sw - w - 24)}+{max(0, sh - h - 80)}")
        self.buttons(False)
        self.done = False

    def buttons(self, on):
        for b in (self.next_btn, self.run_btn):
            b.state(["!disabled"] if on else ["disabled"])

    def write(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def answer(self, cmd, close=False):
        if self.dbg and not self.done:
            self.dbg.answer(cmd)
            if cmd == "stop":
                self.app.stop_current_run("stopped while stepping through")
        self.buttons(False)
        if close or (cmd == "stop" and self.done):
            self.close()

    def show_next(self, num, what, why, xy, careful):
        if not self.winfo_exists():
            return
        self.next_lbl.configure(text=f"Next: step {num} · {what}" + ("   ⚠ careful" if careful else ""))
        self.why_lbl.configure(text=why)
        self.buttons(True)
        self.lift()
        if xy:
            self.app.flash_marker(xy[0], xy[1], f"step {num}", seconds=1.2)

    def show_running(self, num, what):
        if self.winfo_exists():
            self.next_lbl.configure(text=f"Running: step {num} · {what}")
            self.why_lbl.configure(text="")

    def show_result(self, num, what, ok, msg):
        if self.winfo_exists():
            self.write(f"{'✔' if ok else '✖'} step {num} · {what}" + (f": {msg}" if msg else ""))

    def finished(self, ok, msg):
        self.done = True
        if not self.winfo_exists():
            return
        self.buttons(False)
        self.next_lbl.configure(text="Finished" if ok else "Stopped")
        self.why_lbl.configure(text=msg or "")
        self.write(("✔ " if ok else "✖ ") + (msg or ("done" if ok else "stopped")))
        self.run_btn.configure(text="Close", command=self.close)
        self.run_btn.state(["!disabled"])

    def close(self):
        try:
            self.destroy()
        finally:
            if self.on_close:
                cb, self.on_close = self.on_close, None
                cb()


class RecordDialog(Dialog):
    """Options before recording a macro."""

    def __init__(self, app):
        super().__init__(app, "Record a macro")
        s = app.settings
        f = self.body
        ttk.Label(f, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "Clickue hides, then records your mouse and keyboard until you press Stop on the "
            "red recording bar (or the hotkey). Afterwards you get the steps to check, edit "
            "and save as a job. Clickue's own windows and its own clicks are never "
            "recorded.")).pack(anchor="w")
        r = ttk.Frame(f)
        r.pack(anchor="w", pady=(10, 0))
        ttk.Label(r, text="Name").pack(side="left")
        n = sum(1 for j in app.jobs if j.get("name", "").startswith("Recorded macro")) + 1
        self.v_name = tk.StringVar(value=f"Recorded macro {n}")
        ttk.Entry(r, textvariable=self.v_name, width=34).pack(side="left", padx=6)
        self.v_moves = tk.BooleanVar(value=bool(s.get("rec_moves", True)))
        ttk.Checkbutton(f, variable=self.v_moves, text=(
            "Record mouse movement (simplified; useful for menus that open on hover)")).pack(
            anchor="w", pady=(10, 0))
        self.v_pics = tk.BooleanVar(value=bool(s.get("rec_pictures", True)) and HAVE_CV)
        cb = ttk.Checkbutton(f, variable=self.v_pics, text=(
            "Save a small picture of each clicked spot, so clicks find their target even if "
            "it moves (recommended)"))
        cb.pack(anchor="w", pady=(2, 0))
        if not HAVE_CV:
            cb.state(["disabled"])
        self.v_timing = tk.BooleanVar(value=bool(s.get("rec_timing", True)))
        ttk.Checkbutton(f, variable=self.v_timing, text=(
            "Keep the pauses between actions (as waits you can edit)")).pack(anchor="w", pady=(2, 0))
        self.v_pause = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, variable=self.v_pause, text=(
            "Pause my other jobs while I record")).pack(anchor="w", pady=(2, 0))
        self.v_human = tk.BooleanVar(value=bool(s.get("rec_human", False)))
        ttk.Checkbutton(f, variable=self.v_human, text=(
            "When it plays, move the mouse to each click like a person (instead of jumping "
            "there)")).pack(anchor="w", pady=(2, 0))
        ttk.Label(f, style="Warn.TLabel", wraplength=560, justify="left", text=(
            "Everything you type is recorded, including passwords. Don't type secrets while "
            "recording (add them afterwards as a Secret paste step). The recording stays on "
            "this computer.")).pack(anchor="w", pady=(10, 0))
        ttk.Label(f, style="Muted.TLabel", wraplength=560, justify="left", text=(
            f"Hotkeys: {s.get('hk_record') or '(off)'} start/stop · {s.get('hk_rec_pause') or '(off)'} "
            f"pause/resume · {s.get('hk_stop') or '(off)'} emergency stop (throws the recording "
            f"away).")).pack(anchor="w", pady=(6, 0))
        ttk.Button(self.footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(self.footer, text="⏺  Start recording", style="Accent.TButton",
                   command=self.start).pack(side="right", padx=6)
        self.finish()

    def start(self):
        s = self.app.settings
        s.update(rec_moves=bool(self.v_moves.get()), rec_pictures=bool(self.v_pics.get()),
                 rec_timing=bool(self.v_timing.get()), rec_human=bool(self.v_human.get()))
        self.app.save()
        opts = dict(moves=bool(self.v_moves.get()), pictures=bool(self.v_pics.get()),
                    timing=bool(self.v_timing.get()))
        name, pause = self.v_name.get().strip() or "Recorded macro", bool(self.v_pause.get())
        self.destroy()
        self.app.start_recording(opts, name, pause_jobs=pause, countdown=3)


class RecordingIndicator(tk.Toplevel):
    """The small red bar shown while recording (it's never recorded itself)."""

    def __init__(self, app, countdown=0):
        super().__init__(app.root)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        bg = "#1f2937"
        self.configure(bg=bg, highlightthickness=1, highlightbackground="#ef4444")
        row = tk.Frame(self, bg=bg)
        row.pack(padx=10, pady=8)
        self.dot = tk.Label(row, text="●", fg="#ef4444", bg=bg, font=(app.font_family, 14, "bold"))
        self.dot.pack(side="left")
        self.lbl = tk.Label(row, text="REC", fg="#ffffff", bg=bg, font=(app.font_family, 10, "bold"),
                            width=38, anchor="w")
        self.lbl.pack(side="left", padx=(4, 8))
        self.pause_btn = tk.Button(row, text="⏸ Pause", command=app.toggle_recording_pause,
                                   relief="flat", bg="#374151", fg="#ffffff", bd=0, padx=8)
        self.pause_btn.pack(side="left", padx=2)
        tk.Button(row, text="■ Stop", command=app.stop_recording, relief="flat", bg="#ef4444",
                  fg="#ffffff", bd=0, padx=8).pack(side="left", padx=2)
        tk.Button(row, text="✕", command=lambda: app.stop_recording(save=False), relief="flat",
                  bg="#374151", fg="#ffffff", bd=0, padx=8).pack(side="left", padx=2)
        self.drag = None
        for w in (self, row, self.lbl, self.dot):
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<B1-Motion>", self._motion)
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"+{max(0, sw - self.winfo_reqwidth() - 24)}+{max(0, sh - self.winfo_reqheight() - 70)}")
        self.countdown = countdown
        self.blink = False
        self.after(100, self.tick)

    def _press(self, e):
        self.drag = (e.x_root - self.winfo_rootx(), e.y_root - self.winfo_rooty())

    def _motion(self, e):
        if self.drag:
            self.geometry(f"+{e.x_root - self.drag[0]}+{e.y_root - self.drag[1]}")

    def rect(self):
        try:
            return [self.winfo_rootx() - 4, self.winfo_rooty() - 4, self.winfo_width() + 8,
                    self.winfo_height() + 8]
        except Exception:
            return [0, 0, 0, 0]

    def tick(self):
        if not self.winfo_exists():
            return
        rec = self.app.recorder
        if rec is not None:
            r = self.rect()
            if r not in rec.exclude:
                rec.exclude.append(r)
            st = rec.state
            secs = int(rec.now()) if st in ("recording", "paused") else 0
            if st == "paused":
                txt = f"PAUSED {secs // 60}:{secs % 60:02d}"
                self.pause_btn.configure(text="▶ Resume")
                self.dot.configure(fg="#9ca3af")
            else:
                txt = (f"REC {secs // 60}:{secs % 60:02d} · {rec.counts['clicks']} clicks · "
                       f"{rec.counts['keys']} keys")
                self.pause_btn.configure(text="⏸ Pause")
                self.blink = not self.blink
                self.dot.configure(fg="#ef4444" if self.blink else "#7f1d1d")
            if st == "full":
                txt = "Recording is full - press Stop"
            self.lbl.configure(text=txt)
        self.after(500, self.tick)


class GroupsDialog(Dialog):
    """Reusable groups of steps (☰ Menu → Step groups)."""

    def __init__(self, app):
        super().__init__(app, "Step groups")
        f = self.body
        ttk.Label(f, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "A step group is a saved set of steps you can use in several jobs (“Use a step "
            "group”). Change it here once and every job that uses it gets the change.")).pack(
            anchor="w")
        tf = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(8, 0))
        self.tree = ttk.Treeview(tf, columns=("name", "steps", "used"), show="headings",
                                 height=8, selectmode="browse")
        enable_column_fit(self.tree)
        for c, h, w in (("name", "Name", 260), ("steps", "Steps", 70), ("used", "Used by", 200)):
            self.tree.heading(c, text=h, anchor="w")
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        br = ttk.Frame(f)
        br.pack(fill="x", pady=(8, 0))
        for text, cmd in (("New", self.new), ("Edit", self.edit), ("Duplicate", self.dup),
                          ("Delete", self.delete)):
            ttk.Button(br, text=text, style="Small.TButton", command=cmd).pack(side="left",
                                                                              padx=(0, 4))
        ttk.Button(self.footer, text="Close", command=self.destroy).pack(side="right")
        self.fill()
        self.finish()

    def users(self, gid):
        return [j["name"] for j in self.app.jobs
                if any(s.get("group_id") == gid for s in j.get("steps") or [])]

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        for g in self.app.groups:
            u = self.users(g["id"])
            self.tree.insert("", "end", iid=g["id"], values=(
                g["name"], len(g.get("steps") or []),
                ", ".join(u[:3]) + (f" +{len(u) - 3}" if len(u) > 3 else "") if u else "not used"))

    def selected(self):
        sel = self.tree.selection()
        return next((g for g in self.app.groups if sel and g["id"] == sel[0]), None)

    def new(self):
        GroupEditDialog(self.app, {"id": uuid.uuid4().hex, "name": f"Group {len(self.app.groups) + 1}",
                                   "steps": []}, True, self)

    def edit(self):
        g = self.selected()
        if g:
            GroupEditDialog(self.app, g, False, self)

    def dup(self):
        g = self.selected()
        if g:
            with self.app.lock:
                self.app.groups.append(dict(copy.deepcopy(g), id=uuid.uuid4().hex,
                                            name=g["name"] + " (copy)"))
            self.app.save()
            self.fill()

    def delete(self):
        g = self.selected()
        if not g:
            return
        u = self.users(g["id"])
        msg = f"Delete the step group “{g['name']}”?"
        if u:
            msg += (f"\n\n{len(u)} job(s) use it ({', '.join(u[:5])}). Their “Use group” step "
                    f"will fail until you change it.")
        if messagebox.askyesno(APP_NAME, msg, parent=self):
            with self.app.lock:
                self.app.groups = [x for x in self.app.groups if x["id"] != g["id"]]
            self.app.save()
            self.fill()


class GroupEditDialog(Dialog):
    def __init__(self, app, group, is_new, owner):
        super().__init__(app, "New step group" if is_new else f"Edit group - {group['name']}",
                         owner)
        self.group, self.is_new, self.owner = group, is_new, owner
        self.steps = copy.deepcopy(group.get("steps") or [])
        r = ttk.Frame(self.body)
        r.pack(fill="x")
        ttk.Label(r, text="Name", width=8).pack(side="left")
        self.v_name = tk.StringVar(value=group["name"])
        ttk.Entry(r, textvariable=self.v_name, width=40).pack(side="left")
        self.stepsed = StepsEditor(app, self, self.body, self.steps, "Steps in this group",
                                   "These run wherever a job uses this group, as if they were "
                                   "written there.", allow_groups=False)
        ttk.Button(self.footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(self.footer, text="Save", style="Accent.TButton", command=self.save).pack(
            side="right", padx=6)
        self.finish()

    def save(self):
        name = self.v_name.get().strip()[:MAX_NAME]
        if not name:
            messagebox.showerror(APP_NAME, "Give the group a name.", parent=self)
            return
        if not self.steps:
            messagebox.showerror(APP_NAME, "Add at least one step.", parent=self)
            return
        errs = parse_blocks(self.steps)[1]
        if errs:
            messagebox.showerror(APP_NAME, f"Please fix the steps: {errs[0]}", parent=self)
            return
        app = self.app
        with app.lock:
            self.group.update(name=name, steps=copy.deepcopy(self.steps))
            if self.is_new:
                app.groups.append(self.group)
        app.save()
        self.destroy()
        try:
            self.owner.fill()
        except Exception:
            pass


class RunHistoryDialog(Dialog):
    """Every run, with its steps and results (no typed text), linked to its screen video."""

    def __init__(self, app, job_name=None):
        super().__init__(app, "Run history")
        f = self.body
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Search").pack(side="left")
        self.v_q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.v_q, width=28)
        e.pack(side="left", padx=6)
        e.bind("<KeyRelease>", lambda ev: self.fill())
        self.v_fail = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Only failed runs", variable=self.v_fail,
                        command=self.fill).pack(side="left", padx=8)
        if job_name:
            self.v_q.set(job_name)
        tf = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(8, 0))
        self.runs = ttk.Treeview(tf, columns=("time", "job", "len", "result", "video"),
                                 show="headings", height=8, selectmode="browse")
        enable_column_fit(self.runs)
        for c, h, w, stv in (("time", "Started", 140, False), ("job", "Job", 160, False),
                             ("len", "Took", 60, False), ("result", "Result", 260, True),
                             ("video", "Video", 60, False)):
            self.runs.heading(c, text=h, anchor="w")
            self.runs.column(c, width=w, minwidth=40, stretch=stv, anchor="w")
        self.runs.pack(fill="both", expand=True)
        self.run_tools = LogGrid(app, self.runs, frame=tf, owner=self, fit_col="result",
                                 job_of=lambda iid: self.runs.set(iid, "job"),
                                 name="run-history", natural="new", refresh=self.reload,
                                 delete=self.delete_runs)
        self.run_tools.toolbar(top)
        self.runs.bind("<<TreeviewSelect>>", lambda e: self.show_run())
        ttk.Label(f, text="Steps of the selected run", style="Section.TLabel").pack(
            anchor="w", pady=(10, 2))
        tf2 = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf2.pack(fill="both", expand=True)
        self.acts = ttk.Treeview(tf2, columns=("at", "pos", "step", "action", "result"),
                                 show="headings", height=8, selectmode="browse")
        enable_column_fit(self.acts)
        for c, h, w, stv in (("at", "After", 60, False), ("pos", "Video", 60, False),
                             ("step", "#", 60, False), ("action", "Action", 300, True),
                             ("result", "Result", 200, True)):
            self.acts.heading(c, text=h, anchor="w")
            self.acts.column(c, width=w, minwidth=40, stretch=stv, anchor="w")
        self.acts.pack(fill="both", expand=True)
        self.act_tools = LogGrid(app, self.acts, frame=tf2, owner=self, fit_col="result",
                                 natural="old", refresh=self.show_run,
                                 job_of=lambda iid: (self.runs.set(self.runs.selection()[0], "job")
                                                     if self.runs.selection() else None),
                                 extra=lambda iid: [("▶  Play video from this step", self.play)],
                                 name="run-steps")
        self.acts.bind("<Double-1>", lambda e: self.play())
        ttk.Label(f, style="Muted.TLabel", wraplength=640, justify="left", text=(
            "Typed and pasted text is never stored here (only how many characters). Videos are "
            "only recorded for jobs that ask for it, and stay on this computer.")).pack(
            anchor="w", pady=(6, 0))
        ttk.Button(self.footer, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(self.footer, text="▶  Play video from this step", style="Accent.TButton",
                   command=self.play).pack(side="left")
        ttk.Button(self.footer, text="Open video folder", command=self.open_folder).pack(
            side="left", padx=6)
        self.rows = read_runlog()
        self.fill()
        self.finish()

    def grouped(self):
        runs = {}
        for r in self.rows:
            runs.setdefault(r.get("run", ""), []).append(r)
        return runs

    def fill(self):
        q = self.v_q.get().strip().lower()
        self.runs.delete(*self.runs.get_children())
        self.by_id = self.grouped()
        for rid, rows in reversed(list(self.by_id.items())):
            if not rid:
                continue
            end = next((r for r in reversed(rows) if r.get("action") == "Run finished"), None)
            result = end.get("result", "") if end else "(still running or interrupted)"
            if self.v_fail.get() and result == "ok":
                continue
            if q and not any(q in " ".join(str(v) for v in r.values()).lower() for r in rows):
                continue
            video = next((r.get("video") for r in rows if r.get("video")), "")
            self.runs.insert("", "end", iid=rid, values=(
                rows[0].get("time", ""), rows[0].get("job", ""),
                fmt_secs(end.get("elapsed", 0)) if end else "", result, "yes" if video else ""))
        self.run_tools.done_filling()

    def show_run(self):
        sel = self.runs.selection()
        self.acts.delete(*self.acts.get_children())
        if not sel:
            return
        for k, r in enumerate(self.by_id.get(sel[0], [])):
            pos = r.get("video_pos", "")
            try:
                pos = f"{int(float(pos)) // 60}:{int(float(pos)) % 60:02d}" if pos != "" else ""
            except ValueError:
                pos = ""
            self.acts.insert("", "end", iid=str(k), values=(
                fmt_secs(r.get("elapsed", 0)), pos, r.get("step", ""), r.get("action", ""),
                r.get("result", "")))
        self.act_tools.done_filling()

    def reload(self):
        self.rows = read_runlog()
        self.fill()
        self.show_run()

    def delete_runs(self):
        """Delete run history for good: the selected runs, or all of it."""
        sel = [i for i in self.runs.selection()]
        q = (f"Delete the {len(sel)} selected run{'s' if len(sel) != 1 else ''} from the run "
             f"history for good? (Their videos are kept.)" if sel else
             "Delete the whole run history for good? (Videos are kept; ☰ Menu → Run history "
             "& videos → Open video folder to remove them.)")
        if not messagebox.askyesno(APP_NAME, q, parent=self):
            return
        try:
            n = rewrite_runlog((lambda r: r.get("run") not in sel) if sel else (lambda r: False))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't delete:\n{e}", parent=self)
            return
        self.app.log(f"Deleted {n} run history line{'s' if n != 1 else ''}")
        self.reload()

    def video_path(self, rows):
        name = next((r.get("video") for r in rows if r.get("video")), "")
        if not name or not VIDEO_FILE_RE.match(name):
            return ""
        return os.path.join(video_folder(self.app.settings), name)

    def play(self):
        sel = self.runs.selection()
        if not sel:
            return
        rows = self.by_id.get(sel[0], [])
        path = self.video_path(rows)
        if not path:
            messagebox.showinfo(APP_NAME, "This run has no screen video.", parent=self)
            return
        if not os.path.exists(path):
            messagebox.showinfo(APP_NAME, f"The video file isn't there any more (old videos are "
                                          f"deleted after a while):\n{path}", parent=self)
            return
        a = self.acts.selection()
        pos = 0.0
        if a:
            try:
                pos = float(rows[int(a[0])].get("video_pos") or 0)
            except Exception:
                pos = 0.0
        VideoPlayer(self.app, path, pos, self)

    def open_folder(self):
        d = video_folder(self.app.settings)
        try:
            os.makedirs(d, exist_ok=True)
            if IS_WIN:
                os.startfile(d)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e), parent=self)


class VideoPlayer(tk.Toplevel):
    """Plays a run's video from a given second (local file, opened with OpenCV)."""

    def __init__(self, app, path, start=0.0, parent=None):
        super().__init__(parent or app.root)
        self.app, self.path = app, path
        self.title(f"Video - {os.path.basename(path)}")
        self.cap = cv2.VideoCapture(path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 5
        self.total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        self.playing = False
        self.img = None
        self.lbl = ttk.Label(self, anchor="center")
        self.lbl.pack(fill="both", expand=True)
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        self.play_btn = ttk.Button(bar, text="▶ Play", command=self.toggle)
        self.play_btn.pack(side="left")
        ttk.Button(bar, text="−5 s", command=lambda: self.seek(self.pos() - 5)).pack(side="left", padx=4)
        ttk.Button(bar, text="+5 s", command=lambda: self.seek(self.pos() + 5)).pack(side="left")
        self.v_pos = tk.DoubleVar(value=start)
        self.scale = ttk.Scale(bar, from_=0, to=max(1.0, self.total / self.fps), variable=self.v_pos,
                               command=lambda v: self.seek(float(v), from_scale=True))
        self.scale.pack(side="left", fill="x", expand=True, padx=8)
        self.time_lbl = ttk.Label(bar, width=14)
        self.time_lbl.pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close)
        app.theme_window(self)
        self.geometry("980x620")
        if not self.cap.isOpened():
            self.lbl.configure(text="This video can't be opened.")
            return
        self.seek(start)

    def pos(self):
        return (self.cap.get(cv2.CAP_PROP_POS_FRAMES) or 0) / self.fps

    def seek(self, secs, from_scale=False):
        secs = max(0.0, min(secs, self.total / self.fps if self.total else secs))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(secs * self.fps))
        self.show_frame()
        if not from_scale:
            self.v_pos.set(secs)

    def show_frame(self):
        ok, frame = self.cap.read()
        if not ok:
            self.playing = False
            self.play_btn.configure(text="▶ Play")
            return False
        img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        W = max(320, self.lbl.winfo_width() or 960)
        H = max(200, self.lbl.winfo_height() or 540)
        f = min(W / img.width, H / img.height, 1.0)
        if f < 1:
            img = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))))
        self.img = ImageTk.PhotoImage(img)
        self.lbl.configure(image=self.img)
        p = self.pos()
        self.time_lbl.configure(text=f"{int(p) // 60}:{int(p) % 60:02d} / "
                                     f"{int(self.total / self.fps) // 60}:{int(self.total / self.fps) % 60:02d}")
        return True

    def toggle(self):
        self.playing = not self.playing
        self.play_btn.configure(text="⏸ Pause" if self.playing else "▶ Play")
        if self.playing:
            self.loop()

    def loop(self):
        if not self.playing or not self.winfo_exists():
            return
        if self.show_frame():
            self.v_pos.set(self.pos())
            self.after(int(1000 / self.fps), self.loop)

    def close(self):
        self.playing = False
        try:
            self.cap.release()
        except Exception:
            pass
        self.destroy()


class BackupsDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Backups")
        f = self.body
        ttk.Label(f, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "Clickue saves a backup of all your jobs and settings once a day (and before a "
            "restore). Restoring never deletes backups.")).pack(anchor="w")
        tf = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(8, 0))
        self.tree = ttk.Treeview(tf, columns=("when", "kind", "jobs"), show="headings", height=8,
                                 selectmode="browse")
        enable_column_fit(self.tree)
        for c, h, w in (("when", "Saved", 220), ("kind", "Type", 140), ("jobs", "Jobs", 80)):
            self.tree.heading(c, text=h, anchor="w")
            self.tree.column(c, width=w, anchor="w", stretch=(c == "when"))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.restore())
        b = self.footer
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Restore…", style="Accent.TButton", command=self.restore).pack(
            side="right", padx=6)
        ttk.Button(b, text="Back up now", command=self.backup).pack(side="left")
        ttk.Button(b, text="Open folder", command=self.open_folder).pack(side="left", padx=6)
        self.fill()
        self.finish()

    def fill(self):
        self.tree.delete(*self.tree.get_children())
        self.items = list_backups()
        names = {"auto": "Daily", "manual": "Manual", "before-restore": "Before a restore",
                 "before-uninstall": "Before uninstall",
                 "before-fresh-start": "Before a fresh start"}
        for i, b in enumerate(self.items):
            when = b["created"].replace("T", "  ") if b["created"] else b["name"]
            self.tree.insert("", "end", iid=str(i), values=(when, names.get(b["tag"], b["tag"]),
                                                            b["jobs"]))

    def backup(self):
        self.app.backup_now()
        self.fill()

    def open_folder(self):
        try:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            if IS_WIN:
                os.startfile(BACKUP_DIR)
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e), parent=self)

    def restore(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Select a backup first.", parent=self)
            return
        b = self.items[int(sel[0])]
        ans = messagebox.askyesnocancel(
            APP_NAME, f"Restore {b['jobs']} job(s) from this backup?\n\n"
                      f"Yes  =  replace your current jobs\nNo   =  add them to your current jobs\n"
                      f"Cancel  =  do nothing\n\n(Your current jobs are backed up first.)",
            parent=self)
        if ans is None:
            return
        try:
            n = self.app.restore_backup(b["path"], replace=bool(ans))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't restore:\n{e}", parent=self)
            return
        messagebox.showinfo(APP_NAME, f"Restored {n} job(s).", parent=self)
        self.fill()


class StatsDialog(Dialog):
    def __init__(self, app, job):
        super().__init__(app, f"Stats - {job['name']}")
        self.job = job
        f = self.body
        rows = read_history()
        st = job_stats(rows, job["name"])
        grid = ttk.Frame(f)
        grid.pack(fill="x")
        cards = (("CLICKS TOTAL", st["total"]), ("TODAY", st["today"]),
                 ("LAST 7 DAYS", st["week"]), ("PROBLEMS", st["problems"]))
        for i, (t, v) in enumerate(cards):
            grid.columnconfigure(i, weight=1, uniform="s")
            c = ttk.Frame(grid, style="Card.TFrame", padding=(12, 8))
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            ttk.Label(c, text=t, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(c, text=str(v), style="CardBad.TLabel" if t == "PROBLEMS" and v
                      else "CardValue.TLabel").pack(anchor="w")
        k = st["kinds"]
        ttk.Label(f, style="Muted.TLabel", justify="left", text=(
            f"Last click: {st['last']}\nLast problem: {st['last_problem']}\n"
            f"By type: {k['scheduled']} scheduled, {k['watcher']} watcher, {k['test']} test, "
            f"{k['manual']} manual")).pack(anchor="w", pady=(10, 6))
        hr = ttk.Frame(f)
        hr.pack(fill="x")
        ttk.Label(hr, text="Recent activity", style="Section.TLabel").pack(side="left")
        self.st_filter = FilterBox(hr, self.fill)
        self.st_filter.pack(side="right")
        tf = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(4, 0))
        tr = ttk.Treeview(tf, columns=("time", "kind", "result", "detail"), show="headings",
                          height=8)
        enable_column_fit(tr)
        for c, h, w in (("time", "Time", 150), ("kind", "Type", 90), ("result", "Result", 80),
                        ("detail", "Details", 260)):
            tr.heading(c, text=h, anchor="w")
            tr.column(c, width=w, anchor="w", stretch=False)
        sb = ttk.Scrollbar(tf, orient="vertical", command=tr.yview)
        tr.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tr.pack(fill="both", expand=True)
        self.tree = tr
        self.tools = LogGrid(app, tr, frame=tf, owner=self, fit_col="detail",
                             job_of=lambda iid: job["name"], filterbox=self.st_filter,
                             name="click-history", natural="new", refresh=self.reload,
                             delete=self.delete_rows)
        self.tools.toolbar(hr)
        tr.bind("<Double-1>", lambda e: self.show(e))
        self.mine = [r for r in rows if r.get("job") == job["name"]][-200:]
        self.fill()
        b = self.footer
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Export this job's history…",
                   command=lambda: app.export_history(job["name"], self)).pack(side="left")
        self.finish()


    def fill(self):
        tr = self.tree
        tr.delete(*tr.get_children())
        self.row_of = {}
        for r in reversed(self.mine):
            det = r.get("detail") or (f"({r.get('x')}, {r.get('y')}) {r.get('how', '')}"
                                      if r.get("x") else "")
            vals = (r["time"], r.get("kind", ""), r.get("result", ""), det)
            if self.st_filter.matches(*vals):
                self.row_of[tr.insert("", "end", values=vals)] = r
        self.tools.done_filling()

    def reload(self):
        self.mine = [r for r in read_history() if r.get("job") == self.job["name"]][-200:]
        self.fill()

    def delete_rows(self):
        """Delete click history for good: the selected rows, or all of this job's rows."""
        sel = [self.row_of[i] for i in self.tree.selection() if i in self.row_of]
        name = self.job["name"]
        if sel:
            q = f"Delete the {len(sel)} selected history row{'s' if len(sel) != 1 else ''} for good?"
        else:
            q = f"Delete the whole click history of \u201c{name}\u201d for good?"
        if not messagebox.askyesno(APP_NAME, q, parent=self):
            return
        keys = {(r.get("time"), r.get("kind"), r.get("result"), r.get("x"), r.get("y"))
                for r in sel}
        try:
            n = rewrite_history(
                (lambda r: not (r.get("job") == name and (r.get("time"), r.get("kind"),
                                                          r.get("result"), r.get("x"),
                                                          r.get("y")) in keys))
                if sel else (lambda r: r.get("job") != name))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't delete:\n{e}", parent=self)
            return
        self.app.log(f"[{name}] deleted {n} click history row{'s' if n != 1 else ''}")
        self.reload()

    def show(self, e):
        iid = self.tree.identify_row(e.y)
        if iid:
            text = " ".join(str(v) for v in self.tree.item(iid, "values"))
            if LOC_RE.search(text):
                self.app.show_places(text, parent=self, job_name=self.job["name"])


class ColorPicker(Dialog):
    """A colour wheel (hue around, saturation outwards), a brightness slider, the colour
    code and R/G/B. on_pick("#rrggbb") when OK is clicked."""
    SIZE = 220

    def __init__(self, app, parent, color, on_pick, title="Pick a colour"):
        super().__init__(app, title, parent)
        self.on_pick = on_pick
        self.old = color
        import colorsys
        self.colorsys = colorsys
        r, g, b = hex_to_rgb(color)
        h, sat, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        self.h, self.s_, self.v = h, sat, v
        f = self.body
        top = ttk.Frame(f)
        top.pack()
        self.cv = tk.Canvas(top, width=self.SIZE, height=self.SIZE, highlightthickness=0,
                            bg=app.pal["bg"], cursor="crosshair")
        self.cv.pack(side="left")
        self.wheel_img = None
        self.wheel_item = self.cv.create_image(0, 0, anchor="nw")
        self.dot = self.cv.create_oval(0, 0, 0, 0, outline="#ffffff", width=2)
        self.cv.bind("<Button-1>", self.wheel_at)
        self.cv.bind("<B1-Motion>", self.wheel_at)
        right = ttk.Frame(top, padding=(14, 0, 0, 0))
        right.pack(side="left", fill="y")
        ttk.Label(right, text="Brightness").pack(anchor="w")
        self.v_bright = tk.DoubleVar(value=v * 100)
        ttk.Scale(right, from_=100, to=0, orient="vertical", length=150, variable=self.v_bright,
                  command=lambda e: self.bright_changed()).pack(anchor="w", pady=(2, 8))
        self.swatch = tk.Canvas(right, width=90, height=44, highlightthickness=1,
                                highlightbackground=app.pal["border"])
        self.swatch.pack(anchor="w")
        self.sw_old = self.swatch.create_rectangle(0, 0, 45, 44, outline="", fill=color)
        self.sw_new = self.swatch.create_rectangle(45, 0, 90, 44, outline="", fill=color)
        ttk.Label(right, text="was · new", style="Muted.TLabel").pack(anchor="w")
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=(10, 0))
        ttk.Label(row, text="Code").pack(side="left")
        self.v_hex = tk.StringVar(value=color)
        e = ttk.Entry(row, textvariable=self.v_hex, width=9)
        e.pack(side="left", padx=(6, 12))
        e.bind("<KeyRelease>", lambda ev: self.hex_changed())
        self.v_rgb = []
        for lbl_, val in zip("RGB", (r, g, b)):
            ttk.Label(row, text=lbl_).pack(side="left")
            v_ = tk.IntVar(value=val)
            sp = ttk.Spinbox(row, from_=0, to=255, width=4, textvariable=v_,
                             command=self.rgb_changed)
            sp.pack(side="left", padx=(UNIT_GAP, 10))
            sp.bind("<KeyRelease>", lambda ev: self.rgb_changed())
            self.v_rgb.append(v_)
        ttk.Button(self.footer, text="OK", style="Accent.TButton", command=self.ok).pack(
            side="right")
        ttk.Button(self.footer, text="Cancel", command=self.destroy).pack(side="right",
                                                                          padx=(0, 6))
        self.draw_wheel()
        self.update_all(skip=None)
        self.finish()

    def draw_wheel(self):
        n = self.SIZE
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        c = (n - 1) / 2
        dx, dy = xx - c, yy - c
        r = np.sqrt(dx * dx + dy * dy) / c
        hue = (np.arctan2(-dy, dx) / (2 * np.pi)) % 1.0
        sat = np.clip(r, 0, 1)
        v = self.v
        i = np.floor(hue * 6).astype(int) % 6
        f_ = hue * 6 - np.floor(hue * 6)
        p_, q, t = v * (1 - sat), v * (1 - sat * f_), v * (1 - sat * (1 - f_))
        rgb = np.zeros((n, n, 3), np.float32)
        for k, (a, b_, cc) in enumerate(((v, t, p_), (q, v, p_), (p_, v, t), (p_, q, v),
                                         (t, p_, v), (v, p_, q))):
            m = i == k
            for ch, arr in enumerate((a, b_, cc)):
                rgb[..., ch][m] = (arr if np.ndim(arr) else np.full((n, n), arr))[m]
        bg = hex_to_rgb(self.app.pal["bg"])
        img = (rgb * 255).astype(np.uint8)
        img[r > 1.0] = bg
        self.wheel_img = ImageTk.PhotoImage(Image.fromarray(img))
        self.cv.itemconfigure(self.wheel_item, image=self.wheel_img)

    def wheel_at(self, e):
        import math
        c = (self.SIZE - 1) / 2
        dx, dy = e.x - c, e.y - c
        self.h = (math.atan2(-dy, dx) / (2 * math.pi)) % 1.0
        self.s_ = min(1.0, math.hypot(dx, dy) / c)
        if self.v < 0.05:
            self.v = 1.0
            self.v_bright.set(100)
            self.draw_wheel()
        self.update_all(skip=None)

    def bright_changed(self):
        self.v = max(0.0, min(1.0, self.v_bright.get() / 100))
        self.draw_wheel()
        self.update_all(skip="bright")

    def color(self):
        r, g, b = self.colorsys.hsv_to_rgb(self.h, self.s_, self.v)
        return rgb_to_hex(r * 255, g * 255, b * 255)

    def update_all(self, skip):
        import math
        col = self.color()
        c = (self.SIZE - 1) / 2
        ang = self.h * 2 * math.pi
        x, y = c + math.cos(ang) * self.s_ * c, c - math.sin(ang) * self.s_ * c
        self.cv.coords(self.dot, x - 6, y - 6, x + 6, y + 6)
        self.swatch.itemconfigure(self.sw_new, fill=col)
        if skip != "hex":
            self.v_hex.set(col)
        if skip != "rgb":
            for v_, val in zip(self.v_rgb, hex_to_rgb(col)):
                v_.set(val)

    def set_from_rgb(self, r, g, b, skip):
        h, sat, v = self.colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        redraw = abs(v - self.v) > 1e-3
        self.h, self.s_, self.v = h, sat, v
        self.v_bright.set(v * 100)
        if redraw:
            self.draw_wheel()
        self.update_all(skip=skip)

    def hex_changed(self):
        t = self.v_hex.get().strip()
        if not t.startswith("#"):
            t = "#" + t
        if HEX_RE.match(t):
            self.set_from_rgb(*hex_to_rgb(t), skip="hex")

    def rgb_changed(self):
        try:
            vals = [max(0, min(255, int(v_.get()))) for v_ in self.v_rgb]
        except Exception:
            return
        self.set_from_rgb(*vals, skip="rgb")

    def ok(self):
        col = self.color()
        self._initial = None
        self.destroy()
        self.on_pick(col)


class ColorsDialog(Dialog):
    """Preferences → Appearance → Customize colours (4.5.6): every colour of the app, for the
    light and the dark theme separately. Changes apply right away; ↺ puts one back."""

    def __init__(self, app, parent=None):
        super().__init__(app, "Colours", parent)
        f = self.body
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Colours", style="Title.TLabel").pack(side="left")
        self.v_mode = tk.StringVar(value="dark" if app.is_dark() else "light")
        for val, txt in (("light", "Light theme"), ("dark", "Dark theme")):
            ttk.Radiobutton(top, text=txt, value=val, variable=self.v_mode,
                            style="Seg.TRadiobutton", command=self.fill).pack(side="left",
                                                                             padx=(12, 0))
        ttk.Label(f, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "Click a colour (or Change…) to pick it with a colour wheel or type its code. The "
            "theme you're editing is used while this window is open, so you see the result.")
                  ).pack(anchor="w", pady=(6, 8))
        self.grid = ttk.Frame(f)
        self.grid.pack(fill="x")
        self.rows = {}
        for r, (key, label) in enumerate(COLOR_NAMES):
            sw = tk.Canvas(self.grid, width=34, height=20, highlightthickness=1,
                           highlightbackground=app.pal["border"], cursor="hand2")
            sw.grid(row=r, column=0, padx=(0, 8), pady=2)
            sw.bind("<Button-1>", lambda e, k=key: self.pick(k))
            ttk.Label(self.grid, text=label).grid(row=r, column=1, sticky="w")
            code = ttk.Label(self.grid, style="Muted.TLabel", width=9)
            code.grid(row=r, column=2, sticky="w", padx=(10, 6))
            ttk.Button(self.grid, text="Change…", style="Small.TButton",
                       command=lambda k=key: self.pick(k)).grid(row=r, column=3, padx=(0, 4))
            rb = ttk.Button(self.grid, text="↺", width=3, style="Small.TButton",
                            command=lambda k=key: self.reset(k))
            rb.grid(row=r, column=4)
            self.rows[key] = (sw, code, rb)
        ttk.Button(self.footer, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(self.footer, text="Reset all colours of this theme",
                   command=self.reset_all).pack(side="left")
        self._prev_theme = app.settings.get("theme", "system")
        self.fill()
        self.finish()

    def mine(self):
        cc = dict(self.app.settings.get("custom_colors") or {})
        return cc, dict(cc.get(self.v_mode.get()) or {})

    def fill(self):
        # show the theme being edited
        app = self.app
        want = self.v_mode.get()
        if app.is_dark() != (want == "dark"):
            app.settings["theme"] = want
        app.apply_theme()
        pal = theme_palette(app.settings, want == "dark")
        _, mine = self.mine()
        for key, (sw, code, rb) in self.rows.items():
            sw.configure(bg=pal[key], highlightbackground=app.pal["border"])
            code.configure(text=pal[key] + ("  ✱" if key in mine else ""))
            rb.state(["!disabled"] if key in mine else ["disabled"])

    def save_colors(self, mine):
        cc, _ = self.mine()
        cc[self.v_mode.get()] = mine
        self.app.settings["custom_colors"] = cc
        self.app.save()
        self.fill()

    def pick(self, key):
        pal = theme_palette(self.app.settings, self.v_mode.get() == "dark")
        label = dict(COLOR_NAMES)[key]

        def done(col):
            _, mine = self.mine()
            base = (DARK if self.v_mode.get() == "dark" else LIGHT)[key]
            if col.lower() == base.lower():
                mine.pop(key, None)
            else:
                mine[key] = col
            self.save_colors(mine)
        ColorPicker(self.app, self, pal[key], done, title=f"Colour: {label}")

    def reset(self, key):
        _, mine = self.mine()
        mine.pop(key, None)
        self.save_colors(mine)

    def reset_all(self):
        if messagebox.askyesno(APP_NAME, "Put every colour of this theme back to Clickue's "
                                         "own?", parent=self):
            self.save_colors({})

    def destroy(self):
        try:
            if self.app.settings.get("theme") != self._prev_theme:
                self.app.settings["theme"] = self._prev_theme
                self.app.apply_theme()
                self.app.save()
        except Exception:
            pass
        super().destroy()


class UpgradeDialog(Dialog):
    """Upgrade Clickue in the app (4.6): what's new, then download, check, install."""

    def __init__(self, app, info):
        super().__init__(app, f"Upgrade to Clickue {info['version']}")
        self.info = info
        self.kind = install_kind()
        self.cancel_flag = False
        f = self.body
        ttk.Label(f, text=f"Clickue {info['version']} is available", style="Title.TLabel").pack(
            anchor="w")
        how = {"installer": "It's downloaded from GitHub, checked against the release's "
                            "checksum, and installed over this copy. Clickue closes and starts "
                            "again by itself.",
               "portable": "The portable package is downloaded from GitHub and checked; the "
                           "new Clickue.exe replaces this one (the old one is kept as "
                           "Clickue.old.exe until the next start). Clickue closes and starts "
                           "again by itself.",
               "source": "This copy runs from the source code, so it can't upgrade itself. "
                         "Get the new version from the release page (or with git pull)."}
        ttk.Label(f, style="Muted.TLabel", wraplength=600, justify="left", text=(
            f"You have {VERSION}. {how[self.kind]} Your jobs, settings, history and backups "
            f"stay where they are and are kept; a backup of your jobs is made first.")).pack(
            anchor="w", pady=(4, 8))
        ttk.Label(f, text="What's new", style="Section.TLabel").pack(anchor="w")
        tf = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(4, 0))
        notes = tk.Text(tf, height=14, width=80, wrap="word", borderwidth=0, padx=10, pady=8,
                        bg=app.pal["panel"], fg=app.pal["fg"])
        sb = ttk.Scrollbar(tf, orient="vertical", command=notes.yview)
        notes.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        notes.pack(fill="both", expand=True)
        notes.insert("1.0", info.get("notes") or "(no description)")
        notes.configure(state="disabled")
        self.status = ttk.Label(f, style="Muted.TLabel", text="")
        self.status.pack(anchor="w", pady=(8, 0))
        self.bar = ttk.Progressbar(f, mode="determinate", maximum=100)
        b = self.footer
        ttk.Button(b, text="Close", command=self.close).pack(side="right")
        if self.kind == "source":
            ttk.Button(b, text="Open the release page", style="Accent.TButton",
                       command=lambda: app.open_url(info.get("page"))).pack(side="right",
                                                                            padx=(0, 6))
        else:
            self.go_btn = ttk.Button(b, text=f"⬆  Upgrade to {info['version']}",
                                     style="Accent.TButton", command=self.go)
            self.go_btn.pack(side="right", padx=(0, 6))
            ttk.Button(b, text="Release page", command=lambda: app.open_url(info.get("page"))
                       ).pack(side="left")
        self.finish()

    def close(self):
        self.cancel_flag = True
        self.destroy()

    def go(self):
        app = self.app
        busy = getattr(app, "aq", None) is not None and app.aq.running
        if busy and not messagebox.askyesno(APP_NAME, "A job is running right now. Upgrade "
                                                      "anyway? (It's stopped when Clickue "
                                                      "closes.)", parent=self):
            return
        self.go_btn.state(["disabled"])
        self.bar.pack(fill="x", pady=(6, 0))
        self.status.configure(text="Downloading…")

        def prog(got, total):
            app.cmdq.put(lambda: self.show_progress(got, total))

        def work():
            try:
                path, err = download_update(self.info, self.kind, prog,
                                            stop=lambda: self.cancel_flag), ""
            except Exception as e:
                path, err = None, friendly_net_error(e)[:300]
            app.cmdq.put(lambda: self.downloaded(path, err))
        threading.Thread(target=work, daemon=True).start()

    def show_progress(self, got, total):
        try:
            if total:
                self.bar["value"] = 100 * got / total
            self.status.configure(text=f"Downloading… {got / 1048576:.1f} MB"
                                       + (f" of {total / 1048576:.1f} MB" if total else ""))
        except Exception:
            pass

    def downloaded(self, path, err):
        if err:
            if self.cancel_flag:
                return
            self.app.log(f"Upgrade download failed: {err}")
            try:
                self.status.configure(text=f"Couldn't download: {err}")
                self.go_btn.state(["!disabled"])
            except Exception:
                pass
            return
        try:
            self.status.configure(text="Checked (checksum OK). Installing - Clickue will close "
                                       "and start again…")
        except Exception:
            pass
        self.app.root.after(600, lambda: self.app.finish_upgrade(self.info, self.kind, path))


class DeleteLogsDialog(Dialog):
    """☰ Menu → Delete logs and history… (4.5.6): delete logs and histories for good."""

    def __init__(self, app):
        super().__init__(app, "Delete logs and history")
        f = self.body
        ttk.Label(f, text="Delete logs and history", style="Title.TLabel").pack(anchor="w")
        ttk.Label(f, style="Muted.TLabel", wraplength=520, justify="left", text=(
            "Tick what to delete for good. Your jobs, settings and backups are not touched. "
            "To hide lines only for now, use Clear view in the log itself.")).pack(
            anchor="w", pady=(4, 8))
        self.v = {}
        for key, text in (("log", "Activity and the log file (clickue.log and its older "
                                  "copies)"),
                          ("tests", "Test history (the Tests window)"),
                          ("clicks", "Click history (stats and CSV export)"),
                          ("runs", "Run history (screen videos are kept)")):
            self.v[key] = tk.BooleanVar(value=False)
            ttk.Checkbutton(f, text=text, variable=self.v[key]).pack(anchor="w", pady=2)
        ttk.Button(self.footer, text="Delete", style="Accent.TButton",
                   command=self.go).pack(side="right")
        ttk.Button(self.footer, text="Cancel", command=self.destroy).pack(side="right",
                                                                          padx=(0, 6))
        self.finish()

    def go(self):
        what = [k for k, v in self.v.items() if v.get()]
        if not what:
            self.destroy()
            return
        if not messagebox.askyesno(APP_NAME, "Delete the ticked logs for good? This can't be "
                                             "undone.", parent=self):
            return
        app = self.app
        done = []
        try:
            if "tests" in what:
                with app.lock:
                    app.test_history = []
                    app.tests_dirty = True
                    write_json(TESTS_PATH, app.test_history)
                done.append("test history")
            if "clicks" in what:
                rewrite_history(lambda r: False)
                done.append("click history")
            if "runs" in what:
                rewrite_runlog(lambda r: False)
                done.append("run history")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Couldn't delete everything:\n{e}", parent=self)
        self.destroy()
        if "log" in what:
            app.delete_activity_log(confirm=False)
            done.append("the log file")
        if done:
            app.log("Deleted for good: " + ", ".join(done))
            if app.tests_win is not None:
                app.tests_win.refresh(force=True)


class HelpDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Help & shortcuts")
        f = self.body
        sections = (
            ("Scheduled clicks", "＋ New click → Pick on screen (point within 5 s; Esc or Cancel "
             "stops it) → set how often and an optional random delay → Save. A picture of the "
             "spot is saved, so it's found even if windows move or the screen size changes. "
             "With “Only the exact picture” (on by default) a similar-looking spot is never "
             "clicked."),
            ("Screen watchers", "👁 New watcher → Draw box around the picture (mouse wheel "
             "zooms in, up to 24×, with a magnifier showing the exact pixels) → choose to click "
             "when it disappears or appears → pick the button (or click the picture itself) → "
             "Save. Optionally search only an area (searched with a small margin), and add "
             "active hours. Match: “the exact picture” (default) or “part of the picture is "
             "enough” (a share you choose, e.g. 75 %) when a number or animation inside the "
             "box changes. A watcher doesn't count the picture as gone while the mouse "
             "pointer rests on it (hovering can change how it looks)."),
            ("The job list", "All, Scheduled clicks and Screen watchers each show their own "
             "columns, sized to fit their text (drag or double-click a border to set a width "
             "yourself; ☰ Menu → Reset column widths). Drag the divider above Activity, or "
             "use ▲ / ▼ (Ctrl+Up / Ctrl+Down), to give the list or Activity more room."),
            ("Several jobs at once", "Tick the box at the start of a row (or press X; Ctrl+A "
             "ticks every job shown, the heading box ticks or unticks all). A bar appears: "
             "Start, Stop, Pause, Resume, Duplicate or Delete the ticked jobs, or “Edit "
             "together…” to set the same settings on all of them (only the ones you tick are "
             "changed). One Undo brings back everything a batch delete removed."),
            ("Steps, conditions & loops", "Any job can do more after its click (or instead of "
             "it): click other spots, wait, wait for a picture, type or paste text, press keys, "
             "scroll, drag, branch with If / Otherwise / End, repeat with limits, set "
             "variables, and reuse saved step groups - add them under “Steps” in Edit. Dry run "
             "checks them without clicking; Step through runs them one at a time."),
            ("Recording macros", "⏺ Record (or "
             f"{app.settings.get('hk_record') or 'its hotkey'}) records your mouse and keyboard, "
             "then shows the steps to edit. Don't type passwords while recording."),
            ("Type or paste?", "Type text presses each key like a keyboard (works everywhere, "
             "slower). Paste text puts it on the clipboard and presses Ctrl+V (fast, exact, "
             "any language), then puts your clipboard back. Either way the text goes to "
             "whatever has focus, so click the field first."),
            ("One mouse, many jobs", "Only one job clicks or types at a time; the others wait "
             "their turn (shown above the job list). Watchers keep watching meanwhile. "
             f"Emergency stop: {app.settings.get('hk_stop') or '(set a hotkey)'}."),
            ("Tests", "🧪 Tests opens a popup with Show spot, Test click, Check picture, Dry run "
             "and scheduled tests, in three sections (All tests, Click tests, Watcher tests), "
             "each with its own history for this job or all jobs. Check picture outlines "
             "every copy of the picture it finds. The whole app hides while a test runs. Preferences → "
             "Clicking sets how long the marker stays and can outline every similar picture."),
            ("Updates", "When a new version is out, a bar appears: Upgrade now downloads it from "
             "GitHub, checks it and installs it, keeping your jobs and settings. ☰ Menu → Check "
             "for updates. Turn checks off in Preferences → General and Clickue never goes "
             "online for updates. A certificate error means the connection couldn't be "
             "trusted (often antivirus HTTPS scanning or a company proxy); Clickue then doesn't "
             "connect."),
            ("Watchers and windows", "A watcher whose button is inside a window watches that "
             "window too: closed or minimized means Can't watch and no click. A watched "
             "picture never counts as found where a Clickue window is in front of it; a "
             "Clickue window behind the browser doesn't matter."),
            ("Is everything OK?", "Hover over a job: it says what the job is doing, any "
             "problem and what to do. A watcher that can't see its picture shows ⚠ Can't watch. "
             "The tray icon dot: amber = a click is counting down, green = clicking now, red = "
             "a problem. ⟳ Refresh (F5) makes watchers look right away. The summary follows "
             "the filter (all / clicks / watchers). Jobs with steps have ▸ to list their steps."),
            ("Mouse movement", "A job (or a click step, or a recorded macro) can move the mouse "
             "to its click like a person instead of jumping: Edit → Click → Mouse movement, "
             "or the default in Preferences → Clicking (with a speed)."),
            ("Colours", "Preferences → Appearance → Customize colours: every colour of the "
             "light and dark theme, with a colour wheel or a code."),
            ("Logs", "Every log (Activity, test history, run history, stats, dry run): "
             "right-click to copy rows, one cell or everything (pastes into a spreadsheet), "
             "save as CSV, or show a place like (878, 243) on screen; type in the 🔍 box to "
             "filter. In Activity, click a place to see it. Activity keeps earlier lines until "
             "its Delete button (Clear view only hides lines for now). ⟳ Refresh and newest/oldest "
             "first are on every log; Preferences → Data & backups → How much to log. Test "
             "results say what their colour means: "
             "OK, Attention or Failed."),
            ("Tray icon", "Point at Clickue's tray icon to see whether your jobs are running fine; "
             "right-click it → Job status for every job."),
            ("Locked screen", "Windows blocks clicks and screenshots while locked or "
             "disconnected. Hand the session to the console when leaving RDP, and lock your own "
             "PC instead of the VM."),
            ("Shortcuts", "Ctrl+N new click  ·  Ctrl+Shift+N new watcher  ·  Enter edit  ·  "
             "Space start/stop  ·  P pause job  ·  Ctrl+P pause all  ·  Ctrl+T tests  ·  "
             "Ctrl+Z undo delete  ·  Ctrl+, preferences  ·  Del delete  ·  X tick  ·  "
             "Ctrl+A tick all\n"
             f"Anywhere (global): {app.settings.get('hk_pause') or '-'} pause all  ·  "
             f"{app.settings.get('hk_show') or '-'} show/hide Clickue"),
        )
        for title, text in sections:
            ttk.Label(f, text=title, style="Section.TLabel").pack(anchor="w", pady=(8, 2))
            ttk.Label(f, text=text, style="Muted.TLabel", wraplength=560,
                      justify="left").pack(anchor="w")
        ttk.Label(f, text="Please note", style="Section.TLabel").pack(anchor="w", pady=(8, 2))
        ttk.Label(f, text=DISCLOSURE, style="Warn.TLabel", wraplength=560,
                  justify="left").pack(anchor="w")
        ttk.Label(f, text="Every feature, with examples and pictures, is explained in the "
                          "complete guide on GitHub.", style="Muted.TLabel", wraplength=560,
                  justify="left").pack(anchor="w", pady=(12, 0))
        ttk.Button(self.footer, text="Open the complete guide", style="Accent.TButton",
                   command=app.open_guide).pack(side="left")
        ttk.Button(self.footer, text="Close", command=self.destroy).pack(side="right")
        self.finish()


class AboutDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, f"About {APP_NAME}")
        f = self.body
        row = ttk.Frame(f)
        row.pack(anchor="w")
        if HAVE_PIL:
            self._logo = ImageTk.PhotoImage(make_logo(72))
            ttk.Label(row, image=self._logo).pack(side="left", padx=(0, 14))
        col = ttk.Frame(row)
        col.pack(side="left")
        ttk.Label(col, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(col, text=f"Version {VERSION}" + ("  ·  portable" if PORTABLE else ""),
                  style="Muted.TLabel").pack(anchor="w")
        feats = []
        for ok, name in ((HAVE_TRAY, "tray icon"), (HAVE_CV, "picture matching"),
                         (IS_WIN, "Windows clicking")):
            feats.append(("✔ " if ok else "✖ ") + name)
        ttk.Label(f, text="   ".join(feats), style="Muted.TLabel").pack(anchor="w", pady=(12, 2))
        ttk.Label(f, text=f"Your data: {DATA_DIR}", style="Muted.TLabel").pack(anchor="w")
        ttk.Label(f, text="Planned (not in this version): " + ", ".join(
            n for _, n, _ in PLANNED_ADAPTERS) + ".", style="Muted.TLabel", wraplength=520,
            justify="left").pack(anchor="w", pady=(6, 0))
        ttk.Label(f, text=DISCLOSURE, style="Warn.TLabel", wraplength=520,
                  justify="left").pack(anchor="w", pady=(10, 0))
        ttk.Label(f, text=f"Source code and security notes: {REPO_URL}", style="Muted.TLabel",
                  wraplength=520, justify="left").pack(anchor="w", pady=(6, 0))
        ttk.Button(self.footer, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(self.footer, text="Check for updates…",
                   command=lambda: app.check_for_updates(True, self)).pack(side="left")
        self.finish()


class SettingsDialog(Dialog):
    """Preferences, in tabs."""
    TABS = (("general", "General"), ("clicking", "Clicking"), ("watchers", "Watchers"),
            ("hotkeys", "Hotkeys"), ("alerts", "Phone alerts"), ("recording", "Recording & video"),
            ("look", "Appearance"), ("data", "Data & backups"))

    def __init__(self, app):
        super().__init__(app, "Preferences")
        s = app.settings
        f = self.body
        self.vars = {}
        tabs = ttk.Frame(f)
        tabs.pack(fill="x", pady=(0, 10))
        self.v_tab = tk.StringVar(value=app.settings.get("prefs_tab", "general"))
        for key, text in self.TABS:
            ttk.Radiobutton(tabs, text=text, value=key, variable=self.v_tab,
                            style="Seg.TRadiobutton", command=self.show_tab).pack(
                side="left", padx=(0, 2))
        self.holder = ttk.Frame(f)
        self.holder.pack(fill="both", expand=True)
        self.pages = {k: ttk.Frame(self.holder) for k, _ in self.TABS}

        def check(parent, key, text, enabled=True):
            v = tk.BooleanVar(value=bool(s.get(key)))
            self.vars[key] = v
            cb = ttk.Checkbutton(parent, text=text, variable=v)
            cb.pack(anchor="w", pady=2)
            if not enabled:
                cb.state(["disabled"])
            return cb

        def spin(parent, key, label, lo, hi, unit):
            row = ttk.Frame(parent)
            row.pack(anchor="w", pady=2)
            ttk.Label(row, text=label).pack(side="left")
            v = tk.IntVar(value=int(s.get(key)))
            self.vars[key] = v
            ttk.Spinbox(row, from_=lo, to=hi, width=6, textvariable=v).pack(side="left", padx=(6, UNIT_GAP))
            ttk.Label(row, text=unit, style="Muted.TLabel").pack(side="left")

        def text(parent, key, label, width=40, show=None):
            row = ttk.Frame(parent)
            row.pack(anchor="w", pady=2, fill="x")
            ttk.Label(row, text=label, width=22).pack(side="left")
            v = tk.StringVar(value=str(s.get(key) or ""))
            self.vars[key] = v
            e = ttk.Entry(row, textvariable=v, width=width, show=show or "")
            e.pack(side="left", fill="x", expand=True)
            return e

        def note(parent, txt, style="Muted.TLabel"):
            ttk.Label(parent, text=txt, style=style, wraplength=560, justify="left").pack(
                anchor="w", pady=(4, 2))

        # General
        p = self.pages["general"]
        check(p, "minimize_to_tray", "Minimize to the system tray", HAVE_TRAY)
        check(p, "close_to_tray", "Close button (X) hides to the tray instead of exiting", HAVE_TRAY)
        check(p, "notifications", "Tray notifications (missed clicks, watchers, test results)",
              HAVE_TRAY)
        check(p, "start_minimized", "Start minimized")
        check(p, "start_with_windows", "Start automatically when I sign in to Windows", IS_WIN)
        check(p, "keep_awake", "Keep the PC and display awake")
        check(p, "tray_status", "Show the jobs' status when I point at the tray icon (and in "
                                "its right-click menu → Job status)", HAVE_TRAY)
        check(p, "update_check", "Check for new versions once a day (only asks GitHub; off = "
                                 "Clickue never connects to the internet for updates)")
        check(p, "tray_colors", "Colour the tray icon: amber = a click is coming up, green = "
                                "clicking now, red = a job has a problem", HAVE_TRAY)
        check(p, "activity_clear_on_start", "Clear Activity every time Clickue starts "
                                            "(off: it keeps earlier lines until Clear view)")
        if not HAVE_TRAY:
            note(p, "Tray features need the pystray and pillow packages. Start Clickue.bat "
                    "installs them.", "Warn.TLabel")

        # Clicking
        p = self.pages["clicking"]
        spin(p, "retry_minutes", "If a click can't happen (screen locked / disconnected), "
                                 "keep retrying for", 0, 1440, "min")
        spin(p, "idle_seconds", "Wait until mouse & keyboard have been idle for", 0, 300,
             "sec  (0 = off)")
        check(p, "restore_cursor", "Put the mouse back where it was after clicking")
        check(p, "human_move", "Move the mouse to each click like a person (curved, smooth, "
                               "not a jump) - jobs can choose otherwise in their editor")
        hr = ttk.Frame(p)
        hr.pack(anchor="w", pady=2)
        ttk.Label(hr, text="Speed of those movements").pack(side="left", padx=(0, 8))
        hv = tk.StringVar(value=s.get("human_speed", "normal")
                          if s.get("human_speed") in HUMAN_SPEEDS else "normal")
        self.vars["human_speed"] = hv
        for val, txt in (("slow", "Slow"), ("normal", "Normal"), ("fast", "Fast")):
            ttk.Radiobutton(hr, text=txt, value=val, variable=hv).pack(side="left", padx=(0, 10))
        note(p, "Waiting for idle keeps Clickue from grabbing the mouse while you're using it.")
        check(p, "warn_conflicts", "Warn me when two running jobs use the same window or spot")
        note(p, "Only one job clicks or types at a time (Windows has one mouse and one keyboard "
                "focus); the others wait their turn. Watchers keep watching meanwhile.")
        ttk.Label(p, text="Checking a spot (Show spot, Check now)", style="Section.TLabel").pack(
            anchor="w", pady=(10, 0))
        spin(p, "marker_seconds", "Keep the marker on screen for", 1, 120, "sec  (default 5)")
        check(p, "show_similar", "Also point out every similar picture on the screen at the "
                                 "same time", HAVE_CV)
        note(p, "Green = the place that would be used, orange = the same picture somewhere "
                "else (not used), grey = similar but not the same (ignored). Useful to see "
                "why a spot is or isn't found.")

        # Watchers
        p = self.pages["watchers"]
        spin(p, "default_watch_interval", "New watchers check every", 1, 86400, "sec")
        spin(p, "default_watch_confirm", "New watchers click after the change is seen", 1, 20,
             "checks in a row")
        note(p, "These are only the starting values for new watchers; each watcher has its own "
                "settings in Edit.")

        # Hotkeys
        p = self.pages["hotkeys"]
        check(p, "hotkeys_on", "Use global hotkeys (they work even while Clickue is hidden)", IS_WIN)
        text(p, "hk_pause", "Pause / resume all", 20)
        text(p, "hk_show", "Show / hide Clickue", 20)
        text(p, "hk_stop", "Emergency stop", 20)
        text(p, "hk_record", "Start / stop recording", 20)
        text(p, "hk_rec_pause", "Pause / resume recording", 20)
        note(p, "Emergency stop ends the running job at once, drops queued clicks, lets go of "
                "any held keys or buttons, throws away a recording in progress, and pauses "
                "everything.")
        note(p, "Use at least one of Ctrl, Alt, Shift, Win plus a key, e.g. Ctrl+Alt+P. Leave a "
                "box empty to turn that hotkey off.")

        # Alerts
        p = self.pages["alerts"]
        check(p, "alerts_on", "Send alerts to my phone")
        note(p, "Discord: in a server you own, Channel settings → Integrations → Webhooks → "
                "New webhook → Copy URL. Telegram: create a bot with @BotFather (gives the "
                "token), send it a message, then get your chat id from @userinfobot.")
        text(p, "alert_discord", "Discord webhook URL", 52, show="•")
        text(p, "alert_tg_token", "Telegram bot token", 52, show="•")
        text(p, "alert_tg_chat", "Telegram chat id", 20)
        note(p, "Treat these like passwords: anyone who has them can post to your channel or "
                "bot. Clickue only sends to discord.com and api.telegram.org over HTTPS, and "
                "keeps them out of logs, backups and exported jobs.")
        check(p, "protect_secrets", "Protect them with my Windows account (encrypted on disk; "
                                    "after moving to another PC or account, enter them again)",
              HAVE_DPAPI)
        ttk.Label(p, text="Send an alert when…").pack(anchor="w", pady=(8, 2))
        ev = s.get("alert_events") or {}
        self.ev_vars = {}
        for key, label in ALERT_EVENTS:
            v = tk.BooleanVar(value=bool(ev.get(key)))
            self.ev_vars[key] = v
            ttk.Checkbutton(p, text=label, variable=v).pack(anchor="w", padx=(16, 0))
        r = ttk.Frame(p)
        r.pack(anchor="w", pady=(8, 0))
        ttk.Button(r, text="Send a test alert", command=self.test_alert).pack(side="left")
        self.alert_result = ttk.Label(r, style="Muted.TLabel")
        self.alert_result.pack(side="left", padx=10)
        note(p, "Alerts need internet access from this computer.")

        # Recording & video
        p = self.pages["recording"]
        ttk.Label(p, text="Macro recorder", style="Section.TLabel").pack(anchor="w")
        check(p, "rec_moves", "Record mouse movement (simplified)")
        check(p, "rec_pictures", "Save a picture of each clicked spot (so clicks can find "
                                 "their target later)", HAVE_CV)
        check(p, "rec_timing", "Keep the pauses between actions")
        ttk.Label(p, text="Screen video of runs", style="Section.TLabel").pack(anchor="w",
                                                                               pady=(10, 0))
        check(p, "video_on", "Allow screen videos for jobs that ask for it (each job: Edit → "
                             "Run options → Record the screen)", HAVE_CV)
        r = ttk.Frame(p)
        r.pack(anchor="w", pady=2)
        ttk.Label(r, text="Quality").pack(side="left")
        names = {k: v["label"].split(":")[0] for k, v in VIDEO_PRESETS.items()}
        self.v_preset = tk.StringVar(value=names.get(s.get("video_preset"), "Standard"))
        cb = ttk.Combobox(r, values=list(names.values()), state="readonly", width=10,
                          textvariable=self.v_preset)
        cb.pack(side="left", padx=6)
        self.preset_note = ttk.Label(p, style="Muted.TLabel", wraplength=560, justify="left")
        self.preset_note.pack(anchor="w")
        cb.bind("<<ComboboxSelected>>", lambda e: self.preset_changed())
        self.preset_changed()
        r = ttk.Frame(p)
        r.pack(anchor="w", pady=2, fill="x")
        ttk.Label(r, text="Save videos in").pack(side="left")
        self.v_vdir = tk.StringVar(value=s.get("video_dir") or "")
        self.vdir_lbl = ttk.Label(r, style="Muted.TLabel")
        self.vdir_lbl.pack(side="left", padx=6)
        ttk.Button(r, text="Choose…", style="Small.TButton", command=self.choose_vdir).pack(
            side="left")
        ttk.Button(r, text="Default", style="Small.TButton",
                   command=lambda: (self.v_vdir.set(""), self.show_vdir())).pack(side="left",
                                                                                padx=4)
        self.show_vdir()
        spin(p, "video_keep_days", "Delete videos older than", 1, 3650, "days")
        spin(p, "video_max_gb", "and keep at most", 1, 2000, "GB of them (oldest go first)")
        check(p, "video_hide_text", "Black out the video while Clickue types or pastes text")
        self.redact = [list(r) for r in (s.get("video_redact") or []) if _clean_rect(r)]
        r = ttk.Frame(p)
        r.pack(anchor="w", pady=(4, 0))
        self.redact_lbl = ttk.Label(r)
        self.redact_lbl.pack(side="left")
        ttk.Button(r, text="Add an area to hide…", style="Small.TButton",
                   command=self.add_redact).pack(side="left", padx=6)
        ttk.Button(r, text="Clear", style="Small.TButton",
                   command=lambda: (self.redact.clear(), self.show_redact())).pack(side="left")
        self.show_redact()
        note(p, "Videos stay on this computer: Clickue never uploads them. They show whatever "
                "is on screen during a run, so keep them private. Only the run itself is "
                "recorded, and a small red bar at the top of the screen shows while it is.")
        ttk.Label(p, text="Run history", style="Section.TLabel").pack(anchor="w", pady=(10, 0))
        check(p, "run_log_on", "Keep a run history: each step, its result and the video "
                               "position (never the text typed or pasted)")
        spin(p, "diag_keep", "Keep the newest", 1, 500, "failure screenshots")
        ttk.Button(p, text="Run history & videos…", command=app.open_run_history).pack(
            anchor="w", pady=(4, 0))

        # Appearance
        p = self.pages["look"]
        row = ttk.Frame(p)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Theme").pack(side="left")
        self.v_theme = tk.StringVar(value=s.get("theme", "system").capitalize())
        ttk.Combobox(row, values=("System", "Light", "Dark"), state="readonly", width=9,
                     textvariable=self.v_theme).pack(side="left", padx=6)
        check(p, "show_cards", "Show the summary cards at the top")
        ttk.Label(p, text="Colours", style="Section.TLabel").pack(anchor="w", pady=(12, 0))
        note(p, "Change any colour of the app - window, text, labels, borders, buttons, rows, "
                "status colours - with a colour wheel or a code (#1e5ac8). Light and dark "
                "themes have their own colours. Changes show right away.")
        ttk.Button(p, text="🎨  Customize colours…",
                   command=lambda: ColorsDialog(app, self)).pack(anchor="w", pady=(4, 0))

        # Data & backups
        p = self.pages["data"]
        check(p, "backups_on", "Back up my jobs and settings once a day")
        spin(p, "backups_keep", "Keep the newest", 1, 365, "daily backups")
        check(p, "history_on", "Keep a click history (for stats and CSV export)")
        spin(p, "log_max_mb", "Log file size limit", 1, 50,
             "MB  (2 older copies are kept; older ones are deleted)")
        lr = ttk.Frame(p)
        lr.pack(anchor="w", pady=(6, 0))
        ttk.Label(lr, text="How much to log (Activity and the log file)").pack(side="left",
                                                                            padx=(0, 8))
        v = tk.StringVar(value=s.get("log_level", "normal")
                         if s.get("log_level") in LOG_LEVELS else "normal")
        self.vars["log_level"] = v
        for val, txt in (("quiet", "Quiet"), ("normal", "Normal"), ("detailed", "Detailed")):
            ttk.Radiobutton(lr, text=txt, value=val, variable=v).pack(side="left", padx=(0, 10))
        note(p, "Quiet: clicks, problems and starts/stops only. Normal (default): also every "
                "check that has a problem, with what to do. Detailed: also every successful "
                "check with where the picture was seen - useful while setting up or tracking "
                "down a problem.")
        note(p, f"Everything is stored in:\n{DATA_DIR}")
        r = ttk.Frame(p)
        r.pack(anchor="w", pady=(6, 0))
        ttk.Button(r, text="Backups…", command=lambda: BackupsDialog(app)).pack(side="left")
        ttk.Button(r, text="Open data folder", command=app.open_data_folder).pack(side="left",
                                                                               padx=6)
        ttk.Button(r, text="Export click history…", command=lambda: app.export_history(
            parent=self)).pack(side="left")
        ttk.Button(p, text="Uninstall Clickue…", command=lambda: app.uninstall(self)).pack(
            anchor="w", pady=(14, 0))

        b = self.footer
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Save", style="Accent.TButton", command=self.on_save).pack(
            side="right", padx=6)
        # make room for the tallest tab so switching tabs never needs scrolling
        self.update_idletasks()
        mh = max(p.winfo_reqheight() for p in self.pages.values())
        mw = max(p.winfo_reqwidth() for p in self.pages.values())
        self.holder.configure(height=mh, width=mw)
        self.holder.pack_propagate(False)
        self.show_tab()
        self.finish()

    def show_tab(self):
        for p in self.pages.values():
            p.pack_forget()
        key = self.v_tab.get()
        self.pages.get(key, self.pages["general"]).pack(fill="both", expand=True)
        self.app.settings["prefs_tab"] = key
        self.after(30, self._sync_scroll)

    def preset_changed(self):
        key = next((k for k, v in VIDEO_PRESETS.items()
                    if v["label"].startswith(self.v_preset.get())), "standard")
        self.preset_note.configure(text=VIDEO_PRESETS[key]["label"] + " Higher quality = bigger "
                                   "files. Videos are MP4 (or AVI if MP4 isn't available).")

    def preset_key(self):
        return next((k for k, v in VIDEO_PRESETS.items()
                     if v["label"].startswith(self.v_preset.get())), "standard")

    def show_vdir(self):
        d = self.v_vdir.get() or data_path("recordings")
        self.vdir_lbl.configure(text=short_title(d, 48) + ("" if self.v_vdir.get() else " (default)"))

    def choose_vdir(self):
        d = filedialog.askdirectory(parent=self, title="Folder for screen videos",
                                    mustexist=True)
        if d:
            if not os.access(d, os.W_OK):
                messagebox.showerror(APP_NAME, "Clickue can't write to that folder.", parent=self)
                return
            self.v_vdir.set(os.path.abspath(d))
            self.show_vdir()

    def show_redact(self):
        n = len(self.redact)
        self.redact_lbl.configure(text=f"Always hidden in videos and failure screenshots: "
                                       f"{n} area{'s' if n != 1 else ''}")

    def add_redact(self):
        def done(img, rect):
            self.redact.append(rect)
            self.show_redact()
        self.app.draw_capture(self, "Drag a box around an area to always hide in videos", done,
                              with_rect=True)

    def test_alert(self):
        settings = dict(self.app.settings)
        for k in ("alert_discord", "alert_tg_token", "alert_tg_chat"):
            settings[k] = self.vars[k].get().strip()
        self.alert_result.configure(text="Sending…")

        def show(res):
            txt = "   ".join(f"{svc}: {'✔ sent' if ok else '✖ ' + info}" for svc, ok, info in res)
            try:
                self.after(0, lambda: self.alert_result.configure(text=txt))
            except Exception:
                pass

        def run():
            show(send_alert(settings, "This is a test alert. If you can read this, alerts work!",
                            limit=False))
        threading.Thread(target=run, daemon=True).start()

    def on_save(self):
        app, s = self.app, self.app.settings
        new = {}
        try:
            for k, v in self.vars.items():
                if isinstance(v, tk.BooleanVar):
                    new[k] = bool(v.get())
                elif isinstance(v, tk.IntVar):
                    new[k] = max(0, int(v.get()))
                else:
                    new[k] = v.get().strip()
        except Exception:
            messagebox.showerror(APP_NAME, "Please check the numbers.", parent=self)
            return
        hks = ("hk_pause", "hk_show", "hk_stop", "hk_record", "hk_rec_pause")
        for k in hks:
            if new[k]:
                try:
                    parse_hotkey(new[k])
                except ValueError as e:
                    messagebox.showerror(APP_NAME, f"Hotkey “{new[k]}”: {e}", parent=self)
                    return
        used = [new[k].replace(" ", "").lower() for k in hks if new[k]]
        if len(used) != len(set(used)):
            messagebox.showerror(APP_NAME, "Each hotkey must be different.", parent=self)
            return
        if new["alert_discord"]:
            good, why = check_discord_url(new["alert_discord"])
            if not good:
                messagebox.showerror(APP_NAME, f"Discord webhook URL: {why}.", parent=self)
                return
        if new["alert_tg_token"] or new["alert_tg_chat"]:
            good, why = check_telegram(new["alert_tg_token"], new["alert_tg_chat"])
            if not good:
                messagebox.showerror(APP_NAME, f"Telegram: {why}.", parent=self)
                return
        new["video_preset"] = self.preset_key()
        new["video_dir"] = self.v_vdir.get().strip()
        new["video_redact"] = [list(r) for r in self.redact]
        new["video_keep_days"] = max(1, new["video_keep_days"])
        new["video_max_gb"] = max(1, new["video_max_gb"])
        new["diag_keep"] = max(1, new["diag_keep"])
        new["log_max_mb"] = max(1, new["log_max_mb"])
        new["backups_keep"] = max(1, new["backups_keep"])
        new["default_watch_interval"] = max(1, new["default_watch_interval"])
        new["default_watch_confirm"] = max(1, new["default_watch_confirm"])
        new["theme"] = self.v_theme.get().lower()
        new["alert_events"] = {k: bool(v.get()) for k, v in self.ev_vars.items()}

        old_start, old_mb, old_cards = (s.get("start_with_windows"), s.get("log_max_mb"),
                                        s.get("show_cards", True))
        old_hk = (s.get("hotkeys_on"), s.get("hk_pause"), s.get("hk_show"), s.get("hk_stop"),
                  s.get("hk_record"), s.get("hk_rec_pause"))
        with app.lock:
            s.update(new)
        if new["start_with_windows"] != old_start or new["start_with_windows"]:
            if not set_run_at_startup(new["start_with_windows"]) and IS_WIN:
                s["start_with_windows"] = old_start
                messagebox.showwarning(APP_NAME, "Couldn't change the start-with-Windows "
                                                 "setting.", parent=self)
        if new["log_max_mb"] != old_mb:
            app.setup_logging()
        if bool(new["show_cards"]) != bool(old_cards):
            s["show_cards"] = old_cards
            app.toggle_cards()
        if (new["hotkeys_on"], new["hk_pause"], new["hk_show"], new["hk_stop"], new["hk_record"],
                new["hk_rec_pause"]) != old_hk:
            app.start_hotkeys()
        keep_awake(s["keep_awake"])
        app.apply_theme()
        app.save()
        app.log("Preferences saved")
        self.destroy()


# ---------------------------------------------------------------- main
_MUTEX = None


def main():
    global _MUTEX
    if "--make-icon" in sys.argv:
        write_icon_file(sys.argv[sys.argv.index("--make-icon") + 1])
        return
    if IS_WIN:
        # Tell Windows this is "Clickue" (taskbar, tray settings, notifications), not the
        # program that runs it (python.exe) or an older name it may remember.
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                ctypes.c_wchar_p(APP_ID + "." + APP_NAME))
        except Exception:
            pass
    root = tk.Tk()
    if IS_WIN:
        _MUTEX = kernel32.CreateMutexW(None, False, "Local\\" + APP_ID + "_single_instance")
        already = ctypes.get_last_error() == 183        # ERROR_ALREADY_EXISTS
        old = kernel32.CreateMutexW(None, False, "Local\\" + OLD_APP_ID + "_single_instance")
        if not already and ctypes.get_last_error() == 183:
            root.withdraw()
            messagebox.showinfo(APP_NAME, "The old Scheduled AutoClicker is still running.\n\n"
                                          "Exit it first (right-click its tray icon > Exit), then "
                                          "start Clickue again.")
            root.destroy()
            return
        if already:
            root.withdraw()
            messagebox.showinfo(APP_NAME, f"{APP_NAME} is already running.\n\n"
                                          "Look for its icon in the system tray (near the "
                                          "clock); you may need to click the ^ arrow.")
            root.destroy()
            return
    else:
        print("Note: clicking only works on Windows. The window opens for preview.")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
