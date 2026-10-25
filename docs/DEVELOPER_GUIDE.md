# Clickue developer guide

Everything a developer (or an AI coding session) needs to understand, rebuild, change, test
and release Clickue. User-facing docs: [README](../README.md) · [FEATURES](../FEATURES.md) ·
[USER_GUIDE](USER_GUIDE.md) (quick start) · [GUIDE](GUIDE.md) (complete guide, every feature) ·
[SECURITY](../SECURITY.md).

> **Disclosure.** Clickue is vibe-coded and was developed with substantial AI assistance. Keep
> the disclosure (see [SECURITY.md](../SECURITY.md)) in every public surface where people decide
> to download or rely on Clickue: README, GUIDE, USER_GUIDE, the in-app Help/About (`DISCLOSURE`
> in `src/clickue.py`), the installer notice (`installer/before-install.txt`) and the release
> notes (`.github/workflows/build.yml`). `tests/check_release.py` checks this.

## 1. What Clickue is (one paragraph)

A Windows tray app (Python 3 + Tkinter) that performs **scheduled clicks** (interval +
optional random delay), runs **screen watchers** (click when a saved picture disappears or
appears) and records **macros**. Click spots are found by **picture matching** (OpenCV
multi-scale template matching), so they survive moved windows, resolution changes and DPI
scaling. Jobs run **steps** through a small **workflow engine** (click / wait / wait for picture
/ type / paste / keys / scroll / drag / If / Repeat / variables / step groups) with retries and
limits, through **one input queue**. Extras: active hours, run limits, global hotkeys including
an emergency stop, Discord/Telegram alerts (hardened), daily backups, undo, click history +
CSV, run history + optional local screen video, Dry run / Step through, a Tests window,
portable mode, installer. Formerly named *Scheduled AutoClicker*.

## 2. Repository layout

```
src/clickue.py            the whole app (single file, ~11,000 lines)
assets/                   clickue.ico, logo.png, logo-128.png (all generated from make_logo())
installer/clickue.iss     Inno Setup 6 script (per-user or all-users install)
installer/portable.txt    marker file shipped in the portable zip
scripts/*.bat             run from source / build the exe locally (Windows)
tests/                    headless logic tests, release checks, a GUI test (see section 8)
SECURITY.md               disclosure, what was reviewed, reporting, remaining risks
installer/before-install.txt  notice shown by the installer (and READ-ME-FIRST in the zip)
.github/workflows/build.yml   Windows build + automatic GitHub Release
docs/                     GUIDE.md (complete guide), USER_GUIDE.md (quick start), this file,
                          images/guide/ (example pictures for GUIDE.md)
scripts/make_guide_images.py  draws docs/images/guide/*.png (needs only Pillow)
README.md FEATURES.md CHANGELOG.md LICENSE (MIT) requirements.txt
```

## 3. Runtime & dependencies

- **Windows 10/11, 64-bit** for real use. Clicking, screen capture, hotkeys, tray, start-with-
  Windows and the DPI/window APIs are Win32 via `ctypes` (`user32`, `kernel32`, `shcore`,
  `dwmapi`) and `winreg`.
