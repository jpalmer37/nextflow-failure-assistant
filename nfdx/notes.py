"""Troubleshooting notes: the one knowledge source both arms are given.

Kept as a single table so the keyword baseline and the model see identical
knowledge. If the notes lived only in the prompt, a win would mean the model was
told more, not that it matched better.

`signature` is what the baseline greps for. `checks[0]` is the resolving check
the evaluation scores.
"""

from dataclasses import dataclass, field

from nfdx.schema import CauseCategory


@dataclass(frozen=True)
class Note:
    category: CauseCategory
    signature: str
    cause: str
    checks: list[str] = field(default_factory=list)
    # Killed tasks carry no error text, so the exit status is the only signal.
    exit_codes: tuple[int, ...] = ()


# Order matters: the baseline takes the first match, so specific precedes generic.
NOTES: tuple[Note, ...] = (
    Note(
        CauseCategory.CONDA_SOLVE_FAILED,
        r"PackagesNotFoundError|ResolvePackageNotFound|Failed to create Conda environment|libmamba.*failed",
        "Conda could not solve the environment, usually a pinned version absent for this platform.",
        [
            "Search the pinned package and version on the configured channels for this platform",
            "Relax or update the version pin in the environment YAML",
            "Confirm bioconda and conda-forge are both configured",
        ],
    ),
    Note(
        CauseCategory.CONTAINER_UNAVAILABLE,
        r"manifest unknown|Unable to find image|repository does not exist|pull access denied|Error response from daemon",
        "The container image could not be pulled.",
        [
            "Verify the image tag exists in the registry and is spelled correctly",
            "Check registry credentials and network access from the execution node",
        ],
    ),
    Note(
        CauseCategory.CORRUPT_INPUT,
        r"invalid gzip header|not in gzip format|unexpected end of file|Unexpected end of gzip|CRC check failed",
        "An input file is truncated or is not valid gzip despite its extension.",
        [
            "Test the input archive integrity with gzip -t",
            "Re-transfer the input and compare checksums against the source",
        ],
    ),
    Note(
        CauseCategory.OUT_OF_MEMORY,
        r"OutOfMemoryError|MemoryError|Cannot allocate memory|out of memory|Killed|oom-kill",
        "The task exceeded the memory available to it.",
        [
            "Raise the memory directive for this process and resume",
            "Check whether an unusually large input drove the allocation",
        ],
        exit_codes=(137,),
    ),
    Note(
        CauseCategory.BAD_INTERPOLATION,
        r"null(?=[a-zA-Z])|[-\w]*null[gGmM]\b|=null\b|'null'",
        "A pipeline value was interpolated into the command wrongly: resolved to "
        "null, or concatenated into a malformed path or filename. The tool error "
        "names the symptom, so read the command as executed rather than the error.",
        [
            "Read 'Command executed' and find the value that interpolated wrongly",
            "Check the process directive or params entry that feeds this value",
        ],
    ),
    Note(
        CauseCategory.TIMEOUT,
        r"Process exceeded running time|walltime|TIME LIMIT|exceeded the time limit|SIGTERM",
        "The task was killed for exceeding its time limit.",
        [
            "Raise the time directive for this process and resume",
            "Check whether the input size or a hung dependency caused the overrun",
        ],
        exit_codes=(124, 143),
    ),
    Note(
        CauseCategory.PERMISSION_DENIED,
        r"Permission denied|EACCES|not permitted",
        "The task could not read or write a path because of filesystem permissions.",
        [
            "Check read and write permissions on the reported path",
            "Confirm the execution user can reach the work and output directories",
        ],
    ),
    Note(
        CauseCategory.COMMAND_NOT_FOUND,
        r"command not found|No such file or directory: '[^']+'|executable file not found",
        "The tool is not on PATH in the task environment.",
        [
            "Confirm the tool is declared in the process environment or container",
            "Check the environment actually activated for this process",
        ],
    ),
    Note(
        CauseCategory.MISSING_OUTPUT,
        r"Missing output file|did not produce any output|Missing `?output`? file",
        "The task finished but did not produce a file matching its output declaration.",
        [
            "Compare the output declaration glob against what the command actually writes",
            "List the work directory to see the real output filenames",
        ],
    ),
    Note(
        CauseCategory.MALFORMED_SAMPLESHEET,
        r"Missing required column|samplesheet|header.*mismatch|Invalid input file",
        "The samplesheet is missing a required column or has an unexpected header.",
        [
            "Compare the samplesheet header against the schema the pipeline expects",
            "Check for stray whitespace, BOM, or CRLF line endings in the header",
        ],
    ),
    Note(
        CauseCategory.TOOL_ERROR,
        r"unrecognized option|unrecognized arguments|unknown option|invalid option|no such option|usage:",
        "The tool rejected its arguments, usually a flag that this version does not accept.",
        [
            "Compare the flags in 'Command executed' against this tool version's help output",
            "Check whether the pinned tool version changed under the process",
        ],
    ),
    Note(
        CauseCategory.MISSING_INPUT,
        r"No such file or directory|Cannot read reference|make sure the file|does not exist|cannot access",
        "An input the command expects is absent from the task work directory.",
        [
            "Confirm the file was staged into the work directory as an input",
            "Check the channel that supplies this input actually emitted a path",
        ],
    ),
)


NO_EVIDENCE_CHECK = "insufficient_evidence.0"

# Stable IDs so the evaluation can score "was the first suggested check the right
# one" by identity instead of matching free text.
CHECKS: dict[str, str] = {
    f"{note.category.value}.{i}": text
    for note in NOTES
    for i, text in enumerate(note.checks)
} | {NO_EVIDENCE_CHECK: "Inspect .command.err and .command.sh in the work directory"}


def check_ids(category: CauseCategory) -> list[str]:
    return [k for k in CHECKS if k.rsplit(".", 1)[0] == category.value]


def as_markdown() -> str:
    lines = []
    for note in NOTES:
        lines.append(f"## {note.category.value}")
        lines.append(note.cause)
        if note.exit_codes:
            codes = ", ".join(str(c) for c in note.exit_codes)
            lines.append(f"Exit status {codes} indicates this even with no error text.")
        lines.append("Checks, best first:")
        lines.extend(
            f"- {f'{note.category.value}.{i}'}: {text}"
            for i, text in enumerate(note.checks)
        )
        lines.append("")
    lines.append("## insufficient_evidence")
    lines.append("The evidence does not identify a cause.")
    lines.append(f"- {NO_EVIDENCE_CHECK}: {CHECKS[NO_EVIDENCE_CHECK]}")
    return "\n".join(lines)
