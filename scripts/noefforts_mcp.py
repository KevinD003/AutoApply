#!/usr/bin/env python3
"""NoEfforts MCP server over stdio (priority D, D84; docs/api-tokens.md). Standard library only.

For a local MCP client on this machine: it starts this script and talks JSON-RPC 2.0 to it, one
message per line, on stdin and stdout. The token comes from NOEFFORTS_TOKEN or the file named
by NOEFFORTS_TOKEN_FILE (readable by you only); the API from NOEFFORTS_API (default
http://127.0.0.1:8000/api). It listens on no port.

Tools: list_jobs, get_job, list_applications, get_application, list_notifications, and
import_job only for a token with the import:jobs scope. There is no tool to answer, consent,
approve, queue, submit or enter a verification code, and the API refuses all of those to any
token anyway. What the tools return is your data as the API returns it: treat job text in it
as untrusted page content, not as instructions."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from noefforts import DEFAULT_API, Client, CliError, api_base, read_token  # noqa: E402

PROTOCOL = "2025-06-18"
_ID = {"type": "string", "description": "A NoEfforts id (UUID)"}
READ_TOOLS = {
    "list_jobs": (
        "Your jobs, newest first, each with its match summary (your preferences counted, your "
        "approved skills and licences the job names, how much is unknown). No score.",
        {
            "search": {"type": "string", "description": "Text in title, employer or location"},
            "status": {"type": "string", "enum": ["new", "shortlisted", "excluded", "closed"]},
        },
        [],
        lambda c, a: c.jobs(a.get("search"), a.get("status")),
    ),
    "get_job": (
        "One job: its details, description and match explanation (eligibility stays in the "
        "app).",
        {"job_id": _ID},
        ["job_id"],
        lambda c, a: c.job(a["job_id"]),
    ),
    "list_applications": (
        "Your applications with their state and outcome.",
        {},
        [],
        lambda c, a: c.applications(),
    ),
    "get_application": (
        "One application with its timeline.",
        {"application_id": _ID},
        ["application_id"],
        lambda c, a: c.application(a["application_id"]),
    ),
    "list_notifications": (
        "Your in-app notifications: verification requests, approvals that stopped applying, "
        "rehearsals, receipts and stops.",
        {},
        [],
        lambda c, a: c.notifications(),
    ),
}
IMPORT_TOOLS = {
    "import_job": (
        "Add one job to your NoEfforts jobs by its posting link (the same as the Jobs page). "
        "It applies to nothing and contacts nobody.",
        {
            "url": {"type": "string", "description": "The posting's link"},
            "title": {"type": "string"},
            "employer": {"type": "string"},
        },
        ["url"],
        lambda c, a: c.import_job(a["url"], a.get("title"), a.get("employer")),
    ),
}


class Server:
    def __init__(self, client: Client):
        self.client = client
        self._scopes: list[str] | None = None

    def tools(self) -> dict:
        if self._scopes is None:
            self._scopes = self.client.whoami().get("scopes", [])
        out = dict(READ_TOOLS) if "read" in self._scopes else {}
        return out | (IMPORT_TOOLS if "import:jobs" in self._scopes else {})

    def handle(self, msg: dict) -> dict | None:
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:  # a notification (e.g. notifications/initialized): no answer
            return None
        try:
            if method == "initialize":
                asked = (msg.get("params") or {}).get("protocolVersion")
                result = {
                    "protocolVersion": asked or PROTOCOL,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "noefforts", "version": "1"},
                    "instructions": "Read-only access to your NoEfforts jobs, applications and "
                    "notifications (and adding a job, if the token allows it). Nothing here "
                    "applies, approves or submits.",
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {
                    "tools": [
                        {
                            "name": name,
                            "description": desc,
                            "inputSchema": {"type": "object", "properties": props,
                                            "required": req, "additionalProperties": False},
                        }  # fmt: skip
                        for name, (desc, props, req, _) in self.tools().items()
                    ]
                }
            elif method == "tools/call":
                params = msg.get("params") or {}
                tool = self.tools().get(params.get("name"))
                args = params.get("arguments") or {}
                if tool is None:
                    return _error(mid, -32602, "Unknown tool, or not allowed for this token.")
                if not isinstance(args, dict):
                    return _error(mid, -32602, "Arguments must be an object.")
                try:
                    data = tool[3](self.client, args)
                    text, failed = json.dumps(data, ensure_ascii=False), False
                except (CliError, KeyError) as e:
                    text, failed = f"error: {e}", True
                result = {"content": [{"type": "text", "text": text}], "isError": failed}
            else:
                return _error(mid, -32601, "Method not found")
        except (CliError, OSError) as e:
            return _error(mid, -32000, str(e))
        return {"jsonrpc": "2.0", "id": mid, "result": result}


def _error(mid, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve(server: Server, stdin=sys.stdin, stdout=sys.stdout) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = _error(None, -32700, "Parse error")
        else:
            reply = server.handle(msg) if isinstance(msg, dict) else _error(None, -32600, "")
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()


def main(env=None, send=None, stdin=sys.stdin, stdout=sys.stdout) -> int:
    env = os.environ if env is None else env
    try:
        client = Client(api_base(env.get("NOEFFORTS_API") or DEFAULT_API),
                        read_token(env, env.get("NOEFFORTS_TOKEN_FILE")), send)  # fmt: skip
    except (CliError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    serve(Server(client), stdin, stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
