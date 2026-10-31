"""Capabilities NoEfforts must never gain (S4, D54), checked statically: no mailbox, IMAP or
Gmail client (R7.5: the legacy bot read the user's mail for verification codes, U1, U3, U18;
narrowed by the owner in D101 to one read-only Gmail reader, INBOX_READING below), and
no screenshot, video, trace, HAR or captured browser session in the code that drives a page
(R11.4: the legacy bot kept a full-page screenshot of every form it filled, U11).

Python is read with `ast` (never imported): comments and docstrings are prose and never match;
string constants are checked as exact identifiers, so `traceback` or ".pdf" in an upload list
never does; a text built from literals (an f-string, a `+` chain, a `"".join([...])`) is checked
as one text, and a text that is itself code (a `python -c` or `node -e` script, an `exec`) is
parsed and checked the same way. JavaScript is read as written, comments included (a comment
naming a capture call fails too: rewording it is cheaper than a parser that can be fooled).
Scope: every Python, JavaScript and shell file outside the frontend, the virtualenv and
node_modules (this file excepted: its samples are strings), the Dockerfiles, compose files and
CI workflows, every dependency manifest and the pytest configuration; for mail, the frontend's
own source too. The frontend's Playwright tests (frontend/e2e, playwright.config.ts) drive the
product UI, not an employer page, and are outside R11.4.

A static guard is a tripwire for capabilities added by accident, not a proof against code
written to evade it: a name or an option built from data at run time outside the code that
drives a page, or a mail protocol written by hand over a raw socket, is not seen."""

import ast
import json
import os
import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", ".venv", "node_modules", "frontend", "__pycache__", ".next"}
JS_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}

# ---------------------------------------------------------------------------------------------
# R7.5: mail
MAIL_MODULES = {
    "imaplib", "poplib", "smtplib", "smtpd", "nntplib", "mailbox", "email", "imapclient",
    "imap_tools", "aioimaplib", "aiosmtplib", "aiosmtpd", "exchangelib", "o365", "msal",
    "msgraph", "msgraph_core", "googleapiclient", "google", "google_auth_oauthlib",
    "google_auth_httplib2", "oauth2client", "httplib2", "gmail", "simplegmail", "ezgmail",
    "yagmail", "mailparser", "flanker", "sendgrid", "mailjet_rest", "postmarker", "redmail",
    "emails", "fastapi_mail", "flask_mail", "imbox", "jmapc", "pyzmail", "zmail", "mailgun",
    "nylas", "boto3", "botocore",
}  # fmt: skip
MAIL_WORDS = ("imap", "smtp", "pop3", "mail", "gmail", "outlook", "exchangelib", "msgraph", "o365",
              "jmap", "nylas")  # fmt: skip
# pydantic's EmailStr syntax check; the stdlib's header and date helpers; MIME type tables.
MAIL_ALLOWED = {"email_validator", "email-validator", "email.utils", "email.headerregistry",
                "mailcap", "media-types"}  # fmt: skip
EMAIL_HELPERS = {"utils", "headerregistry"}  # "from email import utils"
MAIL_STRINGS = re.compile(
    r"\b(imap|pop3?|smtp)s?(-[a-z0-9-]+)?\.[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}\b|"
    r"gmail\.googleapis\.com|googleapis\.com/(batch/)?gmail|/gmail/v1/|/auth/gmail\b|"
    r"\bmail\.google\.com\b|outlook\.office(365)?\.com|graph\.microsoft\.com|"
    r"/me/(messages|mailfolders)\b|\bMail\.(Read|ReadWrite|ReadBasic|Send)(\.(All|Shared))?\b|"
    r"\b(imaps?|pop3s?|smtps?)://|\bjmap\b|urn:ietf:params:jmap|\bnylas\b|"
    r"(^|[\s/'\"])(fetchmail|getmail\d?|offlineimap|mbsync|isync|neomutt|mutt|himalaya|notmuch|"
    r"mailx|s-nail|msmtp)(\s|$)",
    re.I,
)
OS_MAIL_PACKAGES = re.compile(
    r"(fetchmail|getmail\d?|mutt|neomutt|offlineimap|isync|mailutils|msmtp|dovecot\S*|postfix|"
    r"exim4)"
)
NPM_MAIL = {"imapflow", "imap", "node-imap", "imap-simple", "emailjs-imap-client", "mailparser",
            "nodemailer", "smtp-server", "googleapis", "@googleapis/gmail", "@azure/msal-node",
            "@microsoft/microsoft-graph-client", "nylas"}  # fmt: skip
IMPORT_CALLS = {"__import__", "import_module", "find_spec", "resolve_name", "run_module",
                "run_path"}  # fmt: skip
JS_IMPORT = re.compile(
    r"\brequire\(\s*[\"'`]([^\"'`]+)[\"'`]\s*\)|\bfrom\s+[\"'`]([^\"'`]+)[\"'`]|"
    r"\bimport\(\s*[\"'`]([^\"'`]+)[\"'`]\s*\)|^\s*import\s+[\"'`]([^\"'`]+)[\"'`]",
    re.M,
)
PY_IMPORT = re.compile(
    r"\bimport\s+([\w.]+)|\bfrom\s+([\w.]+)\s+import\b|__import__\(\s*['\"]([\w.]+)"
)

