"""Score an arm against the labelled corpus.

Usage:
    python evaluate.py --split dev  --arm baseline
    python evaluate.py --split test --arm llm --output reports/test-llm.json
"""

import argparse
import json
import time
from pathlib import Path

from nfdx import baseline, diagnose
from nfdx.evidence import from_log
from nfdx.schema import CauseCategory, Diagnosis

ABSTAIN = CauseCategory.INSUFFICIENT_EVIDENCE.value


def load_cases(root: Path, split: str) -> list[dict]:
    cases = []
    for label_path in sorted(root.glob("cases/*/label.json")):
        label = json.loads(label_path.read_text())
        if split != "all" and label["split"] != split:
            continue
        label["log"] = label_path.parent / "log.txt"
        cases.append(label)
    return cases


def grounded(result: Diagnosis, evidence_text: str) -> bool:
    """Every supporting line must appear verbatim in the evidence."""
    return all(line.strip() in evidence_text for line in result.supporting_lines)


def score_rows(rows: list[dict]) -> dict:
    total = len(rows)
    scored = [r for r in rows if r["error"] is None]
    abstain_cases = [r for r in scored if r["expected_category"] == ABSTAIN]
    answerable = [r for r in scored if r["expected_category"] != ABSTAIN]

    def rate(subset: list[dict], key: str) -> float | None:
        return round(sum(r[key] for r in subset) / len(subset), 3) if subset else None

    return {
        "cases": total,
        "parse_failures": total - len(scored),
        "category_accuracy": rate(scored, "category_correct"),
        "first_check_accuracy": rate(scored, "first_check_correct"),
        "grounding_rate": rate([r for r in scored if r["supporting_lines"]], "grounded"),
        "abstained_when_it_should": rate(abstain_cases, "abstained"),
        "abstained_when_it_should_not": rate(answerable, "abstained"),
        "median_latency_s": round(
            sorted(r["latency_s"] for r in scored)[len(scored) // 2], 3
        )
        if scored
        else None,
    }


def run_case(case: dict, arm: str, model: str, backend: str | None) -> dict:
    evidence = from_log(case["log"], read_work_dir=False)
    row = {
        "id": case["id"],
        "origin": case["origin"],
        "expected_category": case["cause_category"],
        "expected_check": case["resolving_check_id"],
        "error": None,
    }
    if evidence is None:
        # A log with no failure block is itself insufficient evidence.
        row |= {
            "predicted_category": ABSTAIN,
            "predicted_check": None,
            "category_correct": case["cause_category"] == ABSTAIN,
            "first_check_correct": case["resolving_check_id"] == "insufficient_evidence.0",
            "abstained": True,
            "supporting_lines": 0,
            "grounded": True,
            "latency_s": 0.0,
        }
        return row

    started = time.monotonic()
    try:
        if arm == "baseline":
            result = baseline.diagnose(evidence)
        else:
            result = diagnose.diagnose(evidence.as_text(), model=model, backend=backend)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"
        row["latency_s"] = round(time.monotonic() - started, 3)
        return row
    latency = time.monotonic() - started

    predicted_check = result.suggested_check_ids[0] if result.suggested_check_ids else None
    row |= {
        "predicted_category": result.cause_category.value,
        "predicted_check": predicted_check,
        "category_correct": result.cause_category.value == case["cause_category"],
        "first_check_correct": predicted_check == case["resolving_check_id"],
        "abstained": result.cause_category.value == ABSTAIN,
        "supporting_lines": len(result.supporting_lines),
        "grounded": grounded(result, evidence.as_text()),
        "confidence": result.confidence,
        "latency_s": round(latency, 3),
    }
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Score an arm against the corpus.")
    parser.add_argument("--split", choices=("dev", "test", "all"), default="dev")
    parser.add_argument("--arm", choices=("baseline", "llm"), default="baseline")
    parser.add_argument("--model", default=diagnose.DEFAULT_MODEL)
    parser.add_argument("--backend", choices=("sdk", "cli"), default=None)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    cases = load_cases(root, args.split)
    if not cases:
        print(f"no cases in split {args.split}")
        return 1

    rows = [run_case(c, args.arm, args.model, args.backend) for c in cases]
    report = {
        "arm": args.arm,
        "model": args.model if args.arm == "llm" else None,
        "backend": (args.backend or diagnose.default_backend()) if args.arm == "llm" else None,
        "split": args.split,
        "overall": score_rows(rows),
        "by_origin": {
            origin: score_rows([r for r in rows if r["origin"] == origin])
            for origin in sorted({r["origin"] for r in rows})
        },
        "rows": rows,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")

    print(f"{args.arm} / {args.split}")
    for name, stats in [("overall", report["overall"])] + list(report["by_origin"].items()):
        print(f"  {name:10s} {json.dumps(stats)}")
    for row in rows:
        if row["error"]:
            print(f"  ERROR {row['id']}: {row['error']}")
        elif not row["category_correct"]:
            print(f"  miss  {row['id']}: expected {row['expected_category']}, got {row['predicted_category']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
