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
  watch_delay_max_s, watch_cooldown_on, watch_cooldown_s, watch_once, watch_match
  ("exact"|"partial", 4.5.3), watch_partial_pct (40-95, default 75)`; runtime `next_check,
  last_check, last_seen, miss_count, watch_state ("seen"|"missing"|"unknown"), armed,
  pending_click_at, pending_since, watch_scale, watch_note, found_xy, once_logged,
  pointer_logged`
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
   - **Never let an old file replace current jobs (4.5.2).** `load(ask=)` records
     `jobs_file_state` (`ok` / `missing` / `unreadable`), `saved_version` and
     `jobs_file_info`. The v1 `OLD_CONFIG` (`autoclicker_config.json` next to the program) is
     only offered when both files are missing **and** `data_folder_used()` is false (no
     backups, log, histories, `.corrupt` files), and only after asking; before 4.5.2 it was
     imported silently and brought back long-deleted jobs. A missing/unreadable jobs file
     leads to `offer_backup_recovery()` (newest backup with jobs; restored jobs disabled).
     `App.__init__` saves `before-upgrade-<VERSION>` whenever `saved_version != VERSION`
     (not only on a schema change), and logs what was loaded. Don't set `migrated` to mean
     anything but "save now"; the old-config log line depends on `old_config_imported`.
   - `save()` writes `jobs.json` first, retries each file once after 0.3 s, and sets
     `save_error`, which `ui_tick` shows once.

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

**Picture matching** (tuning constants near `MATCH_*` / `WATCH_*` / `EXACT_*`)
- `picture_candidates` tries scales `MATCH_SCALES` (a DPI ratio hint and the last seen scale
  go first), keeps the top candidates per scale, scores each on the **whole picture** and a
  **60×34 close-up around the spot**, and returns one candidate per place. `find_picture`
  (tolerant) needs `whole ≥ 0.65` and `close-up ≥ 0.62` (`is_match`).
- **Exact matching (4.5.1, `exact_match`, default on for jobs and click steps).** The tolerant
  thresholds let a different button in the same style pass (a *Reload* button scored 0.97 /
  0.69 against a saved *Refresh*), and when the picked spot was off-screen, a look-alike was
  clicked. `spot_report()` (used by `locate_spot`) therefore runs `verify_exact()` on every
  tolerant candidate: at the same size both scores must be ≥ `EXACT_SAME_SIZE_MIN` (0.95); at
  another scale the screen region is resized back to the template size, both are blurred
  (3×3), and whole ≥ 0.88 and close-up ≥ 0.85 are required (measured: genuine 0.87–0.93,
  changed text ≤ 0.80); then the colour check (`WATCH_COLOR_MAX`/`WATCH_LIGHT_MAX`). Several
  exact copies: only the one within half a picture of the expected position (window-relative
  when targeting a window) is used, otherwise nothing is clicked ("on screen N times"). Never
  relax this without a test in `tests/test_click_spot.py` (it runs both modes).
- `spot_report()` also returns `similar` boxes (screen coordinates, label, chosen, exact) for
  the "point out every similar picture" overlay; `picture_on_screen(..., report=list)` does the
  same for watched pictures.
- `_match` **must** reject windows whose contrast is far below or above the template's
  (`sd < 0.5·σ` or `> 2·σ`). Without this, flat areas give false "perfect" matches. This was a
  real bug.
- Look-alikes: among near-equal candidates, take the one nearest the saved position.
- Watchers are stricter (`picture_on_screen`): at the drawn size both scores must be ≥ 0.93,
  and the Lab colour difference must be ≤ 15 (brightness ≤ 25). Grayscale-only matching once
  counted a red "OFFLINE" badge as the green "CONNECTED" one. At other scales (4.5.1) the
  candidate must also pass `verify_exact`.
- **Watchers go through `watched_picture(job, report, move_ok)` (4.5.3)**, never
  `picture_on_screen` directly: it applies the search area, the match mode
  (`watch_partial(job)`) and the pointer rule, and returns `((found, x, y, score, scale), note,
  pointer)`. Real cause of a "Picture NOT on screen (best 77%)" report: before 4.5.3 an area
  drawn as big as (or a few px smaller than) the watched picture left `matchTemplate` no room
  at scale 1, so only shrunken scales were tried. `search_box()` now pads the area by
  `max(AREA_PAD_MIN, 25 % of the picture)` and makes it at least picture + padding.
- **Partial matching** (`partial_fraction`, opt-in per watcher): the region at the candidate
  (scaled back to the picture's size, ±4 px) is compared in ~24 px tiles (2-10 per side). A
  detailed tile matches at TM_CCOEFF_NORMED ≥ `PARTIAL_TILE_MIN` (0.85) within ±4 px, a plain
  tile (σ < 3) when its brightness differs ≤ 12; both must also pass a per-tile Lab check
  (chroma ≤ 18, lightness ≤ 24). Tiles off the screen don't match. Score = matched / all
  tiles; found when ≥ `watch_partial_pct`. Candidates use a lower first-stage floor (0.3).
  Tested in `tests/test_watchers.py` 22-26 (changing number seen, badge gone/red missing,
  no false positives on unrelated screens).
- **Mouse pointer (4.5.3).** Hover changes a button's look. `grab_screen(move_cursor=True)`
  (pointer moved to the virtual-screen corner for 0.3 s) is used for Draw box (watcher) and
  for re-checks. `watched_picture`: if not found and `pointer_near_watch` (pointer within 30 px
  of the best candidate, the last-seen box or the search area), re-grab with the pointer
  moved when `move_ok` (tests, Check now, Dry run; scheduled checks only when
  `may_move_pointer()`: idle ≥ `POINTER_IDLE_S` (20 s), input thread idle, `HELD` empty);
  otherwise the scheduled check returns `pointer=True` and `watch_check` doesn't count a miss
  ("mouse pointer on the picture", logged once via `pointer_logged`). `CURSOR_LOCK` makes
  `grab_screen(move_cursor=True)` and `do_click` mutually exclusive, so a scheduler-thread
  re-check can never move the pointer in the middle of a click. `current_pointer()` returns
  None off Windows (tests patch it).
- **4.5.4 matching.** `picture_candidates(..., limit, floor)`: a plain close-up (σ < 4)
  scores like the whole picture (noise made it 0 before); same in `verify_exact`. Pictures
  from 6 px work. **Exact (watchers, `picture_on_screen`)**: after the old checks,
  `exact_tiles()` compares the picture tile by tile (`_tile_grid`): every tile's mean RGB
  difference ≤ `EXACT_TILE_DIFF` (14, ×1.6 when scaled) and every detailed tile's correlation
  ≥ `EXACT_TILE_CORR` (0.90; `EXACT_TILE_CORR_SCALED` 0.70 at other sizes: measured genuine
  0.79+, changed text < 0.1), with ±1 px alignment. Before, a card whose price differed
  passed (the changed part was outside the close-up). Click-spot matching (`spot_report`) is
  unchanged. **Partial**: `partial_candidates()` searches the 16 most detailed tiles on their
  own (TM_CCOEFF_NORMED ≥ 0.80, dilated ±2 px) and lets each hit vote for the picture's
  origin; peaks become candidates (at the hint scale and 100 %), then `partial_fraction`
  decides. Before, only the top whole-picture candidates within 0.15 of the best were
  checked, so other copies with a different changing part were never considered.
  `report` lists up to `MAX_MATCHES` places; Check now always outlines the ones that count.
  Typical times (1920×1080, whole screen): exact 0.1–1.1 s, partial 1.4 s (2560×1440: 2.6 s).
- **`BoxDrawer` (4.5.4)** is the one Draw-box overlay (watcher editor `_draw_overlay` and
  `App.draw_capture`): view state `z`, `ox`, `oy` (screenshot px), `to_px` maps canvas →
  pixel corners, so the box is always in real pixels; dimmed base re-rendered on zoom/pan
  (NEAREST, grid from 8×), the undimmed selection as a second image, magnifier
  (`show_loupe`, 15 px at 11 px each). Minimum box `PICTURE_MIN_PX` (8).
- **Job list views (4.5.4):** all columns exist in the Treeview (`JOB_COLS`); `JOB_VIEWS`
  picks the displayed ones per filter; `build_rows` returns `RowVals` (the classic 9-tuple,
  still used by `tray_status`, plus `.cells` for every column). `apply_view` sets headings,
  fits widths to text (`column_fit_width`, capped per column), gives the rest to *last*,
  hides `VIEW_DROP` columns when narrow; it grows-only during the 1 s refresh and refits on
  full refreshes, view changes and resizes (throttled to 3 s otherwise). User widths in
  `col_widths` win. Divider: `nudge_split`, `SPLIT_MIN/MAX`, visible `Sash` style.
- **Buttons:** disabled `TButton`/`Accent.TButton` map `relief` to `solid` with the `outline`
  palette colour and no fill (clam draws no border with relief flat).
- **Tests window (4.5.4):** sections `tests_section` (all/click/watch) with `test_kind(name)`;
  per-section scope `tests_scopes`; no paned split any more (history right under the buttons).
- **4.6 updates.** `fetch_latest_release()` (GitHub API, `UPDATE_API`), `https_get()` (HTTPS,
  default SSL context, manual redirects only to `UPDATE_HOSTS`, size/time limits; tests set
  `_HTTPS_GET`), `download_update()` (package by `install_kind()`: installer when
  `install.ini` exists, portable when frozen without it, source otherwise; checked with
  `expected_sha256` against SHA256SUMS.txt into `data_path("updates")`),
  `extract_portable_exe()`. App: `auto_update_check` (hourly timer, checks at most every
  `UPDATE_EVERY_S`, nothing at all while `update_check` is off), `check_for_updates`,
  `show_update_bar` / `update_later` / `update_skip`, `UpgradeDialog`, `finish_upgrade`
  (save, backup `before-upgrade-<v>`, `upgrade_pending`, then the installer with
  `/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /RELAUNCH /ALLUSERS|/CURRENTUSER`,
  or rename the running exe to `Clickue.old.exe` and swap in the new one; then quit),
  `after_upgrade` (logs the result, clears the flag, removes `Clickue.old.exe`). The
  install-id "keep your jobs?" question is skipped while `upgrade_pending` is set. The
  installer's `[Run]` entry with `Check: WantRelaunch` restarts Clickue after a silent
  `/RELAUNCH` install. Security rule (section 11) updated: GitHub is the only other network
  destination, and only while the check is on.
- **4.6 watchers.** `watch_window(job)` → "ok"/"missing"/"minimized"/"none" for watchers whose
  button is `target_mode == "window"`; `watch_scope(job)` (Check now, Dry run, watcher tests)
  and `watch_check` restrict the search to the window (∩ area), report missing/minimized via
  `watch_issue(..., cancel_click=True)`, and `window_covering()` reports another window on top
  where the picture was. `watch_click` re-checks the window too. `picture_on_screen(...,
  exclude=)` drops candidates overlapping Clickue's own windows (`App.own_rects`, from
  `ui_tick`, title bar included). Exact scaled matches report the verified score. Timing:
  `first_miss_at`, `click_planned_at`, `planned_run` (runtime), `clock()`; logs and
  `last_result` include them. Tray tooltip lines are only shortened when they don't fit.
- **4.6.1 fixes.** `tls_context()` (default SSL context + `certifi.where()`; used by
  `https_get` and `_http_post`; never disables checks) and `friendly_net_error()`; certifi is
  in `requirements.txt` and bundled with `--collect-data certifi`. `tray_wrap()` wraps every
  tooltip entry to `TRAY_TIP_WIDTH` (36) characters, because Windows cuts wide lines.
  `own_on_top(x, y)` (WindowFromPoint is ours) decides z-order: the `exclude` filter in
  `picture_on_screen` only drops a candidate where a Clickue window is really in front, and
  `App.own_covers(job)` (at `found_xy` / the search area's middle, else Clickue being the
  foreground window) replaces the bare `own_visible` test for *Clickue window in front of the
  picture* in `watch_check` and the watcher test note. Off Windows it falls back to the old
  rectangle/visibility rules, which the headless tests use. Screen settle: `watch_check` no
  longer returns early while `settle_until` is in the future. It looks, and only a *change*
  (`found == appears`) is held back as an issue; no change clears `settle_until`.
- **4.5.6 watcher engine.** `watch_check` runs during a pending click too (scheduler dues a
  `watchcheck` while `pending_click_at` is in the future; `next_check` during the delay is
  `min(interval, max(5, delay/4))`) and cancels it when the condition no longer holds;
  `watch_click` re-checks with `watched_picture` right before clicking (gone/appears without
  "click the picture itself"). Screen changes: `screen_sig` = virtual screen + DPI per job;
  a change sets `settle_until` = now + `SCREEN_SETTLE_S` (15 s) and resets `miss_count`.
  `watch_issue()` is the single path for "can't tell" (sets `watch_state="unknown"`, counts
  `issue_count`/`issue_since`, logs every check, the first with `issue_hint()`);
  `watch_ok_again()` logs recovery. `watch_row` shows unknown as **⚠ Can't watch** /
  state `warn` (was `paused`, which looked fine). `watch_area_note()` explains scaled areas.
- **Issue reporting.** `job_health(app, job, iid)` = the job list's hover text (`HoverTip`,
  refreshed every second while shown); `issue_hint(msg)` maps messages to advice
  (`ISSUE_HINTS`). `log_retry()` logs every try of a waiting click (idle waits every 6th).
  `App.log(msg, level)`: "detail" / "info" / "important", filtered by `log_wanted()` and
  `settings["log_level"]` (quiet keeps lines with problem/click words).
- **Tray:** `tray_badge()` → None / "due" / "clicking" / "issue"; `make_icon(badge)` draws a
  dot; `update_tray_status` swaps `tray.icon` only when it changes. Watchers' tooltip detail
  includes "next check in Ns".
- **Logs:** `LogGrid(..., natural, refresh, delete)` + `toolbar()`; `done_filling(refilled)`
  applies Clear view (`app.log_hidden[name]`, session only, by row values), order
  (`settings["log_order"][name]`, reversing relative to the fill's natural order) and the
  column fit. Activity: `refresh_activity` (re-read `read_log_tail`), `toggle_activity_order`
  (inserts at a right-gravity mark for newest-first), `clear_activity` (temporary:
  `act_hidden_before`), `delete_activity_log` (truncates the handler's stream, removes
  rotations). `rewrite_history` / `rewrite_runlog` delete rows; `DeleteLogsDialog`.
- **Main window:** `update_cards` per view (`card_titles`, `cards_caption`,
  `stats_*_watch` counters via `bump_stats(..., watch=True)`); `Summary.TButton`;
  `Accent3.TButton` (Record, group 0); `refresh_all` (F5); step rows: `build_rows` wraps
  `_build_rows`, adds ▸/▾ and `step_row()` rows `step:<job id>:<n>` for `self.expanded`;
  `_job_for_iid` takes `split(":")[1]`; `selected_is_test` checks the `test:`/`wtest:` prefix.
- **Mouse:** `human_path()` (pure: quadratic Bézier with a random bend, smoothstep easing,
  jitter, optional overshoot, Fitts-like duration × `HUMAN_SPEEDS`), `glide()`,
  `do_click(..., human=speed)` (also glides back when restoring the cursor),
  `mouse_style(settings, job, step)` (step > job > Preferences). Inside `CURSOR_LOCK`.
- **Colours:** `theme_palette(settings, dark)` merges `custom_colors[light|dark]` (validated
  `#rrggbb`, known keys only) over `LIGHT`/`DARK`; `COLOR_NAMES`; `ColorsDialog`,
  `ColorPicker` (numpy-drawn HSV wheel + brightness + hex + RGB).