# ---------------------------------------------------------------------------------------------
# R11.4: capture
CAPTURE_ATTRS = {
    "screenshot", "tracing", "start_tracing", "stop_tracing", "new_cdp_session",
    "new_browser_cdp_session", "route_from_har", "to_have_screenshot",
    # a captured session: cookies and storage written to disk, a profile kept, raw CDP
    "storage_state", "launch_persistent_context", "connect_over_cdp",
}  # fmt: skip
# Words that are data elsewhere (DocumentKind.pdf, a job's video link, cookie settings): capture
# where a page runs, and in execution code.
PAGE_ATTRS = {"pdf", "video", "cookies", "add_cookies", "__getattribute__"}
CAPTURE_KWARGS = {
    "record_video_dir", "record_video_size", "record_har_path", "record_har_content",
    "record_har_mode", "record_har_omit_content", "record_har_url_filter", "traces_dir",
    "screenshots", "snapshots", "storage_state", "user_data_dir", "devtools",
}  # fmt: skip
CAPTURE_IMPORTS = {"Video", "Tracing", "CDPSession"}
CAPTURE_FLAGS = (
    r"--(screenshot|print-to-pdf|dump-dom|enable-tracing|trace-startup|trace-to-file|log-net-log|"
    r"net-log|enable-logging|remote-debugging-(port|pipe|address)|auto-open-devtools-for-tabs|"
    r"user-data-dir)\b"
)
# Playwright's protocol log prints every filled value; the inspector keeps a debugger open.
PW_DEBUG = r"\bPWDEBUG\b|(^|[\"'`=:\s])pw:[a-z*]|(^|[\"'`])pw\*"
CAPTURE_STRINGS = re.compile(
    r"^(screenshot|tracing|start_tracing|stop_tracing|new_cdp_session|new_browser_cdp_session|"
    r"route_from_har|storage_state|launch_persistent_context|connect_over_cdp|record_video_dir|"
    r"record_video_size|record_har_path|record_har_content|record_har_mode|"
    r"record_har_omit_content|record_har_url_filter|traces_dir|user_data_dir)$|"
    r"\b(Page\.(captureScreenshot|startScreencast|printToPDF|captureSnapshot)|Tracing\.start|"
    r"HeapProfiler\.takeHeapSnapshot|DOMSnapshot\.captureSnapshot)\b|"
    rf"(?<![\w-]){CAPTURE_FLAGS}|\bplaywright (screenshot|pdf)\b|{PW_DEBUG}|"
    r"\b(html2canvas|toDataURL|toBlob|getDisplayMedia|captureStream|MediaRecorder|html-to-image|"
    r"htmlToImage|dom-to-image|domtoimage)\b"
)
BROWSER_ONLY_STRINGS = re.compile(r"^(pdf|video|screencast|cookies)$")
BROWSER_FILES = ("backend/app/modules/preparation/gh_readonly.py",
                 "compose_tests/run_execution_test.py")  # fmt: skip
JS_CAPTURE = re.compile(
    r"\.screenshot\b|\[\s*[\"'`](screenshot|tracing|pdf)[\"'`]\s*\]|\.tracing\b|recordVideo|"
    r"recordHar|tracesDir|startTracing|captureScreenshot|startScreencast|printToPDF|"
    r"\.video\s*\(|\.pdf\s*\(|newCDPSession|newBrowserCDPSession|routeFromHAR|connectOverCDP|"
    r"launchPersistentContext|storageState|userDataDir|\.cookies\s*\(|addCookies|"
    r"[\"'`]?\bdevtools[\"'`]?\s*:|"
    rf"(?<![\w-]){CAPTURE_FLAGS}|{PW_DEBUG}|html2canvas|toDataURL|toBlob|getDisplayMedia|"
    r"MediaRecorder|html-to-image|htmlToImage|dom-to-image|domtoimage"
)
JS_LIKE = re.compile(r"\b(await|const|let|function)\b|=>|\.then\(")
INFRA_CAPTURE = re.compile(
    r"\bDEBUG[\"']?\s*(=|:\s*|\s+)[\"']?(\S*pw[:*]|\*)|"
    rf"{PW_DEBUG}|(?<![\w-]){CAPTURE_FLAGS}|\bplaywright (screenshot|pdf)\b"
)
INSTALL = re.compile(
    r"\b(pip[\d.]*|uv pip|uv|npm|yarn( global)?|pnpm|bun|apt-get|apt|apk|yum|dnf)"
    r"((\s+-[-\w=]+)*)\s+(install|add|i)\b(?P<what>.*)"
)


def _walk(root: Path, pred, skip=SKIP_DIRS) -> list[Path]:
    me = Path(__file__).resolve()
    out = []
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in skip]  # never descend into them
        for name in files:
            p = Path(d) / name
            if p.resolve() != me and pred(p):
                out.append(p)
    return sorted(out)


def py_files(root: Path = REPO) -> list[Path]:
    return _walk(root, lambda p: p.suffix == ".py")


def js_files(root: Path = REPO) -> list[Path]:
    return _walk(root, lambda p: p.suffix in JS_SUFFIXES)


def frontend_sources(root: Path = REPO) -> list[Path]:
    """The frontend's own code, read for mail only (R7.5); its e2e tests are outside R11.4."""
    src = root / "frontend" / "src"
    skip = {"node_modules", ".next"}
    return _walk(src, lambda p: p.suffix in JS_SUFFIXES, skip) if src.exists() else []


def infra_files(root: Path = REPO) -> list[Path]:
    named = [p for p in (root / "frontend/Dockerfile",) if p.exists()]
    return sorted(
        named
        + _walk(
            root,
            lambda p: (
                p.name.startswith("Dockerfile")
                or p.suffix in (".sh", ".yml", ".yaml")
                or p.name.startswith("docker-compose")
            ),
        )
    )


def manifests(root: Path = REPO) -> dict[str, list[Path]]:
    found = {"pyproject": [], "requirements": [], "package": []}
    for p in _walk(root, lambda p: p.name in ("pyproject.toml", "package.json")
                   or re.fullmatch(r"requirements.*\.txt", p.name)):  # fmt: skip
        kind = {"pyproject.toml": "pyproject", "package.json": "package"}.get(
            p.name, "requirements"
        )
        found[kind].append(p)
    if (root / "frontend/package.json").exists():
        found["package"].append(root / "frontend/package.json")
    return found


def _docstrings(tree) -> set[int]:
    ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = n.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant):
                ids.add(id(b[0].value))
    return ids


def _fold(n) -> str | None:
    """The text of a literal built at write time: a constant, an f-string (each value read as
    "X"), a `+` chain, a `"sep".join([...])` of literals; None for anything else."""
    if isinstance(n, ast.Constant) and isinstance(n.value, (str, bytes)):
        v = n.value
        return v.decode("utf-8", "replace") if isinstance(v, bytes) else v
    if isinstance(n, ast.JoinedStr):
        return "".join(_fold(x) or "X" for x in n.values)
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
        a, b = _fold(n.left), _fold(n.right)
        return None if a is None and b is None else (a or "X") + (b or "X")
    if (
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "join"
        and isinstance(n.func.value, ast.Constant)
        and isinstance(n.func.value.value, str)
        and n.args
        and isinstance(n.args[0], (ast.List, ast.Tuple))
    ):
        return n.func.value.value.join(_fold(x) or "X" for x in n.args[0].elts)
    return None


