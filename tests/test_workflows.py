"""Clickue 4.5: security checks, import validation, workflows (if / repeat / variables /
groups / retries), the input queue, the macro recorder's compression, paste, screen video
and the run history. Headless (no display, no real input). Expect: RESULT N/N"""
import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_helpers.py")).read())
import base64, json, queue, tempfile, threading, time, types
from datetime import datetime
from PIL import Image, ImageDraw

d = tempfile.mkdtemp()
for k, v in (("DATA_DIR", os.path.join(d, "Clickue")), ("TESTS_PATH", d + "/t.json"),
             ("HISTORY_PATH", d + "/h.csv"), ("BACKUP_DIR", d + "/Clickue/backups")):
    setattr(ac, k, v)
os.makedirs(ac.DATA_DIR, exist_ok=True)
ac.SETTINGS_PATH, ac.JOBS_PATH = ac.data_path("settings.json"), ac.data_path("jobs.json")
ac.LOG_PATH = ac.data_path("clickue.log")
R = []


def ok(name, cond, info=""):
    R.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, info if not cond or info else "")


def make_app():
    A = object.__new__(ac.App)
    A.lock = threading.RLock(); A.logq = queue.Queue(); A.wait_msgs = {}; A.res_warned = set()
    A.tray = None; A.uninstalled = False; A.settings = dict(ac.DEFAULT_SETTINGS); A.jobs = []
    A.setup_logging(); A.own_visible = False; A.test_history = []; A.tests_dirty = False
    A.stop = threading.Event(); A.cmdq = queue.Queue(); A.undo_stack = []; A.groups = []
    A.refresh_tree = lambda *a, **k: None; A.update_buttons = lambda: None
    A.notify = lambda *a, **k: None
    return A


A = make_app()
ac.screen_available = lambda: True; ac.idle_seconds = lambda: 100; ac.system_dpi = lambda: 96
clicks, typed, keys, pasted = [], [], [], []
ac.do_click = lambda x, y, *a, **k: (clicks.append((x, y)) or (True, "clicked"))
ac.send_text = lambda t: (typed.append(t) or (True, "typed"))
ac.press_keys = lambda c: (keys.append(c) or (True, "pressed"))
ac.paste_text = lambda t, k="Ctrl+V", r=True, s=0.3: (pasted.append(t) or (True, "pasted"))


def logs():
    out = []
    while True:
        try:
            out.append(A.logq.get_nowait())
        except queue.Empty:
            return out


def run(steps, **job):
    j = ac.new_job(); j.update(main_click=False, steps=steps, name=job.pop("name", "W"), **job)
    A.ensure_runtime()
    return A.perform(j, check_idle=False)[:2], j


# ======================================================================== security: alerts
HOOK = "https://discord.com/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyz_ABCDEF-123"
TOKEN = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_0123456"
ok("discord: real webhook URL accepted", ac.check_discord_url(HOOK)[0])
for bad in ("http://discord.com/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyz",
            "https://evil.example/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyz",
            "https://discord.com.evil.example/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyz",
            "https://user:pw@discord.com/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyz",
            "https://discord.com:8443/api/webhooks/123456789012/abcdefghijklmnopqrstuvwxyz",
            "https://discord.com/api/other/123", "file:///etc/passwd", "javascript:alert(1)", ""):
    ok(f"discord: rejects {bad[:48]!r}", not ac.check_discord_url(bad)[0])
ok("telegram: good token + chat id", ac.check_telegram(TOKEN, "-100123")[0])
ok("telegram: rejects a bad token", not ac.check_telegram("abc", "1")[0])
ok("telegram: rejects a bad chat id", not ac.check_telegram(TOKEN, "1; DROP")[0])
posted = []
ac._http_post = lambda url, body, ctype: (posted.append((url, body)), 200)[1]
res = ac.send_alert({"alert_discord": "https://evil.example/hook"}, "x")
ok("send_alert never posts to an unexpected host", not posted and not res[0][1], res)
ac._ALERT_SENT.clear()
res = ac.send_alert({"alert_tg_token": TOKEN, "alert_tg_chat": "42"}, "hi")
ok("telegram: token goes in the URL path over https, text in the POST body",
   posted and posted[-1][0] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
   and b"hi" in posted[-1][1] and res[0][1], posted[-1:])
ac._ALERT_SENT.clear(); posted.clear()
r1 = ac.send_alert({"alert_discord": HOOK}, "one"); r2 = ac.send_alert({"alert_discord": HOOK}, "two")
ok("alerts are rate limited (no spam from a flapping watcher)", r1[0][1] and not r2[0][1]
   and "skipped" in r2[0][2] and len(posted) == 1, (r1, r2))
ok("a test alert can skip the rate limit", ac.send_alert({"alert_discord": HOOK}, "t", limit=False)[0][1])
for t in range(ac.ALERT_MAX_PER_HOUR + 5):
    ac._alert_allowed("X", now=1000 + t * 10)
ok("at most N alerts an hour", not ac._alert_allowed("X", now=1000 + 2000)[0])


def boom(url, body, ctype):
    raise OSError(f"failed talking to {url}")
ac._http_post = boom; ac._ALERT_SENT.clear()
res = ac.send_alert({"alert_discord": HOOK, "alert_tg_token": TOKEN, "alert_tg_chat": "1"}, "x")
ok("errors never contain the webhook token or bot token",
   all("abcdefghijklmnop" not in r[2] and TOKEN not in r[2] for r in res), res)
ok("redact() hides webhook tokens and bot tokens",
   "abcdefghij" not in ac.redact(HOOK) and TOKEN not in ac.redact("bot" + TOKEN))
A.settings.update(alert_discord=HOOK)
A.log(f"oops {HOOK}")
ok("log lines are redacted", all("abcdefghijklmnop" not in l for l in logs()))

