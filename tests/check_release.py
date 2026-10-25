"""Release checks for the repository (no network, no display): documentation links and
pictures resolve, version and changelog agree, the AI-assistance disclosure is where it must
be, planned features are labelled as planned, nothing private or secret is in public files,
and the GitHub workflow keeps least-privilege permissions and pinned actions.

    python tests/check_release.py          Expect: RESULT N/N
"""
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
R = []


def ok(name, cond, info=""):
    R.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name, ("" if cond else info))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def slug(heading):
    """GitHub's anchor for a heading (it drops punctuation and symbols, keeps letters, digits,
    spaces -> hyphens, and the emoji variation selector U+FE0F)."""
    h = re.sub(r"<[^>]+>", "", heading).strip().lower()
    h = re.sub(r"[^\w\- \ufe0f]", "", h, flags=re.UNICODE)
    return h.replace(" ", "-")


DOCS = ["README.md", "FEATURES.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "CLAUDE.md",
        "docs/GUIDE.md", "docs/USER_GUIDE.md", "docs/DEVELOPER_GUIDE.md"]

# ---- links and anchors
anchors = {}
for d in DOCS:
    text = read(d)
    seen = {}
    names = set()
    for m in re.finditer(r"^#{1,6} (.+)$", text, re.M):
        s = slug(m.group(1))
        n = seen.get(s, 0)
        seen[s] = n + 1
        names.add(s if n == 0 else f"{s}-{n}")
    anchors[d] = names

bad = []
for d in DOCS:
    text = read(d)
    base = os.path.dirname(d)
    text_no_code = re.sub(r"```.*?```", "", text, flags=re.S)
    for m in re.finditer(r"\]\(([^)\s]+)\)|<a href=\"([^\"]+)\"|<img src=\"([^\"]+)\"", text_no_code):
        link = m.group(1) or m.group(2) or m.group(3)
        if re.match(r"^(https?:|mailto:)", link) or link.startswith("../../"):
            continue
        path, _, frag = link.partition("#")
        frag = __import__("urllib.parse").parse.unquote(frag)
        target = os.path.normpath(os.path.join(base, path)) if path else d
        if path and not os.path.exists(os.path.join(ROOT, target)):
            bad.append(f"{d}: {link} (missing file)")
            continue
        if frag and target in anchors and frag not in anchors[target]:
            bad.append(f"{d}: {link} (no such heading)")
ok("every local link and #anchor in the docs resolves", not bad, "\n  " + "\n  ".join(bad))

guide = read("docs/GUIDE.md")
used = set(re.findall(r"images/guide/([\w\-]+\.png)", guide + read("README.md")))
have = {n for n in os.listdir(os.path.join(ROOT, "docs/images/guide")) if n.endswith(".png")}
ok("every guide picture exists", used <= have, used - have)
ok("every guide picture is used", have <= used, have - used)

# ---- version and changelog
src = read("src/clickue.py")
version = re.search(r'^VERSION = "([^"]+)"', src, re.M).group(1)
top = re.search(r"^## (\d+\.\d+)", read("CHANGELOG.md"), re.M)
ok("CHANGELOG starts with this version", top and top.group(1) == version, (top and top.group(1), version))
ok("the guide names this version", f"Clickue {version}" in guide)

# ---- the disclosure
CORE = ("vibe-coded and was developed with substantial AI assistance", "does not guarantee",
        "protect notification credentials")
for rel in ("README.md", "docs/GUIDE.md", "docs/USER_GUIDE.md", "SECURITY.md",
            "installer/before-install.txt", ".github/workflows/build.yml"):
    t = read(rel)
    ok(f"disclosure in {rel}", all(c in t.replace("\n> ", " ").replace("\n", " ") for c in CORE))
ok("disclosure in the app (About / Help)", all(c in src.replace('"\n              "', "")
                                                .replace('" "', "") for c in CORE[:1]) and "DISCLOSURE" in src)
for rel in ("README.md", "docs/GUIDE.md"):
    first = "\n".join(read(rel).splitlines()[:40])
    ok(f"disclosure near the top of {rel}", "vibe-coded" in first)
for rel in ("FEATURES.md", "docs/DEVELOPER_GUIDE.md", "CLAUDE.md", "CONTRIBUTING.md"):
    t = read(rel)
    ok(f"{rel} mentions the disclosure or links to it", "vibe-coded" in t or "SECURITY.md" in t)
ok("guide has a responsible-use section with the disclosure",
   "## 24. Security, privacy and responsible use" in guide
   and "vibe-coded" in guide.split("## 24.")[1].split("## 25.")[0])