def _texts(tree):
    """(line, text) for every literal text that is not a docstring."""
    docs = _docstrings(tree)
    for n in ast.walk(tree):
        if id(n) in docs or not isinstance(n, (ast.Constant, ast.JoinedStr, ast.BinOp, ast.Call)):
            continue
        v = _fold(n)
        if v is not None:
            yield n.lineno, v


def _embedded(tree):
    """Texts that are themselves Python code (a `python -c` script, an exec)."""
    seen = set()
    for line, v in _texts(tree):
        if v in seen or len(v) < 6 or ("(" not in v and "import" not in v):
            continue
        seen.add(v)
        try:
            sub = ast.parse(v)
        except (SyntaxError, ValueError):
            continue
        if any(isinstance(x, (ast.Call, ast.Import, ast.ImportFrom)) for x in ast.walk(sub)):
            yield line, sub


def _mail_name(name: str) -> bool:
    low = name.lower()
    if low in MAIL_ALLOWED or low.split(".")[0] in MAIL_ALLOWED:
        return False
    root = low.split(".")[0]
    return root in MAIL_MODULES or any(w in root for w in MAIL_WORDS)


def _import_aliases(tree) -> set[str]:
    """Local names bound to the import functions ("from importlib import import_module as
    im")."""
    names = set(IMPORT_CALLS)
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and (n.module or "") in (
            "importlib",
            "importlib.util",
            "pkgutil",
            "runpy",
        ):
            names |= {a.asname or a.name for a in n.names if a.name in IMPORT_CALLS}
    return names


def _imported(n, calls: set[str]) -> list[str] | None:
    """Modules an import statement or an import call names; None for a computed name."""
    if isinstance(n, ast.Import):
        return [a.name for a in n.names]
    if isinstance(n, ast.ImportFrom):
        if not n.module or n.level:
            return []
        if n.module == "email" and {a.name for a in n.names} <= EMAIL_HELPERS:
            return []
        return [n.module]
    if isinstance(n, ast.Call):
        f = n.func
        name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
        if name in calls:
            args = list(n.args[:1]) + [
                k.value for k in n.keywords if k.arg in ("name", "path_name")
            ]
            if not args:
                return None
            v = _fold(args[0])
            return [v] if v is not None and "X" not in v else None
    return []


def _mail_tree(tree, where: str, computed_imports_fail: bool, depth: int = 0) -> list[str]:
    out = []
    calls = _import_aliases(tree)
    for n in ast.walk(tree):
        mods = _imported(n, calls)
        if mods is None:
            if computed_imports_fail:  # fail closed: an import named at run time
                out.append(f"{where}:{getattr(n, 'lineno', 0)} computed import")
            continue
        out += [f"{where}:{n.lineno} import {m}" for m in mods if _mail_name(m)]
    for line, v in _texts(tree):
        if MAIL_STRINGS.search(v):
            out.append(f"{where}:{line} mail endpoint {v[:40]!r}")
    if depth < 2:
        for line, sub in _embedded(tree):
            out += _mail_tree(sub, f"{where}:{line}(code in a string)", True, depth + 1)
    return out


def _js_package(name: str) -> bool:
    """A package a script imports (not a file of its own, such as "./EmailField")."""
    return not name.startswith((".", "/", "@/", "~/")) and _npm_mail(name)


def _mail_js(src: str, where: str) -> list[str]:
    out = [f"{where}:{src[: m.start()].count(chr(10)) + 1} imports {name}"
           for m in JS_IMPORT.finditer(src) for name in m.groups()
           if name and _js_package(name)]  # fmt: skip
    out += [f"{where}:{i} {line.strip()[:60]}" for i, line in enumerate(src.splitlines(), 1)
            if MAIL_STRINGS.search(line)]  # fmt: skip
    return out


def mail_hits(paths, *, computed_imports_fail=False) -> list[str]:
    out = []
    for p in paths:
        src = Path(p).read_text()
        if Path(p).suffix in JS_SUFFIXES:
            out += _mail_js(src, str(p))
            continue
        out += _mail_tree(ast.parse(src, str(p)), str(p), computed_imports_fail)
    return out


def _drives_a_page(tree, src: str) -> bool:
    plays = any(
        (isinstance(n, ast.ImportFrom) and (n.module or "").startswith("playwright"))
        or (isinstance(n, ast.Import) and any(a.name.startswith("playwright") for a in n.names))
        for n in ast.walk(tree)
    )
    return plays or "browser_session" in src


def _computed(n) -> bool:
    v = _fold(n)
    return v is None or "X" in v


LOOKUPS = ("getattr", "attrgetter", "methodcaller")


def _capture_tree(tree, where: str, page: bool, strict: bool, depth: int = 0) -> list[str]:
    out = []
    called = {id(c.func) for c in ast.walk(tree) if isinstance(c, ast.Call)}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and (
            n.attr in CAPTURE_ATTRS or (strict and n.attr in PAGE_ATTRS)
        ):
            out.append(f"{where}:{n.lineno} .{n.attr}")
        elif isinstance(n, ast.keyword) and n.arg in CAPTURE_KWARGS:
            out.append(f"{where}:{n.value.lineno} {n.arg}=")
        elif isinstance(n, ast.ImportFrom) and (n.module or "").startswith("playwright"):
            out += [f"{where}:{n.lineno} import {a.name}" for a in n.names
                    if a.name in CAPTURE_IMPORTS]  # fmt: skip
            if re.search(r"tracing|video|har", n.module):
                out.append(f"{where}:{n.lineno} from {n.module}")
        elif not page:
            continue
        # Where a page runs, a name built at run time could reach the page: fail closed.
        elif isinstance(n, ast.Call):
            f = n.func
            name = (
                f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            )
            at = 1 if name == "getattr" else 0
            if name in LOOKUPS and len(n.args) > at and _computed(n.args[at]):
                out.append(f"{where}:{n.lineno} computed {name}")
            elif (
                isinstance(f, ast.Name)  # the built-ins, not re.compile
                and name in ("exec", "eval", "compile")
                and n.args
                and _computed(n.args[0])
            ):
                out.append(f"{where}:{n.lineno} {name} of a built text")
        elif isinstance(n, ast.Name) and n.id in LOOKUPS and id(n) not in called:
            out.append(f"{where}:{n.lineno} {n.id} as a value")  # "g = getattr"
    for line, v in _texts(tree):
        if CAPTURE_STRINGS.search(v) or (strict and BROWSER_ONLY_STRINGS.search(v)):
            out.append(f"{where}:{line} {v[:40]!r}")
        elif JS_LIKE.search(v) and JS_CAPTURE.search(v):
            out.append(f"{where}:{line} script {v[:40]!r}")  # a `node -e` script
    if depth < 2:
        for line, sub in _embedded(tree):
            out += _capture_tree(sub, f"{where}:{line}(code in a string)", True, True, depth + 1)
    return out


