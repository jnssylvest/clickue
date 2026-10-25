"""Draws the example pictures used in docs/GUIDE.md.

    python scripts/make_guide_images.py

Writes PNGs to docs/images/guide/. They are illustrations (invented "Example App" screens),
not screenshots, so they can be regenerated anywhere with only Pillow installed. Pictures
are drawn at 2x so they stay sharp on high-DPI screens.
"""
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "images", "guide")
S = 2  # drawing scale

BG = "#f6f7f9"
WIN = "#ffffff"
LINE = "#d0d5dd"
SOFT = "#eef1f5"
FG = "#1f2937"
MUTED = "#6b7280"
ACCENT = "#2563eb"
GREEN = "#16a34a"
RED = "#dc2626"
AMBER = "#d97706"
PURPLE = "#7c3aed"
TINT = {GREEN: "#dcfce7", RED: "#fee2e2", AMBER: "#fef3c7", ACCENT: "#dbeafe",
        PURPLE: "#ede9fe", MUTED: "#f3f4f6"}

FONT_FILES = {
    "regular": ["/usr/share/fonts/opentype/inter/Inter-Regular.otf", "segoeui.ttf", "arial.ttf",
                "DejaVuSans.ttf"],
    "medium": ["/usr/share/fonts/opentype/inter/Inter-Medium.otf", "seguisb.ttf", "arial.ttf",
               "DejaVuSans.ttf"],
    "bold": ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf", "segoeuib.ttf",
             "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "mono": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "consola.ttf",
             "DejaVuSansMono.ttf"],
}
_fonts = {}


def font(size, weight="regular"):
    key = (size, weight)
    if key not in _fonts:
        for path in FONT_FILES[weight]:
            try:
                _fonts[key] = ImageFont.truetype(path, int(size * S))
                break
            except OSError:
                continue
        else:
            _fonts[key] = ImageFont.load_default(int(size * S))
    return _fonts[key]


class Pic:
    def __init__(self, w, h, title=None, subtitle=None):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * S, h * S), BG)
        self.d = ImageDraw.Draw(self.img)
        if title:
            self.text(32, 22, title, 19, "bold")
        if subtitle:
            self.text(32, 50, subtitle, 13, fill=MUTED)

    # ---- basics (all coordinates are logical pixels)
    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1, r=0):
        box = [x0 * S, y0 * S, x1 * S, y1 * S]
        if r:
            self.d.rounded_rectangle(box, r * S, fill=fill, outline=outline, width=int(width * S))
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=int(width * S))

    def text(self, x, y, s, size=13, weight="regular", fill=FG, anchor="la"):
        self.d.text((x * S, y * S), s, font=font(size, weight), fill=fill, anchor=anchor)
        return self.tw(s, size, weight)

    def tw(self, s, size=13, weight="regular"):
        return self.d.textlength(s, font=font(size, weight)) / S

    def para(self, x, y, s, size=13, width=40, fill=FG, weight="regular", gap=1.45):
        for i, line in enumerate(textwrap.wrap(s, width)):
            self.text(x, y + i * size * gap, line, size, weight, fill)
        return y + len(textwrap.wrap(s, width)) * size * gap

    def line(self, pts, fill=FG, width=2):
        self.d.line([(x * S, y * S) for x, y in pts], fill=fill, width=int(width * S),
                    joint="curve")

    def circle(self, cx, cy, r, fill=None, outline=None, width=1):
        self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=fill,
                       outline=outline, width=int(width * S))

    def dashed_rect(self, x0, y0, x1, y1, color, width=2, dash=7, gap=5):
        for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1),
                                 (x0, y1, x0, y0)):
            length = abs(bx - ax) + abs(by - ay)
            dx = (bx - ax) / length if length else 0
            dy = (by - ay) / length if length else 0
            t = 0
            while t < length:
                e = min(t + dash, length)
                self.line([(ax + dx * t, ay + dy * t), (ax + dx * e, ay + dy * e)], color, width)
                t += dash + gap

    def arrow(self, x0, y0, x1, y1, color=MUTED, width=2.5, head=9):
        import math
        self.line([(x0, y0), (x1, y1)], color, width)
        a = math.atan2(y1 - y0, x1 - x0)
        pts = [(x1, y1),
               (x1 - head * math.cos(a - 0.45), y1 - head * math.sin(a - 0.45)),
               (x1 - head * math.cos(a + 0.45), y1 - head * math.sin(a + 0.45))]
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=color)

    def shade(self, x0, y0, x1, y1, alpha=60):
        """Darken an area (like the dimmed page behind a dialog)."""
        box = (int(x0 * S), int(y0 * S), int(x1 * S), int(y1 * S))
        part = self.img.crop(box)
        dark = Image.new("RGB", part.size, (0, 0, 0))
        self.img.paste(Image.blend(part, dark, alpha / 255), box[:2])

    def save(self, name):
        os.makedirs(OUT, exist_ok=True)
        self.img.save(os.path.join(OUT, name), optimize=True)
        print("wrote", name)


# ---------------------------------------------------------------- widgets
def window(p, x, y, w, h, title, title_size=12):
    p.rect(x + 3, y + 4, x + w + 3, y + h + 4, fill="#e3e6eb", r=8)
    p.rect(x, y, x + w, y + h, fill=WIN, outline=LINE, r=8)
    p.rect(x, y, x + w, y + 30, fill=SOFT, r=8)
    p.rect(x, y + 20, x + w, y + 30, fill=SOFT)
    p.line([(x, y + 30), (x + w, y + 30)], LINE, 1)
    p.text(x + 12, y + 15, title, title_size, "medium", anchor="lm")
    bx = x + w - 18
    p.line([(bx - 4, y + 11), (bx + 4, y + 19)], MUTED, 1.4)      # ✕
    p.line([(bx - 4, y + 19), (bx + 4, y + 11)], MUTED, 1.4)
    p.rect(bx - 28, y + 11, bx - 20, y + 19, outline=MUTED, width=1.2)  # ▢
    p.line([(bx - 52, y + 15), (bx - 44, y + 15)], MUTED, 1.4)    # —
    return x + 14, y + 42


def button(p, x, y, label, kind="secondary", size=13, h=30, pad=14):
    w = p.tw(label, size, "medium") + 2 * pad
    if kind == "primary":
        p.rect(x, y, x + w, y + h, fill=ACCENT, r=6)
        col = "#ffffff"
    elif kind == "disabled":
        p.rect(x, y, x + w, y + h, fill=SOFT, outline=LINE, r=6)
        col = "#a0a7b4"
    else:
        p.rect(x, y, x + w, y + h, fill=WIN, outline=LINE, r=6)
        col = FG
    p.text(x + w / 2, y + h / 2, label, size, "medium", fill=col, anchor="mm")
    return (x, y, x + w, y + h)


def badge(p, x, y, label, color, size=12, h=24):
    w = p.tw(label, size, "medium") + 34
    p.rect(x, y, x + w, y + h, fill=TINT.get(color, SOFT), r=h / 2)
    p.circle(x + 13, y + h / 2, 4, fill=color)
    p.text(x + 23, y + h / 2, label, size, "medium", fill=color, anchor="lm")
    return (x, y, x + w, y + h)


def bars(p, x, y, widths, gap=16, h=8, color="#e5e7eb"):
    for i, w in enumerate(widths):
        p.rect(x, y + i * gap, x + w, y + i * gap + h, fill=color, r=4)


def capture(p, box, color=ACCENT, label=None, pad=6, dashed=False, below=False, size=11):
    x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    if dashed:
        p.dashed_rect(x0, y0, x1, y1, color, 2)
    else:
        p.rect(x0, y0, x1, y1, outline=color, width=2.5, r=3)
    if label:
        w = p.tw(label, size, "bold") + 14
        ty = y1 + 4 if below else y0 - 22
        p.rect(x0, ty, x0 + w, ty + 18, fill=color, r=3)
        p.text(x0 + 7, ty + 9, label, size, "bold", fill="#ffffff", anchor="lm")
    return (x0, y0, x1, y1)


def crosshair(p, cx, cy, color=RED, r=13):
    p.circle(cx, cy, r, outline=color, width=2.5)
    p.circle(cx, cy, 2.5, fill=color)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        p.line([(cx + dx * (r - 5), cy + dy * (r - 5)), (cx + dx * (r + 6), cy + dy * (r + 6))],
               color, 2.5)


def click_target(p, box, color=RED, pad=9, label=None):
    """Where Clickue clicks: a red outline around the target plus a pointer at its corner."""
    x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    p.rect(x0, y0, x1, y1, outline=color, width=2.5, r=6)
    cursor(p, x1 - 10, y1 - 8)
    if label:
        p.text(x1 + 18, (y0 + y1) / 2, label, 12, "bold", fill=color, anchor="lm")


def icon_button(p, x, y, size=34):
    """A square toolbar button with a refresh icon (no text to cover)."""
    import math
    p.rect(x, y, x + size, y + size, fill=WIN, outline=LINE, r=6)
    cx, cy, r = x + size / 2, y + size / 2, size * 0.26
    pts = [(cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a)))
           for a in range(-60, 241, 15)]
    p.line(pts, FG, 2)
    ex, ey = pts[0]
    p.d.polygon([((ex + 5) * S, (ey - 1) * S), ((ex - 3) * S, (ey - 6) * S),
                 ((ex - 1) * S, (ey + 4) * S)], fill=FG)
    return (x, y, x + size, y + size)


def cursor(p, x, y, s=1.0):
    pts = [(0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12)]
    poly = [((x + a * s) * S, (y + b * s) * S) for a, b in pts]
    p.d.polygon(poly, fill="#111827", outline="#ffffff")
    p.d.line(poly + [poly[0]], fill="#ffffff", width=int(1.2 * S))


def num(p, cx, cy, n, color=ACCENT, r=11):
    p.circle(cx, cy, r, fill=color)
    p.text(cx, cy + 0.5, str(n), 12, "bold", fill="#ffffff", anchor="mm")


def mark(p, cx, cy, ok, r=9):
    """A round tick or cross icon."""
    col = GREEN if ok else RED
    p.circle(cx, cy, r, fill=col)
    if ok:
        p.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.4)],
               "#ffffff", 2)
    else:
        k = r * 0.38
        p.line([(cx - k, cy - k), (cx + k, cy + k)], "#ffffff", 2)
        p.line([(cx - k, cy + k), (cx + k, cy - k)], "#ffffff", 2)


def click_dot(p, cx, cy, color=ACCENT):
    p.circle(cx, cy, 8, fill=color)
    p.circle(cx, cy, 3, fill="#ffffff")


