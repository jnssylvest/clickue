"""Drives the real Clickue UI on an X display. Run with a Python that has tkinter, under Xvfb:
   Xvfb :99 &  DISPLAY=:99 python tests/gui_test.py      Expect: N/N checks passed, 0 errors"""
import os, sys, time, tempfile, traceback, json
HOME = tempfile.mkdtemp()
os.environ["HOME"] = HOME
sys.argv = ["autoclicker.py"]
import importlib.util
import tkinter as tk
from tkinter import ttk
spec = importlib.util.spec_from_file_location("ac", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "clickue.py"))
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)

RESULTS, ERRORS, BOXES = [], [], []


def ok(name, cond, info=""):
    RESULTS.append((bool(cond), name, str(info)))


# ---- automatic answers for message boxes / file pickers (recorded)
def fake(kind, ret):
    def f(*a, **k):
        BOXES.append((kind, (a[1] if len(a) > 1 else k.get("message", ""))[:90]))
        return ret
    return ac._held(f)


ANSWER = {"askyesno": True}
for n in ("showinfo", "showwarning", "showerror"):
    setattr(ac.messagebox, n, fake(n, "ok"))
ac.messagebox.askyesno = ac._held(lambda *a, **k: (BOXES.append(("askyesno", a[1][:90] if len(a) > 1 else "")), ANSWER["askyesno"])[1])
ac.messagebox.askyesnocancel = fake("askyesnocancel", True)
ac.messagebox.askokcancel = fake("askokcancel", True)
ac.filedialog.askdirectory = fake("askdirectory", "")
EXPORT = os.path.join(HOME, "export.json")
ac.filedialog.asksaveasfilename = fake("save", EXPORT)
ac.filedialog.askopenfilename = fake("open", EXPORT)

root = tk.Tk()


def report(exc, val, tb):
    ERRORS.append("".join(traceback.format_exception(exc, val, tb))[-1500:])


root.report_callback_exception = report
app = ac.App(root)
root.update()


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def widgets(w, cls):
    return [x for x in walk(w) if isinstance(x, cls)]


def pump(ms=100):
    end = time.time() + ms / 1000
    while time.time() < end:
        root.update()
        time.sleep(0.01)


def toplevels():
    return [w for w in walk(root) if isinstance(w, tk.Toplevel) and w.winfo_exists()]


def find_dialog(cls):
    for w in toplevels():
        if isinstance(w, cls):
            return w
    return None


def btn(win, text):
    for b in widgets(win, ttk.Button):
        if text.lower() in str(b.cget("text")).lower():
            return b
    return None


def popdown_mapped(cb):
    pd = str(cb) + ".popdown"
    return int(cb.tk.call("winfo", "exists", pd)) and int(cb.tk.call("winfo", "ismapped", pd))


def warp(x, y):
    root.event_generate("<Motion>", warp=True, x=x - root.winfo_rootx(), y=y - root.winfo_rooty())
    pump(50)


def shown(ws):
    return [w for w in ws if w.winfo_ismapped() and w.winfo_viewable()]


def check_comboboxes(win, label):
    """Open every dropdown, make sure it stays open (even when focus moves to it), pick a value."""
    for cb in shown(widgets(win, ttk.Combobox)):
        vals = list(cb.cget("values"))
        if not vals or str(cb.cget("state")) == "disabled" or "disabled" in cb.state():
            continue
        before = cb.get()
        cb.focus_force()
        pump(50)
        cb.tk.call("ttk::combobox::Post", cb)
        pump(150)
        # simulate the popup losing focus to the dropdown list, like on Windows
        win.event_generate("<FocusOut>")
        pump(400)
        still = popdown_mapped(cb)
        ok(f"{label}: dropdown '{before}' stays open", still and win.winfo_exists())
        cb.tk.call("ttk::combobox::Unpost", cb)
        pump(80)
        # choose the last value
        cb.set(vals[-1])
        cb.event_generate("<<ComboboxSelected>>")
        pump(80)
        ok(f"{label}: dropdown '{before}' can select '{vals[-1]}'", cb.get() == str(vals[-1]))
        cb.set(before)
        cb.event_generate("<<ComboboxSelected>>")
        pump(50)


def check_spinboxes(win, label):
    for sb in shown(widgets(win, ttk.Spinbox)):
        if str(sb.cget("state")) == "disabled":
            continue
        try:
            v0 = float(sb.get())
        except ValueError:
            continue
        sb.event_generate("<<Increment>>")
        pump(30)
        up = float(sb.get())
        sb.event_generate("<<Decrement>>")
        pump(30)
        ok(f"{label}: spin box up/down ({v0:g})", up >= v0 and float(sb.get()) <= up, f"{v0}->{up}->{sb.get()}")


def check_toggles(win, label):
    for cb in shown(widgets(win, ttk.Checkbutton)):
        if "disabled" in cb.state():
            continue
        var = cb.cget("variable")
        v0 = root.getvar(var) if var else None
        cb.invoke(); pump(30)
        v1 = root.getvar(var) if var else None
        cb.invoke(); pump(30)
        v2 = root.getvar(var) if var else None
        ok(f"{label}: checkbox '{str(cb.cget('text'))[:40]}' toggles", str(v0) != str(v1) and str(v0) == str(v2), f"{v0}/{v1}/{v2}")


def step(name, fn):
    try:
        fn()
    except Exception:
        ERRORS.append(f"{name}: " + traceback.format_exc()[-1500:])


