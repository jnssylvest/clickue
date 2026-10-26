"""Clickue 4 features: hours, limits, steps, appears/area, history, backups, undo, alerts, migration. Expect: RESULT 97/97"""
import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_helpers.py")).read())
import time, threading, queue, tempfile, json, os
from datetime import datetime, timedelta
d = tempfile.mkdtemp()
for k, v in (("DATA_DIR", d), ("SETTINGS_PATH", d + "/s.json"), ("JOBS_PATH", d + "/j.json"),
             ("LOG_PATH", d + "/a.log"), ("TESTS_PATH", d + "/t.json"),
             ("HISTORY_PATH", d + "/h.csv"), ("BACKUP_DIR", d + "/backups")):
    setattr(ac, k, v)
A = object.__new__(ac.App)
A.lock = threading.RLock(); A.logq = queue.Queue(); A.wait_msgs = {}; A.res_warned = set()
A.tray = None; A.uninstalled = False; A.settings = dict(ac.DEFAULT_SETTINGS); A.jobs = []
A.setup_logging(); A.own_visible = False; A.test_history = []; A.tests_dirty = False
A.stop = threading.Event(); A.cmdq = queue.Queue(); A.undo_stack = []
A.refresh_tree = lambda *a, **k: None; A.update_buttons = lambda: None
ac.screen_available = lambda: True; ac.idle_seconds = lambda: 100; ac.system_dpi = lambda: 96
R = []


def ok(name, cond, info=""):
    R.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name, info if not cond or info else "")


clicks, typed, keys = [], [], []
ac.do_click = lambda x, y, *a, **k: (clicks.append((x, y)) or (True, "clicked"))
ac.send_text = lambda t: (typed.append(t) or (True, "typed"))
ac.press_keys = lambda c: (keys.append(c) or (True, "pressed"))

# ---------------------------------------------------------------- active hours
def ts(h, m=0, day=0):     # day 0 = a Monday
    base = datetime(2026, 10, 19)   # Monday
    return (base + timedelta(days=day, hours=h, minutes=m)).timestamp()

j = ac.new_job(); j.update(hours_on=True, hours_from="08:00", hours_to="22:00", hours_days=[0, 1, 2, 3, 4])
ok("hours: Mon 09:00 active", ac.in_active_hours(j, ts(9)))
ok("hours: Mon 23:00 not active", not ac.in_active_hours(j, ts(23)))
ok("hours: Sat 10:00 not active (weekday only)", not ac.in_active_hours(j, ts(10, day=5)))
nxt = ac.next_active_start(j, ts(23))
ok("hours: next start after Mon 23:00 is Tue 08:00", datetime.fromtimestamp(nxt) == datetime(2026, 10, 20, 8, 0))
nxt = ac.next_active_start(j, ts(23, day=4))
ok("hours: next start after Fri night is Mon 08:00", datetime.fromtimestamp(nxt) == datetime(2026, 10, 26, 8, 0))
j2 = ac.new_job(); j2.update(hours_on=True, hours_from="22:00", hours_to="06:00", hours_days=[0])
ok("overnight: Mon 23:00 active", ac.in_active_hours(j2, ts(23)))
ok("overnight: Tue 03:00 active (Mon's night)", ac.in_active_hours(j2, ts(3, day=1)))
ok("overnight: Tue 23:00 not active", not ac.in_active_hours(j2, ts(23, day=1)))
ok("hours off -> always active", ac.in_active_hours(ac.new_job(), ts(3)))
ok("describe hours", ac.describe_hours(j) == "08:00–22:00 Mon–Fri", ac.describe_hours(j))

# scheduled click outside hours: wait / skip
c = ac.new_job(1); c.update(x=10, y=10, use_image=False, interval_s=3600, random_on=False,
                            hours_on=True, hours_from="00:00", hours_to="00:01",
                            hours_days=[(datetime.now().weekday() + 3) % 7])
A.jobs = [c]; A.start_job(c); c["next_run"] = time.time() - 1
A.execute(c, "scheduled")
ok("outside hours (wait): no click, moved to next active start", not clicks and c["next_run"] > time.time() + 3600,
   fmt := ac.fmt_time(c["next_run"]))
c["hours_outside"] = "skip"; c["next_run"] = time.time() - 1; A.execute(c, "scheduled")
ok("outside hours (skip): no click, next slot", not clicks and "Skipped" in c["last_result"])

