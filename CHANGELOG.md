# Changelog

## 4.6.0 - Upgrade in the app; window-aware watchers; full click timing in the logs

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

From now on, versions with new features raise the middle number (4.6, 4.7 …); versions with
only fixes raise the last one (4.6.1 …).

**New**
- **Upgrade in the app.** A daily check (Preferences → General, on by default) shows a
  dismissible notice when a new version is out: **Upgrade now**, What's new, Later, Skip this
  version; ☰ Menu → Check for updates. Upgrading downloads the right package from GitHub, checks
  it against the release's SHA-256 checksums, backs up your jobs, installs it (installed: the
  installer runs silently and Clickue restarts; portable: the new Clickue.exe replaces the old
  one) and keeps your jobs and settings without asking. With the check off, Clickue never
  connects to the internet for updates.
- **Window-aware watchers.** A watcher whose button is *Inside a window* watches that window:
  if it's not open or minimized, the watcher reports **Can't watch** (not "picture gone"),
  nothing is clicked, and a click counting down is cancelled; it only looks inside that
  window (and its area); a window covering it is reported. Works with whole-screen and area
  searches, and in Check now / Dry run.
- **Click timing in the logs.** Watcher clicks log when the change was first seen, when it was
  confirmed, when the click was scheduled for and when it clicked; scheduled clicks log their
  slot, random delay, due time and click time (and how late, if they had to wait).

**Fixed**
- **"Picture seen" while Clickue's own window covered it** (and "picture came back" cancelling
  a click when Clickue was brought up): a small picture could match something inside Clickue's
  own window. Clickue's windows are now left out of the search.
- The tray tooltip cut lines off at 34 characters ("· next c…"); whole lines are shown when
  they fit.
- Exact matches at another display size reported the unverified score (e.g. 67 %); they now
  report the verified one.

**Data:** new settings `update_check` (on), `update_last_check`, `update_skip`,
`update_later_until`, `update_known`, `upgrade_pending`, `upgrade_from`; runtime job fields
`first_miss_at`, `click_planned_at`, `planned_run`. No schema change. The installer restarts
Clickue after a silent in-app upgrade (`/RELAUNCH`).

**Docs:** guide sections 6 (window-aware watchers, own windows, click timing), 17, 20, 25
(updating), 26; SECURITY (update checks), README (privacy), feature list, quick start,
developer guide.

## 4.5.6 - Honest status everywhere, watcher fixes, log tools, person-like mouse, your own colours

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

**Fixed**
- **A watcher clicked after its random delay even though the picture had come back.** During
  the delay it didn't look any more. Now it keeps checking during the delay and looks once
  more right before the click; if the picture is back (or, for "appears", gone) the click is
  **cancelled** and logged.
- **Switching between a remote session and the console could make a picture count as gone.**
  When the screen's size or scaling changes, a watcher now waits 15 s before counting checks
  again (logged with the old and new size). When a picture isn't found inside a search area
  that was drawn on another screen size, the log says so and what to do.
- **"Can't tell" looked like "fine".** A watcher that can't see its picture (screen locked,
  Clickue window open, mouse pointer on it, screen just changed…) now shows **⚠ Can't
  watch** in orange, is listed under *needs attention* in the tray, and the tray tooltip no
  longer says *all OK*.
- The "picture was here" label on screen was cut off for small pictures.
- Watcher test and dry-run results now include **where the picture was found** (or the closest
  place), not only the button.

**Status and logs**
- **Hover over a job** for its full status in plain words: any problem and what to do, the
  next check or click (live), the last result, where it clicks.
- **Every check that has a problem is logged** (the first one with what to do), every try of
  a waiting click too, and missing pictures with the closest place found.
- **Log level** (Preferences → Data & backups): Quiet, Normal, Detailed.
- **Every log**: ⟳ Refresh, newest / oldest first, **Clear view** (hides for now, deletes
  nothing) and **Delete…** (for good). Activity: ⟳ Refresh, order, Clear view (now temporary),
  **Delete log…**. ☰ Menu → **Delete logs and history…** for several at once.