- **Logs (4.5.5).** `LogGrid(app, tree, frame, owner, job_of, extra, fit_col, filterbox)`
  gives a Treeview log its right-click menu (copy rows / cell / all, select all, CSV,
  📍 show on screen when `LOC_RE` finds "(x, y)", filter to job/test, extras), Ctrl+C/A/F,
  and an auto-hiding horizontal scrollbar (`fit()` widens `fit_col` to its text so the table
  scrolls instead of cutting). Used by the Tests history, Run history (both tables), Stats
  and Dry run. `FilterBox` = the 🔍 field (phrase match, case-insensitive; 180 ms debounce);
  each log filters its own data (not by detaching tree items). `App.show_places(text,
  parent, job_name)` hides the app and calls `flash_marker`: crosshair on the spot, the
  watched picture's outline (size × "at N% size") where the text says a picture was found.
  Activity: `insert_activity` tags places with `loc` (link), `activity_menu`,
  `load_activity_history` reads `read_log_tail(800)` lines older than `session_start` and
  newer than `settings["activity_cleared_at"]` (set by Clear view, or at start when
  `activity_clear_on_start`). Tests history: `meaning` column from `TEST_LEVELS`, legend
  (`flow_legend` stacks it when narrow); columns are no longer hidden when narrow.
  Job list: `on_tree_click` unselects on the empty area, `on_double` ignores mouse
  double-clicks there (it used to open the editor, which click-outside closed again).
  `Accent2.TButton` (teal, `accent2` palette keys) for New watcher. `flash_status()` shows a
  short confirmation in the status bar.
