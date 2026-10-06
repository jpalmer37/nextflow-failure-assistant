"""Model arm: sanitized evidence plus the notes, in; a validated Diagnosis, out."""

import json
import os
import subprocess

from pydantic import ValidationError

from nfdx import notes
from nfdx.schema import CauseCategory, Diagnosis

DEFAULT_MODEL = "claude-sonnet-5"

PROMPT = """You are diagnosing a failed Nextflow task.

Use only the evidence below. Do not invent file names, paths, or log lines.
Every entry in supporting_lines must be copied verbatim from the evidence.
If the evidence does not identify a cause, answer with cause_category
"insufficient_evidence" rather than guessing.

The tool error often names a symptom rather than the cause. Read the command as
executed, not only the error text.

Troubleshooting notes, with the check IDs you must choose from:
{notes}

Allowed cause_category values:
{categories}

Evidence:
{evidence}

Reply with one JSON object and nothing else. suggested_check_ids must contain
IDs from the notes above, most useful first:
{{"cause_category": "...", "explanation": "...", "supporting_lines": ["..."],
  "suggested_check_ids": ["..."], "confidence": 0.0}}"""


class ModelOutputError(ValueError):
    """Raised when model output does not contain a schema-valid JSON object."""


def _first_json_object(text: str) -> dict:
    stripped = text.strip()
    try:
        value = json.loads(stripped)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    offset = 0
    while (start := stripped.find("{", offset)) >= 0:
        try:
            value, _ = decoder.raw_decode(stripped[start:])
        except json.JSONDecodeError:
            offset = start + 1
            continue
        if isinstance(value, dict):
            return value
        offset = start + 1

    raise ModelOutputError("model output did not contain a JSON object")


def parse_model_output(text: str) -> Diagnosis:
    try:
        result = Diagnosis.model_validate(_first_json_object(text))
    except ValidationError as exc:
        raise ModelOutputError("model output did not match the diagnosis schema") from exc
    if unknown := [c for c in result.suggested_check_ids if c not in notes.CHECKS]:
        raise ModelOutputError(f"model invented check ids: {unknown}")
    return result


def build_prompt(evidence_text: str) -> str:
    return PROMPT.format(
        notes=notes.as_markdown(),
        categories="\n".join(f"- {c.value}" for c in CauseCategory),
        evidence=evidence_text,
    )


def _via_sdk(prompt: str, model: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model=model, max_tokens=1024, messages=[{"role": "user", "content": prompt}]
    )
    return "".join(b.text for b in response.content if b.type == "text")


def _via_cli(prompt: str, model: str) -> str:
    """Route through the Claude Code CLI, for machines with no API key configured."""
    result = subprocess.run(
        ["claude", "-p", "--model", model],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise ModelOutputError(f"claude cli failed: {result.stderr.strip()[:200]}")
    return result.stdout


BACKENDS = {"sdk": _via_sdk, "cli": _via_cli}


def default_backend() -> str:
    return "sdk" if os.environ.get("ANTHROPIC_API_KEY") else "cli"


def diagnose(evidence_text: str, model: str = DEFAULT_MODEL, backend: str | None = None) -> Diagnosis:
    """Evidence must already be sanitized: this call leaves the machine."""
    send = BACKENDS[backend or default_backend()]
    return parse_model_output(send(build_prompt(evidence_text), model))