# redirects are refused (local server answering 302)
import http.server, socketserver, urllib.error
class Redir(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(302); self.send_header("Location", "http://127.0.0.1:9/elsewhere"); self.end_headers()
    def log_message(self, *a):
        pass
srv = socketserver.TCPServer(("127.0.0.1", 0), Redir); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
import importlib
real_post = importlib.util.module_from_spec(spec); spec.loader.exec_module(real_post)
try:
    real_post._http_post("http://127.0.0.1:9/x", b"{}", "application/json"); plain = "allowed"
except ValueError:
    plain = "refused"
ok("plain http refused even if called directly", plain == "refused")
real_post._ALLOW_PLAIN_HTTP_FOR_TESTS = True
try:
    real_post._http_post(f"http://127.0.0.1:{port}/x", b"{}", "application/json"); redirected = "followed"
except urllib.error.HTTPError as e:
    redirected = e.code
except Exception as e:
    redirected = repr(e)
srv.shutdown()
ok("HTTP redirects are not followed", redirected == 302, redirected)

# secrets are kept out of backups and exports
A.settings.update(alert_discord=HOOK, alert_tg_token=TOKEN, alert_tg_chat="99")
A.jobs = [ac.new_job()]
p = ac.make_backup(A.jobs, A.settings, "manual")
txt = open(p, encoding="utf-8").read()
ok("backups never contain alert credentials", HOOK not in txt and TOKEN not in txt and '"99"' not in txt)

# protected settings (DPAPI simulated: real DPAPI only exists on Windows)
ac.HAVE_DPAPI = True
ac.protect_text = lambda t: "dpapi:" + base64.b64encode(t[::-1].encode()).decode()
real_unprotect = ac.unprotect_text
ac.unprotect_text = lambda v: base64.b64decode(v[6:]).decode()[::-1] if v.startswith("dpapi:") else v
A.settings["protect_secrets"] = True; A.save()
raw = json.load(open(ac.SETTINGS_PATH))
ok("protect_secrets: settings.json holds only protected values",
   raw["alert_discord"].startswith("dpapi:") and TOKEN not in json.dumps(raw))
B = make_app(); s2, j2, _ = B.load()
ok("protect_secrets: they are readable again after loading", s2["alert_discord"] == HOOK and s2["alert_tg_token"] == TOKEN)
def nope(v):
    raise ValueError("this text was protected by another Windows account or computer")
ac.unprotect_text = nope
B = make_app(); s3, _, _ = B.load()
ok("protected settings from another PC: cleared with a clear note", s3["alert_discord"] == ""
   and "enter them again" in B.secret_note.lower(), B.secret_note)
ac.unprotect_text = lambda v: base64.b64decode(v[6:]).decode()[::-1] if v.startswith("dpapi:") else v
A.settings.update(protect_secrets=False, alert_discord="", alert_tg_token="", alert_tg_chat="")

# ======================================================================== import validation
def write(name, data):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))
    return p


def import_err(p):
    try:
        ac.load_import_file(p); return ""
    except ValueError as e:
        return str(e)

ok("import: not JSON -> clear error", "not valid JSON" in import_err(write("a.json", "{nope")))
ok("import: no jobs -> clear error", "no jobs" in import_err(write("b.json", {"jobs": []})))
ok("import: newer schema refused", "newer" in import_err(write("c.json", {"schema": 99, "jobs": [{"x": 1, "y": 2}]})))
big = os.path.join(d, "big.json")
with open(big, "wb") as f:
    f.seek(ac.MAX_IMPORT_BYTES + 10); f.write(b"0")
ok("import: oversized file refused before reading", "too large" in import_err(big))
good_png = ac.img_to_b64(Image.new("RGB", (40, 30), (200, 10, 10)))
evil = {"schema": 2, "jobs": [{
    "x": "12", "y": 5, "name": "A" * 5000, "clicks": 99, "interval_s": "bad", "button": "nuke",
    "kind": "watch", "enabled": True, "snap_png": "not base64!!", "watch_png": good_png,
    "watch_area": [0, 0, "w", 5], "hours_days": [0, 9, "x", 3], "first_time": "99:99",
    "__class__": "x", "unknown_key": 1, "next_run": 1,
    "steps": [{"type": "click", "x": 1e12, "y": "3", "button": "left", "use_image": True},
              {"type": "exec", "cmd": "calc.exe"},
              {"type": "type", "text": "x" * (ac.MAX_TYPE_CHARS + 1)},
              {"type": "key", "keys": "Ctrl+Banana"},
              {"type": "waitpic", "png": ""},
              {"type": "wait", "min": -5, "max": 1e9},
              {"type": "repeat", "times": 10 ** 9},
              {"type": "end"},
              {"type": "set", "var": "bad name", "value": 1},
              {"type": "paste", "text": "hello", "paste_keys": "rm -rf"}]}],
    "groups": [{"id": "g1", "name": "G", "steps": [{"type": "group", "group_id": "g1"},
                                                    {"type": "wait", "min": 1}]}]}
jobs, groups, problems = ac.load_import_file(write("evil.json", evil))
j = jobs[0]
types_ = [s["type"] for s in j["steps"]]
ok("import: values coerced and clamped", j["x"] == 12 and j["clicks"] == 3 and j["button"] == "left"
   and j["interval_s"] == ac.new_job()["interval_s"] and len(j["name"]) == ac.MAX_NAME, (j["x"], j["clicks"]))
ok("import: unreadable picture dropped, good one kept", j["snap_png"] == "" and j["watch_png"] == good_png)
ok("import: bad area / days / time cleaned", j["watch_area"] is None and j["hours_days"] == [0, 3]
   and j["first_time"] == "")
ok("import: unknown and runtime keys dropped", "unknown_key" not in j and "__class__" not in j and j["next_run"] is None)
ok("import: unsafe or invalid steps left out and reported",
   types_ == ["click", "wait", "repeat", "end", "paste"] and len(problems) >= 5, (types_, problems))
ok("import: numbers in steps clamped", j["steps"][0]["x"] == 100000 and j["steps"][0]["use_image"] is False
   and j["steps"][1]["min"] == 0 and j["steps"][1]["max"] == 86400 and j["steps"][2]["times"] == ac.MAX_REPEAT)
ok("import: paste keys limited to the known choices", j["steps"][4]["paste_keys"] == "Ctrl+V")
ok("import: groups can't nest (no recursion)", [s["type"] for s in groups[0]["steps"]] == ["wait"])
bomb = Image.new("L", (9000, 10)); bp = ac.img_to_b64(bomb)
ok("import: oversized pictures refused", ac.clean_png(bp) == "")
ok("risky step summary counts keyboard steps", ac.risky_step_summary(jobs)["paste"] == 1)

# exports never contain secret text
sj = ac.new_job(); sj["steps"] = [{"type": "paste", "secret": True, "text": "", "text_enc": "dpapi:SECRET"},
                                  {"type": "type", "text": "visible"}]
