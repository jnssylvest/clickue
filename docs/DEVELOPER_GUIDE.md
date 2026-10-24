# Clickue developer guide

Everything a developer (or an AI coding session) needs to understand, rebuild, change, test
and release Clickue. User-facing docs: [README](../README.md) · [FEATURES](../FEATURES.md) ·
[USER_GUIDE](USER_GUIDE.md).

## 1. What Clickue is (one paragraph)

A Windows tray app (Python 3 + Tkinter) that performs **scheduled clicks** (interval +
optional random delay) and runs **screen watchers** (click when a saved picture disappears or
appears). Click spots are found by **picture matching** (OpenCV multi-scale template matching),
so they survive moved windows, resolution changes and DPI scaling (e.g. RDP vs. VM console).
Extras: active hours, run limits, multi-step jobs (click/wait/type/keys), global hotkeys,
Discord/Telegram alerts, daily backups, undo, click history + CSV, a Tests window, portable
mode, installer. Formerly named *Scheduled AutoClicker*.

## 2. Repository layout

```
src/clickue.py            the whole app (single file, ~6,700 lines)
assets/                   clickue.ico, logo.png, logo-128.png (all generated from make_logo())
installer/clickue.iss     Inno Setup 6 script (per-user or all-users install)
installer/portable.txt    marker file shipped in the portable zip
scripts/*.bat             run from source / build the exe locally (Windows)
tests/                    headless logic tests + a GUI test (see section 8)
.github/workflows/build.yml   Windows build + automatic GitHub Release
docs/                     USER_GUIDE.md, this file, images/ (screenshots go here)
README.md FEATURES.md CHANGELOG.md LICENSE (MIT) requirements.txt
```

## 3. Runtime & dependencies

- **Windows 10/11, 64-bit** for real use. Clicking, screen capture, hotkeys, tray, start-with-
  Windows and the DPI/window APIs are Win32 via `ctypes` (`user32`, `kernel32`, `shcore`,
  `dwmapi`) and `winreg`.
- Python **3.10+** (CI builds with 3.12). Packages (`requirements.txt`): `pillow`
  (screenshots via `ImageGrab`, images), `pystray` (tray), `opencv-python-headless` + `numpy`
  (picture matching). Each is optional at import time: flags `HAVE_PIL`, `HAVE_TRAY`, `HAVE_CV`
  disable features gracefully.
- On non-Windows (`IS_WIN = False`) the UI opens for preview and tests, but nothing clicks and
  `screen_available()` is always False.
- Command line: `--minimized` (start hidden), `--make-icon PATH` (write the .ico and exit).

## 4. Architecture of `src/clickue.py` (top to bottom)