- Lines about **steps** stand out in Activity (teal ↳).

**Main window**
- **Summary per view:** Scheduled clicks and Screen watchers each show their own cards (for
  watchers: next check with a live countdown, watchers that can't watch, watcher clicks
  today). The toggle is now a clear **📊 Hide / Show summary** button.
- **⟳ Refresh** (F5): watchers check right away, the list is rebuilt.
- **Record** is a rose primary button next to New click and New watcher.
- **Jobs with steps** have ▸ / ▾ arrows; their steps can be shown as indented ↳ rows.
- **Tray icon colours:** amber while a click counts down, green while clicking, red when a job
  has a problem (Preferences → General).
- Watchers' live next-check countdown also in the tray tooltip and the summary.

**New**
- **Move the mouse like a person:** smooth, slightly curved, eased movements to each click
  (and back) instead of jumping. Per job and per click step (*Mouse movement*), for recorded
  macros (Record dialog), and as the default with a speed in Preferences → Clicking.
- **Your own colours:** Preferences → Appearance → Customize colours… with a colour wheel,
  brightness, colour codes and R/G/B, for every colour of the light and the dark theme.

**Data:** new job key `human_move` (empty = Preferences) and click/wait-for-picture step key
`human_move`; new settings `log_level`, `log_order`, `tray_colors`, `human_move`,
`human_speed`, `rec_human`, `custom_colors`, `stats_clicks_watch`, `stats_missed_watch`.
Existing jobs behave as before (mouse still jumps). No schema change.

**Docs:** guide sections 3, 5, 6, 9, 15, 19, 20, 23, 26; feature list, quick start, README,
developer guide.

## 4.5.5 - Logs you can copy, filter and show on screen; Activity kept across restarts

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

**Logs**
- **Right-click → Copy** in every log: Activity, the Tests window's history, Run history (runs
  and steps), a job's Stats and Dry run results. Copy the selected rows, one cell, or
  everything shown with headings (tab-separated, pastes into a spreadsheet); Select all; Save
  as CSV (Activity: text file); Filter to this job or test; Edit this job; Ctrl+C, Ctrl+A,
  Ctrl+F.
- **🔍 Filter box** on every log: shows only the lines containing what you type.
- **Show on screen:** a place in a log line, like *(878, 243)*, is a link in Activity, and a
  right-click (or double-click) item in the test and stats logs. Clickue hides and marks it
  like Check picture, with the watched picture's outline where the line says it was found.
- **What the colours mean:** every test-history row says *OK*, *Attention* or *Failed* in a new
  Meaning column, and a legend under the table explains them.
- **Horizontal scrollbar** in the logs when the text is wider than the window (the Tests
  history no longer hides columns or cuts results off when the window is narrow).
- **Activity keeps its lines when Clickue exits and starts again.** Only *Clear view* removes
  them (for good), or Preferences → General → *Clear Activity every time Clickue starts*.

**Main window**
- **New watcher** is now a teal primary button next to the blue New click.
- **Click the empty part of the job list** to unselect the row. A double-click there no
  longer opens (and immediately closes) the editor; only a double-click on a row edits it.

**Data:** new settings `activity_clear_on_start` (off) and `activity_cleared_at`. No job or
schema changes.

**Docs:** guide sections 3, 10 (colour meanings), 15 (logs: copy, filter, show on screen;
Activity kept across restarts), 20, 23; feature list, quick start, developer guide.

## 4.5.4 - More accurate picture matching, zoom while drawing, smarter job list, cleaner Tests window

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

**Picture matching**
- **Exact matching is now exact for watchers.** Every part of the picture is compared tile
  by tile (colour and shape), so a single changed digit anywhere in the box means "not this
  picture". Before, a copy with a different number could pass when the number was away from
  the middle of the box. Compression noise of remote sessions and display scaling are still
  tolerated (tested with JPEG 75, noise and 125/150 %).