A.jobs = [sj]; ep = os.path.join(d, "export.json"); A.export_to(ep)
et = open(ep, encoding="utf-8").read()
ok("export: secret text never exported, normal text kept", "SECRET" not in et and "visible" in et
   and '"secret_missing": true' in et)

# ======================================================================== data folder safety
ok("data dir check: Clickue folder ok", ac.is_clickue_data_dir(ac.DATA_DIR))
ok("data dir check: home folder refused", not ac.is_clickue_data_dir(os.path.expanduser("~")))
ok("data dir check: root refused", not ac.is_clickue_data_dir(os.sep))
other = os.path.join(d, "Clickue2"); os.makedirs(other)
ok("data dir check: other names refused", not ac.is_clickue_data_dir(other))
odd = os.path.join(d, "x", "Clickue"); os.makedirs(odd); open(os.path.join(odd, "my thesis.docx"), "w").close()
ok("data dir check: a 'Clickue' folder with unrelated files refused", not ac.is_clickue_data_dir(odd))
vf = os.path.join(d, "videos"); os.makedirs(vf)
for n in ("clickue_run_20260101_120000_job.mp4", "clickue_run_20260102_120000_job.avi",
          "holiday.mp4", "clickue_run_../evil.mp4".replace("/", "_"), "notes.txt"):
    open(os.path.join(vf, n), "w").close()
removed = ac.prune_files(vf, ac.VIDEO_FILE_RE, keep_count=0)
left = sorted(os.listdir(vf))
ok("video cleanup removes only Clickue's own video files", removed == 2 and "holiday.mp4" in left
   and "notes.txt" in left and "clickue_run_.._evil.mp4" in left, left)
ok("file names from job names are safe", ac.safe_file_part("..\\..\\Windows/System32 x") == "Windows-System32-x")

# ======================================================================== variables & blocks
v = ac.builtin_vars(datetime(2026, 10, 24, 9, 5, 7).timestamp())
ok("vars: built-ins", v["date"] == "2026-10-24" and v["time"] == "09:05:07" and v["weekday"] == "Sat")
ok("vars: expand, escapes, unknown kept", ac.expand_vars("{a}-{{x}}-{nope}-{b}", {"a": 1, "b": "z"}) == "1-{x}-{nope}-z")
try:
    ac.expand_vars("{a}", {"a": "x" * 50}, limit=10); lim = False
except ValueError:
    lim = True
ok("vars: result length limited", lim)
ok("compare: numbers and text", ac.compare_values("10", ">", "9") and not ac.compare_values("abc", ">", "b")
   and ac.compare_values("hello", "contains", "ell"))
_, errs = ac.parse_blocks([{"type": "if"}, {"type": "else"}, {"type": "else"}, {"type": "end"}, {"type": "end"}])
ok("blocks: extra Otherwise / End reported", len(errs) == 2, errs)
ok("blocks: missing End reported", ac.parse_blocks([{"type": "repeat"}])[1])
ok("blocks: indentation", ac.step_depths([{"type": "if"}, {"type": "wait"}, {"type": "else"},
                                          {"type": "wait"}, {"type": "end"}]) == [0, 1, 0, 1, 0])

# ======================================================================== workflows
A.settings["paused"] = False
def var_if(op, val):
    return {"type": "if", "cond": {"kind": "var", "var": "n", "op": op, "value": val}}
typed.clear()
(okk, msg), _ = run([{"type": "set", "var": "n", "value": "5"}, var_if(">", "3"),
                     {"type": "type", "text": "big {n}", "use_vars": True}, {"type": "else"},
                     {"type": "type", "text": "small"}, {"type": "end"}])
ok("if/else on a variable, with {variables} filled in", okk and typed == ["big 5"], (msg, typed))
typed.clear()
(okk, msg), _ = run([{"type": "set", "var": "n", "value": "1"}, var_if(">", "3"),
                     {"type": "type", "text": "big"}, {"type": "else"},
                     {"type": "type", "text": "small {n}"}, {"type": "end"}])
ok("if/else: the Otherwise branch; text without the option is typed as written", typed == ["small {n}"], typed)
typed.clear()
(okk, msg), _ = run([{"type": "repeat", "mode": "times", "times": 3},
                     {"type": "type", "text": "{loop}", "use_vars": True}, {"type": "end"}])
ok("repeat 3 times with {loop}", typed == ["1", "2", "3"], typed)
typed.clear()
(okk, msg), _ = run([{"type": "set", "var": "c", "value": "0"},
                     {"type": "repeat", "mode": "until", "max_times": 50, "max_seconds": 60,
                      "cond": {"kind": "var", "var": "c", "op": ">=", "value": "4"}},
                     {"type": "set", "var": "c", "op": "add", "value": "1"}, {"type": "end"},
                     {"type": "type", "text": "{c}", "use_vars": True}])
ok("repeat until a condition (counter)", okk and typed == ["4"], (msg, typed))
(okk, msg), _ = run([{"type": "repeat", "mode": "until", "max_times": 5, "max_seconds": 60,
                      "cond": {"kind": "var", "var": "never", "op": "==", "value": "x"}},
                     {"type": "wait", "min": 0, "max": 0}, {"type": "end"}])
ok("repeat until: stops at its limit and says why (no endless loop)", not okk and "5 time" in msg, msg)
ac.MAX_EXECUTED_STEPS, old_max = 30, ac.MAX_EXECUTED_STEPS
(okk, msg), _ = run([{"type": "repeat", "mode": "times", "times": 10000},
                     {"type": "wait", "min": 0, "max": 0}, {"type": "end"}])
ac.MAX_EXECUTED_STEPS = old_max
ok("runaway safety: total steps in one run are capped", not okk and "to be safe" in msg, msg)
(okk, msg), _ = run([{"type": "wait", "min": 5, "max": 5}], run_limit_s=10)
ok("run time limit is enforced (10 s minimum)", okk)
t0 = time.time()
(okk, msg), _ = run([{"type": "repeat", "mode": "times", "times": 100}, {"type": "wait", "min": 1, "max": 1},
                     {"type": "end"}], run_limit_s=10)
ok("run time limit stops a long run", not okk and "time limit" in msg and time.time() - t0 < 13, msg)

# retries and failure choices
attempts = {"n": 0}
def flaky(x, y, *a, **k):
    attempts["n"] += 1
    return (attempts["n"] >= 3), ("clicked" if attempts["n"] >= 3 else "missed")