| Section | Key items |
|---|---|
| Constants & paths | `APP_NAME/APP_ID = "Clickue"`, `OLD_APP_ID = "ScheduledAutoClicker"`, **`VERSION`**, `PORTABLE`, `DATA_DIR` (`%APPDATA%\Clickue`, or `<exe folder>\ClickueData` when a `portable`/`portable.txt` file sits next to the program), `RUNTIME_KEYS` |
| Windows API | ctypes prototypes; `get_cursor`, `screen_available` (OpenInputDesktop + SwitchDesktop, False when locked/disconnected), `idle_seconds`, `do_click` (SetCursorPos + mouse_event, restores the cursor), `keep_awake` |
| Window targets | `describe_point`, `find_window`, `bring_to_front`, `resolve_target` (screen / inside-a-window modes) |
| Picture matching | `capture_snapshot`, `_match`, `find_picture`, `is_match`, `locate_spot` (click targets), `picture_on_screen` (watchers: stricter, plus `color_difference`), `job_area` |
| UI helpers | `make_logo`, `write_icon_file`, `migrate_old_data`, `set_run_at_startup`, popup click-outside helpers (`_held`, `ui_held`, `dropdown_open`, `pointer_over`, `close_on_click_outside`), formatting, `read_json`/`write_json` (atomic) |
| Clickue extras | active hours (`in_active_hours`, `next_active_start`, `describe_hours`), keyboard (`parse_combo`, `send_text` via SendInput unicode, `press_keys`), alerts (`send_alert`), history CSV (`append_history`, `read_history`, `trim_history`, `job_stats`), backups (`make_backup`, `list_backups`, `prune_backups`), hotkeys (`parse_hotkey`, `HotkeyThread` = RegisterHotKey + GetMessage loop) |
| Data model | `DEFAULT_SETTINGS`, `new_job()`, `new_watch()`, `is_watch()`, colour palettes `LIGHT`/`DARK` |
| `App` | everything stateful: load/save, scheduler thread, watcher engine, `perform`/`run_steps`/`execute`, UI build + theming, job list rows, tray, hotkeys, backups, undo, tests window plumbing, uninstall |
| Dialogs | `Dialog` (base: resizable, scrollable body, pinned footer, remembers geometry, click-outside closes unless unsaved), `JobEditor` (clicks and watchers), `TestDialog`, `WatchTestDialog`, `StepDialog`, `BackupsDialog`, `StatsDialog`, `HelpDialog`, `AboutDialog`, `SettingsDialog` (= tabbed Preferences), `TestsWindow` (floating Toplevel) |
| `main()` | single-instance mutexes (new + old name), `App(root)`, `mainloop()` |

### Threads
- **UI thread:** Tk mainloop. `ui_tick()` runs every 1 s (log queue, rows, cards, buttons,
  `own_visible`); `poll_cmds()` every 200 ms drains `cmdq` (tray/hotkey commands: `show`,
  `pause`, `toggle_window`, `exit`).
- **Scheduler thread:** `scheduler_loop()` wakes every 1 s, collects due work under
  `self.lock` (an RLock), then runs it: `execute(job, "scheduled"|"test"|"manual")`,
  `watch_check`, `watch_click`, `watch_test`. Long waits inside multi-step jobs block this
  thread (acceptable; steps are short).
- **Hotkey thread**, **tray** (pystray `run_detached`), and short-lived threads for alerts and
  "Test click now". **Never touch Tk widgets from non-UI threads.** Use `self.log()` (a queue)
  or `cmdq`.

### Data files (in `DATA_DIR`)
`settings.json`, `jobs.json` (`{"app","version","jobs":[...]}`), `test_history.json`,
`click_history.csv` (capped at 50,000 rows), `clickue.log` (+ `.1`, `.2`, RotatingFileHandler),
`backups/YYYY-MM-DD_HHMMSS_<tag>.json` (tags: `auto`, `manual`, `before-restore`).
All JSON is written atomically (`.tmp` + `os.replace`). A corrupt file is copied to
`.corrupt` and defaults are used.

### Job model (`new_job()`)
A job is a plain dict. **Settings fields** are saved and exported; **runtime fields** (listed in
`RUNTIME_KEYS`) are cleared on duplicate/import/export.
- Common: `id, name, kind ("click"|"watch"), enabled, paused, button, clicks, count, last_result`
- Where to click: `x, y, target_mode ("screen"|"window"), window_title, window_class, rel_x,
  rel_y, client_w, client_h, bring_to_front, scale_with_window, scale_with_screen,
  pick_screen, use_image, snap_png (base64 PNG), snap_spot, snap_size, image_fallback, pick_dpi`
- Schedule (click): `interval_s, delay_min_s, delay_max_s, random_on, anchored, first_time`;
  runtime `base_next, next_run, deadline`
- Watcher: `watch_png, watch_trigger ("gone"|"appears"), watch_click_picture, watch_area,
  watch_area_screen, watch_interval_s, watch_confirm, watch_random_on, watch_delay_min_s,
  watch_delay_max_s, watch_cooldown_on, watch_cooldown_s, watch_once`; runtime `next_check,
  last_check, last_seen, miss_count, watch_state ("seen"|"missing"|"unknown"), armed,
  pending_click_at, pending_since, watch_scale, watch_note, found_xy, once_logged`
