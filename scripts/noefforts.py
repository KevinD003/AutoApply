#!/usr/bin/env python3
"""NoEfforts command line (priority D, D84; docs/api-tokens.md). Standard library only.

    export NOEFFORTS_TOKEN=ne_...        # or: --token-file PATH (readable by you only)
    python3 scripts/noefforts.py jobs [--search TEXT] [--status new|shortlisted|excluded|closed]
    python3 scripts/noefforts.py job JOB_ID
    python3 scripts/noefforts.py applications
    python3 scripts/noefforts.py application APPLICATION_ID
    python3 scripts/noefforts.py notifications
    python3 scripts/noefforts.py whoami                     # this token's scopes and expiry
    python3 scripts/noefforts.py import-job URL [--title T] [--employer E]   # needs import:jobs

Read commands need a token with the `read` scope. There is no command to answer, consent,
approve, queue, submit or enter a code: those stay in the app. The token is never taken from
the command line (shell history would keep it) and never printed. It talks to your own API
only: http://127.0.0.1:8000/api by default (NOEFFORTS_API or --api to change it; plain http
is refused for any host but this machine)."""

import argparse
import json
import os
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_API = "http://127.0.0.1:8000/api"
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class CliError(Exception):
    pass


def api_base(value: str) -> str:
    p = urllib.parse.urlsplit(value)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise CliError("The API address must be an http(s) URL.")
    if p.scheme == "http" and p.hostname not in LOOPBACK:
        raise CliError("Plain http is allowed to this machine only; use https for another host.")
    if p.username or p.password or p.query or p.fragment:
        raise CliError("The API address must not carry credentials, a query or a fragment.")
    return value.rstrip("/")


def read_token(env: dict, token_file: str | None) -> str:
    if token_file:
        try:
            st = os.stat(token_file)
            if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise CliError("The token file must be readable by you only (chmod 600).")
            with open(token_file, encoding="utf-8") as f:
                token = f.read().strip()
        except OSError:
            # Never echo the path back: it may be a token typed in the wrong place.
            raise CliError("Cannot read the token file.") from None
    else:
        token = env.get("NOEFFORTS_TOKEN", "").strip()
    if not token:
        raise CliError("No token: set NOEFFORTS_TOKEN or pass --token-file.")
    if not token.startswith("ne_"):
        raise CliError("That is not a NoEfforts API token.")
    return token


def _urllib_send(method: str, url: str, headers: dict, body: bytes | None):
    # No proxy: the API is your own, usually on this machine.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Client:
    """The API calls the CLI and the MCP server make. `send` is replaceable for tests."""

    def __init__(self, base: str, token: str, send=None):
        self.base, self._token, self._send = base, token, send or _urllib_send

    def call(self, method: str, path: str, query: dict | None = None, body: dict | None = None):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v})
        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        status, raw = self._send(method, url, headers, data)
        try:
            out = json.loads(raw or b"null")
        except ValueError:
            out = None
        if status >= 400:
            detail = out.get("detail") if isinstance(out, dict) else None
            raise CliError(f"HTTP {status}: {detail or 'request refused'}")
        return out

    # One method per command; ids are checked to be UUIDs before they go in a path.
    def jobs(self, search=None, status=None):
        return self.call("GET", "/jobs", {"q": search, "status": status})

    def job(self, job_id):
        return self.call("GET", f"/jobs/{_uuid(job_id)}")

    def applications(self):
        return self.call("GET", "/applications")

    def application(self, app_id):
        return self.call("GET", f"/applications/{_uuid(app_id)}")

    def notifications(self):
        return self.call("GET", "/notifications")

    def whoami(self):
        return self.call("GET", "/token")

    def import_job(self, url, title=None, employer=None):
        body = {"url": url} | {k: v for k, v in (("title", title), ("employer", employer)) if v}
        return self.call("POST", "/jobs", body=body)


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise CliError("That is not an id NoEfforts uses (a UUID).") from None


class _Parser(argparse.ArgumentParser):
    """Option names are never abbreviated (`--token` is not `--token-file`), and an error never
    repeats what was typed, which could be a token pasted in the wrong place."""

    def error(self, message):
        self.exit(2, f"{self.prog}: error: unknown option or missing argument (see --help)\n")


def parser() -> argparse.ArgumentParser:
    p = _Parser(prog="noefforts", description="Read your NoEfforts data.", allow_abbrev=False)
    p.add_argument("--api", help=f"API address (default NOEFFORTS_API or {DEFAULT_API})")
    p.add_argument("--token-file", help="file holding the token, readable by you only")
    sub = p.add_subparsers(dest="command", required=True, parser_class=_Parser)
    j = sub.add_parser("jobs", help="your jobs, each with its match summary")
    j.add_argument("--search")
    j.add_argument("--status", choices=["new", "shortlisted", "excluded", "closed"])
    sub.add_parser("job", help="one job").add_argument("job_id")
    sub.add_parser("applications", help="your applications")
    sub.add_parser("application", help="one application and its timeline").add_argument("app_id")
    sub.add_parser("notifications", help="your notifications")
    sub.add_parser("whoami", help="this token's scopes and expiry")
    imp = sub.add_parser("import-job", help="add one job by its link (needs import:jobs)")
    imp.add_argument("url")
    imp.add_argument("--title")
    imp.add_argument("--employer")
    return p


def main(argv=None, env=None, send=None, out=sys.stdout, err=sys.stderr) -> int:
    env = os.environ if env is None else env
    args = parser().parse_args(argv)
    try:
        client = Client(api_base(args.api or env.get("NOEFFORTS_API") or DEFAULT_API),
                        read_token(env, args.token_file), send)  # fmt: skip
        result = {
            "jobs": lambda: client.jobs(args.search, args.status),
            "job": lambda: client.job(args.job_id),
            "applications": client.applications,
            "application": lambda: client.application(args.app_id),
            "notifications": client.notifications,
            "whoami": client.whoami,
            "import-job": lambda: client.import_job(args.url, args.title, args.employer),
        }[args.command]()
    except (CliError, OSError) as e:
        print(f"error: {e}", file=err)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False), file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