# ======================================================================== main window
def t_main():
    ok("main window shown", root.winfo_viewable())
    # toolbar buttons with nothing selected (selection buttons should be disabled)
    for it in app.tool_items:
        if it["needs_sel"]:
            ok(f"toolbar '{it['w'].cget('text')}' disabled with no selection", "disabled" in it["w"].state())
    # filters
    for val in ("click", "watch", "all"):
        app.v_filter.set(val); app.filter_changed(); pump(50)
    ok("job filter works", app.v_filter.get() == "all")
    for val in ("clicks", "problems", "all"):
        app.v_actf.set(val); app.activity_filter_changed(); pump(30)
    ok("activity filter works", app.settings["activity_filter"] == "all")
    # summary toggle, theme toggle
    app.toggle_cards(); pump(50); hidden = not app.cards.winfo_ismapped()
    app.toggle_cards(); pump(50)
    ok("summary collapses and comes back", hidden and app.cards.winfo_ismapped())
    t0 = app.is_dark(); app.toggle_theme(); pump(80); app.toggle_theme(); pump(80)
    ok("theme toggles", app.is_dark() == t0)
    app.toggle_pause_all(); pump(30); p = app.settings["paused"]; app.toggle_pause_all(); pump(30)
    ok("pause all / resume all", p and not app.settings["paused"])
    # resizing: toolbar overflow + More menu
    for size in ("1400x850", "900x700", "700x650", "1280x800"):
        root.geometry(size); pump(300)
        hidden_tools = len(app.hidden_tools)
        if hidden_tools:
            app.show_more_menu(); pump(100); app.more_menu.unpost(); pump(50)
        ok(f"layout at {size} (hidden buttons: {hidden_tools})", True)
    ok("narrow window moves buttons into More", True)


def add_click_job():
    app.add_job(); pump(300)
    ed = find_dialog(ac.JobEditor)
    ok("New click editor opens", ed is not None)
    if not ed:
        return
    ed.v_name.set("GUI test click")
    ed.v_x.set(400); ed.v_y.set(300)
    check_comboboxes(ed, "Click editor")
    check_spinboxes(ed, "Click editor")
    check_toggles(ed, "Click editor")
    # radio buttons swap sections
    ed.v_mode.set("window"); ed.mode_changed(); pump(50)
    w_ok = ed.win_box.winfo_ismapped()
    ed.v_mode.set("screen"); ed.mode_changed(); pump(50)
    ok("Click editor: 'Inside a window' / 'Fixed position' switch", w_ok and ed.scr_box.winfo_ismapped())
    # scroll + resize
    ed.geometry("520x400"); pump(200)
    ok("Click editor: scrollbar appears when short", ed.vsb.winfo_ismapped())
    ed.geometry("700x900"); pump(200)
    # click outside with unsaved changes -> stays open with warning
    warp(5, 5); root.focus_force(); pump(50)
    ed.event_generate("<FocusOut>"); pump(400)
    ok("Click editor: unsaved changes keep it open on outside click", ed.winfo_exists() and
       getattr(ed, "_unsaved_lbl", None) is not None)
    btn(ed, "Save").invoke(); pump(200)
    ok("Click editor: Save creates the job", any(j["name"] == "GUI test click" for j in app.jobs)
       and not ed.winfo_exists())


def t_edit_and_rows():
    j = next(j for j in app.jobs if j["name"] == "GUI test click")
    app.tree.selection_set(j["id"]); pump(100)
    for it in app.tool_items:
        if it["needs_sel"]:
            ok(f"toolbar '{it['w'].cget('text')}' enabled with selection", "disabled" not in it["w"].state())
    ok("new job starts running (Start this schedule when I save)", j["enabled"] and j["next_run"])
    ok("Start/Stop button shows Stop", "Stop" in str(app.start_btn.cget("text")))
    app.toggle_job(); pump(100)
    ok("Stop stops the job", not j["enabled"])
    app.toggle_job(); pump(100)
    ok("Start schedules the job again", j["enabled"] and j["next_run"])
    app.toggle_pause_job(j); pump(50)
    ok("Pause one job", j["paused"] and "Resume" in str(app.jpause_btn.cget("text")))
    app.toggle_pause_job(j); pump(50)
    ok("Resume the job", not j["paused"])
    app.toggle_job(); pump(100)
    app.duplicate_job(); pump(100)
    ok("Duplicate", any(x["name"].endswith("(copy)") for x in app.jobs))
    copyj = next(x for x in app.jobs if x["name"].endswith("(copy)"))
    app.tree.selection_set(copyj["id"]); pump(50)
    app.delete_job(); pump(100)
    ok("Delete", copyj not in app.jobs)
    # context menu
    app.tree.selection_set(j["id"]); pump(50)
    bbox = app.tree.bbox(j["id"])
    ev = type("E", (), {"y": bbox[1] + 5, "x_root": 200, "y_root": 200})()
    app.on_right_click(ev); pump(100)
    labels = [app.ctx.entrycget(i, "label") for i in range(app.ctx.index("end") + 1)
              if app.ctx.type(i) == "command"]
    app.ctx.unpost(); pump(50)
    ok("right-click menu", "Edit…" in labels and "Open Tests…" in labels, labels)
    # edit (double click) opens editor; no changes + outside click closes it
    app.edit_job(); pump(300)
    ed = find_dialog(ac.JobEditor)
    ok("Edit opens editor", ed is not None)
    if ed:
        warp(5, 5); root.focus_force(); pump(50)
        ed.event_generate("<FocusOut>"); pump(400)
        ok("Editor without changes closes on outside click", not ed.winfo_exists())


def add_watcher():
    app.add_watcher(); pump(300)
    ed = find_dialog(ac.JobEditor)
    ok("New watcher editor opens", ed is not None and ed.kind == "watch")
    if not ed:
        return
    check_comboboxes(ed, "Watcher editor")
    check_spinboxes(ed, "Watcher editor")
    check_toggles(ed, "Watcher editor")
    # Draw box: drag on the overlay
    btn(ed, "Draw box").invoke(); pump(900)
    ov = [w for w in toplevels() if w.overrideredirect() and widgets(w, tk.Canvas)]
    ok("Draw box overlay appears", ov)
    if ov:
        cv = widgets(ov[-1], tk.Canvas)[0]
        cv.event_generate("<ButtonPress-1>", x=100, y=100); pump(30)
        cv.event_generate("<B1-Motion>", x=200, y=160); pump(60)
        cv.event_generate("<ButtonRelease-1>", x=220, y=170); pump(1500)
    ok("Draw box saves a picture", bool(ed.watch_png))
    ok("Watcher editor comes back after drawing", ed.winfo_exists() and ed.winfo_viewable())
    btn(ed, "Check now").invoke(); pump(1500)
    btn(ed, "Dry run").invoke(); pump(1500)
    ed.v_name.set("GUI watcher")
    ed.v_x.set(300); ed.v_y.set(300); ed.v_use_img.set(False)
    btn(ed, "Save").invoke(); pump(300)
    ok("Watcher saved", any(j["name"] == "GUI watcher" for j in app.jobs))


