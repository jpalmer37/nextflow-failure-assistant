import argparse
import json
import sys
from pathlib import Path

from nfdx import baseline, diagnose, evidence as evidence_mod
from nfdx.sanitize import scrub_evidence


def main():
    parser = argparse.ArgumentParser(
        prog="nfdx", description="Diagnose a failed Nextflow run from its log."
    )
    parser.add_argument("-l", "--log", required=True, type=Path, help="path to .nextflow.log")
    parser.add_argument(
        "-a", "--arm", choices=("baseline", "llm"), default="baseline", help="which diagnoser"
    )
    parser.add_argument("-m", "--model", default=diagnose.DEFAULT_MODEL)
    parser.add_argument("--backend", choices=("sdk", "cli"), default=None)
    parser.add_argument("-o", "--output", type=Path, help="write JSON here instead of stdout")
    parser.add_argument(
        "--redact",
        action="append",
        default=[],
        metavar="REGEX",
        help="additional pattern to scrub; repeatable",
    )
    parser.add_argument(
        "--no-work-dir",
        action="store_true",
        help="do not read .command.err from the work directory",
    )
    args = parser.parse_args()

    found = evidence_mod.from_log(args.log, read_work_dir=not args.no_work_dir)
    if found is None:
        print(f"no task failure found in {args.log}", file=sys.stderr)
        return 1

    clean = scrub_evidence(found, tuple(args.redact))
    if args.arm == "baseline":
        result = baseline.diagnose(clean)
    else:
        result = diagnose.diagnose(clean.as_text(), model=args.model, backend=args.backend)

    payload = json.dumps(
        {"evidence": clean.model_dump(), "diagnosis": result.model_dump(mode="json")}, indent=2
    )
    if args.output:
        args.output.write_text(payload + "\n")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