def capture_hits(paths, browser_files=()) -> list[str]:
    out = []
    browser_files = {Path(x).resolve() for x in browser_files}
    for p in paths:
        src = Path(p).read_text()
        tree = ast.parse(src, str(p))
        page = _drives_a_page(tree, src)
        strict = page or Path(p).resolve() in browser_files or "/modules/execution/" in str(p)
        out += _capture_tree(tree, str(p), page, strict)
    return out


def js_hits(paths) -> list[str]:
    out = []
    for p in paths:
        for i, line in enumerate(Path(p).read_text().splitlines(), 1):
            if JS_CAPTURE.search(line):
                out.append(f"{p}:{i} {line.strip()[:60]}")
    return out


def _dist(name: str) -> str:  # PEP 503
    return re.sub(r"[-_.]+", "-", name).lower()


def _mail_dist(name: str) -> bool:
    n = _dist(name)
    return n not in MAIL_ALLOWED and (
        n.replace("-", "_") in MAIL_MODULES
        or n in {"google-api-python-client", "google-auth", "msgraph-sdk", "mail-parser"}
        or any(w in n for w in MAIL_WORDS)
    )


def _capture_dist(name: str) -> bool:
    return _dist(name).startswith("pytest-playwright")


def _npm_mail(name: str) -> bool:
    base = name.rsplit("/", 1)[-1].lower()
    return name in NPM_MAIL or (base not in MAIL_ALLOWED and any(w in base for w in MAIL_WORDS))


def _addopts_capture(addopts) -> bool:
    text = " ".join(addopts) if isinstance(addopts, list) else str(addopts or "")
    return bool(re.search(r"--(tracing|screenshot|video|output)\b", text))


def _requirement(line: str) -> str:
    return re.split(r"[\s\[<>=!~;@]", line.strip(), maxsplit=1)[0]


def dependency_hits(root: Path = REPO) -> list[str]:
    out = []
    found = manifests(root)
    for pyproject in found["pyproject"]:
        pp = tomllib.loads(pyproject.read_text())
        project = pp.get("project", {})
        declared = list(project.get("dependencies", []))
        declared += [d for g in project.get("optional-dependencies", {}).values() for d in g]
        for group in pp.get("dependency-groups", {}).values():
            declared += [d for d in group if isinstance(d, str)]
        out += [f"{pyproject} {_requirement(d)}" for d in declared
                if _mail_dist(_requirement(d)) or _capture_dist(_requirement(d))]  # fmt: skip
        addopts = pp.get("tool", {}).get("pytest", {}).get("ini_options", {}).get("addopts")
        if _addopts_capture(addopts):
            out.append(f"{pyproject} pytest addopts")
        lock = pyproject.with_name("uv.lock")
        if lock.exists():
            for pkg in tomllib.loads(lock.read_text()).get("package", []):
                if _mail_dist(pkg["name"]) or _capture_dist(pkg["name"]):
                    out.append(f"{lock} {pkg['name']}")
    for req in found["requirements"]:
        for line in req.read_text().splitlines():
            name = _requirement(line)
            if name and not name.startswith("#") and (_mail_dist(name) or _capture_dist(name)):
                out.append(f"{req} {name}")
    for name in ("pytest.ini", "setup.cfg", "tox.ini"):
        for cfg in _walk(root, lambda p, name=name: p.name == name):
            if re.search(r"(?m)^\s*addopts\s*=.*--(tracing|screenshot|video|output)\b",
                         cfg.read_text()):  # fmt: skip
                out.append(f"{cfg} addopts")
    for pkg_json in found["package"]:
        pkg = json.loads(pkg_json.read_text())
        for section in ("dependencies", "devDependencies", "optionalDependencies"):
            out += [f"{pkg_json} {n}" for n in pkg.get(section, {}) if _npm_mail(n)]
        lock = pkg_json.with_name("package-lock.json")
        if lock.exists():
            for path in json.loads(lock.read_text()).get("packages", {}):
                name = path.rsplit("node_modules/", 1)[-1]
                if path and _npm_mail(name):
                    out.append(f"{lock} {name}")
    return out


def _bad_install(word: str) -> bool:
    if word.startswith("-"):
        return False
    name = re.split(r"[=<>@]", word.lstrip("@"))[0] or word
    return bool(
        _mail_dist(name)
        or _npm_mail(word)
        or OS_MAIL_PACKAGES.fullmatch(word)
        or _capture_dist(name)
    )


def infra_hits(paths) -> list[str]:
    out = []
    for p in paths:
        joined = re.sub(r"\\\n", " ", Path(p).read_text())  # a command continued over lines
        for i, line in enumerate(joined.splitlines(), 1):
            code = re.sub(r"(^|\s)#.*$", "", line)  # comments
            if not code.strip():
                continue
            flat = re.sub(r"[\[\]\",]", " ", code)  # RUN ["pip", "install", "x"]
            mods = [m for g in PY_IMPORT.findall(code) for m in g if m]
            if (
                INFRA_CAPTURE.search(code)
                or MAIL_STRINGS.search(code)
                or any(_mail_name(m) for m in mods)
                or (JS_LIKE.search(code) and JS_CAPTURE.search(code))
            ):
                out.append(f"{p}:{i} {code.strip()[:60]}")
            for m in INSTALL.finditer(flat):
                words = re.findall(r"[@\w./-]+", re.split(r"&&|;|\|", m.group("what"))[0])
                out += [f"{p}:{i} installs {w}" for w in words if _bad_install(w)]
    return out