- Rules: `hours_on, hours_from, hours_to, hours_days [0=Mon..6=Sun], hours_outside
  ("wait"|"skip"), limit_clicks_on, limit_clicks, limit_until_on, limit_until
  ("YYYY-MM-DD HH:MM")`; runtime `run_clicks`
- Steps: `steps: [{type:"click", x, y, use_image, snap_png, snap_spot, button, clicks, ...} |
  {type:"wait", min, max} | {type:"type", text} | {type:"key", keys}]`
- Tests: runtime `test_at, test_deadline, wtest_at, wtest_deadline, wtest_click`

### Compatibility rules (don't break users' data)
1. **Never rename or remove a saved key.** Add new keys to `new_job()` / `DEFAULT_SETTINGS`
   with a default that keeps old behaviour. `load()` merges saved data over `new_job()`, so old
   files gain new fields automatically.
2. New runtime-only fields go into `RUNTIME_KEYS` too.
3. Nested dict defaults (e.g. `alert_events`, `dlg_geom`) must be **replaced, not mutated**
   (`DEFAULT_SETTINGS` is shallow-copied).
4. `load()` only keeps settings keys that exist in `DEFAULT_SETTINGS`.
5. Keep `migrate_old_data()` (copies `%APPDATA%\ScheduledAutoClicker` once, leaving it as a
   backup) and the old-name mutex check in `main()`.
6. **Startup prompts (in `App.__init__`, before `load()` builds the UI):**
   - If `DATA_DIR` doesn't exist yet and the old folder has jobs (`count_saved_jobs`), ask
     *"Import them?"*. Never import silently. Saying No still creates `DATA_DIR`, so it isn't
     asked again.
   - The installer writes `install.ini` (`[Install] Id=<timestamp>`) next to `Clickue.exe`.
     `read_install_id()` compares it with `settings["install_id"]`. On a new id, if jobs exist,
     ask *"Keep them?"*. No means backup (tag `before-fresh-start`) and an empty job list. The id
     is then stored, so each Windows user is asked once per install. Portable/source runs have
     no `install.ini` and never ask.
   - The uninstaller (Inno `[Code]`) asks whether to delete `%APPDATA%\Clickue` too.

## 5. Behaviour decisions & hard-won lessons (keep these)

**Scheduling**
- Anchored schedule: the next base time is the previous *base* + interval (skipping passed
  slots), and the random delay is added on top, so delays never drift the schedule.
- A due click retries every 30 s while the screen is unavailable, until `retry_minutes`
  (default 15) past its time, then it's marked **Missed** and the next slot is scheduled. A
  click that's long overdue (app was closed) is marked missed without clicking.
- Pausing one job keeps its schedule; on resume an overdue click is skipped
  (`schedule_after_run`). Stop clears it.
- Outside active hours: `hours_outside="wait"` moves `next_run` to `next_active_start()`
  (plus a random delay); `"skip"` jumps to the next slot.

**Picture matching** (tuning constants near `MATCH_*` / `WATCH_*`)
- `find_picture` tries scales `MATCH_SCALES` (a DPI ratio hint and the last seen scale go
  first), keeps the top candidates per scale, and scores each on the **whole picture** and a
  **60×34 close-up around the spot**. It needs `whole ≥ 0.65` and `close-up ≥ 0.62`.
- `_match` **must** reject windows whose contrast is far below or above the template's
  (`sd < 0.5·σ` or `> 2·σ`). Without this, flat areas give false "perfect" matches. This was a
  real bug.
- Look-alikes: among near-equal candidates, take the one nearest the saved position.
- Watchers are stricter (`picture_on_screen`): at the drawn size both scores must be ≥ 0.93,
  and the Lab colour difference must be ≤ 15 (brightness ≤ 25). Grayscale-only matching once
  counted a red "OFFLINE" badge as the green "CONNECTED" one.
- Before screenshots for click spots, `grab_screen()` moves the mouse away for 0.3 s to avoid
  hover effects. Watchers capture without moving the mouse.