def note_box(p, x, y, w, h, color=ACCENT):
    p.rect(x, y, x + w, y + h, fill=TINT.get(color, SOFT), r=8)
    p.rect(x, y, x + 4, y + h, fill=color, r=2)


# ---------------------------------------------------------------- pictures
def main_window_layout():
    p = Pic(980, 650, "The main window", "What each part of Clickue's main window is for.")
    x0, y0, w, h = 32, 82, 700, 540
    window(p, x0, y0, w, h, "Clickue")
    L = x0 + 16
    # 1 header
    p.circle(L + 14, y0 + 58, 13, fill=ACCENT)
    p.circle(L + 14, y0 + 58, 5, fill="#ffffff")
    p.text(L + 36, y0 + 50, "Clickue", 17, "bold")
    p.text(L + 36, y0 + 70, "Scheduled clicks and screen watchers that click for you.", 10,
           fill=MUTED)
    bx = x0 + w - 16
    b = button(p, bx - 74, y0 + 44, "Menu", size=11, h=26, pad=10)
    b2 = button(p, b[0] - 70, y0 + 44, "Theme", size=11, h=26, pad=10)
    button(p, b2[0] - 86, y0 + 44, "Summary", size=11, h=26, pad=10)
    # 2 cards
    cy = y0 + 92
    cw = (w - 32 - 3 * 10) / 4
    for i, (t, v, sub) in enumerate((("NEXT CLICK", "in 2h 14m", "Refresh report"),
                                     ("ACTIVE JOBS", "3 of 4", "1 watcher"),
                                     ("CLICKS TODAY", "17", "0 problems"),
                                     ("SCREEN", "Available", "unlocked"))):
        cx = L + i * (cw + 10)
        p.rect(cx, cy, cx + cw, cy + 62, fill=WIN, outline=LINE, r=6)
        p.text(cx + 10, cy + 10, t, 9, "bold", fill=MUTED)
        p.text(cx + 10, cy + 25, v, 15, "bold")
        p.text(cx + 10, cy + 46, sub, 9, fill=MUTED)
    # 3 toolbar
    ty = cy + 76
    x = L
    for lbl, kind in (("+ New click", "primary"), ("New watcher", ""), ("Edit", ""),
                      ("Duplicate", ""), ("Delete", ""), ("Start", ""), ("Pause", ""),
                      ("Pause all", ""), ("Tests", ""), ("Record", "")):
        bb = button(p, x, ty, lbl, kind or "secondary", size=10, h=24, pad=8)
        x = bb[2] + 5
    button(p, x0 + w - 16 - 62, ty, "More", size=10, h=24, pad=12)
    # 4 filter
    fy = ty + 36
    x = L
    for i, lbl in enumerate(("All", "Scheduled clicks", "Screen watchers")):
        ww = p.tw(lbl, 10, "medium") + 18
        p.rect(x, fy, x + ww, fy + 22, fill=ACCENT if i == 0 else SOFT, r=4)
        p.text(x + ww / 2, fy + 11, lbl, 10, "medium", fill="#ffffff" if i == 0 else FG,
               anchor="mm")
        x += ww + 3
    # run bar (only while a job runs or waits)
    ry0 = fy + 30
    p.rect(L, ry0, L + w - 32, ry0 + 24, fill=WIN, outline=LINE, r=4)
    p.text(L + 10, ry0 + 12, "▶ Running “Daily report” · step 3 of 8 · 42s · Waiting their turn: "
                             "Reconnect", 10, fill=MUTED, anchor="lm")
    button(p, L + w - 32 - 98, ry0 + 2, "Stop this run", size=9, h=20, pad=8)
    # 5 job list
    gy = ry0 + 34
    gw = w - 32
    p.rect(L, gy, L + gw, gy + 112, fill=WIN, outline=LINE, r=4)
    cols = (("Status", 26), ("Type", 112), ("Name", 180), ("What it does", 290),
            ("Next / last seen", 458), ("In", 562), ("Clicks", 626))
    p.rect(L + 1, gy + 1, L + gw - 1, gy + 24, fill=SOFT)
    tickbox(p, L + 7, gy + 6)
    for c, cx in cols:
        p.text(L + 8 + cx, gy + 12, c, 10, "bold", fill=MUTED, anchor="lm")
    rows = ((GREEN, "Running", "Click", "Refresh report", "Every 8h → Left", "16:04:12",
             "2h 14m", "41"),
            (ACCENT, "Watching", "Watcher", "Reconnect", "Disappears → Left", "Seen 13:49:58",
             "12s", "3"),
            (AMBER, "Paused", "Click", "Weekly export", "Every 7d → window", "Paused", "—", "9"))
    for i, r in enumerate(rows):
        ry = gy + 24 + i * 29
        p.line([(L, ry), (L + gw, ry)], LINE, 1)
        tickbox(p, L + 7, ry + 8)
        p.circle(L + 40, ry + 14, 4, fill=r[0])
        p.text(L + 50, ry + 14, r[1], 10, "medium", fill=r[0], anchor="lm")
        for (c, cx), val in zip(cols[1:], r[2:]):
            p.text(L + 8 + cx, ry + 14, val, 10, anchor="lm")
    for c, cx in cols:
        p.line([(L + cx, gy), (L + cx, gy + 112)], "#e5e7eb", 1)
    # 6 activity
    ay = gy + 124
    p.text(L, ay + 2, "Activity", 12, "bold")
    x = L + 70
    for i, lbl in enumerate(("Everything", "Clicks", "Problems")):
        ww = p.tw(lbl, 10, "medium") + 16
        p.rect(x, ay, x + ww, ay + 20, fill=ACCENT if i == 0 else SOFT, r=4)
        p.text(x + ww / 2, ay + 10, lbl, 10, "medium", fill="#ffffff" if i == 0 else FG,
               anchor="mm")
        x += ww + 3
    p.rect(L, ay + 28, L + gw, ay + 92, fill=WIN, outline=LINE, r=4)
    for i, (t, col) in enumerate((("13:49:58  [Reconnect] picture seen", MUTED),
                                  ("14:02:11  [Reconnect] picture gone 2 checks - clicked", GREEN),
                                  ("14:02:12  [Refresh report] next click 16:04:12", MUTED))):
        p.text(L + 10, ay + 40 + i * 17, t, 10, "regular", fill=col)
    # 7 status bar
    p.text(L, y0 + h - 18, "v4.5  ·  tray on  ·  Emergency stop: Ctrl+Alt+X  ·  Data: "
                           "%APPDATA%\\Clickue  ·  Shortcuts: Ctrl+N new …", 10, fill=MUTED)

    # callouts
    notes = ((1, y0 + 58, "Header: Summary toggle, light/dark theme, and the Menu"),
             (2, cy + 31, "Summary cards: next click, active jobs, clicks today, screen"),
             (3, ty + 12, "Toolbar (overflow: More)"),
             (4, fy + 4, "Filter: all, clicks or watchers"),
             (5, ry0 + 16, "While a job runs: what's running and who's waiting"),
             (6, gy + 56, "Job list: columns fit their text and change with the filter; "
                          "tick boxes for batch actions"),
             (7, ay + 50, "Activity: a live log, filterable"),
             (8, y0 + h - 18, "Status bar, with the emergency-stop hotkey"))
    for n, yy, t in notes:
        num(p, x0 + w + 22, yy, n)
        p.line([(x0 + w - 4, yy), (x0 + w + 10, yy)], ACCENT, 1.5)
        p.para(x0 + w + 40, yy - 9, t, 11, 30)
    p.save("main-window.png")


def tickbox(p, x, y, on=False, size=13):
    p.rect(x, y, x + size, y + size, fill=ACCENT if on else WIN, outline=ACCENT if on else MUTED,
           r=3)
    if on:
        p.line([(x + 3, y + size / 2), (x + size * 0.42, y + size - 3.5), (x + size - 3, y + 3)],
               "#ffffff", 2)


def batch_actions():
    p = Pic(980, 470, "Tick boxes and batch actions",
            "Tick jobs, then act on all of them at once, or Edit together.")
    x0, y0, w = 32, 82, 600
    window(p, x0, y0, w, 360, "Clickue")
    L = x0 + 16
    # batch bar
    by = y0 + 46
    p.rect(L, by, L + w - 32, by + 34, fill=WIN, outline=LINE, r=4)
    p.text(L + 10, by + 17, "3 jobs ticked", 10, "bold", fill=MUTED, anchor="lm")
    x = L + 100
    for lbl in ("Start", "Stop", "Pause", "Resume", "Edit together…", "Delete…", "Clear"):
        bb = button(p, x, by + 6, lbl, "primary" if lbl.startswith("Edit") else "secondary",
                    size=9, h=22, pad=7)
        x = bb[2] + 4
    # list
    gy = by + 46
    gw = w - 32
    p.rect(L, gy, L + gw, gy + 24 + 5 * 29, fill=WIN, outline=LINE, r=4)
    p.rect(L + 1, gy + 1, L + gw - 1, gy + 24, fill=SOFT)
    tickbox(p, L + 7, gy + 6)
    for c, cx in (("Status", 26), ("Name", 120), ("Schedule", 300)):
        p.text(L + 8 + cx, gy + 12, c, 10, "bold", fill=MUTED, anchor="lm")
    rows = ((True, GREEN, "Watching", "Status badge A", "check every 10s"),
            (True, GREEN, "Watching", "Status badge B", "check every 10s"),
            (False, GREEN, "Running", "Morning report", "every 24h"),
            (True, AMBER, "Paused", "Session prompt", "check every 10s"),
            (False, MUTED, "Stopped", "Weekly export", "every 7d"))
    for i, (on, col, st, name, sched) in enumerate(rows):
        ry = gy + 24 + i * 29
        if on:
            p.rect(L + 1, ry, L + gw - 1, ry + 29, fill="#e8f0fe")
        p.line([(L, ry), (L + gw, ry)], LINE, 1)
        tickbox(p, L + 7, ry + 8, on)
        p.circle(L + 40, ry + 14, 4, fill=col)
        p.text(L + 50, ry + 14, st, 10, "medium", fill=col, anchor="lm")
        p.text(L + 128, ry + 14, name, 10, anchor="lm")
        p.text(L + 308, ry + 14, sched, 10, anchor="lm")
    cursor(p, L + 12, gy + 24 + 3 * 29 + 12)
    # edit together panel
    ex, ey = 660, 82
    window(p, ex, ey, 290, 250, "Edit 3 jobs")
    rows2 = ((True, "Check every", "0 h  0 m  30 s"), (False, "Act after", "2  checks in a row"),
             (False, "Random delay", "off"), (True, "Match", "part is enough: 75 %"),
             (False, "Mouse button", "left"))
    for i, (on, lbl, val) in enumerate(rows2):
        yy = ey + 46 + i * 30
        tickbox(p, ex + 14, yy, on)
        p.text(ex + 34, yy + 7, lbl, 10, "medium", anchor="lm")
        p.text(ex + 140, yy + 7, val, 10, fill=FG if on else MUTED, anchor="lm")
    button(p, ex + 290 - 104, ey + 250 - 40, "Apply to all", "primary", size=10, h=26, pad=10)
    p.arrow(L + w - 32, by + 17, ex - 4, by + 17, ACCENT)
    p.text(32, 452, "Only the settings you tick are changed. One Undo restores everything a "
                    "batch delete removed.", 12, fill=MUTED)
    p.save("batch-actions.png")