# ---------------------------------------------------------------------------------------------


def test_the_scanned_tree_is_the_repository():
    """Each guard reads the files it is responsible for (a scope that shrank would pass)."""
    py = {str(p.relative_to(REPO)) for p in py_files()}
    for f in ("backend/app/modules/execution/browser.py", "backend/app/main.py",
              "backend/scripts/e2e_worker.py", "backend/tests/conftest.py",
              "backend/tests/execution_harness.py", "fixtures/ats_receiver/receiver.py",
              "compose_tests/run_execution_test.py", *BROWSER_FILES):  # fmt: skip
        assert f in py, f
    assert any(f.startswith("backend/migrations/versions/") for f in py)
    assert not any(f.startswith(("frontend/", "backend/.venv/")) for f in py)
    js = {str(p.relative_to(REPO)) for p in js_files()}
    assert {"browser/launcher.js", "compose_tests/browser_probe.js"} <= js
    front = {str(p.relative_to(REPO)) for p in frontend_sources()}
    assert "frontend/src/lib/api.ts" in front and not any("/e2e/" in f for f in front)
    infra = {str(p.relative_to(REPO)) for p in infra_files()}
    for f in ("docker-compose.yml", "docker-compose.execution-test.yml", "browser/Dockerfile",
              "backend/Dockerfile", "frontend/Dockerfile", ".github/workflows/ci.yml",
              "scripts/docker-smoke.sh"):  # fmt: skip
        assert f in infra, f
    found = {k: {str(p.relative_to(REPO)) for p in v} for k, v in manifests().items()}
    assert "backend/pyproject.toml" in found["pyproject"]
    assert "frontend/package.json" in found["package"]


# D94: email reminders to the account owner are authorized, outbound SMTP only. These files may
# import exactly these names: the standard library's SMTP client and message classes, and the
# local test sink. Reading mail (IMAP, POP, a mailbox, Gmail or any provider's API) stays
# forbidden everywhere, these files included.
OUTBOUND_MAIL = {
    "backend/app/modules/mail/transport.py": {"smtplib", "email.message"},
    "backend/app/modules/mail/service.py": {"email.message"},
    "fixtures/ats_receiver/mail_sink.py": {"email"},
    "fixtures/ats_receiver/receiver.py": {"mail_sink"},
    "backend/tests/test_email_reminders.py": {"mail_sink"},
}


# D101 (the owner's instruction of 2026-10-31, reversing R7.5 for one purpose): reading the
# owner's own Gmail, read-only, through Google's REST API, is allowed in these files only and
# only for these names: the API's message path, its host and the read-only scope. No mail
# library, IMAP, POP or another provider, there or anywhere.
INBOX_READING = {
    "backend/app/modules/inbox/provider.py": re.compile(
        r"mail endpoint '(/gmail/v1/users/me/messages|https://gmail\.googleapis\.com|"
        r"https://www\.googleapis\.com/auth/gmail\.r)"
    ),
    # The stand-in's route: its prefix is a name the scan cannot resolve ("X").
    "fixtures/ats_receiver/inbox_fixture.py": re.compile(
        r"mail endpoint '(X)?/gmail/v1/users/me/messages'"
    ),
}


def _inbox_allowed(hit: str, root: Path) -> bool:
    m = re.fullmatch(r"(.+?):\d+ (mail endpoint .*)", hit)
    if not m:
        return False
    path = Path(m[1])
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else None
    return rel in INBOX_READING and bool(INBOX_READING[rel].match(m[2]))


def _outbound_allowed(hit: str, root: Path) -> bool:
    m = re.fullmatch(r"(.+):\d+ import (\S+)", hit)
    if not m:
        return False
    path, name = Path(m[1]), m[2]
    rel = path.relative_to(root).as_posix() if path.is_relative_to(root) else None
    return rel in OUTBOUND_MAIL and name in OUTBOUND_MAIL[rel]


def repo_mail_hits(root: Path = REPO) -> list[str]:
    app = root / "backend/app"
    files = py_files(root)
    hits = mail_hits([p for p in files if app not in p.parents])
    hits += mail_hits([p for p in files if app in p.parents], computed_imports_fail=True)
    hits = [h for h in hits if not _outbound_allowed(h, root) and not _inbox_allowed(h, root)]
    return hits + mail_hits(js_files(root) + frontend_sources(root))


def test_no_mailbox_client_is_imported_or_addressed_anywhere():
    """R7.5: no module imports a mail client (stdlib, SDK, or one whose name says mail), names a
    mail host, API, protocol or OAuth scope, or runs a mail program; in backend/app an import
    whose name is computed fails too."""
    assert repo_mail_hits() == []


def test_outbound_mail_is_allowed_only_where_listed_and_reading_mail_never(tmp_path):
    """D94: the exception is per file and per name; a mailbox client fails even there."""
    t = tmp_path / "backend/app/modules/mail/transport.py"
    t.parent.mkdir(parents=True)
    t.write_text("import smtplib\nfrom email.message import EmailMessage\n")
    assert repo_mail_hits(tmp_path) == []
    for reading in ("import imaplib\n", "import poplib\n", "import mailbox\n",
                    "from googleapiclient import discovery\n"):  # fmt: skip
        t.write_text("import smtplib\n" + reading)
        assert repo_mail_hits(tmp_path), reading
    other = tmp_path / "backend/app/modules/notifications/service.py"
    other.parent.mkdir(parents=True)
    t.write_text("import smtplib\n")
    other.write_text("import smtplib\n")
    assert repo_mail_hits(tmp_path) == [f"{other}:1 import smtplib"]