ac.do_click = flaky
(okk, msg), _ = run([{"type": "click", "x": 5, "y": 5, "retries": 3, "retry_wait": 0}])
ok("retries: a step tried again until it works", okk and attempts["n"] == 3, (msg, attempts))
attempts["n"] = -100; typed.clear()
(okk, msg), _ = run([{"type": "click", "x": 5, "y": 5, "retries": 1, "retry_wait": 0},
                     {"type": "type", "text": "after"}])
ok("retries: gives up after the limit and stops the run", not okk and msg.startswith("step 1") and typed == [], msg)
attempts["n"] = -100; typed.clear()
(okk, msg), _ = run([{"type": "click", "x": 5, "y": 5, "on_fail": "continue"},
                     {"type": "type", "text": "after"}])
ok("on_fail=continue: carries on only when chosen", okk and typed == ["after"], msg)
ac.do_click = lambda x, y, *a, **k: (clicks.append((x, y)) or (True, "clicked"))

# step groups
A.groups = [{"id": "g1", "name": "Login", "steps": [{"type": "type", "text": "user"},
                                                    {"type": "key", "keys": "Tab"}]},
            {"id": "g2", "name": "Loop", "steps": [{"type": "group", "group_id": "g2"}]}]
typed.clear(); keys.clear()
(okk, msg), _ = run([{"type": "group", "group_id": "g1"}, {"type": "group", "group_id": "g1"}])
ok("step group reused twice", okk and typed == ["user", "user"] and keys == ["Tab", "Tab"], msg)
(okk, msg), _ = run([{"type": "group", "group_id": "g2"}])
ok("a group can't run itself (no recursion)", not okk and "itself" in msg, msg)
(okk, msg), _ = run([{"type": "group", "group_id": "gone"}])
ok("a deleted group fails clearly", not okk and "deleted" in msg, msg)

# remembered variables
(okk, msg), jj = run([{"type": "set", "var": "count", "op": "add", "value": "1", "persist": True}],
                     saved_vars={"count": "41"})
ok("variables remembered between runs", jj["saved_vars"]["count"] == "42", jj["saved_vars"])

# secret text: never logged; missing secret fails clearly
logs(); typed.clear(); pasted.clear()
(okk, msg), _ = run([{"type": "paste", "secret": True, "text_enc": ac.protect_text("hunter2")}])
ok("secret paste: decrypted only when pasting", okk and pasted == ["hunter2"], msg)
(okk, msg), _ = run([{"type": "paste", "secret": True, "text": ""}])
ok("secret missing (e.g. imported): fails with a clear message", not okk and "enter it again" in msg, msg)
ok("typed/pasted text never appears in the log", not any("hunter2" in l for l in logs()))
rh = open(ac.runlog_path(), encoding="utf-8").read()
ok("typed/pasted text never appears in the run history", "hunter2" not in rh and "Paste text" in rh)
(okk, msg), _ = run([{"type": "type", "text": "x" * (ac.MAX_TYPE_CHARS + 5)}])
ok("text over the limit fails safely", not okk and "longer than" in msg, msg)

# held keys and buttons are released when a run fails or is stopped
events = []
fake32 = types.SimpleNamespace(mouse_event=lambda f, *a: events.append(("mouse", f)),
                               SetCursorPos=lambda x, y: events.append(("move", x, y)) or 1)
ac.user32, ac.IS_WIN = fake32, True
ac._send = lambda inputs: [events.append(("key",) + i) for i in inputs]
ac._key_input = lambda vk=0, scan=0, flags=0: (vk, flags)
(okk, msg), _ = run([{"type": "keyhold", "keys": "Shift", "action": "down"},
                     {"type": "mouse", "button": "left", "action": "down", "x": 10, "y": 10},
                     {"type": "click", "x": 1, "y": 1, "use_image": True, "snap_png": "", "target_mode": "window",
                      "window_title": ""},
                     {"type": "type", "text": "never"}])
ok("held Shift and left button are released when the run fails",
   ("key", 0x10, 0x0002) in events and ("mouse", 0x0004) in events and not ac.HELD.holding(), (msg, events[-4:]))
events.clear()
(okk, msg), _ = run([{"type": "drag", "button": "left", "path": [[0, 0, 0], [0.05, 50, 0], [0.1, 100, 20]]},
                     {"type": "scroll", "x": 5, "y": 6, "amount": -3}])
ok("drag: press, follow the path, release; scroll", okk and events[0] == ("move", 0, 0)
   and ("mouse", 0x0002) in events and events.index(("mouse", 0x0004)) > events.index(("move", 100, 20))
   and ("mouse", 0x0800) in events, events)
ac.IS_WIN = False

# cancel and pause between steps
A.run_cancel.set(); typed.clear()
(okk, msg), _ = run([{"type": "wait", "min": 0, "max": 0}, {"type": "type", "text": "no"}])
ok("stop request ends the run before the next step", not okk and "stopped by you" in msg and not typed, msg)
A.run_cancel.clear()
A.settings["paused"] = True; typed.clear()
th = threading.Thread(target=lambda: run([{"type": "type", "text": "later"}]), daemon=True); th.start()
time.sleep(0.8); waited = not typed
A.settings["paused"] = False; th.join(3)
ok("Pause all pauses a running job between steps; resume continues", waited and typed == ["later"])

# dry run: never clicks or types
clicks.clear(); typed.clear(); pasted.clear()
dj = ac.new_job(); dj.update(main_click=False, steps=[
    {"type": "click", "x": 3, "y": 4}, {"type": "type", "text": "secret words"},
    var_if("==", "x"), {"type": "paste", "text": "p"}, {"type": "end"},
    {"type": "repeat", "times": 5}, {"type": "key", "keys": "Enter"}, {"type": "end"}])
lines = A.dry_run_steps(dj)
txt = " ".join(r for _, _, r in lines)
ok("dry run: reports each step, sends no input", not clicks and not typed and not pasted
   and "would click at (3, 4)" in txt and "12 characters" in txt and "secret words" not in txt, lines)

# ======================================================================== the input queue
q = ac.ActionQueue()
a = {"id": "a", "name": "A", "priority": "low"}; b = {"id": "b", "name": "B"}; c = {"id": "c", "name": "C", "priority": "high"}
q.put(a, "scheduled"); q.put(b, "scheduled"); q.put(c, "scheduled")
ok("queue: same job + action isn't queued twice", q.put(b, "scheduled") is None)
order = [q.take(0)["label"] for _ in range(3)]
ok("queue: high priority first, then first come first served", order == ["C", "B", "A"], order)
q.put(a, "x"); q.put(b, "x"); q.remove_job("a")
ok("queue: a deleted job's actions are dropped", [i["label"] for i in q.waiting()] == ["B"])
ok("queue: clear (emergency stop)", q.clear() == 1 and not q.waiting())

