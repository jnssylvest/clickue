<p align="center">
  <img src="assets/logo-128.png" alt="Clickue logo" width="112">
</p>

<h1 align="center">Clickue</h1>

<p align="center">
  <b>Scheduled clicks and screen watchers that click for you.</b><br>
  A lightweight Windows tray app that clicks the right spot at the right time, or the moment
  something on your screen changes, even when windows move or the screen size changes.
</p>

<p align="center">
  <a href="../../releases/latest">Download</a> ·
  <a href="#why-would-i-need-clickue">Why use it?</a> ·
  <a href="FEATURES.md">All features</a> ·
  <a href="docs/USER_GUIDE.md">User guide</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

> [!WARNING]
> **Clickue clicks, types and presses keys on your behalf while you're not watching.**
> Read [Responsible use & warnings](#%EF%B8%8F-responsible-use--warnings) before you set up
> your first job, and always try a job with the built-in **Tests** before you rely on it.

## What is Clickue?

Clickue automates the repetitive clicks you'd otherwise have to sit and do yourself, such as
pressing a refresh button every few hours, confirming a dialog that keeps popping up, or
re-connecting something whenever it drops.

It does that in two ways:

| | **Scheduled clicks** | **Screen watchers** |
|---|---|---|
| **When it clicks** | On a timetable, e.g. every 8 hours, with an optional random delay so the clicks don't land on the exact same second | When a picture on your screen **disappears** (e.g. a "Connected" badge) or **appears** (e.g. a "Session expired" dialog) |
| **Good for** | Regular refreshes, keep-alives, routine actions | Reacting to changes, recovering from errors, dismissing pop-ups |

Unlike a classic macro recorder, Clickue doesn't blindly click saved pixel coordinates.
**It remembers what the spot looks like** and finds it again before every click. It still
hits the right button when a window has moved, the screen resolution changed, or display
scaling is different (for example when switching between a remote-desktop session and the
console).

It runs quietly in the system tray, uses no internet connection unless you turn on phone
alerts, and keeps all of its data on your own computer.

## Why would I need Clickue?

Because some apps and web pages need a click now and then, or every time something changes,
and you shouldn't have to sit there to do it. Clickue is for the moments when you'd otherwise
be thinking *"I'll just keep an eye on it and click when…"*.

### Keep things fresh and alive
- **Dashboards and status pages that don't refresh on their own.** Press their Refresh
  button every few minutes or hours, so whatever is on screen is always current.
- **Sessions that time out.** Click a harmless spot (or a "Stay signed in" / "Keep working"
  button) on a schedule so a web app, remote tool or console doesn't log you out.
- **Wall screens and kiosks.** Keep a shared display cycling, refreshed and in the right view
  without anyone touching it.

### React when something changes on screen
- **"Session expired" / "Reconnect" / "Try again" dialogs.** A watcher that clicks the
  button when the dialog *appears* gets things running again by itself.
- **A status badge, icon or "Connected" indicator that goes away.** A watcher that clicks
  *Reconnect* (or *Retry*, *Refresh*) when the picture *disappears*.
- **Recurring pop-ups and prompts** that block a long-running task until someone clicks OK.
- **Waiting for something to finish.** Click *Next* or *Continue* the moment a "Done" message
  or a button appears, instead of watching a progress bar.

### Take care of routine clicking
- **Recurring checks and confirmations.** Open a page, click through to the same screen and
  press the same buttons on a schedule, with **multi-step jobs** that click, wait, type and
  press keys.
- **Only during working hours.** Active hours and days keep it quiet at night and on weekends.
- **A fixed number of times.** "Stop after 20 clicks" or "stop on Friday at 18:00".

### Look after a remote or virtual machine
- Clickue runs inside the machine it automates, such as a VM or a remote desktop. It keeps
  working when you switch between connection methods with different screen sizes or display
  scaling, because it finds spots by their **picture**, not fixed pixel positions.
- **Phone alerts** (Discord / Telegram) tell you when a watcher had to step in, or when a click
  couldn't happen, so you know without logging in.

### Save your hands and attention
- Fewer repetitive clicks means less strain, and less need to babysit a screen. Set it up once,
  test it with **Dry run**, and get on with something else.

> Clickue isn't a game bot or a scraper. It's a careful, visible helper for clicks you'd
> otherwise do yourself. See [Responsible use & warnings](#%EF%B8%8F-responsible-use--warnings).

## Highlights

- 🎯 **Finds the spot by its picture.** Multi-scale image matching survives moved windows,
  different resolutions and 100–175 % display scaling.
- ⏱️ **Flexible scheduling.** Any interval, an optional random delay (down to the second), a
  fixed first time of day, and active hours and days (including overnight).
- 👁️ **Screen watchers.** Click when a picture appears or disappears. Search the whole screen
  or just an area, with flicker protection and "click once until it changes back".
- 🧩 **Multi-step jobs.** After the click, click other spots, wait, type text and press keys.
- 🧪 **Built-in tests.** Show the spot, test-click, check the picture, dry-run a watcher, or
  schedule a test for later and read the result when you're back.
- 🔔 **Alerts.** Tray notifications, plus optional Discord and Telegram messages to your phone.
- 🛡️ **Safety nets.** Waits until you stop using the mouse, refuses to click when its target
  is covered, retries or reports instead of clicking blindly, stops after N clicks or at a set
  time, and has global pause hotkeys.
- 💾 **Your data stays yours.** Daily automatic backups, undo delete, import/export, a click
  history with CSV export, and size-capped logs. No telemetry, no account.
- 🌓 **Modern, responsive UI.** Light and dark themes, resizable everything, keyboard
  shortcuts, and it remembers your window sizes.
- 📦 **Portable or installed.** Run it from a folder or USB stick, or install it for just you
  or for everyone on the PC.

➡️ **See the complete [feature list](FEATURES.md).**

<!--
## Screenshots
Add screenshots to docs/images/ (main.png, watcher.png, tests.png) and remove this comment:
| Main window | Screen watcher | Tests |
|---|---|---|
| ![Main window](docs/images/main.png) | ![Watcher editor](docs/images/watcher.png) | ![Tests](docs/images/tests.png) |
-->

## Download & install

Get the latest version from the [**Releases**](../../releases/latest) page.

| Package | Best for | How |
|---|---|---|
| **`Clickue-Setup-x.y.exe`** | Most people | Run it and choose **Only for me** (no admin needed) or **All users** (installs to Program Files). Adds Start-menu shortcuts and an uninstaller. |
| **`Clickue-Portable-x.y.zip`** | USB sticks, locked-down PCs, trying it out | Unzip anywhere and run `Clickue.exe`. The included `portable.txt` keeps all data in a `ClickueData` folder next to it, so nothing is written elsewhere. |
| **Source** | Developers | See [Run from source](#run-from-source). |

**Multiple users:** when installed for all users, every Windows account gets its own jobs,
settings and history (stored in that user's `%APPDATA%\Clickue`).

> [!NOTE]
> Windows SmartScreen may warn about a new, unsigned download (*"Windows protected your
> PC"*). Click **More info → Run anyway** if you trust the source. Clickue is open source, so
> you can read every line or build it yourself.

**Requirements:** Windows 10 or 11 (64-bit). Nothing else for the installer or portable
version.

## Quick start

1. Start Clickue. It opens its main window and adds an icon to the system tray.
2. **Scheduled click:** click **＋ New click** → **Pick on screen…** → point at the button within
   5 seconds → choose how often → **Save**.
3. **Screen watcher:** click **👁 New watcher** → **Draw box around picture…** → drag a box
   around something that should stay on screen → **Pick on screen…** for the button to click
   when it disappears → **Save**.
4. Open **🧪 Tests** and use **Show spot** / **Dry run** to confirm it found the right things.
5. Minimize Clickue to the tray. It keeps working in the background.

The [user guide](docs/USER_GUIDE.md) walks through every option.

## How it works (in short)

- When you pick a spot or draw a box, Clickue saves a small **picture** of that area.
- Before each click, it takes a screenshot and searches it for the picture at several sizes,
  checking the shape, a close-up of the exact spot and the colours. It only clicks when all
  of them agree, so a look-alike (say, a red badge where a green one used to be) isn't
  mistaken for the real thing.
- Clicks are real mouse events sent through Windows, the same as if you clicked yourself.
  That means the screen must be **unlocked and connected**: Windows blocks all clicking and
  screen capture on the lock screen or a disconnected remote session. Clickue detects this,
  waits and retries, and reports a missed click instead of clicking blindly.

## ⚠️ Responsible use & warnings

Clickue is a general-purpose automation tool. Please read this before using it.

- **You are responsible for what you automate.** Clickue does exactly what you set it up to
  do, unattended, possibly many times. A wrongly placed click can confirm, submit, delete,
  buy, sell or send something you didn't intend.
- **Test before you trust it.** Use **Show spot**, **Dry run** and **Test click now** after
  creating or changing a job, and again after changes to your screen, display scaling or the
  app you automate. Apps change their look, and a redesigned button may not be recognized.
- **Don't automate anything where a mistake would be costly** without a way to notice and
  undo it. Use **Stop after N clicks** and **Stop at** limits, keep **phone alerts** on for
  problems, and check the click history regularly.
- **Check the rules of what you automate.** Many websites, services and apps don't allow
  automated interaction in their terms of service. Following those rules, and any laws or
  workplace policies that apply, is up to you.
- **Keep your computer secure.** Clickue needs an unlocked session to click. Don't leave an
  unlocked computer where others can reach it. Protect remote access (RDP, VNC, virtual-
  machine consoles) with strong passwords and two-factor sign-in, and lock the computer you
  connect *from*.
- **Phone alert settings are private.** A Discord webhook URL or Telegram bot token lets
  anyone who has it post to your channel. Don't share your settings, backups or exported
  files with those filled in.
- **No warranty.** Clickue is provided "as is", without warranty of any kind (see
  [LICENSE](LICENSE)). The authors aren't liable for any loss or damage from its use.

## Privacy

- No telemetry, analytics, accounts or ads. Clickue never phones home.
- Everything (jobs, the pictures it saved, settings, logs, history, backups) stays in
  `%APPDATA%\Clickue` (or `ClickueData` in portable mode).
- The only network traffic happens if **you** turn on phone alerts, and then it goes only to
  the Discord or Telegram address you entered.
- Saved pictures are small crops around the spots you picked. They can contain whatever was on
  screen there, so treat backups and exports accordingly.

## Run from source

```bat
git clone https://github.com/<you>/clickue.git
cd clickue
pip install -r requirements.txt
pythonw src\clickue.py
```

Or double-click `scripts\Start Clickue.bat`, which installs the requirements the first time.
Python 3.10 or newer (64-bit) is recommended.

**Build the .exe yourself:** run `scripts\Build Clickue EXE.bat`. The [GitHub Actions
workflow](.github/workflows/build.yml) builds the portable zip and the installer
automatically for every release.

## FAQ

**Does it work while the screen is locked or my remote session is disconnected?**
No. Windows itself blocks this, for every app. Leave the session unlocked (hand an RDP
session over to the console instead of disconnecting) and lock the computer you connect from
instead. See the [user guide](docs/USER_GUIDE.md#locked-screens-and-remote-sessions).

**It clicked in the wrong place / says "picture not found".**
Re-pick the spot with some text or an icon nearby (plain areas look the same everywhere), or
choose a larger picture size. **Show spot** shows exactly where it would click.

**Will it grab my mouse while I'm working?**
By default it waits until you've been idle for 5 seconds, then puts the mouse back where it
was after clicking.

**I reinstalled it and my old jobs are still there.**
Your jobs live in your user folder, not in the program, so they survive a reinstall. After a
fresh install Clickue asks whether to keep them or start fresh (with a backup). To remove
everything, answer **Yes** when the uninstaller asks about deleting your data, or use
☰ Menu → **Uninstall…**.

**Where are my settings?** ☰ Menu → **Open data folder**.

**How do I stop everything at once?** Ctrl+Alt+P (global hotkey) or **Pause all**.

## For developers

The [developer guide](docs/DEVELOPER_GUIDE.md) covers the architecture, data model, design
decisions, tests and the release process. Run the tests in `tests/` before sending changes.

## Contributing

Bug reports and ideas are welcome. Please open an [issue](../../issues) with what you
expected, what happened, and the relevant lines from the log (☰ Menu → **Open log file**).
Remove anything private first.

## License

[MIT](LICENSE). Free to use, modify and share.