def test_reading_mail_is_allowed_only_in_the_inbox_reader_and_only_its_names(tmp_path):
    """D101: the Gmail REST path and the read-only scope in the reader; nothing else there, and
    none of it anywhere else."""
    r = tmp_path / "backend/app/modules/inbox/provider.py"
    r.parent.mkdir(parents=True)
    r.write_text("MESSAGES = '/gmail/v1/users/me/messages'\n"
                 "SCOPE = 'https://www.googleapis.com/auth/gmail.readonly'\n")  # fmt: skip
    assert repo_mail_hits(tmp_path) == []
    for extra in ("import imaplib\n", "HOST = 'imap.gmail.com'\n",
                  "SCOPE2 = 'https://www.googleapis.com/auth/gmail.modify'\n",
                  "from googleapiclient import discovery\n"):  # fmt: skip
        r.write_text("MESSAGES = '/gmail/v1/users/me/messages'\n" + extra)
        assert repo_mail_hits(tmp_path), extra
    r.write_text("MESSAGES = '/gmail/v1/users/me/messages'\n")
    other = tmp_path / "backend/app/modules/notifications/service.py"
    other.parent.mkdir(parents=True)
    other.write_text("MESSAGES = '/gmail/v1/users/me/messages'\n")
    assert len(repo_mail_hits(tmp_path)) == 1 and str(other) in repo_mail_hits(tmp_path)[0]


def test_the_repository_mail_scan_reads_each_place_as_it_should(tmp_path):
    def plant(rel, text):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    computed = "import importlib\nimportlib.import_module(NAME)\n"
    tests = plant("backend/tests/helper.py", computed)
    e2e = plant("frontend/e2e/spec.ts", "const H = 'imap.gmail.com';\n")
    assert repo_mail_hits(tmp_path) == []  # outside backend/app; the frontend's tests
    app = plant("backend/app/x.py", computed)
    assert repo_mail_hits(tmp_path)  # backend/app fails closed
    app.unlink()
    plant("frontend/src/lib/mail.ts", "const H = 'imap.gmail.com';\n")
    assert repo_mail_hits(tmp_path)  # the frontend's own source is read for mail
    assert tests.exists() and e2e.exists()


def test_no_mail_or_capture_package_is_a_dependency_or_installed_by_an_image():
    assert dependency_hits() == []
    assert infra_hits(infra_files()) == []


def test_no_screenshot_video_trace_har_or_captured_session_in_python():
    """R11.4: no capture call, capture keyword, capture import, CDP capture method, Chromium
    capture flag, Playwright debug log or in-page capture script; where a page runs, no
    attribute named at run time."""
    assert capture_hits(py_files(), [REPO / f for f in BROWSER_FILES]) == []


def test_no_capture_in_the_browser_runner():
    assert js_hits(js_files()) == []