def partial_matching():
    p = Pic(980, 420, "Exact or partial matching",
            "The box includes a time that changes. Exact: gone. Part of it is enough: found.")
    # saved picture
    def panel(x, y, t, changed=False):
        p.rect(x, y, x + 250, y + 56, fill=WIN, outline=LINE, r=6)
        if changed:                          # the tiles Clickue compares, changed ones in red
            for k in range(10):
                for r_ in range(2):
                    tx, ty = x + 1 + k * 24.8, y + 1 + r_ * 27
                    p.rect(tx + 1, ty + 1, tx + 23.8, ty + 26,
                           fill=TINT[RED] if k == 8 else None,
                           outline=RED if k == 8 else "#e5e7eb", width=2 if k == 8 else 1)
        badge(p, x + 12, y + 16, "Connected", GREEN)
        p.text(x + 132, y + 28, t, 11, "medium", fill=MUTED, anchor="lm")
    p.text(40, 96, "Saved picture", 13, "bold")
    panel(40, 118, "updated 14:32")
    p.text(360, 96, "On screen a minute later", 13, "bold")
    panel(360, 118, "updated 14:33", changed=True)
    p.text(360, 186, "Grey tiles match, red tiles differ: the time changed.", 11, fill=MUTED)
    # verdicts
    y = 230
    p.rect(40, y, 470, y + 120, fill=TINT[RED], r=8)
    p.text(56, y + 16, "Match: the exact picture", 13, "bold")
    p.para(56, y + 42, "Shape, detail and colour of the whole box must match. The changed time "
                       "makes it \u201cPicture NOT on screen (best 77%)\u201d, so a gone-watcher would "
                       "click.", 11, 52)
    p.rect(500, y, 940, y + 120, fill=TINT[GREEN], r=8)
    p.text(516, y + 16, "Match: part of the picture is enough: 75 %", 13, "bold")
    p.para(516, y + 42, "Each small tile is compared on its own. 18 of 20 tiles (90 %) match, so it "
                        "counts as showing. If the badge itself disappears, far less matches and "
                        "the watcher clicks.", 11, 52)
    p.text(40, 380, "Best fix when possible: draw the box around the badge only and keep exact "
                    "matching.", 12, fill=MUTED)
    p.save("partial-matching.png")


def draw_zoom():
    p = Pic(980, 470, "Zooming in while you draw",
            "Mouse wheel: zoom up to 24x. The magnifier shows the exact pixels.")
    x0, y0, W, H = 32, 82, 600, 340
    p.rect(x0, y0, x0 + W, y0 + H, fill="#4b5563", r=6)
    # zoomed view: big pixels of a small icon
    cell = 20
    icon = ["..........", "....##....", "...####...", "..######..", ".########.",
            "....##....", "....##....", "....##....", "..........", ".........."]
    gx, gy = x0 + 120, y0 + 40
    for r_, row in enumerate(icon):
        for c, ch in enumerate(row):
            col = "#16a34a" if ch == "#" else "#e5e7eb"
            p.rect(gx + c * cell, gy + r_ * cell, gx + (c + 1) * cell, gy + (r_ + 1) * cell,
                   fill=col, outline="#9ca3af")
    p.rect(gx + cell, gy + cell, gx + 9 * cell, gy + 8 * cell, outline=ACCENT, width=3)
    p.text(gx + cell, gy - 6, "8 × 7 px", 11, "bold", fill="#ffffff", anchor="lb")
    cursor(p, gx + 9 * cell, gy + 8 * cell)
    # magnifier
    lx, ly = gx + 10 * cell + 40, gy
    p.rect(lx, ly, lx + 150, ly + 150, fill="#e5e7eb", outline=ACCENT, width=2)
    for k in range(1, 15):
        p.line([(lx + k * 10, ly), (lx + k * 10, ly + 150)], "#9ca3af", 1)
        p.line([(lx, ly + k * 10), (lx + 150, ly + k * 10)], "#9ca3af", 1)
    p.rect(lx + 70, ly + 70, lx + 80, ly + 80, outline="#ff00fe", width=2)
    p.rect(lx, ly + 150, lx + 150, ly + 196, fill="#111827", r=0)
    p.text(lx + 8, ly + 160, "512, 347   #e5e7eb", 10, fill="#ffffff")
    p.text(lx + 8, ly + 176, "zoom 12×   box 8 × 7 px", 10, fill="#ffffff")
    p.rect(x0 + 8, y0 + H - 30, x0 + W - 8, y0 + H - 8, fill="#1f2937", r=4)
    p.text(x0 + 16, y0 + H - 19, "Zoom 12×  ·  wheel or + / − to zoom  ·  middle-drag or arrows "
                                 "to move  ·  0 = whole screen", 10, fill="#e5e7eb", anchor="lm")
    tx = 670
    for i, t in enumerate(("Wheel up/down: zoom in/out around the pointer.",
                           "From 8× a pixel grid shows every pixel.",
                           "The magnifier shows position and colour.",
                           "Zoom while dragging to place each edge exactly.",
                           "The saved picture is always the real pixels.")):
        num(p, tx, 120 + i * 60, i + 1)
        p.para(tx + 22, 110 + i * 60, t, 12, 24)
    p.save("draw-zoom.png")


def good_and_bad_spots():
    p = Pic(980, 440, "Picking a good spot",
            "Clickue saves a small picture around the spot you pick and looks for it before "
            "every click.")
    x0, y0 = 32, 86
    cx, cy = window(p, x0, y0, 600, 320, "Reports - Example App")
    b1 = button(p, cx, cy, "Refresh", "primary")
    b2 = button(p, b1[2] + 8, cy, "Export")
    button(p, b2[2] + 8, cy, "Settings")
    bars(p, cx, cy + 56, (250, 190, 230, 170, 240, 200, 120), gap=26, h=10)
    capture(p, b1, GREEN, "Good", below=True)
    cursor(p, b1[2] - 14, b1[3] - 10)
    capture(p, (cx + 360, cy + 110, cx + 520, cy + 210), RED, "Bad", pad=0, dashed=True)
    # explanations
    ex = 670
    mark(p, ex + 9, 120, True)
    p.text(ex + 26, 111, "Good: text or an icon nearby", 13, "bold")
    p.para(ex + 26, 134, "It looks unique, so Clickue finds it again after windows move, the "
                         "screen size changes or display scaling is different.", 12, 36,
           MUTED)
    mark(p, ex + 9, 250, False)
    p.text(ex + 26, 241, "Bad: a plain, empty area", 13, "bold")
    p.para(ex + 26, 264, "It looks the same everywhere, so it can't be told apart from other "
                         "plain areas. Clickue warns you when you pick one.", 12, 36, MUTED)
    p.save("good-and-bad-spots.png")