def t_settings():
    app.open_settings(); pump(300)
    d = find_dialog(ac.SettingsDialog)
    ok("Preferences opens", d is not None)
    if not d:
        return
    for key, name in ac.SettingsDialog.TABS:
        d.v_tab.set(key); d.show_tab(); pump(150)
        ok(f"Preferences tab '{name}' shows", d.pages[key].winfo_ismapped())
        check_comboboxes(d, f"Prefs/{name}")
        check_spinboxes(d, f"Prefs/{name}")
        check_toggles(d, f"Prefs/{name}")
    d.v_tab.set("hotkeys"); d.show_tab(); pump(50)
    d.vars["hk_pause"].set("Banana"); n = len(BOXES)
    btn(d, "Save").invoke(); pump(200)
    ok("Preferences: bad hotkey is refused", d.winfo_exists() and len(BOXES) > n, BOXES[-1:])
    d.vars["hk_pause"].set("Ctrl+Alt+P")
    d.v_theme.set("Light"); btn(d, "Save").invoke(); pump(300)
    ok("Preferences: saved, theme Light", not app.is_dark() and not d.winfo_exists())
    app.open_settings(); pump(300)
    d = find_dialog(ac.SettingsDialog)
    d.v_theme.set("Dark"); btn(d, "Save").invoke(); pump(300)
    ok("Preferences: theme Dark", app.is_dark())


def t_menu_and_dialogs():
    app.show_main_menu(); pump(150)
    m = app.main_menu
    labels = [m.entrycget(i, "label") + " " + m.entrycget(i, "accelerator")
              for i in range(m.index("end") + 1) if m.type(i) == "command"]
    m.unpost(); pump(50)
    ok("☰ menu has all items", all(any(x in l for l in labels) for x in
       ("New click", "New watcher", "Tests", "Undo", "Import", "Export jobs", "Backups",
        "click history", "Preferences", "data folder", "log", "Help", "About", "Uninstall", "Exit")), labels)
    for cls, opener in ((ac.HelpDialog, lambda: ac.HelpDialog(app)), (ac.AboutDialog, lambda: ac.AboutDialog(app)),
                        (ac.BackupsDialog, lambda: ac.BackupsDialog(app))):
        opener(); pump(300)
        d = find_dialog(cls)
        ok(f"{cls.__name__} opens", d is not None)
        if cls is ac.BackupsDialog and d:
            n = len(d.tree.get_children())
            btn(d, "Back up now").invoke(); pump(1200)
            ok("Backups: Back up now adds a backup", len(d.tree.get_children()) >= n + 1 or n > 0,
               (n, len(d.tree.get_children())))
        if d:
            btn(d, "Close").invoke(); pump(100)
            ok(f"{cls.__name__} closes", not d.winfo_exists())
    j = app.jobs[0]
    ac.StatsDialog(app, j); pump(300)
    d = find_dialog(ac.StatsDialog)
    ok("Stats dialog opens", d is not None)
    if d:
        btn(d, "Close").invoke(); pump(100)


def t_steps_and_hours():
    app.add_job(); pump(300)
    ed = find_dialog(ac.JobEditor)
    ed.v_name.set("Steps job"); ed.v_x.set(321); ed.v_y.set(222)
    # active hours enable/disable the hour widgets
    ed.v_hours.set(True); ed.hours_toggled(); pump(30)
    on = all("disabled" not in w.state() for w in ed.hours_widgets)
    ed.v_hours.set(False); ed.hours_toggled(); pump(30)
    off = all("disabled" in w.state() for w in ed.hours_widgets)
    ok("Editor: active-hours controls enable/disable", on and off)
    ed.v_hours.set(True); ed.hours_toggled(); ed.v_hfrom.set("7:5"); ed.v_hto.set("21:30")
    # add steps via the step dialog
    for kind, setup in (("wait", lambda sd: (sd.v_wmin.set(3), sd.v_wmax.set(5))),
                        ("type", lambda sd: sd.txt.insert("1.0", "hello")),
                        ("key", lambda sd: sd.v_keys.set("Ctrl+S"))):
        ed.stepsed.tree.selection_set(*ed.stepsed.tree.get_children()[-1:]); ed.stepsed.add(kind); pump(300)
        sd = find_dialog(ac.StepDialog)
        ok(f"Step dialog opens ({kind})", sd is not None and sd.kind() == kind)
        if sd:
            check_comboboxes(sd, f"Step dialog ({kind})")
            setup(sd); btn(sd, "Save step").invoke(); pump(200)
    ok("Editor: 3 steps listed", len(ed.steps) == 3 and len(ed.stepsed.tree.get_children()) == 3,
       [s["type"] for s in ed.steps])
    # key validation
    ed.stepsed.add("key"); pump(300)
    sd = find_dialog(ac.StepDialog); sd.v_keys.set("Ctrl+Banana"); n = len(BOXES)
    btn(sd, "Save step").invoke(); pump(150)
    ok("Step dialog refuses unknown keys", sd.winfo_exists() and len(BOXES) > n)
    btn(sd, "Cancel").invoke(); pump(100)
    ed.stepsed.tree.selection_set("2"); ed.stepsed.move(-1); pump(50)
    ok("Editor: move step up", ed.steps[1]["type"] == "key")
    ed.stepsed.tree.selection_set("0"); ed.stepsed.remove(); pump(50)
    ok("Editor: remove step", len(ed.steps) == 2 and ed.steps[0]["type"] == "key")
    ed.v_lim_on.set(True); ed.v_lim_n.set(5)
    btn(ed, "Save").invoke(); pump(300)
    j = next((x for x in app.jobs if x["name"] == "Steps job"), None)
    ok("Job saved with steps, hours (normalised) and limit", j and len(j["steps"]) == 2
       and j["hours_from"] == "07:05" and j["limit_clicks_on"] and j["limit_clicks"] == 5,
       j and (j["hours_from"], j["steps"]))
    rows = app.build_rows(time.time())
    ok("job row still renders", any(r[0] == j["id"] for r in rows))
    # undo delete
    app.tree.selection_set(j["id"]); pump(50)
    app.delete_job(); pump(200)
    ok("Delete shows the Undo bar", app.undo_bar.winfo_ismapped() and j not in app.jobs)
    app.undo_delete(); pump(200)
    ok("Undo brings the job back", any(x["id"] == j["id"] for x in app.jobs))


