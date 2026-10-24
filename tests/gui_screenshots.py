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
app.stop.set(); root.destroy()
print("done")