**Watchers**
- `watch_check` sets `hit = found` ("appears") or `not found` ("gone"). Hits count up to
  `watch_confirm` (re-checks every ≤ 5 s), then a click is scheduled after the optional random
  delay. A non-hit resets the count and **re-arms** "click once".
- After a successful click, `miss_count` is **not** reset, so if the condition still holds after
  the cool-down (or the normal interval if the cool-down is off), it clicks again immediately
  (when "click once" is off).
- "Gone" watchers don't count a miss while any Clickue window is visible (`own_visible`,
  updated by `ui_tick`), because it might be covering the picture.
- "Click the picture itself" re-finds the picture at click time; if it has vanished, nothing is
  clicked.

**UI**
- Theme: `ttk` `clam` re-styled from `LIGHT`/`DARK` palettes in `apply_theme()`. Dark title bar
  via DwmSetWindowAttribute. `Seg.TRadiobutton` = segmented tabs/filters.
- Treeview has no grid lines; `draw_grid()` overlays 1-px Frames for column/row lines.
- Toolbar overflow: `layout_toolbar()` places buttons on one row and moves the lowest-priority
  ones into **More ▾**. Table columns hide by priority in `on_tree_resize()`.
- Popups: `Dialog` and `TestsWindow` close on **click outside** via
  `close_on_click_outside()`. It must ignore our own message boxes (monkey-patched
  `messagebox`/`filedialog` wrappers set `_UI_HOLD`), **open combobox dropdowns**
  (`dropdown_open`: the popdown is a separate window; this was a real bug where dropdowns
  wouldn't stay open), the pointer being over the popup, child dialogs (`belongs_to` walks
  `.master`), `_spot_busy` (tests running) and `_hold` (Pick/Draw in progress). Editors with
  unsaved changes refuse to close (snapshot of `tk.Variable`s).
- **No `grab_set()` anywhere** (modal grabs broke click-outside).
- `hide_app(parent)` hides every visible app window during tests and returns `restore()`.
  The main window is restored with `restore_main()` (keeps maximized state and geometry).
  Never use `root.state("normal")` directly, since it un-maximizes the window.
- Window geometry is remembered (`main_geom`/`main_zoomed`, `tests_geom`, `dlg_geom[class]`)
  and clamped with `fit_geometry()` because screen sizes differ between RDP and console.
- DPI-aware (`SetProcessDpiAwareness(2)`). On-screen markers are positioned with
  `SetWindowPos`, so they line up exactly with mouse coordinates.
- The pick countdown box dodges the mouse (jumps to the farthest corner) and can be dragged
  (the countdown pauses while dragging).

## 6. Run from source (Windows)

```bat
pip install -r requirements.txt
pythonw src\clickue.py          rem or double-click scripts\Start Clickue.bat
```

## 7. Build

- **Locally:** `scripts\Build Clickue EXE.bat` → `dist\Clickue.exe` (PyInstaller `--onefile
  --noconsole --icon assets\clickue.ico --hidden-import pystray._win32`).
- **Installer locally:** install Inno Setup 6, set `CLICKUE_VERSION=4.1`, run
  `ISCC installer\clickue.iss` → `dist\Clickue-Setup-4.1.exe`.
- **Icon/logo:** generated by `make_logo()`. After changing it, regenerate the assets with
  `python src\clickue.py --make-icon assets\clickue.ico`, and save PNGs with
  `make_logo(256)` / `make_logo(128)`.

## 8. Tests

Run from the repository root.

| Command | What | Expected |
|---|---|---|
| `python tests/test_watchers.py` | watcher scenarios (seen/gone/flicker/scaling/look-alikes/retries) | `RESULT 21/21` |
| `python tests/test_features.py` | hours, limits, steps, appears/area, history, backups, undo, alerts (faked network), migration, install id | `RESULT 48/48` |
| `python tests/test_click_spot.py` | click-spot matching at 3 picture sizes × 8 screens (100–175 % scaling, moved, look-alikes) | `0 of 24` failures |
| `python tests/gui_test.py` | drives every window and control of the real UI | `N/N checks passed, 0 errors` |
| `python tests/gui_screenshots.py` | saves screenshots to `tests/screenshots/` | `done` |

