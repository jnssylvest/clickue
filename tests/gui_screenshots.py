"""Saves screenshots of the main windows into tests/screenshots/ (needs Xvfb on :99)."""
import os, sys, time, tempfile
HOME = tempfile.mkdtemp(); os.environ["HOME"] = HOME
sys.argv = ["clickue.py"]
import importlib.util, tkinter as tk
spec = importlib.util.spec_from_file_location("ac", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "clickue.py"))
ac = importlib.util.module_from_spec(spec); spec.loader.exec_module(ac)
from PIL import ImageGrab
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(OUT, exist_ok=True)
for n in ("showinfo", "showwarning", "showerror"):
    setattr(ac.messagebox, n, lambda *a, **k: "ok")
ac.messagebox.askyesno = lambda *a, **k: True
root = tk.Tk()
app = ac.App(root)
root.geometry("1400x880+0+0")


def pump(ms):
    end = time.time() + ms / 1000
    while time.time() < end:
        root.update(); time.sleep(0.01)


def shot(win, name):
    pump(400)
    win.update_idletasks()
    x, y, w, h = win.winfo_rootx(), win.winfo_rooty(), win.winfo_width(), win.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h), xdisplay=":99").save(f"{OUT}/{name}.png")


# a few jobs so the list has content
c = ac.new_job(1); c.update(name="Daily login", x=500, y=300, use_image=False, hours_on=True,
                            hours_days=[0, 1, 2, 3, 4], steps=[{"type": "wait", "min": 2, "max": 2}])
w = ac.new_watch(1); w.update(name="Reconnect", x=700, y=400, use_image=False, watch_trigger="gone")
w2 = ac.new_watch(2); w2.update(name="Claim reward", watch_trigger="appears", watch_click_picture=True)
for j in (c, w, w2):
    app.jobs.append(j); app.start_job(j)
app.refresh_tree(full=True); pump(800)
shot(root, "01_main")
app.show_main_menu(); pump(300)
m = app.main_menu
ImageGrab.grab(bbox=(m.winfo_rootx(), m.winfo_rooty(), m.winfo_rootx() + m.winfo_width(),
                     m.winfo_rooty() + m.winfo_height()), xdisplay=":99").save(f"{OUT}/02_menu.png")
m.unpost()
app.add_watcher(); pump(500)
ed = [x for x in ac.walk(root) if isinstance(x, ac.JobEditor)][0] if hasattr(ac, "walk") else None
eds = [x for x in root.winfo_children() if isinstance(x, ac.JobEditor)]
ed = eds[0]
ed.geometry("760x1000+20+0"); pump(300)
shot(ed, "03_watcher_editor_top")
ed.canvas.yview_moveto(0.55); pump(200); shot(ed, "04_watcher_editor_mid")
ed.canvas.yview_moveto(1.0); pump(200); shot(ed, "05_watcher_editor_bottom")
ed.destroy()
app.open_settings(); pump(400)
d = [x for x in root.winfo_children() if isinstance(x, ac.SettingsDialog)][0]
for key, name in ac.SettingsDialog.TABS:
    d.v_tab.set(key); d.show_tab(); pump(200)
    shot(d, f"06_prefs_{key}")
d.destroy()
ed = ac.JobEditor(app, c, is_new=False); pump(400)
ed.geometry("760x1000+20+0"); ed.canvas.yview_moveto(1.0); pump(300)
shot(ed, "07_click_editor_bottom")
sd = ac.StepDialog(app, ed, {"type": "key"}); pump(400)
shot(sd, "08_step_dialog")
sd.destroy(); ed.destroy()
app.open_tests(); pump(600)
shot(app.tests_win, "09_tests")
app.tests_win.close()
ac.BackupsDialog(app); pump(400)
b = [x for x in root.winfo_children() if isinstance(x, ac.BackupsDialog)][0]; shot(b, "10_backups"); b.destroy()
ac.AboutDialog(app); pump(400)
b = [x for x in root.winfo_children() if isinstance(x, ac.AboutDialog)][0]; shot(b, "11_about"); b.destroy()
root.geometry("760x700+0+0"); pump(800); shot(root, "12_main_narrow")
root.geometry("1400x880+0+0"); pump(400)