# watchers keep watching while a chain waits; actions run one at a time
A2 = make_app(); A2.ensure_runtime(); A2.start_input_thread()
order = []
img, _ = draw_app(1.0, 1920, 1080, 200, 150)
ac.grab_screen = lambda move_cursor=True: (img, (0, 0))
ac.STEP_POLL_S = 0.05
chain = ac.new_job(); chain.update(name="Chain", main_click=False, enabled=True, next_run=time.time() - 1,
                                   steps=[{"type": "waitpic", "png": good_png, "until": "appears", "timeout": 3,
                                           "on_timeout": "continue"}, {"type": "type", "text": "chain done"}])
w = ac.new_watch(); w.update(name="Watcher", enabled=True, watch_png=good_png, watch_interval_s=1,
                             next_check=time.time(), main_click=True, x=1, y=1, use_image=False)
other = ac.new_job(); other.update(name="Other", enabled=True, next_run=time.time() + 0.3, x=7, y=7, use_image=False,
                                   random_on=False)
A2.jobs = [chain, w, other]; typed.clear(); clicks.clear()
th = threading.Thread(target=A2.scheduler_loop, daemon=True); th.start()
running, waiting, checks_during, t_end = None, [], False, time.time() + 6
while time.time() < t_end:          # watch for: the chain running while Other waits
    r = A2.aq.running and A2.aq.running["label"]
    wl = [i["label"] for i in A2.aq.waiting()]
    if r == "Chain" and w.get("last_check") and time.time() - w["last_check"] < 2.5:
        checks_during = True
    if r == "Chain" and "Other" in wl:
        running, waiting = r, wl
    if (7, 7) in clicks:
        break
    time.sleep(0.05)
time.sleep(0.5)
A2.stop.set(); th.join(3)
ok("watchers keep checking while a chain is waiting", checks_during, w.get("last_check"))
ok("the chain holds the mouse; the other job waits its turn", running == "Chain" and "Other" in waiting,
   (running, waiting))
ok("queued job ran after the chain finished", (7, 7) in clicks and typed == ["chain done"], (clicks, typed))
txt_status = A2.queue_status()
ok("queue status text", isinstance(txt_status, tuple))

# a chain that lets others go first
A3 = make_app(); A3.ensure_runtime(); A3.start_input_thread(); clicks.clear(); typed.clear()
ac.grab_screen = lambda move_cursor=True: (img, (0, 0))
pol = ac.new_job(); pol.update(name="Polite", main_click=False, let_others_run=True,
                               steps=[{"type": "wait", "min": 2, "max": 2}, {"type": "type", "text": "polite done"}])
quick = ac.new_job(); quick.update(name="Quick", x=9, y=9, use_image=False)
A3.jobs = [pol, quick]
it1 = A3.aq.put(pol, "manual"); time.sleep(0.5); it2 = A3.aq.put(quick, "manual")
it1["done"].wait(6); it2["done"].wait(1)
ok("let others run: a waiting chain lets another job click in between", clicks == [(9, 9)] and
   typed == ["polite done"] and it2["done"].is_set(), (clicks, typed))
A3.stop.set()

# emergency stop
A4 = make_app(); A4.ensure_runtime(); A4.start_input_thread(); typed.clear()
long = ac.new_job(); long.update(name="Long", main_click=False, steps=[{"type": "wait", "min": 30, "max": 30},
                                                                       {"type": "type", "text": "never"}])
A4.jobs = [long]; it = A4.aq.put(long, "manual"); A4.aq.put(quick, "manual"); time.sleep(0.6)
A4.emergency_stop(); it["done"].wait(3)
ok("emergency stop: running job ends, queue emptied, everything paused",
   it["done"].is_set() and not typed and not A4.aq.waiting() and A4.settings["paused"])
A4.stop.set()

# conflicts
j1 = ac.new_job(); j1.update(name="J1", enabled=True, target_mode="window", window_title="Report", use_image=False)
j2 = ac.new_job(); j2.update(name="J2", enabled=True, main_click=False,
                             steps=[{"type": "click", "target_mode": "window", "window_title": "report"}])
j3 = ac.new_job(); j3.update(name="J3", enabled=True, use_image=True, snap_png=good_png)
ok("conflicts: same window found", ac.find_conflicts([j1, j2, j3])[0][:2] == ("J1", "J2"))
ok("conflicts: picture-based jobs don't count as the same spot", not ac.find_conflicts([j1, j3]))
j4 = ac.new_job(); j4.update(name="J4", enabled=True, x=100, y=100, use_image=False)
j5 = ac.new_job(); j5.update(name="J5", enabled=True, x=110, y=105, use_image=False)
ok("conflicts: same fixed spot found", ac.find_conflicts([j4, j5]))

# ======================================================================== recorder compression
ac.vk_char = lambda vk, shift=False, caps=False: (chr(vk) if shift else chr(vk).lower()) if 0x41 <= vk <= 0x5A else (" " if vk == 0x20 else None)
E = [("move", 0.00, 10, 10), ("move", 0.05, 60, 40), ("move", 0.10, 120, 80),
     ("down", 0.50, 120, 80, "left"), ("up", 0.55, 120, 80, "left"),
     ("down", 0.70, 121, 81, "left"), ("up", 0.75, 121, 81, "left"),
     ("down", 1.50, 200, 200, "left"), ("move", 1.60, 260, 230), ("move", 1.70, 320, 260), ("up", 1.80, 320, 260, "left"),
     ("down", 2.50, -500, 300, "right"), ("up", 3.80, -500, 300, "right"),
     ("wheel", 4.00, 50, 50, -1.0, False), ("wheel", 4.10, 50, 50, -1.0, False), ("wheel", 4.20, 51, 50, -1.0, False),
     ("kdown", 5.0, 0x10, False, False), ("kdown", 5.05, 0x48, False, False), ("kup", 5.08, 0x48),
     ("kup", 5.1, 0x10), ("kdown", 5.2, 0x49, False, False), ("kup", 5.25, 0x49),
     ("kdown", 5.3, 0x58, False, False), ("kup", 5.35, 0x58), ("kdown", 5.4, 0x08, False, False), ("kup", 5.45, 0x08),
     ("kdown", 6.0, 0x0D, False, False), ("kup", 6.05, 0x0D),
     ("kdown", 7.0, 0xA2, False, False), ("kdown", 7.05, 0x53, False, False), ("kup", 7.1, 0x53), ("kup", 7.15, 0xA2),
     ("kdown", 8.0, 0xA0, False, False), ("down", 8.2, 400, 400, "left"), ("up", 8.25, 400, 400, "left"), ("kup", 8.4, 0xA0),
     ("kdown", 9.0, 0x5B, False, False), ("kup", 9.1, 0x5B),
     ("down", 10.0, 900, 900, "left"), ("up", 10.05, 900, 900, "left"),
     ("snap", 0.50, good_png, (20, 15))]
