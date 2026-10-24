# Clickue: complete feature list

← Back to the [README](README.md) · Step-by-step help in the [user guide](docs/USER_GUIDE.md)

## Contents
- [Finding the right spot](#finding-the-right-spot)
- [Scheduled clicks](#scheduled-clicks)
- [Screen watchers](#screen-watchers)
- [Rules for any job](#rules-for-any-job)
- [Multi-step jobs](#multi-step-jobs)
- [Safety](#safety)
- [Tests](#tests)
- [Notifications & phone alerts](#notifications--phone-alerts)
- [Managing jobs](#managing-jobs)
- [History, stats & logs](#history-stats--logs)
- [Backups & data](#backups--data)
- [Window, tray & hotkeys](#window-tray--hotkeys)
- [Appearance & layout](#appearance--layout)
- [Install options](#install-options)

---

## Finding the right spot

- **Pick on screen.** A 5-second countdown, then the spot under your mouse is captured. The
  countdown box can be dragged anywhere, pauses while you drag it, and moves out of the way
  by itself when your mouse comes near.
- **Find the spot by its picture.** A small picture around the spot is saved and searched
  for before every click:
  - multi-scale search (50 %–200 %) that handles different resolutions and 100–175 % display
    scaling, and remembers the scaling it last saw for faster checks
  - a whole-picture match plus a close-up match of the exact spot, so it can tell the right
    place from look-alikes
  - when the picture appears more than once, it picks the copy closest to where it was saved
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
  watch (shows the size while dragging).
- Click **when the picture disappears** or **when it appears**.
- For "appears": optionally **click the picture itself** where it was found, instead of a
  separate button.
- Search **the whole screen** or **only an area** you draw (faster, ignores look-alikes
  elsewhere, scales with the screen size).
- Strict matching: shape, close-up detail and colour must all agree. A same-shaped badge in a
  different colour, or with changed text, counts as changed.
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

## Multi-step jobs

After its main click, any job can run more steps in order:
- **Click a spot**, picked on screen and found by its picture; any button, single or double
- **Wait** a fixed time or a random range
- **Type text** of any characters, including other languages and symbols; new lines press Enter
- **Press keys**, e.g. `Enter`, `Tab`, `Esc`, `Ctrl+S`, `Alt+F4`, `Ctrl+Shift+S`, arrows, F1–F12
- Add, edit, reorder and remove steps. If a step fails, the rest are skipped and it's
  reported.

## Safety

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
  how it was found (e.g. "picture 81 % at 150 % size"). No click.
- **Test click now.** Clicks once, without changing the schedule.
- **Schedule test click.** Clicks once in X minutes (e.g. after you disconnect) and reports.
- **Check picture.** Is the watched picture on screen (or in its area) right now?
- **Dry run.** Marks the watched picture, then the button it would click, and says whether it
  would click now. No click.
- **Schedule watcher test.** Runs the watcher check later in the background; optionally
  really clicks.
- Pending tests show as purple rows with a countdown. **Test history** for this job or all
  jobs, with full details.

## Notifications & phone alerts

- Tray notifications for watcher clicks, missed or failed clicks and test results.
- **Phone alerts** through a **Discord webhook** and/or a **Telegram bot**.
- Choose the events: a watcher clicked, a click was missed or failed, a job finished, or
  scheduled test results.
- **Send a test alert** button. Alerts are sent in the background and never slow down
  clicking.

## Managing jobs

- Separate **scheduled clicks** and **screen watchers**, with a filter: All / Scheduled clicks
  / Screen watchers.
- Add, edit (double-click), duplicate, delete with **undo** (Ctrl+Z), start/stop, pause/resume.
- Right-click any job for every action.
- **Import / export** jobs to a file (add to or replace current jobs).
- Unsaved-changes protection in editors.

## History, stats & logs

- **Click history** of every click, miss and failure (time, job, type, result, position, how
  the spot was found).
- **Stats per job:** total clicks, today, last 7 days, problems, last click and last problem,
  and recent activity.
- **Export history to CSV** (opens in Excel or Google Sheets), for one job or all.
- **Activity** panel, colour-coded, filterable by Everything / Clicks / Problems.
- Log file with a size limit and 2 older copies kept; the history is capped at 50,000 rows.

## Backups & data

- **Daily automatic backup** of all jobs and settings (keeps the newest 14, adjustable).
- **Backups window** to back up now, restore (replace or add) and open the folder. Your
  current jobs are backed up before any restore.
- Everything is stored in `%APPDATA%\Clickue` and survives reinstalling or moving the
  program. Damaged files are set aside instead of wiping your jobs.
- Offers to import jobs from the previous version (*Scheduled AutoClicker*). It asks first and
  never imports silently.
- **Reinstalling:** if jobs from before are found after a fresh install, Clickue asks whether
  to keep them or start fresh (they're backed up first). The uninstaller asks whether to remove
  your data too.
- **Uninstall** from inside the app, with an optional backup of your jobs to Documents first.

## Window, tray & hotkeys

- Minimize and/or close to the **system tray**; tray menu with Show, Pause all and Exit.
- **Global hotkeys** that work while hidden: pause/resume all (default **Ctrl+Alt+P**),
  show/hide Clickue (default **Ctrl+Alt+K**), both changeable.
- Start with Windows and start minimized (optional).
- Keyboard shortcuts: Ctrl+N new click, Ctrl+Shift+N new watcher, Enter edit, Space
  start/stop, P pause job, Ctrl+P pause all, Ctrl+T tests, Ctrl+Z undo, Ctrl+, preferences,
  Del delete.
- **Tests** opens as a popup over the main window; popups close when you click outside them.

## Appearance & layout

- **Light, dark or system** theme, including dark title bars.
- **Responsive.** Toolbar buttons that don't fit fold into **More ▾**, less important columns
  hide, and summary cards re-flow (4 → 2 → 1). The summary can be collapsed.
- **Drag dividers** to resize the job list, the activity panel, and the tests and history
  areas.
- Every window and dialog **remembers its size and position** (and whether it was maximized).
  Sizes are kept on screen if the screen gets smaller.
- Clear grid with column lines, status icons and colour coding.

## Install options

- **Installer.** For only you (no admin) or for all users (Program Files). Each Windows user
  keeps their own jobs and settings.
- **Portable.** Unzip and run. A `portable.txt` file next to `Clickue.exe` keeps all data in
  a `ClickueData` folder beside it.
- **From source.** Python 3 with pillow, pystray, opencv-python-headless and numpy.