- **Partial matching finds every copy.** Each detailed piece of the picture is searched on
  its own and the pieces vote for where the picture is, so copies whose changing part differs
  (and look quite different as a whole) are found wherever they are. Before, only places
  almost as good as the best one were considered, so other copies were missed.
- **Check now outlines every copy** it finds and says how many times the picture is on screen.
- Plain areas in the middle of a picture no longer make real matches fail on a slightly
  noisy screen. Pictures down to 6–8 pixels work.

**Drawing boxes**
- **Zoom while drawing** on every Draw box screen: mouse wheel or + / − up to 24× around the
  pointer, a pixel grid from 8×, middle-drag or arrow keys (Shift: one pixel) to move, 0 for
  the whole screen; you can zoom while dragging. A **magnifier** next to the pointer shows
  the exact pixels, their screen position and colour, and the box size. The saved picture is
  always the real screen pixels. Boxes from **8 × 8** pixels (was 16 × 16).
- Pictures for *Wait for a picture* steps and conditions are also captured with the mouse
  pointer moved aside.

**Job list**
- **Columns per view.** *Scheduled clicks*: Clicks at, Schedule, Runs (active hours, limits),
  Next click, Starts in. *Screen watchers*: Watching for (disappears/appears, size, area,
  exact or % match), Then, Checks (interval, checks in a row, once), Picture (last seen),
  Next check. *All*: Type, What it does, Next / last seen, In. Every view: tick box, Status,
  Name, Clicks, Last result. Switch with the filter buttons.
- **Columns fit their text** automatically (with sensible maximums); they don't jump around
  while countdowns run. Widths you set yourself are kept; ☰ Menu → Reset column widths goes
  back to automatic.
- **Taller list or taller Activity:** a visible divider to drag, plus ▲ / ▼ next to Activity
  (Ctrl+Up / Ctrl+Down). Either part can be made almost as small or as big as you like;
  remembered.
- **Buttons you can't use right now are outlines without fill**; usable buttons are filled.

**Tests window**
- **Sections:** All tests, Click tests, Watcher tests. Each shows its own buttons and its own
  history, for this job or all jobs (remembered per section). The history now sits right
  under the buttons instead of below empty space.

**Data:** new settings `tests_section`, `tests_scopes`. No job or schema changes.

**Docs:** guide sections 3 (views, columns, heights), 6 (zooming while drawing, exact and
partial matching), 10 (Tests sections), 23, 26; new picture *draw-zoom*, updated
*main-window*; feature list, quick start, README, developer guide.

## 4.5.3 - Tick boxes and batch editing, partial picture matching, watcher and layout fixes

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

**New**
- **Tick boxes in the job list.** Click the box at the start of a row (or press **X**;
  **Ctrl+A** or the heading box ticks every job shown). A bar above the list then offers
  **Start, Stop, Pause, Resume, Duplicate, Delete** for all ticked jobs. One Undo brings back
  every job a batch delete removed.
- **Edit together (batch edit).** Set the same settings on all ticked jobs: tick only the
  settings to change (mouse button, single/double, priority, exact picture, picture fallback,
  active hours, run time limit, bring to front, let others run, video, failure screenshot;
  interval and random delay for scheduled clicks; check interval, checks in a row, random
  delay, wait after clicking, click only once and match mode for watchers). Settings that
  don't fit a kind of job are skipped, values are validated like an import, running jobs pick
  up new timing, paused jobs stay paused.
- **Watchers: "part of the picture is enough".** A new **Match** option per watcher: *the
  exact picture* (default, as before) or *part of the picture is enough: N %* (40–95 %,
  default 75 %). The picture is compared in small tiles (colour included), so a changing
  number, time or animation inside the box no longer makes it count as gone. Results say how
  much of it matched.