SAMPLES_MAIL = [
    "import imaplib",
    "from email import message_from_bytes",
    "import email.parser",
    "import importlib\nimportlib.import_module('poplib')",
    "import importlib\nimportlib.import_module(name='imaplib')",
    "from importlib import import_module as im\nim('imaplib')",
    "import importlib.util\nimportlib.util.find_spec('imaplib')",
    "import pkgutil\npkgutil.resolve_name('imaplib:IMAP4')",
    "import runpy\nrunpy.run_module('smtplib')",
    "import runpy\nrunpy.run_path(path_name='imaplib_poller')",
    "__import__('smtplib')",
    "exec('import imaplib')",
    "from google.oauth2.credentials import Credentials",
    "from O365 import Account",
    "import exchangelib as x",
    "import nylas",
    "import acme_mailreader",
    "def f():\n    import imaplib",
    "HOST = 'imap.example.com'",
    "HOST = b'imap.example.com'",
    "HOST = 'imap-mail.outlook.com'",
    "SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']",
    "SCOPES = ['https://mail.google.com/']",
    "SCOPES = ['Mail.Read']",
    "URL = 'https://gmail.googleapis.com'",
    "URL = f'https://www.googleapis.com/gmail/v1/users/{uid}/threads'",
    "URL = 'https://outlook.office.com/api/v2.0/me/messages'",
    "URL = BASE + '/me/messages'",
    "URL = f'https://graph.microsoft.com/v1.0/users/{uid}/messages'",
    "CAP = 'urn:ietf:params:jmap:mail'",
    "URL = 'imaps://mail.example.org:993/INBOX'",
    "import subprocess\nsubprocess.run(['fetchmail'])",
    "import subprocess\nsubprocess.run(['/usr/bin/fetchmail', '-a'])",
    "import subprocess\nsubprocess.run('fetchmail -a', shell=True)",
    "SCRIPT = 'import imaplib\\nimaplib.IMAP4_SSL(host)'",
    "SCRIPT = f'import sys, imaplib\\nprint({host!r})'",
    "SCRIPT = \"__import__('imaplib').IMAP4_SSL(H)\"",
    "SCRIPT = '\\n'.join(['import imaplib', 'imaplib.IMAP4_SSL(h)'])",
    "HOST = 'imap.' + 'example.com'",
    "HOST = '.'.join(['imap', 'example', 'com'])",
]
SAMPLES_MAIL_STRICT = [  # as `backend/app` is read: an import named at run time
    "import importlib\nimportlib.import_module(NAME)",
    "import importlib\nimportlib.import_module(f'{base}box')",
]
CLEAN_MAIL = [
    "import email_validator\nfrom pydantic import EmailStr",
    "from email.utils import parsedate_to_datetime",
    "from email import utils",
    '"""Never calls https://mail.google.com/ or imaplib."""\n# import imaplib',
    "FONTS = 'https://fonts.googleapis.com/css'",
    "from .email import x",
    "smtp_port = 25",
    "KEYS = ['population.size.mean', 'popover.module.css']",
    "MSG = 'The employer rejected that code. Check the latest email.'",
    "import importlib\nimportlib.import_module('app.modules.jobs')",
]
SAMPLES_JS_MAIL = [
    "const H = 'imap.gmail.com';",
    "const imap = require('imapflow');",
    "import nodemailer from 'nodemailer';",
    "const m = await import('imap-simple');",
]
CLEAN_JS_MAIL = ["import { EmailField } from './EmailField';", "import x from '@/lib/mailto';"]
SAMPLES_CAPTURE = [
    "page.screenshot(path='x.png')",
    "page.locator('#a').screenshot()",
    "p = page\np.screenshot()",
    "ctx.tracing.start(screenshots=True, snapshots=True)",
    "browser.new_context(record_video_dir='/tmp/v')",
    "browser.new_context(**{'record_har_path': 'x.har'})",
    "getattr(page, 'screenshot')()",
    "ctx.new_cdp_session(page).send('Page.captureScreenshot')",
    "browser.new_browser_cdp_session()",
    "ARGS = ['--remote-debugging-port=9222']",
    "from playwright.sync_api import Tracing",
    "p.chromium.launch(traces_dir='/tmp/t')",
    "browser.start_tracing(page, screenshots=True)",
    "ctx.route_from_har('x.har', update=True)",
    "page.evaluate('c => c.toDataURL()')",
    "page.evaluate('c => c.toBlob(cb)')",
    "expect(page).to_have_screenshot()",
    "ctx.storage_state(path='state.json')",
    "p.chromium.connect_over_cdp('http://127.0.0.1:9222')",
    "p.chromium.launch_persistent_context('/tmp/profile')",
    "OPTS = {'args': ['--log-net-log=/tmp/n.json']}",
    "CMD = 'chromium --headless --screenshot=/tmp/a.png https://example.com'",
    "CMD = 'playwright screenshot https://example.com a.png'",
    "OLD = 'b = p.chromium.launch()\\nctx = b.new_context(record_video_dir=d)'",
    "OLD = f'b = p.chromium.launch()\\nb.new_context(record_video_dir={d!r})'",
    "JS = 'const p = await b.newPage(); await p.screenshot({path: \"a.png\"});'",
    "JS = 'b.newPage().then(p => p.screenshot())'",
    "import os\nos.environ['DEBUG'] = 'pw:api'",
    "import os\nos.environ['PWDEBUG'] = '1'",
    "ENV = {'DEBUG': 'pw:protocol'}",
]
SAMPLES_PAGE = [  # each only where a page runs (or, for the strict words, in execution code)
    "import playwright\nname = 'screen' + 'shot'\ngetattr(page, name)",
    "from playwright.sync_api import sync_playwright\nKIND = 'video'",
    "from app.modules.execution.browser import browser_session\ngetattr(page, n)",
    "import playwright\nimport operator\noperator.methodcaller(n)(page)",
    "import playwright\nfrom operator import attrgetter\nattrgetter(n)(page)",
    "import playwright\ng = getattr\ng(page, n)",
    "import playwright\nexec('page.' + n + '()')",
    "import playwright\npage.__getattribute__(n)()",
    "import playwright\njson.dump(context.cookies(), f)",
    "import playwright\npage.pdf(path='x.pdf')",
    "import playwright\npage.video.path()",
]
PAGE_ONLY = [  # the same rules, in a file that drives no page: ordinary code
    "name = 'scr' + n\ngetattr(obj, name)",
    "import operator\noperator.methodcaller(n)(obj)",
    "g = getattr",
    "kind = DocumentKind.pdf\nurl = job.video\nprefs = settings.cookies",
]
CLEAN_CAPTURE = [
    '"""No screenshots, traces or videos: page.screenshot() is never called."""\n# screenshot',
    "import traceback\ntraceback.format_exc()",
    "import logging\nlogging.getLogger('celery.app.trace')",
    "D = {'traceback': '', 'pdf': 1, 'accept': '.pdf,.docx'}",
    "html = page.content()",
    "CMD = ['node', '--trace-warnings', 'x.js']",
    "CMD = ['pytest', '--traceconfig']",
    "MSG = 'NoEfforts takes no screenshot of a form.'",
    "import os\nlevel = os.environ.get('DEBUG', '')",
]
SAMPLES_JS = [
    "await page.screenshot({path:'a.png'})",
    "await page['screenshot']()",
    "chromium.launchServer({...opts, tracesDir:'/tmp'})",
    "browser.newContext({recordVideo:{dir:'/tmp'}})",
    "context.tracing.start({screenshots:true})",
    "chromium.connectOverCDP(url)",
    "const args = ['--enable-logging'];",
    "await page.pdf({path: 'a.pdf'})",
    "const s = await browser.newBrowserCDPSession();",
    "fs.writeFileSync('c.json', JSON.stringify(await context.cookies()));",
    "process.env.DEBUG = 'pw:api';",
    "const trim = (p) => p.replace(/\\/*$/, ''); await page.screenshot();",
    "const s = 'a\\\"b // c'; await page.screenshot();",
    "// a comment naming page.screenshot() fails too",
]
CLEAN_JS = [
    "console.log('no screenshot taken, no tracing');",
    "spawn('node', ['--trace-warnings', 'x.js']);",
    "await page.route('**/*', r => r.continue());",
]
SAMPLES_INFRA = [
    "RUN pip install imapclient",
    'RUN pip install "playwright==1.56.0" \\\n    imapclient',
    "RUN pip3 install aioimaplib",
    "RUN pip3.12 --no-cache-dir install imapclient",
    "RUN uv add exchangelib",
    "RUN apt-get install -y fetchmail",
    "RUN apt-get update && apt-get -y install fetchmail",
    "RUN apt install -y mutt",
    "RUN npm install nodemailer",
    "RUN npm i imapflow",
    "RUN yarn global add nodemailer",
    "RUN bun add imapflow",
    'RUN ["pip", "install", "imapclient"]',
    "RUN pip install pytest-playwright",
    "ENV DEBUG=pw:api",
    "ENV DEBUG pw:api",
    "ENV DEBUG=*",
    "      DEBUG: pw:protocol",
    '      DEBUG: "pw:api"',
    "      PWDEBUG: '1'",
    "    command: chromium --remote-debugging-port=9222",
    '    command: ["python", "-c", "import imaplib; imaplib.IMAP4_SSL(h)"]',
    "      run: curl https://gmail.googleapis.com/gmail/v1/users/me/messages",
    "      run: fetchmail -a",
    '      run: node -e "const p = await b.newPage(); await p.screenshot()"',
]
CLEAN_INFRA = [
    "RUN apt-get install -y mailcap ca-certificates",
    "RUN echo hi  # pip install imapclient",
    "      LOG_LEVEL: debug",
    "    command: node --trace-warnings x.js",
    "      run: python -c 'import json; print(1)'",
]


@pytest.mark.parametrize("src", SAMPLES_MAIL)
def test_the_mail_guard_catches_each_sample(src, tmp_path):
    p = tmp_path / "planted.py"
    p.write_text(src + "\n")
    assert mail_hits([p])  # caught without the fail-closed rule for computed imports