steps = ac.compress_recording(E, exclude=[[880, 880, 50, 50]])
kinds = [s["type"] for s in steps if s["type"] != "wait"]
ok("recorder: move, double click, drag, hold, scroll, text, keys, Shift+click, Win tap",
   kinds == ["move", "click", "drag", "mouse", "mouse", "scroll", "type", "key", "key", "keyhold", "click",
             "keyhold", "key"], kinds)
st = {s["type"]: s for s in reversed(steps)}
clk = [s for s in steps if s["type"] == "click"]
ok("recorder: two quick clicks became a double click, with its picture", clk[0]["clicks"] == 2
   and clk[0]["use_image"] and clk[0]["snap_png"] == good_png)
ok("recorder: typing with Backspace gives the corrected text", st["type"]["text"] == "Hi", st["type"])
ok("recorder: Ctrl+S and Enter", [s["keys"] for s in steps if s["type"] == "key"] == ["Enter", "Ctrl+S", "Win"])
ok("recorder: scroll notches added up", st["scroll"]["amount"] == -3)
ok("recorder: multi-monitor (negative) coordinates kept", any(s.get("x") == -500 for s in steps))
ok("recorder: long press became button down / wait / up", [s["action"] for s in steps if s["type"] == "mouse"] == ["down", "up"]
   and any(s["type"] == "wait" and s["min"] >= 1.2 for s in steps))
ok("recorder: clicks on the recording bar left out", not any(s.get("x") == 900 for s in steps))
ok("recorder: pauses kept as waits", any(s["type"] == "wait" for s in steps))
clean = [ac.sanitize_step(s)[0] for s in steps]
ok("recorder: every recorded step is a valid step", all(clean))
ok("recorder: empty recording", ac.finish_recording(ac.compress_recording([])) == [])
hk = [("kup", 0.0, 0x52), ("kup", 0.01, 0xA2), ("kdown", 1.0, 0x41, False, False), ("kup", 1.1, 0x41),
      ("kdown", 2.0, 0xA2, False, False), ("kdown", 2.01, 0xA4, False, False), ("kdown", 2.02, 0x52, False, False)]
hk_steps = ac.finish_recording(ac.compress_recording(hk))
ok("recorder: the start/stop hotkey isn't recorded", [s["type"] for s in hk_steps] == ["type"], hk_steps)
big_ev = [("move", i * 0.008, int(500 + 300 * __import__("math").sin(i / 50)), int(i / 10)) for i in range(20000)]
big_steps = ac.compress_recording(big_ev)
size = len(json.dumps(big_steps))
ok("recorder: 20,000 mouse samples compress to a small path", len(big_steps) == 1 and
   len(big_steps[0]["path"]) <= ac.MAX_PATH_POINTS and size < 80_000, (len(big_steps[0]["path"]), size))
ok("recorder: trailing moves to the Stop button dropped",
   [s["type"] for s in ac.finish_recording([{"type": "click"}, {"type": "wait"}, {"type": "move"}])] == ["click"])
moves_off = ac.compress_recording(E, opts={"moves": False, "timing": False})
ok("recorder: options (no moves, no pauses)", not any(s["type"] in ("move", "wait") and s.get("min", 0) < 1
                                                      for s in moves_off))

# ======================================================================== paste text (clipboard)
rp = real_post
rp.IS_WIN = True
clip = {"items": [(13, "old".encode("utf-16-le"))], "log": []}
rp.clipboard_snapshot = lambda: (list(clip["items"]), True)
rp.clipboard_set_text = lambda t, private=True: clip["log"].append(("set", t, private)) or True
rp.clipboard_restore = lambda items: clip["log"].append(("restore", items)) or True
rp.press_keys = lambda c: (keys.append(c) or (True, "pressed"))
keys.clear()
okk, m = rp.paste_text("Zürich ✓\nline 2", "Ctrl+V", True, 0.05)
ok("paste: private clipboard text, Ctrl+V, then the old clipboard back",
   okk and clip["log"][0] == ("set", "Zürich ✓\nline 2", True) and keys == ["Ctrl+V"]
   and clip["log"][1] == ("restore", clip["items"]) and "Zürich" not in m, (clip["log"], m))
clip["log"].clear(); rp.clipboard_snapshot = lambda: ([], False)
okk, m = rp.paste_text("x", "Shift+Insert", True, 0.05)
ok("paste: says honestly when the clipboard couldn't be fully put back", okk and "cleared" in m, m)
clip["log"].clear()
okk, m = rp.paste_text("x", "Ctrl+V", False, 0.05)
ok("paste: optionally leaves it on the clipboard", not any(e[0] == "restore" for e in clip["log"]))
rp.clipboard_snapshot = lambda: (None, False); clip["log"].clear()
okk, m = rp.paste_text("x", "Ctrl+V", True, 0.05)
ok("paste: clipboard can't be read -> nothing is touched, clear message", not okk and not clip["log"]
   and "clipboard" in m, (m, clip["log"]))
rp.clipboard_snapshot = lambda: ([], True)
rp.clipboard_set_text = lambda t, private=True: False
ok("paste: clipboard busy -> fails with a clear message", "clipboard" in rp.paste_text("x")[1])
rp.IS_WIN = False

# ======================================================================== screen video + run history
frames = {"n": 0}
def fake_grab():
    frames["n"] += 1
    im = Image.new("RGB", (640, 360), (frames["n"] * 7 % 255, 40, 90))
    ImageDraw.Draw(im).rectangle((100, 100, 200, 200), fill=(255, 255, 255))
    return im, (0, 0)
