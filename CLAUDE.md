# Notes for AI coding sessions

Read **[docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** first. It explains the
architecture, data model, design decisions, tests, and the release process.

Essentials:
- The whole app is `src/clickue.py` (Python 3 + Tkinter, Windows via ctypes).
- **Don't break saved data:** never rename or remove job/settings keys. Add new ones with
  defaults in `new_job()` / `DEFAULT_SETTINGS` (and `RUNTIME_KEYS` for runtime-only fields).
- Never call Tk from background threads. Use `self.log()` or `self.cmdq`.
- No `grab_set()`. Popups close on click-outside (see `close_on_click_outside`).
- Restore the main window with `restore_main()`, never `root.state("normal")`.
- Before every release, run `python tests/test_watchers.py`,
  `python tests/test_features.py` and `python tests/test_click_spot.py` (all must pass).
- **Release** = bump `VERSION` in `src/clickue.py`, add a `CHANGELOG.md` entry, update the
  docs if behaviour changed, then push to `main`. The GitHub workflow builds the exe, the
  portable zip and the installer, and creates the `v<VERSION>` release itself. Don't push tags;
  this session's proxy blocks them.
- Keep the docs in sync: `README.md` (overview, use cases, warnings), `FEATURES.md`
  (complete list), `docs/USER_GUIDE.md` (how to), `CHANGELOG.md`.
- Public docs must stay general: no personal details about the owner's own use.