**Fixed**
- **A watched picture was reported missing although it was on screen.** Several causes fixed:
  - A **search area** drawn as big as the watched picture, or a few pixels smaller, left no
    room to find it; the area is now searched with a small margin.
  - The picture was saved with the **mouse pointer** wherever it was, so a hover highlight
    could be saved with it (or be on screen during a check). Draw box now moves the pointer
    aside for a moment; Check now, Dry run and watcher tests re-check with the pointer moved
    aside; a running watcher doesn't count the picture as missing while the pointer rests on
    it (and re-checks with the pointer moved aside when the computer has been idle for 20 s).
  - **Changing content inside the box:** right after drawing, Clickue now checks the box
    again and warns when part of it changes, and suggests a smaller box or partial matching.
  - Dry run now outlines the closest places when the picture isn't found, and messages say how
    close they came.
- **The Tests window showed no test buttons until it was resized.** The buttons are laid out
  as soon as the window opens (Windows didn't always report the size of the still-empty
  button area).
- **h / m / s units sat far from their fields** in the editors. Every number field now keeps
  its unit right next to it, with the same spacing everywhere (editors, step dialogs, tests,
  Preferences).

**Data:** two new watcher fields, `watch_match` (`"exact"`) and `watch_partial_pct` (75), with
defaults that keep existing watchers exactly as they were. Imports validate both. No schema
change.

**Docs:** guide sections 3, 6 (exact or partial matching, the mouse pointer, search-area
margin), 14 (tick boxes, batch actions, Edit together), 23 and 26; feature list, quick start,
README.

## 4.5.2 - Jobs can't be replaced by old files any more; smoother columns; live tray countdown

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

**Fixed**
- **Jobs could come back from an old file after an update.** When the jobs and settings files
  were missing from the data folder, Clickue silently imported a settings file from its very
  first versions (`autoclicker_config.json` next to the program), which could bring back
  long-deleted jobs instead of your current ones. Now that file is only offered when the data
  folder has never been used, and only after asking (with its job names).
- **A missing or damaged jobs file** now leads to an offer to restore the newest backup (with
  its date and job names) instead of an empty or outdated list. Restored jobs start stopped.
- **A backup is made every time a new version first starts** with your jobs
  (*before-upgrade-&lt;version&gt;*), not only when the file format changes.
- **Misleading log line:** "Moved your jobs and settings from the old config file" was also
  written after every fresh install although nothing was moved. The log now says how many jobs
  were loaded, from which file, which version saved them, when, and their names.
- **Saving:** the jobs file is written first, a briefly blocked file is retried, and a lasting
  failure shows a warning once (it was only a log line before).
- **Column borders felt sticky:** a quick second click on a column border (taken as a
  double-click) didn't start a drag, and the thin grid lines over the headings caught clicks
  meant for the border. Both fixed: borders respond on the first grab.
- **Tray countdowns jumped two seconds at a time.** The tooltip now updates live, second by
  second; the tray menu's Job status shows clock times (*next at 19:16:30*) so it never goes
  stale. The main window's countdown no longer skips a second now and then.

**Docs:** guide sections 2, 3, 17, 19 and 26 (including where portable and installed copies
keep their jobs), feature list, quick start.

## 4.5.1 - Exact picture matching, tray status and window fixes

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

**Fixed**
- **A similar-looking picture could be clicked** when the picked spot wasn't on screen (for
  example scrolled out of view), or when a different button looked alike. New **Only the exact
  picture** option, **on by default** for all jobs and click steps (including existing ones):
  the place must match the saved picture almost pixel for pixel; at another display scaling it
  is scaled back and compared again, close-up and colours included. If the real spot isn't
  there, nothing is clicked and the job retries as usual. Identical copies are only used at the
  place you picked; otherwise nothing is clicked and the log says why. Untick it for the
  previous, more tolerant matching. Watchers' watched pictures get the same extra check at
  other display scalings.
- **The job editor could disappear behind the main window** after Pick on screen, Show spot or
  Check now (especially after using a dropdown such as Picture size). Clickue's windows now
  come back on top, with the one you were using focused; dropdown lists are detached before
  hiding so Windows can't keep the editor hidden.
- **The main window could change size** after Check now or Show spot. Every window now comes
  back at exactly the size, position and state (maximized or not) it had, and saved sizes are
  only changed when a window no longer fits on the screen.