def picture_sizes():
    p = Pic(980, 410, "Picture size: Small, Medium or Large",
            "How much of the screen around the spot is saved. Chosen in the editor; used the "
            "next time you pick.")
    x0, y0 = 32, 86
    cx, cy = window(p, x0, y0, 560, 300, "Example App")
    yb = cy + 90
    b0 = button(p, cx + 40, yb, "Back")
    b1 = button(p, b0[2] + 10, yb, "Refresh", "primary")
    b2 = button(p, b1[2] + 10, yb, "Export")
    button(p, b2[2] + 10, yb, "Print")
    bars(p, cx + 40, yb + 112, (330, 260), gap=20, h=9)
    sx, sy = (b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2
    for (name, (w, h)), col in zip((("Small", (90, 56)), ("Medium", (150, 90)),
                                    ("Large", (260, 150))), (GREEN, ACCENT, PURPLE)):
        w2, h2 = w / 2 * 0.85, h / 2 * 0.85
        p.rect(sx - w2, sy - h2, sx + w2, sy + h2, outline=col, width=2, r=2)
        if name == "Small":
            p.text(sx - w2 + 2, sy + h2 + 1, name, 9, "bold", fill=col)
        else:
            p.text(sx - w2 + 5, sy - h2 + 4, name, 10, "bold", fill=col)
    p.circle(sx, sy + 9, 3.5, fill=RED, outline="#ffffff", width=1.5)
    ex = 630
    rows = ((GREEN, "Small", "Fastest. Fine when the spot itself is distinctive."),
            (ACCENT, "Medium (default)", "Good for most buttons and links."),
            (PURPLE, "Large", "Most unique. Use it when several buttons look alike, like "
                              "a row of identical icons."))
    y = 104
    for col, name, t in rows:
        p.rect(ex, y + 3, ex + 14, y + 17, outline=col, width=2, r=2)
        p.text(ex + 24, y, name, 13, "bold", fill=col)
        y = p.para(ex + 24, y + 22, t, 12, 38, MUTED) + 16
    p.para(ex, y + 4, "Bigger pictures are more unique but each search takes a little longer.",
           12, 44)
    p.save("picture-sizes.png")


def schedule_timeline():
    p = Pic(980, 420, "Every 8 hours, with a random delay of 10 s to 15 min",
            "Shaded = the random-delay window after each scheduled time. Delays are drawn "
            "larger so you can see them.")
    left, right = 300, 950
    hrs = 32
    scale = (right - left) / hrs
    k = 3.2  # px per minute of delay (exaggerated)

    def X(h, minutes=0.0):
        return left + h * scale + minutes * k

    def axis(y):
        p.line([(left - 10, y), (right, y)], LINE, 2)
        for h in range(0, hrs + 1, 8):
            p.line([(X(h), y - 6), (X(h), y + 6)], MUTED, 2)

    lanes = (
        ("Random delay on,", "fixed schedule (default)", [(0, 4.2, "08:04:12"),
                                                          (8, 12.0, "16:12:01"),
                                                          (16, 0.6, "00:00:37"),
                                                          (24, 9.8, "08:09:50")], False),
        ("Random delay on,", "fixed schedule off", [(0, 4.2, "08:04:12"), (8, 16.2, "16:16:13"),
                                                    (16, 16.8, "00:16:50"),
                                                    (24, 27.4, "08:27:25")], True),
        ("Random delay off", "(exact timing)", [(0, 0, "08:00:00"), (8, 0, "16:00:00"),
                                                (16, 0, "00:00:00"), (24, 0, "08:00:00")], None),
    )
    y = 120
    labels = ["08:00", "16:00", "00:00", "08:00", "16:00"]
    for h, lab in zip(range(0, hrs + 1, 8), labels):
        p.text(X(h), 96, lab, 11, "medium", fill=MUTED, anchor="mm")
    for t1, t2, clicks, drift in lanes:
        p.text(32, y + 2, t1, 13, "bold")
        p.text(32, y + 22, t2, 12, fill=MUTED)
        axis(y + 18)
        prev = 0.0
        for i, (h, m, lab) in enumerate(clicks):
            base = prev if drift else 0.0
            if drift is not None:
                p.rect(X(h, base), y + 6, X(h, base + 15), y + 30, fill=TINT[ACCENT], r=3)
                if drift and i:
                    p.line([(X(h), y + 34), (X(h, base), y + 34)], AMBER, 2)
            click_dot(p, X(h, m), y + 18, GREEN)
            p.text(X(h, m), y + 46, lab, 11, "medium", anchor="mm")
            prev = m
        y += 92
    note_box(p, 32, 382, 916, 30, AMBER)
    p.text(46, 397, "Fixed schedule off: each wait starts from the actual click, so times drift "
                    "later (orange). With it on, the schedule stays at 08:00 / 16:00 / 00:00.",
           11, anchor="lm")
    p.save("schedule-random-delay.png")


def active_hours():
    p = Pic(980, 480, "Active hours: 08:00 to 22:00, Monday to Friday",
            "Outside the green hours a scheduled click waits or is skipped; a watcher rests.")
    left, right = 110, 940
    sc = (right - left) / 24
    top = 100
    for h in range(0, 25, 6):
        p.text(left + h * sc, top - 8, f"{h:02d}:00", 11, "medium", fill=MUTED, anchor="mm")
    days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    rh = 30
    for i, dname in enumerate(days):
        y = top + 6 + i * rh
        p.text(32, y + rh / 2 - 2, dname, 12, "medium", anchor="lm")
        p.rect(left, y, right, y + rh - 6, fill="#eceff3", r=4)
        if i < 5:
            p.rect(left + 8 * sc, y, left + 22 * sc, y + rh - 6, fill="#bbf7d0", r=4)
    # a click due at Wed 23:30 waits until Thu 08:00
    wy = top + 6 + 2 * rh + (rh - 6) / 2
    ty = top + 6 + 3 * rh + (rh - 6) / 2
    num(p, left + 23.5 * sc, wy, 1, AMBER, 10)
    num(p, left + 8 * sc, ty, 2, GREEN, 10)
    y = top + 6 + 7 * rh + 14
    num(p, 42, y + 8, 1, AMBER, 10)
    p.text(60, y + 8, "A click comes due on Wednesday at 23:30, outside the hours.", 12,
           anchor="lm")
    num(p, 42, y + 34, 2, GREEN, 10)
    p.text(60, y + 34, "\"Wait until the hours start, then click\": it clicks on Thursday at "
                       "08:00. \"Skip that click\": it waits for the next scheduled time.", 12,
           anchor="lm")
    # overnight example
    y = top + 6 + 7 * rh + 82
    p.text(32, y - 2, "Overnight: 22:00 to 06:00", 13, "bold")
    y += 22
    p.rect(left, y, right, y + 24, fill="#eceff3", r=4)
    p.rect(left, y, left + 6 * sc, y + 24, fill="#bbf7d0", r=4)
    p.rect(left + 22 * sc, y, right, y + 24, fill="#bbf7d0", r=4)
    for h in (0, 6, 22, 24):
        p.text(left + h * sc, y + 38, f"{h:02d}:00", 10, fill=MUTED, anchor="mm")
    p.save("active-hours.png")


def watcher_disappears():
    p = Pic(980, 440, "Watcher example: click when a picture disappears",
            "Watch the \"Connected\" badge. When it's gone, click Reconnect.")
    for k, (title, ok) in enumerate((("Before", True), ("After", False))):
        x0 = 32 + k * 490
        p.text(x0, 84, title, 14, "bold", fill=MUTED)
        cx, cy = window(p, x0, 108, 430, 250, "Dashboard - Example App")
        p.text(cx, cy + 10, "Example App", 14, "bold")
        if ok:
            bb = badge(p, cx + 300, cy + 2, "Connected", GREEN)
            capture(p, bb, ACCENT, "Watched picture", pad=5, below=True)
        else:
            bb = badge(p, cx + 128, cy + 2, "Connection lost", RED)
            capture(p, (cx + 300, cy + 2, cx + 300 + p.tw("Connected", 12, "medium") + 34,
                        cy + 26), MUTED, "missing", pad=5, dashed=True, below=True)
        bars(p, cx, cy + 60, (360, 300, 330, 250), gap=22, h=10)
        rb = button(p, cx, cy + 160, "Reconnect")
        if not ok:
            click_target(p, rb, label="Clickue clicks here")
        mark(p, x0 + 9, 386, ok)
        p.text(x0 + 26, 386, "Picture showing: nothing to do" if ok else
               "Missing 2 checks in a row: click Reconnect", 13, "medium", anchor="lm")
    p.arrow(470, 230, 512, 230, ACCENT, 3, 11)
    p.save("watcher-disappears.png")


def watcher_appears():
    p = Pic(980, 450, "Watcher example: click when a picture appears",
            "Watch for the \"Stay signed in\" button and click it as soon as it shows up.")
    for k, (title, shown) in enumerate((("Before", False), ("After", True))):
        x0 = 32 + k * 490
        p.text(x0, 84, title, 14, "bold", fill=MUTED)
        cx, cy = window(p, x0, 108, 430, 260, "Portal - Example App")
        p.text(cx, cy + 10, "Example App", 14, "bold")
        bars(p, cx, cy + 50, (380, 330, 360, 300, 340, 280), gap=24, h=10)
        if shown:
            p.shade(x0 + 1, 139, x0 + 429, 367)
            dx, dy = x0 + 70, 170
            p.rect(dx + 3, dy + 4, dx + 293, dy + 154, fill="#d6d9de", r=8)
            p.rect(dx, dy, dx + 290, dy + 150, fill=WIN, outline=LINE, r=8)
            p.text(dx + 18, dy + 22, "Still there?", 14, "bold")
            p.text(dx + 18, dy + 48, "Your session ends in 60 seconds.", 12, fill=MUTED)
            sb = button(p, dx + 18, dy + 96, "Stay signed in", "primary")
            button(p, sb[2] + 10, dy + 96, "Sign out")
            capture(p, sb, ACCENT, "Watched picture", pad=4, below=True)
            click_target(p, sb, pad=9)
        mark(p, x0 + 9, 400, shown)
        p.text(x0 + 26, 400, "Appears: Clickue clicks the picture itself" if shown else
               "Not showing yet: nothing to do", 13, "medium", anchor="lm")
    p.arrow(470, 240, 512, 240, ACCENT, 3, 11)
    p.save("watcher-appears.png")


def strict_matching():
    p = Pic(980, 330, "Strict matching: shape, detail and colour must all agree",
            "The saved picture on the left, compared with what's on screen now.")
    p.text(32, 96, "Saved picture", 12, "bold", fill=MUTED)
    sb = badge(p, 40, 130, "Online", GREEN, 14, 30)
    capture(p, sb, ACCENT, pad=6)
    p.arrow(sb[2] + 24, 145, sb[2] + 64, 145, MUTED)
    cols = ((GREEN, "Online", 1.0, True, "Same picture", "counts as showing"),
            (GREEN, "Online", 1.4, True, "Bigger (other scaling)", "still found"),
            (RED, "Online", 1.0, False, "Different colour", "counts as changed"),
            (GREEN, "Offline", 1.0, False, "Different text", "counts as changed"))
    x = 240
    for col, txt, scl, ok, t1, t2 in cols:
        bb = badge(p, x, 145 - 15 * scl, txt, col, 14 * scl, 30 * scl)
        mark(p, x + 10, 222, ok)
        p.text(x + 26, 214, t1, 12, "bold")
        p.text(x + 26, 233, t2, 12, fill=GREEN if ok else RED)
        x += 180
    note_box(p, 32, 272, 916, 34, ACCENT)
    p.text(46, 289, "Screen watchers are strict, so a badge that turns from green to red, or "
                    "says something else, counts as \"gone\".", 12, anchor="lm")
    p.save("strict-matching.png")


def search_area():
    p = Pic(980, 470, "Search only an area",
            "Draw an area to search in. It's faster, and look-alikes elsewhere are ignored.")
    x0, y0, w, h = 32, 84, 700, 360
    cx, cy = window(p, x0, y0, w, h, "Inbox - Example App")
    p.rect(x0 + 1, y0 + 31, x0 + 220, y0 + h - 1, fill="#f9fafb")
    p.line([(x0 + 220, y0 + 31), (x0 + 220, y0 + h)], LINE, 1)
    p.text(cx, cy + 6, "Folders", 12, "bold")
    bars(p, cx, cy + 36, (120, 90, 140, 100), gap=24, h=9)
    lb = badge(p, cx, cy + 150, "New", AMBER)
    p.text(cx, cy + 186, "look-alike,", 11, "bold", fill=MUTED)
    p.text(cx, cy + 202, "outside: ignored", 11, "bold", fill=MUTED)
    mx = x0 + 240
    p.text(mx, cy + 6, "Messages", 12, "bold")
    nb = badge(p, mx + 340, cy + 2, "New", AMBER)
    bars(p, mx, cy + 46, (420, 360, 400, 300, 380, 340, 260), gap=26, h=10)
    capture(p, (mx - 8, cy - 6, x0 + w - 14, y0 + h - 14), ACCENT, "Search area", pad=0,
            dashed=True)
    capture(p, nb, GREEN, "Watched", pad=4, below=True)
    ex = 760
    y = 110
    for t in ("Faster: only the area is checked, not the whole screen.",
              "Look-alikes outside the area are ignored.",
              "If the screen size changes, the area scales with it.",
              "Draw the area big enough to allow for the window moving a little."):
        p.circle(ex + 5, y + 8, 3, fill=ACCENT)
        y = p.para(ex + 16, y, t, 12, 26) + 14
    p.save("search-area.png")


def flicker_protection():
    p = Pic(980, 330, "Flicker protection: \"Click when missing for 2 checks in a row\"",
            "A one-off blip is ignored. Repeat checks are quick (5 s), so a real change is "
            "confirmed fast.")
    y = 160
    p.line([(60, y), (930, y)], LINE, 2)
    pts = ((80, True, "0 s", "seen"), (250, False, "30 s", "missing (1 of 2)"),
           (360, True, "35 s", "seen again: reset"), (540, False, "65 s", "missing (1 of 2)"),
           (650, False, "70 s", "missing (2 of 2)"))
    for x, ok, t, lab in pts:
        p.circle(x, y, 14, fill=GREEN if ok else RED)
        p.text(x, y - 32, t, 12, "medium", fill=MUTED, anchor="mm")
        p.text(x, y + 32, lab, 12, "medium", anchor="mm")
    p.text(305, y + 62, "a flicker: no click", 11, "bold", fill=MUTED, anchor="mm")
    p.line([(250, y + 50), (360, y + 50)], MUTED, 1.5)
    p.arrow(672, y, 790, y, ACCENT, 3, 11)
    click_dot(p, 820, y, ACCENT)
    p.text(820, y - 32, "~72 s", 12, "medium", fill=MUTED, anchor="mm")
    p.text(820, y + 32, "click", 12, "bold", fill=ACCENT, anchor="mm")
    p.text(735, y - 16, "random delay", 10, fill=MUTED, anchor="mm")
    note_box(p, 32, 266, 916, 40, ACCENT)
    p.text(46, 286, "Green = the picture is on screen, red = it isn't. This watcher checks "
                    "every 30 s and has a random delay of 1-5 s before clicking.", 12,
           anchor="lm")
    p.save("flicker-protection.png")


def click_once():
    p = Pic(980, 420, "\"Click only once\" on or off",
            "The same watcher (click when it disappears), with the option on and off.")
    L, R = 260, 940
    y = 110
    p.text(32, y + 2, "The picture", 13, "bold")
    segs = ((0, 0.2, True), (0.2, 0.36, False), (0.36, 0.56, True), (0.56, 1.0, False))
    for a, b, on in segs:
        p.rect(L + a * (R - L), y, L + b * (R - L), y + 22, fill="#bbf7d0" if on else "#fecaca")
        p.text(L + (a + b) / 2 * (R - L), y + 11, "showing" if on else "gone", 11, "medium",
               fill=GREEN if on else RED, anchor="mm")

    def lane(yy, t1, t2, clicks, note):
        p.text(32, yy, t1, 13, "bold")
        p.text(32, yy + 20, t2, 12, fill=MUTED)
        p.line([(L, yy + 14), (R, yy + 14)], LINE, 2)
        for c in clicks:
            click_dot(p, L + c * (R - L), yy + 14)
        p.text(L, yy + 36, note, 11, fill=MUTED)

    lane(180, "Click only once: on", "(the default)", (0.22, 0.58),
         "One click each time it disappears. Then it waits for the picture to come back.")
    lane(270, "Click only once: off", "after-click wait 30 s", (0.22, 0.31, 0.58, 0.67, 0.76,
                                                              0.85, 0.94),
         "Keeps clicking while it stays gone (after each click it waits, then looks again).")
    note_box(p, 32, 356, 916, 42, ACCENT)
    p.para(46, 364, "Use \"on\" for one-shot actions (reconnect once). Use \"off\" for actions "
                    "that may need retrying until they work, with a sensible wait in between.",
           12, 118)
    p.save("click-once.png")


def click_chain():
    p = Pic(1000, 470, "Click chain: each step waits for the result of the last",
            "Main click Refresh, then three \"Wait for a picture\" steps.")
    W, H, gap = 214, 190, 32
    y0 = 96
    labels = (("1", "Main click: Refresh"), ("2", "Wait for Export to appear,", "then click it"),
              ("3", "Wait for Save,", "then click it"),
              ("4", "Wait for \"Download", "complete\" (no click)"))
    for i in range(4):
        x0 = 32 + i * (W + gap)
        cx, cy = window(p, x0, y0, W, H, "Example App", 10)
        if i == 0:
            b = button(p, cx, cy, "Refresh", "primary", 11, 24, 10)
            click_target(p, b, pad=6)
            bars(p, cx, cy + 46, (120, 90), gap=20, h=8, color="#eceff3")
        if i == 1:
            button(p, cx, cy, "Refresh", "primary", 11, 24, 10)
            bars(p, cx, cy + 40, (170, 140, 160), gap=18, h=8)
            b = button(p, cx, cy + 100, "Export", "secondary", 11, 24, 10)
            capture(p, b, ACCENT, pad=3)
            click_target(p, b, pad=8)
        if i == 2:
            bars(p, cx, cy + 4, (170, 140, 160, 120), gap=18, h=8)
            p.rect(x0 + 24, y0 + 62, x0 + W - 24, y0 + H - 16, fill=WIN, outline=LINE, r=6)
            p.text(x0 + 36, y0 + 80, "Save file", 11, "bold")
            p.rect(x0 + 36, y0 + 96, x0 + W - 36, y0 + 114, outline=LINE, r=3)
            p.text(x0 + 42, y0 + 105, "report.csv", 10, fill=MUTED, anchor="lm")
            b = button(p, x0 + W - 36 - 60, y0 + 130, "Save", "primary", 11, 24, 10)
            capture(p, b, ACCENT, pad=3)
            click_target(p, b, pad=8)
        if i == 3:
            bars(p, cx, cy + 4, (170, 140, 160), gap=18, h=8)
            bb = badge(p, cx, cy + 90, "Download complete", GREEN, 11, 24)
            capture(p, bb, ACCENT, pad=4)
        if i < 3:
            p.arrow(x0 + W + 6, y0 + H / 2, x0 + W + gap - 6, y0 + H / 2, ACCENT, 3, 10)
        lab = labels[i]
        num(p, x0 + 11, y0 + H + 28, lab[0])
        for j, t in enumerate(lab[1:]):
            p.text(x0 + 30, y0 + H + 28 + j * 18, t, 12, "medium", anchor="lm")
    note_box(p, 32, 380, 936, 66, ACCENT)
    p.para(46, 390, "Blue box = the picture that step waits for. Red outline and pointer = where it clicks. "
                    "Each wait has a time limit (e.g. 60 s). If the picture never shows, the "
                    "step either stops the chain (the safe choice) or continues anyway. Draw "
                    "each picture while that screen is actually showing.", 12, 130)
    p.save("click-chain.png")


def multi_step_search():
    p = Pic(980, 440, "Multi-step job: search for something and open the first result",
            "One job, five actions: the main click plus four extra steps.")
    x0, y0 = 32, 86
    cx, cy = window(p, x0, y0, 560, 330, "Orders - Example App")
    p.rect(cx, cy, cx + 360, cy + 32, fill=WIN, outline=ACCENT, width=1.5, r=6)
    p.text(cx + 12, cy + 16, "1042", 13, anchor="lm")
    p.line([(cx + 12 + p.tw("1042", 13) + 2, cy + 8), (cx + 12 + p.tw("1042", 13) + 2,
                                                        cy + 24)], FG, 1.2)
    bs = button(p, cx + 370, cy + 1, "Search", "secondary", 12, 30, 12)
    rows = ("Order 1042 - shipped", "Order 10420 - open", "Order 10421 - open")
    for i, r in enumerate(rows):
        ry = cy + 60 + i * 44
        p.rect(cx, ry, cx + 530, ry + 36, fill="#f9fafb" if i else TINT[ACCENT], outline=LINE,
               r=5)
        p.text(cx + 14, ry + 18, r, 12, "medium" if i == 0 else "regular", anchor="lm")
    num(p, cx - 2, cy - 4, 1)
    num(p, cx + 70, cy + 16, 2)
    num(p, bs[2] + 14, cy + 16, 3, PURPLE)
    num(p, cx + 520, cy + 46, 4, PURPLE)
    p.text(cx + 504, cy + 46, "results load", 11, fill=MUTED, anchor="rm")
    cursor(p, cx + 160, cy + 72)
    num(p, cx + 190, cy + 78, 5)
    ex = 630
    p.text(ex, 100, "In the job editor", 13, "bold", fill=MUTED)
    steps = (("1", "Main click", "the search box"),
             ("2", "Type text", "1042"),
             ("3", "Press keys", "Enter"),
             ("4", "Wait", "2 s, while results load"),
             ("5", "Click a spot", "the first result"))
    y = 128
    for n, t, d in steps:
        p.rect(ex, y, ex + 320, y + 44, fill=WIN, outline=LINE, r=6)
        num(p, ex + 22, y + 22, n, PURPLE if n in "34" else ACCENT)
        p.text(ex + 44, y + 13, t, 12, "bold")
        p.text(ex + 44, y + 30, d, 11, fill=MUTED)
        y += 52
    p.text(ex, y + 6, "Blue = clicks, purple = keys and waits.", 11, fill=MUTED)
    p.save("multi-step-search.png")


def show_spot():
    p = Pic(980, 360, "Tests: Show spot and Dry run",
            "See exactly where Clickue would click, without clicking.")
    for k, title in enumerate(("Show spot (scheduled click)", "Dry run (screen watcher)")):
        x0 = 32 + k * 490
        p.text(x0, 84, title, 14, "bold", fill=MUTED)
        cx, cy = window(p, x0, 108, 430, 220, "Example App")
        if k == 0:
            b0 = button(p, cx + 20, cy + 58, "Export")
            b1 = icon_button(p, b0[2] + 10, cy + 56)
            button(p, b1[2] + 10, cy + 58, "Print")
            sx, sy = (b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2
            crosshair(p, sx, sy, RED, 20)
            p.rect(cx + 20, cy + 112, cx + 330, cy + 156, fill="#1f2937", r=6)
            p.text(cx + 32, cy + 125, "Found by picture 81% at 150% size", 11, "bold",
                   fill="#ffffff")
            p.text(cx + 32, cy + 143, "No click - the mouse just moves there", 10,
                   fill="#cbd5e1")
        else:
            bb = badge(p, cx + 260, cy + 2, "Connected", GREEN)
            capture(p, bb, ACCENT, "1  picture", pad=5, below=True)
            rb = button(p, cx, cy + 120, "Reconnect")
            click_target(p, rb)
            p.text(rb[2] + 24, rb[1] + 2, "2  button it would click", 11, "bold", fill=RED)
            p.text(rb[2] + 24, rb[1] + 20, "Picture is showing: would NOT click now", 11,
                   fill=MUTED)
    p.save("tests-show-spot-dry-run.png")


def remote_sessions():
    p = Pic(980, 430, "Remote desktop: leave the session running, not disconnected",
            "Windows lets no program click on a locked or disconnected screen.")
    def node(x, y, w, t1, t2, col=FG):
        p.rect(x, y, x + w, y + 56, fill=WIN, outline=LINE, r=8)
        p.text(x + 14, y + 18, t1, 13, "bold", fill=col)
        p.text(x + 14, y + 38, t2, 11, fill=MUTED)

    node(32, 92, 230, "Your computer", "lock this one when you leave")
    p.arrow(266, 120, 330, 120, MUTED)
    p.text(298, 108, "RDP", 11, "bold", fill=MUTED, anchor="mm")
    node(334, 92, 290, "Remote PC or virtual machine", "Clickue runs here")
    rows = ((False, "Close the remote-desktop window", "The session is disconnected:",
             "there's no screen to click.", "Clickue waits, retries, then reports Missed."),
            (True, "Hand the session to the console (tscon)", "The desktop stays active",
             "after you leave.", "Clicks keep working."),
            (False, "Lock the remote PC", "Windows blocks clicks and", "screenshots.",
             "Clickue waits, retries, then reports Missed."))
    y = 182
    for ok, a, b1, b2, c in rows:
        p.rect(32, y, 948, y + 66, fill=TINT[GREEN] if ok else TINT[RED], r=8)
        mark(p, 54, y + 33, ok, 11)
        p.text(76, y + 33, a, 13, "bold", anchor="lm")
        p.text(420, y + 22, b1, 12, anchor="lm")
        p.text(420, y + 42, b2, 12, anchor="lm")
        p.text(640, y + 33, c, 12, "medium", fill=GREEN if ok else RED, anchor="lm")
        y += 78
    p.save("remote-sessions.png")


def phone_alert():
    p = Pic(980, 400, "Phone alerts through Discord or Telegram",
            "Pick which events send a message. Each message starts with \"Clickue:\".")
    x0, y0 = 60, 84
    p.rect(x0, y0, x0 + 250, y0 + 290, fill="#111827", r=30)
    p.rect(x0 + 10, y0 + 12, x0 + 240, y0 + 278, fill="#e5e7eb", r=22)
    p.text(x0 + 125, y0 + 34, "14:02", 22, "bold", anchor="mm")
    msgs = (("Clickue: Reconnect: picture was gone, clicked.", "now"),
            ("Clickue: [Daily report] MISSED - couldn't click within 15 min (screen locked or "
             "session disconnected). Moving on to the next scheduled time.", "2 h ago"))
    y = y0 + 66
    for t, when in msgs:
        lines = textwrap.wrap(t, 30)
        hh = 30 + len(lines) * 15
        p.rect(x0 + 20, y, x0 + 230, y + hh, fill=WIN, r=10)
        p.text(x0 + 30, y + 10, "Alerts", 10, "bold")
        p.text(x0 + 220, y + 10, when, 9, fill=MUTED, anchor="ra")
        for i, ln in enumerate(lines):
            p.text(x0 + 30, y + 26 + i * 15, ln, 10)
        y += hh + 10
    ex = 380
    p.text(ex, 100, "Send an alert when…", 14, "bold")
    events = ((True, "A watcher clicked"), (True, "A click was missed or failed"),
              (True, "A job finished (limit reached)"), (False, "Scheduled test results"))
    y = 132
    for on, t in events:
        p.rect(ex, y, ex + 16, y + 16, fill=ACCENT if on else WIN, outline=ACCENT, width=1.5,
               r=3)
        if on:
            p.line([(ex + 4, y + 8), (ex + 7, y + 12), (ex + 13, y + 4)], "#ffffff", 2)
        p.text(ex + 26, y + 8, t, 13, anchor="lm")
        y += 30
    p.para(ex, y + 14, "These are the default choices. Alerts are sent in the background, so "
                       "they never slow down clicking. Use \"Send a test alert\" to check the "
                       "setup.", 12, 60, MUTED)
    p.save("phone-alerts.png")


# ---------------------------------------------------------------- 4.5 pictures
def table(p, x, y, w, cols, rows, row_h=26, head=24, size=10, depth=None, sel=None):
    """A Treeview-like table: cols = ((title, x offset), ...)."""
    h = head + row_h * len(rows)
    p.rect(x, y, x + w, y + h, fill=WIN, outline=LINE, r=4)
    p.rect(x + 1, y + 1, x + w - 1, y + head, fill=SOFT)
    for c, cx in cols:
        p.text(x + 8 + cx, y + head / 2, c, size, "bold", fill=MUTED, anchor="lm")
    for i, r in enumerate(rows):
        ry = y + head + i * row_h
        if sel == i:
            p.rect(x + 1, ry, x + w - 1, ry + row_h, fill=TINT[ACCENT])
        p.line([(x, ry), (x + w, ry)], "#eceff3", 1)
        for k, ((c, cx), val) in enumerate(zip(cols, r)):
            weight = "medium" if k == 2 and depth is not None else "regular"
            p.text(x + 8 + cx, ry + row_h / 2, val, size, weight, anchor="lm",
                   fill=MUTED if k == 1 else FG)
    return y + h


def caret(p, x, y, color=FG):
    """The small ▾ of a drop-down button (drawn: the UI font has it, the picture font doesn't)."""
    p.d.polygon([((x - 4) * S, (y - 2) * S), ((x + 4) * S, (y - 2) * S), (x * S, (y + 3) * S)],
                fill=color)


def small_buttons(p, x, y, labels, size=10):
    for lbl in labels:
        drop = lbl.endswith(" ▾")
        name = lbl[:-2] if drop else lbl
        if drop:
            w = p.tw(name, size, "medium") + 30
            p.rect(x, y, x + w, y + 24, fill=WIN, outline=LINE, r=6)
            p.text(x + 8, y + 12, name, size, "medium", anchor="lm")
            caret(p, x + w - 11, y + 12)
            x = x + w + 5
        else:
            b = button(p, x, y, lbl, size=size, h=24, pad=8)
            x = b[2] + 5
    return x


def record_macro():
    p = Pic(1000, 520, "Recording a macro",
            "Do the task once; the red bar shows you're recording. The steps then open in the "
            "editor, ready to edit.")
    x0, y0 = 32, 92
    cx, cy = window(p, x0, y0, 420, 300, "Weekly report - Example App")
    b = button(p, cx, cy + 4, "Reports", "secondary", 12, 28, 12)
    click_target(p, b, pad=6)
    p.rect(cx, cy + 56, cx + 300, cy + 86, fill=WIN, outline=ACCENT, width=1.5, r=5)
    p.text(cx + 10, cy + 71, "Weekly", 12, anchor="lm")
    bars(p, cx, cy + 110, (360, 300, 330), gap=20, h=8)
    # the recording bar (RecordingIndicator)
    rx, ry = x0 + 74, y0 + 236
    p.rect(rx, ry, rx + 372, ry + 40, fill="#1f2937", outline="#ef4444", width=1.5, r=4)
    p.circle(rx + 18, ry + 20, 6, fill="#ef4444")
    p.text(rx + 32, ry + 20, "REC 0:12 · 5 clicks · 23 keys", 11, "bold", fill="#ffffff",
           anchor="lm")
    # ⏸ Pause
    p.rect(rx + 222, ry + 8, rx + 282, ry + 32, fill="#374151", r=2)
    p.rect(rx + 230, ry + 15, rx + 232, ry + 25, fill="#ffffff")
    p.rect(rx + 235, ry + 15, rx + 237, ry + 25, fill="#ffffff")
    p.text(rx + 242, ry + 20, "Pause", 10, "medium", fill="#ffffff", anchor="lm")
    # ■ Stop
    p.rect(rx + 286, ry + 8, rx + 338, ry + 32, fill="#ef4444", r=2)
    p.rect(rx + 293, ry + 16, rx + 301, ry + 24, fill="#ffffff")
    p.text(rx + 305, ry + 20, "Stop", 10, "medium", fill="#ffffff", anchor="lm")
    # ✕ cancel
    p.rect(rx + 342, ry + 8, rx + 364, ry + 32, fill="#374151", r=2)
    p.line([(rx + 349, ry + 16), (rx + 357, ry + 24)], "#ffffff", 1.5)
    p.line([(rx + 349, ry + 24), (rx + 357, ry + 16)], "#ffffff", 1.5)
    p.text(x0, y0 + 322, "The red recording bar (Clickue's own windows are never recorded).", 11,
           fill=MUTED)
    p.arrow(470, 240, 506, 240, ACCENT, 3, 10)
    # the timeline
    ex = 516
    p.text(ex, 96, "Steps (in the job editor)", 13, "bold")
    cols = (("#", 0), ("At", 26), ("Step", 74), ("Details", 166))
    rows = (("1", "0.5s", "Click", "left click at (412, 300), by picture"),
            ("2", "0.9s", "Wait", "0.7s"),
            ("3", "1.6s", "Type text", "Weekly"),
            ("4", "2.4s", "Press keys", "Enter"),
            ("5", "3.1s", "Scroll", "3 notches down at (700, 500)"),
            ("6", "4.2s", "Drag", "left from (300, 420) to (520, 460) · 0.6s"))
    yb = table(p, ex, 120, 452, cols, rows, size=10, sel=0)
    small_buttons(p, ex, yb + 10, ("+ Add step ▾", "Edit", "Duplicate", "Remove", "▲", "▼"))
    small_buttons(p, ex + 452 - 66, yb + 10, ("More ▾",))
    note_box(p, ex, yb + 52, 452, 92, ACCENT)
    p.para(ex + 14, yb + 62, "Clicks keep a small picture of their spot, so they're checked "
                             "before clicking. Then: remove mouse movements, turn guessed waits "
                             "into \"Wait for a picture\", and test with Dry run and Step "
                             "through.", 11, 70)
    p.save("record-macro.png")


def type_vs_paste():
    p = Pic(1000, 430, "Type text or Paste text?",
            "Both send text to whatever has keyboard focus, so click the field first.")
    for k, title in enumerate(("Type text", "Paste text")):
        x0 = 32 + k * 488
        p.text(x0, 90, title, 15, "bold")
        p.text(x0, 112, ("presses one key per character, like a keyboard" if k == 0 else
                         "uses the clipboard, then puts it back"), 11, fill=MUTED)
        cx, cy = window(p, x0, 134, 450, 160, "New message - Example App")
        p.rect(cx, cy + 6, cx + 420, cy + 96, fill=WIN, outline=ACCENT, width=1.5, r=5)
        if k == 0:
            p.text(cx + 10, cy + 22, "Hello Ann", 12, anchor="lm")
            keys = "a", ",", "⏎"
            for i, ch in enumerate(keys):
                kx = cx + 140 + i * 40
                p.rect(kx, cy + 50, kx + 30, cy + 80, fill=SOFT, outline=LINE, r=4)
                p.text(kx + 15, cy + 65, ch, 12, "medium", anchor="mm")
            p.text(cx + 270, cy + 65, "… one at a time", 11, fill=MUTED, anchor="lm")
        else:
            for i, ln in enumerate(("Hello Anna,", "The report for 2026-10-24 is attached.",
                                    "Grüße · Привет · ✓")):
                p.text(cx + 10, cy + 22 + i * 20, ln, 12, anchor="lm")
            p.text(cx + 410, cy + 82, "all at once", 11, fill=MUTED, anchor="rm")
        ny = 316
        items = ((("~80 characters a second", "Works where pasting is blocked"),
                  ("Up to 20,000 characters", "A new line presses Enter")) if k == 0 else
                 (("1  Your clipboard is saved", "2  Text goes on it (kept out of Win+V history)"),
                  ("3  Ctrl+V (or Shift+Insert)", "4  Your clipboard is put back")))
        for row in range(2):
            for col in range(2):
                p.text(x0 + col * 230, ny + row * 22, items[row][col], 11,
                       "medium" if k == 1 else "regular")
    note_box(p, 32, 370, 936, 40, PURPLE)
    p.text(46, 390, "Tick Secret for passwords: encrypted with your Windows account, hidden, "
                    "never exported or logged. Tick Fill in {variables} for {date} and friends.",
           11, anchor="lm")
    p.save("type-vs-paste.png")


def conditional_workflow():
    p = Pic(1000, 470, "Steps with If, Otherwise and Repeat",
            "Blocks are indented, so you can see which steps belong to which If or Repeat.")
    cols = (("#", 0), ("At", 30), ("Step", 70), ("Details", 236))
    rows = (("1", "", "Set variable", "{count} += “1”  · remembered between runs"),
            ("2", "", "If", "the picture is showing"),
            ("3", "", "    Click", "left click at (640, 410), by picture"),
            ("4", "", "Otherwise", ""),
            ("5", "", "    Use group", "“Sign in”"),
            ("6", "", "End", ""),
            ("7", "", "Repeat until", "the picture is showing · at most 50× / 10m 00s"),
            ("8", "", "    Click", "left click at (300, 220), by picture"),
            ("9", "", "    Wait for picture", "until it goes away · up to 30s, then stop the chain"),
            ("10", "", "End", ""),
            ("11", "", "Paste text", "Report {date}  · fills in {variables}"))
    table(p, 32, 92, 640, cols, rows, row_h=29, size=11, depth=True)
    notes = ((2, 175, "If: runs step 3 only when the picture is showing; Otherwise runs step 5"),
             (7, 291, "Repeat until: again and again, at most 50 times and 10 minutes"),
             (11, 407, "Variables: {count}, {date}, {loop}… filled into text when ticked"))
    for n, yy, t in notes:
        p.line([(676, yy), (700, yy)], ACCENT, 1.5)
        num(p, 712, yy, n)
        p.para(732, yy - 9, t, 11, 34)
    p.save("conditional-workflow.png")


def step_through():
    p = Pic(1000, 470, "Step through: one step at a time",
            "Before each step: what it will do, why that target, and where it will click.")
    x0, y0 = 32, 92
    cx, cy = window(p, x0, y0, 440, 300, "Weekly report - Example App")
    bars(p, cx, cy + 10, (300, 260), gap=20, h=8)
    b = button(p, cx + 20, cy + 70, "Export", "primary", 12, 30, 14)
    crosshair(p, (b[0] + b[2]) / 2, (b[1] + b[3]) / 2, RED, 22)
    p.rect(b[2] + 30, b[1] + 2, b[2] + 92, b[1] + 26, fill="#1f2937", r=4)
    p.text(b[2] + 40, b[1] + 14, "step 3", 11, "bold", fill="#ffffff", anchor="lm")
    # the step-through window
    dx, dy, dw = 500, 92, 468
    window(p, dx, dy, dw, 340, "Step through - Weekly report")
    p.text(dx + 14, dy + 48, "Stepping through “Weekly report”", 12, "bold")
    p.para(dx + 14, dy + 66, "Clickue stops before each step. Drag this window aside if it "
                             "covers what Clickue needs to click.", 10, 78, MUTED)
    p.text(dx + 14, dy + 112, "Next: step 3 · Click: left click at (412, 300), by picture", 11,
           "bold")
    p.para(dx + 14, dy + 132, "Will click at (412, 300), found picture 97%. Finds the saved "
                              "picture; no fallback: if the picture isn't found, nothing is "
                              "clicked.", 10, 80, MUTED)
    p.rect(dx + 14, dy + 172, dx + dw - 14, dy + 246, fill=WIN, outline=LINE, r=4)
    for i, t in enumerate(("✓ step 1 · Wait: waited", "✓ step 2 · Type text: typed")):
        p.text(dx + 24, dy + 186 + i * 18, t, 10, fill=GREEN)
    bb = button(p, dx + 14, dy + 258, "▶ Run this step", "primary", 11, 28, 12)
    button(p, bb[2] + 6, dy + 258, "Run to the end", "secondary", 11, 28, 12)
    button(p, dx + dw - 14 - 70, dy + 258, "■ Stop", "secondary", 11, 28, 12)
    p.para(dx + 14, dy + 296, "“Run to the end” still stops before steps marked ⚠ careful.",
           10, 80, MUTED)
    p.save("step-through.png")


def taking_turns():
    p = Pic(1000, 430, "One mouse: jobs take turns",
            "Clicks and keys from all jobs go through one queue. Watchers keep looking meanwhile.")
    x0 = 32
    p.rect(x0, 92, 968, 124, fill=WIN, outline=LINE, r=4)
    p.text(x0 + 12, 108, "▶ Running “Daily report” · step 3 of 8 · 42s · Waiting their turn: "
                         "Reconnect", 12, fill=MUTED, anchor="lm")
    button(p, 968 - 128, 96, "■ Stop this run", size=11, h=24, pad=10)
    lanes = (("Mouse & keyboard", 170), ("Watchers (only look)", 260))
    for name, ly in lanes:
        p.text(x0, ly, name, 12, "bold", anchor="lm")
        p.line([(200, ly), (960, ly)], LINE, 1)
    # input lane blocks
    blocks = (("Daily report: click → wait for Export… → Save", 220, 640, ACCENT),
              ("Reconnect", 652, 760, GREEN), ("Refresh", 772, 850, PURPLE))
    for t, a, b, col in blocks:
        p.rect(a, 152, b, 188, fill=TINT[col], outline=col, width=1.5, r=6)
        p.text((a + b) / 2, 170, t, 11, "medium", fill=col, anchor="mm")
    for t in range(230, 950, 40):
        p.circle(t, 260, 5, fill=ACCENT)
    p.text(430, 290, "checks continue every few seconds, even while a job uses the mouse", 11,
           fill=MUTED, anchor="mm")
    p.arrow(470, 250, 650, 194, GREEN, 2, 8)
    p.text(668, 222, "Reconnect's watcher saw the change, so its click waits its turn", 10,
           fill=GREEN, anchor="lm")
    note_box(p, 32, 318, 936, 88, ACCENT)
    p.para(46, 328, "Windows has one mouse pointer and one keyboard focus, so two jobs clicking "
                    "at once would collide. Priority (High / Normal / Low) decides who goes first; "
                    "\"Let other jobs click in between\" lets a waiting job step aside; Ctrl+Alt+X "
                    "stops everything. Running jobs side by side on separate desktops or VMs is "
                    "planned.", 11, 140)
    p.save("taking-turns.png")


def run_history():
    p = Pic(1000, 520, "Run history and screen video",
            "Every run and its steps, with where each step is in the run's video.")
    x0, y0 = 32, 92
    window(p, x0, y0, 620, 400, "Run history")
    p.text(x0 + 14, y0 + 52, "Search", 11, anchor="lm")
    p.rect(x0 + 64, y0 + 40, x0 + 260, y0 + 64, fill=WIN, outline=LINE, r=3)
    p.rect(x0 + 276, y0 + 45, x0 + 290, y0 + 59, outline=MUTED, r=2)
    p.text(x0 + 298, y0 + 52, "Only failed runs", 11, anchor="lm")
    cols = (("Started", 0), ("Job", 140), ("Took", 280), ("Result", 330), ("Video", 530))
    rows = (("2026-10-24 07:45:02", "Daily report", "6.1s", "ok", "yes"),
            ("2026-10-23 07:45:01", "Daily report", "38s", "failed: step 3 (click): not found", "yes"),
            ("2026-10-23 06:12:40", "Reconnect", "0.8s", "ok", ""))
    yb = table(p, x0 + 14, y0 + 74, 592, cols, rows, row_h=24, size=10, sel=1)
    p.text(x0 + 14, yb + 16, "Steps of the selected run", 11, "bold")
    cols = (("After", 0), ("Video", 52), ("#", 104), ("Action", 134), ("Result", 430))
    rows = (("0s", "0:00", "", "Run started", ""),
            ("0.4s", "0:00", "0", "Click: left at (412, 300), picture 97%", "ok"),
            ("1.2s", "0:01", "1", "Type text: 12 characters", "ok"),
            ("31s", "0:31", "2", "Wait for picture: until it appears", "ok"),
            ("38s", "0:38", "3", "Click: left click at (300, 220), by picture", "failed"))
    yb2 = table(p, x0 + 14, yb + 30, 592, cols, rows, row_h=22, size=10, sel=4)
    button(p, x0 + 14, yb2 + 10, "▶ Play video from this step", "primary", 11, 26, 12)
    # the video player
    vx, vy = 680, 92
    window(p, vx, vy, 288, 230, "Video")
    p.rect(vx + 12, vy + 42, vx + 276, vy + 180, fill="#d1d5db", r=3)
    p.rect(vx + 60, vy + 60, vx + 230, vy + 160, fill=WIN, outline=LINE, r=4)
    bars(p, vx + 72, vy + 76, (120, 90), gap=14, h=6)
    p.rect(vx + 150, vy + 132, vx + 220, vy + 152, fill=TINT[RED], outline=RED, r=3)
    p.rect(vx + 12, vy + 188, vx + 276, vy + 192, fill=LINE, r=2)
    p.rect(vx + 12, vy + 188, vx + 175, vy + 192, fill=ACCENT, r=2)
    p.text(vx + 14, vy + 210, "▶ Play  −5 s  +5 s", 10, "medium", anchor="lm")
    p.text(vx + 274, vy + 210, "0:38 / 0:40", 10, fill=MUTED, anchor="rm")
    # the recording indicator
    p.rect(vx, 340, vx + 288, 364, fill="#7f1d1d", r=3)
    p.text(vx + 8, 352, "● Recording the screen: Daily report", 9, "bold", fill="#ffffff",
           anchor="lm")
    p.para(vx, 378, "While a run is recorded, this red bar shows at the top of the screen, "
                    "with Pause video and Stop video. Videos stay on this computer.", 10, 46,
           MUTED)
    p.save("run-history.png")


# ---------------------------------------------------------------- 4.5.1
def exact_matching():
    p = Pic(980, 400, "Only the exact picture (on by default)",
            "The button you picked must be on screen. A similar-looking button is never clicked.")
    p.text(32, 92, "Saved picture", 12, "bold", fill=MUTED)
    sx, sy = 40, 120
    p.rect(sx - 12, sy - 12, sx + 196, sy + 42, fill=WIN, outline=LINE, r=6)
    b0 = button(p, sx, sy, "Save", size=12)
    b1 = button(p, b0[2] + 8, sy, "Refresh", size=12)
    capture(p, (sx - 8, sy - 8, sx + 192, sy + 38), ACCENT, pad=0)
    crosshair(p, (b1[0] + b1[2]) / 2, (b1[1] + b1[3]) / 2, RED, 9)
    cases = (("Same picture", "Clicked", True, "Refresh", True),
             ("Same, other display scaling", "Clicked (checked again at its size)", True,
              "Refresh", "big"),
             ("A different button there", "Not clicked: \"Reload\" isn't \"Refresh\"", False,
              "Reload", True),
             ("Your button scrolled off-screen", "Not clicked: only a look-alike is visible",
              False, "Refresh", False))
    x = 270
    for i, (t1, t2, good, label, where) in enumerate(cases):
        cx = x + (i % 2) * 350
        cy = 92 + (i // 2) * 140
        p.text(cx, cy, t1, 12, "bold")
        p.rect(cx, cy + 22, cx + 320, cy + 92, fill=WIN, outline=LINE, r=6)
        if where is False:
            bars(p, cx + 14, cy + 36, (200, 150), gap=18, h=8)
            button(p, cx + 230, cy + 58, "Refresh", size=11, h=24, pad=8)
            p.text(cx + 14, cy + 74, "(the toolbar is out of view)", 10, fill=MUTED)
        elif where == "big":
            bb0 = button(p, cx + 14, cy + 34, "Save", size=15, h=38)
            button(p, bb0[2] + 10, cy + 34, label, size=15, h=38)
        else:
            bb0 = button(p, cx + 14, cy + 42, "Save", size=12)
            button(p, bb0[2] + 8, cy + 42, label, size=12)
        mark(p, cx + 10, cy + 112, good)
        p.text(cx + 26, cy + 104, t2, 12, fill=GREEN if good else RED)
    note_box(p, 32, 352, 916, 34, ACCENT)
    p.text(46, 369, "Nothing to click is the safe outcome: the job waits and tries again. "
                    "Untick \"Only the exact picture\" for the older, more tolerant matching.",
           12, anchor="lm")
    p.save("exact-matching.png")


def similar_outlines():
    p = Pic(980, 440, "Point out every similar picture (Preferences → Clicking)",
            "Show spot and Check now can outline everything that looks like your picture.")
    cx, cy = window(p, 32, 84, 640, 330, "Example App")
    tb = [button(p, cx + 6, cy + 6, "Save", size=12)]
    tb.append(button(p, tb[-1][2] + 8, cy + 6, "Refresh", size=12))
    bars(p, cx + 6, cy + 70, (420, 380, 400, 300), gap=24, h=9)
    r2 = button(p, cx + 300, cy + 176, "Reload", size=12)
    r3 = button(p, cx + 40, cy + 200, "Refresh all", size=12)

    def outline(box, col, label):
        x0, y0, x1, y1 = box[0] - 5, box[1] - 5, box[2] + 5, box[3] + 5
        p.rect(x0, y0, x1, y1, outline=col, width=2.5, r=3)
        w = p.tw(label, 10, "bold") + 12
        p.rect(x0, y0 - 18, x0 + w, y0, fill=col, r=2)
        p.text(x0 + 6, y0 - 9, label, 10, "bold", fill="#111827", anchor="lm")
    outline(tb[1], "#22c55e", "exact 100%")
    crosshair(p, (tb[1][0] + tb[1][2]) / 2, (tb[1][1] + tb[1][3]) / 2, RED, 11)
    outline(r2, "#9ca3af", "similar 74%")
    outline(r3, "#9ca3af", "similar 68%")
    p.rect(cx + 6, cy + 250, cx + 600, cy + 300, fill="#111827", r=6)
    p.text(cx + 18, cy + 262, "Watcher  ·  found by exact picture 100%", 11, "bold", fill="#ffffff")
    p.text(cx + 18, cy + 282, "Green = used · orange = same picture, not used · grey = similar, "
                              "ignored", 10, fill="#cbd5e1")
    ex = 700
    y = 100
    for col, t in (("#22c55e", "Green: the place that would be clicked."),
                   ("#f59e0b", "Orange: the same picture somewhere else (not used)."),
                   ("#9ca3af", "Grey: looks similar, but isn't your picture (ignored)."),
                   (ACCENT, "Marks stay for 5 seconds; change it in Preferences → Clicking "
                            "(1-120 s). Click a mark or press Esc to close sooner.")):
        p.rect(ex, y + 2, ex + 14, y + 16, fill=col, r=3)
        y = p.para(ex + 24, y, t, 12, 28) + 14
    p.save("similar-pictures.png")


def pick_cancel():
    p = Pic(980, 300, "Pick on screen: Esc or Cancel",
            "Point at the spot. Changed your mind? Press Esc or click Cancel - nothing changes.")
    x0, y0 = 32, 96
    p.rect(x0, y0, x0 + 560, y0 + 96, fill="#1f2937", outline="#3b82f6", width=1.5, r=4)
    p.text(x0 + 20, y0 + 18, "Point at the spot to click…", 15, "bold", fill="#ffffff")
    p.text(x0 + 20, y0 + 42, "Capturing in 3    (812, 344)", 15, "bold", fill="#ffffff")
    p.text(x0 + 20, y0 + 72, "Drag this box to move it. It moves aside if your mouse rests "
                             "near it. Esc cancels.", 10, fill="#9ca3af")
    cb = (x0 + 420, y0 + 16, x0 + 545, y0 + 46)
    p.rect(*cb, fill="#dc2626", r=3)
    p.text((cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2, "×  Cancel (Esc)", 12, "bold",
           fill="#ffffff", anchor="mm")
    cursor(p, cb[0] + 60, cb[1] + 18)
    ex = 630
    y = 100
    for t in ("Esc works from anywhere, even if another window has the focus.",
              "The countdown waits while the mouse is on Cancel, so it never picks the "
              "button itself.",
              "The same works in Draw box around picture and Draw area (or right-click).",
              "After picking or cancelling, the editor comes back exactly where it was."):
        p.circle(ex + 5, y + 8, 3, fill=ACCENT)
        y = p.para(ex + 16, y, t, 12, 40) + 12
    p.save("pick-cancel.png")


def tray_status():
    p = Pic(980, 380, "Job status on the tray icon",
            "Point at Clickue's tray icon to see what your jobs are doing while it's minimized.")
    tx, ty = 32, 96
    p.rect(tx, ty, tx + 420, ty + 138, fill="#2b2b2b", r=6)
    lines = ("Clickue: 3 active · 1 needs attention",
             "▶ Running “Refresh dashboard” · step 2 of 4",
             "⚠ Reconnect watcher: Picture missing",
             "✓ Refresh dashboard: Running · next in 4m 10s",
             "✓ Stay signed in: Watching · Not showing")
    for i, l in enumerate(lines):
        p.text(tx + 14, ty + 16 + i * 23, l, 12, "bold" if i == 0 else "regular",
               fill="#ffffff")
    # taskbar
    p.rect(32, 250, 948, 290, fill="#1f2937", r=4)
    for k in range(4):
        p.rect(760 + k * 32, 260, 782 + k * 32, 280, fill="#374151", r=4)
    p.circle(889, 270, 9, fill=ACCENT)
    p.text(889, 270, "C", 10, "bold", fill="#ffffff", anchor="mm")
    cursor(p, 886, 268)
    p.arrow(452, 170, 870, 252, MUTED)
    # menu
    mx, my = 520, 84
    p.rect(mx, my, mx + 210, my + 150, fill=WIN, outline=LINE, r=6)
    for i, t in enumerate(("Show window", "Job status  ›", "Pause all", "Stop everything now",
                           "Exit")):
        if i == 1:
            p.rect(mx + 4, my + 6 + i * 28, mx + 206, my + 30 + i * 28, fill="#dbeafe", r=4)
        p.text(mx + 14, my + 18 + i * 28, t, 12, "medium", anchor="lm")
    sx = mx + 214
    p.rect(sx, my + 34, sx + 230, my + 130, fill=WIN, outline=LINE, r=6)
    for i, t in enumerate(("⚠ Reconnect watcher: Picture missing", "✓ Refresh dashboard: Running",
                           "✓ Stay signed in: Watching")):
        p.text(sx + 12, my + 52 + i * 26, t, 11, anchor="lm")
    p.text(32, 312, "Right-click the icon → Job status lists every active job. Turn it off in "
                    "Preferences → General.", 12, fill=MUTED)
    p.text(32, 334, "Order: problems first (failed, then needs attention), then working, "
                    "then paused.", 12, fill=MUTED)
    p.save("tray-status.png")


if __name__ == "__main__":
    for fn in (main_window_layout, good_and_bad_spots, picture_sizes, schedule_timeline,
               active_hours, watcher_disappears, watcher_appears, strict_matching, search_area,
               flicker_protection, click_once, click_chain, multi_step_search, show_spot,
               remote_sessions, phone_alert, record_macro, type_vs_paste, conditional_workflow,
               step_through, taking_turns, run_history, exact_matching, similar_outlines,
               pick_cancel, tray_status, batch_actions, partial_matching, draw_zoom):
        fn()
