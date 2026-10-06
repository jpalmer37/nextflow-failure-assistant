"""Extract the five real failures from local run logs into sanitized cases.

Source logs stay on John's machine; only the sanitized failure block is written
to cases/, because that directory is committed to a public repository.

Run once: python corpus/build_real.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfdx.evidence import _BLOCK_END, _FAILURE_LINE, _LOG_LINE  # noqa: E402
from nfdx.sanitize import scrub  # noqa: E402

CASES = (
    {
        "id": "real-conda-solve",
        "source": "~/work/flu/.nextflow.log",
        "cause_category": "conda_solve_failed",
        "resolving_check_id": "conda_solve_failed.0",
        "note": "spades=3.15.3* absent for osx-64; env creation aborted before the task ran.",
    },
    {
        "id": "real-corrupt-gzip",
        "source": "~/work/flu/.nextflow.log.2",
        "cause_category": "corrupt_input",
        "resolving_check_id": "corrupt_input.0",
        "note": "fastp/igzip rejected the R1 FASTQ; five samples shared one cause.",
    },
    {
        "id": "real-missing-reference",
        "source": "~/work/norovirus/.nextflow.log.1",
        "cause_category": "missing_input",
        "resolving_check_id": "missing_input.0",
        "note": "augur align could not read the reference FASTA.",
    },
    {
        "id": "real-gzx-filename",
        "source": "~/work/testing/.nextflow.log.1",
        "cause_category": "bad_interpolation",
        "resolving_check_id": "bad_interpolation.0",
        "note": "A stray x produced *.fastq.gzx. Surfaces as 'No such file', so the "
        "error text points at the wrong cause.",
    },
    {
        "id": "real-xmx-null",
        "source": "~/work/testing/.nextflow.log.5",
        "cause_category": "bad_interpolation",
        "resolving_check_id": "bad_interpolation.0",
        "note": "A null memory value produced -Xmxnullg.",
    },
)


def excerpt(log_path: Path) -> str:
    """The failure block, from the ERROR line through Nextflow's resume tip."""
    lines = log_path.read_text(errors="replace").splitlines()
    start = next(i for i, line in enumerate(lines) if _FAILURE_LINE.search(line))
    out = [lines[start]]
    for line in lines[start + 1 :]:
        out.append(line)
        if _BLOCK_END.match(line):
            break
        if _LOG_LINE.match(line):
            break
    return "\n".join(out) + "\n"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    written = 0
    for case in CASES:
        source = Path(case["source"]).expanduser()
        if not source.is_file():
            print(f"skip {case['id']}: {source} not found")
            continue
        case_dir = root / "cases" / case["id"]
        case_dir.mkdir(parents=True, exist_ok=True)
        (case_dir / "log.txt").write_text(scrub(excerpt(source)))
        (case_dir / "label.json").write_text(
            json.dumps(
                {
                    "id": case["id"],
                    "origin": "real",
                    "split": "test",
                    "cause_category": case["cause_category"],
                    "resolving_check_id": case["resolving_check_id"],
                    "note": case["note"],
                },
                indent=2,
            )
            + "\n"
        )
        written += 1
        print(f"wrote {case['id']}")
    print(f"{written} real cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