- **The tray icon could show an old name.** Clickue now tells Windows its name and identity
  (AppUserModelID), and the exe carries its own version details (name *Clickue*, version).

**New**
- **Esc or ✕ Cancel** on the Pick on screen countdown (Esc works from anywhere; right-click
  also cancels). The countdown waits while the mouse is on Cancel. Draw box / Draw area got a
  Cancel button and the same global Esc.
- **Point out every similar picture** (Preferences → Clicking, off by default): Show spot and
  Check now outline everything that looks like the picture: green = would be used, orange =
  same picture elsewhere, grey = similar but ignored. Also shown when nothing is found.
- **How long the Show spot / Check now marker stays** (Preferences → Clicking, 1–120 s, default
  5 s as before). Esc or a click closes it sooner.
- **Job status on the tray icon:** point at it for a summary (*3 active · all OK* / *1 needs
  attention*), what's running and each active job's health, problems first. Right-click →
  **Job status** lists every active job. Preferences → General can turn it off.
- **Column widths like a spreadsheet:** double-click a column border to fit the column to its
  contents (every table); the job list remembers fitted or dragged widths; ☰ Menu → **Reset
  column widths**.

**Docs:** guide sections 3, 4, 6, 10, 19, 20, 23 and 26 updated, with four new pictures.

**Compatibility:** no change to the jobs file format. New job/step field `exact_match`
(default on) and new settings (`marker_seconds`, `show_similar`, `tray_status`, `col_widths`)
get their defaults automatically.

## 4.5 - Workflows, macro recording and security hardening

> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

**New**
- **Record a macro** (⏺ Record, Ctrl+Alt+R): clicks, double clicks, drags, scrolling, mouse
  movement (simplified), typing (Backspace fixes the text), key combinations, Shift/Ctrl-held
  clicks and pauses become editable steps; optional picture of each clicked spot. Red recording
  bar with Pause / Stop / Cancel and hotkeys.
- **Timeline editor** for steps: add after the selection, duplicate, move several, indented
  blocks, make waits shorter/longer, remove short waits or mouse moves, step names, "At" times.
- **Paste text** step (clipboard + Ctrl+V / Shift+Insert / Ctrl+Shift+V) that puts your
  clipboard back and keeps pasted text out of Windows clipboard history; **Type text** stays.
- **Workflows:** If / Otherwise / End (picture, window or variable), Repeat N times or until a
  condition (always limited), **variables** (`{date}`, `{time}`, `{loop}`… and your own, optionally
  remembered between runs), reusable **step groups**, per-step **retries** and **stop or
  continue if it fails**, plus Scroll, Drag, Move, Mouse button down/up and Hold key steps.
- **Steps-only jobs** (no main click), e.g. for recordings or watchers that run steps.
- **Dry run** of a job's steps (no clicks) and **Step through** (one step at a time, with why
  each target was chosen and ⚠ careful steps).
- **One input queue:** jobs take turns using the mouse and keyboard while **watchers keep
  watching**; a bar shows the running job and who's waiting; **priorities**, optional "let other
  jobs click in between", and warnings when two running jobs use the same window or spot.
- **Emergency stop** (Ctrl+Alt+X, ☰ Menu, tray): ends the running job, drops queued clicks,
  releases held keys and buttons, pauses everything. Pause all now also pauses a running job
  between steps.
- **Run history** (searchable; never contains typed text) and optional local **screen video of
  runs** (off by default, per job, visible indicator, presets, hidden areas, blacked out while
  typing, size/age clean-up, disk-space checks, built-in player from any step). Optional
  **failure screenshots**.
- **Who Clickue helps** / industries and workflows in the README and guide; guide updated for
  every new feature, with new pictures.

**Security and safety**
- Phone alerts only go to Discord webhooks / api.telegram.org over HTTPS with certificate
  checks; redirects aren't followed; short timeouts, response limit and rate limit. URLs and
  tokens are validated, masked, redacted from logs, **removed from backups** and never exported;
  optional encryption with your Windows account (DPAPI).