for word in ("professionally audited", "certified"):
    for rel in ("README.md", "SECURITY.md", "docs/GUIDE.md"):
        t = " ".join(read(rel).split())
        claims = [t[max(0, m.start() - 80):m.end()] for m in re.finditer(word, t)
                  if not re.search(r"\b(not|n't|no|isn't|hasn't)\b", t[max(0, m.start() - 80):m.start()])]
        ok(f"{rel} never claims to be {word}", not claims, claims)
for rel in DOCS:
    t = " ".join(read(rel).lower().split())
    claims = [t[max(0, m.start() - 60):m.end()] for m in
              re.finditer(r"\b(is|are) (completely |fully |100% )?(secure|vulnerability-free|bug-free)\b", t)
              if not re.search(r"\b(never|not|n't|no|nor)\b", t[max(0, m.start() - 60):m.start()])]
    ok(f"{rel} makes no absolute security claim", not claims, claims)

# ---- planned features are labelled as planned
for rel in ("README.md", "FEATURES.md", "docs/GUIDE.md", "docs/USER_GUIDE.md"):
    lines = read(rel).splitlines()
    section = ""
    marked = []
    for k, l in enumerate(lines):
        if l.startswith("#"):
            section = l
        near = " ".join(lines[max(0, k - 3):k + 4])
        marked.append(bool(re.search(r"planned|not (available|in this version)|not yet", near + section, re.I)))
    for kw in ("OCR", "UI Automation", "browser element"):
        bad_l = [l for l, m in zip(lines, marked) if kw.lower() in l.lower() and not m]
        ok(f"{rel}: '{kw}' only mentioned as planned", not bad_l, bad_l)

# ---- nothing private or secret in public files
public = DOCS + ["installer/before-install.txt", "installer/clickue.iss", ".github/workflows/build.yml",
                 ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
                 "src/clickue.py"]
leaks = []
for rel in public:
    t = read(rel)
    if re.search(r"discord(app)?\.com/api/webhooks/\d{6,}/[A-Za-z0-9_\-]{30,}", t):
        leaks.append(f"{rel}: a real-looking webhook URL")
    if re.search(r"\b\d{8,10}:[A-Za-z0-9_\-]{35}\b", t):
        leaks.append(f"{rel}: a real-looking bot token")
    for w in ("portfolio", "stock market", "stocks", "proxmox", "mobaxterm", "nucbox"):
        if w in t.lower():
            leaks.append(f"{rel}: mentions '{w}'")
    if re.search(r"C:\\Users\\[A-Za-z]+\\", t) and "C:\\Users\\<" not in t:
        leaks.append(f"{rel}: a personal Windows path")
ok("no secrets or private details in public files", not leaks, leaks)
ok("the private handoff isn't in the repository",
   not any("handoff" in f.lower() for _, _, fs in os.walk(ROOT) for f in fs if ".git" not in _))

# ---- workflow: least privilege, pinned actions
wf = read(".github/workflows/build.yml")
ok("workflow: read-only by default", re.search(r"^permissions:\n  contents: read", wf, re.M))
ok("workflow: write access only in the release job",
   wf.count("contents: write") == 1 and wf.index("contents: write") > wf.index("  release:"))
uses = re.findall(r"uses: ([\w\-/]+)@([\w.]+)", wf)
ok("workflow: every action pinned to a full commit", uses and all(re.fullmatch(r"[0-9a-f]{40}", v) for _, v in uses), uses)
ok("workflow: release never runs for pull requests", "github.event_name == 'push'" in wf.split("  release:")[1])
ok("workflow: tests and security checks run before building",
   wf.index("Headless tests") < wf.index("Build Clickue.exe") and "pip_audit" in wf and "bandit" in wf)

# ---- installer and uninstall boundaries
iss = read("installer/clickue.iss")
ok("installer: only deletes the Clickue data folder, and only when asked",
   iss.count("DelTree(") == 1 and "{userappdata}\\Clickue" in iss and "MB_DEFBUTTON2" in iss)
ok("installer: removes its start-with-Windows entry", "RegDeleteValue" in iss)
ok("installer: shows the notice before installing", "InfoBeforeFile=before-install.txt" in iss)
ok("app: recursive delete only after checking the folder",
   src.count("shutil.rmtree(") == 1 and "if is_clickue_data_dir(DATA_DIR):\n                shutil.rmtree" in src)
ok("app: no eval/exec/pickle/shell=True", not re.search(r"\beval\(|\bexec\(|pickle|shell=True", src))
ok("app: no telemetry / unexpected network hosts",
   set(re.findall(r"https://([\w.\-]+)", src)) <= {"github.com", "api.telegram.org", "discord.com"})

print(f"\nRESULT {sum(R)}/{len(R)}")
sys.exit(0 if all(R) else 1)
