"""Pull the failure block out of a .nextflow.log.

Nextflow emits a fixed set of `Header:` sections after the task-failure ERROR
line, so this is section splitting rather than log mining. Every section is
optional: an environment or container failure aborts before the task runs and
emits only `Caused by:`.
"""

import re
import textwrap
from pathlib import Path

from nfdx.schema import Evidence

_FAILURE_LINE = re.compile(
    r"ERROR nextflow\.processor\.TaskProcessor - Error executing process > '(?P<process>.+)'"
)

# A new timestamped log line, or Nextflow's -resume tip, ends the block.
_LOG_LINE = re.compile(r"^\w{3}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \[")
_BLOCK_END = re.compile(r"^Tip:")

_SECTIONS = {
    "Caused by:": "caused_by",
    "Command executed:": "command_executed",
    "Command exit status:": "exit_status",
    "Command output:": "command_output",
    "Command error:": "command_error",
    "Work dir:": "work_dir",
}


def _clean(body: list[str]) -> str | None:
    text = textwrap.dedent("\n".join(body)).strip()
    if not text or text == "(empty)":
        return None
    return text


def _split_sections(block: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    field: str | None = None
    body: list[str] = []
    for line in block:
        if (header := _SECTIONS.get(line.strip())) and not line.startswith(" "):
            if field and (text := _clean(body)):
                found[field] = text
            field, body = header, []
        elif field:
            body.append(line)
    if field and (text := _clean(body)):
        found[field] = text
    return found


def from_log(log_path: Path, read_work_dir: bool = True) -> Evidence | None:
    """Evidence for the first failed task, or None if the log records no failure."""
    lines = log_path.read_text(errors="replace").splitlines()

    start = next(
        ((i, m) for i, line in enumerate(lines) if (m := _FAILURE_LINE.search(line))),
        None,
    )
    if start is None:
        return None
    index, match = start

    block: list[str] = []
    for line in lines[index + 1 :]:
        if _LOG_LINE.match(line) or _BLOCK_END.match(line):
            break
        block.append(line)

    evidence = Evidence(process=match.group("process"), **_split_sections(block))
    if read_work_dir and evidence.work_dir:
        _fill_from_work_dir(evidence)
    return evidence


def _fill_from_work_dir(evidence: Evidence) -> None:
    """Nextflow truncates long stderr in the log; the work dir holds the full text."""
    work_dir = Path(evidence.work_dir)
    err = work_dir / ".command.err"
    if err.is_file() and (text := err.read_text(errors="replace").strip()):
        evidence.command_error = text
    exitcode = work_dir / ".exitcode"
    if evidence.exit_status is None and exitcode.is_file():
        evidence.exit_status = exitcode.read_text(errors="replace").strip() or None
