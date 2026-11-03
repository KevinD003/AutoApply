"""#150: make an after-send failure diagnosable without leaking page content, and make the
confirmation reads fail closed against unexpected (non-Playwright) errors.

The after-send handler (runner.py) deliberately never logs an exception's message or arguments,
because a browser error can quote a URL, selector or page text. That left an opaque
"internal error (TypeError)" with no line to look at. `_origin_frames` logs only code locations
(file:line:function), so the next occurrence names its own line while still leaking nothing.

The Greenhouse confirmation reads (`_confirmed`, `_code_rejected`) must fail closed: any read
failure means "no confirmation / no rejection seen", never a false acceptance, and never a crash
into the generic handler. Synthetic data only; no browser."""

from app.modules.execution import runner
from app.modules.execution.adapters.greenhouse_dom import GreenhouseDomAdapter


def test_origin_frames_names_the_code_location_not_the_message():
    def deepest():
        # A message shaped like the sensitive strings a real browser error could carry.
        raise ValueError("https://boards.example/token=sue%40example.com body text selector #x")

    try:
        deepest()
    except ValueError as e:
        frames = runner._origin_frames(e)

    # It names our own code: this file, this line, the raising function.
    assert "test_after_send_diagnostics.py:" in frames
    assert ":deepest" in frames
    # It never carries the exception's message (URLs, selectors, addresses, page text).
    for leaked in ("boards.example", "token=", "example.com", "body text", "selector", "#x"):
        assert leaked not in frames, leaked


def test_origin_frames_never_raises_on_a_bare_exception():
    # No traceback attached: the helper returns its placeholder rather than raising.
    assert runner._origin_frames(ValueError("x")) == "-"


class _UnreadablePage:
    """A page whose every read raises an unexpected, non-Playwright error carrying sensitive
    text — exactly the shape that must never crash the attempt or be read as a confirmation."""

    url = "https://boards.greenhouse.io/acme/jobs/123"

    def locator(self, *_a, **_k):
        raise TypeError("unexpected page state: applicant answer / confirmation message text")


def _adapter() -> GreenhouseDomAdapter:
    # The reads use only the page and module constants, so no captured form is needed.
    return GreenhouseDomAdapter.__new__(GreenhouseDomAdapter)


def test_confirmed_fails_closed_on_an_unexpected_read_error():
    assert _adapter()._confirmed(_UnreadablePage()) is False


def test_code_rejected_fails_closed_on_an_unexpected_read_error():
    assert _adapter()._code_rejected(_UnreadablePage()) is False
