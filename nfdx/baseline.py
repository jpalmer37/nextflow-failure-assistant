"""Keyword baseline: first matching signature in the notes table wins.

This is the bar the model has to clear. Nextflow usually prints the cause in
plain text under `Command error:`, so it is a stronger baseline than it looks.
"""

import re

from nfdx.notes import NOTES, NO_EVIDENCE_CHECK, check_ids
from nfdx.schema import CauseCategory, Diagnosis, Evidence

# Fields searched for a signature, most specific first.
_SEARCH_ORDER = ("command_error", "caused_by", "command_output", "command_executed")


def diagnose(evidence: Evidence) -> Diagnosis:
    for note in NOTES:
        pattern = re.compile(note.signature, re.IGNORECASE | re.MULTILINE)
        for field in _SEARCH_ORDER:
            text = getattr(evidence, field)
            if not text:
                continue
            if match := pattern.search(text):
                return Diagnosis(
                    cause_category=note.category,
                    explanation=note.cause,
                    supporting_lines=[_line_of(text, match.start())],
                    suggested_check_ids=check_ids(note.category),
                    confidence=0.5,
                )

    for note in NOTES:
        if note.exit_codes and _exit_code(evidence) in note.exit_codes:
            return Diagnosis(
                cause_category=note.category,
                explanation=note.cause,
                supporting_lines=[evidence.exit_status.strip()],
                suggested_check_ids=check_ids(note.category),
                confidence=0.4,
            )

    return Diagnosis(
        cause_category=CauseCategory.INSUFFICIENT_EVIDENCE,
        explanation="No known signature matched the evidence.",
        supporting_lines=[],
        suggested_check_ids=[NO_EVIDENCE_CHECK],
        confidence=0.0,
    )


def _exit_code(evidence: Evidence) -> int | None:
    try:
        return int((evidence.exit_status or "").strip())
    except ValueError:
        return None


def _line_of(text: str, offset: int) -> str:
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return text[start : end if end != -1 else len(text)].strip()
