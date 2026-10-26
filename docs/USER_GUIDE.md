# Clickue quick start guide

← [README](../README.md) · [All features](../FEATURES.md) · [**Complete guide**](GUIDE.md) · [Security](../SECURITY.md)

> [!IMPORTANT]
> Clickue is vibe-coded and was developed with substantial AI assistance. Caution was taken
> during development, but AI-assisted development does not guarantee bug-free or secure
> software. Review the source and use normal precautions. Test automations safely, protect
> notification credentials, and avoid unattended use for consequential actions.

> [!TIP]
> This page is the short version. The [**complete guide**](GUIDE.md) explains every feature in
> detail, with scenarios, recipes and example pictures. In the app: **☰ Menu → Complete guide
> (online)**.

1. [The main window](#the-main-window)
2. [Your first scheduled click](#your-first-scheduled-click)
3. [Your first screen watcher](#your-first-screen-watcher)
4. [Where to click: picture, window or position](#where-to-click-picture-window-or-position)
5. [When it may run: hours and limits](#when-it-may-run-hours-and-limits)
6. [Steps after the click](#steps-after-the-click)
7. [Recording a macro](#recording-a-macro)
8. [Testing a job](#testing-a-job)
9. [Pausing, stopping and hotkeys](#pausing-stopping-and-hotkeys)
10. [Phone alerts](#phone-alerts)
11. [History, run history, videos and backups](#history-run-history-videos-and-backups)
12. [Preferences](#preferences)
13. [Locked screens and remote sessions](#locked-screens-and-remote-sessions)
14. [Troubleshooting](#troubleshooting)

---

## Updates

When a new version is out, a bar appears above the job list: **⬆ Upgrade now…** downloads it
from GitHub, checks it and installs it; your jobs and settings are kept. **Later** or **Skip
this version** hide it. ☰ Menu → **Check for updates…** looks right away. Don't want Clickue to
go online for this? Turn off **Preferences → General → Check for new versions**.

## The main window

- **Summary cards** (top): the next click and countdown, active jobs, clicks today, and whether
  the screen is available. Collapse them with **▴ Summary**.
- **Toolbar:** New click, New watcher, Edit, Duplicate, Delete, Start/Stop, Pause, Pause all,
  Tests, Record, Import, Export. Buttons that don't fit go into **More ▾**.
- **Running bar:** while a job runs (or others wait their turn), a bar above the list shows
  which, with **Stop this run**.
- **Job list:** one row per job. The filter (All / Scheduled clicks / Screen watchers) also
  picks the columns, so each kind of job shows what matters for it; columns fit their text.
  Drag the divider above Activity (or ▲ / ▼) to make the list or Activity taller. Double-click to edit; right-click for everything else. Use the filter above
  it to show all jobs, only scheduled clicks or only watchers.
- **Hover over a job** to see how it's doing, any problem and what to do. A watcher that
  can't see its picture shows **⚠ Can't watch**. The **summary** at the top follows the
  filter; **⟳ Refresh** (F5) makes watchers look right away. Jobs with steps have a ▸ to show
  their steps.
- **Tick boxes:** tick jobs at the start of their rows (or press **X**; the heading box ticks
  all). A bar appears to **Start, Stop, Pause, Resume, Duplicate or Delete** them together, or
  **Edit together…** to change the same settings on all of them at once (only the settings
  you tick are changed).
- **Activity:** a live, colour-coded log. Filter it to *Clicks* or *Problems* or type in the
  🔍 box; click a place like *(878, 243)* to see it on screen; right-click to copy. It keeps
  its lines across restarts. **Clear view** hides lines for now, **Delete log…** removes them
  for good; ⟳ Refresh and newest/oldest first are there too. Every log in the app can be
  copied (right-click, Ctrl+C), filtered, sorted, refreshed, cleared from view and deleted the
  same way. Preferences → Data & backups → *How much to log*: Quiet / Normal / Detailed.
- **☰ Menu:** record a macro, step groups, run history & videos, stop everything now,
  import/export, backups, click-history export, preferences, data folder, log, the complete
  guide (online), help, about, uninstall, exit.

Drag the divider between the list and Activity to give either more room.

## Your first scheduled click

1. Click **＋ New click** (Ctrl+N) and give it a name.
2. Click **◎ Pick on screen…**. The app hides and a countdown appears. Point at the button
   within 5 seconds. If the countdown box is in the way, rest your mouse near it and it
   jumps aside, or drag it. Changed your mind? Press **Esc** or click **✕ Cancel**.
3. Under **Schedule**, set **Scheduled every** (e.g. 8 h).
4. Leave **Add a random delay** on to vary the time (e.g. 10 s to 15 min after each scheduled
   time), or turn it off for exact timing.
5. Optionally set a **First scheduled time** (24 h, e.g. 08:00).
6. Leave **Start this schedule when I save** ticked and click **Save**.

The row shows the next click time and counts down. Hover over Activity to follow what happens.

## Your first screen watcher

A watcher looks at the screen every so often and clicks when something changes.

1. Click **👁 New watcher** (Ctrl+Shift+N).
2. Choose **Click when the picture disappears** or **when the picture appears**.
3. Click **▢ Draw box around picture…**. The screen freezes; drag a box around the picture
   to watch (something distinctive, with text or an icon), then release.
   Small picture? Turn the **mouse wheel** to zoom in (up to 24×); the magnifier shows the
   exact pixels. Draw it around something that **doesn't change**. If something inside the box changes (a
   number, a time), Clickue warns you right after drawing.
4. Optional: **Search only an area** → **Draw area…** to limit where it looks.
   **Match:** keep **the exact picture**, or choose **part of the picture is enough** (e.g.
   75 %) when the box has to include something that changes.
5. Under **Button to click…**, **Pick on screen…** the button. For "appears" watchers you can
   instead tick **Click the picture itself**.
6. Set **Check every** (e.g. 30 s) and **Click when missing/showing for** (e.g. 2 checks in a
   row, to ignore brief flickers).
7. **Click only once each time it disappears** (on by default): after a click it waits for
   the picture to come back before it will click again. Turn it off to keep clicking for as
   long as the picture stays gone.
8. Optional: a **random delay** before clicking, and a **wait after each click** before it
   looks again (useful when "click once" is off and the app needs a moment to recover).
9. **Check now** and **Dry run** confirm everything is found. Then **Save**.

> [!TIP]
> While the Clickue window is open on screen, a *missing* picture isn't counted (the window
> might be covering it). Minimize Clickue or send it to the tray when you're done.

## Where to click: picture, window or position

When you pick a spot, Clickue saves three things and uses them in this order:

1. **Its picture** (recommended, on by default). Found again anywhere on screen and at any
   size. Choose **Small / Medium / Large**; bigger is more unique but slower. If it can't be
   found: **Wait and retry** (safe) or **Click the saved position**.
2. **Inside a window.** Used when you picked inside an app window. Follows that window when
   it moves; optionally brings it to the front and scales with its size. Edit **Window title
   contains** if the app's title changes (keep only the part that stays the same).
3. **Fixed screen position.** The exact pixel. Can scale with the screen resolution.

**Only the exact picture** (on by default) makes sure a similar-looking button is never
clicked: if the one you picked isn't on screen, nothing is clicked and the job tries again.

**Show spot** always shows where it would click *right now*, and how it found it. To see
every similar picture too, turn on **Preferences → Clicking → Also point out every similar
picture**; the same tab sets how long the marker stays (5 s by default).

**Tip:** while Clickue is minimized, point at its **tray icon** to see whether your jobs are
running fine; right-click it → **Job status** for every job.

## When it may run: hours and limits

In any job's editor, under **When it may run**:

- **Only run during set hours and days.** E.g. 08:00–22:00 Mon–Fri. Overnight ranges like
  22:00–06:00 work, and the same time twice means all day. For scheduled clicks, choose what
  happens when a click comes due outside the hours: **Wait until the hours start, then
  click**, or **Skip that click**. Watchers simply don't look outside the hours.
- **Stop after N clicks**, counted from when the job is (re)started.
- **Stop at** a date and time (`YYYY-MM-DD HH:MM`).

A job that reaches a limit stops, shows *Finished*, and can send a phone alert.

## Steps after the click

Under **Steps**, add steps that run in order right after the main click. Untick **Start with a
click on this spot** for a job that only runs its steps. **＋ Add step ▾** offers:

| Step | What it does |
|---|---|
| **Click a spot** | Pick on screen; found by its picture (checked), inside a window, or at a fixed position |
| **Wait** | e.g. 3 s, or a random 3–5 s |
| **Wait for a picture** | Waits until a picture **appears** (optionally **clicks it**) or **goes away**, up to a time limit; then stops the chain or continues |
| **Type text** | Presses one key per character into whatever has focus; a new line presses Enter |
| **Paste text** | Puts the text on the clipboard, presses Ctrl+V, puts your clipboard back. Best for long, multi-line or any-language text |
| **Press keys** | e.g. `Enter`, `Tab`, `Ctrl+S`, `Alt+F4`, `Ctrl+Shift+S`, `F5`, arrows |
| **If … Otherwise … End** | Runs steps only when a picture is (not) showing, a window is (not) open, or a variable has a value |
| **Repeat … End** | N times, or until a condition is true (always with limits) |
| **Set a variable** | E.g. a counter; use it as `{count}` in text. Built in: `{date}`, `{time}`, `{loop}`… |
| **Use a step group** | Steps saved once (☰ Menu → Step groups) and reused in many jobs |
| **Scroll, Drag, Move the mouse, Mouse button down/up, Hold a key** | For recorded or hand-made routines |

Every step can **retry** a few times, and either **stop** the run or **continue** if it still
fails. Mark steps that send, delete or buy as **⚠ careful**.

**Type or paste?** Both go to whatever has keyboard focus, so add a **Click a spot** on the
field first. Paste is faster and exact; Type works where pasting is blocked. Tick **Secret** for
passwords: they're encrypted with your Windows account and never exported or logged.

Example: *click the search box → type a name → press Enter → wait 2 s → click the first
result.* If a step fails (e.g. its spot can't be found), the run stops (unless that step is
set to continue) and it's reported in Activity, the click history and the run history.

### Click chains: react to each click

Fixed waits are guesses: too short and the next click lands before the app is ready, too long
and time is wasted. **Wait for a picture** waits for the actual result instead:

1. Main click: **Refresh**.
2. **Wait for a picture** → draw a box around the **Export** button → *until it appears* →
   *then click it* → up to 60 s → *stop the chain*.
3. **Wait for a picture** → the **Save** button → *appears* → *click it*.
4. **Wait for a picture** → the "Download complete" message → *appears* (no click).

Draw each picture while that screen is showing (open the app to that state first). Start the
chain on a schedule, or make the job a **screen watcher** so the chain starts when something
changes. Only one job clicks at a time: while a chain waits, other jobs wait their turn
(watchers keep watching). Keep the time limits sensible.

## Recording a macro

1. Click **⏺ Record** (or press **Ctrl+Alt+R** anywhere) → **Start recording**.
2. Do the routine once. A red bar shows that you're recording (**Pause**, **Stop**, **✕**
   cancel).
3. **Stop**: the steps open in a new job (not started yet). Remove what you don't need, give
   clicks without a picture one (**Picture of this spot now**), and replace guessed waits with
   **Wait for a picture**.
4. **Dry run**, then **Step through…**, then set a schedule and **Save**.

> [!WARNING]
> Everything you type while recording is recorded, including passwords. Add passwords
> afterwards as a **Secret** paste step.

## Testing a job

Open **🧪 Tests** (Ctrl+T, or right-click a job → **Open Tests…**). Pick the job at the top.
The whole app hides during each test and comes back with the result.

| Test | Does |
|---|---|
| **Show spot** | Moves the mouse to the spot and marks it. No click |
| **Test click now** | One real click, runs the extra steps too; schedule unchanged |
| **Schedule test click…** | One click X minutes from now (e.g. after you disconnect) |
| **Check picture** | Is the watched picture on screen / in its area? |
| **Dry run** | Marks the picture, then the button, and says whether it would click. No click |
| **Schedule watcher test…** | Runs the watcher check later in the background; optionally clicks |

Every result goes into the **Test history** (this job or all jobs). Click a line for details.

For jobs with steps, the editor has two more buttons:

- **Dry run** goes through every step without clicking or typing and lists what would happen
  (is each target there? is each condition true?).
- **Step through…** runs the job for real, one step at a time, showing what comes next, why
  that target was chosen, and where it will click. It always stops before **⚠ careful** steps.

## Pausing, stopping and hotkeys

- **Pause** (or **P**): keeps the job's schedule but doesn't click until you resume. A click
  that came due while paused is skipped, not fired the moment you resume.
- **Stop**: turns the job off and clears its schedule.
- **Pause all** (Ctrl+P, the tray menu, or **Ctrl+Alt+P** from anywhere). A job in the middle
  of its steps pauses before its next step.
- **Emergency stop** from anywhere: **Ctrl+Alt+X**. Ends the running job, drops queued clicks,
  lets go of held keys and buttons, and pauses everything.
- **Show / hide Clickue** from anywhere: **Ctrl+Alt+K**. Recording: **Ctrl+Alt+R** start/stop,
  **Ctrl+Alt+U** pause/resume.
- Change or turn off the global hotkeys in **Preferences → Hotkeys**.

## Phone alerts

**Preferences → Phone alerts**, tick **Send alerts to my phone**, then set up one or both:

- **Discord:** in a server you own, open *Channel settings → Integrations → Webhooks → New
  webhook → Copy webhook URL*, and paste it in.
- **Telegram:** message **@BotFather**, create a bot and paste its **token**. Send your new
  bot any message, then get your **chat id** (for example from @userinfobot) and paste it.

Choose which events send alerts and click **Send a test alert**. Alerts need internet access
from the computer running Clickue, and go only to Discord or Telegram over HTTPS. Keep the
webhook URL and bot token private: Clickue masks them, keeps them out of logs, backups and
exports, and can encrypt them with your Windows account (**Protect them with my Windows
account**).

## History, run history, videos and backups

- **Stats:** right-click a job → **Stats & click history…** shows totals, today, the last 7
  days, problems and recent activity. You can export that job's history.
- **Export click history (CSV):** ☰ Menu. Opens in Excel or Google Sheets.
- **Run history:** ☰ Menu → **Run history & videos…** lists every run and its steps (never the
  text typed or pasted). Searchable.
- **Screen videos (optional, off by default):** turn them on in **Preferences → Recording &
  video**, then tick **Record the screen while it runs** in a job's **Run options**. Videos are
  only made while that job runs, with a red indicator, stay on your computer, and are deleted
  after 14 days or 5 GB (adjustable). Play one from any step in the run history.
- **Backups:** ☰ Menu → **Backups…**. One is made automatically every day (keeps 14). **Back
  up now**, or **Restore…** to replace or add jobs (your current jobs are backed up first).
- **Undo delete:** right after deleting, click **Undo** or press Ctrl+Z.
- **Import / Export** jobs to share them between computers. Imported jobs are checked and
  arrive **stopped**; review them first. Secret text isn't exported.
- **Reinstalling:** your jobs are kept in your user folder. After a fresh install, Clickue asks
  whether to keep them or start fresh (it saves a backup first). When uninstalling, choose
  whether to delete your data as well (both Windows' uninstaller and ☰ Menu → Uninstall ask).

## Preferences

**☰ Menu → Preferences** (Ctrl+,):

| Tab | Settings |
|---|---|
| General | Tray behaviour, notifications, start with Windows, start minimized, keep awake |
| Clicking | Retry time when the screen is unavailable, wait-for-idle, put mouse back, conflict warnings |
| Watchers | Default check interval and confirmation count for new watchers |
| Hotkeys | Global hotkeys on/off and their key combinations (pause all, show/hide, emergency stop, recording) |
| Phone alerts | Discord / Telegram, which events, test alert, protect with your Windows account |
| Recording & video | Recorder options; screen videos (on/off, quality, folder, clean-up, hidden areas, black out while typing); run history; failure screenshots |
| Appearance | Light / dark / system theme, summary cards |
| Data & backups | Daily backups and how many to keep, click history on/off, log size, data folder, uninstall |

## Locked screens and remote sessions

Windows doesn't allow **any** program to click on, or take pictures of, a locked screen or a
disconnected remote-desktop session. While that's the case, Clickue waits, retries, and then
reports *Missed*. It never clicks blindly.

To keep Clickue working while you're away:

- **Don't lock the computer running Clickue.** Turn off its screensaver and lock screen, and
  lock the computer you connect *from* instead.
- **Leaving an RDP session:** instead of closing the window, hand the session back to the
  console so the desktop stays active. Run this from an administrator command prompt inside
  the session:
  ```bat
  for /f "skip=1 tokens=3" %s in ('query user %USERNAME%') do %windir%\System32\tscon.exe %s /dest:console
  ```
- **Virtual machines:** protect the hypervisor console and remote access with strong
  passwords and two-factor sign-in, since the session itself stays unlocked.
- Check it works: **Schedule test click…** for 2 minutes, disconnect, reconnect later and
  read the result in the Test history.

## Troubleshooting

| Problem | Try |
|---|---|
| "Picture not found" | Is the spot on screen? Re-pick with text or an icon near the spot, or use a Large picture. **Show spot** (with similar pictures outlined) to check |
| Clicks the wrong place | Keep **Only the exact picture** ticked. **Show spot**. Re-pick if the app's look changed. Make sure the target isn't covered |
| Watcher shows "Can't tell: Clickue window in front of the picture" | Bring the watched window to the front, minimize Clickue or send it to the tray (a Clickue window behind it doesn't count) |
| "Couldn't check for a new version: … CERTIFICATE_VERIFY_FAILED" | Install 4.6.1 or later. If it continues, antivirus HTTPS scanning or a company proxy may be intercepting secure connections - see the complete guide, Troubleshooting |
| Watcher counted a picture as gone after switching remote session ↔ console | Update to 4.5.6 (it waits for the screen to settle and cancels the click if the picture comes back); search the whole screen or re-draw the search area |
| After switching remote session ↔ console, "seen" took a few checks to come back | Update to 4.6.1: it looks right away and shows *seen* on the first check; only a missing picture waits 15 s |
| Picture too small to box | Zoom in with the mouse wheel while drawing |
| Watcher says the picture is NOT there, but it is | **Dry run** outlines the closest places. Re-draw the box around a part that never changes, or choose **Match: part of the picture is enough** |
| Watcher never clicks again | "Click only once" is waiting for the picture to come back; untick it to keep clicking |
| Nothing happens while away | The screen was locked or disconnected; see [above](#locked-screens-and-remote-sessions) |
| A hotkey doesn't work | Another program uses it; choose a different one in Preferences → Hotkeys (see the log) |
| Alerts don't arrive | **Send a test alert**; check the URL / token / chat id and internet access |
| A recorded macro misses its targets | Open the click steps → **Picture of this spot now**; replace waits with **Wait for a picture**; **Step through** |
| Paste puts nothing | Click the field first; try **Shift+Insert** or a longer **Wait after pasting**; some fields block pasting (use Type) |
| A job waits a long time | Another job is running (see the bar above the list). Only one job uses the mouse at a time |
| Something went wrong | **Ctrl+Alt+X** stops everything |
| Want to start over | ☰ Menu → **Backups…** to restore, or **Uninstall…** |
| Jobs went back to an older list after an update | ☰ Menu → **Backups…** → restore the newest backup with your jobs. A portable copy and the installed Clickue keep separate jobs |

Still stuck? Open an issue with the relevant lines from the log (☰ Menu → **Open log file**),
with anything private removed.
