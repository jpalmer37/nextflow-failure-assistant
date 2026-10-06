"""Strip local and site-identifying detail before evidence leaves the machine.

Runs on every path into the model and on everything committed to `cases/`.
Filenames are kept because they carry diagnostic signal (a `.gzx` suffix is the
whole answer in one real case); only the directories leading to them go.
"""

import getpass
import re

from nfdx.schema import Evidence

_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s'\"]+")
_ABS_PATH = re.compile(r"/(?:[\w.+@-]+/)+[\w.+@-]*")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _redact_paths(text: str) -> str:
    """Replace directories with <path>, keeping the final component. URLs are left alone."""

    def swap(match: re.Match) -> str:
        basename = match.group(0).rsplit("/", 1)[-1]
        return f"<path>/{basename}" if basename else "<path>/"

    pieces = []
    last = 0
    for url in _URL.finditer(text):
        pieces.append(_ABS_PATH.sub(swap, text[last : url.start()]))
        pieces.append(url.group(0))
        last = url.end()
    pieces.append(_ABS_PATH.sub(swap, text[last:]))
    return "".join(pieces)


def scrub(text: str | None, extra: tuple[str, ...] = ()) -> str | None:
    if not text:
        return text
    text = _redact_paths(text)
    text = _EMAIL.sub("<email>", text)
    text = _IPV4.sub("<ip>", text)
    user = getpass.getuser()
    if user:
        text = re.sub(rf"\b{re.escape(user)}\b", "<user>", text)
    for pattern in extra:
        text = re.sub(pattern, "<redacted>", text)
    return text


def scrub_evidence(evidence: Evidence, extra: tuple[str, ...] = ()) -> Evidence:
    return Evidence(
        **{k: scrub(v, extra) for k, v in evidence.model_dump().items()}
    )