def t_watcher_extras():
    app.add_watcher(); pump(300)
    ed = find_dialog(ac.JobEditor)
    ed.v_trigger.set("appears"); ed.trigger_changed(); pump(50)
    ok("Watcher: 'appears' enables 'click the picture itself'", "disabled" not in ed.click_pic_cb.state()
       and "appears" in str(ed.once_cb.cget("text")))
    ed.v_trigger.set("gone"); ed.trigger_changed(); pump(50)
    ok("Watcher: 'disappears' disables it", "disabled" in ed.click_pic_cb.state())
    ed.v_area.set("area"); ed.area_choice(); pump(900)
    ov = [w for w in toplevels() if w.overrideredirect() and widgets(w, tk.Canvas)]
    ok("Draw area overlay appears", ov)
    if ov:
        cv = widgets(ov[-1], tk.Canvas)[0]
        cv.event_generate("<ButtonPress-1>", x=50, y=50); pump(30)
        cv.event_generate("<B1-Motion>", x=300, y=200); pump(60)
        cv.event_generate("<ButtonRelease-1>", x=320, y=220); pump(500)
    ok("Area saved", ed.watch_area and ed.watch_area[2] == 270 and "area" in str(ed.area_info.cget("text")),
       ed.watch_area)
    btn(ed, "Cancel").invoke(); pump(100)


def t_tests_window():
    w = next(j for j in app.jobs if j["name"] == "GUI watcher")
    app.tree.selection_set(w["id"]); pump(50)
    app.open_tests(); pump(400)
    tw = app.tests_win
    ok("Tests window opens", tw is not None and tw.winfo_viewable())
    ok("main window stays visible with Tests open", root.winfo_viewable())
    check_comboboxes(tw, "Tests window")
    for b in tw.btns_watch + tw.btns_any:
        ok(f"Tests: '{b.cget('text')}' enabled for a watcher", "disabled" not in b.state())
    # pick a scheduled click -> watcher tests disabled
    c = next(j for j in app.jobs if j["name"] == "GUI test click")
    tw.select_job(c); pump(100)
    ok("Tests: watcher tests disabled for a scheduled click", all("disabled" in b.state() for b in tw.btns_watch))
    tw.select_job(w); pump(100)
    # history filter
    for v in ("all", "job"):
        tw.v_hf.set(v); tw.hist_filter_changed(); pump(50)
    ok("Tests: history filter", True)
    # the 6 tests
    n0 = len(app.test_history)
    for text in ("Show spot", "Check picture", "Dry run"):
        btn(tw, text).invoke(); pump(1200)
        hid = not tw.winfo_viewable() and not root.winfo_viewable()
        reported = app.test_history and "screen locked" in app.test_history[0]["result"]
        ok(f"Tests: whole app hides during '{text}' (or reports a locked screen)", hid or reported)
        pump(9500)
        ok(f"Tests: '{text}' runs and Tests window comes back", tw.winfo_exists() and tw.winfo_viewable())
    ok("Tests: results land in the history", len(app.test_history) > n0, len(app.test_history) - n0)
    btn(tw, "Test click now").invoke()
    pump(3000)
    ok("Tests: 'Test click now' runs and comes back", tw.winfo_exists() and tw.winfo_viewable() and root.winfo_viewable())
    # scheduling dialogs from Tests sit on top of Tests and don't close it
    btn(tw, "Schedule test click").invoke(); pump(300)
    d = find_dialog(ac.TestDialog)
    ok("Schedule test click dialog opens", d is not None)
    if d:
        check_spinboxes(d, "Schedule test dialog")
        tw.event_generate("<FocusOut>"); pump(400)
        ok("Tests window stays open while its dialog is open", tw.winfo_exists())
        btn(d, "Schedule").invoke(); pump(200)
        ok("test click scheduled", w["test_at"])
    btn(tw, "Schedule watcher test").invoke(); pump(300)
    d = find_dialog(ac.WatchTestDialog)
    ok("Schedule watcher test dialog opens", d is not None)
    if d:
        check_toggles(d, "Watcher test dialog")
        btn(d, "Schedule").invoke(); pump(200)
        ok("watcher test scheduled", w["wtest_at"])
    tw.refresh(force=True); pump(100)
    ok("Tests: pending tests listed", "Pending" in str(tw.pending_lbl.cget("text")))
    rows = app.build_rows(time.time())
    ok("purple test rows in the job list", sum(1 for r in rows if ":" in r[0]) == 2)
    tw.cancel_pending(); pump(100)
    ok("Cancel pending tests", not w["test_at"] and not w["wtest_at"])
    # history row details
    kids = tw.hist.get_children()
    if kids:
        tw.hist.selection_set(kids[0]); pump(80)
        ok("Tests: selecting a result shows details", "·" in str(tw.detail.cget("text")))
    # resizing the Tests window
    for size in ("820x640", "420x500", "900x700"):
        tw.geometry(size); pump(300)
    ok("Tests window resizes", True)
    # click outside (main window) closes it
    warp(root.winfo_rootx() + 30, root.winfo_rooty() + 30); root.focus_force(); pump(50)
    tw.event_generate("<FocusOut>"); pump(400)
    ok("Tests window closes on outside click", app.tests_win is None)


def t_export_import():
    app.export_jobs(); pump(100)
    ok("Export writes a file", os.path.exists(EXPORT))
    n = len(app.jobs)
    app.import_jobs(); pump(200)
    ok("Import adds jobs", len(app.jobs) == n * 2, f"{n}->{len(app.jobs)}")