# ---------------------------------------------------------------- limits
c = ac.new_job(2); c.update(x=10, y=10, use_image=False, interval_s=60, random_on=False,
                            limit_clicks_on=True, limit_clicks=3)
A.jobs = [c]; A.start_job(c)
for i in range(5):
    if c["enabled"]:
        c["next_run"] = time.time() - 1; A.execute(c, "scheduled")
ok("limit: stops after 3 clicks", len(clicks) == 3 and not c["enabled"] and "Finished" in c["last_result"],
   (len(clicks), c["last_result"]))
clicks.clear()
c = ac.new_job(3); c.update(x=1, y=1, use_image=False, limit_until_on=True,
                            limit_until=(datetime.now() - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"))
A.jobs = [c]; A.start_job(c)
A.stop.clear(); th = threading.Thread(target=A.scheduler_loop, daemon=True); th.start(); time.sleep(1.4); A.stop.set(); th.join(2)
ok("limit: stops at end time", not c["enabled"] and "end time" in c["last_result"], c["last_result"])

# ---------------------------------------------------------------- extra steps
clicks.clear()
c = ac.new_job(4); c.update(x=50, y=60, use_image=False, steps=[
    {"type": "click", "x": 200, "y": 210, "use_image": False, "button": "left", "clicks": 1, "target_mode": "screen"},
    {"type": "wait", "min": 1, "max": 1},
    {"type": "type", "text": "hello\nworld"},
    {"type": "key", "keys": "Ctrl+S"}])
A.jobs = [c]
A.stop.clear(); t0 = time.time(); okk, msg, *_ = A.perform(c, check_idle=False)
ok("steps: main click + step click + type + keys, in order", okk and clicks == [(50, 60), (200, 210)]
   and typed == ["hello\nworld"] and keys == ["Ctrl+S"] and time.time() - t0 >= 1, msg)
c["steps"].insert(0, {"type": "click", "x": 0, "y": 0, "use_image": True, "snap_png": "", "button": "left"})
ok("parse_combo works", ac.parse_combo("Ctrl+Shift+S") == [0x11, 0x10, 0x53] and ac.parse_combo("Enter") == [0x0D])
try:
    ac.parse_combo("Ctrl+Banana"); bad = False
except ValueError:
    bad = True
ok("parse_combo rejects unknown keys", bad)
ok("parse_hotkey", ac.parse_hotkey("Ctrl+Alt+P") == (0x3, ord("P")))
try:
    ac.parse_hotkey("P"); bad = False
except ValueError:
    bad = True
ok("parse_hotkey needs a modifier", bad)

# ---------------------------------------------------------------- watcher: appears trigger, click picture, area
img, _ = draw_app(1.0, 1920, 1080, 200, 150)
dd = ImageDraw.Draw(img); dd.rounded_rectangle((720, 530, 880, 560), radius=6, fill=(22, 163, 74))
dd.text((732, 536), "● CONNECTED", fill="white", font=F(13))
crop = img.crop((710, 525, 890, 565)); gone, _ = draw_app(1.0, 1920, 1080, 200, 150)
clicks.clear()
w = ac.new_watch(1); w.update(watch_png=ac.img_to_b64(crop), x=300, y=300, use_image=False,
                              watch_interval_s=10, watch_random_on=False, watch_trigger="appears",
                              watch_click_picture=True, watch_cooldown_on=False)
A.jobs = [w]; A.start_job(w)
def show(im): ac.grab_screen = lambda move_cursor=True, im=im: (im, (0, 0))
def check(): w["next_check"] = 0; A.watch_check(w)
def tick():
    if w.get("pending_click_at"):
        w["pending_click_at"] = 0; A.watch_click(w)
show(gone); check(); check()
ok("appears: nothing showing -> no click", not w["pending_click_at"] and not clicks)
show(img); check(); ok("appears: first sighting -> confirming", not w["pending_click_at"])
check(); ok("appears: confirmed -> click pending", w["pending_click_at"])
tick(); ok("appears: clicked the picture itself", clicks and abs(clicks[-1][0] - 800) <= 3 and abs(clicks[-1][1] - 545) <= 3, clicks)
check(); check(); tick(); ok("appears + once: still showing -> no 2nd click", len(clicks) == 1)
show(gone); check(); show(img); check(); check(); tick(); ok("appears again -> clicks again", len(clicks) == 2)
# picture vanished before the click
show(gone); check(); show(img); check(); check(); show(gone); tick()
ok("appears: picture went away before the click -> no click", len(clicks) == 2 and "went away" in w["last_result"])
# area
w2 = ac.new_watch(2); w2.update(watch_png=ac.img_to_b64(crop), watch_area=[600, 450, 400, 200],
                                watch_area_screen=list(ac.virtual_screen()[2:]))
r = ac.picture_on_screen(w2["watch_png"], area=ac.job_area(w2), shot=(img, (0, 0)))
ok("area: found inside the area", r[0] and abs(r[1] - 800) <= 3, r)
w2["watch_area"] = [0, 0, 400, 300]
r = ac.picture_on_screen(w2["watch_png"], area=ac.job_area(w2), shot=(img, (0, 0)))
ok("area: not found when it's outside the area", not r[0])
ok("describe watch", ac.describe_watch(dict(w2, watch_trigger="appears")).startswith("When picture appears"), ac.describe_watch(w2))
# gone trigger still behaves as before (quick)
clicks.clear()
g = ac.new_watch(3); g.update(watch_png=ac.img_to_b64(crop), x=300, y=300, use_image=False,
                              watch_random_on=False)
A.jobs = [g]; A.start_job(g)
show(img); g["next_check"] = 0; A.watch_check(g); show(gone)
for _ in range(2):
    g["next_check"] = 0; A.watch_check(g)
g["pending_click_at"] = 0; A.watch_click(g)
ok("gone trigger still clicks the button", clicks == [(300, 300)])
# dry run wording for appears
w["watch_click_picture"] = True; show(img)
rr = A.watcher_dry_run(w); txt, lvl = A.describe_dry_run(rr)
ok("dry run (appears, showing): WOULD click the picture", "WOULD click" in txt and "picture itself" in txt, txt)
show(gone); rr = A.watcher_dry_run(w); txt, lvl = A.describe_dry_run(rr)
ok("dry run (appears, not showing): would NOT click", "would NOT click" in txt, txt)

# ---------------------------------------------------------------- history, stats, backups, undo
rows = ac.read_history()
ok("history written", len(rows) >= 5, len(rows))
st = ac.job_stats(rows, "Watcher 1")
ok("stats for a job", st["total"] == 2 and st["kinds"]["watcher"] == 2, st)
p1 = A.backup_now(); bl = ac.list_backups()
ok("backup made and listed", bl and bl[0]["jobs"] == len(A.jobs), bl[:1])
for i in range(5):
    ac.make_backup(A.jobs, A.settings, "auto"); time.sleep(1.05)
ac.prune_backups(3)
ok("old daily backups pruned", sum(1 for b in ac.list_backups() if b["tag"] == "auto") == 3)
n_before = len(A.jobs)
A.restore_backup(p1, replace=False)
ok("restore adds jobs", len(A.jobs) == n_before * 2)
A.jobs = [w, g]; A.save()
A.undo_stack.append((w, 0, True)); A.jobs = [g]; A.show_undo_bar = lambda: None
A.undo_delete()
ok("undo delete restores the job", A.jobs[0] is w and w["enabled"])

# ---------------------------------------------------------------- alerts (no network: fake POST)
sent = []
ac._http_post = lambda url, body, ctype: (sent.append(url), 200)[1]
HOOK = "https://discord.com/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyz_ABCDEF-123"
TOKEN = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_0123456"
res = ac.send_alert({"alert_discord": HOOK, "alert_tg_token": TOKEN, "alert_tg_chat": "1"}, "hello")
ok("alerts: Discord + Telegram sent", [r[0] for r in res] == ["Discord", "Telegram"] and all(r[1] for r in res), res)
ok("alerts: nothing configured -> clear message", ac.send_alert({}, "x")[0][2] == "no service set up")
A.settings.update(alerts_on=True, alert_discord=HOOK, alert_tg_token="", alert_tg_chat="",
                  alert_events={"watch": True, "problem": False})
ac._ALERT_SENT.clear(); sent.clear(); A.notify("watch fired", "watch"); A.notify("problem", "problem"); time.sleep(0.5)
ok("alerts: only chosen events are sent", len(sent) == 1, sent)
A.settings.update(alerts_on=False)

# ---------------------------------------------------------------- migration from the old name
old = tempfile.mkdtemp(); new = os.path.join(tempfile.mkdtemp(), "Clickue")
open(os.path.join(old, "jobs.json"), "w").write('{"jobs": [{"name": "old job"}]}')
open(os.path.join(old, "autoclicker.log"), "w").write("old log")
ac.DATA_DIR, ac.OLD_DATA_DIR = new, old
ok("migration copies the old folder", ac.migrate_old_data() and os.path.exists(os.path.join(new, "jobs.json"))
   and os.path.exists(os.path.join(old, "jobs.json")))
ok("migration only once", not ac.migrate_old_data())

# ---------------------------------------------------------------- v4.2: ask before reusing old jobs
fold = tempfile.mkdtemp()
ok("count_saved_jobs: none", ac.count_saved_jobs(fold) == 0)
json.dump({"jobs": [{"name": "a"}, {"name": "b"}]}, open(os.path.join(fold, "jobs.json"), "w"))
ok("count_saved_jobs: 2", ac.count_saved_jobs(fold) == 2)
empty_old = tempfile.mkdtemp(); new2 = os.path.join(tempfile.mkdtemp(), "Clickue")
ac.DATA_DIR, ac.OLD_DATA_DIR = new2, empty_old
ok("migration skipped when the old folder has no jobs", not ac.migrate_old_data() and not os.path.exists(new2))
inst = tempfile.mkdtemp(); ac.INSTALL_MARKER = os.path.join(inst, "install.ini")
ok("no install.ini -> no install id (portable/source)", ac.read_install_id() == "")
open(ac.INSTALL_MARKER, "w").write("[Install]\nId=20261024162500\n")
ok("install.ini -> install id", ac.read_install_id() == "20261024162500")

# ---------------------------------------------------------------- v4.3: click chains ("wait for a picture" steps)
ac.STEP_POLL_S = 0.05
A.stop.clear(); clicks.clear(); typed.clear()
btn_img, _ = draw_app(1.0, 1920, 1080, 200, 150)
db = ImageDraw.Draw(btn_img)
db.rounded_rectangle((1300, 700, 1460, 740), radius=6, fill=(37, 99, 235))
db.text((1325, 710), "EXPORT", fill="white", font=F(16))
export_png = ac.img_to_b64(btn_img.crop((1290, 690, 1470, 750)))
plain, _ = draw_app(1.0, 1920, 1080, 200, 150)
frames = {"n": 0}
def screen_seq():          # the button shows up on the 3rd look
    frames["n"] += 1
    return (btn_img if frames["n"] >= 3 else plain), (0, 0)
ac.grab_screen = lambda move_cursor=True: screen_seq()
chain = ac.new_job(9); chain.update(name="Chain", x=10, y=10, use_image=False, steps=[
    {"type": "waitpic", "png": export_png, "until": "appears", "click_it": True, "timeout": 5},
    {"type": "type", "text": "report"}])
A.jobs = [chain]
okk, msg, *_ = A.perform(chain, check_idle=False)
ok("chain: click, wait for the button to appear, click it, then type",
   okk and len(clicks) == 2 and abs(clicks[1][0] - 1380) <= 3 and abs(clicks[1][1] - 720) <= 3
   and typed == ["report"] and frames["n"] >= 3, (msg, clicks, frames["n"]))
clicks.clear(); typed.clear()
ac.grab_screen = lambda move_cursor=True: (plain, (0, 0))
chain["steps"][0]["timeout"] = 1
t0 = time.time(); okk, msg, *_ = A.perform(chain, check_idle=False)
ok("chain: picture never appears -> stops after the timeout, rest skipped",
   okk and "timeout" in msg and typed == [] and 0.9 <= time.time() - t0 < 3, msg)
chain["steps"][0]["on_timeout"] = "continue"
okk, msg, *_ = A.perform(chain, check_idle=False)
ok("chain: timeout set to 'continue' -> carries on", typed == ["report"], msg)
typed.clear(); clicks.clear()
seq = {"n": 0}
def going():
    seq["n"] += 1
    return (btn_img if seq["n"] < 3 else plain), (0, 0)
ac.grab_screen = lambda move_cursor=True: going()
chain["steps"][0].update(until="disappears", click_it=True, timeout=5, on_timeout="stop")
okk, msg, *_ = A.perform(chain, check_idle=False)
ok("chain: wait until it goes away (no extra click), then continue",
   len(clicks) == 1 and typed == ["report"], (msg, clicks))

# ---- the complete guide: menu link points to a guide that exists, and opens it
import webbrowser
repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rel = ac.GUIDE_URL.split("/blob/main/", 1)[-1]
ok("guide: link points at a file in the repository",
   ac.GUIDE_URL.startswith(ac.REPO_URL + "/blob/main/") and os.path.isfile(os.path.join(repo, rel)),
   ac.GUIDE_URL)
opened = []
webbrowser.open = lambda url, new=0: opened.append(url) or True
A.open_guide()
ok("guide: menu item opens the guide in the browser", opened == [ac.GUIDE_URL], opened)
guide = open(os.path.join(repo, rel), encoding="utf-8").read()
import re
missing = [m for m in re.findall(r"\]\((images/[^)]+)\)", guide)
           if not os.path.isfile(os.path.join(repo, "docs", m))]
ok("guide: every example picture exists", not missing and "images/guide/" in guide, missing)

# ---- 4.5.3: tick boxes and batch actions (start / stop / pause / resume / delete / edit)
A.checked = set(); A.show_undo_bar = lambda: None
c1, c2 = ac.new_job(1), ac.new_job(2)
for c in (c1, c2):
    c.update(x=5, y=5, use_image=False, interval_s=600, random_on=False)
w1 = ac.new_watch(1); w1["watch_png"] = "x"
A.jobs = [c1, c2, w1]
A.checked = {c1["id"], w1["id"]}
ok("batch: ticked jobs are the ones in the list", [j["id"] for j in A.checked_jobs()] == [c1["id"], w1["id"]])
n = A.batch_action("start")
ok("batch: start starts every ticked job (only those)", n == 2 and c1["enabled"] and w1["enabled"] and not c2["enabled"])
n = A.batch_action("pause")
ok("batch: pause keeps them enabled, paused", n == 2 and c1["paused"] and w1["paused"] and c1["next_run"])
n = A.batch_action("pause")
ok("batch: pausing again skips them", n == 0)
n = A.batch_action("resume")
ok("batch: resume", n == 2 and not c1["paused"] and not w1["paused"])
rep = A.apply_batch_edit(A.checked_jobs(), {"button": "right", "interval_s": 120, "watch_interval_s": 7,
                                            "watch_match": "partial", "watch_partial_pct": 80, "bogus": 1})
ok("batch edit: common setting applies to both kinds", c1["button"] == "right" and w1["button"] == "right", rep)
ok("batch edit: click-only and watcher-only settings go to the right kind",
   c1["interval_s"] == 120 and w1["interval_s"] == ac.new_job()["interval_s"] and w1["watch_interval_s"] == 7
   and "watch_interval_s" not in rep.get(c1["name"], []), rep)
ok("batch edit: running click job rescheduled with the new interval", c1["next_run"] and c1["next_run"] - time.time() <= 121)
ok("batch edit: watcher match mode set, unknown keys dropped", w1["watch_match"] == "partial" and w1["watch_partial_pct"] == 80 and "bogus" not in w1)
A.batch_action("pause"); A.apply_batch_edit([w1], {"watch_interval_s": 9})
ok("batch edit: a paused watcher stays paused", w1["paused"] and w1["watch_interval_s"] == 9)
A.apply_batch_edit([c1, c2], {"delay_min_s": 1200, "random_on": True})
ok("batch edit: delay 'from' above a job's 'to' -> 'to' raised to match", c2["delay_max_s"] == c2["delay_min_s"] == 1200)
A.apply_batch_edit([c1], {"interval_s": -5, "priority": "urgent", "hours_from": "99:99"})
ok("batch edit: values validated like an import", c1["interval_s"] >= 1 and c1["priority"] in ("high", "normal", "low") and c1["hours_from"] == "08:00", (c1["interval_s"], c1["priority"], c1["hours_from"]))
n = A.batch_action("duplicate")
ok("batch: duplicate makes stopped copies and ticks them", n == 2 and len(A.jobs) == 5 and len(A.checked) == 2
   and all(not j["enabled"] for j in A.checked_jobs()))
A.checked = {c1["id"], c2["id"], w1["id"]}
n = A.delete_jobs(A.checked_jobs())
ok("batch: delete removes all ticked jobs", n == 3 and len(A.jobs) == 2 and not A.checked)
A.undo_delete()
ok("batch: one undo brings them all back, in place, running again", [j["id"] for j in A.jobs[:3]] == [c1["id"], c2["id"], w1["id"]] and c1["enabled"] and w1["enabled"])
A.checked = {c1["id"]}; A.batch_action("stop")
ok("batch: stop", not c1["enabled"])

# ---- 4.5.6: moving the mouse like a person, settings resolution, palettes, deleting history
import random as _r
pts = ac.human_path(100, 100, 900, 500, "normal", _r.Random(5))
ok("human path ends exactly on the target", pts[-1][1:] == (900, 500), pts[-1])
ok("human path takes a human-like time (0.15-1.4 s) and has many small steps",
   0.15 <= pts[-1][0] <= 1.4 and len(pts) >= 10, (pts[-1][0], len(pts)))
mid = pts[len(pts) // 2]
line_y = 100 + (mid[1] - 100) * 400 / 800
ok("human path is not a straight jump (it curves or eases)", len({p[1] for p in pts}) > 5)
steps = [abs(pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1)]
ok("human path is slow at the start and end, quick in the middle",
   max(steps[:2]) < max(steps) and max(steps[-3:]) < max(steps), (steps[:3], max(steps), steps[-3:]))
slow = ac.human_path(0, 0, 800, 0, "slow", _r.Random(1))[-1][0]
fast = ac.human_path(0, 0, 800, 0, "fast", _r.Random(1))[-1][0]
ok("human speed: slow takes longer than fast", slow > fast, (slow, fast))
ok("human path for a tiny move is one point", len(ac.human_path(5, 5, 6, 5)) == 1)
S0 = {"human_move": False, "human_speed": "fast"}
ok("mouse style: job says 'like a person' -> its speed", ac.mouse_style(S0, {"human_move": True}) == "fast")
ok("mouse style: step 'jump' overrides the job", ac.mouse_style(S0, {"human_move": True}, {"human_move": False}) is None)
ok("mouse style: nothing chosen -> Preferences", ac.mouse_style({"human_move": True, "human_speed": "slow"}, {}) == "slow"
   and ac.mouse_style(S0, {"human_move": None}) is None)
jj = ac.sanitize_job(dict(ac.new_job(), human_move="yes"))[0]
ok("import: invalid human_move -> follow Preferences", jj["human_move"] is None)
st, _ = ac.sanitize_step({"type": "click", "x": 1, "y": 2, "human_move": True})
ok("import: click step keeps its mouse movement choice", st.get("human_move") is True)
pal = ac.theme_palette({"custom_colors": {"dark": {"bg": "#123456", "fg": "nonsense", "nokey": "#ffffff"}}}, True)
ok("custom colours: valid ones used, invalid codes and unknown names ignored",
   pal["bg"] == "#123456" and pal["fg"] == ac.DARK["fg"] and "nokey" not in pal)
ok("custom colours don't touch the other theme", ac.theme_palette({"custom_colors": {"dark": {"bg": "#123456"}}}, False)["bg"] == ac.LIGHT["bg"])
ok("hex <-> rgb", ac.rgb_to_hex(*ac.hex_to_rgb("#1e5ac8")) == "#1e5ac8")
ac.append_history(job="Keep me", kind="scheduled", result="ok")
ac.append_history(job="Drop me", kind="scheduled", result="ok")
n = ac.rewrite_history(lambda r: r.get("job") != "Drop me")
rows = ac.read_history()
ok("delete click history for good (one job)", n >= 1 and not any(r["job"] == "Drop me" for r in rows) and any(r["job"] == "Keep me" for r in rows))
A.settings.update(stats_date="", stats_clicks=0)
A.bump_stats("stats_clicks"); A.bump_stats("stats_clicks", watch=True)
ok("clicks today counted for watchers separately", A.settings["stats_clicks"] == 2 and A.settings["stats_clicks_watch"] == 1)
ok("issue hints: screen locked / Clickue window / search area",
   "console" in ac.issue_hint("screen locked or remote session disconnected")
   and "Minimize" in ac.issue_hint("Clickue window open") and "Minimize" in ac.issue_hint("Clickue window in front of the picture") and ac.issue_hint("zzz") == "")

# ---- 4.6: updates (no real network: a fake GitHub)
ok("versions: newer / same / older / junk", ac.newer_version("v9.0.0") and not ac.newer_version(ac.VERSION)
   and not ac.newer_version("0.1") and not ac.newer_version("banana") and ac.parse_version("4.6") == (4, 6, 0))
import hashlib, io as _io2, zipfile as _zf
setup_bytes = b"MZ fake installer"
zbuf = _io2.BytesIO()
with _zf.ZipFile(zbuf, "w") as z:
    z.writestr("Clickue.exe", b"MZ new exe"); z.writestr("README.md", "x")
zip_bytes = zbuf.getvalue()
sums = (f"{hashlib.sha256(setup_bytes).hexdigest()}  Clickue-Setup-99.0.exe\n"
        f"{hashlib.sha256(zip_bytes).hexdigest()}  Clickue-Portable-99.0.zip\n")
release = {"tag_name": "v99.0", "name": "Clickue 99.0", "body": "Notes", "html_url": "https://github.com/jnssylvest/clickue/releases/tag/v99.0",
           "assets": [{"name": n, "browser_download_url": f"https://github.com/jnssylvest/clickue/releases/download/v99.0/{n}"}
                      for n in ("Clickue-Setup-99.0.exe", "Clickue-Portable-99.0.zip", "SHA256SUMS.txt")]
           + [{"name": "evil.exe", "browser_download_url": "https://evil.example/evil.exe"}]}
served = {}
def fake_get(url, max_bytes, dest=None, progress=None):
    served[url] = served.get(url, 0) + 1
    if url == ac.UPDATE_API:
        data = json.dumps(release).encode()
    elif url.endswith("SHA256SUMS.txt"):
        data = sums.encode()
    elif url.endswith(".exe"):
        data = setup_bytes
    elif url.endswith(".zip"):
        data = zip_bytes
    else:
        raise ValueError("not GitHub")
    if dest:
        open(dest, "wb").write(data); return len(data)
    return data
ac._HTTPS_GET = fake_get
info = ac.fetch_latest_release()
ok("update: newest release read, foreign download links ignored", info["version"] == "99.0" and "evil.exe" not in info["assets"], info["assets"].keys())
p1 = ac.download_update(info, "installer")
ok("update: installer downloaded and its checksum checked", open(p1, "rb").read() == setup_bytes and os.path.dirname(p1).endswith("updates"))
p2 = ac.download_update(info, "portable")
exe = ac.extract_portable_exe(p2, d)
ok("update: portable zip checked, only Clickue.exe taken out", open(exe, "rb").read() == b"MZ new exe")
sums = sums.replace(hashlib.sha256(setup_bytes).hexdigest(), "0" * 64)
try:
    ac.download_update(info, "installer"); bad = False
except ValueError as e:
    bad = "checksum" in str(e)
ok("update: a download that doesn't match its checksum is refused and deleted", bad and not os.path.exists(p1))
ac._HTTPS_GET = None
try:
    ac.https_get("https://evil.example/x", 10); refused = False
except ValueError as e:
    refused = "not GitHub" in str(e)
ok("update: connecting anywhere but GitHub is refused", refused)
try:
    ac.https_get("http://github.com/x", 10); refused = False
except ValueError:
    refused = True
ok("update: plain http is refused", refused)
ok("update: this test copy runs from source (it can't replace itself)", ac.install_kind() == "source")
A.settings["update_check"] = False
calls = []
ac._HTTPS_GET = lambda *a, **k: calls.append(a) or b"{}"
A.cmdq = queue.Queue()
A.check_for_updates(manual=False)
ok("update checks off: nothing is sent anywhere", not calls)
# 4.6.1: certificate checks trust Windows' store plus certifi's list, and stay on
import ssl as _ssl
_ctx = ac.tls_context()
ok("update: certificates and host names are always checked",
   _ctx.verify_mode == _ssl.CERT_REQUIRED and _ctx.check_hostname)
try:
    import certifi as _cf
    _n = len(_ctx.get_ca_certs())
    _plain = _ssl.create_default_context(); _plain.load_verify_locations(cafile=_cf.where())
    ok("update: certifi's trusted root certificates are loaded", _n >= len(_plain.get_ca_certs()) > 50, _n)
except ImportError:
    ok("update: certifi's trusted root certificates are loaded", False, "pip install certifi")
_msg = ac.friendly_net_error(Exception("<urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1010)>"))
ok("update: a certificate error is explained in plain words", "intercepting" in _msg and "CERTIFICATE_VERIFY_FAILED" in _msg)
ac._HTTPS_GET = None
print(f"\nRESULT {sum(R)}/{len(R)}")
