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
VERSION = "4.4"
REPO_URL = "https://github.com/jnssylvest/clickue"
GUIDE_URL = REPO_URL + "/blob/main/docs/GUIDE.md"      # the complete guide (☰ Menu)

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
                "found_xy")

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


def do_click(x, y, button="left", clicks=1, restore_cursor=True):
    if not IS_WIN:
        return False, "this program only clicks on Windows"
    old = get_cursor()
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
        user32.SetCursorPos(*old)
    return True, "clicked"


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
    w = max(min_w, min(w, vw - 20))
    h = max(min_h, min(h, vh - 60))
    x = min(max(x, vx), vx + vw - w)
    y = min(max(y, vy), vy + vh - h - 40)
    return f"{w}x{h}+{x}+{max(vy, y)}"


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


def grab_screen(move_cursor=True):
    """Screenshot of all monitors -> (image, (left, top) of the image in screen pixels).
    The mouse is moved out of the way first so hover highlights don't change the picture."""
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


def find_picture(screen_gray, tmpl_gray, spot, expected=None, scale_hint=None):
    """Search a screenshot for the saved picture at several sizes.
    Each candidate is checked twice: the whole picture, and a small close-up around the
    spot itself (the close-up is what tells the right place from look-alikes).
    Returns (score, x, y, scale, whole, closeup) in screenshot pixels, or None."""
    H, W = screen_gray.shape[:2]
    th0, tw0 = tmpl_gray.shape[:2]
    cw, ch = min(tw0, 60), min(th0, 34)
    cx0 = int(min(max(spot[0] - cw // 2, 0), tw0 - cw))
    cy0 = int(min(max(spot[1] - ch // 2, 0), th0 - ch))
    core = tmpl_gray[cy0:cy0 + ch, cx0:cx0 + cw]
    scales = list(MATCH_SCALES)
    if scale_hint and abs(scale_hint - 1) > 0.02:
        scales = sorted(set(scales) | {round(scale_hint, 3)},
                        key=lambda v: abs(np.log(v / scale_hint)))
    cands = []
    for sc in scales:
        tw, th = round(tw0 * sc), round(th0 * sc)
        if tw < 16 or th < 12 or tw > W or th > H:
            continue
        interp = cv2.INTER_AREA if sc < 1 else cv2.INTER_LINEAR
        t = tmpl_gray if sc == 1 else cv2.resize(tmpl_gray, (tw, th), interpolation=interp)
        c = core if sc == 1 else cv2.resize(core, (max(8, round(cw * sc)), max(6, round(ch * sc))),
                                            interpolation=interp)
        res = _match(screen_gray, t)
        top = None
        for _ in range(6):                       # a few best places at this size
            _, v, _, (lx, ly) = cv2.minMaxLoc(res)
            if top is None:
                top = v
            if v < max(0.5, top - 0.15):
                break
            px, py = lx + cx0 * sc, ly + cy0 * sc
            x0, y0 = int(max(0, px - 4)), int(max(0, py - 4))
            win = screen_gray[y0:int(py) + c.shape[0] + 5, x0:int(px) + c.shape[1] + 5]
            cs = -1.0
            if win.shape[0] >= c.shape[0] and win.shape[1] >= c.shape[1]:
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
    good = [c for c in cands if c[4] >= MATCH_WHOLE_MIN and c[5] >= MATCH_CLOSEUP_MIN]
    if not good:
        return max(cands, key=lambda c: c[0]) if cands else None
    best = max(c[0] for c in good)
    near = [c for c in good if c[0] >= best - 0.02]
    if expected and len(near) > 1:               # look-alikes: take the one nearest the saved spot
        ex, ey = expected
        return min(near, key=lambda c: (c[1] - ex) ** 2 + (c[2] - ey) ** 2)
    return max(near, key=lambda c: c[0])


def is_match(r):
    return bool(r) and r[4] >= MATCH_WHOLE_MIN and r[5] >= MATCH_CLOSEUP_MIN


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
    if not uses_picture(job):
        ok, x, y, msg = resolve_target(job, activate=activate, check_cover=check_cover)
        return ok, x, y, msg, "saved position"
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
        return False, 0, 0, f"couldn't capture the screen ({e})", ""
    tmpl = cv2.cvtColor(np.asarray(b64_to_img(job["snap_png"])), cv2.COLOR_RGB2GRAY)
    spot = job.get("snap_spot") or [tmpl.shape[1] // 2, tmpl.shape[0] // 2]
    full = cv2.cvtColor(np.asarray(shot), cv2.COLOR_RGB2GRAY)
    tries = []
    if region:                                   # look inside the window first
        l, t, w, h = region
        x0, y0 = max(0, l - vx), max(0, t - vy)
        sub = full[y0:y0 + h, x0:x0 + w]
        if sub.size:
            tries.append((sub, vx + x0, vy + y0))
    tries.append((full, vx, vy))
    ps_dpi, cur_dpi = job.get("pick_dpi"), system_dpi()
    hint = cur_dpi / ps_dpi if ps_dpi else None
    found = None
    for img, ox, oy in tries:
        exp = (ex - ox, ey - oy) if eok else None
        r = find_picture(img, tmpl, spot, exp, hint)
        if r and (found is None or (is_match(r), r[0]) > (is_match(found), found[0])):
            found = (r[0], round(r[1] + ox), round(r[2] + oy), r[3], r[4], r[5])
        if is_match(found):
            break
    if is_match(found):
        score, x, y, sc = found[:4]
        if check_cover and IS_WIN:
            w = window_at(x, y)
            if w and is_own_window(w):
                return False, x, y, "the Clickue window is covering the spot", ""
        how = f"picture {min(found[4], found[5]):.0%}" + (
            "" if abs(sc - 1) < 0.01 else f" at {sc:.0%} size")
        return True, x, y, "", how
    best = f"{max(0.0, min(found[4], found[5])):.0%}" if found else "none"
    if job.get("image_fallback") == "position":
        ok, x, y, msg = resolve_target(job, activate=False, check_cover=check_cover)
        return ok, x, y, msg, f"saved position (picture not found, best {best})"
    return False, 0, 0, f"couldn't find the saved picture on screen (best match {best})", ""


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


def picture_on_screen(png_b64, scale_hint=None, shot=None, area=None):
    """Is this exact picture on the screen (or inside `area`) right now?
    Stricter than finding a click spot: shape, colour and (at the original size) fine
    detail must all agree, so a similar-looking replacement doesn't count as "still there".
    Returns (found, x, y, score, scale) - x, y is the picture's centre on screen."""
    if shot is None:
        shot = grab_screen(move_cursor=False)
    img, (vx, vy) = shot
    if area:
        ax, ay, aw, ah = area
        l, t = max(0, ax - vx), max(0, ay - vy)
        r, b = min(img.width, ax - vx + aw), min(img.height, ay - vy + ah)
        if r - l >= 16 and b - t >= 16:
            img = img.crop((l, t, r, b))
            vx, vy = vx + l, vy + t
    t_rgb = np.ascontiguousarray(np.asarray(b64_to_img(png_b64)))
    s_rgb = np.ascontiguousarray(np.asarray(img))
    tmpl = cv2.cvtColor(t_rgb, cv2.COLOR_RGB2GRAY)
    full = cv2.cvtColor(s_rgb, cv2.COLOR_RGB2GRAY)
    spot = (tmpl.shape[1] // 2, tmpl.shape[0] // 2)
    r = find_picture(full, tmpl, spot, None, scale_hint)
    if not r:
        return False, 0, 0, 0.0, None
    score = max(0.0, min(r[4], r[5]))
    sc = r[3]
    ok = is_match(r)
    if ok and abs(sc - 1) < 0.01:
        ok = r[4] >= WATCH_SAME_SIZE_MIN - 0.03 and r[5] >= WATCH_SAME_SIZE_MIN
    if ok:
        chroma, light = color_difference(t_rgb, s_rgb, r[1], r[2], sc)
        if chroma > WATCH_COLOR_MAX or light > WATCH_LIGHT_MAX:
            ok = False
            score = min(score, 0.5)
    return ok, round(r[1] + vx), round(r[2] + vy), score, sc


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


def describe_watch(j):
    what = ("When picture appears" if j.get("watch_trigger") == "appears"
            else "If picture gone")
    area = " · area" if j.get("watch_area") else ""
    return f"{what} · every {fmt_compact(j.get('watch_interval_s', 30))}{area}"


def target_text(j):
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
for _n in ("asksaveasfilename", "askopenfilename"):
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
    **{f"f{i}": 0x6F + i for i in range(1, 13)},
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
        elif len(p) == 1 and (p.isalpha() or p.isdigit()):
            keys.append(ord(p.upper()))
        else:
            raise ValueError(f"unknown key “{part}”")
    if not keys:
        raise ValueError("no key given")
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


def send_alert(settings, text):
    """Send text to the configured services. Returns a list of (service, ok, message)."""
    import urllib.request
    import urllib.parse
    results = []
    msg = f"{APP_NAME}: {text}"
    url = (settings.get("alert_discord") or "").strip()
    if url:
        try:
            req = urllib.request.Request(url, data=json.dumps({"content": msg[:1900]}).encode(),
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": f"{APP_NAME}/{VERSION}"})
            urllib.request.urlopen(req, timeout=12).read()
            results.append(("Discord", True, "sent"))
        except Exception as e:
            results.append(("Discord", False, str(e)[:200]))
    tok = (settings.get("alert_tg_token") or "").strip()
    chat = (settings.get("alert_tg_chat") or "").strip()
    if tok and chat:
        try:
            q = urllib.parse.urlencode({"chat_id": chat, "text": msg[:3900]})
            urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage?{q}",
                                   timeout=12).read()
            results.append(("Telegram", True, "sent"))
        except Exception as e:
            results.append(("Telegram", False, str(e)[:200]))
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


def make_backup(jobs, settings, tag="auto"):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    skip = set(RUNTIME_KEYS) | {"last_result", "last_run"}
    data = {"app": APP_ID, "version": VERSION, "kind": "backup", "tag": tag,
            "created": datetime.now().isoformat(timespec="seconds"),
            "jobs": [{k: v for k, v in j.items() if k not in skip} for j in jobs],
            "settings": {k: v for k, v in settings.items()
                         if k not in ("main_geom", "tests_geom", "dlg_geom")}}
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
    "tests_geom": "",
    "tests_split": 0.0,
    "tests_hist_filter": "job",
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
             warn="#b45309", good="#15803d", bad="#c62828", test="#7c3aed", grid="#e2e5ea")
DARK = dict(bg="#18191c", panel="#212226", panel_alt="#26282c", head="#1c1d21",
            fg="#e8e9ec", muted="#9097a1", border="#30333a", btn="#2a2c31",
            btn_border="#363940", btn_active="#34373d", accent="#3b82f6",
            accent_active="#2f6fe0", sel="#24406e", sel_fg="#ffffff", field="#26282c",
            warn="#f5a524", good="#4ade80", bad="#f87171", test="#c4a8ff", grid="#383b43")


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
        self.root = root
        self.lock = threading.RLock()
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
        self.settings, self.jobs, migrated = self.load()
        install_id = read_install_id()
        if install_id and self.settings.get("install_id") != install_id:
            # freshly installed / reinstalled: offer a clean start if jobs are left over
            if self.jobs and not asked_import:
                root.withdraw()
                keep = messagebox.askyesno(
                    APP_NAME, f"Clickue was just installed and found {len(self.jobs)} job(s) "
                              f"from before on this computer.\n\nKeep them?\n\n"
                              f"Yes = keep my jobs and settings\n"
                              f"No = start fresh (your old jobs are saved in a backup first, "
                              f"so you can bring them back from \u2630 Menu \u2192 Backups)",
                    parent=root)
                if not keep:
                    try:
                        make_backup(self.jobs, self.settings, "before-fresh-start")
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
            try:
                os.replace(OLD_CONFIG, OLD_CONFIG + ".migrated")
            except Exception:
                pass
            self.log("Moved your jobs and settings from the old config file into the data folder.")
        if self.settings.get("paused"):
            self.log("All jobs are PAUSED (use Resume all).")

        self.refresh_tree(full=True)
        self.update_buttons()
        root.after(150, self.restore_split)
        self.paned.bind("<ButtonRelease-1>", lambda e: self.root.after(50, self.remember_split))
        self.undo_stack = []
        self.hk_thread = None
        self.start_hotkeys()
        threading.Thread(target=trim_history, daemon=True).start()
        self.root.after(3000, self.backup_check)
        self.start_tray()
        threading.Thread(target=self.scheduler_loop, daemon=True).start()
        root.after(500, self.ui_tick)
        root.after(200, self.poll_cmds)
        if self.settings.get("start_minimized") or "--minimized" in sys.argv:
            root.after(300, self.hide_window)

    # ------------------------------------------------------------ persistence
    def load(self):
        settings, jobs, migrated = dict(DEFAULT_SETTINGS), [], False
        s_data, j_data = read_json(SETTINGS_PATH), read_json(JOBS_PATH)
        if s_data is None and j_data is None and os.path.exists(OLD_CONFIG):
            old = read_json(OLD_CONFIG) or {}
            s_data, j_data, migrated = old.get("settings", {}), {"jobs": old.get("jobs", [])}, True
        if isinstance(s_data, dict):
            settings.update({k: v for k, v in s_data.items() if k in DEFAULT_SETTINGS})
        for j in (j_data or {}).get("jobs", []):
            base = new_job()
            base.update(j)
            jobs.append(base)
        return settings, jobs, migrated

    def save(self):
        if self.uninstalled:
            return
        with self.lock:
            try:
                write_json(SETTINGS_PATH, self.settings)
                write_json(JOBS_PATH, {"app": APP_ID, "version": VERSION, "jobs": self.jobs})
            except Exception as e:
                self.log(f"Could not save: {e}")

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

    def log(self, msg):
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
                    if kind == "wtest":
                        self.watch_test(j)
                    elif kind == "watchcheck":
                        self.watch_check(j)
                    elif kind == "watchclick":
                        self.watch_click(j)
                    else:
                        self.execute(j, kind)
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

    def watch_check(self, job):
        """Look for the watched picture once and decide whether to click."""
        now = time.time()
        with self.lock:
            if not self.find_job(job) or not job.get("enabled"):
                return
            name, png = job["name"], job.get("watch_png")
            interval = max(1, int(job.get("watch_interval_s", 30)))
            job["next_check"] = now + interval
            job["last_check"] = now
            hint = job.get("watch_scale")
        if not png:
            with self.lock:
                job["watch_state"], job["watch_note"] = "unknown", "no picture saved"
            return
        if not HAVE_CV:
            with self.lock:
                job["watch_state"], job["watch_note"] = "unknown", "picture matching not installed"
            return
        if not screen_available():
            with self.lock:
                job["watch_state"], job["watch_note"] = "unknown", "screen locked"
            return
        try:
            found, x, y, score, sc = picture_on_screen(png, hint, area=job_area(job))
        except Exception as e:
            with self.lock:
                job["watch_state"], job["watch_note"] = "unknown", f"couldn't look ({e})"
            self.log(f"[{name}] couldn't check the screen: {e}")
            return

        with self.lock:
            if not self.find_job(job) or not job.get("enabled"):
                return
            appears = job.get("watch_trigger") == "appears"
            if found:
                job.update(last_seen=now, watch_scale=sc, found_xy=[x, y])
            if not found and self.own_visible and not appears:
                # This app's own window might be covering the picture - don't count it
                job["watch_state"], job["watch_note"] = "unknown", "Clickue window open"
                return
            hit = found if appears else not found
            if not hit:
                # the condition isn't met: reset, and allow the next click
                prev = job.get("watch_state")
                if found and prev == "missing":
                    self.log(f"[{name}] picture is back ({score:.0%})")
                elif not found and prev == "seen" and appears:
                    self.log(f"[{name}] picture went away")
                job.update(miss_count=0, armed=True, once_logged=False,
                           watch_state="seen" if found else "missing",
                           watch_note=(f"seen {score:.0%}" if found
                                       else f"not showing (best {score:.0%})"))
                return
            job["miss_count"] = int(job.get("miss_count", 0)) + 1
            job["watch_state"] = "seen" if found else "missing"
            need = max(1, int(job.get("watch_confirm", 2)))
            what = "showing" if appears else "missing"
            job["watch_note"] = (f"{what} ({job['miss_count']} of {need} checks)"
                                 if job["miss_count"] < need else what)
            if job["miss_count"] == 1:
                if appears:
                    self.log(f"[{name}] picture appeared ({score:.0%}) - "
                             + ("confirming" if need > 1 else "clicking"))
                else:
                    self.log(f"[{name}] picture not found (best {score:.0%}) - "
                             + ("confirming" if need > 1 else "clicking"))
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
            job["pending_since"] = now
            job["armed"] = False
            self.log(f"[{name}] picture {'APPEARED' if appears else 'GONE'} - clicking in "
                     f"{fmt_dur(delay)}")
            self.save()

    def watcher_dry_run(self, job):
        """Look for the watched picture and the button, without clicking.
        Returns dict(picture=(found, x, y, score, scale) or None, button=(ok, x, y, msg, how),
        error=str)."""
        out = dict(picture=None, button=None, error="",
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
        try:
            out["picture"] = picture_on_screen(job["watch_png"], job.get("watch_scale"),
                                               area=job_area(job))
            if job.get("watch_trigger") == "appears" and job.get("watch_click_picture"):
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
        pic = (f"Picture found ({score:.0%}{size})" if found
               else f"Picture NOT on screen (best {score:.0%})")
        btn = (f"button found at ({bx}, {by}) by {bhow}" if bok
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
        if (not r["error"] and not r["picture"][0] and self.own_visible
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
                f, px, py, score, sc = picture_on_screen(snap["watch_png"], snap.get("watch_scale"),
                                                         area=job_area(snap))
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
        ok, msg, retry_in, x, y, how = self.perform(snap, check_idle=True, point=point)
        now = time.time()
        wkey = (job["id"], "watch")
        with self.lock:
            if not self.find_job(job):
                return
            if ok:
                self.wait_msgs.pop(wkey, None)
                job["count"] = int(job.get("count", 0)) + 1
                self.bump_stats("stats_clicks")
                job["last_run"] = now
                job["last_result"] = "Clicked " + stamp() + (" (picture appeared)" if appears
                                                             else " (picture gone)")
                job["pending_click_at"] = job["pending_since"] = None
                # already confirmed gone: if it's still gone after the wait, click again
                # straight away instead of re-confirming from scratch
                wait_s = (job.get("watch_cooldown_s", 30) if job.get("watch_cooldown_on", True)
                          else job.get("watch_interval_s", 30))
                job["next_check"] = now + max(1, int(wait_s))
                via = f" ({how})" if how else ""
                m = (f"[{name}] picture {'appeared' if appears else 'was gone'} - "
                     f"{job['button']} click at ({x}, {y}){via} - OK")
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
                self.bump_stats("stats_missed")
                m = f"[{name}] couldn't click within {retry_s // 60} min ({msg})."
                self.log(m)
                self.notify(m, "problem")
                self.history(name, "watcher", "failed", detail=msg)
            else:
                job["pending_click_at"] = now + retry_in
                job["last_result"] = "Click waiting: " + msg
                if self.wait_msgs.get(wkey) != msg:
                    self.log(f"[{name}] click waiting - {msg}. Retrying.")
                self.wait_msgs[wkey] = msg
            self.save()

    def perform(self, job, check_idle, point=None):
        """Click the job's spot (or `point`), then run its extra steps.
        Returns (ok, message, seconds-until-retry, x, y, how-it-was-found)."""
        if not screen_available():
            return False, "screen locked or session disconnected", 30, 0, 0, ""
        need = int(self.settings.get("idle_seconds", 0) or 0)
        if check_idle and need > 0 and idle_seconds() < need:
            return False, "you were using the mouse/keyboard", 5, 0, 0, ""
        if point:
            x, y, how = int(point[0]), int(point[1]), "the picture itself"
        else:
            ok, x, y, msg, how = locate_spot(job, activate=True)
            if not ok:
                return False, msg, 30, x, y, how
        ok, msg = do_click(x, y, job["button"], job["clicks"], self.settings["restore_cursor"])
        if ok and job.get("steps"):
            sok, smsg = self.run_steps(job)
            msg = smsg
            if not sok:
                self.log(f"[{job['name']}] extra steps stopped: {smsg}")
                self.notify(f"{job['name']}: extra steps stopped ({smsg})", "problem")
        return ok, msg, 30, x, y, how

    def run_steps(self, job):
        """Run a job's extra steps in order. Returns (ok, message)."""
        steps = job.get("steps") or []
        for i, st in enumerate(steps, 1):
            if self.stop.is_set():
                return False, "Clickue is closing"
            time.sleep(0.15)
            t = st.get("type")
            if t == "waitpic":
                ok, msg = self.wait_for_picture(st)
                if ok:
                    self.log(f"[{job['name']}] step {i}: picture {msg}")
                    continue
                if msg.startswith("timeout") and st.get("on_timeout") == "continue":
                    self.log(f"[{job['name']}] step {i}: {msg} - continuing")
                    continue
                return False, f"step {i}: {msg}"
            if t == "wait":
                lo, hi = int(st.get("min", 1)), int(st.get("max", st.get("min", 1)))
                secs = random.randint(min(lo, hi), max(lo, hi)) if hi != lo else lo
                end = time.time() + secs
                while time.time() < end and not self.stop.is_set():
                    time.sleep(0.2)
                continue
            if not screen_available():
                return False, f"step {i}: screen locked or session disconnected"
            if t == "click":
                ok, x, y, msg, how = locate_spot(st, activate=False)
                if not ok:
                    return False, f"step {i} (click): {msg}"
                ok, msg = do_click(x, y, st.get("button", "left"), int(st.get("clicks", 1)),
                                   self.settings["restore_cursor"])
            elif t == "type":
                ok, msg = send_text(st.get("text", ""))
            elif t == "key":
                ok, msg = press_keys(st.get("keys", ""))
            else:
                ok, msg = False, f"unknown step type {t}"
            if not ok:
                return False, f"step {i}: {msg}"
        return True, f"clicked + {len(steps)} extra step{'s' if len(steps) != 1 else ''}"

    def wait_for_picture(self, st):
        """A chain step: wait until a picture appears (optionally click it) or disappears.
        Returns (ok, message); a message starting with "timeout" means it didn't happen in time."""
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
                    found, x, y, score, sc = picture_on_screen(st["png"], hint)
                except Exception as e:
                    return False, f"couldn't look at the screen ({e})"
                if found:
                    hint = sc
                if found == appear:
                    if appear and st.get("click_it"):
                        ok, m = do_click(x, y, st.get("button", "left"), int(st.get("clicks", 1)),
                                         self.settings["restore_cursor"])
                        if not ok:
                            return False, f"couldn't click it ({m})"
                        return True, f"appeared ({score:.0%}) and was clicked at ({x}, {y})"
                    return True, f"appeared ({score:.0%})" if appear else "went away"
            if time.time() >= end:
                return False, (f"timeout - the picture didn't {'appear' if appear else 'go away'}"
                               f" within {fmt_dur(limit)}")
            nxt = time.time() + STEP_POLL_S
            while time.time() < nxt and not self.stop.is_set():
                time.sleep(min(0.2, STEP_POLL_S))
        return False, "Clickue is closing"

    def draw_capture(self, parent, prompt, on_done):
        """Freeze the screen, let the user drag a box, call on_done(picture) (PIL image).
        The whole app hides meanwhile."""
        if not (HAVE_PIL and HAVE_CV) or getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def start():
            try:
                shot, (vx, vy) = grab_screen(move_cursor=False)
            except Exception as e:
                restore()
                messagebox.showerror(APP_NAME, f"Couldn't capture the screen:\n{e}",
                                     parent=parent or self.root)
                return
            W, H = shot.size
            dim = Image.blend(shot, Image.new("RGB", shot.size, (0, 0, 0)), 0.5)
            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)
            ov.attributes("-topmost", True)
            ov.geometry(f"{W}x{H}+{vx}+{vy}")
            cv = tk.Canvas(ov, width=W, height=H, highlightthickness=0, bd=0,
                           cursor="crosshair", bg="#000000")
            cv.pack()
            imgs = [ImageTk.PhotoImage(dim)]
            cv.create_image(0, 0, image=imgs[0], anchor="nw")
            bright = cv.create_image(0, 0, anchor="nw")
            rect = cv.create_rectangle(0, 0, 0, 0, outline="#3b82f6", width=2)
            tw = cv.create_text(W // 2, 34, text=prompt + "   ·   Esc to cancel", fill="#ffffff",
                                font=(self.font_family, 13, "bold"))
            bx = cv.bbox(tw)
            bg = cv.create_rectangle(bx[0] - 18, bx[1] - 10, bx[2] + 18, bx[3] + 10,
                                     fill="#1f2937", outline="#3b82f6")
            cv.tag_raise(tw, bg)
            if IS_WIN:
                try:
                    ov.update_idletasks()
                    hwnd = user32.GetParent(ov.winfo_id()) or ov.winfo_id()
                    user32.SetWindowPos(hwnd, wt.HWND(-1), vx, vy, W, H, 0x0040)
                except Exception:
                    pass
            st = {"x0": None, "y0": None}

            def box(e):
                return (max(0, min(st["x0"], e.x)), max(0, min(st["y0"], e.y)),
                        min(W, max(st["x0"], e.x)), min(H, max(st["y0"], e.y)))

            def down(e):
                st["x0"], st["y0"] = e.x, e.y
                cv.itemconfigure(bg, state="hidden")
                cv.itemconfigure(tw, state="hidden")

            def move(e):
                if st["x0"] is None:
                    return
                b = box(e)
                cv.coords(rect, *b)
                if b[2] - b[0] > 2 and b[3] - b[1] > 2:
                    ph = ImageTk.PhotoImage(shot.crop(b))
                    imgs[1:] = [ph]
                    cv.itemconfigure(bright, image=ph)
                    cv.coords(bright, b[0], b[1])

            def up(e):
                if st["x0"] is None:
                    return
                b = box(e)
                st["x0"] = None
                if b[2] - b[0] < 16 or b[3] - b[1] < 16:
                    cv.itemconfigure(bg, state="normal")
                    cv.itemconfigure(tw, state="normal", text="Too small (at least 16 × 16) - "
                                                              "drag again, or Esc to cancel")
                    return
                crop = shot.crop(b)
                ov.destroy()
                restore()
                on_done(crop)

            def cancel(e=None):
                ov.destroy()
                restore()

            cv.bind("<ButtonPress-1>", down)
            cv.bind("<B1-Motion>", move)
            cv.bind("<ButtonRelease-1>", up)
            cv.bind("<Button-3>", cancel)
            ov.bind("<Escape>", cancel)
            ov.focus_force()
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
                    job["last_result"] = "OK " + stamp() + (" · " + how if "picture" in how else "")
                    self.log(f"[{name}] {button} click at ({x}, {y}){via} - OK")
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
                if self.wait_msgs.get(wkey) != msg:
                    self.log(f"[{name}] {'test ' if kind == 'test' else ''}click waiting - {msg}."
                             f" Retrying until {fmt_time(job[dl_key])}.")
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
        self.cards_btn = ttk.Button(hdr, text="", command=self.toggle_cards)
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
        for i, (key, title) in enumerate((("next", "NEXT CLICK"), ("active", "ACTIVE JOBS"),
                                          ("today", "CLICKS TODAY"), ("screen", "SCREEN"))):
            c = ttk.Frame(cards, style="Card.TFrame", padding=(14, 10))
            self.card_frames.append(c)
            ttk.Label(c, text=title, style="CardTitle.TLabel").pack(anchor="w")
            v = ttk.Label(c, text="—", style="CardValue.TLabel")
            v.pack(anchor="w", pady=(2, 0))
            sub = ttk.Label(c, text="", style="CardSub.TLabel")
            sub.pack(anchor="w")
            self.card_vals[key] = (v, sub)
        cards.bind("<Configure>", lambda e: self.layout_cards())
        if not self.settings.get("show_cards", True):
            cards.pack_forget()
        self.cards_btn.configure(text="▴  Summary" if self.settings.get("show_cards", True)
                                 else "▾  Summary")

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
        tool("👁  New watcher", self.add_watcher, 0, 95)
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

        # ---- job table
        self.undo_bar = ttk.Frame(main, style="Card.TFrame", padding=(10, 4))
        self.undo_lbl = ttk.Label(self.undo_bar, style="CardSub.TLabel")
        self.undo_lbl.pack(side="left")
        ttk.Button(self.undo_bar, text="↶  Undo", style="Small.TButton",
                   command=self.undo_delete).pack(side="left", padx=10)
        ttk.Button(self.undo_bar, text="✕", style="Small.TButton",
                   command=lambda: self.undo_bar.pack_forget()).pack(side="right")
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
        cols = ("status", "name", "pos", "button", "schedule", "next", "countdown", "count",
                "last")
        spec = (("Status", 105, 80, "w"), ("Name", 160, 90, "w"),
                ("Target", 170, 90, "w"), ("Click", 75, 55, "w"),
                ("Schedule", 190, 120, "w"), ("Next click", 160, 110, "w"),
                ("Starts in", 100, 75, "w"), ("Clicks", 65, 50, "center"),
                ("Last result", 190, 110, "w"))
        self.tree = ttk.Treeview(tf, columns=cols, show="headings", height=4,
                                 selectmode="browse")
        self.col_base = {c: w for c, (h, w, minw, anchor) in zip(cols, spec)}
        self._shown_cols = None
        for c, (h, w, minw, anchor) in zip(cols, spec):
            self.tree.heading(c, text=h, anchor=anchor)
            self.tree.column(c, width=w, minwidth=minw, stretch=True, anchor=anchor)
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
        self.tree.bind("<p>", lambda e: self.toggle_pause_job())

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
        self.act_tools = ttk.Frame(ah)
        self.act_tools.pack(side="right")
        ttk.Button(self.act_tools, text="Clear view", style="Small.TButton",
                   command=self.clear_activity).pack(side="right")
        ttk.Button(self.act_tools, text="Open log file", style="Small.TButton",
                   command=self.open_log).pack(side="right", padx=6)
        ah.bind("<Configure>", lambda e: self.act_tools.pack_forget() if e.width < 560
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

    def toggle_cards(self):
        show = not self.settings.get("show_cards", True)
        self.settings["show_cards"] = show
        if show:
            self.cards.pack(fill="x", pady=(12, 12), after=self.hdr)
        else:
            self.cards.pack_forget()
        self.cards_btn.configure(text="▴  Summary" if show else "▾  Summary")
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
        for i, c in enumerate(self.card_frames):
            r, col = divmod(i, ncols)
            c.grid(row=r, column=col, sticky="nsew",
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
        p = self.pal = DARK if dark else LIGHT
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
        s.map("TButton",
              background=[("disabled", p["bg"]), ("pressed", p["btn_active"]),
                          ("active", p["btn_active"])],
              foreground=[("disabled", p["muted"])],
              bordercolor=[("disabled", p["border"])],
              lightcolor=[("pressed", p["btn_active"]), ("active", p["btn_active"])],
              darkcolor=[("pressed", p["btn_active"]), ("active", p["btn_active"])])
        s.configure("Small.TButton", padding=(8, 2), font=(F, 9))
        s.configure("Accent.TButton", background=p["accent"], foreground="#ffffff",
                    bordercolor=p["accent"], lightcolor=p["accent"], darkcolor=p["accent"],
                    font=(F, 10, "bold"))
        s.map("Accent.TButton",
              background=[("pressed", p["accent_active"]), ("active", p["accent_active"])],
              lightcolor=[("active", p["accent_active"])],
              darkcolor=[("active", p["accent_active"])])
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
        s.configure("Sash", sashthickness=8, gripcount=0, background=p["bg"],
                    lightcolor=p["border"], darkcolor=p["border"], bordercolor=p["bg"])

        self.root.option_add("*TCombobox*Listbox.background", p["field"])
        self.root.option_add("*TCombobox*Listbox.foreground", p["fg"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", p["sel"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", p["sel_fg"])
        for menu in (self.ctx, self.more_menu, self.main_menu):
            menu.configure(bg=p["panel"], fg=p["fg"], activebackground=p["sel"],
                           activeforeground=p["sel_fg"], disabledforeground=p["muted"],
                           borderwidth=1, font=(F, 10))

        self.logbox.configure(bg=p["panel"], fg=p["fg"], insertbackground=p["fg"],
                              selectbackground=p["sel"], selectforeground=p["sel_fg"],
                              highlightthickness=0)
        self.logbox.tag_configure("ok", foreground=p["good"])
        self.logbox.tag_configure("bad", foreground=p["bad"])
        self.logbox.tag_configure("warn", foreground=p["warn"])
        self.logbox.tag_configure("test", foreground=p["test"])
        self.logbox.tag_configure("time", foreground=p["muted"])

        self.tree.tag_configure("even", background=p["panel"])
        self.tree.tag_configure("odd", background=p["panel_alt"])
        self.tree.tag_configure("running", foreground=p["fg"])
        self.tree.tag_configure("stopped", foreground=p["muted"])
        self.tree.tag_configure("paused", foreground=p["muted"])
        self.tree.tag_configure("warn", foreground=p["warn"])
        self.tree.tag_configure("bad", foreground=p["bad"])
        self.tree.tag_configure("test", foreground=p["test"])
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

    def theme_window(self, w):
        try:
            w.configure(bg=self.pal["bg"])
        except Exception:
            pass
        set_dark_titlebar(w, self.pal is DARK)

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
            return "👁  Watching", sched, f"Can't tell: {note}", cd, "paused"
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

    def build_rows(self, now):
        rows = []
        paused = self.settings.get("paused")
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
                rows.append((j["id"], (status, j["name"], pos, btn, sched, nxt, cd,
                                       j.get("count", 0), last), state))
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
            rows.append((j["id"], (status, j["name"], pos, btn, self.describe_schedule(j),
                                   nxt, cd, j.get("count", 0), last), state))
            if j.get("test_at"):
                rows.append(self.test_row(j, now, pos, btn))
        return rows

    def wtest_row(self, j, now, pos, btn):
        at = j["wtest_at"]
        waiting = j.get("wtest_deadline") and at > now and at - now <= 31
        cd = "retrying…" if waiting else fmt_dur(at - now)
        what = ("checks, clicks if missing" if j.get("wtest_click")
                else "checks only, no click")
        return ("wtest:" + j["id"], ("◆  Watch test", f"   ↳ {j['name']} (watch test)", pos,
                                     btn, "One time only", fmt_time(at), cd, "",
                                     f"Temporary — {what}"), "test")

    def test_row(self, j, now, pos, btn):
        tw = self.wait_msgs.get((j["id"], "test"))
        if tw:
            t_nxt = f"until {fmt_time(j.get('test_deadline'))}"
            t_cd, t_last = "retrying…", f"Waiting: {tw}"
        else:
            t_nxt, t_cd = fmt_time(j["test_at"]), fmt_dur(j["test_at"] - now)
            t_last = "Temporary — doesn't change the schedule"
        return ("test:" + j["id"], ("◆  Test", f"   ↳ {j['name']} (test)", pos, btn,
                                    "One time only", t_nxt, t_cd, "", t_last), "test")

    def refresh_tree(self, full=False):
        now = time.time()
        with self.lock:
            rows = self.build_rows(now)
        want = [r[0] for r in rows]
        for iid in self.tree.get_children():
            if full or iid not in want:
                self.tree.delete(iid)
        sel = set(self.tree.selection())
        for idx, (iid, vals, state) in enumerate(rows):
            vals = tuple(v if i == 7 else f"  {v}" for i, v in enumerate(vals))
            tags = [state]
            if iid not in sel:
                tags.insert(0, "odd" if idx % 2 else "even")
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
        self.draw_grid()

    def on_tree_resize(self):
        """Hide the least important columns when the table gets narrow."""
        W = self.tree.winfo_width()
        if W > 1:
            shown = list(self.tree["columns"])
            drop = ["count", "button", "schedule", "pos", "countdown"]
            while drop and sum(self.col_base[c] for c in shown) * 0.72 > W:
                shown.remove(drop.pop(0))
            if tuple(shown) != self._shown_cols:
                self._shown_cols = tuple(shown)
                self.tree["displaycolumns"] = shown
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
            self.grid_lines.append(f)
            self.grid_geom.append(None)
        for i, f in enumerate(self.grid_lines):
            g = lines[i] if i < len(lines) else None
            if g == self.grid_geom[i]:
                continue
            if g:
                f.place(x=g[0], y=g[1], width=g[2], height=g[3])
            else:
                f.place_forget()
            self.grid_geom[i] = g

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
        with self.lock:
            paused = self.settings.get("paused")
            total = len(self.jobs)
            enabled = [j for j in self.jobs
                       if j.get("enabled") and not j.get("paused")
                       and (j.get("next_run") or is_watch(j))]
            n_jpaused = sum(1 for j in self.jobs if j.get("enabled") and j.get("paused"))
            upcoming = [] if paused else [
                (j["next_run"], j["name"], False) for j in enabled if j.get("next_run")]
            upcoming += [] if paused else [
                (j["pending_click_at"], j["name"], False) for j in enabled
                if is_watch(j) and j.get("pending_click_at")]
            n_watch = sum(1 for j in enabled if is_watch(j))
            upcoming += [(j["test_at"], j["name"], True) for j in self.jobs if j.get("test_at")]
            upcoming += [(j["wtest_at"], j["name"], True) for j in self.jobs if j.get("wtest_at")]
            if self.settings.get("stats_date") == datetime.now().strftime("%Y-%m-%d"):
                today, missed = self.settings.get("stats_clicks", 0), \
                    self.settings.get("stats_missed", 0)
            else:
                today = missed = 0

        v, sub = self.card_vals["next"]
        if upcoming:
            t, name, is_test = min(upcoming)
            v.configure(text=fmt_dur(t - now) if t > now else "now",
                        style="CardValue.TLabel")
            sub.configure(text=f"{name}{' (test)' if is_test else ''} · {fmt_time(t)}")
        else:
            v.configure(text="—", style="CardValue.TLabel")
            sub.configure(text="All paused" if paused and enabled else
                          ("Watchers only click when their picture disappears" if enabled
                           else "Nothing scheduled"))

        v, sub = self.card_vals["active"]
        v.configure(text=f"{len(enabled)} of {total}",
                    style="CardWarn.TLabel" if paused else "CardValue.TLabel")
        sub.configure(text="All jobs paused" if paused else
                      (f"{len(enabled) - n_watch} scheduled · {n_watch} watching"
                       + (f" · {n_jpaused} paused" if n_jpaused else "") if enabled
                       else (f"{n_jpaused} paused" if n_jpaused else "none running")))

        v, sub = self.card_vals["today"]
        v.configure(text=str(today), style="CardValue.TLabel")
        sub.configure(text=f"{missed} missed" if missed else "no missed clicks")

        avail = screen_available()
        x, y = get_cursor()
        v, sub = self.card_vals["screen"]
        v.configure(text="Available" if avail else "Locked",
                    style="CardGood.TLabel" if avail else "CardBad.TLabel")
        sub.configure(text=f"Idle {fmt_dur(idle_seconds())} · Mouse {x}, {y}" if avail
                      else "Clicks will wait for the screen")

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
                self.logbox.insert("end", ts + "  ", ("time",))
                self.logbox.insert("end", msg + "\n", tag)
        if added:
            lines = int(self.logbox.index("end-1c").split(".")[0])
            if lines > MAX_UI_LOG_LINES:
                self.logbox.delete("1.0", f"{lines - MAX_UI_LOG_LINES}.0")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")

        now = time.time()
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
        self.status.configure(text=f"v{VERSION}   ·   {tray}   ·   Data: {DATA_DIR}   ·   "
                                   f"Shortcuts: Ctrl+N new · Enter edit · Space start/stop · P pause · "
                                   f"Ctrl+T test · Del delete")
        self.root.after(1000, self.ui_tick)

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
                frac = min(0.8, max(0.2, float(self.settings.get("split", 0.45))))
                self.paned.sashpos(0, int(h * frac))
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
        return f == "all" or (f == "clicks" and item[3]) or (f == "problems" and item[4])

    def render_activity(self):
        self.logbox.configure(state="normal")
        self.logbox.delete("1.0", "end")
        for item in self.act_lines:
            if self.activity_shows(item):
                self.logbox.insert("end", item[0] + "  ", ("time",))
                self.logbox.insert("end", item[1] + "\n", item[2])
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

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
            r = self.watcher_dry_run(job)
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

            if found:
                size = "" if not sc or abs(sc - 1) < 0.01 else f" at {sc:.0%} size"
                self.flash_marker(px, py, f"Step 1 of 2  ·  Watched picture found "
                                          f"({score:.0%}{size}) - no click needed",
                                  step_button, seconds=4)
            else:
                step_button()
        self.root.after(400, run)

    def filter_changed(self):
        self.settings["view_filter"] = self.v_filter.get()
        self.save()
        self.refresh_tree(full=True)
        self.update_buttons()

    def clear_activity(self):
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
        jid = iid.split(":", 1)[1] if ":" in iid else iid
        with self.lock:
            return next((j for j in self.jobs if j["id"] == jid), None)

    def on_double(self, event=None):
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
            m.add_separator()
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
    def make_icon(self):
        return make_logo(64)

    def start_tray(self):
        if not HAVE_TRAY:
            return
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Show window", lambda icon, item: self.cmdq.put("show"),
                                 default=True),
                pystray.MenuItem(
                    lambda item: "Resume all" if self.settings.get("paused") else "Pause all",
                    lambda icon, item: self.cmdq.put("pause")),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", lambda icon, item: self.cmdq.put("exit")))
            self.tray = pystray.Icon(APP_ID, self.icon_img, APP_NAME, menu)
            self.tray.run_detached()
        except Exception as e:
            self.tray = None
            self.log(f"Tray icon unavailable: {e}")

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
                make_backup(jobs, settings, "auto")
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
        path = make_backup(jobs, settings, tag)
        self.log(f"Backup saved: {os.path.basename(path)}")
        return path

    def restore_backup(self, path, replace=True):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.backup_now("before-restore")
        new = []
        for j in data.get("jobs", []):
            b = new_job()
            b.update({k: v for k, v in j.items() if k not in RUNTIME_KEYS})
            b["id"] = uuid.uuid4().hex
            for k in RUNTIME_KEYS:
                b[k] = new_job().get(k)
            new.append(b)
        with self.lock:
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
        self.log(f"Restored {len(new)} job(s) from {os.path.basename(path)}")
        return len(new)

    # ------------------------------------------------------------ undo delete
    def undo_delete(self, event=None):
        if not self.undo_stack:
            return
        job, idx, was_on = self.undo_stack.pop()
        with self.lock:
            self.jobs.insert(min(idx, len(self.jobs)), job)
            if was_on:
                self.start_job(job)
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
            job = self.undo_stack[-1][0]
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
            if cmd == "show":
                self.show_window()
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

    def quit_app(self):
        try:
            self.remember_geometry()
        except Exception:
            pass
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
    def bump_stats(self, key):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.settings.get("stats_date") != today:
            self.settings.update(stats_date=today, stats_clicks=0, stats_missed=0)
        self.settings[key] = int(self.settings.get(key, 0)) + 1

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
        return bool(sel) and ":" in sel[0]

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

    # ------------------------------------------------------------ ☰ menu
    def show_main_menu(self):
        m = self.main_menu
        m.delete(0, "end")
        m.add_command(label="New click…", accelerator="Ctrl+N", command=self.add_job)
        m.add_command(label="New watcher…", accelerator="Ctrl+Shift+N", command=self.add_watcher)
        m.add_command(label="Tests…", accelerator="Ctrl+T", command=self.open_tests)
        m.add_separator()
        m.add_command(label="Undo delete", accelerator="Ctrl+Z", command=self.undo_delete,
                      state="normal" if self.undo_stack else "disabled")
        m.add_command(label="Import jobs…", command=self.import_jobs)
        m.add_command(label="Export jobs…", command=self.export_jobs)
        m.add_command(label="Backups…", command=lambda: BackupsDialog(self))
        m.add_command(label="Export click history (CSV)…", command=self.export_history)
        m.add_separator()
        m.add_command(label="Preferences…", accelerator="Ctrl+,", command=self.open_settings)
        m.add_command(label="Open data folder", command=self.open_data_folder)
        m.add_command(label="Open log file", command=self.open_log)
        m.add_separator()
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

    def pick_point(self, parent, on_done):
        """Countdown, then capture the mouse position and a picture around it.
        Calls on_done(x, y, snap_png, snap_spot). The whole app hides meanwhile."""
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)
        cd = tk.Toplevel(self.root, bg="#1f2937", highlightthickness=1,
                         highlightbackground="#3b82f6", highlightcolor="#3b82f6")
        cd.overrideredirect(True)
        cd.attributes("-topmost", True)
        lbl = tk.Label(cd, font=(self.font_family, 13, "bold"), bg="#1f2937", fg="#ffffff",
                       padx=20, pady=10, justify="left", anchor="w", cursor="fleur", bd=0)
        lbl.pack(fill="x")
        tip = tk.Label(cd, font=(self.font_family, 9), bg="#1f2937", fg="#9ca3af", padx=20,
                       justify="left", anchor="w", cursor="fleur", bd=0,
                       text="Drag this box to move it (the countdown waits while you drag).\n"
                            "It also moves out of the way when your mouse comes near.")
        tip.pack(fill="x", pady=(0, 10))
        st = {"drag": None, "moved": False, "done": False}
        vx, vy, vw, vh = virtual_screen()
        cd.geometry(f"+{vx + 20}+{vy + 20}")

        def press(e):
            st["drag"] = (e.x_root - cd.winfo_rootx(), e.y_root - cd.winfo_rooty())

        def motion(e):
            if st["drag"]:
                cd.geometry(f"+{e.x_root - st['drag'][0]}+{e.y_root - st['drag'][1]}")

        def release(e):
            st["drag"], st["moved"] = None, True

        for wdg in (lbl, tip):
            wdg.bind("<ButtonPress-1>", press)
            wdg.bind("<B1-Motion>", motion)
            wdg.bind("<ButtonRelease-1>", release)

        def dodge():
            if st["done"]:
                return
            if not st["drag"] and not st["moved"]:
                try:
                    mx, my = get_cursor()
                    bx, by, bw, bh = cd.winfo_rootx(), cd.winfo_rooty(), cd.winfo_width(), \
                        cd.winfo_height()
                    if bx - 60 <= mx <= bx + bw + 60 and by - 60 <= my <= by + bh + 60:
                        corners = [(vx + 20, vy + 20), (vx + vw - bw - 20, vy + 20),
                                   (vx + 20, vy + vh - bh - 60),
                                   (vx + vw - bw - 20, vy + vh - bh - 60)]
                        c = max(corners, key=lambda c: (c[0] + bw / 2 - mx) ** 2 +
                                (c[1] + bh / 2 - my) ** 2)
                        cd.geometry(f"+{int(c[0])}+{int(c[1])}")
                except Exception:
                    pass
            cd.after(80, dodge)
        dodge()

        def step(n):
            if st["drag"]:
                cd.after(200, step, n)
                return
            if n > 0:
                x, y = get_cursor()
                lbl.configure(text=f"Point at the spot to click…\nCapturing in {n}    ({x}, {y})")
                cd.after(1000, step, n - 1)
                return
            x, y = get_cursor()
            st["done"] = True
            cd.destroy()
            self.root.after(250, lambda: finish(x, y))

        def finish(x, y):
            snap_png, spot = "", None
            if HAVE_CV:
                try:
                    snap, spot, _ = capture_snapshot(x, y, "Medium")
                    snap_png, spot = img_to_b64(snap), list(spot)
                except Exception:
                    pass
            restore()
            on_done(x, y, snap_png, spot)
        step(5)

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

    def hide_app(self, parent=None):
        """Hide every visible window of this app (so it's out of the way while testing).
        Returns a function that brings them back the way they were."""
        wins = []
        for w in (parent, self.tests_win, self.root):
            try:
                if w is not None and w not in wins and w.winfo_exists() and w.winfo_viewable():
                    wins.append(w)
            except Exception:
                pass
        for w in wins:
            w.withdraw()

        def restore():
            for w in reversed(wins):
                try:
                    if w is self.root:
                        self.restore_main()
                    else:
                        w.deiconify()
                except Exception:
                    pass
            top = parent if parent is not None else self.tests_win
            if top is not None:
                try:
                    top.lift()
                    top.focus_force()
                except Exception:
                    pass
            # let focus settle before popups may close on "click outside" again
            self.root.after(600, lambda: setattr(self, "_spot_busy", False))
        return restore

    def show_spot_for(self, job, parent=None):
        """Hide this app, find the spot, mark it for a few seconds, then come back."""
        activate = job.get("target_mode") == "window" and job.get("bring_to_front", True)
        owner = parent or self.root
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def run():
            try:
                res = locate_spot(job, activate=activate, check_cover=False)
            except Exception as e:
                res = (False, 0, 0, f"error while looking ({e})", "")
            ok, x, y, msg, how = res
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
            self.flash_marker(x, y, f"{job['name']}  ·  found by {how}", done)
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
            try:
                found, x, y, score, sc = picture_on_screen(job["watch_png"],
                                                           job.get("watch_scale"),
                                                           area=job_area(job))
            except Exception as e:
                restore()
                messagebox.showerror(APP_NAME, f"Couldn't check the screen:\n{e}", parent=owner)
                return
            if not found:
                restore()
                self.log(f"[{job['name']}] check: watched picture NOT on screen "
                         f"(best {score:.0%})")
                appears = job.get("watch_trigger") == "appears"
                where = "in its search area" if job.get("watch_area") else "on the screen"
                self.record_test(job["name"], "Check picture now",
                                 f"Picture NOT {where} (best {score:.0%}) - the watcher "
                                 f"would {'not ' if appears else ''}click",
                                 "ok" if appears else "warn")
                messagebox.showwarning(
                    APP_NAME, f"The watched picture is NOT {where} right now "
                              f"(best match {score:.0%}).\n\nIf this watcher were running, it "
                              f"would {'NOT click (it waits for the picture to appear)' if appears else 'click'}.",
                    parent=owner)
                return
            size = "" if not sc or abs(sc - 1) < 0.01 else f" at {sc:.0%} size"
            self.log(f"[{job['name']}] check: watched picture found at ({x}, {y}), "
                     f"{score:.0%}{size}")
            self.record_test(job["name"], "Check picture now",
                             f"Picture found at ({x}, {y}), {score:.0%}{size}", "ok")
            self.flash_marker(x, y, f"{job['name']}  ·  watched picture found "
                                    f"({score:.0%}{size})", restore)
        self.root.after(400, run)

    def flash_marker(self, x, y, caption="", on_done=None, seconds=5):
        """Red crosshair on (x, y) plus a small caption bar. Click either one, or press
        Esc, to close early."""
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
        if caption:
            cap = tk.Toplevel(self.root, bg="#111827")
            wins.append(cap)
            cap.overrideredirect(True)
            cap.attributes("-topmost", True)
            lbl = tk.Label(cap, bg="#111827", fg="#ffffff", padx=12, pady=6,
                           font=(self.font_family, 10), justify="left")
            lbl.pack()
            lbl.bind("<Button-1>", close)

            def cap_text():
                return f"{caption}\nClick here or press Esc to close  ({left[0]}s)"
            lbl.configure(text=cap_text())
            cap.update_idletasks()
            cw, chh = cap.winfo_reqwidth(), cap.winfo_reqheight()
            sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            cx = min(max(0, x - cw // 2), max(0, sw - cw))
            cy = y + size // 2 + 8
            if cy + chh > sh - 40:
                cy = y - size // 2 - 8 - chh
            cap.geometry(f"+{cx}+{cy}")
            place_exact(cap, cx, cy)
        for w in wins:
            w.bind("<Escape>", close)
        try:
            m.focus_force()
        except Exception:
            pass

        def tick(n=0):
            if finished:
                return
            if n and n % 3 == 0:
                left[0] -= 1
                if caption:
                    try:
                        lbl.configure(text=cap_text())
                    except Exception:
                        pass
            if left[0] <= 0:
                close()
                return
            try:
                c.itemconfigure(ring, width=3 if n % 2 == 0 else 5)
            except Exception:
                return
            m.after(333, tick, n + 1)
        tick()

    def test_click(self, job=None, parent=None):
        j = job or self.selected_job()
        if not j:
            return
        owner = parent or self.root
        if not messagebox.askyesno(
                APP_NAME, f"The app will hide and '{j['name']}' will click once at "
                          f"{target_text(j)}.\nThe schedule is not changed. Continue?",
                parent=owner):
            return
        if getattr(self, "_spot_busy", False):
            return
        self._spot_busy = True
        restore = self.hide_app(parent)

        def go():
            th = threading.Thread(target=self.execute, args=(j, "manual"), daemon=True)
            th.start()

            def wait():
                if th.is_alive():
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
    def export_to(self, path):
        with self.lock:
            skip = set(RUNTIME_KEYS) | {"last_result", "last_run", "count"}
            jobs = [{k: v for k, v in j.items() if k not in skip} for j in self.jobs]
        write_json(path, {"app": APP_ID, "version": VERSION,
                          "exported": datetime.now().isoformat(timespec="seconds"),
                          "jobs": jobs})

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
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("jobs") if isinstance(data, dict) else data
            raw = [j for j in (raw or []) if isinstance(j, dict) and "x" in j and "y" in j]
            if not raw:
                raise ValueError("no jobs found in that file")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not import:\n{e}", parent=self.root)
            return
        with self.lock:
            have = len(self.jobs)
        choice = True
        if have:
            choice = messagebox.askyesnocancel(
                APP_NAME, f"Found {len(raw)} job(s) in the file.\n\n"
                          f"Yes  =  add them to your {have} current job(s)\n"
                          f"No   =  replace your current jobs\n"
                          f"Cancel  =  do nothing", parent=self.root)
            if choice is None:
                return
        new = []
        for j in raw:
            b = new_job()
            b.update({k: v for k, v in j.items() if k not in RUNTIME_KEYS})
            b.update(id=uuid.uuid4().hex, count=0, last_run=None, last_result="Imported")
            for k in RUNTIME_KEYS:
                b[k] = None
            new.append(b)
        with self.lock:
            if choice is False:
                self.jobs = new
            else:
                self.jobs.extend(new)
            for b in new:
                if b.get("enabled"):
                    self.schedule_first(b)
        self.log(f"Imported {len(new)} job(s) from {path}")
        self.save()
        self.refresh_tree(full=True)

    # ------------------------------------------------------------ uninstall
    def uninstall(self, parent):
        items = ("• all scheduled clicks (they stop now)\n• your settings and jobs\n"
                 "• the log files\n• the start-with-Windows entry")
        if FROZEN:
            items += "\n• Clickue.exe itself"
        if not messagebox.askyesno(APP_NAME, f"Uninstall {APP_NAME}?\n\nThis removes:\n{items}",
                                   icon="warning", parent=parent):
            return
        backup_path = None
        with self.lock:
            has_jobs = bool(self.jobs)
        if has_jobs and messagebox.askyesno(
                APP_NAME, "Save a backup copy of your jobs to your Documents folder first?\n"
                          "(You can load it later with Import…)", parent=parent):
            try:
                docs = os.path.join(os.path.expanduser("~"), "Documents")
                backup_path = os.path.join(
                    docs, f"Clickue jobs backup {datetime.now():%Y-%m-%d %H%M}.json")
                self.export_to(backup_path)
            except Exception as e:
                if not messagebox.askyesno(APP_NAME, f"Backup failed:\n{e}\n\nUninstall anyway?",
                                           parent=parent):
                    return
                backup_path = None

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
        shutil.rmtree(DATA_DIR, ignore_errors=True)

        msg = f"{APP_NAME} has been uninstalled."
        if backup_path:
            msg += f"\n\nYour jobs were saved to:\n{backup_path}"
        if FROZEN and IS_WIN:
            try:
                subprocess.Popen(
                    f'cmd /c ping 127.0.0.1 -n 4 > nul & del /f /q "{sys.executable}"',
                    creationflags=0x08000000)  # CREATE_NO_WINDOW
                msg += "\n\nClickue.exe will delete itself in a few seconds."
            except Exception:
                msg += f"\n\nPlease delete this file yourself:\n{sys.executable}"
        else:
            msg += f"\n\nTo finish, delete the program folder:\n{PROGRAM_DIR}"
        messagebox.showinfo(APP_NAME, msg, parent=parent)
        self.root.destroy()


# ---------------------------------------------------------------- dialogs
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


class JobEditor(Dialog):
    def __init__(self, app, job, is_new):
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
        g2.pack(fill="x", pady=(12, 0))
        self.v_button = tk.StringVar(value=job["button"])
        ttk.Combobox(g2, values=("left", "right", "middle"), state="readonly", width=8,
                     textvariable=self.v_button).pack(side="left")
        self.v_clicks = tk.StringVar(value="double" if job["clicks"] == 2 else "single")
        ttk.Combobox(g2, values=("single", "double"), state="readonly", width=8,
                     textvariable=self.v_clicks).pack(side="left", padx=6)

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

        self.v_enabled = tk.BooleanVar(value=job.get("enabled", False) or is_new)
        ttk.Checkbutton(f, text="Start watching when I save" if self.kind == "watch"
                        else "Start this schedule when I save",
                        variable=self.v_enabled).pack(anchor="w", pady=(10, 0))

        b = self.footer
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Save", style="Accent.TButton", command=self.on_save).pack(
            side="right", padx=6)

        self.mode_changed()
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
            side="left", padx=6)
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

    # ---- extra steps
    def build_steps_section(self, f, job):
        g = ttk.LabelFrame(f, text="More steps after the click (optional)", padding=(12, 8))
        g.pack(fill="x", pady=(12, 0))
        ttk.Label(g, style="Muted.TLabel", wraplength=560, justify="left", text=(
            "Run right after the main click, in order: click other spots, wait, wait for a "
            "picture to appear or go away (and click it), type text or press keys. Chain them "
            "to react to each click's result, e.g. click Refresh, wait for Export to appear, "
            "click it, wait for Save, click it.")).pack(anchor="w")
        tf = ttk.Frame(g, style="Card.TFrame", padding=1)
        tf.pack(fill="x", pady=(6, 6))
        self.steps_tree = ttk.Treeview(tf, columns=("n", "what", "detail"), show="headings",
                                       height=4, selectmode="browse")
        for c, h, w, st in (("n", "#", 40, False), ("what", "Step", 120, False),
                            ("detail", "Details", 360, True)):
            self.steps_tree.heading(c, text=h, anchor="w")
            self.steps_tree.column(c, width=w, minwidth=30, stretch=st, anchor="w")
        self.steps_tree.pack(fill="x")
        self.steps_tree.bind("<Double-1>", lambda e: self.edit_step())
        br = ttk.Frame(g)
        br.pack(fill="x")
        for text, kind in (("+ Click", "click"), ("+ Wait", "wait"),
                           ("+ Wait for picture", "waitpic"), ("+ Type", "type"),
                           ("+ Keys", "key")):
            ttk.Button(br, text=text, style="Small.TButton",
                       command=lambda k=kind: StepDialog(self.app, self, {"type": k})).pack(
                side="left", padx=(0, 4))
        for text, cmd in (("▼", lambda: self.move_step(1)), ("▲", lambda: self.move_step(-1)),
                          ("Remove", self.remove_step), ("Edit", self.edit_step)):
            ttk.Button(br, text=text, style="Small.TButton", command=cmd).pack(side="right",
                                                                              padx=(4, 0))

    @staticmethod
    def describe_step(st):
        t = st.get("type")
        if t == "click":
            how = "by picture" if st.get("use_image") and st.get("snap_png") else "fixed spot"
            return ("Click", f"{st.get('button', 'left')} {'double ' if st.get('clicks') == 2 else ''}"
                             f"click at ({st.get('x')}, {st.get('y')}), {how}")
        if t == "wait":
            lo, hi = st.get("min", 1), st.get("max", st.get("min", 1))
            return "Wait", (f"{fmt_dur(lo)}" if lo == hi else f"{fmt_dur(lo)} to {fmt_dur(hi)} (random)")
        if t == "type":
            txt = st.get("text", "")
            return "Type text", (txt[:60] + "…") if len(txt) > 60 else txt.replace("\n", " ⏎ ")
        if t == "key":
            return "Press keys", st.get("keys", "")
        if t == "waitpic":
            what = ("until it appears, then click it" if st.get("until", "appears") == "appears"
                    and st.get("click_it") else
                    "until it appears" if st.get("until", "appears") == "appears"
                    else "until it goes away")
            then = "stop the chain" if st.get("on_timeout", "stop") == "stop" else "continue"
            return "Wait for picture", (f"{what} · up to {fmt_dur(int(st.get('timeout', 60)))}, "
                                        f"then {then}")
        return t, ""

    def refresh_steps(self):
        tr = self.steps_tree
        tr.delete(*tr.get_children())
        for i, st in enumerate(self.steps):
            what, det = self.describe_step(st)
            tr.insert("", "end", iid=str(i), values=(i + 1, what, det))

    def selected_step(self):
        sel = self.steps_tree.selection()
        return int(sel[0]) if sel else None

    def step_saved(self, step, index=None):
        if index is None:
            self.steps.append(step)
            index = len(self.steps) - 1
        else:
            self.steps[index] = step
        self.refresh_steps()
        self.steps_tree.selection_set(str(index))

    def edit_step(self):
        i = self.selected_step()
        if i is not None:
            StepDialog(self.app, self, copy.deepcopy(self.steps[i]), i)

    def remove_step(self):
        i = self.selected_step()
        if i is not None:
            del self.steps[i]
            self.refresh_steps()

    def move_step(self, d):
        i = self.selected_step()
        if i is None or not (0 <= i + d < len(self.steps)):
            return
        self.steps[i], self.steps[i + d] = self.steps[i + d], self.steps[i]
        self.refresh_steps()
        self.steps_tree.selection_set(str(i + d))

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
        ttk.Spinbox(grid, from_=1, to=20, width=5, textvariable=self.v_confirm).grid(
            row=r, column=1, sticky="w")
        ttk.Label(grid, text="checks in a row  (ignores brief flickers; repeat checks are "
                             "quick)", style="Muted.TLabel").grid(
            row=r, column=2, columnspan=5, sticky="w", padx=(3, 0))
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
                                   job.get("watch_cooldown_s", 30))
        cool_lbl = ttk.Label(grid, text="then look again", style="Muted.TLabel")
        cool_lbl.grid(row=r, column=7, sticky="w")
        self._row_widgets[id(self.w_cool)].append(cool_lbl)
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
        self.withdraw()
        root_was_visible = self.app.main_visible()
        self.app.root.withdraw()
        self.after(450, lambda: self._draw_overlay(root_was_visible, mode))

    def _draw_overlay(self, root_was_visible, mode="picture"):
        app = self.app

        def restore():
            if root_was_visible:
                app.restore_main()
            self.deiconify()
            self.lift()
            self.focus_force()
            self.after(600, lambda: setattr(self, "_hold", max(0, self._hold - 1)))

        try:
            shot, (vx, vy) = grab_screen(move_cursor=False)
        except Exception as e:
            restore()
            messagebox.showerror(APP_NAME, f"Couldn't capture the screen:\n{e}", parent=self)
            return
        W, H = shot.size
        dim = Image.blend(shot, Image.new("RGB", shot.size, (0, 0, 0)), 0.5)
        ov = tk.Toplevel(app.root)
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        ov.geometry(f"{W}x{H}+{vx}+{vy}")
        cv = tk.Canvas(ov, width=W, height=H, highlightthickness=0, bd=0, cursor="crosshair",
                       bg="#000000")
        cv.pack()
        self._ov_imgs = [ImageTk.PhotoImage(dim)]
        cv.create_image(0, 0, image=self._ov_imgs[0], anchor="nw")
        bright = cv.create_image(0, 0, anchor="nw")
        rect = cv.create_rectangle(0, 0, 0, 0, outline="#3b82f6", width=2)
        size_txt = cv.create_text(0, 0, anchor="sw", fill="#ffffff",
                                  font=(app.font_family, 10, "bold"))
        msg = ("Drag a box around the picture to watch   ·   release to save   ·   "
               "Esc to cancel") if mode == "picture" else (
            "Drag a box around the AREA to search in   ·   release to save   ·   Esc to cancel")
        tw = cv.create_text(W // 2, 34, text=msg, fill="#ffffff",
                            font=(app.font_family, 13, "bold"))
        bx = cv.bbox(tw)
        bg = cv.create_rectangle(bx[0] - 18, bx[1] - 10, bx[2] + 18, bx[3] + 10,
                                 fill="#1f2937", outline="#3b82f6")
        cv.tag_raise(tw, bg)
        if IS_WIN:
            try:
                ov.update_idletasks()
                hwnd = user32.GetParent(ov.winfo_id()) or ov.winfo_id()
                user32.SetWindowPos(hwnd, wt.HWND(-1), vx, vy, W, H, 0x0040)  # SHOWWINDOW
            except Exception:
                pass
        st = {"x0": None, "y0": None, "box": None, "pending": False}

        def norm(x0, y0, x1, y1):
            return (max(0, min(x0, x1)), max(0, min(y0, y1)),
                    min(W, max(x0, x1)), min(H, max(y0, y1)))

        def redraw():
            st["pending"] = False
            b = st["box"]
            if not b or b[2] - b[0] < 2 or b[3] - b[1] < 2:
                return
            ph = ImageTk.PhotoImage(shot.crop(b))
            self._ov_imgs[1:] = [ph]
            cv.itemconfigure(bright, image=ph)
            cv.coords(bright, b[0], b[1])

        def down(e):
            st["x0"], st["y0"] = e.x, e.y
            st["box"] = None
            cv.itemconfigure(bg, state="hidden")
            cv.itemconfigure(tw, state="hidden")

        def move(e):
            if st["x0"] is None:
                return
            b = norm(st["x0"], st["y0"], e.x, e.y)
            st["box"] = b
            cv.coords(rect, *b)
            cv.coords(size_txt, b[0], max(14, b[1] - 4))
            cv.itemconfigure(size_txt, text=f"{b[2] - b[0]} × {b[3] - b[1]}")
            if not st["pending"]:
                st["pending"] = True
                ov.after(30, redraw)

        def up(e):
            if st["x0"] is None:
                return
            b = norm(st["x0"], st["y0"], e.x, e.y)
            st["x0"] = None
            if b[2] - b[0] < 16 or b[3] - b[1] < 16:
                cv.itemconfigure(bg, state="normal")
                cv.itemconfigure(tw, state="normal",
                                 text="That box is too small (at least 16 × 16). Drag again, "
                                      "or press Esc to cancel")
                bx2 = cv.bbox(tw)
                cv.coords(bg, bx2[0] - 18, bx2[1] - 10, bx2[2] + 18, bx2[3] + 10)
                cv.coords(rect, 0, 0, 0, 0)
                cv.itemconfigure(bright, image="")
                cv.itemconfigure(size_txt, text="")
                return
            if mode == "area":
                ov.destroy()
                self._ov_imgs = []
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
            ov.destroy()
            self._ov_imgs = []
            self.watch_png = img_to_b64(crop)
            self.update_watch_thumb()
            restore()
            gray = np.asarray(crop.convert("L"), dtype=np.float32)
            app.log(f"Watch picture saved: {crop.width}×{crop.height} at "
                    f"({b[0] + vx}, {b[1] + vy})")
            if float(gray.std()) < 6:
                messagebox.showwarning(APP_NAME, "That area is very plain (almost one "
                                                 "colour), so it can't be told apart from "
                                                 "other plain areas. Try a box around text, "
                                                 "an icon or a logo.", parent=self)
            elif crop.width * crop.height > 500 * 400:
                messagebox.showinfo(APP_NAME, "That's a big picture. It works, but each check "
                                              "takes longer. A smaller box around the most "
                                              "distinctive part is faster.", parent=self)

        def cancel(e=None):
            ov.destroy()
            self._ov_imgs = []
            restore()

        cv.bind("<ButtonPress-1>", down)
        cv.bind("<B1-Motion>", move)
        cv.bind("<ButtonRelease-1>", up)
        cv.bind("<Button-3>", cancel)
        ov.bind("<Escape>", cancel)
        ov.focus_force()

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

    def hms_row(self, f, r, label, seconds):
        h, rem = divmod(int(seconds), 3600)
        m, s = divmod(rem, 60)
        lbl = ttk.Label(f, text=label)
        lbl.grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
        # fixed column widths so nothing moves when values or text change
        f.columnconfigure(0, minsize=190)
        for c in (1, 3, 5):
            f.columnconfigure(c, minsize=70)
        for c in (2, 4, 6):
            f.columnconfigure(c, minsize=34)
        vs = []
        widgets = [lbl]
        for col, (val, top, unit) in enumerate(((h, 999, "h"), (m, 59, "m"), (s, 59, "s"))):
            v = tk.IntVar(value=val)
            sp = ttk.Spinbox(f, from_=0, to=top, width=5, textvariable=v,
                             command=self.update_preview)
            sp.grid(row=r, column=1 + col * 2, sticky="w")
            sp.bind("<KeyRelease>", lambda e: self.update_preview())
            ul = ttk.Label(f, text=unit)
            ul.grid(row=r, column=2 + col * 2, sticky="w", padx=(3, 10))
            vs.append(v)
            widgets += [sp, ul]
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
        self._hold += 1
        self.withdraw()
        root_was_visible = self.app.main_visible()
        self.app.root.withdraw()
        cd = tk.Toplevel(self.app.root, bg="#1f2937", highlightthickness=1,
                         highlightbackground="#3b82f6", highlightcolor="#3b82f6")
        cd.overrideredirect(True)
        cd.attributes("-topmost", True)
        lbl = tk.Label(cd, font=(self.app.font_family, 13, "bold"), bg="#1f2937", fg="#ffffff",
                       padx=20, pady=10, justify="left", anchor="w", cursor="fleur", bd=0)
        lbl.pack(fill="x")
        tip = tk.Label(cd, font=(self.app.font_family, 9), bg="#1f2937", fg="#9ca3af",
                       padx=20, pady=0, justify="left", anchor="w", cursor="fleur", bd=0,
                       text="Drag this box to move it (the countdown waits while you drag).\n"
                            "It also moves out of the way when your mouse comes near.")
        tip.pack(fill="x", pady=(0, 10))
        st = {"drag": None, "user_moved": False, "done": False}
        vx, vy, vw, vh = virtual_screen()

        def place(px, py):
            cd.geometry(f"+{int(px)}+{int(py)}")

        place(vx + 20, vy + 20)

        def press(e):
            st["drag"] = (e.x_root - cd.winfo_rootx(), e.y_root - cd.winfo_rooty())

        def motion(e):
            if st["drag"]:
                place(e.x_root - st["drag"][0], e.y_root - st["drag"][1])

        def release(e):
            st["drag"] = None
            st["user_moved"] = True

        for wdg in (lbl, tip):
            wdg.bind("<ButtonPress-1>", press)
            wdg.bind("<B1-Motion>", motion)
            wdg.bind("<ButtonRelease-1>", release)

        def dodge():
            """If the mouse gets close (and the user isn't dragging), jump to the corner
            farthest from the mouse."""
            if st["done"]:
                return
            if not st["drag"] and not st["user_moved"]:
                try:
                    mx, my = get_cursor()
                    bx, by = cd.winfo_rootx(), cd.winfo_rooty()
                    bw, bh = cd.winfo_width(), cd.winfo_height()
                    pad = 60
                    if bx - pad <= mx <= bx + bw + pad and by - pad <= my <= by + bh + pad:
                        corners = [(vx + 20, vy + 20), (vx + vw - bw - 20, vy + 20),
                                   (vx + 20, vy + vh - bh - 60),
                                   (vx + vw - bw - 20, vy + vh - bh - 60)]
                        cx, cy = max(corners, key=lambda c: (c[0] + bw / 2 - mx) ** 2
                                     + (c[1] + bh / 2 - my) ** 2)
                        place(cx, cy)
                except Exception:
                    pass
            cd.after(80, dodge)
        dodge()

        def step(n):
            if st["drag"]:                     # paused while the box is being dragged
                cd.after(200, step, n)
                return
            if n > 0:
                x, y = get_cursor()
                lbl.configure(text=f"Point at the spot to click…\n"
                                   f"Capturing in {n}    ({x}, {y})")
                cd.after(1000, step, n - 1)
                return
            x, y = get_cursor()
            st["done"] = True
            cd.destroy()
            self.app.root.update()
            self.app.root.after(250, lambda: finish(x, y))

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
            if root_was_visible:
                self.app.restore_main()
            self.deiconify()
            self.lift()
            self.focus_force()
            self.after(600, lambda: setattr(self, "_hold", max(0, self._hold - 1)))
            if warn:
                messagebox.showwarning(APP_NAME, warn, parent=self)
            self.app.log(f"Picked ({x}, {y})" + (f" inside “{short_title(info['window_title'])}”"
                                                 if info else ""))
        step(5)

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
                     steps=copy.deepcopy(self.steps))
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
                         watch_area_screen=copy.deepcopy(self.watch_area_screen))
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
        if d["target_mode"] == "window" and not d["window_title"]:
            messagebox.showerror(APP_NAME, "Enter the window title to follow, or pick the spot "
                                           "again, or choose “Fixed screen position”.",
                                 parent=self)
            return None
        # keep window details from the pick only if the title wasn't changed by hand
        same_title = d["window_title"] == self.job.get("window_title") or self.window_class
        d["window_class"] = self.window_class if same_title else ""
        d["client_w"], d["client_h"] = self.client_size
        d["pick_screen"] = self.pick_screen
        d["use_image"] = bool(self.v_use_img.get())
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
        if (not d["watch_click_picture"] and not d["snap_png"] and d["target_mode"] == "screen"
                and d["x"] == 0 and d["y"] == 0):
            messagebox.showerror(APP_NAME, "Pick the button to click (\u201cPick on "
                                           "screen\u201d).", parent=self)
            return
        app, j = self.app, self.job
        with app.lock:
            changed = any(j.get(k) != d.get(k) for k in (
                "watch_png", "watch_interval_s", "watch_confirm", "watch_trigger",
                "watch_area"))
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
        ttk.Spinbox(row, from_=0, to=1440, width=5, textvariable=self.v_m).pack(side="left",
                                                                               padx=6)
        ttk.Label(row, text="min").pack(side="left")
        ttk.Spinbox(row, from_=0, to=59, width=4, textvariable=self.v_s).pack(side="left",
                                                                             padx=6)
        ttk.Label(row, text="sec").pack(side="left")

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

        # ---- draggable split: test buttons (top) / history (bottom)
        self.paned = ttk.PanedWindow(main, orient="vertical")
        self.paned.pack(fill="both", expand=True, pady=(8, 0))
        ctl = ttk.Frame(self.paned)
        self.ctl = ctl
        hist = ttk.Frame(self.paned)
        self.paned.add(ctl, weight=0)
        self.paned.add(hist, weight=1)

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
                                                         "right now?"),
            ("Dry run", lambda: self.run("dry"), "marks the watched picture, then the button "
                                                 "it would click (no click)"),
            ("Schedule watcher test…", lambda: self.run("wsched"), "runs the check later, in "
                                                                   "the background"),
        ), self.btns_watch)
        self.groups.bind("<Configure>", lambda e: (self.flow_groups(),
                                                   self.after(60, self.keep_buttons_visible)))
        self.hint = ttk.Label(ctl, text=default_hint, style="Muted.TLabel")
        self.hint.pack(anchor="w", pady=(6, 0))
        self.pending_lbl = ttk.Label(ctl, style="Warn.TLabel")
        self.pending_row = ttk.Frame(ctl)
        self.pending_row.pack(fill="x", pady=(4, 0))
        self.pending_lbl.pack(in_=self.pending_row, side="left")
        self.cancel_btn = ttk.Button(self.pending_row, text="Cancel pending tests",
                                     style="Small.TButton", command=self.cancel_pending)

        # ---- history
        hh = ttk.Frame(hist)
        hh.pack(fill="x", pady=(10, 4))
        ttk.Label(hh, text="Test history", style="Section.TLabel").pack(side="left",
                                                                       padx=(0, 10))
        self.v_hf = tk.StringVar(value=app.settings.get("tests_hist_filter", "job"))
        for val, text in (("job", "This job"), ("all", "All jobs")):
            ttk.Radiobutton(hh, text=text, value=val, variable=self.v_hf,
                            style="Seg.TRadiobutton", command=self.hist_filter_changed).pack(
                side="left", padx=(0, 2))
        ttk.Button(hh, text="Clear", style="Small.TButton",
                   command=lambda: app.clear_test_history(self)).pack(side="right")

        hf = ttk.Frame(hist, style="Card.TFrame", padding=1)
        hf.pack(fill="both", expand=True)
        cols = ("time", "job", "test", "result")
        self.hist = ttk.Treeview(hf, columns=cols, show="headings", height=6,
                                 selectmode="browse")
        self.hist_base = {"time": 120, "job": 130, "test": 150, "result": 320}
        for c, h in (("time", "Time"), ("job", "Job"), ("test", "Test"), ("result", "Result")):
            self.hist.heading(c, text=h, anchor="w")
            self.hist.column(c, width=self.hist_base[c], minwidth=60,
                             stretch=(c == "result"), anchor="w")
        sb = ttk.Scrollbar(hf, orient="vertical", command=self.hist.yview)
        self.hist.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.hist.pack(side="left", fill="both", expand=True)
        self.hist.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.hist.bind("<Configure>", lambda e: self.flow_columns(e.width))
        self.hist_empty = ttk.Label(self.hist, style="Empty.TLabel", text="No tests yet")
        self.detail = ttk.Label(hist, style="Muted.TLabel", justify="left",
                                text="Select a result to see all the details.")
        self.detail.pack(fill="x", pady=(6, 0))
        hist.bind("<Configure>", lambda e: self.detail.configure(wraplength=max(200, e.width)))
        self.hist_rows = []

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
        self.after(200, self.restore_split)
        self.paned.bind("<ButtonRelease-1>", lambda e: self.after(50, self.remember_split))
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
    def flow_groups(self):
        """Side by side when there's room, stacked when narrow."""
        W = self.groups.winfo_width()
        if W <= 1:
            return
        need = sum(sum(b.winfo_reqwidth() for b in btns) + 40 for _, btns in self.group_frames)
        narrow = W < need + 10
        if narrow == self._narrow:
            return
        self._narrow = narrow
        for i, (g, _) in enumerate(self.group_frames):
            g.grid_forget()
            if narrow:
                g.grid(row=i, column=0, sticky="ew", pady=(0 if i == 0 else 8, 0))
            else:
                g.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 10, 0))
        self.groups.columnconfigure(0, weight=1, uniform="tg" if not narrow else "")
        self.groups.columnconfigure(1, weight=0 if narrow else 1,
                                    uniform="" if narrow else "tg")

    def flow_buttons(self, g, btns):
        """One row of buttons if they fit, otherwise one per line."""
        W = g.winfo_width()
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
        shown = ["time", "job", "test", "result"]
        if self.v_hf.get() == "job":
            shown.remove("job")
        if width < 560 and "job" in shown:
            shown.remove("job")
        if width < 440:
            shown.remove("test")
        if tuple(shown) != tuple(self.hist["displaycolumns"]):
            self.hist["displaycolumns"] = shown

    def keep_buttons_visible(self):
        """If the buttons were re-flowed (window got narrower), grow their pane to fit."""
        try:
            need = self.ctl.winfo_reqheight() + 4
            if self.paned.sashpos(0) < need:
                self.paned.sashpos(0, need)
        except Exception:
            pass

    def restore_split(self):
        """Give the test buttons the room they need (or the user's saved split, if bigger)."""
        try:
            self.update_idletasks()
            h = self.paned.winfo_height()
            need = self.ctl.winfo_reqheight() + 4
            frac = float(self.app.settings.get("tests_split") or 0)
            pos = int(h * frac) if h > 50 and 0.15 < frac < 0.85 else 0
            self.paned.sashpos(0, min(max(pos, need), max(need, h - 120)))
        except Exception:
            pass

    def remember_split(self):
        try:
            h = self.paned.winfo_height()
            if h > 50:
                self.app.settings["tests_split"] = round(self.paned.sashpos(0) / h, 3)
                self.app.save()
        except Exception:
            pass

    def retheme(self):
        p = self.app.pal
        self.app.theme_window(self)
        for tag, col in (("ok", p["good"]), ("warn", p["warn"]), ("bad", p["bad"]),
                         ("info", p["fg"])):
            self.hist.tag_configure(tag, foreground=col)
        self.hist.tag_configure("even", background=p["panel"])
        self.hist.tag_configure("odd", background=p["panel_alt"])

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
        rows = [e for e in hist if flt == "all" or not job or e["job"] == job["name"]]
        sig = (len(hist), hist[0]["t"] if hist else 0, flt, job["name"] if job else "")
        if force or dirty or sig != self._hist_sig:
            self._hist_sig = sig
            app.tests_dirty = False
            self.hist.delete(*self.hist.get_children())
            self.hist_rows = rows
            for i, e in enumerate(rows):
                when = datetime.fromtimestamp(e["t"]).strftime("%m/%d %H:%M:%S")
                icon = {"ok": "✔", "warn": "⚠", "bad": "✖"}.get(e.get("level"), "•")
                self.hist.insert("", "end", iid=str(i), values=(
                    when, e["job"], e["test"], f"{icon}  {e['result']}"),
                    tags=(e.get("level", "info"), "odd" if i % 2 else "even"))
            if rows:
                self.hist_empty.place_forget()
            else:
                self.hist_empty.configure(text="No tests for this job yet" if flt == "job"
                                          else "No tests yet")
                self.hist_empty.place(relx=0.5, rely=0.5, anchor="center")
            self.detail.configure(text="Select a result to see all the details.")

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
        ttk.Spinbox(row, from_=0, to=1440, width=5, textvariable=self.v_m).pack(side="left",
                                                                               padx=6)
        ttk.Label(row, text="min").pack(side="left")
        ttk.Spinbox(row, from_=0, to=59, width=4, textvariable=self.v_s).pack(side="left",
                                                                             padx=6)
        ttk.Label(row, text="sec").pack(side="left")
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
    """Add or edit one extra step of a job: click a spot, wait, type text, press keys."""
    TYPES = (("click", "Click a spot"), ("wait", "Wait"), ("waitpic", "Wait for a picture"),
             ("type", "Type text"), ("key", "Press keys"))

    def __init__(self, app, editor, step, index=None):
        super().__init__(app, "Edit step" if index is not None else "Add a step", editor)
        self.editor, self.index = editor, index
        self.step = dict(step)
        f = self.body
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Step").pack(side="left", padx=(0, 8))
        names = [n for _, n in self.TYPES]
        self.v_type = tk.StringVar(value=dict(self.TYPES).get(self.step.get("type", "click")))
        cb = ttk.Combobox(row, values=names, state="readonly", width=20, textvariable=self.v_type)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self.show_type())
        self.frames = {}

        # click
        fr = ttk.Frame(f, padding=(0, 10, 0, 0))
        self.frames["click"] = fr
        br = ttk.Frame(fr)
        br.pack(anchor="w")
        ttk.Button(br, text="◎  Pick on screen…", style="Accent.TButton",
                   command=self.pick).pack(side="left")
        self.click_info = ttk.Label(fr, style="Muted.TLabel", wraplength=420, justify="left")
        self.click_info.pack(anchor="w", pady=(8, 4))
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="X").pack(side="left")
        self.v_x = tk.IntVar(value=int(self.step.get("x", 0)))
        ttk.Spinbox(r, from_=-10000, to=20000, width=7, textvariable=self.v_x).pack(side="left", padx=6)
        ttk.Label(r, text="Y").pack(side="left")
        self.v_y = tk.IntVar(value=int(self.step.get("y", 0)))
        ttk.Spinbox(r, from_=-10000, to=20000, width=7, textvariable=self.v_y).pack(side="left", padx=6)
        r2 = ttk.Frame(fr)
        r2.pack(anchor="w", pady=(6, 0))
        self.v_btn = tk.StringVar(value=self.step.get("button", "left"))
        ttk.Combobox(r2, values=("left", "right", "middle"), state="readonly", width=8,
                     textvariable=self.v_btn).pack(side="left")
        self.v_clicks = tk.StringVar(value="double" if self.step.get("clicks") == 2 else "single")
        ttk.Combobox(r2, values=("single", "double"), state="readonly", width=8,
                     textvariable=self.v_clicks).pack(side="left", padx=6)
        self.v_img = tk.BooleanVar(value=bool(self.step.get("use_image", True)) and HAVE_CV)
        ttk.Checkbutton(fr, text="Find the spot by its picture (recommended)",
                        variable=self.v_img).pack(anchor="w", pady=(6, 0))

        # wait
        fr = ttk.Frame(f, padding=(0, 10, 0, 0))
        self.frames["wait"] = fr
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="Wait").pack(side="left")
        self.v_wmin = tk.IntVar(value=int(self.step.get("min", 2)))
        ttk.Spinbox(r, from_=0, to=86400, width=7, textvariable=self.v_wmin).pack(side="left", padx=6)
        ttk.Label(r, text="to").pack(side="left")
        self.v_wmax = tk.IntVar(value=int(self.step.get("max", self.step.get("min", 2))))
        ttk.Spinbox(r, from_=0, to=86400, width=7, textvariable=self.v_wmax).pack(side="left", padx=6)
        ttk.Label(r, text="seconds (the same number twice = exactly that long)",
                  style="Muted.TLabel").pack(side="left")

        # type
        fr = ttk.Frame(f, padding=(0, 10, 0, 0))
        self.frames["type"] = fr
        ttk.Label(fr, text="Text to type (into whatever has focus after the previous step). "
                           "New lines press Enter.", style="Muted.TLabel",
                  wraplength=420).pack(anchor="w")
        self.txt = tk.Text(fr, height=5, width=48, wrap="word", bd=0, padx=8, pady=6,
                           bg=app.pal["field"], fg=app.pal["fg"],
                           insertbackground=app.pal["fg"], highlightthickness=1,
                           highlightbackground=app.pal["border"], highlightcolor=app.pal["accent"])
        self.txt.pack(fill="x", pady=(6, 0))
        self.txt.insert("1.0", self.step.get("text", ""))

        # wait for a picture
        fr = ttk.Frame(f, padding=(0, 10, 0, 0))
        self.frames["waitpic"] = fr
        top = ttk.Frame(fr)
        top.pack(fill="x")
        self.pic_lbl = ttk.Label(top, style="Thumb.TLabel", anchor="center", width=24)
        self.pic_lbl.pack(side="left", anchor="n")
        rc = ttk.Frame(top, padding=(12, 0, 0, 0))
        rc.pack(side="left", fill="x", expand=True, anchor="n")
        ttk.Button(rc, text="▢  Draw box around picture…", style="Accent.TButton",
                   command=self.draw_pic).pack(anchor="w")
        ttk.Label(rc, style="Muted.TLabel", wraplength=280, justify="left", text=(
            "Draw a box around what the previous click should make appear (or disappear), "
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
            side="left", padx=6)
        ttk.Label(r, text="seconds; if it doesn't happen,").pack(side="left")
        self.v_ponto = tk.StringVar(value="continue anyway" if self.step.get("on_timeout") ==
                                    "continue" else "stop the chain")
        ttk.Combobox(r, values=("stop the chain", "continue anyway"), state="readonly", width=15,
                     textvariable=self.v_ponto).pack(side="left", padx=6)
        ttk.Label(fr, style="Muted.TLabel", wraplength=460, justify="left", text=(
            "It looks about once a second. While a chain is waiting, other jobs wait their turn "
            "(the mouse can only do one thing at a time).")).pack(anchor="w", pady=(8, 0))
        self._pic_thumb = None

        # key
        fr = ttk.Frame(f, padding=(0, 10, 0, 0))
        self.frames["key"] = fr
        r = ttk.Frame(fr)
        r.pack(anchor="w")
        ttk.Label(r, text="Keys").pack(side="left")
        self.v_keys = tk.StringVar(value=self.step.get("keys", "Enter"))
        ttk.Entry(r, textvariable=self.v_keys, width=22).pack(side="left", padx=6)
        qr = ttk.Frame(fr)
        qr.pack(anchor="w", pady=(6, 0))
        for k in ("Enter", "Tab", "Esc", "Ctrl+S", "Ctrl+A", "Ctrl+V", "F5", "Alt+Tab"):
            ttk.Button(qr, text=k, style="Small.TButton",
                       command=lambda k=k: self.v_keys.set(k)).pack(side="left", padx=(0, 4))
        ttk.Label(fr, style="Muted.TLabel", wraplength=440, justify="left", text=(
            "Combine with +, e.g. Ctrl+Shift+S. Names: Ctrl, Alt, Shift, Win, Enter, Tab, Esc, "
            "Space, Backspace, Delete, Up, Down, Left, Right, Home, End, PageUp, PageDown, "
            "F1-F12, letters and digits.")).pack(anchor="w", pady=(6, 0))

        b = self.footer
        ttk.Button(b, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Save step", style="Accent.TButton", command=self.on_save).pack(
            side="right", padx=6)
        self.update_click_info()
        self.update_pic_thumb()
        self.until_changed()
        self.show_type()
        self.finish()

    def until_changed(self):
        on = self.v_until.get() == "appears"
        for w in (self.click_it_cb, self.pbtn_cb, self.pclk_cb):
            w.state(["!disabled"] if on else ["disabled"])
            if on and isinstance(w, ttk.Combobox):
                w.state(["readonly"])

    def update_pic_thumb(self):
        png = self.step.get("png")
        if not (HAVE_PIL and png):
            self.pic_lbl.configure(image="", text="No picture yet")
            return
        try:
            img = b64_to_img(png)
            f = min(200 / img.width, 110 / img.height, 3.0)
            if abs(f - 1) > 0.05:
                img = img.resize((max(1, round(img.width * f)), max(1, round(img.height * f))))
            self._pic_thumb = ImageTk.PhotoImage(img)
            self.pic_lbl.configure(image=self._pic_thumb, text="")
        except Exception:
            self.pic_lbl.configure(image="", text="(picture unreadable)")

    def draw_pic(self):
        def done(img):
            self.step["png"] = img_to_b64(img)
            self.update_pic_thumb()
        self.app.draw_capture(self, "Drag a box around the picture to wait for", done)

    def kind(self):
        return {n: k for k, n in self.TYPES}.get(self.v_type.get(), "click")

    def show_type(self):
        for k, fr in self.frames.items():
            fr.pack_forget()
        self.frames[self.kind()].pack(fill="x")

    def update_click_info(self):
        if self.step.get("snap_png"):
            self.click_info.configure(text="A picture of the spot is saved, so it will be found "
                                           "even if things move.")
        else:
            self.click_info.configure(text="Click “Pick on screen”, then point at the "
                                           "spot within 5 seconds.")

    def pick(self):
        def done(x, y, png, spot):
            self.v_x.set(x)
            self.v_y.set(y)
            self.step.update(snap_png=png, snap_spot=spot, pick_dpi=system_dpi(),
                             pick_screen=list(screen_size()))
            self.update_click_info()
        self.app.pick_point(self, done)

    def on_save(self):
        k = self.kind()
        st = {"type": k}
        try:
            if k == "click":
                st.update(x=int(self.v_x.get()), y=int(self.v_y.get()), button=self.v_btn.get(),
                          clicks=2 if self.v_clicks.get() == "double" else 1,
                          use_image=bool(self.v_img.get()) and bool(self.step.get("snap_png")),
                          snap_png=self.step.get("snap_png", ""),
                          snap_spot=self.step.get("snap_spot"),
                          pick_dpi=self.step.get("pick_dpi"),
                          pick_screen=self.step.get("pick_screen"),
                          image_fallback="wait", target_mode="screen")
                if st["x"] == 0 and st["y"] == 0 and not st["snap_png"]:
                    messagebox.showerror(APP_NAME, "Pick the spot to click first.", parent=self)
                    return
            elif k == "wait":
                lo, hi = int(self.v_wmin.get()), int(self.v_wmax.get())
                if hi < lo:
                    lo, hi = hi, lo
                st.update(min=max(0, lo), max=max(0, hi))
            elif k == "waitpic":
                if not self.step.get("png"):
                    messagebox.showerror(APP_NAME, "Draw a box around the picture to wait for "
                                                   "first.", parent=self)
                    return
                st.update(png=self.step["png"], until=self.v_until.get(),
                          click_it=bool(self.v_click_it.get()) and self.v_until.get() == "appears",
                          button=self.v_pbtn.get(),
                          clicks=2 if self.v_pclicks.get() == "double" else 1,
                          timeout=max(1, min(STEP_MAX_WAIT_S, int(self.v_ptimeout.get()))),
                          on_timeout="continue" if self.v_ponto.get().startswith("continue")
                          else "stop")
            elif k == "type":
                st["text"] = self.txt.get("1.0", "end-1c")
                if not st["text"]:
                    messagebox.showerror(APP_NAME, "Enter the text to type.", parent=self)
                    return
            else:
                parse_combo(self.v_keys.get())
                st["keys"] = self.v_keys.get().strip()
        except ValueError as e:
            messagebox.showerror(APP_NAME, f"Please check this step: {e}", parent=self)
            return
        except Exception:
            messagebox.showerror(APP_NAME, "Please check the numbers.", parent=self)
            return
        self.editor.step_saved(st, self.index)
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
        ttk.Label(f, text="Recent activity", style="Section.TLabel").pack(anchor="w")
        tf = ttk.Frame(f, style="Card.TFrame", padding=1)
        tf.pack(fill="both", expand=True, pady=(4, 0))
        tr = ttk.Treeview(tf, columns=("time", "kind", "result", "detail"), show="headings",
                          height=8)
        for c, h, w in (("time", "Time", 150), ("kind", "Type", 90), ("result", "Result", 80),
                        ("detail", "Details", 260)):
            tr.heading(c, text=h, anchor="w")
            tr.column(c, width=w, anchor="w", stretch=(c == "detail"))
        sb = ttk.Scrollbar(tf, orient="vertical", command=tr.yview)
        tr.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tr.pack(fill="both", expand=True)
        mine = [r for r in rows if r.get("job") == job["name"]][-200:]
        for r in reversed(mine):
            det = r.get("detail") or (f"({r.get('x')}, {r.get('y')}) {r.get('how', '')}"
                                      if r.get("x") else "")
            tr.insert("", "end", values=(r["time"], r.get("kind", ""), r.get("result", ""), det))
        b = self.footer
        ttk.Button(b, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(b, text="Export this job's history…",
                   command=lambda: app.export_history(job["name"], self)).pack(side="left")
        self.finish()


class HelpDialog(Dialog):
    def __init__(self, app):
        super().__init__(app, "Help & shortcuts")
        f = self.body
        sections = (
            ("Scheduled clicks", "＋ New click → Pick on screen (point within 5 s) → set how often "
             "and an optional random delay → Save. A picture of the spot is saved, so it's found "
             "even if windows move or the screen size changes."),
            ("Screen watchers", "👁 New watcher → Draw box around the picture → choose to click "
             "when it disappears or appears → pick the button (or click the picture itself) → "
             "Save. Optionally search only an area, and add active hours."),
            ("More steps & click chains", "Any job can do more after its click: click other "
             "spots, wait, wait for a picture to appear (and click it) or go away, type text, "
             "press keys - add them under “More steps” in Edit."),
            ("Tests", "🧪 Tests opens a popup with Show spot, Test click, Check picture, Dry run "
             "and scheduled tests. The whole app hides while a test runs."),
            ("Locked screen", "Windows blocks clicks and screenshots while locked or "
             "disconnected. Hand the session to the console when leaving RDP, and lock your own "
             "PC instead of the VM."),
            ("Shortcuts", "Ctrl+N new click  ·  Ctrl+Shift+N new watcher  ·  Enter edit  ·  "
             "Space start/stop  ·  P pause job  ·  Ctrl+P pause all  ·  Ctrl+T tests  ·  "
             "Ctrl+Z undo delete  ·  Ctrl+, preferences  ·  Del delete\n"
             f"Anywhere (global): {app.settings.get('hk_pause') or '-'} pause all  ·  "
             f"{app.settings.get('hk_show') or '-'} show/hide Clickue"),
        )
        for title, text in sections:
            ttk.Label(f, text=title, style="Section.TLabel").pack(anchor="w", pady=(8, 2))
            ttk.Label(f, text=text, style="Muted.TLabel", wraplength=560,
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
        ttk.Button(self.footer, text="Close", command=self.destroy).pack(side="right")
        self.finish()


class SettingsDialog(Dialog):
    """Preferences, in tabs."""
    TABS = (("general", "General"), ("clicking", "Clicking"), ("watchers", "Watchers"),
            ("hotkeys", "Hotkeys"), ("alerts", "Phone alerts"), ("look", "Appearance"),
            ("data", "Data & backups"))

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
            ttk.Spinbox(row, from_=lo, to=hi, width=6, textvariable=v).pack(side="left", padx=6)
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
        note(p, "Waiting for idle keeps Clickue from grabbing the mouse while you're using it.")

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
        note(p, "Use at least one of Ctrl, Alt, Shift, Win plus a key, e.g. Ctrl+Alt+P. Leave a "
                "box empty to turn that hotkey off.")

        # Alerts
        p = self.pages["alerts"]
        check(p, "alerts_on", "Send alerts to my phone")
        note(p, "Discord: in a server you own, Channel settings → Integrations → Webhooks → "
                "New webhook → Copy URL. Telegram: create a bot with @BotFather (gives the "
                "token), send it a message, then get your chat id from @userinfobot.")
        text(p, "alert_discord", "Discord webhook URL", 52)
        text(p, "alert_tg_token", "Telegram bot token", 52, show="•")
        text(p, "alert_tg_chat", "Telegram chat id", 20)
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

        # Appearance
        p = self.pages["look"]
        row = ttk.Frame(p)
        row.pack(anchor="w", pady=2)
        ttk.Label(row, text="Theme").pack(side="left")
        self.v_theme = tk.StringVar(value=s.get("theme", "system").capitalize())
        ttk.Combobox(row, values=("System", "Light", "Dark"), state="readonly", width=9,
                     textvariable=self.v_theme).pack(side="left", padx=6)
        check(p, "show_cards", "Show the summary cards at the top")

        # Data & backups
        p = self.pages["data"]
        check(p, "backups_on", "Back up my jobs and settings once a day")
        spin(p, "backups_keep", "Keep the newest", 1, 365, "daily backups")
        check(p, "history_on", "Keep a click history (for stats and CSV export)")
        spin(p, "log_max_mb", "Log file size limit", 1, 50,
             "MB  (2 older copies are kept; older ones are deleted)")
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
            show(send_alert(settings, "This is a test alert. If you can read this, alerts work!"))
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
        for k in ("hk_pause", "hk_show"):
            if new[k]:
                try:
                    parse_hotkey(new[k])
                except ValueError as e:
                    messagebox.showerror(APP_NAME, f"Hotkey “{new[k]}”: {e}", parent=self)
                    return
        if new["hk_pause"] and new["hk_pause"].lower() == new["hk_show"].lower():
            messagebox.showerror(APP_NAME, "The two hotkeys must be different.", parent=self)
            return
        new["log_max_mb"] = max(1, new["log_max_mb"])
        new["backups_keep"] = max(1, new["backups_keep"])
        new["default_watch_interval"] = max(1, new["default_watch_interval"])
        new["default_watch_confirm"] = max(1, new["default_watch_confirm"])
        new["theme"] = self.v_theme.get().lower()
        new["alert_events"] = {k: bool(v.get()) for k, v in self.ev_vars.items()}

        old_start, old_mb, old_cards = (s.get("start_with_windows"), s.get("log_max_mb"),
                                        s.get("show_cards", True))
        old_hk = (s.get("hotkeys_on"), s.get("hk_pause"), s.get("hk_show"))
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
        if (new["hotkeys_on"], new["hk_pause"], new["hk_show"]) != old_hk:
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