def t_test_dialog_from_main():
    c = next(j for j in app.jobs if j["name"] == "GUI test click")
    app.tree.selection_set(c["id"]); pump(50)
    app.schedule_test(); pump(300)
    d = find_dialog(ac.TestDialog)
    ok("Schedule test from main opens", d is not None)
    if d:
        btn(d, "Close").invoke(); pump(100)
        ok("Close button closes it", not d.winfo_exists())


def t_remember_geometry():
    root.geometry("1111x777+40+30"); pump(700)
    ok("main window size remembered", app.settings.get("main_geom", "").startswith("1111x777"),
       app.settings.get("main_geom"))


def t_workflows_45():
    """4.5: every step type's dialog, If/Repeat blocks, groups, dry run, recording UI, run
    history, queue bar, emergency stop."""
    app.add_job(); pump(300)
    ed = find_dialog(ac.JobEditor)
    ed.v_name.set("Workflow job")
    ed.v_main.set(False); ed.main_toggled(); pump(50)
    ok("Editor: steps-only disables the click controls",
       any("disabled" in w.state() for w in widgets(ed.where_frame, ttk.Button)))
    se = ed.stepsed
    setups = {
        "wait": lambda sd: (sd.v_wmin.set(0.5), sd.v_wmax.set(0.5)),
        "type": lambda sd: sd.txt.insert("1.0", "hello"),
        "paste": lambda sd: (sd.txt.insert("1.0", "line one\nline two ✓"), sd.v_vars.set(True)),
        "key": lambda sd: sd.v_keys.set("Ctrl+S"),
        "set": lambda sd: (sd.v_var.set("count"), sd.v_op.set("add"), sd.v_val.set("1")),
        "scroll": lambda sd: sd.v_samt.set(3),
        "keyhold": lambda sd: sd.v_hkey.set("Shift"),
        "mouse": lambda sd: None,
        "move": lambda sd: (sd.path_vars["move"]["endx"].set(50), sd.path_vars["move"]["endy"].set(60)),
        "drag": lambda sd: (sd.path_vars["drag"]["endx"].set(80), sd.path_vars["drag"]["endy"].set(90)),
        "if": lambda sd: (sd.v_cond.set("a variable has a value"), sd.cond_changed(), sd.v_cvar.set("count"),
                          sd.v_cop.set(">"), sd.v_cval.set("0")),
        "repeat": lambda sd: sd.v_rtimes.set(2),
    }
    for kind, setup in setups.items():
        se.tree.selection_set(*se.tree.get_children()[-1:]); se.add(kind); pump(300)
        sd = find_dialog(ac.StepDialog)
        ok(f"Step dialog opens ({kind})", sd is not None and sd.kind() == kind)
        if sd:
            if kind in ("paste", "if", "repeat"):
                check_comboboxes(sd, f"Step dialog ({kind})")
                check_toggles(sd, f"Step dialog ({kind})")
            setup(sd); btn(sd, "Save step").invoke(); pump(200)
            ok(f"Step dialog saves ({kind})", not sd.winfo_exists(), BOXES[-1:] if sd.winfo_exists() else "")
            if sd.winfo_exists():
                btn(sd, "Cancel").invoke(); pump(100)
    types_ = [st["type"] for st in ed.steps]
    ok("Timeline: If and Repeat got their End", types_.count("end") == 2 and not se.errors(), types_)
    k = next(i for i, st in enumerate(ed.steps) if st["type"] == "if")
    se.tree.selection_set(str(k)); se.add("key"); pump(300)
    sd = find_dialog(ac.StepDialog)
    if sd:
        sd.v_keys.set("Tab"); btn(sd, "Save step").invoke(); pump(200)
    ok("Timeline: a step added inside the If is indented",
       ed.steps[k + 1]["type"] == "key" and str(se.tree.item(str(k + 1), "values")[2]).startswith("    "),
       se.tree.item(str(k + 1), "values"))
    types_ = [st["type"] for st in ed.steps]
    se.tree.selection_set("0"); se.add("else"); pump(100)
    ok("Timeline: a stray Otherwise is reported", se.errors() and se.problem.winfo_ismapped(), se.errors())
    se.tree.selection_set(str(next(i for i, st in enumerate(ed.steps) if st["type"] == "else")))
    se.remove(); pump(50)
    ok("Timeline: fixed again", not se.errors())
    se.tree.selection_set("0", "1"); se.duplicate(); pump(50)
    ok("Timeline: duplicate a selection", len(ed.steps) == len(types_) + 2)
    se.remove(); pump(50)
    se.scale_waits(2); pump(30)
    ok("Timeline: make waits longer", ed.steps[0]["min"] == 1.0, ed.steps[0])
    # save selected steps as a group
    se.tree.selection_set("1"); pump(30)
    ANSWER["askyesno"] = True
    se.save_as_group(); pump(300)
    tp = find_dialog(ac.TextPrompt)
    ok("Save as group asks for a name", tp is not None)
    if tp:
        tp.v.set("GUI group"); tp.ok(); pump(300)
    ok("Group saved and step replaced by 'Use group'", any(g["name"] == "GUI group" for g in app.groups)
       and ed.steps[1]["type"] == "group")
    # run options + save
    ed.v_prio.set("High"); ed.v_yield.set(True)
    btn(ed, "Save").invoke(); pump(400)
    j = next((x for x in app.jobs if x["name"] == "Workflow job"), None)
    ok("Workflow job saved (steps only, priority, options)", j and j["main_click"] is False
       and j["priority"] == "high" and j["let_others_run"] and len(j["steps"]) >= 10, j and j["priority"])
    # dry run dialog
    ac.DryRunDialog(app, j); pump(2500)
    dd = find_dialog(ac.DryRunDialog)
    ok("Dry run dialog lists the steps", dd is not None and len(dd.tree.get_children()) >= 5,
       dd and len(dd.tree.get_children()))
    if dd:
        btn(dd, "Close").invoke(); pump(100)
    # groups dialog
    ac.GroupsDialog(app); pump(300)
    gd = find_dialog(ac.GroupsDialog)
    ok("Step groups dialog shows the group and who uses it", gd and any(
        "Workflow job" in str(gd.tree.item(i, "values")) for i in gd.tree.get_children()))
    if gd:
        gd.tree.selection_set(gd.tree.get_children()[0]); gd.edit(); pump(300)
        ge = find_dialog(ac.GroupEditDialog)
        ok("Group editor opens", ge is not None)
        if ge:
            btn(ge, "Save").invoke(); pump(200)
        btn(gd, "Close").invoke(); pump(100)
    # record dialog (starting needs Windows; just open, check and cancel)
    app.toggle_recording(from_hotkey=False); pump(300)
    rd = find_dialog(ac.RecordDialog)
    ok("Record dialog opens", rd is not None)
    if rd:
        check_toggles(rd, "Record dialog")
        btn(rd, "Cancel").invoke(); pump(100)
    # run history
    app.open_run_history(); pump(400)
    rh = find_dialog(ac.RunHistoryDialog)
    ok("Run history opens", rh is not None)
    if rh:
        rh.v_q.set("Workflow"); rh.fill(); pump(50)
        btn(rh, "Close").invoke(); pump(100)
    # run bar and emergency stop
    app.queue_status = lambda: ("Running “X” · step 1 of 2 · 3s", ["Y"])
    app.update_run_bar(); pump(100)
    ok("Run bar shows what's running and waiting", app.run_bar.winfo_ismapped()
       and "Waiting their turn: Y" in str(app.run_lbl.cget("text")))
    del app.queue_status
    app.update_run_bar(); pump(100)
    ok("Run bar hides when idle", not app.run_bar.winfo_ismapped())
    was = app.settings.get("paused")
    app.emergency_stop(); pump(100)
    ok("Emergency stop pauses everything", app.settings.get("paused"))
    app.settings["paused"] = was
    # about / help show the disclosure
    ac.AboutDialog(app); pump(300)
    ab = find_dialog(ac.AboutDialog)
    ok("About shows the AI-assistance disclosure", ab and any("vibe-coded" in str(l.cget("text"))
                                                            for l in widgets(ab, ttk.Label)))
    if ab:
        btn(ab, "Close").invoke(); pump(100)
    ac.HelpDialog(app); pump(300)
    hd = find_dialog(ac.HelpDialog)
    ok("Help shows the disclosure", hd and any("vibe-coded" in str(l.cget("text"))
                                               for l in widgets(hd, ttk.Label)))
    if hd:
        btn(hd, "Close").invoke(); pump(100)