- Python **3.10+** (CI builds with 3.12). Packages (`requirements.txt`, minimums include
  security fixes): `pillow` (screenshots via `ImageGrab`, images), `pystray` (tray),
  `opencv-python-headless` + `numpy` (picture matching, and screen video via
  `cv2.VideoWriter`, so video adds no dependency). Each is optional at import time: flags
  `HAVE_PIL`, `HAVE_TRAY`, `HAVE_CV` disable features gracefully. `HAVE_DPAPI` (Windows
  `crypt32`) enables protected secrets.
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
| Clickue extras | active hours (`in_active_hours`, `next_active_start`, `describe_hours`), keyboard (`parse_combo`, `send_text` via SendInput unicode, `press_keys`), alerts (`check_discord_url`, `check_telegram`, `redact`, `_http_post`, `_alert_allowed`, `send_alert`), history CSV (`append_history`, `read_history`, `trim_history`, `job_stats`), backups (`make_backup`, `list_backups`, `prune_backups`) |
| 4.5 section | data helpers (`data_path`, `is_clickue_data_dir`), DPAPI (`protect_text`, `unprotect_text`), validation (`sanitize_step`, `sanitize_steps`, `sanitize_job`, `sanitize_groups`, `load_import_file`, `clean_png`, `strip_secret_text`, `risky_step_summary`), variables (`builtin_vars`, `expand_vars`, `compare_values`), clipboard (`clipboard_snapshot`, `clipboard_set_text`, `clipboard_restore`, `paste_text`), `InputGuard`/`HELD` (held keys/buttons, `release_all`), `move_mouse`, `scroll_wheel`, blocks (`parse_blocks`, `step_depths`), **target adapters** (`TargetAdapter`, `register_adapter`, `PictureAdapter`, `WindowAdapter`, `ScreenPositionAdapter`, `adapter_for`, `check_condition`), `describe_step`/`describe_cond`, conflicts (`job_targets`, `find_conflicts`), recorder (`vk_name`, `vk_char`, `rdp`, `compress_recording`, `MacroRecorder`, `finish_recording`), run history (`append_runlog`, `read_runlog`, `trim_runlog`), video (`VIDEO_PRESETS`, `video_folder`, `prune_files`, `RunVideo`), engine (`WorkflowRun`, `StopRun`, `StepFailed`), queue (`ExecutionWorker`, `LocalDesktopWorker`, `ActionQueue`) |
| Hotkeys | `parse_hotkey`, `HotkeyThread` = RegisterHotKey + GetMessage loop |
| Data model | `DEFAULT_SETTINGS`, `new_job()`, `new_watch()`, `is_watch()`, colour palettes `LIGHT`/`DARK` |
| `App` | everything stateful: load/save, scheduler (monitor) thread, input thread (`input_loop`, `run_item`, `queue_or_run`, `yield_to_others`), watcher engine, `perform`/`run_steps`/`run_workflow`/`dry_run_steps`/`execute`, run bookkeeping (`begin_run`, `end_run`, `failure_screenshot`, `prune_media`), `emergency_stop`, recording (`start_recording`, `stop_recording`), step-through (`start_debug`), UI build + theming, run bar, job list rows, tray, hotkeys, backups, undo, tests window plumbing, uninstall |
| Dialogs | `Dialog` (base: resizable, scrollable body, pinned footer, remembers geometry, click-outside closes unless unsaved), `StepsEditor` (the timeline, used by `JobEditor` and `GroupEditDialog`), `TextPrompt`, `JobEditor` (clicks and watchers), `TestDialog`, `WatchTestDialog`, `StepDialog` (every step type), `DryRunDialog`, `StepDebugger` + `DebugWindow`, `RecordDialog`, `RecordingIndicator`, `GroupsDialog`, `GroupEditDialog`, `RunHistoryDialog`, `VideoPlayer`, `BackupsDialog`, `StatsDialog`, `HelpDialog`, `AboutDialog`, `SettingsDialog` (= tabbed Preferences), `TestsWindow` (floating Toplevel) |
| `main()` | single-instance mutexes (new + old name), `App(root)`, `mainloop()` |

### Threads
- **UI thread:** Tk mainloop. `ui_tick()` runs every 1 s (log queue, rows, cards, buttons,
  `own_visible`); `poll_cmds()` every 200 ms drains `cmdq` (tray/hotkey commands: `show`,
  `pause`, `toggle_window`, `exit`).
- **Scheduler (monitor) thread:** `scheduler_loop()` wakes every 1 s, collects due work under
  `self.lock` (an RLock). It runs `watch_check` itself (only looks at the screen, never sends
  input) and hands every action that needs the mouse/keyboard to the **input queue**
  (`queue_or_run`): `execute(job, "scheduled"|"test")`, `watch_click`, `watch_test`. It also
  logs when a queued action has waited > 10 s (`note_waiting`).