@pytest.mark.parametrize("src", SAMPLES_MAIL_STRICT)
def test_backend_app_fails_closed_on_an_import_named_at_run_time(src, tmp_path):
    p = tmp_path / "planted.py"
    p.write_text(src + "\n")
    assert mail_hits([p], computed_imports_fail=True) and not mail_hits([p])


@pytest.mark.parametrize("src", SAMPLES_JS_MAIL)
def test_the_mail_guard_reads_javascript(src, tmp_path):
    p = tmp_path / "planted.ts"
    p.write_text(src + "\n")
    assert mail_hits([p])


@pytest.mark.parametrize("src", SAMPLES_CAPTURE)
def test_the_capture_guard_catches_each_sample(src, tmp_path):
    p = tmp_path / "planted.py"
    p.write_text(src + "\n")
    assert capture_hits([p])


@pytest.mark.parametrize("src", SAMPLES_PAGE)
def test_the_capture_guard_is_stricter_where_a_page_runs(src, tmp_path):
    p = tmp_path / "planted.py"
    p.write_text(src + "\n")
    assert capture_hits([p])


@pytest.mark.parametrize("src", PAGE_ONLY)
def test_the_page_rules_apply_only_where_a_page_runs(src, tmp_path):
    p = tmp_path / "planted.py"
    p.write_text(src + "\n")
    assert capture_hits([p]) == []
    marked = tmp_path / "marked.py"
    marked.write_text("import playwright\n" + src + "\n")
    assert capture_hits([marked])


def test_execution_and_browser_files_are_strict(tmp_path):
    execution = tmp_path / "backend" / "app" / "modules" / "execution"
    execution.mkdir(parents=True)
    p = execution / "planted.py"
    p.write_text("KIND = 'video'\n")
    assert capture_hits([p])
    other = tmp_path / "other.py"
    other.write_text("KIND = 'video'\n")
    assert capture_hits([other]) == [] and capture_hits([other], [other])
    code = tmp_path / "code.py"  # code in a string is read as code where a page runs
    code.write_text("SCRIPT = 'run()\\nKIND = \"video\"'\n")
    assert capture_hits([code])
    for f in BROWSER_FILES:
        assert (REPO / f).exists(), f


@pytest.mark.parametrize("src", SAMPLES_JS)
def test_the_runner_guard_catches_each_sample(src, tmp_path):
    p = tmp_path / "planted.js"
    p.write_text(src + "\n")
    assert len(js_hits([p])) == 1


@pytest.mark.parametrize("src", SAMPLES_INFRA)
def test_the_infrastructure_guard_catches_each_sample(src, tmp_path):
    p = tmp_path / "Dockerfile"
    p.write_text("# RUN pip install imapclient (a comment)\n" + src + "\n")
    assert infra_hits([p])


def test_the_guards_leave_prose_and_ordinary_code_alone(tmp_path):
    for i, src in enumerate(CLEAN_MAIL + CLEAN_CAPTURE):
        p = tmp_path / f"clean{i}.py"
        p.write_text(src + "\n")
        assert mail_hits([p], computed_imports_fail=True) == [], src
        assert capture_hits([p]) == [], src
    p = tmp_path / "pdf_upload.py"
    p.write_text("ALLOWED = {'pdf': 'application/pdf'}\n")
    assert capture_hits([p]) == []  # outside browser code "pdf" is an upload type
    assert capture_hits([p], [p])  # in browser code it is a capture word
    for i, src in enumerate(CLEAN_JS + CLEAN_JS_MAIL):
        p = tmp_path / f"clean{i}.ts"
        p.write_text(src + "\n")
        assert js_hits([p]) == [] and mail_hits([p]) == [], src
    for i, src in enumerate(CLEAN_INFRA):
        p = tmp_path / f"Dockerfile.clean{i}"
        p.write_text(src + "\n")
        assert infra_hits([p]) == [], src


def test_the_dependency_guard_reads_every_manifest_and_pytest_setting(tmp_path):
    for rel in ("backend/pyproject.toml", "backend/uv.lock", "frontend/package.json",
                "frontend/package-lock.json"):  # fmt: skip
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text((REPO / rel).read_text())
    assert dependency_hits(tmp_path) == []

    def planted(rel, edit) -> list[str]:
        p = tmp_path / rel
        before = p.read_text() if p.exists() else None
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(edit(before or ""))
        try:
            return dependency_hits(tmp_path)
        finally:
            p.unlink() if before is None else p.write_text(before)

    def lock_entry(s):
        d = json.loads(s)
        d.setdefault("packages", {})["node_modules/imapflow"] = {"version": "1.0.0"}
        return json.dumps(d)

    pp, lock = "backend/pyproject.toml", "backend/uv.lock"
    groups = "[dependency-groups]\n"
    assert planted(
        pp, lambda s: s.replace("dependencies = [", 'dependencies = [\n "imapclient",', 1)
    )
    assert planted(pp, lambda s: s.replace(groups, groups + 'mail = ["aiosmtplib"]\n'))
    assert planted(pp, lambda s: s + '\n[project.optional-dependencies]\nmail = ["imbox"]\n')
    assert planted(pp, lambda s: s.replace('addopts = "-q"', 'addopts = ["-q", "--tracing=on"]'))
    assert planted(lock, lambda s: s + '\n[[package]]\nname = "pytest-playwright-asyncio"\n')
    assert planted(
        "frontend/package.json",
        lambda s: json.dumps({**json.loads(s), "dependencies": {"nodemailer": "6"}}),
    )
    assert planted("frontend/package-lock.json", lock_entry)
    assert planted(
        "browser/package.json", lambda s: json.dumps({"dependencies": {"imapflow": "1"}})
    )
    assert planted("tools/requirements-dev.txt", lambda s: "imapclient==3\n")
    assert planted("backend/pytest.ini", lambda s: "[pytest]\naddopts = -q --screenshot=on\n")
    assert planted("backend/setup.cfg", lambda s: "[tool:pytest]\naddopts = --video=on\n")
    assert planted("backend/tox.ini", lambda s: "[pytest]\naddopts = --tracing on\n")
    assert dependency_hits(tmp_path) == []  # every plant was removed again