# ---- 4.5: recording, timeline, step types, dry run, step through, groups, run history
steps = ac.finish_recording(ac.compress_recording([
    ("down", 0.5, 412, 300, "left"), ("up", 0.55, 412, 300, "left"),
    ("kdown", 1.2, 0x48, False, False), ("kup", 1.25, 0x48), ("kdown", 1.3, 0x49, False, False),
    ("kup", 1.35, 0x49), ("kdown", 2.5, 0x0D, False, False), ("kup", 2.55, 0x0D),
    ("wheel", 3.5, 700, 500, -3.0, False),
    ("down", 5.0, 300, 420, "left"), ("move", 5.2, 380, 440), ("up", 5.6, 520, 460, "left")]))
app.groups = [{"id": "g1", "name": "Sign in", "steps": [{"type": "key", "keys": "Tab"}]}]
cond = {"kind": "var", "var": "count", "op": "<", "value": "10"}
steps += [{"type": "set", "var": "count", "op": "add", "value": "1", "persist": True},
          {"type": "if", "cond": cond}, {"type": "paste", "text": "Report {date}", "use_vars": True},
          {"type": "else"}, {"type": "group", "group_id": "g1"}, {"type": "end"},
          {"type": "repeat", "mode": "times", "times": 3}, {"type": "key", "keys": "Down"},
          {"type": "end"}]
rj = ac.new_job(9); rj.update(name="Recorded macro 1", main_click=False, steps=steps)
ed = ac.JobEditor(app, rj, is_new=True, start_on=False); pump(400)
ed.geometry("820x1000+20+0"); pump(200)
ed.canvas.yview_moveto(0.62); pump(300); shot(ed, "13_timeline")
for i, (kind, extra) in enumerate((("paste", {"text": "Line one\nLine two ✓", "use_vars": True}),
                                    ("type", {"text": "hello"}), ("if", {"cond": cond}),
                                    ("repeat", {"mode": "until", "cond": {"kind": "window", "title": "Export done"}}),
                                    ("set", {"var": "count"}), ("group", {"group_id": "g1"}),
                                    ("click", {"x": 412, "y": 300, "target_mode": "screen", "use_image": False}),
                                    ("scroll", {"amount": -3}))):
    sd = ac.StepDialog(app, ed.stepsed, dict({"type": kind}, **extra)); pump(400)
    shot(sd, f"14_step_{kind}"); sd.destroy()
ed.destroy()
ac.RecordDialog(app); pump(400)
d = [x for x in root.winfo_children() if isinstance(x, ac.RecordDialog)][0]; shot(d, "15_record_dialog"); d.destroy()
class FakeRec:
    state, counts, exclude = "recording", {"clicks": 5, "keys": 23}, []
    def now(self): return 12.0
app.recorder = FakeRec(); ind = ac.RecordingIndicator(app); pump(700); shot(ind, "16_recording_bar")
ind.destroy(); app.recorder = None
ac.GroupsDialog(app); pump(400)
d = [x for x in root.winfo_children() if isinstance(x, ac.GroupsDialog)][0]; shot(d, "17_groups"); d.destroy()
for k, (act, res, pos) in enumerate((("Run started", "", 0), ("Click: left at (412, 300), picture 97%", "ok", 0.4),
                                     ("Type text: 2 characters", "ok", 1.2), ("Wait for picture: until it appears", "ok", 4.0),
                                     ("Run finished", "ok", 6.1))):
    ac.append_runlog({"run": "abc123", "time": "2026-10-24 18:30:00", "job": "Recorded macro 1",
                      "elapsed": pos, "video_pos": pos, "step": str(k) if k else "", "action": act, "result": res,
                      "video": "clickue_run_20261024_183000_Recorded-macro-1.mp4"})
rh = ac.RunHistoryDialog(app); pump(400); rh.runs.selection_set("abc123"); pump(300); shot(rh, "18_run_history")
rh.destroy()
dw = ac.DebugWindow(app, rj, on_close=None); pump(300)
dw.show_next("3", "Click: left double click at (412, 300), by picture",
             "Will click at (412, 300), found picture 97%. Finds the saved picture; no fallback: if "
             "the picture isn't found, nothing is clicked", None, False)
dw.show_result("1", "Wait", True, "waited"); dw.show_result("2", "Type text", True, "typed")
pump(300); shot(dw, "19_step_through"); dw.destroy()
app.queue_status = lambda: ("Running “Daily login” · step 3 of 8 · 42s", ["Reconnect"])
app.update_run_bar(); pump(500); shot(root, "20_main_running")
app.stop.set(); root.destroy()
print("done")