- Imports are validated (size, schema, types, ranges, pictures, steps) and arrive **stopped**,
  with a summary of keyboard steps; restores are validated too. **Secret** Type/Paste text is
  encrypted, hidden and never exported or logged.
- Held keys/buttons are always released; every wait, loop and run has a limit; a test click
  can no longer send input at the same time as a scheduled job.
- Uninstall asks to keep or delete your data, only deletes a verified Clickue data folder, uses
  Windows' uninstaller for installed copies, and the installer's uninstaller now also removes
  the start-with-Windows entry Clickue created. The installer shows a short notice first.
- Build: least-privilege workflow (write access only for the release job), actions pinned to
  commits, tests + `pip-audit` + `bandit` before building, SHA-256 checksums with each release.
  Dependency minimums raised past known vulnerabilities (Pillow ≥ 12.3.0).
- New **SECURITY.md** and the AI-assistance disclosure in the README, guides, app, installer and
  release notes.

**Compatibility:** jobs from 4.4 and earlier keep working; a *before-upgrade-4.5* backup is saved
before they're stored in the new format (`schema: 2`). Not yet available (planned): OCR text
targets, Windows UI Automation, browser elements, isolated parallel workers.

## 4.4 - The complete guide
- New **[complete guide](docs/GUIDE.md)**: every feature, setting and default explained, with
  scenarios, six step-by-step recipes, troubleshooting, an FAQ and 16 example pictures.
- **☰ Menu → Complete guide (online)** opens it in your browser. **Help & shortcuts** has an
  **Open the complete guide** button, and mentions click chains.

## 4.3 - Click chains
- New step **Wait for a picture**: pause a job's steps until a picture **appears** (and
  optionally **click it** where it appeared) or **goes away**, with a time limit
  (**stop the chain** or **continue anyway**). This lets one job react to the result of each
  click: click → wait for the next button → click it → wait for "Done" → …
- Shorter step buttons in the editor (+ Click, + Wait, + Wait for picture, + Type, + Keys).
- Each release is now announced in GitHub Discussions; feature-request and bug-report forms.

## 4.2
- **Asks before reusing old jobs.** The first start no longer imports *Scheduled AutoClicker*
  jobs silently; it asks. After a fresh install or reinstall, if jobs from before are found,
  it asks whether to keep them or **start fresh** (a backup is saved first).
- The uninstaller asks whether to also delete your jobs, settings, history and backups.

## 4.1
- Developer guide, AI-session notes (CLAUDE.md) and the test suites added to the repository.
- README: "Why would I need Clickue?" use cases.
- **Portable mode:** a `portable.txt` file next to the program keeps all data in a
  `ClickueData` folder beside it.
- Installer for one user or all users; release builds made automatically.

## 4.0 - Clickue
- Renamed from *Scheduled AutoClicker* to **Clickue**, with a new logo. Existing data is
  imported automatically.
- ☰ menu and tabbed **Preferences**.
- Watchers can click when a picture **appears**, optionally clicking the picture itself, and
  can search **only an area**.
- **Active hours and days**, **stop after N clicks**, **stop at** a date and time.
- **Multi-step jobs:** click more spots, wait, type text, press keys.
- **Global hotkeys** (pause all, show/hide).
- **Phone alerts** through Discord and Telegram.
- **Daily backups** with restore, **undo delete**, **click history** with per-job stats and
  CSV export.

## 3.x
- Pause and resume individual jobs.
- Random delays can be turned off; the watcher's after-click wait can be turned off.
- Watchers re-click immediately while a picture stays gone (when "click once" is off).
- Clearer messages when "click only once" holds back a click.

## 2.x
- Screen watchers (click when a picture disappears), with flicker protection and strict
  colour-aware matching.
- Finding the spot by its picture (multi-scale), plus "inside a window" targets.
- Separate Tests window with dry runs, scheduled tests and test history.
- Tray icon, dark mode, responsive layout, draggable dividers, remembered window sizes.
- Log rotation, data folder in `%APPDATA%`, import/export, in-app uninstall.

## 1.0
- First version: scheduled clicks with a random delay after each scheduled time.
