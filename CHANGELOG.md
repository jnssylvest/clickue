# Changelog

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
