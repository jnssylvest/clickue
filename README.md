<p align="center">
  <img src="assets/logo-128.png" alt="Clickue logo" width="112">
</p>

<h1 align="center">Clickue</h1>

<p align="center">
  <b>Scheduled clicks, screen watchers and recorded macros that click for you.</b><br>
  A lightweight, local-first Windows tray app that clicks the right spot at the right time, or
  the moment something on your screen changes, even when windows move or the screen size changes.
</p>

<p align="center">
  <a href="../../releases/latest">Download</a> ·
  <a href="#who-clickue-helps">Who it helps</a> ·
  <a href="FEATURES.md">All features</a> ·
  <a href="docs/GUIDE.md"><b>Complete guide</b></a> ·
  <a href="SECURITY.md">Security</a> ·
  <a href="CHANGELOG.md">Changelog</a> ·
  <a href="../../issues/new?template=feature_request.yml">Suggest a feature</a>
</p>

---

> [!IMPORTANT]
> **Clickue is vibe-coded and was developed with substantial AI assistance.** Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.
> More in [SECURITY.md](SECURITY.md).

> [!WARNING]
> **Clickue clicks, types and presses keys on your behalf while you're not watching.**
> Read [Responsible use & warnings](#%EF%B8%8F-responsible-use--warnings) before you set up
> your first job, and always try a job with **Dry run** or **Step through** before you rely on it.

## What is Clickue?

Clickue automates the repetitive clicks and keystrokes you'd otherwise have to sit and do
yourself, such as pressing a refresh button every few hours, confirming a dialog that keeps
popping up, or re-connecting something whenever it drops.

It does that in three ways:

| | **Scheduled clicks** | **Screen watchers** | **Recorded macros** |
|---|---|---|---|
| **When it runs** | On a timetable, e.g. every 8 hours, with an optional random delay | When a picture on your screen **disappears** (e.g. a "Connected" badge) or **appears** (e.g. a "Session expired" dialog) | Whenever you run them, or on a schedule / from a watcher like any other job |
| **Good for** | Regular refreshes, keep-alives, routine actions | Reacting to changes, recovering from errors, dismissing pop-ups | Repeating a routine you showed Clickue once, then edited |

Unlike a classic macro tool, Clickue doesn't have to click saved pixel coordinates blindly.
**It remembers what each spot looks like** and finds it again before every click. It still
hits the right button when a window has moved, the screen resolution changed, or display
scaling is different (for example when switching between a remote-desktop session and the
console). If it can't find the target, it doesn't click.

Jobs can do much more than one click: **steps** click other spots, wait, wait for a picture,
type or paste text, press keys, scroll and drag, and **If / Repeat / variables / step groups**
turn them into small, readable workflows with time limits and retries.

It runs quietly in the system tray, uses no internet connection unless you turn on phone
alerts, and keeps all of its data on your own computer.

## Who Clickue helps

Clickue is for repetitive work on a Windows screen where a person would otherwise click the same
things again and again. Some examples, all using features available today:

| Who | A repetitive screen task Clickue can take over |
|---|---|
| **QA and software testing** | Record a click-through of a test build, add *Wait for a picture* checks, and replay it after each build; **Dry run** and **Step through** show what each step finds before it clicks. |
| **IT operations and remote support** | A watcher clicks *Reconnect* when a remote console's "Connected" badge disappears, then sends a phone alert so you know it happened. |
| **Office and administrative work** | Each morning: open the report screen, click *Export*, wait for *Save*, **paste** a file name with today's `{date}`, and confirm. |
| **Manufacturing and laboratory workflows** | Press *Acknowledge* or *Next sample* in a vendor desktop app when its "Ready" indicator appears, only during active hours, with a run history (and optional video) of every run. |
| **Customer support and staff training** | Record a routine once, edit it into clear steps, and use **Step through** to show a new colleague what happens at each step and why. |
| **Accessibility and repetitive strain** | Replace long, repetitive clicking sequences with one recorded, checked macro, so fewer clicks need a hand on the mouse. |
| **Kiosks, dashboards and shared displays** | Refresh a wall dashboard every few minutes, keep it in the right view, and dismiss a "Session expired" dialog the moment it appears. |
| **E-commerce and content operations** | In an admin page you're allowed to automate, work through a review queue: click the first item, press *Approve*, wait for the confirmation, and **Repeat until** the "No more items" message appears, with a limit on how many it may do. |

Fuller, step-by-step recipes for each are in the guide:
[Industries and workflows](docs/GUIDE.md#22-industries-and-workflows).

> [!NOTE]
> These are examples, not promises. Clickue isn't certified for any regulated use and doesn't
> guarantee correctness or safety. Follow your workplace's policies and the terms of the
> programs and sites you automate, and keep a person in charge of anything important.
> **Not available yet** (planned): finding text on screen (OCR), Windows UI Automation
> controls, browser element targeting, and running jobs on separate, isolated desktops at the
> same time. See [Planned](FEATURES.md#planned-not-in-this-version).

Clickue isn't a game bot or a scraper, and it doesn't get around CAPTCHAs, sign-ins or other
security checks. See [Responsible use & warnings](#%EF%B8%8F-responsible-use--warnings).

## Highlights

- 🎯 **Finds the spot by its picture.** Multi-scale image matching survives moved windows,
  different resolutions and 100–175 % display scaling. Every step shows how its target is
  found, and never silently falls back to an unchecked position.
- ⏺️ **Record and edit macros.** Record your mouse and keyboard (clicks, double clicks, drags,
  scrolling, key combinations, typed text, pauses), then edit the steps on a timeline: rename,
  reorder, change delays, add waits, and turn raw coordinates into picture or window targets.
- 🧩 **Workflows.** If / Otherwise / End on a picture, a window or a variable; Repeat N times or
  until something happens (always with limits); variables such as `{date}` and counters;
  reusable **step groups**; per-step retries and "stop or continue if it fails".
- ⌨️ **Type or paste.** *Type text* presses each key; *Paste text* puts long, multi-line or
  any-language text in at once and then puts your clipboard back. Secret text can be protected
  with your Windows account and is never exported.
- 👁️ **Screen watchers.** Click (or run steps) when a picture appears or disappears. Search
  the whole screen or just an area, with flicker protection and "click once until it changes back".
  Match the exact picture (every pixel area checked), or let **part of the picture** be
  enough when something inside the box changes; every copy on screen is found. Zoom in up to
  24× with a pixel magnifier while drawing the box.
- 🖱️ **Moves like a person (optional).** Smooth, curved mouse movements to each click instead
  of jumps, per job, per step or for recorded macros.
- 🩺 **Honest status.** Hover a job to see what it's doing, any problem and what to do; the
  tray icon turns amber, green or red. Logs say what went wrong, every time.
- 🎨 **Your colours.** Change every colour of the app with a colour wheel or codes.
- ☑️ **Batch actions.** Tick jobs in the list to start, stop, pause, resume, duplicate or
  delete them together, or **Edit together** to change the same settings on all of them.
- 🎯 **Only the exact picture.** By default a similar-looking button is never clicked, even when
  the one you picked is scrolled out of view. Show spot can outline every similar picture so
  you can see what Clickue sees.
- 🧪 **Test before you trust.** Show spot, Test click, Check picture, **Dry run** (finds every
  target and checks every condition without clicking) and **Step through** (runs one step at a
  time and explains why it chose each target).
- 🖱️ **Status at a glance.** Point at the tray icon to see whether your jobs are healthy while
  Clickue is minimized.
- 🚦 **One mouse, many jobs.** Jobs take turns through one queue, watchers keep watching
  meanwhile, and a status bar shows what's running and what's waiting. Priorities, "let other
  jobs go first" and warnings when two jobs use the same window.
- 🎬 **Optional run videos and run history.** Record the screen during a job's run, locally,
  with a visible indicator, hidden areas, size presets and automatic cleanup; a searchable run
  history links each step to its moment in the video.
- 🔔 **Alerts.** Tray notifications, plus optional Discord and Telegram messages to your phone
  (HTTPS only, to those services only, rate-limited).
- 🛡️ **Safety nets.** Emergency-stop hotkey, Pause all (also pauses a running job between
  steps), waits until you stop using the mouse, refuses to click when its target is covered,
  releases held keys and buttons whenever a run ends, time limits on every wait and loop, and
  stops after N clicks or at a set time.
- 💾 **Your data stays yours.** Daily automatic backups (without your alert credentials), undo
  delete, validated import/export, a click history with CSV export, and size-capped logs.
  No telemetry, no account.
- 🌓 **Modern, responsive UI.** Light and dark themes, resizable everything, keyboard
  shortcuts, and it remembers your window sizes.
- 📦 **Portable or installed.** Run it from a folder or USB stick, or install it for just you
  or for everyone on the PC.

➡️ **See the complete [feature list](FEATURES.md).**

📖 **New to Clickue?** The [**complete guide**](docs/GUIDE.md) explains every feature with
step-by-step scenarios, recipes and example pictures. It's also one click away inside the app:
**☰ Menu → Complete guide (online)**.

### In pictures

| A watcher reacts to a change | A recorded macro, ready to edit |
|---|---|
| [![Watcher: when the Connected badge disappears, click Reconnect](docs/images/guide/watcher-disappears.png)](docs/GUIDE.md#6-screen-watchers) | [![Recording bar and the recorded steps on the timeline](docs/images/guide/record-macro.png)](docs/GUIDE.md#9-recording-a-macro) |

*Illustrations from the [complete guide](docs/GUIDE.md), using an invented example app.*

## Download & install

Get the latest version from the [**Releases**](../../releases/latest) page. Before you
download, please read the AI-assistance note at the top of this page and
[SECURITY.md](SECURITY.md).

| Package | Best for | How |
|---|---|---|
| **`Clickue-Setup-x.y.exe`** | Most people | Run it and choose **Only for me** (no admin needed) or **All users** (installs to Program Files). Adds Start-menu shortcuts and an uninstaller. |
| **`Clickue-Portable-x.y.zip`** | USB sticks, locked-down PCs, trying it out | Unzip anywhere and run `Clickue.exe`. The included `portable.txt` keeps all data in a `ClickueData` folder next to it, so nothing is written elsewhere. |
| **`SHA256SUMS.txt`** | Checking your download | Compare with `Get-FileHash <file>` in PowerShell. |
| **Source** | Developers | See [Run from source](#run-from-source). |

**Multiple users:** when installed for all users, every Windows account gets its own jobs,
settings and history (stored in that user's `%APPDATA%\Clickue`).

> [!NOTE]
> Windows SmartScreen may warn about a new, unsigned download (*"Windows protected your
> PC"*). Only click **More info → Run anyway** if you downloaded it from this repository's
> Releases page. Clickue is open source, so you can read every line or build it yourself.

**Requirements:** Windows 10 or 11 (64-bit). Nothing else for the installer or portable
version. Clickue is Windows-only.

**Uninstalling:** Windows Settings → Apps → Clickue, or ☰ Menu → **Uninstall…** in Clickue.
Both remove the program, its shortcuts and its start-with-Windows entry, and **ask** whether to
keep or delete your jobs and other data. See the guide's
[Install, portable and uninstall](docs/GUIDE.md#25-install-portable-and-uninstall) section for exactly
what is removed and what stays.

## Quick start

1. Start Clickue. It opens its main window and adds an icon to the system tray.
2. **Scheduled click:** click **＋ New click** → **Pick on screen…** → point at the button within
   5 seconds → choose how often → **Save**.
3. **Screen watcher:** click **👁 New watcher** → **Draw box around picture…** → drag a box
   around something that should stay on screen → **Pick on screen…** for the button to click
   when it disappears → **Save**.
4. **Recorded macro:** click **⏺ Record** → **Start recording** → do the task once → **Stop** on
   the red bar → check the steps → **Save**.
5. Open **🧪 Tests**, or use **Dry run** / **Step through** in the editor, to confirm it found
   the right things.
6. Minimize Clickue to the tray. It keeps working in the background. **Ctrl+Alt+X** stops
   everything at once.

The [quick start guide](docs/USER_GUIDE.md) covers the basics; the
[**complete guide**](docs/GUIDE.md) explains every option with examples and pictures.

## How it works (in short)

- When you pick a spot or draw a box, Clickue saves a small **picture** of that area.
- Before each click, it takes a screenshot and searches it for the picture at several sizes,
  checking the shape, a close-up of the exact spot and the colours. It only clicks when all
  of them agree, so a look-alike (say, a red badge where a green one used to be, or a
  *Reload* button where *Refresh* used to be) isn't mistaken for the real thing.
- Clicks and keystrokes are real input sent through Windows, the same as if you did them
  yourself. Windows has **one mouse and one keyboard focus per desktop**, so Clickue runs one
  job at a time; it can't run several "virtual mice" on the same desktop. Watchers keep looking
  at the screen while another job is running.
- The screen must be **unlocked and connected**: Windows blocks all clicking and screen capture
  on the lock screen or a disconnected remote session. Clickue detects this, waits and retries,
  and reports a missed click instead of clicking blindly.

## ⚠️ Responsible use & warnings

Clickue is a general-purpose automation tool. Please read this before using it.

- **It's AI-assisted software.** Clickue is vibe-coded and was developed with substantial AI
  assistance. Caution was taken, but that doesn't guarantee it's bug-free or secure. It hasn't
  been professionally audited or certified.
- **You are responsible for what you automate.** Clickue does exactly what you set it up to
  do, unattended, possibly many times. A wrongly placed click or keystroke can confirm, submit,
  delete, buy, sell or send something you didn't intend.
- **Test before you trust it.** Use **Dry run**, **Step through**, **Show spot** and **Test
  click now** after creating or changing a job, and again after changes to your screen, display
  scaling or the app you automate. Mark steps that send, delete or buy as **⚠ careful** so
  Step through always stops before them.
- **Don't run consequential actions unattended** without a way to notice and undo them. Use
  **Stop after N clicks** / **Stop at** limits, time limits on runs, phone alerts for problems,
  and the run history.
- **Check the rules of what you automate.** Many websites, services and apps don't allow
  automated interaction in their terms of service. Following those rules, and any laws or
  workplace policies that apply, is up to you. Clickue isn't for games, scraping, or getting
  around CAPTCHAs, sign-ins or other security controls.
- **Recording captures what you type.** Don't type passwords while recording a macro; add them
  afterwards as a **Secret** paste step.
- **Keep your computer secure.** Clickue needs an unlocked session to click. Don't leave an
  unlocked computer where others can reach it. Protect remote access (RDP, VNC, virtual-
  machine consoles) with strong passwords and two-factor sign-in, and lock the computer you
  connect *from*.
- **Phone alert settings are secrets.** A Discord webhook URL or Telegram bot token lets anyone
  who has it post to your channel. Clickue keeps them out of logs, backups and exports, and can
  encrypt them with your Windows account (Preferences → Phone alerts).
- **Only import jobs from people you trust.** Imported jobs are checked, cleaned and arrive
  **stopped**, and Clickue tells you which ones type or press keys, but review them with Dry run
  before starting them.
- **No warranty.** Clickue is provided "as is", without warranty of any kind (see
  [LICENSE](LICENSE)). The authors aren't liable for any loss or damage from its use.

## Privacy

- No telemetry, analytics, accounts or ads. Clickue never phones home.
- Everything (jobs, the pictures it saved, settings, logs, history, backups, run history,
  failure screenshots) stays in `%APPDATA%\Clickue` (or `ClickueData` in portable mode).
- **Screen videos** are off unless you turn them on and ask for them per job. They're recorded
  only while that job runs, with a red indicator on screen, saved locally (never uploaded), and
  deleted after the time / size you choose. You can black out areas of the screen, and the video
  is blacked out while Clickue types or pastes text.
- Typed and pasted text is never written to the log, click history, run history or error
  messages. Text you mark as **Secret** is encrypted with your Windows account and never exported.
- The only network traffic happens if **you** turn on phone alerts, and then it goes only to
  discord.com or api.telegram.org over HTTPS.
- Saved pictures are small crops around the spots you picked. They can contain whatever was on
  screen there, so treat backups and exports accordingly.

## Run from source

```bat
git clone https://github.com/jnssylvest/clickue.git
cd clickue
pip install -r requirements.txt
pythonw src\clickue.py
```

Or double-click `scripts\Start Clickue.bat`, which installs (or updates) the requirements the
first time. Python 3.10 or newer (64-bit) is recommended. Running from source behaves exactly
like the installed and portable versions (it's the same file).

**Build the .exe yourself:** run `scripts\Build Clickue EXE.bat`. The [GitHub Actions
workflow](.github/workflows/build.yml) runs the tests and security checks, then builds the
portable zip and the installer for every release.

## FAQ

**Can Clickue run several mice / jobs at the same time?**
Not on one Windows desktop: Windows has a single mouse pointer and keyboard focus, so two jobs
clicking at once would fight over them. Clickue runs one job at a time and shows the others as
"waiting their turn"; watchers keep watching meanwhile. Running jobs side by side on genuinely
separate desktops (e.g. several VMs) is planned.

**Should I use Type text or Paste text?**
Paste for long, multi-line or non-English text (fast and exact; your clipboard is put back).
Type for short text, or for fields that block pasting. Both go to whatever has keyboard focus,
so add a click on the field first.

**Does it work while the screen is locked or my remote session is disconnected?**
No. Windows itself blocks this, for every app. Leave the session unlocked (hand an RDP
session over to the console instead of disconnecting) and lock the computer you connect from
instead. See the [guide](docs/GUIDE.md#18-locked-screens-remote-desktop-and-virtual-machines).

**It clicked in the wrong place / says "picture not found".**
Re-pick the spot with some text or an icon nearby (plain areas look the same everywhere), or
choose a larger picture size. Keep **Only the exact picture** ticked (the default) so look-alikes
are never clicked. **Show spot** (optionally with every similar picture outlined) and **Step
through** show exactly where it would click.

**Will it grab my mouse while I'm working?**
By default it waits until you've been idle for 5 seconds, then puts the mouse back where it
was after clicking.

**How do I stop everything at once?**
**Ctrl+Alt+X** (emergency stop: ends the running job, lets go of held keys, pauses all), or
**Ctrl+Alt+P** / **Pause all**. Both hotkeys can be changed in Preferences → Hotkeys.

**I reinstalled it and my old jobs are still there.**
Your jobs live in your user folder, not in the program, so they survive a reinstall. After a
fresh install Clickue asks whether to keep them or start fresh (with a backup). To remove
everything, answer **Yes** when the uninstaller asks about deleting your data.

**Where are my settings?** ☰ Menu → **Open data folder**.

## For developers

The [developer guide](docs/DEVELOPER_GUIDE.md) covers the architecture, data model, the
workflow engine, target adapters, design decisions, tests and the release process. Run the
tests in `tests/` before sending changes. Security reports: see [SECURITY.md](SECURITY.md).

## Ideas, feature requests & bugs

Have an idea that would make Clickue more useful? We'd love to hear it.

- 💡 **[Suggest a feature](../../issues/new?template=feature_request.yml)**: a short form
  asks what you'd like and why. If someone already suggested it, give it a 👍 instead.
- 💬 **[Discussions](../../discussions)**: talk an idea through, share how you use Clickue, or
  ask a question.
- 🐞 **[Report a bug](../../issues/new?template=bug_report.yml)**: include the steps, your
  version (☰ Menu → About) and the relevant log lines (☰ Menu → **Open log file**). Remove
  anything private first, and **never** paste webhook URLs, bot tokens or screenshots that show them.

See [CONTRIBUTING.md](CONTRIBUTING.md) for details, including how to contribute code.

## License

[MIT](LICENSE). Free to use, modify and share.