- **Draw box (watcher)** captures with the pointer moved aside and, 0.6 s later,
  `picture_changes()` captures the box again: if > 1 % of its pixels changed by > 24 grey
  levels, the user is warned (exact mode) that the box contains changing content.

**Windows hiding and coming back (4.5.1)**
- Never `withdraw()` / `deiconify()` app windows directly for picks and tests. Use
  `app.hide_windows(wins)` → `saved`, then `app.show_windows(saved, focus=win)`; or
  `app.hide_app(parent)` / `app.hide_all_windows()` which return `restore()`. They record each
  window's state and exact geometry, restore the main window first, then raise and focus the
  window the user was in (`bring_to_front`, re-checked twice).
- `release_popdowns(win)` runs before hiding: on Windows a ttk Combobox's dropdown list stays
  a transient (owned) window of the dialog after it was used, and hiding/showing the dialog with
  it attached could leave the dialog hidden behind the main window (the "editor disappears
  after choosing a Picture size" bug).
- `fit_geometry` only shrinks or moves a saved size when it doesn't fit on the screen; it used
  to subtract margins, which changed the main window's size after every test.
- All picks use `app.pick_countdown(on_point, on_cancel)` (Esc from anywhere via
  `key_down(VK_ESCAPE)`, a Cancel label, waits while the mouse is on Cancel).
- `flash_marker(..., seconds=None, others=[...])`: duration from `marker_seconds`; outlines
  for similar pictures.

**Tray status (4.5.1)**
- `tray_status()` builds the tooltip (≤ 127 characters, Windows' `szTip` limit; problems
  first) and the full lines for the tray menu's dynamic **Job status** submenu;
  `update_tray_status()` (from `ui_tick`) sets `tray.title` when it changes and calls
  `update_menu()` at most every 5 s. `main()` sets an explicit AppUserModelID, and the exe
  gets a version resource (`scripts/make_version_file.py`) so Windows shows "Clickue".

**Tables**
- A double-click on a column separator must still start ttk's own resize
  (`ttk::treeview::Press`) before fitting (after idle); returning "break" without it made
  dragging "sticky". The job list's grid-line frames forward presses, drags, releases and
  double-clicks to the tree (`_grid_forward`), because they sit right on the separators.
- `ui_tick` reschedules itself on the second (`1000 - now_ms % 1000`) so countdowns don't
  skip; `tray_tick` (every 250 ms) changes the tooltip only when its text changes.
- **Tick boxes (4.5.3).** The job list's first column `chk` shows ☐/☑ (`App.checked`, a set of
  job ids; UI state only, never saved; pruned in `refresh_tree`). `on_tree_click` toggles on a
  click in display column `#1` (returns "break" so the selection doesn't move); `on_double`
  forwards a quick second click there instead of opening the editor; the heading's command is
  `toggle_check_all`; X and Ctrl+A in the tree. Ticked rows get the `ticked` tag (palette key
  `tick`). The **batch bar** (`build_batch_bar`, `flow_batch_bar`: placed buttons that wrap
  onto more rows, nothing hidden) is packed above the paned list while anything is ticked
  (`update_batch_bar`, from `refresh_tree`). Actions: `batch_action(what)` (start / stop /
  pause / resume / duplicate; skips jobs where it doesn't apply and logs how many),
  `batch_delete` → `delete_jobs(jobs)` pushes **one list entry** on `undo_stack` (entries are a
  `(job, idx, was_on)` tuple or a list of them; `undo_delete` and `show_undo_bar` handle both).
  **Edit together:** `BatchEditDialog` collects only the rows whose tick box is on and calls
  `apply_batch_edit(jobs, changes)`: `clean_batch_changes` (whitelist `BATCH_LABELS`, then
  `sanitize_job` so values are validated like an import), `batch_applies(key, job)`
  (`BATCH_CLICK_ONLY` keys only for scheduled clicks, `watch_*` only for watchers), fixes a
  delay range that became inverted, reschedules running click jobs (`schedule_first`) and
  restarts running watchers (`start_job`) when timing/watch keys changed, keeping `paused`.
- **Number fields (4.5.3):** every spin box with a unit uses `spin_unit()` (or
  `padx=(6, UNIT_GAP)`), so units sit `UNIT_GAP` (4 px) after their field everywhere.
  `JobEditor.hms_row` puts the three h/m/s fields in one frame spanning the grid's columns
  (they used to be separate grid columns, which other rows widened); an optional `suffix`
  label follows them.
- **Tests window layout (4.5.3):** the test buttons and the two groups are gridded when they're
  created, and `relayout()` runs at 60/250/700 ms. Before, they were only placed from
  `<Configure>` events of a still-empty frame, which Windows didn't always send, so the
  buttons stayed invisible until the window was resized.
- `enable_column_fit(tree, on_change)` (every Treeview): a `ColumnFit` bind tag in front of
  the widget's own tags handles double-clicks on a column separator (fit to contents) and on
  headings, returning `"break"` so the row's double-click action doesn't run. The job list
  saves widths in `settings["col_widths"]` (fitted or dragged columns become fixed width).
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

- **Locally:** `scripts\Build Clickue EXE.bat` → `dist\Clickue.exe` (runs
  `scripts\make_version_file.py` for the exe's version details, then PyInstaller `--onefile
  --noconsole --icon assets\clickue.ico --version-file build\version_info.txt
  --hidden-import pystray._win32`).
- **Installer locally:** install Inno Setup 6, set `CLICKUE_VERSION=4.6.1`, run
  `ISCC installer\clickue.iss` → `dist\Clickue-Setup-4.6.1.exe`. The installer shows
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
| `python tests/test_watchers.py` | (4.5.6: click cancelled when the picture returns during the delay or right before the click, screen-change settle, every can't-watch check logged, recovery, can't watch = problem, closest place logged, log levels) watcher scenarios (seen/gone/flicker/scaling/look-alikes/retries), 4.5.3: search-area margin, partial matching, pointer on the picture, import of the match fields; 4.5.4: every copy (exact and partial), one changed digit, compression/noise, 125/150 % scaling, a 15 px icon among 60 others | `RESULT 69/69` |
| `python tests/test_features.py` | hours, limits, steps, click chains, appears/area, history, backups, undo, alerts (faked network), migration, install id, guide link + pictures, 4.5.3 batch actions / delete + undo / Edit together | `RESULT 100/100` |
| `python tests/test_click_spot.py` | click-spot matching at 3 picture sizes × 8 screens (100–175 % scaling, moved, look-alikes), with exact matching and with tolerant matching | `0 of 48` failures |
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
2. Bump `VERSION = "x.y"` (or `"x.y.z"` for a fix release) near the top of `src/clickue.py`.
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
     uninstall keeping data, uninstall deleting data; portable zip; in-app Uninstall for both;
   - 4.5.1: pick a button, scroll it out of view with a similar button visible → Show spot
     says not found (with similar pictures outlined when that's on), the job doesn't click;
     choose Picture size Large, Pick on screen, Show spot and Check now in a watcher editor:
     the editor comes back on top and the main window keeps its size (also when maximized);
     Esc and Cancel during Pick on screen; marker time 2 s; hover the tray icon (status,
     no old name) and right-click → Job status; double-click a job-list column border;
     the exe's Properties → Details shows Clickue 4.5.1.
   - 4.5.3: open 🧪 Tests (also right after starting Clickue): all six test buttons show
     without resizing; a watcher with a search area drawn tightly around its picture is
     *seen*; rest the mouse on a watched button → Check now says *checked again with the mouse
     pointer moved aside* and finds it; a watcher whose box includes a changing value warns
     after Draw box and, with *part of the picture is enough*, stays *Watching*; tick three
     jobs → Pause / Resume / Stop / Delete + one Undo; Edit together → change Check every on
     two watchers; the h/m/s units sit next to their fields in both editors at 100 % and
     125–150 % scaling; ☐/☑ show in the first column.
   - 4.5.4: Draw box → mouse wheel zooms around the pointer, magnifier shows position/colour,
     middle-drag/arrows move, a 10 × 10 icon can be boxed and is found by Check now; a
     picture on screen several times → Check now outlines all; exact watcher on a card whose
     number changes → not found, partial → found on every card; the three filters show their
     own columns, fitted to text; ▲ / ▼ and dragging the divider; disabled toolbar buttons
     are outlines; Tests sections and their history scopes.
   - 4.5.5: right-click → Copy in each log and paste into Excel; the 🔍 filters; click a
     place in Activity / double-click a test row → the app hides and marks it; narrow Tests
     window → the history scrolls sideways; exit and start → Activity still there, Clear view
     → gone after the next start; New watcher is teal; click below the job rows unselects,
     double-click there does nothing.
   - 4.5.6: switch RDP → console with a watcher running: log shows the screen change and
     ~15 s of "can't watch", no click; a gone-watcher with a long random delay: bring the
     picture back during the delay → click cancelled; hover a job (problem + what to do,
     live countdown); tray dot amber during a countdown, green while clicking, red with a
     problem; log level Quiet/Detailed; logs: refresh, order, Clear view, Delete; Delete logs
     and history; job with steps ▸ → ↳ rows; summary per view; Record button colour;
     "Move like a person" on a job, a step, a recorded macro (watch the pointer glide, also
     back) at Slow/Normal/Fast; Customize colours (wheel, code, ↺, both themes).
   - 4.6: the update bar appears for a newer release (test by running an older build), Later /
     Skip / What's new; Upgrade now from an installed copy (for me and for all users) and a
     portable copy: jobs and settings kept, Clickue restarts, Activity says *Upgraded from …*,
     no "keep your jobs?" question; turn checks off and confirm (e.g. with a firewall log) that
     no connection is made; a window watcher with the browser minimized / closed / covered
     (can't watch, no click, pending click cancelled); Clickue's window over the picture (never
     "seen"); click logs show first seen / scheduled for / clicked; the tray tooltip isn't cut.
   - 4.6.1: Check for updates works on a PC that gave *CERTIFICATE_VERIFY_FAILED* before; every
     tray tooltip line is fully visible (a long can't-watch reason wraps); the browser in front
     of a maximized Clickue → the watcher still sees its picture; Clickue in front of the
     picture → *Clickue window in front of the picture*; after a remote session ↔ console
     switch the first check shows *seen* when the picture is there.

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
- No new network destinations, no telemetry. Alerts stay limited to the two services; update
  checks and downloads only to GitHub (`UPDATE_HOSTS`), only while `update_check` is on, and
  every download is checksum-checked.
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
