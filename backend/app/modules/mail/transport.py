"""How an email leaves NoEfforts (D94), and what NoEfforts can know about it afterwards.

`SmtpTransport.send` talks SMTP step by step so that each failure is classified by whether the
server could already have the message:
  * `refused_transient` / `refused_permanent`: definitely not accepted. Everything up to and
    including the recipient was refused or failed (connect, TLS, login, MAIL, RCPT), or the
    server answered the end of the message with an explicit 4xx / 5xx. A transient refusal may
    be retried (bounded, by the service).
  * `uncertain`: the message may have been accepted. The connection was lost, or timed out,
    after the message started to go out and before a definite answer. Never retried: an
    accepted message cannot be recalled, and a resend could deliver it twice.
  * `accepted`: the server answered 250 to the end of the message. That is acceptance by that
    server, not delivery to an inbox.
Nothing here logs: the caller records only the outcome and its fixed code, never the address,
the message or an exception's text."""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


@dataclass(frozen=True)
class SendResult:
    outcome: str  # accepted | refused_transient | refused_permanent | uncertain
    code: str  # a fixed, sanitized reason: never server text or an exception message


class Transport(Protocol):
    def send(self, message: EmailMessage, recipient: str) -> SendResult: ...


def _refused(smtp_code: int, step: str) -> SendResult:
    kind = "refused_permanent" if 500 <= smtp_code < 600 else "refused_transient"
    return SendResult(kind, f"{step}_{'5xx' if kind == 'refused_permanent' else '4xx'}")


class SmtpTransport:
    def __init__(self, host: str, port: int, *, sender: str, timeout: float,
                 starttls: bool, username: str = "", password: str = "") -> None:  # fmt: skip
        self.host, self.port, self.sender, self.timeout = host, port, sender, timeout
        self.starttls, self.username, self.password = starttls, username, password

    def send(self, message: EmailMessage, recipient: str) -> SendResult:
        try:
            smtp = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
        except (OSError, smtplib.SMTPException):
            return SendResult("refused_transient", "connect_failed")
        try:
            try:
                smtp.ehlo()
                if self.starttls:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.ehlo()
                if self.username:
                    smtp.login(self.username, self.password)
                code, _ = smtp.mail(self.sender)
                if code != 250:
                    return _refused(code, "mail_from")
                code, _ = smtp.rcpt(recipient)
                if code not in (250, 251):
                    return _refused(code, "rcpt")
            except smtplib.SMTPAuthenticationError:
                return SendResult("refused_permanent", "auth_failed")
            except smtplib.SMTPNotSupportedError:
                return SendResult("refused_permanent", "tls_unsupported")
            except (OSError, smtplib.SMTPException):
                return SendResult("refused_transient", "before_data")
            # From here on the server may end up holding the message.
            try:
                code, _ = smtp.data(message.as_bytes())
            except smtplib.SMTPDataError as e:  # an explicit answer: not accepted
                return _refused(e.smtp_code, "data")
            except (OSError, smtplib.SMTPException):
                return SendResult("uncertain", "lost_after_data")
            return SendResult("accepted", "accepted") if code == 250 else _refused(code, "data")
        finally:
            try:
                smtp.close()
            except Exception:  # noqa: BLE001 - closing a dead connection cannot change the outcome
                pass