vdir = os.path.join(d, "rec")
vid = ac.RunVideo(vdir, "My Job", "high", redact=[[100, 100, 100, 100]], grab=fake_grab)
started = vid.start()
time.sleep(1.2)
pos = vid.position()
path = vid.stop()
ok("video: records frames to a local file", started and os.path.exists(path) and os.path.getsize(path) > 0
   and ac.VIDEO_FILE_RE.match(os.path.basename(path)), (vid.status, vid.error, path))
ok("video: position counts with the frames", 0.5 <= pos <= 2.0, pos)
cap = ac.cv2.VideoCapture(path); okf, fr = cap.read(); cap.release()
ok("video: hidden areas are blacked out", okf and fr[150, 150].max() < 40, list(fr[150, 150]) if okf else None)
real_vw = ac.cv2.VideoWriter
class NoCodec:
    def __init__(self, *a):
        pass
    def isOpened(self):
        return False
    def release(self):
        pass
ac.cv2.VideoWriter = NoCodec
v2 = ac.RunVideo(vdir, "x", grab=fake_grab)
ok("video: no codec available -> recording off with a reason", not v2.start() and "format" in v2.error)
ac.cv2.VideoWriter = real_vw
real_free = ac.free_bytes
ac.free_bytes = lambda f: 10 * 1024 ** 2
v3 = ac.RunVideo(vdir, "x", grab=fake_grab)
ok("video: low disk space -> doesn't start", not v3.start() and "free" in v3.error)
ac.free_bytes = real_free
v4 = ac.RunVideo(vdir, "x", "compact", grab=fake_grab); v4.start()
ac.free_bytes = lambda f: 10 * 1024 ** 2
time.sleep(6)
ok("video: disk filling up -> recording stops, safely", v4.status == "stopped" and "disk" in v4.error, v4.status)
v4.stop(); ac.free_bytes = real_free
def bad_grab():
    raise OSError("screen gone")
v5 = ac.RunVideo(vdir, "x", "compact", grab=fake_grab); v5.start(); v5.grab = bad_grab; time.sleep(1.2)
ok("video: capture failure stops only the video", v5.status == "stopped" and "screen gone" in v5.error)
v5.stop()

# a run with video: steps in the run history point at video positions
A5 = make_app(); A5.ensure_runtime()
A5.settings.update(video_on=True, video_dir=vdir, video_preset="high", run_log_on=True)
ac.grab_screen = lambda move_cursor=False: fake_grab()
typed.clear()
vj = ac.new_job(); vj.update(name="Video job", main_click=False, record_video=True,
                             steps=[{"type": "wait", "min": 0.6, "max": 0.6}, {"type": "type", "text": "pw123"},
                                    {"type": "wait", "min": 0.6, "max": 0.6}])
okk, msg, *_ = A5.perform(vj, check_idle=False)
rows = [r for r in ac.read_runlog() if r["job"] == "Video job"]
poss = [float(r["video_pos"]) for r in rows if r["video_pos"] != ""]
ok("run history: start, each step, finish", [r["action"].split(":")[0] for r in rows][:1] == ["Run started"]
   and rows[-1]["action"] == "Run finished" and rows[-1]["result"] == "ok", [r["action"] for r in rows])
ok("run history: steps linked to video positions (in order)", len(poss) >= 4 and poss == sorted(poss)
   and rows[0]["video"].startswith("clickue_run_"), poss)
ok("run history: typed text not stored", "pw123" not in json.dumps(rows))
A5.settings["video_on"] = False; A5.settings["run_log_on"] = False
n0 = len(ac.read_runlog()); A5.perform(vj, check_idle=False)
ok("run history can be turned off", len(ac.read_runlog()) == n0)

# failure screenshot (opt-in), with hidden areas
A5.settings.update(diag_keep=2)
fj = ac.new_job(); fj.update(name="Fails", main_click=False, fail_shot=True, steps=[{"type": "group", "group_id": "nope"}])
for _ in range(3):
    A5.video_hide_until = 0; A5.perform(fj, check_idle=False); time.sleep(1.05)
shots = [n for n in os.listdir(ac.data_path("diagnostics")) if ac.DIAG_FILE_RE.match(n)]
ok("failure screenshots: saved when asked, oldest pruned", len(shots) == 2, shots)

# ======================================================================== saved data: migration
old = {"app": "Clickue", "version": "4.4", "jobs": [{"name": "old", "x": 1, "y": 2, "steps": [{"type": "wait", "min": 1}]}]}
json.dump(old, open(ac.JOBS_PATH, "w"))
B = make_app(); s_, j_, _ = B.load()
ok("migration: 4.4 jobs load with new fields defaulted", B.schema_upgrade and j_[0]["main_click"] is True
   and j_[0]["priority"] == "normal" and j_[0]["steps"][0]["min"] == 1)
B.jobs, B.settings = j_, s_; B.save()
saved = json.load(open(ac.JOBS_PATH))
ok("migration: saved in the new format (schema 2, groups)", saved["schema"] == 2 and saved["groups"] == []
   and saved["jobs"][0]["name"] == "old")
B2 = make_app(); B2.load()
ok("migration: only once", not B2.schema_upgrade)
old_job = dict(ac.new_job(), steps=[{"type": "type", "text": "{date} literal"}])
old_job.pop("main_click"); typed.clear()
B2.ensure_runtime(); okk, msg, *_ = B2.perform(old_job, check_idle=False)
ok("old jobs: main click + steps as before, text typed literally", okk and typed == ["{date} literal"], msg)

ok("adapters: registry and fallbacks described", [a.id for a in ac.ADAPTERS] == ["picture", "window", "screen"]
   and "no fallback" in ac.adapter_for({"use_image": True, "snap_png": good_png}).describe({"use_image": True})
   and "not verified" in ac.adapter_for({"x": 1, "y": 2}).describe({"x": 1, "y": 2}))
try:
    class Old(ac.TargetAdapter):
        api, id = 0, "old"
    ac.register_adapter(Old()); refused = False
except ValueError:
    refused = True
ok("adapters: wrong API version refused", refused)

# ======================================================================== 4.5.1 tray menu, matching
import types as _types
class _MI:
    def __init__(self, text, action=None, default=False, visible=True, **k):
        self.text, self.action, self.visible = text, action, visible
class _Menu:
    SEPARATOR = _MI("-")
    def __init__(self, *items):
        self.items = items
