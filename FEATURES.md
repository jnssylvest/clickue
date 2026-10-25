# Clickue: complete feature list

← Back to the [README](README.md) · Every feature explained with examples and pictures in the
[**complete guide**](docs/GUIDE.md) · [Quick start](docs/USER_GUIDE.md) · [Security](SECURITY.md)

> [!IMPORTANT]
> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.
> See [SECURITY.md](SECURITY.md).

Everything below is available in Clickue 4.5 unless it's under
[Planned](#planned-not-in-this-version).

## Contents
- [Finding the right spot](#finding-the-right-spot)
- [Scheduled clicks](#scheduled-clicks)
- [Screen watchers](#screen-watchers)
- [Rules for any job](#rules-for-any-job)
- [Steps & workflows](#steps--workflows)
- [Recording macros](#recording-macros)
- [One job at a time](#one-job-at-a-time)
- [Safety](#safety)
- [Tests](#tests)
- [Notifications & phone alerts](#notifications--phone-alerts)
- [Managing jobs](#managing-jobs)
- [History, stats & logs](#history-stats--logs)
- [Screen video & run history](#screen-video--run-history)
- [Backups & data](#backups--data)
- [Window, tray & hotkeys](#window-tray--hotkeys)
- [Appearance & layout](#appearance--layout)
- [Install options](#install-options)
- [Planned (not in this version)](#planned-not-in-this-version)

---

## Finding the right spot

- **Pick on screen.** A 5-second countdown, then the spot under your mouse is captured. The
  countdown box can be dragged anywhere, pauses while you drag it, and moves out of the way
  by itself when your mouse rests near it. **Esc** (from anywhere) or its **✕ Cancel** button
  cancels without changing anything; afterwards the editor comes back exactly where it was.
- **Find the spot by its picture.** A small picture around the spot is saved and searched
  for before every click:
  - multi-scale search (50 %–200 %) that handles different resolutions and 100–175 % display
    scaling, and remembers the scaling it last saw for faster checks
  - a whole-picture match plus a close-up match of the exact spot, so it can tell the right
    place from look-alikes
  - **Only the exact picture** (on by default, per job and per click step): the place must be
    the saved picture almost pixel for pixel (at another display scaling it's scaled back and
    compared again, colours included). A similar-looking picture is never clicked, also when
    the real one is off-screen; identical copies are only used at the place you picked
  - with exact matching off (tolerant, the pre-4.5.1 behaviour): when the picture appears more
    than once, it picks the copy closest to where it was saved
  - picture size Small / Medium / Large; warns if the spot is too plain to recognize
  - if it can't be found: **wait and retry** (default) or **click the saved position**
- **Inside a window** (alternative). Remembers which window the spot is in and where inside
  it, finds that window wherever it is, can bring it to the front, and can scale the spot if
  the window was resized.
- **Fixed screen position** (simplest), with optional scaling when the resolution changes,
  and a warning when the screen size differs from when it was picked.
- Precise on high-DPI screens. Clicks and the on-screen marker use real pixel coordinates.

## Scheduled clicks

- Any interval in hours, minutes and seconds (e.g. every 8 h).
- **Random delay** after each scheduled time, e.g. 10 s to 15 min, random to the second, or
  **turn it off** for exact timing.
- **Fixed schedule.** Random delays never push later clicks later, so there's no drift.
- Optional **first scheduled time** of day (e.g. start at 08:00).
- Missed-click handling: if the screen is locked or disconnected, it retries every 30 s for
  a set time (default 15 min), then records **Missed** and moves on to the next time. A click
  that came due while Clickue was closed is skipped, not fired late.
- Left, right or middle button; single or double click.

## Screen watchers

- **Draw box around picture.** The screen freezes and dims, and you drag a box around what to
  watch (shows the size while dragging). Saved at **full screen resolution**, lossless, with
  the mouse pointer moved aside so hover highlights aren't saved. Clickue looks again a moment
  later and **warns if part of the box changes** (a number, a clock, an animation).
- Click **when the picture disappears** or **when it appears**.
- For "appears": optionally **click the picture itself** where it was found, instead of a
  separate button.
- Search **the whole screen** or **only an area** you draw (faster, ignores look-alikes
  elsewhere, scales with the screen size). The area is searched **with a small margin**, so a
  picture at its edge, or an area drawn tightly around the picture, still counts.
- **Match the exact picture** (default, strict): shape, close-up detail and colour must all
  agree. A same-shaped badge in a different colour, or with changed text, counts as changed.
- Or **part of the picture is enough: N %** (40–95 %, default 75 %): the picture is compared
  tile by tile (colour included) and counts as showing when at least N % of it matches, so a
  changing value inside the box doesn't make it "gone". Results show *82 % of it matches*.
- **Mouse pointer on the picture:** hovering can change how a button looks, so tests re-check
  with the pointer moved aside, and a running watcher doesn't count the picture as missing
  while you rest the pointer on it (it re-checks with the pointer moved aside once the
  computer has been idle for 20 s).
- **Check every** N seconds (any interval).
- **Flicker protection.** Click only after the change is seen N checks in a row (quick
  re-checks every 5 s).
- Optional **random delay** before clicking (or none).
- Optional **wait after each click** before looking again.
- **Click only once** each time it changes, waiting until the picture comes back (or goes
  away) before clicking again. Can be turned off to keep clicking.
- Won't count "picture missing" while Clickue's own window is open on screen (it could be
  covering the picture).
- Live status in the list: Watching / Missing / Showing / Clicking / Off hours, last seen,
  and a countdown to the next check.

## Rules for any job

- **Active hours and days.** Only run between set times on chosen weekdays; overnight windows
  (e.g. 22:00–06:00) work. For scheduled clicks, a click due outside the hours either **waits
  for them to start** or is **skipped**. Watchers simply rest.
- **Stop after N clicks** (counted from when the job is started).
- **Stop at** a date and time.
- When a limit is reached the job stops, shows *Finished* and can send an alert.

## Steps & workflows

After its main click, any job can run **steps** in order, or a job can be **steps only**
(untick *Start with a click on this spot*). Steps are edited on a **timeline**:
- **Click a spot**, found **by its picture** (checked before clicking), **inside a window**, or
  at a **fixed position** (not verified); any button, single or double. **Picture of this spot
  now** and **Use the window at this spot** turn a fixed position into a checked target. The
  editor says how each target is found and what happens if it isn't (it never silently falls
  back to an unchecked position)
- **Wait** a fixed time or a random range (decimals allowed)
- **Wait for a picture** to **appear** (then optionally **click it**) or **go away**, up to a
  time limit (1 s–1 h), then **stop the chain** or **continue anyway**: a **click chain** that
  reacts to each click's result
- **Type text**: one key per character, any language and symbols; new lines press Enter (up to
  20,000 characters)
- **Paste text**: clipboard + Ctrl+V (or Shift+Insert / Ctrl+Shift+V) for long, multi-line,
  any-language text (up to 200,000 characters); **puts your clipboard back** afterwards, keeps
  pasted text out of Windows clipboard history and cloud sync, and says honestly when a
  clipboard format couldn't be restored
- **Secret** text for Type / Paste: encrypted with your Windows account (DPAPI), hidden in the
  timeline, never logged or exported, blacked out in videos
- **Variables**: `{date}`, `{time}`, `{datetime}`, `{year}`…`{weekday}`, `{job}`, `{run}`, `{loop}`
  and your own, filled into Type / Paste text when ticked
- **Set a variable** (set / add / subtract), optionally **remembered for the next run** (counters)
- **If … Otherwise … End** on a picture showing / not showing, a window open / not open, or a
  variable (`==`, `!=`, `<`, `>`, `<=`, `>=`, `contains`), optionally waiting for it
- **Repeat … End**: N times (up to 10,000), or **until** a condition, always with a maximum
  number of times and seconds
- **Step groups**: save steps once, use them in many jobs (☰ Menu → Step groups); no nesting,
  so they can't call themselves
- **Press keys** (with *× N*), **Scroll**, **Drag**, **Move the mouse**, **Mouse button down /
  up**, **Hold a key down / let go** (e.g. Shift+click)
- Per step: a **name**, **retries** with a wait in between, **stop or continue if it fails**, and
  **⚠ careful** (Step through always stops there)
- Timeline: add after the selected step, edit, duplicate, remove, move (several at once),
  indented blocks with a clear message when they don't match, make all waits shorter / longer,
  remove short waits or mouse movements, save selected steps as a group
- Limits that can't be switched off: a time limit per run (default 6 h, up to 24 h), at most
  200,000 steps per run, limits on every wait and loop; held keys and buttons are always
  released when a run ends
- Start a workflow on a schedule, or from a screen watcher

## Recording macros

- **⏺ Record** (toolbar, ☰ Menu or **Ctrl+Alt+R** from anywhere) records your mouse and
  keyboard; a red bar shows the time, clicks and keys, with **Pause**, **Stop** and **Cancel**
  (hotkeys too)
- Records clicks (left / right / middle), double clicks, long presses, drags (with their path),
  mouse movement (simplified), scrolling, typed text (Backspace fixes the text), keys and
  combinations, Shift/Ctrl held during clicks, and pauses as editable waits
- Optionally saves a small **picture of each clicked spot**, so recorded clicks find their
  target later even if it moves
- Never records Clickue's own windows, its own input, or the start/stop hotkeys; works across
  multiple monitors (including negative coordinates)
- Compact: long mouse movements are reduced to the points that matter; up to 300,000 raw
  events per recording
- The result opens as a new, **stopped**, steps-only job to check and edit
- Warns that typed passwords would be recorded

## One job at a time

- All clicks and keystrokes go through **one queue**: Windows has one mouse and keyboard focus,
  so jobs never click over each other (Clickue doesn't fake several mice)
- **Watchers keep watching** while another job runs
- A bar above the job list shows the **running job** (with its step) and who's **waiting their
  turn**, with **Stop this run**; the log notes long waits
- **Priority** per job (High / Normal / Low); test clicks you start go first
- **Let other jobs click in between** while a job's steps are only waiting (opt-in)
- **Warnings** when two running jobs use the same window or the same fixed spot
- Designed so isolated workers (separate desktops / VMs) can be added later (planned)

## Safety

- **Emergency stop** (**Ctrl+Alt+X**, ☰ Menu, tray): ends the running job, drops queued
  clicks, lets go of held keys and buttons, cancels a recording, pauses everything.
- **Pause all** also pauses a running job between its steps.
- Held keys and mouse buttons are always released when a run ends and when Clickue exits.
- **Waits for idle.** Won't move the mouse until you've stopped using the mouse and keyboard
  for N seconds (default 5).
- **Puts the mouse back** where it was after clicking (optional).
- Refuses to click when another window, or Clickue itself, is covering the target, and
  retries instead.
- Detects a locked or disconnected screen and waits rather than clicking.
- **Pause** a single job (keeps its schedule) or **Pause all**, also from the tray and with a
  global hotkey.
- **Stop** a job, with limits by count and time.
- Only one copy of Clickue can run at a time, so there are never double clicks.
- Keeps the PC and display awake while running (optional).

## Tests

All tests hide the whole app while they run, so nothing is in the way.
- **Show spot.** Moves the mouse to where it would click and shows a pulsing crosshair, with
  how it was found (e.g. "exact picture 93 % at 150 % size"). No click. Optionally outlines
  **every similar picture** on screen at the same time (green = would be used, orange = same
  picture elsewhere, grey = similar but ignored). The marker stays **5 s by default, 1–120 s**
  as you choose in Preferences → Clicking (also for Check picture / Check now).
- **Test click now.** Clicks once, without changing the schedule.
- **Schedule test click.** Clicks once in X minutes (e.g. after you disconnect) and reports.
- **Check picture.** Is the watched picture on screen (or in its area) right now?
- **Dry run.** Marks the watched picture, then the button it would click, and says whether it
  would click now. When the picture isn't found, outlines the closest places with how close
  they came. No click.
- **Schedule watcher test.** Runs the watcher check later in the background; optionally
  really clicks.
- **Dry run of steps** (job editor, right-click menu): checks every step's target and condition
  against the screen as it is now and lists what would happen. Never clicks or types.
- **Step through:** runs a job for real, one step at a time, showing the next step, why its
  target was chosen and where it will click; run to the end (still stopping at ⚠ careful steps)
  or stop.
- Pending tests show as purple rows with a countdown. **Test history** for this job or all
  jobs, with full details.

## Notifications & phone alerts

- Tray notifications for watcher clicks, missed or failed clicks and test results.
- **Phone alerts** through a **Discord webhook** and/or a **Telegram bot**.
- Choose the events: a watcher clicked, a click was missed or failed, a job finished, or
  scheduled test results.
- **Send a test alert** button. Alerts are sent in the background and never slow down
  clicking.
- Hardened: only discord.com webhooks and api.telegram.org, HTTPS with certificate checks, no
  redirects, short timeouts, a small response limit, and a rate limit (one per 2 s and 60 an
  hour per service). Credentials are masked, validated when saved, redacted from logs, kept out
  of backups and exports, and can be **encrypted with your Windows account**.

## Managing jobs

- Separate **scheduled clicks** and **screen watchers**, with a filter: All / Scheduled clicks
  / Screen watchers.
- Add, edit (double-click), duplicate, delete with **undo** (Ctrl+Z), start/stop, pause/resume.
- **Tick boxes** in the job list (click the box, **X**, **Ctrl+A**, or the heading box for all
  shown). A bar for the ticked jobs: **Start, Stop, Pause, Resume, Duplicate, Delete** (one
  Undo restores them all) and **Edit together**.
- **Edit together (batch edit):** set the same settings on all ticked jobs, ticking only the
  settings to change: mouse button, single/double, priority, exact click-spot picture, picture
  fallback, active hours, run time limit, bring to front, let others run, video, failure
  screenshot; for scheduled clicks the interval and random delay; for watchers the check
  interval, checks in a row, random delay, wait after clicking, click only once and the match
  mode. Settings that don't fit a kind of job are skipped; values are validated; running jobs
  pick up new timing, paused jobs stay paused.
- Right-click any job for every action.
- **Import / export** jobs (and the step groups they use) to a file. Imports are checked and
  cleaned (size and version limits, field types and ranges, pictures, steps), report what was
  fixed and which steps send keyboard input, and arrive **stopped**. Exports never contain
  secret text or alert credentials.
- Unsaved-changes protection in editors.

## History, stats & logs

- **Click history** of every click, miss and failure (time, job, type, result, position, how
  the spot was found).
- **Stats per job:** total clicks, today, last 7 days, problems, last click and last problem,
  and recent activity.
- **Export history to CSV** (opens in Excel or Google Sheets), for one job or all.
- **Activity** panel, colour-coded, filterable by Everything / Clicks / Problems.
- Log file with a size limit and 2 older copies kept; the history is capped at 50,000 rows.

## Screen video & run history

- **Run history** (☰ Menu → Run history & videos): every run with its steps, results and timing;
  searchable, filter to failed runs; never contains typed or pasted text
- Optional **screen video of runs** (off by default; per job): only while the job runs, with a
  red indicator (pause / stop the video), saved locally as MP4 (or AVI), never uploaded
- Quality presets **Compact / Standard / High** with their size trade-off; choose the folder
- Each step in the run history is linked to its **position in the video**; **Play video from
  this step** opens a built-in player there
- **Hidden areas** always blacked out; video blacked out while text is typed or pasted
- Clean-up by age (default 14 days) and total size (default 5 GB); only Clickue's own video
  files are deleted
- Won't start with less than 1 GB free; stops (the job carries on) below 300 MB or on errors
- Optional **failure screenshot** when a job's steps fail (hidden areas blacked out; newest 30
  kept)

## Backups & data

- **Daily automatic backup** of all jobs, step groups and settings (keeps the newest 14,
  adjustable). Phone-alert credentials are never copied into backups.
- A backup is saved **every time a new version first starts with your jobs**
  (*before-upgrade-<version>*, e.g. *before-upgrade-4.5.2*), before an import that replaces
  your jobs, before a restore and before a fresh start.
- **Missing or damaged jobs file:** Clickue offers to restore the newest backup (showing its
  date and job names); restored jobs start stopped. A settings file from the very first
  versions is only offered when the data folder was never used, and never imported silently.
- The Activity log says how many jobs were loaded, from which file and which version saved
  them; a failed save is retried and then shown as a warning (never silent).
- **Backups window** to back up now, restore (replace or add) and open the folder. Your
  current jobs are backed up before any restore.
- Everything is stored in `%APPDATA%\Clickue` and survives reinstalling or moving the
  program. Damaged files are set aside instead of wiping your jobs. A portable copy keeps its
  own jobs in `ClickueData` next to it (move jobs with Export / Import).
- Offers to import jobs from the previous version (*Scheduled AutoClicker*). It asks first and
  never imports silently.
- **Reinstalling:** if jobs from before are found after a fresh install, Clickue asks whether
  to keep them or start fresh (they're backed up first). The uninstaller asks whether to remove
  your data too.
- **Uninstall** from inside the app: removes the program (via Windows' uninstaller when
  installed) and the start-with-Windows entry, and **asks** whether to keep or delete your data
  (with an optional copy of your jobs in Documents). It only deletes a folder after checking
  it's really Clickue's data folder.

## Window, tray & hotkeys

- Minimize and/or close to the **system tray**; tray menu with Show, **Job status**, Pause all,
  Stop everything now and Exit.
- **Job status on the tray icon.** Point at the icon to see a summary (*3 active · all OK* or
  *1 needs attention*), what's running now, and each active job's health, problems first,
  with **live** countdowns. The tray menu's **Job status** lists every active job with clock
  times. Can be turned off.
- Windows shows the name **Clickue** for the tray icon, taskbar and the program file's details.
- **Global hotkeys** that work while hidden, all changeable: pause/resume all (**Ctrl+Alt+P**),
  show/hide Clickue (**Ctrl+Alt+K**), emergency stop (**Ctrl+Alt+X**), start/stop recording
  (**Ctrl+Alt+R**), pause/resume recording (**Ctrl+Alt+U**).
- Start with Windows and start minimized (optional).
- Keyboard shortcuts: Ctrl+N new click, Ctrl+Shift+N new watcher, Enter edit, Space
  start/stop, P pause job, Ctrl+P pause all, Ctrl+T tests, Ctrl+Z undo, Ctrl+, preferences,
  Del delete.
- **Tests** opens as a popup over the main window; popups close when you click outside them.
- **Help built in:** ☰ Menu → **Complete guide (online)** opens the [complete guide](docs/GUIDE.md)
  in your browser; **Help & shortcuts** shows a short summary in the app.

## Appearance & layout

- **Light, dark or system** theme, including dark title bars.
- **Responsive.** Toolbar buttons that don't fit fold into **More ▾**, less important columns
  hide, and summary cards re-flow (4 → 2 → 1). The summary can be collapsed.
- **Drag dividers** to resize the job list, the activity panel, and the tests and history
  areas.
- Every window and dialog **remembers its size and position** (and whether it was maximized).
  When the app hides for a pick or a test, every window comes back exactly as it was, with the
  window you were using on top. Sizes only change if a window no longer fits on the screen.
- **Column widths:** drag a column border (it responds on the first grab, also right on its
  line and right after a double-click), or **double-click** it to fit the column to its
  contents (like a spreadsheet), in every table. The job list remembers its widths;
  ☰ Menu → Reset column widths.
- Clear grid with column lines, status icons and colour coding.
- Number fields keep their **units right next to them** (h, m, s, seconds, %), with the same
  spacing everywhere.

## Install options

- **Installer.** For only you (no admin) or for all users (Program Files). Each Windows user
  keeps their own jobs and settings.
- **Portable.** Unzip and run. A `portable.txt` file next to `Clickue.exe` keeps all data in
  a `ClickueData` folder beside it.
- **From source.** Python 3.10+ with pillow, pystray, opencv-python-headless and numpy (no
  other packages; screen video uses OpenCV, which is already needed for picture matching).
- All three run the same program with the same features. Windows 10/11 only.
- The installer shows a short notice before installing; its uninstaller removes the program,
  shortcuts and its start-with-Windows entry, and asks before deleting your data.
- Releases come with SHA-256 checksums.

## Planned (not in this version)

These are **not** available yet:
- Finding **text on screen (OCR)** as a target or condition
- **Windows UI Automation** (clicking controls by name)
- **Browser element** targeting through a browser integration
- Running jobs side by side on **isolated desktops / virtual machines** (separate workers)
- Opt-in, locally installed add-ons for other target types (today, target adapters are built
  into Clickue; see the [developer guide](docs/DEVELOPER_GUIDE.md))
