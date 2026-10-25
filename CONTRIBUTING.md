# Contributing to Clickue

Thanks for your interest! There are three easy ways to help.

Clickue is vibe-coded and was developed with substantial AI assistance; see
[SECURITY.md](SECURITY.md). Reviews of the code, especially of anything security-related, are
very welcome.

## 💡 Suggest a feature
- Open a **[Feature idea](https://github.com/jnssylvest/clickue/issues/new?template=feature_request.yml)**.
  The form asks what you'd like, why, and how you picture it working.
- Already suggested? Add a 👍 reaction to that issue instead. Reactions help decide what comes
  next.
- To talk an idea through first, start a thread in
  **[Discussions → Ideas](https://github.com/jnssylvest/clickue/discussions)**.

## 🐞 Report a bug
- Open a **[Bug report](https://github.com/jnssylvest/clickue/issues/new?template=bug_report.yml)**
  with the steps to reproduce it, your version (☰ Menu → About) and the relevant log lines
  (☰ Menu → Open log file). **Remove anything private first**, and never include webhook URLs,
  bot tokens, passwords or screenshots that show them.

## 🔒 Report a security problem
- Please report it privately, as described in [SECURITY.md](SECURITY.md), not in a public
  issue.

## 🛠️ Contribute code
- Read the [developer guide](docs/DEVELOPER_GUIDE.md). It covers the architecture, the
  data-compatibility rules and the tests.
- Run `python tests/test_watchers.py`, `python tests/test_features.py`,
  `python tests/test_click_spot.py`, `python tests/test_workflows.py` and
  `python tests/check_release.py` before opening a pull request.
- Follow the security rules in the developer guide (section 11): no code execution from data,
  no new network destinations, secrets never in logs or exports, limits on every loop.
- Keep saved data compatible: add new settings with defaults; never rename or remove existing
  ones.

Please be kind and constructive. Everyone here is helping in their spare time.
