# The complete Clickue guide

← [README](../README.md) · [Feature list](../FEATURES.md) · [Quick start](USER_GUIDE.md)

This guide explains **every feature** of Clickue, with real-world scenarios and example
pictures. Read it from top to bottom to learn everything, or jump to the part you need.
In the app, open it from **☰ Menu → Complete guide (online)**.

> [!NOTE]
> The example pictures show an invented "Example App" so the ideas are easy to see. Your own
> apps will look different; the steps are the same.

## Contents

**Getting started**
1. [What Clickue does](#1-what-clickue-does)
2. [Installing and the first start](#2-installing-and-the-first-start)
3. [The main window](#3-the-main-window)

**Making jobs**

4. [Choosing where to click](#4-choosing-where-to-click)
5. [Scheduled clicks](#5-scheduled-clicks)
6. [Screen watchers](#6-screen-watchers)
7. [When a job may run: active hours and limits](#7-when-a-job-may-run-active-hours-and-limits)
8. [Multi-step jobs and click chains](#8-multi-step-jobs-and-click-chains)

**Running jobs**

9. [Testing a job](#9-testing-a-job)
10. [Starting, pausing and stopping](#10-starting-pausing-and-stopping)
11. [Safety features](#11-safety-features)
12. [Notifications and phone alerts](#12-notifications-and-phone-alerts)

**Looking after your jobs**

13. [Managing jobs](#13-managing-jobs)
14. [History, stats and logs](#14-history-stats-and-logs)
15. [Backups and your data](#15-backups-and-your-data)
16. [Window, tray, hotkeys and appearance](#16-window-tray-hotkeys-and-appearance)
17. [Preferences, setting by setting](#17-preferences-setting-by-setting)
18. [Locked screens, remote desktop and virtual machines](#18-locked-screens-remote-desktop-and-virtual-machines)

**Reference**

19. [Recipes: complete examples](#19-recipes-complete-examples)
20. [Keyboard shortcuts](#20-keyboard-shortcuts)
21. [Troubleshooting](#21-troubleshooting)
22. [FAQ](#22-faq)
23. [Getting help and suggesting ideas](#23-getting-help-and-suggesting-ideas)

---

## 1. What Clickue does

Clickue clicks on your screen for you, either **on a schedule** or **when something on the
screen changes**. Every automation is called a **job**, and there are two kinds:

| Kind | Clicks when… | Example |
|---|---|---|
| **Scheduled click** (＋ New click) | a time comes round: every 8 hours, every 5 minutes, at 08:00… | Press *Refresh* every 30 minutes, at a slightly different time each round |
| **Screen watcher** (👁 New watcher) | a picture on the screen **disappears** or **appears** | When the *Connected* badge disappears, click *Reconnect* |

A few ideas run through the whole app:

- **Spots are found by their picture.** When you pick a spot, Clickue saves a small picture
  of it and searches the screen for it before every click. So the click still lands on the
  right button after a window moves, the screen resolution changes, or you connect from a
  different screen. ([Section 4](#4-choosing-where-to-click))
- **Any job can do more after its click:** click other spots, wait, type, press keys, or wait
  for the next picture to appear and click it. That's a **click chain**.
  ([Section 8](#8-multi-step-jobs-and-click-chains))
- **It's careful.** It waits while you're using the mouse, won't click when something covers
  the target, and never clicks blindly on a locked screen. ([Section 11](#11-safety-features))
- **Everything can be tested** without waiting for the real time, and without clicking at
  all if you prefer. ([Section 9](#9-testing-a-job))

Clickue runs on **Windows 10 and 11**. It needs a real, unlocked desktop session to click;
see [section 18](#18-locked-screens-remote-desktop-and-virtual-machines).

---

## 2. Installing and the first start

### Choosing a download

From the [Releases page](https://github.com/jnssylvest/clickue/releases/latest):

| Download | Best for | Notes |
|---|---|---|
| `Clickue-Setup-<version>.exe` | Most people | Installs with Start-menu entries and an uninstaller. Choose **only for me** (no admin needed) or **all users** (Program Files, needs admin). Each Windows user keeps their own jobs |
| `Clickue-Portable-<version>.zip` | USB sticks, locked-down PCs, trying it out | Unzip anywhere and run `Clickue.exe`. All data stays in a `ClickueData` folder beside it |
| Source code | Developers | Python 3 with `pillow`, `pystray`, `opencv-python-headless`, `numpy`. See the [README](../README.md#run-from-source) |

> [!WARNING]
> Clickue isn't code-signed, so Windows SmartScreen may say *"Windows protected your PC"*.
> Click **More info → Run anyway** if you downloaded it from the official Releases page.

### What happens on the first start

- **Previous version found.** If jobs from the older *Scheduled AutoClicker* are found,
  Clickue **asks** whether to import them. It never imports silently.
- **Reinstalled?** If you installed again and jobs from before are still in your user folder,
  Clickue asks whether to **keep them** or **start fresh**. Starting fresh saves a backup first
  (shown as *Before a fresh start* in Backups), so nothing is lost.
- **One copy only.** If Clickue is already running (maybe hidden in the tray), starting it
  again just tells you so, instead of opening a second copy that could double-click. Look for
  its icon near the clock (you may need to click the **^** arrow).

---

## 3. The main window

![The main window, with its seven parts numbered](images/guide/main-window.png)

1. **Header.** **▴ Summary** shows or hides the summary cards, the theme button switches
   light/dark, and **☰ Menu** holds everything else (see below).
2. **Summary cards.** The next click and its countdown, how many jobs are active, clicks
   today, and whether the screen is available (not locked or disconnected).
3. **Toolbar.** ＋ New click, 👁 New watcher, Edit, Duplicate, Delete, ▶ Start / Stop,
   ⏸ Pause (this job), ⏸ Pause all, 🧪 Tests, ↓ Import and ↑ Export. When the window is too
   narrow, the least-used buttons fold into **More ▾**.
4. **Filter.** Show all jobs, only scheduled clicks, or only screen watchers.
5. **Job list.** One row per job. **Double-click** (or Enter) to edit, **right-click** for every
   action. Less important columns hide when the window gets narrow.
6. **Activity.** A live, colour-coded log. Filter it to **Clicks** or **Problems**. **Clear
   view** empties the panel (the log file keeps everything); **Open log file** opens the full
   log.
7. **Status bar.** A one-line summary.

Drag the divider between the job list and Activity to give either more room.

### The job list columns

| Column | Shows |
|---|---|
| **Status** | What the job is doing (see below) |
| **Name** | The job's name |
| **Target** | Where it clicks and how it finds the spot (picture, window, or position) |
| **Click** | Button and single/double, e.g. *Left ×2* |
| **Schedule** | E.g. *every 8h + 10s–15m*, or *check every 30s* for watchers |
| **Next click** | When the next click is due; for watchers, what was last seen |
| **Starts in** | A live countdown |
| **Clicks** | How many times the job has clicked |
| **Last result** | The outcome of the latest click: *OK*, *Missed*, *Click FAILED*, *Finished…* |

### Status values

| Status | Meaning |
|---|---|
| ● **Running** | Scheduled and counting down |
| ● **Waiting** | Due, but can't click yet (screen locked, you're using the mouse, the spot is covered…). It retries |
| 👁 **Watching** | A watcher that's looking and hasn't seen a reason to click |
| ⚠ **Missing** / ⚠ **Showing** | A watcher has seen the change and is confirming it (flicker protection) |
| ⚡ **Clicking** | A watcher is about to click (during its random delay) |
| 🌙 **Off hours** | Outside the job's active hours |
| ⏸ **Paused** | This job, or everything, is paused |
| ○ **Stopped** | Turned off. *Last result* shows **Finished** if a limit stopped it |
| Purple row | A pending **test** (scheduled test click or watcher test), with its own countdown |

### The ☰ Menu

| Item | Does |
|---|---|
| New click… / New watcher… / Tests… | Same as the toolbar |
| Undo delete | Brings back the last deleted job(s) |
| Import jobs… / Export jobs… | Share jobs between computers ([section 13](#13-managing-jobs)) |
| Backups… | Back up now, restore, open the backups folder ([section 15](#15-backups-and-your-data)) |
| Export click history (CSV)… | Every click, miss and failure as a spreadsheet |
| Preferences… | All settings ([section 17](#17-preferences-setting-by-setting)) |
| Open data folder / Open log file | Where your jobs, settings and log live |
| Complete guide (online) | Opens this guide in your browser |
| Help & shortcuts | A short in-app summary and the keyboard shortcuts |
| About Clickue | Version, which optional parts are available, and your data folder |
| Uninstall… | Removes Clickue's data and the start-with-Windows entry |
| Exit | Quits Clickue (closing the window only hides it to the tray, if that's on) |

---

## 4. Choosing where to click

Every job has a **spot** to click: the main click of a scheduled click, or the button a
watcher presses.

### Picking a spot

1. In the job editor, click **◎ Pick on screen…**.
2. Clickue hides and a **5-second countdown** box appears. Point the mouse at the spot and
   keep it still.
3. When the countdown ends, the spot under the pointer is saved.

The countdown box is designed to stay out of your way: it **moves aside** when your mouse
comes near it, and you can **drag** it anywhere (the countdown pauses while you drag).

When you pick, Clickue saves three things, used in this order:

1. **A picture of the spot** (recommended, on by default).
2. **The window** it's in, and where inside that window.
3. **The exact screen position**.

### 1. Finding the spot by its picture

With **Find the spot by its picture** ticked, Clickue searches the screen for the saved
picture before every click. That makes clicks reliable when windows move, the screen
resolution changes, or the display scaling is different (for example one computer at 100 %
and a remote session at 150 %).

![A good spot has text or an icon; a plain area is a bad spot](images/guide/good-and-bad-spots.png)

How the search works:

- It looks at sizes from **50 % to 200 %**, so it handles different resolutions and display
  scaling from 100 % to 175 %. It remembers the size it last found, so later checks are faster.
- It compares the **whole picture** and a **close-up of the exact spot**, so it can tell the
  right button from look-alikes.
- If the picture appears **more than once**, it picks the copy **closest to where you
  picked it**.
- If the spot is **plain** (an empty area that looks the same everywhere), Clickue **warns**
  you when you pick it. Pick a spot with text or an icon nearby instead.

**Picture size.** Choose how much of the screen around the spot is saved. It applies the
next time you pick.

![Small, Medium and Large pictures around the same spot](images/guide/picture-sizes.png)

| Size | Area saved | Use when |
|---|---|---|
| Small | 90 × 56 | The spot itself is distinctive; fastest |
| **Medium** (default) | 150 × 90 | Most buttons and links |
| Large | 260 × 150 | Several buttons look alike (a row of identical icons, repeated "Open" links) |

**If the picture can't be found:**

- **Wait and retry** (default, safest). Clickue doesn't click, logs *picture not found*, and
  tries again, like any other "can't click right now" situation.
- **Click the saved position.** Falls back to the window or screen position. Use it only
  when the layout never changes.

> [!TIP]
> Re-pick a spot whenever the app it's in changes its look (a redesign, a new theme, dark
> mode). The saved picture is how the spot is found.

### 2. Inside a window

When you pick inside an app's window, Clickue also remembers **which window** (by its title)
and **where inside it**. The editor then selects **Inside a window**:

- **Window title contains.** Part of the title used to find the window. If the title changes
  (for example it includes a document name or a count), keep only the part that stays the
  same: `Example App` instead of `Inbox (12) - Example App`.
- **Spot inside the window X / Y.** The position inside the window's content area.
- **Bring the window to the front before clicking** (on by default), so nothing covers it.
- **Adjust the spot if the window changes size.** Scales the position when the window is
  resized. Good for layouts that stretch; leave it off for fixed layouts.

### 3. Fixed screen position

The simplest option: the exact pixel on the screen (**Screen X / Y**). You can type the
numbers yourself.

- **Adjust the spot if the screen resolution changes** scales the position with the screen.
- If the screen size is different from when you picked the spot, the editor warns you.

### Checking a spot

**Show spot** (in the editor, the Tests window, or the right-click menu) moves the mouse to
where Clickue would click **right now**, shows a pulsing crosshair, and tells you how it found
the spot, e.g. *picture 81% at 150% size*. It never clicks. See [section 9](#9-testing-a-job).

**Scenario: the same job from two different screens.** You set up a job while sitting at the
computer, but later connect to it by remote desktop at a different resolution. With **Find the
spot by its picture** on, Clickue finds the button at its new size and position, so the job
keeps working without being re-picked.

---

## 5. Scheduled clicks

Click **＋ New click** (Ctrl+N).

### The settings

| Setting | What it does | Default |
|---|---|---|
| **Name** | Shown in the list, the log, history and alerts | *Click 1* |
| **Where to click** | The spot ([section 4](#4-choosing-where-to-click)) | — |
| **Click** | Left, right or middle; single or double | Left, single |
| **Scheduled every** | Hours, minutes and seconds between clicks | 8 h |
| **Add a random delay after each scheduled time** | Adds a random wait so clicks don't happen at a predictable moment | On |
| **Random delay from / up to** | The range of the random delay, chosen fresh each time, to the second | 10 s to 15 min |
| **First scheduled time** | A time of day (24 h, `HH:MM`) for the first click. Blank = one interval from now | Blank |
| **Keep a fixed schedule** | Random delays don't push later clicks later | On |
| **When it may run** | Active hours and limits ([section 7](#7-when-a-job-may-run-active-hours-and-limits)) | Off |
| **More steps after the click** | Extra steps ([section 8](#8-multi-step-jobs-and-click-chains)) | None |
| **Start this schedule when I save** | Starts the job right away | On for new jobs |

Under the settings, a one-line **summary** describes what the job will do, e.g. *Clicks every
8h, each one 10s to 15m after its scheduled time (random, to the second).*

### How the random delay and the fixed schedule work

![Three ways the same 8-hour job can run](images/guide/schedule-random-delay.png)

- **Random delay on, fixed schedule on (default).** The *scheduled* times stay at exactly
  08:00, 16:00, 00:00… and each click happens a random 10 s to 15 min after its scheduled time.
  Over days and weeks, the clicks never drift.
- **Fixed schedule off.** Each interval counts from the **actual** click, so the delays add up
  and the times slowly drift later. Use this only if you want "at least 8 hours between
  clicks".
- **Random delay off.** Clicks happen at exactly the scheduled times.

If a scheduled time is missed completely (see below), the next one is the next slot on the
same fixed schedule. Old slots aren't "caught up".

### Missed clicks

If a click comes due but can't happen (the screen is locked or the remote session is
disconnected, you're using the mouse, the spot is covered or can't be found), Clickue:

1. shows **Waiting** and retries every 30 seconds,
2. keeps trying for **15 minutes** (change it in **Preferences → Clicking**),
3. then records **Missed** in *Last result* and the history, sends an alert if you've turned
   that on, and moves on to the next scheduled time.

A click that came due **while Clickue was closed** is skipped, not fired late the moment
you start it again.

### Scenarios

- **Refresh a page every 30 minutes, not like clockwork.** Scheduled every 0 h 30 min, random
  delay 10 s to 3 min. Each refresh lands somewhere in the first three minutes of its slot.
- **Every morning at 08:00 exactly.** Scheduled every 24 h, random delay **off**, First
  scheduled time `08:00`.
- **Keep a session alive.** Click a harmless spot (a page title or a blank part of a toolbar)
  every 10 minutes; add active hours so it only runs during the working day.
- **A daily report.** Every 24 h starting at 07:30, with extra steps that click *Export* and
  then *Save* (see [the chain recipe](#recipe-3-refresh-export-and-save-a-report)).

---

## 6. Screen watchers

A watcher looks at the screen every so often and clicks **when a picture disappears** or
**when it appears**. Click **👁 New watcher** (Ctrl+Shift+N).

### When a picture disappears

![Before and after: the Connected badge goes away, so Clickue clicks Reconnect](images/guide/watcher-disappears.png)

Use this when something is **normally on screen** and its absence means something went wrong:
a *Connected* badge, a *Live* indicator, a green status light, a "logged in as…" label.

### When a picture appears

![Before and after: a Stay signed in button appears and Clickue clicks it](images/guide/watcher-appears.png)

Use this when something **shows up** and needs a click: a *Continue* button, a *Stay signed in*
prompt, an *OK* on a message box, a *Retry* banner.

Tick **Click the picture itself (where it's found)** when the thing that appears is the button
to press. Clickue then clicks where it found the picture, and you don't need to pick a separate
button.

### Setting up a watcher, step by step

1. **Click** *when the picture disappears* or *when the picture appears*.
2. **▢ Draw box around picture…** The screen freezes and dims. Drag a box around what to
   watch, then release. The size shows while you drag. Esc or a right-click cancels.
   - Draw it **while the picture is on screen** (for "appears" watchers, open the dialog or
     prompt once so you can draw it).
   - Box something **distinctive**: text, an icon, a logo. Clickue warns you about plain areas
     and very big boxes (big boxes work, but each check is slower). The box must be at least
     16 × 16.
3. **Search** the whole screen, or **only an area** (below).
4. **Button to click.** **◎ Pick on screen…** the button to press. (Not needed when *Click the
   picture itself* is ticked.)
5. Set the timing: **Check every**, **Click when missing/showing for … checks in a row**, the
   optional **random delay**, the optional **wait after each click**, and **Click only once**.
   All explained below.
6. **Check now** confirms the picture can be found right now. **Dry run** shows the picture,
   then the button, and says whether it would click. Neither one clicks.
7. **Save.** Leave **Start watching when I save** ticked to start right away.

### Search only an area

![The search area covers the messages panel; a look-alike in the sidebar is ignored](images/guide/search-area.png)

Choose **only an area:** and **Draw area…** to limit where Clickue looks. This is:

- **faster**, because only that part of the screen is checked, and
- **more precise**, because look-alikes elsewhere on the screen are ignored.

The area scales with the screen if the resolution changes. Draw it a bit bigger than the
panel, so a small window move doesn't push the picture outside it.

### Strict matching

![The saved picture compared with four things on screen](images/guide/strict-matching.png)

Watchers compare **shape, close-up detail and colour**. A badge that turns from green to red,
or whose text changes from *Online* to *Offline*, counts as **changed** (gone), even though
its shape is the same. The same picture at another size (different display scaling) is still
found.

### Timing settings

| Setting | What it does | Default |
|---|---|---|
| **Check every** | How often to look | 30 s |
| **Click when missing for** (or **showing for**) **N checks in a row** | Flicker protection: the change must be seen this many times in a row | 2 |
| **Wait a random delay before clicking** | A random pause before the click | On, 1–5 s |
| **Wait a while after each click before looking again** | Gives the app time to react before the next check | On, 30 s |
| **Click only once each time it disappears / appears** | Don't click again until the picture has come back (or gone away) | On |

New watchers start with the **Check every** and **checks in a row** values from
**Preferences → Watchers**.

**Flicker protection.** Screens flicker: a page reloads, a tooltip covers something for a
moment. Requiring the change for several checks in a row ignores these blips. Once a change
is first seen, the confirming checks come quickly (every 5 seconds), so a real change is still
handled fast.

![A one-off blip is ignored; two missing checks in a row cause a click](images/guide/flicker-protection.png)

**Click only once.** With it on, the watcher clicks **once** per change and then waits for the
picture to come back (or go away) before it will click again. With it off, it keeps clicking
for as long as the change lasts, waiting the *after each click* time between clicks.

![Click only once on: one click per disappearance. Off: keeps clicking](images/guide/click-once.png)

Example with *click when it disappears* and **click only once on**: the picture is there, so
nothing happens. The picture goes away, so Clickue clicks once. The picture comes back, which
re-arms the watcher (no click). The next time it goes away, Clickue clicks once again.

### Clickue's own window

While the Clickue window is **open on screen**, a *missing* picture isn't counted, because the
window might be covering it. The list shows *Can't tell: Clickue window open*. Minimize Clickue
or send it to the tray when you've finished setting up. "Appears" watchers aren't affected.

### Watcher statuses

**Watching** (*Seen 13:49:58* or *Not showing*), **Missing** / **Showing** (confirming a change),
**Clicking** (during the random delay), **Off hours**, and **Paused**. The countdown shows
*check in 12s*.

### Scenarios

- **Reconnect after a drop.** Disappears: the *Connected* badge. Button: *Reconnect*. Check
  every 30 s, 2 checks, click only once on.
- **Dismiss a recurring prompt.** Appears: the prompt's *OK* button. Click the picture itself.
  Check every 10 s, 1 check.
- **Keep a dashboard on its live view.** Disappears: the *Live* label (it vanishes when the page
  falls back to a paused view). Button: the *Live* toggle.
- **Retry until it works.** Appears: the *Retry* button. Click the picture itself. Click only
  once **off**, wait 60 s after each click, so it keeps pressing *Retry* every minute while the
  banner stays.
- **Watch one panel among several identical ones.** Search only an area around the panel you
  care about, so the same badge in another panel is ignored.

---

## 7. When a job may run: active hours and limits

Every job's editor has a **When it may run** section.

### Active hours and days

![A week with active hours 08:00 to 22:00, Monday to Friday](images/guide/active-hours.png)

Tick **Only run during set hours and days**, set **From** and **to** (24 h), and tick the days.

- **Overnight** ranges work: `22:00` to `06:00` runs from 10 pm until 6 am.
- **The same time twice** (e.g. `00:00` to `00:00`) means all day on the ticked days.
- **Scheduled clicks:** *If a click comes due outside these hours*:
  - **Wait until the hours start, then click.** The click happens at the start of the next
    active period.
  - **Skip that click.** It's dropped, and the job waits for its next scheduled time.
- **Watchers** don't look or click outside the hours; the list shows **🌙 Off hours** and when
  the job is active.

### Limits

- **Stop after N clicks**, counted from when the job is started (or restarted).
- **Stop at** a date and time, `YYYY-MM-DD HH:MM`.

When a limit is reached, the job **stops**, *Last result* shows **Finished** with the reason,
and an alert is sent if *A job finished* is ticked in **Preferences → Phone alerts**.

### Scenarios

- **Office hours only.** 08:00 to 18:00, Mon–Fri. A click due on Saturday waits until Monday
  08:00, or is skipped.
- **Only at night.** 22:00 to 06:00 every day, for a task that shouldn't disturb daytime work.
- **A one-week trial.** Stop at next Friday 17:00.
- **Just a few times.** Stop after 3 clicks, e.g. to retry something three times and then give
  up.

---

## 8. Multi-step jobs and click chains

After its main click, any job (scheduled or watcher) can run **more steps**, in order. Open the
editor and use **More steps after the click**.

### Step types

| Button | Step | Settings |
|---|---|---|
| **+ Click** | **Click a spot** | **◎ Pick on screen…**, the button (left/right/middle), single/double, and **Find the spot by its picture** (recommended) |
| **+ Wait** | **Wait** | From … to … seconds. The same number twice waits exactly that long; two different numbers wait a random time in that range (default 2 s) |
| **+ Wait for picture** | **Wait for a picture** | The picture (**▢ Draw box around picture…**); wait until it **appears** or **goes away**; for "appears": **then click it** (where it appeared) with a button and single/double; **Wait up to** N seconds (1 s to 1 h, default 60 s); if it doesn't happen: **stop the chain** or **continue anyway** |
| **+ Type** | **Type text** | Any text, including accents, other languages and symbols. It types into whatever has focus. A new line presses Enter |
| **+ Keys** | **Press keys** | A key or a combination, e.g. `Enter`, `Tab`, `Esc`, `Ctrl+S`, `Ctrl+Shift+S`, `Alt+F4`. Quick buttons for common ones |

**Key names** for *Press keys*: Ctrl, Alt, Shift, Win, Enter, Tab, Esc, Space, Backspace,
Delete, Up, Down, Left, Right, Home, End, PageUp, PageDown, F1–F12, letters and digits.
Combine them with `+`.

**Editing steps.** Select a step, then **Edit** (or double-click it), **▲ / ▼** to move it, or
**Remove**. The list shows each step with a short description, e.g. *Wait for picture: until
it appears, then click it · up to 1 min, then stop the chain*.

**If a step fails** (its spot can't be found, a wait for a picture times out and is set to
*stop the chain*), the remaining steps are **skipped**. The main click still counts, and the
reason appears in Activity, the click history and (if you've turned it on) an alert:
*extra steps stopped (step 2: timeout - the picture didn't appear within …)*.

### A multi-step job

![Main click on the search box, type 1042, press Enter, wait, click the first result](images/guide/multi-step-search.png)

1. Main click: the **search box**.
2. **Type text:** `1042`
3. **Press keys:** `Enter`
4. **Wait:** 2 s
5. **Click a spot:** the first result

### Click chains: react to each click

Fixed waits are guesses. Too short and the next click lands before the app is ready; too long
and time is wasted (and on a slow day, even a long wait may not be enough). **Wait for a
picture** waits for the **actual result** instead, so each step reacts to the one before.

![Refresh, then wait for Export and click it, then wait for Save and click it, then wait for the done message](images/guide/click-chain.png)

1. Main click: **Refresh**.
2. **Wait for a picture:** the **Export** button → *appears* → *then click it* → up to 60 s →
   *stop the chain*.
3. **Wait for a picture:** the **Save** button → *appears* → *then click it* → up to 30 s.
4. **Wait for a picture:** the "Download complete" message → *appears* (no click) → up to
   120 s. This confirms the chain worked; if it times out, you'll see it in Activity.

**How to set one up**

- Draw each picture **while that screen is actually showing**. Walk through the routine by hand
  once, adding each step as you reach its screen.
- Use **appears + then click it** for buttons that show up after the previous step.
- Use **goes away** to wait for something to finish, e.g. until a *Loading…* spinner
  disappears, before the next step.
- Use **stop the chain** when later steps make no sense without this one (the safe default).
  Use **continue anyway** for optional screens, e.g. a "What's new" pop-up that only appears
  sometimes.
- Start the chain **on a schedule** (a scheduled click) or **from a change** (a screen watcher).

> [!IMPORTANT]
> While a chain waits, **other jobs wait their turn**, because the mouse can only do one thing
> at a time. A job that's due during the wait clicks right after the chain finishes. Keep time
> limits sensible (seconds to a few minutes, not an hour) when other jobs depend on timing.

### Scenarios

- **Recover in several steps.** A watcher sees an error banner appear → clicks *Retry* → waits
  for the *Sign in* button → clicks it → waits for the main page to come back.
- **Confirmation dialogs.** Click *Submit* → wait for "Are you sure?" → click *Yes* → wait for
  the success message.
- **Fill a short form.** Click the first field → type → press Tab → type → press Enter.
- **Wait for loading to finish.** Click *Run* → wait until the *Working…* spinner goes away
  (up to 5 minutes) → click *Results*.

---

## 9. Testing a job

Open **🧪 Tests** (Ctrl+T, the toolbar, or right-click a job → **Open Tests…**). Pick the job
at the top. **The whole app hides while a test runs** so nothing is in the way, and comes
back with the result.

![Show spot marks where it would click; Dry run marks the picture and the button](images/guide/tests-show-spot-dry-run.png)

| Test | For | What it does |
|---|---|---|
| **Show spot** | All jobs | Moves the mouse to where it would click right now, shows a pulsing crosshair, and says how it found the spot. **No click** |
| **Test click now** | All jobs | Clicks once right away, including the extra steps. The schedule isn't changed |
| **Schedule test click…** | All jobs | Clicks once in X minutes (at least 5 s away). Follows the same rules as a real click: waits for the screen, retries, then reports |
| **Check picture** | Watchers | Is the watched picture on screen (or in its area) right now? |
| **Dry run** | Watchers | Marks the watched picture, then the button, and says whether it **would** click now. **No click** |
| **Schedule watcher test…** | Watchers | Runs the watcher check later, in the background. Optionally **really clicks** if the picture is missing |

- **Pending tests** show as **purple rows** in the job list with a countdown. Right-click them
  to **change the test time** or **cancel** them; **Cancel pending tests** in the Tests window
  cancels them all.
- **Test history** lists every result for **This job** or **All jobs**. Select a line to see all
  the details. **Clear** empties it.
- The same tests are on each job's **right-click menu**, and the editor has **Show spot**,
  **Check now** and **Dry run** buttons so you can test before saving.

**Scenario: does it still work after I disconnect?** Schedule a test click 2 minutes ahead,
leave the remote session the way you normally would (see
[section 18](#18-locked-screens-remote-desktop-and-virtual-machines)), reconnect later and read
the result in the Test history or *Last result*. If it says *screen locked or session
disconnected*, the way you left the session stopped clicks from working.

---

## 10. Starting, pausing and stopping

| Action | How | Effect |
|---|---|---|
| **Start** | ▶ Start, Space, or right-click | Turns the job on. Scheduled clicks get their first time (the *First scheduled time*, or one interval from now). Limits count from now |
| **Stop** | Same button | Turns the job off and clears its schedule |
| **Pause** this job | ⏸ Pause, **P**, or right-click | Keeps the schedule but doesn't click. A click that comes due while paused is **skipped**, not fired the moment you resume |
| **Pause all** | ⏸ Pause all, **Ctrl+P**, the tray menu, or **Ctrl+Alt+P** from anywhere | Pauses every job at once. Each job's own pause is kept |

Use **Pause all** before you sit down to work on the computer yourself, and resume when you
leave. The global hotkey works even while Clickue is hidden.

---

## 11. Safety features

- **Waits until you're idle.** Clickue won't move the mouse until the mouse and keyboard have
  been idle for 5 seconds (change it, or turn it off with 0, in **Preferences → Clicking**). It
  doesn't grab the mouse from under you.
- **Puts the mouse back** where it was after each click (optional).
- **Won't click a covered target.** If another window, or Clickue itself, is on top of the spot,
  it waits and retries instead.
- **Detects a locked or disconnected screen** and waits instead of clicking blindly
  ([section 18](#18-locked-screens-remote-desktop-and-virtual-machines)).
- **Picture checks before every click** (when finding by picture). If the button isn't there,
  nothing is clicked.
- **One copy at a time**, so jobs never run twice.
- **Keeps the PC and display awake** while it runs (optional), so sleep doesn't stop the jobs.
- **Limits and active hours** stop jobs from running longer or more often than you meant.

> [!CAUTION]
> Automated clicking can do real things in real apps: submit forms, send messages, place
> orders. Test with **Show spot** and **Dry run** first, prefer **Find the spot by its picture**,
> and read the [warnings in the README](../README.md#%EF%B8%8F-responsible-use--warnings). Many
> websites and services don't allow automation; check their terms.

---

## 12. Notifications and phone alerts

### Tray notifications

With **Tray notifications** on (**Preferences → General**), Windows shows a notification for
watcher clicks, missed or failed clicks, and test results.

### Phone alerts

![A phone showing two Clickue alerts, and the events you can choose](images/guide/phone-alerts.png)

**Preferences → Phone alerts**, tick **Send alerts to my phone**, and set up one or both
services:

**Discord**
1. In a Discord server you own (create a private one just for alerts), open the channel's
   **Edit channel → Integrations → Webhooks → New webhook**.
2. **Copy webhook URL** and paste it into **Discord webhook URL**.
3. Install the Discord app on your phone and turn on notifications for that channel.

**Telegram**
1. In Telegram, message **@BotFather**, send `/newbot` and follow the steps. Copy the **token**
   into **Telegram bot token**.
2. Send your new bot any message (so it's allowed to message you).
3. Get your **chat id**, for example by messaging **@userinfobot**, and paste it into
   **Telegram chat id**.

**Choose the events** under **Send an alert when…**:

| Event | Example message | Default |
|---|---|---|
| A watcher clicked | `Clickue: Reconnect: picture was gone, clicked.` | On |
| A click was missed or failed | `Clickue: [Daily report] MISSED - couldn't click within 15 min (…)` | On |
| A job finished (limit reached) | `Clickue: Weekly export finished: …` | On |
| Scheduled test results | `Clickue: Reconnect watcher test: …` | Off |

Click **Send a test alert** to check. The result shows next to the button (✔ sent, or the
error). Alerts are sent in the background, so a slow connection never delays clicking. They
need internet access from the computer running Clickue.

> [!WARNING]
> Anyone with your webhook URL or bot token can post to that channel or bot. Keep them private,
> and remove them from logs or screenshots you share.

---

## 13. Managing jobs

- **New:** ＋ New click (Ctrl+N) or 👁 New watcher (Ctrl+Shift+N).
- **Edit:** double-click, Enter, Edit, or right-click → Edit…. The editor warns you if you try
  to close it with unsaved changes. It remembers its size and can be resized; long editors
  scroll.
- **Duplicate:** a copy of the selected job, a quick way to make a similar one.
- **Delete:** Del, Delete, or right-click. A bar with **↶ Undo** appears; Ctrl+Z (or
  ☰ Menu → Undo delete) brings it back.
- **Right-click** any job for every action: Edit, Start/Stop, Pause/Resume, the tests, Stats &
  click history, Duplicate and Delete.

### Import and export

**↑ Export** saves all your jobs to a `.json` file. **↓ Import** reads one and asks:

- **Yes:** add them to your current jobs,
- **No:** replace your current jobs,
- **Cancel:** do nothing.

Imported jobs start fresh (their click counts are reset), and the ones that were running
start their schedules.

**Scenario: move to a new computer.** Export on the old one, copy the file, Import on the new
one, then use **Show spot** on each job. Picture-based spots usually work straight away;
re-pick any that don't.

---

## 14. History, stats and logs

### Click history

Every click, miss and failure is recorded with the time, the job, the type (scheduled, watcher,
test, manual), the result, the position and how the spot was found. The history keeps up to
50,000 rows (the oldest are dropped). Turn it off in **Preferences → Data & backups**.

- **☰ Menu → Export click history (CSV)…** saves all of it. It opens in Excel, LibreOffice or
  Google Sheets.

### Stats per job

Right-click a job → **Stats & click history…**:

- **Clicks total**, **Today**, **Last 7 days** and **Problems**,
- the **last click** and **last problem**, clicks **by type**,
- **Recent activity** (the last 200 entries),
- **Export this job's history…** to a CSV of just that job.

### Activity and the log file

The **Activity** panel shows what's happening, colour-coded, filterable to **Clicks** or
**Problems**. Everything also goes into the log file (**☰ Menu → Open log file**). The log
is limited to 1 MB by default (**Preferences → Data & backups**); two older copies are kept
and older ones are deleted, so it never grows without limit.

---

## 15. Backups and your data

### Where your data lives

Everything is in **`%APPDATA%\Clickue`** (or `ClickueData` next to `Clickue.exe` in portable
mode). Open it with **☰ Menu → Open data folder**.

| File | Holds |
|---|---|
| `jobs.json` | Your jobs |
| `settings.json` | Your preferences |
| `click_history.csv` | The click history |
| `test_history.json` | Test results |
| `clickue.log` (+ older copies) | The log |
| `backups\` | Backups |

Your data **survives** reinstalling, updating and moving the program. If a file is ever
damaged, it's set aside (renamed) instead of wiping your jobs.

### Backups

- **Automatic:** once a day, of all jobs and settings. The newest 14 are kept (adjustable).
- **☰ Menu → Backups…** lists them (Daily, Manual, Before a restore, Before uninstall, Before a
  fresh start) with how many jobs each holds.
  - **Back up now** makes a manual backup.
  - **Restore…** (or double-click) asks **Yes = replace** your current jobs, **No = add**
    them. Your current jobs are backed up first, and restoring never deletes backups.
  - **Open folder** opens the backups folder.

### Updating

Install the new version over the old one (or unzip the new portable version over the old
folder). Your jobs and settings are kept. After running the installer, Clickue asks whether to
**keep your jobs** or start fresh: choose **Yes** to keep them.

### Uninstalling

- **From Windows** (Settings → Apps, or the Start-menu uninstaller): it asks whether to also
  delete your data. Say **No** to keep your jobs for a later reinstall.
- **From inside Clickue** (☰ Menu → Uninstall…, or Preferences → Data & backups): it lists
  what will be removed, offers to save a backup of your jobs to your **Documents** folder (load
  it later with Import), then removes the data and the start-with-Windows entry. The portable
  `Clickue.exe` deletes itself a few seconds later.

---

## 16. Window, tray, hotkeys and appearance

### System tray

- **Minimize to the system tray** and **Close button (X) hides to the tray** are on by default,
  so jobs keep running after you close the window. The first time, a notification reminds you
  that Clickue is still running.
- **Tray menu** (right-click the icon): **Show window**, **Pause all / Resume all**, **Exit**.
- To quit completely, use **Exit** in the tray menu or ☰ Menu.

### Global hotkeys

They work from any app, even while Clickue is hidden:

| Hotkey | Does |
|---|---|
| **Ctrl+Alt+P** | Pause / resume everything |
| **Ctrl+Alt+K** | Show / hide Clickue |

Change them in **Preferences → Hotkeys** (at least one of Ctrl, Alt, Shift or Win, plus a key).
Leave a box empty to turn that hotkey off. If another program already uses a combination,
the log says so; pick another.

### Starting with Windows

**Preferences → General:** **Start automatically when I sign in to Windows**, and **Start
minimized** to go straight to the tray.

### Appearance and layout

- **Light, dark or system** theme (follows Windows), including dark title bars. Switch it
  quickly with the theme button in the header.
- **Responsive:** toolbar buttons that don't fit go into **More ▾**, less important columns
  hide, and the summary cards re-flow from 4 to 2 to 1 per row. **▴ Summary** hides the cards.
- **Drag dividers** to resize the job list and Activity, and the parts of the Tests window.
- **Every window remembers its size and position** (and whether it was maximized). If your
  screen gets smaller, windows are kept on screen.
- **Popups close when you click outside them** (they also have a Close button), so they never
  block the app.

---

## 17. Preferences, setting by setting

**☰ Menu → Preferences** (Ctrl+,). Click **Save** to apply.

### General

| Setting | Default |
|---|---|
| Minimize to the system tray | On |
| Close button (X) hides to the tray instead of exiting | On |
| Tray notifications (missed clicks, watchers, test results) | On |
| Start minimized | Off |
| Start automatically when I sign in to Windows | Off |
| Keep the PC and display awake | On |

### Clicking

| Setting | Default |
|---|---|
| If a click can't happen (screen locked / disconnected), keep retrying for | 15 min |
| Wait until mouse & keyboard have been idle for (0 = off) | 5 s |
| Put the mouse back where it was after clicking | On |

### Watchers

| Setting | Default |
|---|---|
| New watchers check every | 30 s |
| New watchers click after the change is seen … checks in a row | 2 |

These are only starting values for **new** watchers; each watcher has its own settings.

### Hotkeys

| Setting | Default |
|---|---|
| Use global hotkeys | On |
| Pause / resume all | Ctrl+Alt+P |
| Show / hide Clickue | Ctrl+Alt+K |

### Phone alerts

| Setting | Default |
|---|---|
| Send alerts to my phone | Off |
| Discord webhook URL / Telegram bot token / Telegram chat id | Empty |
| Send an alert when… | Watcher clicked, missed or failed, job finished: on. Test results: off |

### Appearance

| Setting | Default |
|---|---|
| Theme | System |
| Show the summary cards at the top | On |

### Data & backups

| Setting | Default |
|---|---|
| Back up my jobs and settings once a day | On |
| Keep the newest … daily backups | 14 |
| Keep a click history (for stats and CSV export) | On |
| Log file size limit | 1 MB |

Plus buttons for **Backups…**, **Open data folder**, **Export click history…** and
**Uninstall Clickue…**.

---

## 18. Locked screens, remote desktop and virtual machines

![What happens to clicks when you close, hand over, or lock a remote session](images/guide/remote-sessions.png)

Windows doesn't let **any** program click on, or take pictures of, a **locked** screen or a
**disconnected** remote-desktop session. It's a Windows security rule, not a Clickue
limitation. While that's the case, Clickue waits, retries, and then reports *Missed*. It never
clicks blindly.

**To keep Clickue working while you're away:**

- **Don't lock the computer running Clickue.** Turn off its screensaver lock and automatic
  lock, and lock the computer you connect **from** instead.
- **Leaving a remote-desktop (RDP) session:** instead of closing the window, hand the session
  to the console so the desktop stays active. Run this from an **administrator** command
  prompt inside the session (it disconnects you, which is expected):

  ```bat
  for /f "skip=1 tokens=3" %s in ('query user %USERNAME%') do %windir%\System32\tscon.exe %s /dest:console
  ```

  To use it in a `.bat` file, double the percent signs (`%%s`). Next time, connect again as
  usual.
- **Virtual machines:** the VM's own console (in the hypervisor) counts as a real screen.
  Protect the hypervisor and any remote access with strong passwords and two-factor sign-in,
  because the session itself stays unlocked.
- **Check it works:** **Schedule test click…** 2 minutes ahead, leave the session, come back,
  and read the result.

**Different screens, same job.** Connecting from different devices often changes the
resolution and scaling. **Find the spot by its picture** handles this; fixed positions don't.

---

## 19. Recipes: complete examples

### Recipe 1: refresh a page every 15 minutes during the day

| | |
|---|---|
| Kind | Scheduled click |
| Where | The page's *Refresh* button (or the browser's reload button), picture on, Medium |
| Schedule | Every 0 h 15 min, random delay 5 s to 2 min, fixed schedule on |
| When it may run | 07:00 to 19:00, Mon–Fri, outside hours: skip |
| Test | Show spot, then Test click now |

### Recipe 2: reconnect when the connection drops

| | |
|---|---|
| Kind | Screen watcher, **when the picture disappears** |
| Picture | The *Connected* badge |
| Button | *Reconnect* |
| Timing | Check every 20 s, 2 checks, random delay 1–5 s, after-click wait 60 s, click only once on |
| Alerts | A watcher clicked: on |
| Test | Check now, then Dry run. Then Schedule watcher test… with "really click" off |

### Recipe 3: refresh, export and save a report

| | |
|---|---|
| Kind | Scheduled click, every 24 h, first scheduled time 07:30 |
| Main click | *Refresh* |
| Step 1 | Wait for a picture: *Export* appears, then click it, up to 60 s, stop the chain |
| Step 2 | Wait for a picture: *Save* appears, then click it, up to 30 s, stop the chain |
| Step 3 | Wait for a picture: "Download complete" appears, up to 120 s |
| Test | Test click now while watching; check Activity for each step |

### Recipe 4: press "Stay signed in" whenever it pops up

| | |
|---|---|
| Kind | Screen watcher, **when the picture appears** |
| Picture | The *Stay signed in* button (open the prompt once to draw it) |
| Click | **Click the picture itself** |
| Timing | Check every 15 s, 1 check, random delay 1–3 s, click only once on |

### Recipe 5: recover from an error in several steps

| | |
|---|---|
| Kind | Screen watcher, **when the picture appears** |
| Picture | The error banner; click the picture itself is off, button: *Retry* |
| Step 1 | Wait for a picture: *Sign in* appears, then click it, up to 60 s, **continue anyway** (sometimes you're still signed in) |
| Step 2 | Wait for a picture: the main page's header appears, up to 120 s |
| Limits | Stop after 5 clicks, so a permanent problem doesn't loop forever; alert on finish |

### Recipe 6: a weekly task with a deadline

| | |
|---|---|
| Kind | Scheduled click, every 7 days, first scheduled time 09:00, random delay off |
| Steps | Click the *New* button → Type the text → Press `Ctrl+S` |
| When it may run | Stop at the last day of the project, e.g. `2026-12-18 18:00` |

---

## 20. Keyboard shortcuts

### In Clickue

| Keys | Does |
|---|---|
| Ctrl+N | New scheduled click |
| Ctrl+Shift+N | New screen watcher |
| Enter / double-click | Edit the selected job |
| Space | Start / stop the selected job |
| P | Pause / resume the selected job |
| Ctrl+P | Pause / resume all |
| Ctrl+T | Tests |
| Ctrl+Z | Undo delete |
| Ctrl+, | Preferences |
| Del | Delete the selected job |
| Esc / right-click | Cancel drawing a box |

### Anywhere (global, changeable)

| Keys | Does |
|---|---|
| Ctrl+Alt+P | Pause / resume all |
| Ctrl+Alt+K | Show / hide Clickue |

---

## 21. Troubleshooting

| Problem | What to try |
|---|---|
| **"Picture not found"** | Re-pick a spot with text or an icon nearby, or use a **Large** picture. Run **Show spot**. If the app's look changed, re-pick |
| **Clicks the wrong place** | **Show spot** to see what it finds. Use a Large picture if there are look-alikes, or **search only an area** (watchers). Make sure nothing covers the target |
| **Job shows Waiting** | It's due but can't click: the screen is locked or disconnected, you're using the mouse, or the target is covered. Check Activity for the reason |
| **Missed while I was away** | The screen was locked or the session disconnected; see [section 18](#18-locked-screens-remote-desktop-and-virtual-machines) |
| **Watcher says "Can't tell: Clickue window open"** | Minimize Clickue or send it to the tray |
| **Watcher clicked once and never again** | *Click only once* is waiting for the picture to come back (or go away). Untick it to keep clicking |
| **Watcher clicks on a flicker** | Raise *checks in a row* to 3, or check less often |
| **Watcher never sees the change** | **Check now** while the picture is showing. Re-draw a tighter box around the most distinctive part. If the colour or text changes, that counts as "gone" |
| **A chain stops at a step** | Activity shows *step N: timeout…*. Re-draw that picture while its screen is showing, or raise *Wait up to* |
| **Other jobs were late** | A chain was waiting; jobs take turns using the mouse. Shorten the chain's time limits |
| **Typed text goes to the wrong place** | Add a **Click a spot** step on the field (and a short **Wait**) before **Type text** |
| **A hotkey doesn't work** | Another program uses it. Choose another in Preferences → Hotkeys; the log mentions it |
| **Alerts don't arrive** | **Send a test alert** and read the error. Check the URL / token / chat id, that you messaged your Telegram bot first, and internet access |
| **"Picture matching needs opencv…"** (running from source) | Run `scripts\Start Clickue.bat`, or `pip install -r requirements.txt` |
| **Lost jobs or want to undo a change** | ☰ Menu → **Backups…** → Restore |
| **Start completely fresh** | ☰ Menu → Uninstall… (offers a backup first), then reinstall |

---

## 22. FAQ

**Does Clickue work while the screen is locked?**
No program can click on a locked Windows screen. See
[section 18](#18-locked-screens-remote-desktop-and-virtual-machines) for how to keep a session
active safely.

**Does it record or send my screen anywhere?**
No. Pictures are compared in memory on your computer, and only the small pictures you save
for your jobs are stored, in your data folder. The only network traffic is the phone alerts
you set up yourself.

**Can it record and replay a whole macro?**
Not as a recording, but a multi-step job or a click chain does the same job and is more
reliable, because it finds each spot by its picture and waits for each screen.

**Can two jobs click at the same time?**
No. Jobs take turns, so clicks never collide. A job that comes due while another is busy
clicks right after.

**Will it use a lot of CPU?**
Scheduled clicks use almost nothing between clicks. Watchers do a short picture search on each
check; check less often, use a smaller picture, or **search only an area** to make them
lighter.

**Can I use it on several monitors?**
Yes. Picking, drawing boxes and searching cover all monitors.

**Can I share jobs with someone else?**
Export them and send the file. Their screens may look different, so they should use **Show
spot** and re-pick any spot that isn't found.

---

## 23. Getting help and suggesting ideas

- 💡 **Have an idea?** [Suggest a feature](https://github.com/jnssylvest/clickue/issues/new?template=feature_request.yml).
- 🐞 **Found a bug?** [Report it](https://github.com/jnssylvest/clickue/issues/new?template=bug_report.yml)
  with the steps and the relevant log lines (☰ Menu → **Open log file**). Remove anything
  private first: names, paths, webhook URLs and tokens.
- 💬 **Questions, or want to share how you use Clickue?** [Discussions](https://github.com/jnssylvest/clickue/discussions).
- 📣 **New versions** are announced in
  [Discussions → Announcements](https://github.com/jnssylvest/clickue/discussions/categories/announcements).
