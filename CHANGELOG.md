# Changelog

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