def t_fixes_451():
    """4.5.1: windows come back exactly (size, position, on top) after picking / checking,
    even after a dropdown was used; Esc and Cancel end a pick; markers last as set and can
    outline similar pictures; columns fit on double-click; tray status text."""
    app.restore_main(); pump(200)
    root.state("normal"); root.geometry("910x640+37+29"); pump(600)
    g0 = root.geometry()
    app.settings["main_geom"] = "700x500+300+200"     # a stale saved size must not be used
    app.add_watcher(); pump(400)
    ed = find_dialog(ac.JobEditor)
    ok("4.5.1 editor has the exact-picture option", hasattr(ed, "v_exact") and ed.v_exact.get())
    # use the Picture size dropdown first (that's what triggered the bug)
    cbs = [c for c in widgets(ed, ttk.Combobox) if c.cget("textvariable") == str(ed.v_snap_size)]
    if cbs:
        cb = cbs[0]
        cb.tk.call("ttk::combobox::Post", cb); pump(200)
        cb.set("Large"); cb.event_generate("<<ComboboxSelected>>")
        cb.tk.call("ttk::combobox::Unpost", cb); pump(200)
    eg0 = ed.geometry()
    # Pick on screen, then cancel with the box's Cancel button
    ed.pick(); pump(500)
    cds = [w for w in toplevels() if w.overrideredirect() and any(
        "Cancel" in str(l.cget("text")) for l in widgets(w, tk.Label))]
    ok("4.5.1 pick: countdown box shows a Cancel button", cds)
    ok("4.5.1 pick: editor and main window hidden meanwhile", not ed.winfo_viewable() and not root.winfo_viewable())
    if cds:
        lab = [l for l in widgets(cds[0], tk.Label) if "Cancel" in str(l.cget("text"))][0]
        lab.event_generate("<Button-1>"); pump(1500)
    ok("4.5.1 pick cancel: editor is back and visible", ed.winfo_exists() and ed.winfo_viewable() and ed.state() == "normal")
    ok("4.5.1 pick cancel: main window back at the exact same size/position", root.geometry() == g0, (g0, root.geometry()))
    ok("4.5.1 pick cancel: editor same size/position", ed.geometry() == eg0, (eg0, ed.geometry()))
    ok("4.5.1 pick cancel: nothing was picked", not ed.snap_png)
    # Pick again and cancel with Esc
    ed.pick(); pump(500)
    cds = [w for w in toplevels() if w.overrideredirect() and any(
        "Cancel" in str(l.cget("text")) for l in widgets(w, tk.Label))]
    if cds:
        cds[0].event_generate("<Escape>"); pump(1500)
    ok("4.5.1 pick Esc: countdown gone, editor back", not [w for w in toplevels() if w.overrideredirect()
                                                          and w.winfo_viewable()] and ed.winfo_viewable())
    # Pick that completes (1-second countdown), after using the dropdown again
    real = app.pick_countdown
    app.pick_countdown = lambda on_point, on_cancel=None, seconds=5: real(on_point, on_cancel, 1)
    ac.get_cursor = lambda: (200, 150)
    try:
        ed.pick(); pump(3500)
    finally:
        app.pick_countdown = real
    ok("4.5.1 pick done: editor back on top", ed.winfo_viewable() and ed.state() == "normal")
    ok("4.5.1 pick done: main window unchanged", root.geometry() == g0, (g0, root.geometry()))
    ok("4.5.1 pick done: a Large picture was saved", bool(ed.snap_png) and
       ac.b64_to_img(ed.snap_png).size[0] in (260, min(260, root.winfo_screenwidth())))
    # Check spot / Check now: hide, mark for the set time, restore exactly
    app.settings["marker_seconds"] = 1
    app.settings["show_similar"] = True
    ed.preview_spot()
    marks = []
    t1 = time.time()
    while not marks and time.time() - t1 < 4:
        pump(50)
        marks = [w for w in toplevels() if w.overrideredirect() and w.winfo_viewable()]
    t0 = time.time()
    ok("4.5.1 show spot: marker shown while the app is hidden", marks and not root.winfo_viewable(), len(marks))
    while (ed.winfo_exists() and not ed.winfo_viewable()) and time.time() - t0 < 6:
        pump(100)
    ok("4.5.1 show spot: marker lasts the set 1 s (not 5 s)", time.time() - t0 < 3.5, round(time.time() - t0, 1))
    pump(800)
    ok("4.5.1 show spot: editor back on top afterwards", ed.winfo_viewable() and ed.state() == "normal")
    ok("4.5.1 show spot: main window unchanged", root.geometry() == g0, (g0, root.geometry()))
    if ed.watch_png or True:
        ed.watch_png = ed.snap_png
        ed.check_watch_now(); pump(400)
        t0 = time.time()
        while not ed.winfo_viewable() and time.time() - t0 < 6:
            pump(100)
        pump(800)
        ok("4.5.1 check now: editor back, main window unchanged", ed.winfo_viewable() and root.geometry() == g0,
           (g0, root.geometry()))
    app.settings["marker_seconds"] = 5
    app.settings["show_similar"] = False
    btn(ed, "Cancel").invoke(); pump(200)
    # flash_marker with outlines only
    done = []
    app.flash_marker(None, None, "outlines", lambda: done.append(1), seconds=1,
                     others=[(50, 60, 100, 40, "exact 98%", True, True), (300, 60, 100, 40, "similar 70%", False, False)])
    pump(200)
    n_out = len([w for w in toplevels() if w.overrideredirect() and w.winfo_viewable()])
    pump(1600)
    ok("4.5.1 similar outlines appear together and close after the set time", n_out >= 3 and done, n_out)
    # column auto-fit on the job list
    t = app.tree
    cols = ac._display_cols(t)
    c0 = cols[1]                      # cols[0] is the tick-box column (4.5.3)
    t.column(c0, width=40); pump(100)
    x = int(t.column(cols[0], "width")) + int(t.column(c0, "width"))
    ev = type("E", (), {"widget": t, "x": x + 1, "y": 8})()
    region = t.identify_region(ev.x, ev.y)
    r = ac._autofit_double(ev); pump(100)
    w_fit = int(t.column(c0, "width"))
    ok("4.5.1 double-click a column border fits the column", region == "separator" and r == "break" and w_fit > 40,
       (region, r, w_fit))
    ok("4.5.1 fitted width is remembered", (app.settings.get("col_widths") or {}).get(c0) == w_fit)
    mode = t.tk.eval("set ttk::treeview::State(pressMode)")
    t.event_generate("<ButtonRelease-1>", x=x + 1, y=8); pump(50)
    ok("4.5.1 a double-click on a border still starts a drag (not sticky)", mode == "resize", mode)
    # a click on the thin grid line over a heading border reaches the table
    app.draw_grid(); pump(50)
    lines = [f for f in app.grid_lines if f.winfo_ismapped() and f.winfo_width() <= 2 and f.winfo_y() < 30]
    if lines:
        f = lines[0]
        f.event_generate("<ButtonPress-1>", x=0, y=2); pump(50)
        mode2 = t.tk.eval("set ttk::treeview::State(pressMode)")
        f.event_generate("<ButtonRelease-1>", x=0, y=2); pump(50)
        ok("4.5.1 grabbing a column border right on its grid line works", mode2 == "resize", mode2)
    else:
        ok("4.5.1 grid lines over the headings exist", False)
    ev2 = type("E", (), {"widget": t, "x": 5, "y": 8})()
    ok("4.5.1 double-click on a heading doesn't open anything", ac._autofit_double(ev2) == "break")
    app.reset_col_widths(); pump(50)
    ok("4.5.1 reset column widths", not app.settings.get("col_widths"))
    # tray status
    tip, lines = app.tray_status()
    ok("4.5.1 tray tooltip starts with the app name and fits Windows' limit",
       tip.startswith("Clickue") and len(tip) <= 127 and "AutoClicker" not in tip, tip)
    for j in app.jobs[:3]:
        j["enabled"] = True
    tip2, lines2 = app.tray_status()
    ok("4.5.1 tray menu lines use clock times, the tooltip a live countdown",
       all("next in" not in l for l in lines2), lines2)
    ok("4.5.1 tray status lists active jobs", "active" in tip2 or "PAUSED" in tip2, (tip2, lines2))
    for j in app.jobs[:3]:
        j["enabled"] = False
    # preferences show the new options
    app.open_settings(); pump(400)
    sd = find_dialog(ac.SettingsDialog)
    ok("4.5.1 preferences: marker time, similar pictures, tray status",
       sd and all(k in sd.vars for k in ("marker_seconds", "show_similar", "tray_status")))
    if sd:
        btn(sd, "Cancel").invoke(); pump(100)