- **Input thread:** `input_loop()` takes one `ActionQueue` item at a time (priority, then first
  come) and runs it (`run_item`). This is the **only** thread that clicks or types in the real
  app; "Test click now" and Step through go through it too (priority high). `run_cancel` (an
  Event) is checked by the engine between steps and during waits; `emergency_stop()` sets it,
  clears the queue, releases held input and pauses all. `yield_to_others` lets a waiting job
  run one other queued item inline (opt-in per job, depth 1, never while input is held).
  Without the input thread (the headless tests), `queue_or_run` runs the action directly.
- **Recorder threads** (while recording): a low-level hook thread (`WH_MOUSE_LL` +
  `WH_KEYBOARD_LL` with its own message loop; callbacks only append to a list) and a picture
  thread that crops a small screenshot around each mouse-down. **Video thread** (while a run is
  recorded): `RunVideo._loop` grabs frames at the preset rate and checks free space.
- **Hotkey thread**, **tray** (pystray `run_detached`), and short-lived threads for alerts.
  **Never touch Tk widgets from non-UI threads.** Use `self.log()` (a queue) or `cmdq`
  (`poll_cmds` runs callables put on it, on the UI thread).

### Data files (in `DATA_DIR`)
`settings.json`, `jobs.json` (`{"app","version","jobs":[...]}`), `test_history.json`,
`click_history.csv` (capped at 50,000 rows), `clickue.log` (+ `.1`, `.2`, RotatingFileHandler),
`backups/YYYY-MM-DD_HHMMSS_<tag>.json` (tags: `auto`, `manual`, `before-restore`,
`before-import`, `before-fresh-start`, `before-upgrade-<version>`), `run_history.csv` (capped at
50,000 rows; never typed text), `recordings/clickue_run_<stamp>_<job>.mp4|avi` (unless
`video_dir` is set), `diagnostics/clickue_fail_<stamp>_<job>.png`.
`jobs.json` is `{"app","version","schema":2,"jobs":[...],"groups":[...]}`.
All JSON is written atomically (`.tmp` + `os.replace`). A corrupt file is copied to
`.corrupt` and defaults are used. Backups never contain `SECRET_KEYS` (alert credentials).

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
- 4.5: `main_click` (False = steps only), `priority` ("high"|"normal"|"low"), `let_others_run`,
  `record_video`, `fail_shot`, `saved_vars` ({name: value} remembered between runs),
  `run_limit_s` (default 6 h, max 24 h)
- Steps (`sanitize_step` is the authoritative schema; unknown fields are dropped on import).
  Every step except else/end may have `label`, `retries` (0-10), `retry_wait` (s),
  `on_fail` ("stop"|"continue"), `careful`; recorded steps also keep `rec_t` (s).
  `{type:"click", x, y, button, clicks, use_image, snap_png, snap_spot, pick_dpi, pick_screen,
  image_fallback, target_mode ("screen"|"window"), window_title, window_class, rel_x, rel_y,
  client_w, client_h, bring_to_front}` ·
  `{type:"wait", min, max}` (ints or floats) ·
  `{type:"waitpic", png, until, click_it, button, clicks, timeout, on_timeout, area}` ·
  `{type:"type"|"paste", text, use_vars, secret, text_enc ("dpapi:…" when secret)}` + paste:
  `restore_clipboard, paste_keys ("Ctrl+V"|"Shift+Insert"|"Ctrl+Shift+V"), settle` ·
  `{type:"key", keys, times}` · `{type:"move", path:[[t,x,y],…]}` ·
  `{type:"drag", button, path}` · `{type:"mouse", button, action ("down"|"up"), x?, y?}` ·
  `{type:"scroll", x?, y?, amount (notches, − = down/left), horizontal}` ·
  `{type:"keyhold", keys, action}` · `{type:"if", cond}` · `{type:"else"}` · `{type:"end"}` ·
  `{type:"repeat", mode ("times"|"until"), times, max_times, max_seconds, cond?}` ·
  `{type:"set", var, op ("set"|"add"|"sub"), value, persist}` · `{type:"group", group_id}`.
  `cond`: `{kind:"picture", png, state ("shown"|"gone"), area, wait}` |
  `{kind:"window", title, state ("open"|"closed"), wait}` | `{kind:"var", var, op, value}`.