class _Icon:
    made = []
    def __init__(self, name, img, title, menu):
        self.name, self.title, self.menu = name, title, menu
        _Icon.made.append(self)
    def run_detached(self):
        pass
    def stop(self):
        pass
fake = _types.SimpleNamespace(MenuItem=_MI, Menu=_Menu, Icon=_Icon)
fake.Menu.SEPARATOR = _MI("-")
real_tray, real_have = getattr(ac, "pystray", None), ac.HAVE_TRAY
ac.pystray, ac.HAVE_TRAY = fake, True
T = _types.SimpleNamespace(settings={"tray_status": True}, cmdq=_types.SimpleNamespace(put=lambda x: None),
                           icon_img=None, log=lambda m: None, emergency_stop=lambda: None, tray=None,
                           _tray_lines=["✓ A: Running", "⚠ B: Picture missing"])
ac.App.start_tray(T)
icon = T.tray
sub = [i for i in icon.menu.items if getattr(i, "text", "") == "Job status"]
ok("tray: icon titled Clickue with a Job status submenu", icon and icon.title == "Clickue" and sub
   and [x.text for x in sub[0].action.items[0]()] == ["✓ A: Running", "⚠ B: Picture missing"])
class _Bad(_Menu):
    def __init__(self, *items):
        if len(items) == 1 and callable(items[0]):
            raise TypeError("no dynamic menus")
        super().__init__(*items)
fake.Menu = _Bad
T.tray = None
ac.App.start_tray(T)
ok("tray: falls back to the plain menu if the status submenu can't be built",
   T.tray is not None and not [i for i in T.tray.menu.items if getattr(i, "text", "") == "Job status"])
ac.pystray, ac.HAVE_TRAY = real_tray, real_have

ok("exact matching: on by default for jobs and imported click steps",
   ac.new_job()["exact_match"] is True
   and ac.sanitize_step({"type": "click", "x": 1, "y": 1})[0]["exact_match"] is True
   and ac.sanitize_step({"type": "click", "x": 1, "y": 1, "exact_match": False})[0]["exact_match"] is False)
ok("settings: 4.5.1 defaults", ac.DEFAULT_SETTINGS["marker_seconds"] == 5
   and ac.DEFAULT_SETTINGS["show_similar"] is False and ac.DEFAULT_SETTINGS["tray_status"] is True)
ok("saved window sizes are kept when they fit (no shrinking)",
   ac.fit_geometry("1200x1000+10+20") == "1200x1000+10+20" or ac.virtual_screen()[3] < 1000)

# ======================================================================== 4.5.1: never lose jobs
import shutil as _sh
def fresh_folder():
    _sh.rmtree(ac.DATA_DIR, ignore_errors=True); os.makedirs(ac.DATA_DIR, exist_ok=True)
fresh_folder()
oldcfg = os.path.join(d, "autoclicker_config.json")
json.dump({"settings": {}, "jobs": [dict(ac.new_job(), name="Deleted long ago")]}, open(oldcfg, "w"))
ac.OLD_CONFIG = oldcfg
asked = []
# a used data folder (has backups / a log) but no jobs file: the old config is NEVER imported
ac.make_backup([dict(ac.new_job(), name="My 4.5 job")], dict(ac.DEFAULT_SETTINGS), "auto")
B = make_app(); s_, j_, mig = B.load(ask=lambda q: asked.append(q) or True)
ok("jobs safety: old config never imported into a used data folder",
   not j_ and not asked and not mig and B.jobs_file_state == "missing")
# ...and the newest backup is offered instead
B.jobs = j_
got = B.offer_backup_recovery(lambda q: asked.append(q) or True)
ok("jobs safety: missing jobs file -> newest backup offered and restored (stopped)",
   got and [j["name"] for j in B.jobs] == ["My 4.5 job"] and not B.jobs[0]["enabled"]
   and "My 4.5 job" in asked[-1], asked[-1:])
asked.clear()
B.jobs = []
ok("jobs safety: saying No keeps an empty list", not B.offer_backup_recovery(lambda q: False) and not B.jobs)
# a damaged jobs file is not treated as "never used"
fresh_folder()
open(ac.JOBS_PATH, "w").write("{ not json")
ac.messagebox.showwarning = lambda *a, **k: None
B = make_app(); s_, j_, mig = B.load(ask=lambda q: asked.append(q) or True)
ok("jobs safety: unreadable jobs file -> no old-config import, reported as unreadable",
   not asked and B.jobs_file_state == "unreadable" and os.path.exists(ac.JOBS_PATH + ".corrupt"))
# a truly unused data folder: the old config is only imported after asking
fresh_folder()
B = make_app(); s_, j_, mig = B.load(ask=lambda q: asked.append(q) or False)
ok("jobs safety: old config needs a Yes (No = nothing imported)", asked and not j_ and not mig)
asked.clear()
B = make_app(); s_, j_, mig = B.load()
ok("jobs safety: without anyone to ask, nothing is imported", not j_ and not mig)
B = make_app(); s_, j_, mig = B.load(ask=lambda q: True)
ok("jobs safety: Yes imports it", mig and [j["name"] for j in j_] == ["Deleted long ago"]
   and B.old_config_imported)
# the version that saved the file is remembered (a backup is made on every version change)
fresh_folder()
json.dump({"app": "Clickue", "version": "4.5", "schema": 2, "jobs": [dict(ac.new_job(), name="J")]},
          open(ac.JOBS_PATH, "w"))
B = make_app(); s_, j_, mig = B.load()
ok("jobs safety: knows which version saved the jobs", B.saved_version == "4.5" and B.jobs_file_state == "ok"
   and "4.5" in B.jobs_file_info)
# saving: a blocked file is retried once and then reported
real_wj = ac.write_json
calls = []
def flaky(path, data):
    calls.append(path)
    if len(calls) == 1:
        raise PermissionError("in use")
    return real_wj(path, data)
ac.write_json = flaky
B.jobs = j_; B.settings = s_; B.save()
ok("saving: retried after a brief lock, then saved", len(calls) == 3 and json.load(open(ac.JOBS_PATH))["jobs"][0]["name"] == "J")
ac.write_json = lambda p, d: (_ for _ in ()).throw(PermissionError("blocked"))
B.save()
ok("saving: a lasting failure is reported", "blocked" in getattr(B, "save_error", ""))
ac.write_json = real_wj
print(f"\nRESULT {sum(R)}/{len(R)}")