- The three `test_*.py` files are **headless**: `tests/sim_helpers.py` stubs out `tkinter`,
  loads `src/clickue.py`, and draws fake app screens with PIL (needs any TrueType font). They
  run on Linux or Windows and replace screen capture and clicking with fakes.
- The GUI tests need a Python **with tkinter** and a display. On Linux, use `Xvfb :99` and
  `DISPLAY=:99`; the screenshot script grabs from `:99`. On a headless Linux box where the
  system Python lacks tkinter, `uv python install 3.13` provides one, using the system
  site-packages via `PYTHONPATH`. On Linux the screen counts as "locked", so tests that need a
  real unlocked Windows screen report that instead.
- **Run all of them before every release.** After any UI change, also look at the screenshots.

## 9. Making a new version (checklist)

1. Make the change in `src/clickue.py`, following the compatibility rules (section 4).
2. Bump `VERSION = "x.y"` near the top of `src/clickue.py`.
3. Add an entry at the top of `CHANGELOG.md`. Update `FEATURES.md`, `docs/USER_GUIDE.md` and
   `README.md` if the behaviour or UI changed.
4. Run the tests (section 8).
5. Commit and push to `main`. That's all: the workflow builds and publishes the release.

## 10. GitHub: repository, CI and releases

- Repository: `https://github.com/jnssylvest/clickue` (default branch `main`, MIT license).
- `.github/workflows/build.yml` runs on **windows-latest** for every push and pull request:
  1. install requirements + PyInstaller
  2. smoke test: `py_compile`, import every module (asserts `HAVE_CV`, `HAVE_TRAY`,
     `HAVE_PIL`), render the logo
  3. read `VERSION` from `src/clickue.py`
  4. PyInstaller → `dist/Clickue.exe`
  5. portable zip: `Clickue.exe` + `installer/portable.txt` + README + LICENSE →
     `Clickue-Portable-<ver>.zip`
  6. Inno Setup (installed via choco if missing) → `Clickue-Setup-<ver>.exe`
  7. upload as build artifacts
  8. **on pushes to `main` (or `v*` tags): create or update the GitHub Release `v<VERSION>`**
     with both files (softprops/action-gh-release, `tag_name` + `target_commitish`). The
     workflow creates the tag itself.
- Consequences: pushing to `main` without bumping `VERSION` **replaces the files on the
  existing release**. Bump `VERSION` for a new release.
- **Claude Code (claude.ai) sessions:** pushing branches/commits to this repo works once the
  Claude GitHub App is installed on the repo. **Pushing tags and GitHub API writes (creating
  refs/releases) are blocked by the session's proxy.** That's why releases are created by the
  workflow, so never rely on pushing a tag. Reading via `gh api repos/...` (REST) works;
  GraphQL (`gh release list`, `gh pr view`) doesn't. Check a build with
  `gh run list -R jnssylvest/clickue` and the release with
  `gh api repos/jnssylvest/clickue/releases`.
- Commit messages from AI sessions end with the attribution lines the session provides.

## 11. Known limitations / ideas

- Windows forbids clicking or capturing a locked screen or a disconnected RDP session. This is
  documented, not fixable.
- The one-file PyInstaller exe is about 70 MB (OpenCV + Python) and unpacks on each start.
  It's unsigned, so SmartScreen warns. Code signing (e.g. Azure Trusted Signing) would remove
  the warning.
- Planned: a rewrite in Rust (smallest and fastest) or C#/.NET (easiest to maintain) for lower
  memory use and size. Port the behaviour in section 5 exactly, and reuse `tests/` scenarios
  as the acceptance spec.
- Possible features: more step types (scroll, drag), job groups, per-job notes, import from
  other macro tools.