- Step groups (top level of jobs.json): `{id, name, steps}` (no `group` steps inside)
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
6. **Schema 2 (4.5).** Old files have no `schema`; `load()` sets `schema_upgrade`, and
   `App.__init__` saves a `before-upgrade-<version>` backup before the first save in the new
   format. Old jobs keep their behaviour: missing keys default to it (`main_click` True,
   `use_vars` False so braces are typed literally, etc.). Never change what an existing field
   means.
7. **Imports and restores are untrusted:** always go through `load_import_file` /
   `sanitize_job`; imported jobs are disabled. Never execute anything from a jobs file.
8. **Startup prompts (in `App.__init__`, before `load()` builds the UI):**
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

**Workflow engine (`WorkflowRun`)**
- `parse_blocks` turns the flat step list into if/else/repeat nodes (max nesting 8); invalid
  blocks are refused before anything runs (and the editor won't save them).
- Modes: `run`, `debug` (a `StepDebugger` is asked before each step; `before_main` before the
  job's own click) and `dry` (no input: targets located with `check_cover=False`, conditions
  checked once, loops shown once, waits skipped, text only counted).
- `check_stop()` between steps and in every wait: Clickue closing, `run_cancel`, the run time
  limit, and Pause all (releases held input, waits, doesn't count paused time). Hard cap
  `MAX_EXECUTED_STEPS` (200,000).
- Each step: retries (`retries`/`retry_wait`), then `on_fail`; `waitpic` keeps its own
  `on_timeout`. Unexpected exceptions in a step become a failed step, never a crashed thread.
  Messages keep the old format (`step N: …`, `step N (click): …`).
- `finally`: `HELD.release_all()`, video un-hide, persisted variables saved to the job.
- Text: `text_of()` decrypts secrets / fills variables / enforces limits; Type/Paste set
  `app.video_hide_until` so the video blacks out; messages never contain the text.
- Groups: by id, depth ≤ 4, a group can't run itself.

**Target adapters (`ADAPTER_API_VERSION = 1`)**
- The engine never finds targets itself: `adapter_for(target)` returns the first registered
  adapter whose `handles(target)` is true and that is `available()`. Built in: `picture`,
  `window`, `screen` (the fallback). Conditions use `check_condition(cond)` → the adapter with
  `id == cond["kind"]` → `check(cond)`.
- To add one (e.g. OCR, UI Automation): subclass `TargetAdapter` **in `src/clickue.py`**, set
  `api`, `id`, `label`, `needs` (packages), implement `available`, `handles`, `describe`
  (how it finds the target and what happens if it isn't found), `locate` (must not click;
  return `(ok, x, y, msg, how)`), and `check` (for conditions; must not send input), then
  `register_adapter(MyAdapter())` before the screen-position adapter. Add its fields to
  `sanitize_step`/`clean_cond`, its UI to `StepDialog`, tests, docs, and its packages to
  `requirements.txt` and both packages.
- Adapters are code that ships with Clickue. There's deliberately **no** plugin loader: no code
  is loaded from files, the data folder or the internet. A future opt-in local plugin system
  would need explicit user approval per plugin (hash-pinned), a visible list, and no automatic
  download.
- Rule: never fall back to an unverified coordinate unless the user chose it
  (`image_fallback="position"`), and say so in `how`.

**Input queue and workers**
- `ActionQueue` (one per `ExecutionWorker`) de-duplicates (one action per job and kind),
  orders by priority then arrival, and exposes `running` / `waiting()` for the run bar.
- `ExecutionWorker` (api 1): `LocalDesktopWorker` (`isolated = False`) is the only one. Only
  workers with `isolated = True` (separate desktops/VMs, each with its own queue, status and
  screen) may ever run in parallel. Never simulate several cursors on one desktop.
- `find_conflicts` warns (on save) about running jobs that share a window title or a 40-px
  fixed-spot cell.

**Recorder (`MacroRecorder`, `compress_recording`)**
- Hook callbacks drop injected events (`LLMHF_INJECTED`, `LLKHF_INJECTED`), throttle moves
  (15 ms / 4 px), stop at `MAX_EVENTS` (300,000). Pause shifts the clock so pauses vanish.
- `compress_recording` is pure (tested headlessly): drops events inside `exclude` rectangles
  (the red bar), orphan key-ups (start hotkey) and unreleased key-downs (stop hotkey); clicks
  (≤ 4 px, ≤ 0.6 s), double clicks (≤ 0.5 s apart), holds, drags (RDP-simplified path), moves
  (≥ 24 px, simplified), wheel aggregation, text (with Backspace editing; `vk_char` uses
  `ToUnicodeEx` with the foreground layout), key combos, modifier taps, modifier-held clicks
  (`keyhold`), waits ≥ 0.25 s. `finish_recording` trims leading waits and trailing moves.

**Paste / clipboard**
- Snapshot every HGLOBAL clipboard format (not GDI handles: bitmaps/metafiles/palettes are
  usually also offered as DIB), set CF_UNICODETEXT plus the documented
  `ExcludeClipboardContentFromMonitorProcessing` / `CanIncludeInClipboardHistory=0` /
  `CanUploadToCloudClipboard=0` formats, press the keys, wait `settle`, restore. Report
  partial restores honestly; never leave pasted text on the clipboard when restoring.

**Video (`RunVideo`)**
- `cv2.VideoWriter` with `mp4v` (.mp4), falling back to `MJPG` (.avi); frame size fixed at
  start (even numbers); redaction rectangles and "hidden" frames applied before writing; free
  space checked at start (1 GB) and every 5 s (300 MB). Any failure sets `status="stopped"` and
  ends only the video. `position()` = frames / fps, logged with each step.

**Alerts (security)**
- Only `check_discord_url`-valid Discord webhooks and `api.telegram.org`; `_http_post` uses
  HTTPS with the default SSL context, no redirect handler, 10 s timeout, 64 KB response cap;
  `_alert_allowed` rate limit; errors pass through `redact`. `App.log` redacts the configured
  secrets from every line.

**Click chains (`waitpic` steps, `App.wait_for_picture`)**
- Polls `picture_on_screen()` every `STEP_POLL_S` (1 s), up to `timeout` (capped by
  `STEP_MAX_WAIT_S` = 1 h), remembering the last seen scale. When the condition is met it
  optionally clicks the found centre. A message starting with `timeout` plus
  `on_timeout="continue"` continues the chain; anything else stops it (the click itself still
  counts as OK and the reason is logged).
- Runs on the input thread, so **other actions wait while a chain waits** (watchers keep
  checking on the monitor thread). This is intentional, because two jobs can't use the mouse
  at once. `tick()` is called during the wait (stop checks, optional yielding).
- `App.draw_capture(parent, prompt, on_done)` is the reusable "drag a box" screen used by the
  step editor (the watcher editor keeps its own `_draw_overlay`).

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
- **Installer locally:** install Inno Setup 6, set `CLICKUE_VERSION=4.5`, run
  `ISCC installer\clickue.iss` → `dist\Clickue-Setup-4.5.exe`. The installer shows
  `installer/before-install.txt` first; its uninstaller removes the HKCU Run value only when it
  points at `{app}`, and deletes `%APPDATA%\Clickue` only if the user says Yes (skipped when
  Clickue's own Uninstall passes `/KEEPDATA`).
- **Icon/logo:** generated by `make_logo()`. After changing it, regenerate the assets with
  `python src\clickue.py --make-icon assets\clickue.ico`, and save PNGs with
  `make_logo(256)` / `make_logo(128)`.

## 8. Tests

Run from the repository root.

| Command | What | Expected |
|---|---|---|
| `python tests/test_watchers.py` | watcher scenarios (seen/gone/flicker/scaling/look-alikes/retries) | `RESULT 21/21` |
| `python tests/test_features.py` | hours, limits, steps, click chains, appears/area, history, backups, undo, alerts (faked network), migration, install id, guide link + pictures | `RESULT 55/55` |
| `python tests/test_click_spot.py` | click-spot matching at 3 picture sizes × 8 screens (100–175 % scaling, moved, look-alikes) | `0 of 24` failures |
| `python tests/test_workflows.py` | 4.5: alert hardening (hosts, redirects, rate limit, redaction), secrets out of backups/exports, DPAPI flow (simulated), import validation, data-folder safety, variables, blocks, if/repeat/retries/groups/limits/cancel/pause, held-input release, dry run, the input queue (order, watchers keep checking, yielding, emergency stop), conflicts, recorder compression, paste/clipboard flow, video (lifecycle, no codec, disk full, capture failure, redaction), run history + video positions, failure screenshots, schema migration, adapters | `RESULT N/N` |
| `python tests/check_release.py` | docs links/anchors/pictures, version = changelog, disclosure placement, planned features marked planned, no secrets or private details in public files, workflow least privilege + pinned actions, uninstall boundaries | `RESULT N/N` |
| `python tests/gui_test.py` | drives every window and control of the real UI | `N/N checks passed, 0 errors` |
| `python tests/gui_screenshots.py` | saves screenshots to `tests/screenshots/` | `done` |

- The `test_*.py` files are **headless**: `tests/sim_helpers.py` stubs out `tkinter`, loads
  `src/clickue.py`, sets `IS_WIN = False` (so nothing real is clicked, even on Windows CI), and
  draws fake app screens with PIL (needs any TrueType font). They replace screen capture,
  clicking, typing and the clipboard with fakes. Real-desktop behaviour (hooks, SendInput,
  clipboard, DPAPI, installer) must be checked by hand on Windows: see the manual checks in
  section 9.
- The GUI tests need a Python **with tkinter** and a display. On Linux, use `Xvfb :99` and
  `DISPLAY=:99`; the screenshot script grabs from `:99`. On a headless Linux box where the
  system Python lacks tkinter, `uv python install 3.13` provides one, using the system
  site-packages via `PYTHONPATH`. On Linux the screen counts as "locked", so tests that need a
  real unlocked Windows screen report that instead.
- **Run all of them before every release.** After any UI change, also look at the screenshots.

## 9. Making a new version (checklist)

1. Make the change in `src/clickue.py`, following the compatibility rules (section 4).
2. Bump `VERSION = "x.y"` near the top of `src/clickue.py`.
3. Add an entry at the top of `CHANGELOG.md`. Update `FEATURES.md`, `docs/GUIDE.md` (the
   complete guide: every feature, setting and default), `docs/USER_GUIDE.md` and `README.md`
   if the behaviour or UI changed. If a picture in the guide no longer matches, change its
   function in `scripts/make_guide_images.py` and run `python scripts/make_guide_images.py`.
4. Run the tests (section 8).
5. Commit and push to `main`. That's all: the workflow builds and publishes the release.
6. **Manual checks on a real Windows desktop** (the automated tests fake input):
   - record a short macro (click, double click, drag, scroll, typing with Backspace, Ctrl+S,
     Shift+click), stop, check the steps, Dry run, Step through, run it;
   - Paste text with several lines and non-English characters into Notepad; check the
     previous clipboard (text and a copied picture) comes back, and Win+V doesn't list it;
   - a Secret paste step; export and check the text isn't in the file;
   - Emergency stop during a long Wait and during a drag (no stuck mouse button or key);
   - two jobs due at once: the run bar shows one running and one waiting;
   - a job with screen video: red bar, Pause/Stop video, play it from the run history;
   - phone alerts to a real Discord webhook / Telegram bot; a wrong URL is refused;
   - installer: fresh install, upgrade over the previous version (before-upgrade backup),
     uninstall keeping data, uninstall deleting data; portable zip; in-app Uninstall for both.

## 10. GitHub: repository, CI and releases

- Repository: `https://github.com/jnssylvest/clickue` (default branch `main`, MIT license).
- `.github/workflows/build.yml` runs on **windows-latest** for every push and pull request:
  0. permissions: the workflow is `contents: read`; only the separate `release` job (pushes to
     `main` / `v*` tags, never PRs) gets `contents: write` + `discussions: write`. Actions are
     pinned to commit SHAs (update them deliberately); checkout uses
     `persist-credentials: false`.
  1. install requirements + PyInstaller
  2. smoke test: `py_compile`, import every module (asserts `HAVE_CV`, `HAVE_TRAY`,
     `HAVE_PIL`, `HAVE_DPAPI`), render the logo
  2b. headless tests + `tests/check_release.py`; `pip-audit -r requirements.txt` and
     `bandit -r src` (high severity) fail the build
  3. read `VERSION` from `src/clickue.py`
  4. PyInstaller → `dist/Clickue.exe`
  5. portable zip: `Clickue.exe` + `installer/portable.txt` + README + LICENSE +
     `READ-ME-FIRST.txt` (= `installer/before-install.txt`) → `Clickue-Portable-<ver>.zip`
  6. Inno Setup (installed via choco if missing) → `Clickue-Setup-<ver>.exe`
  7. `SHA256SUMS.txt`, then upload as build artifacts (14 days)
  8. **on pushes to `main` (or `v*` tags): create or update the GitHub Release `v<VERSION>`**
     with both files (softprops/action-gh-release, `tag_name` + `target_commitish`). The
     workflow creates the tag itself. A **new** release also posts an announcement in
     **Discussions → Announcements** (`discussion_category_name`; needs the
     `discussions: write` permission and Discussions turned on in the repository settings).
- Community: issue forms in `.github/ISSUE_TEMPLATE/` (Feature idea, Bug report, links to
  Discussions), `CONTRIBUTING.md`. Discussions is on (categories: Announcements, Ideas, Q&A,
  …). Claude sessions can't post to Discussions directly (GraphQL is blocked), so
  announcements go through the workflow.
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

## 11. Security notes

See [SECURITY.md](../SECURITY.md) for the review and remaining risks. Rules for changes:
- No `eval`/`exec`/`pickle`/`shell=True`; subprocesses only with fixed, validated arguments.
- No new network destinations, no telemetry. Alerts stay limited to the two services.
- Secrets (`SECRET_KEYS`, secret step text) never go into logs, history, run history, backups,
  exports, error messages or screenshots/videos.
- Anything read from a file the user didn't create in this app is untrusted: validate it.
- Recursive deletes only after `is_clickue_data_dir`; clean-ups only via `prune_files` with a
  strict name pattern.
- Every new loop/wait needs a limit and must call `check_stop()`/`tick()`; anything that holds
  input must use `HELD`.

## 12. Known limitations / ideas

- Windows forbids clicking or capturing a locked screen or a disconnected RDP session. This is
  documented, not fixable.
- The one-file PyInstaller exe is about 70 MB (OpenCV + Python) and unpacks on each start.
  It's unsigned, so SmartScreen warns. Code signing (e.g. Azure Trusted Signing) would remove
  the warning.
- Planned: a rewrite in Rust (smallest and fastest) or C#/.NET (easiest to maintain) for lower
  memory use and size. Port the behaviour in section 5 exactly, and reuse `tests/` scenarios
  as the acceptance spec.
- Planned: OCR text targets, Windows UI Automation targets, browser element targets (adapters),
  isolated execution workers (separate desktops/VMs), an opt-in local plugin mechanism.
- Possible features: job folders, per-job notes, import from other macro tools.