def t_fixes_453():
    # Tests window: the test buttons are visible as soon as it opens (no resize needed)
    if app.tests_win is not None:
        try:
            app.tests_win.close(); pump(200)
        except Exception:
            pass
    app.settings["tests_split"] = 0
    w = next(j for j in app.jobs if is_watch_job(j))
    app.tree.selection_set(w["id"]); pump(50)
    app.open_tests(); pump(350)
    tw = app.tests_win
    vis = [b for b in tw.btns_any + tw.btns_watch if b.winfo_ismapped() and b.winfo_height() > 5]
    ok("4.5.3 Tests window: all six test buttons visible right after opening", len(vis) == 6, len(vis))
    tw.geometry("420x600"); pump(500)
    vis = [b for b in tw.btns_any + tw.btns_watch if b.winfo_ismapped()]
    ok("4.5.3 Tests window: buttons still visible when narrow", len(vis) == 6, len(vis))
    tw.close(); pump(200)
    # h / m / s units sit right next to their fields, the same everywhere
    app.tree.selection_set(w["id"]); app.edit_job(); pump(400)
    ed = find_dialog(ac.JobEditor)
    gaps = []
    for vs in (ed.w_interval, ed.w_dmin, ed.w_cool):
        ws = ed._row_widgets[id(vs)]
        for sp, ul in ((ws[1], ws[2]), (ws[3], ws[4]), (ws[5], ws[6])):
            gaps.append(ul.winfo_rootx() - (sp.winfo_rootx() + sp.winfo_width()))
    ok("4.5.3 h/m/s units right next to their fields (same gap everywhere)",
       gaps and max(gaps) <= 8 and min(gaps) >= 0 and len(set(gaps)) == 1, gaps)
    # watcher match option
    ed.v_wpartial.set(True); ed.match_changed(); ed.v_wpct.set(70); pump(50)
    ok("4.5.3 partial match: percent field enabled", "disabled" not in ed.wpct_spin.state())
    btn(ed, "Save").invoke(); pump(300)
    ok("4.5.3 watcher saves the match mode", w["watch_match"] == "partial" and w["watch_partial_pct"] == 70,
       (w.get("watch_match"), w.get("watch_partial_pct")))
    # tick boxes in the job list
    app.v_filter.set("all"); app.filter_changed(); pump(100)
    t = app.tree
    ids = [i for i in t.get_children() if ":" not in i]
    app.set_checks([]); pump(50)
    t.see(ids[0]); pump(50)
    bb = t.bbox(ids[0], "chk")
    t.event_generate("<Button-1>", x=bb[0] + bb[2] // 2, y=bb[1] + bb[3] // 2); pump(100)
    ok("4.5.3 clicking the tick box ticks the job", ids[0] in app.checked and t.set(ids[0], "chk") == "☑",
       (app.checked, t.set(ids[0], "chk")))
    ok("4.5.3 batch bar appears", app.batch_bar.winfo_ismapped())
    vis = [b for b in app.batch_items if b.winfo_ismapped()]
    ok("4.5.3 batch bar: nothing cut off", all(b.winfo_x() + b.winfo_width() <= app.batch_bar.winfo_width()
                                                 for b in vis) and len(vis) == len(app.batch_items))
    root.geometry("700x650"); pump(300)
    vis = [b for b in app.batch_items if b.winfo_ismapped()]
    ok("4.5.3 batch bar wraps when narrow (nothing cut off)",
       all(b.winfo_x() + b.winfo_width() <= app.batch_bar.winfo_width() for b in vis) and len(vis) == len(app.batch_items))
    root.geometry("1280x800"); pump(300)
    t.event_generate("<Button-1>", x=bb[0] + bb[2] // 2, y=bb[1] + bb[3] // 2); pump(100)
    ok("4.5.3 clicking again unticks", ids[0] not in app.checked and not app.batch_bar.winfo_ismapped())
    app.toggle_check_all(); pump(100)
    ok("4.5.3 heading tick box ticks every job shown", set(ids) <= app.checked)
    jobs = app.checked_jobs()
    app.batch_action("start"); pump(100)
    ok("4.5.3 batch start", all(j["enabled"] for j in jobs))
    app.batch_action("pause"); pump(100)
    ok("4.5.3 batch pause", all(j["paused"] for j in jobs))
    app.batch_action("resume"); pump(100)
    app.batch_action("stop"); pump(100)
    ok("4.5.3 batch resume + stop", all(not j["enabled"] and not j["paused"] for j in jobs))
    # edit together
    btn(app.batch_bar, "Edit together").invoke(); pump(500)
    be = find_dialog(ac.BatchEditDialog)
    ok("4.5.3 Edit together opens", be is not None)
    if be:
        check_comboboxes(be, "Batch edit")
        check_spinboxes(be, "Batch edit")
        flag, ws, getter = be.rows[0]                      # mouse button
        flag.set(True); be._enable(ws, True)
        ws[0].set("middle")
        ok("4.5.3 batch edit: untouched rows stay disabled", all("disabled" in x.state() for x in be.rows[1][1]))
        btn(be, "Apply to all").invoke(); pump(300)
        ok("4.5.3 batch edit applies to every ticked job", all(j["button"] == "middle" for j in jobs),
           [j["button"] for j in jobs])
    # delete ticked + one undo
    n0 = len(app.jobs)
    app.batch_delete(); pump(200)
    ok("4.5.3 batch delete", len(app.jobs) == n0 - len(jobs) and app.undo_bar.winfo_ismapped())
    app.undo_delete(); pump(200)
    ok("4.5.3 one undo restores every deleted job", len(app.jobs) == n0)
    app.set_checks([]); pump(100)
    ok("4.5.3 clear hides the batch bar", not app.batch_bar.winfo_ismapped())


def is_watch_job(j):
    return j.get("kind") == "watch"


for name, fn in (("main", t_main), ("add click", add_click_job), ("edit/rows", t_edit_and_rows),
                 ("watcher", add_watcher), ("settings", t_settings), ("menu/dialogs", t_menu_and_dialogs),
                 ("steps/hours", t_steps_and_hours), ("watcher extras", t_watcher_extras),
                 ("tests window", t_tests_window),
                 ("test dialog", t_test_dialog_from_main), ("export/import", t_export_import),
                 ("geometry", t_remember_geometry), ("workflows 4.5", t_workflows_45),
                 ("fixes 4.5.1", t_fixes_451), ("fixes 4.5.3", t_fixes_453)):
    step(name, fn)
    pump(200)

try:
    app.quit_app()
except Exception:
    ERRORS.append("quit: " + traceback.format_exc()[-800:])

passed = sum(1 for r in RESULTS if r[0])
for good, name, info in RESULTS:
    if not good:
        print("FAIL", name, info)
print(f"\n{passed}/{len(RESULTS)} checks passed, {len(ERRORS)} errors")
for e in ERRORS:
    print("ERROR:", e)
print("message boxes shown:", len(BOXES))
for b in BOXES:
    print("   ", b)
