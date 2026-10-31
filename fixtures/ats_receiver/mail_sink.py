"""A local SMTP sink for tests (D94). Test-only; never deploy. It accepts mail for anyone,
relays nothing, and keeps what it received in its own ledger: the oracle for what NoEfforts'
email reminders actually handed over. It shares no code or database with NoEfforts.

Modes (`MailSink.mode`):
  normal            250 to everything; the message is recorded.
  refuse_connect    the connection is closed at once (nothing was sent).
  tempfail_rcpt     451 to RCPT TO (a definite transient refusal; nothing recorded).
  permfail_rcpt     550 to RCPT TO (a definite permanent refusal; nothing recorded).
  tempfail_data     451 after the message (an explicit refusal; nothing recorded).
  drop_after_data   the message is recorded, then the connection closes without an answer.
  slow_after_data   the message is recorded, then the answer comes after `slow_seconds`.
  tempfail_once     451 to the first RCPT TO, then normal.
`connections` counts connections, so a test can prove nothing was attempted."""

import asyncio
import email
import threading
import time
from email import policy


class MailSink:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.mode = "normal"
        self.slow_seconds = 3.0
        self.connections = 0
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.port = 0

    def reset(self) -> None:
        with self._lock:
            self.messages, self.mode, self.connections = [], "normal", 0

    def received(self) -> list[dict]:
        with self._lock:
            return [dict(m) for m in self.messages]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        with self._lock:
            self.connections += 1
            mode = self.mode
        if mode == "refuse_connect":
            writer.close()
            return

        async def say(line: str) -> None:
            writer.write((line + "\r\n").encode())
            await writer.drain()

        sender, rcpts = None, []
        try:
            await say("220 mail-sink.test ESMTP (test fixture)")
            while True:
                raw = await reader.readline()
                if not raw:
                    return
                cmd = raw.decode(errors="replace").strip()
                verb = cmd.split(" ", 1)[0].upper()
                if verb in ("EHLO", "HELO"):
                    await say("250-mail-sink.test" if verb == "EHLO" else "250 mail-sink.test")
                    if verb == "EHLO":
                        await say("250 8BITMIME")
                elif verb == "MAIL":
                    sender, rcpts = cmd[10:].strip("<> "), []
                    await say("250 OK")
                elif verb == "RCPT":
                    with self._lock:
                        mode = self.mode
                        if mode == "tempfail_once":
                            self.mode = "normal"
                    if mode in ("tempfail_rcpt", "tempfail_once"):
                        await say("451 4.3.0 try again later")
                    elif mode == "permfail_rcpt":
                        await say("550 5.1.1 no such user")
                    else:
                        rcpts.append(cmd[8:].strip("<> "))
                        await say("250 OK")
                elif verb == "DATA":
                    await say("354 end with .")
                    lines = []
                    while True:
                        line = await reader.readline()
                        if not line or line in (b".\r\n", b".\n"):
                            break
                        lines.append(line[1:] if line.startswith(b"..") else line)
                    with self._lock:
                        mode = self.mode
                    if mode == "tempfail_data":
                        await say("451 4.3.0 not now")
                        continue
                    msg = email.message_from_bytes(b"".join(lines), policy=policy.default)
                    body = msg.get_body(preferencelist=("plain",))
                    with self._lock:
                        self.messages.append({
                            "from": sender, "to": list(rcpts), "subject": str(msg["Subject"]),
                            "body": body.get_content() if body else "",
                            "received_at": time.time(),
                        })  # fmt: skip
                    if mode == "drop_after_data":
                        writer.close()
                        return
                    if mode == "slow_after_data":
                        await asyncio.sleep(self.slow_seconds)
                    await say("250 OK queued")
                elif verb == "RSET":
                    sender, rcpts = None, []
                    await say("250 OK")
                elif verb == "NOOP":
                    await say("250 OK")
                elif verb == "QUIT":
                    await say("221 bye")
                    return
                else:
                    await say("502 not implemented")
        except (ConnectionError, OSError):
            return
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001 - the peer may already be gone
                pass

    def start(self, host: str = "127.0.0.1", port: int = 0) -> int:
        """Serves in a daemon thread; returns the port. Raises if it cannot listen (D103: a port
        held by another test run once made the sink fail silently and every mail vanish)."""
        ready = threading.Event()
        failed: list[BaseException] = []

        def run() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            try:
                server = loop.run_until_complete(asyncio.start_server(self._handle, host, port))
            except OSError as e:
                failed.append(e)
                ready.set()
                return
            self.port = server.sockets[0].getsockname()[1]
            ready.set()
            loop.run_forever()

        threading.Thread(target=run, daemon=True, name="mail-sink").start()
        if not ready.wait(10):
            raise RuntimeError("the mail sink did not start")
        if failed:
            raise RuntimeError(f"the mail sink cannot listen on {host}:{port}") from failed[0]
        return self.port
