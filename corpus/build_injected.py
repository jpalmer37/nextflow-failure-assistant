"""Generate injected failure cases by running a real pipeline that breaks on purpose.

The logs are genuine Nextflow output; only the trigger is chosen, which is what
makes the label ground truth. Scenarios that need an unavailable tool (docker,
conda) are skipped and reported rather than faked.

Run: python corpus/build_injected.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfdx.evidence import _BLOCK_END, _FAILURE_LINE, _LOG_LINE  # noqa: E402
from nfdx.sanitize import scrub  # noqa: E402

RUN_TIMEOUT = 300


def nf(script: str, directives: str = "") -> str:
    return f"""#!/usr/bin/env nextflow
nextflow.enable.dsl=2

process breakme {{
{directives}
    output:
    path 'result.txt'

    script:
    \"\"\"
{script}
    \"\"\"
}}

workflow {{ breakme() }}
"""


SCENARIOS = [
    {
        "id": "inj-command-not-found",
        "split": "dev",
        "cause_category": "command_not_found",
        "resolving_check_id": "command_not_found.0",
        "script": "    definitely_not_a_real_tool --input in.fq > result.txt",
    },
    {
        "id": "inj-tool-bad-flag",
        "split": "dev",
        "cause_category": "tool_error",
        "resolving_check_id": "tool_error.0",
        "script": "    sort --definitely-not-a-flag /etc/hosts > result.txt",
    },
    {
        "id": "inj-missing-output",
        "split": "dev",
        "cause_category": "missing_output",
        "resolving_check_id": "missing_output.0",
        "script": "    echo 'work happened' > actual_name.txt",
    },
    {
        "id": "inj-permission-denied",
        "split": "dev",
        "cause_category": "permission_denied",
        "resolving_check_id": "permission_denied.0",
        "script": (
            "    echo secret > locked.txt\n"
            "    chmod 000 locked.txt\n"
            "    cat locked.txt > result.txt"
        ),
    },
    {
        "id": "inj-timeout",
        "split": "dev",
        "cause_category": "timeout",
        "resolving_check_id": "timeout.0",
        # SIGTERM to the task shell: the same signal a scheduler walltime kill sends.
        "script": "    kill -TERM \\$\\$\n    echo done > result.txt",
    },
    {
        "id": "inj-out-of-memory",
        "split": "dev",
        "cause_category": "out_of_memory",
        "resolving_check_id": "out_of_memory.0",
        # Bounded by -Xmx32m, so it fails fast instead of eating the host. A Java
        # heap error is also the OOM shape most bioinformatics tools actually throw.
        "script": (
            "    printf '%s\\n' 'public class Oom {'"
            " '  public static void main(String[] a) {'"
            " '    java.util.List<byte[]> held = new java.util.ArrayList<>();'"
            " '    while (true) held.add(new byte[1048576]);'"
            " '  }' '}' > Oom.java\n"
            "    javac Oom.java\n"
            "    java -Xmx32m Oom > result.txt"
        ),
        "requires": "javac",
    },
    {
        "id": "inj-malformed-samplesheet",
        "split": "dev",
        "cause_category": "malformed_samplesheet",
        "resolving_check_id": "malformed_samplesheet.0",
        "script": (
            "    printf 'sampleID,fastq_1\\ns1,a.fq.gz\\n' > samplesheet.csv\n"
            "    python3 -c \"import csv,sys; "
            "r=csv.DictReader(open('samplesheet.csv')); "
            "h=r.fieldnames; "
            "sys.exit('ERROR: Missing required column: sample. Found header: %s' % h)\" "
            "> result.txt"
        ),
    },
    {
        "id": "inj-container-unavailable",
        "split": "dev",
        "cause_category": "container_unavailable",
        "resolving_check_id": "container_unavailable.0",
        "script": "    echo hi > result.txt",
        "directives": "    container 'example.invalid/nfdx/no-such-image:0.0.0'",
        "args": ["-with-docker"],
        "requires": "docker",
    },
    {
        "id": "inj-missing-input",
        "split": "test",
        "cause_category": "missing_input",
        "resolving_check_id": "missing_input.0",
        "script": "    cat reference_genome.fasta > result.txt",
    },
    {
        "id": "inj-corrupt-gzip",
        "split": "test",
        "cause_category": "corrupt_input",
        "resolving_check_id": "corrupt_input.0",
        "script": (
            "    printf 'this is not gzip at all' > reads.fq.gz\n"
            "    gunzip -c reads.fq.gz > result.txt"
        ),
    },
    {
        "id": "inj-null-interpolation",
        "split": "test",
        "cause_category": "bad_interpolation",
        "resolving_check_id": "bad_interpolation.0",
        "script": "    java -Xmx${params.heap_gb}g -version 2> result.txt",
    },
    {
        "id": "inj-conda-solve",
        "split": "test",
        "cause_category": "conda_solve_failed",
        "resolving_check_id": "conda_solve_failed.0",
        "script": "    echo hi > result.txt",
        "directives": "    conda 'bioconda::nfdx-no-such-package=9.9.9'",
        "args": ["-with-conda", "true"],
        "requires": "conda",
    },
    {
        "id": "inj-silent-exit255",
        "split": "test",
        "cause_category": "insufficient_evidence",
        "resolving_check_id": "insufficient_evidence.0",
        "script": "    exit 255",
    },
    {
        "id": "inj-silent-exit1",
        "split": "test",
        "cause_category": "insufficient_evidence",
        "resolving_check_id": "insufficient_evidence.0",
        "script": "    exit 1",
    },
    {
        "id": "inj-truncated-log",
        "split": "test",
        "cause_category": "insufficient_evidence",
        "resolving_check_id": "insufficient_evidence.0",
        "script": "    cat reference_genome.fasta > result.txt",
        "truncate_after": "Command executed:",
    },
]


def available(requirement: str | None) -> bool:
    if requirement is None:
        return True
    if requirement == "docker":
        if not shutil.which("docker"):
            return False
        return subprocess.run(["docker", "info"], capture_output=True).returncode == 0
    return bool(shutil.which(requirement) or shutil.which("mamba"))


def excerpt(log_text: str) -> str | None:
    lines = log_text.splitlines()
    start = next((i for i, line in enumerate(lines) if _FAILURE_LINE.search(line)), None)
    if start is None:
        return None
    out = [lines[start]]
    for line in lines[start + 1 :]:
        out.append(line)
        if _BLOCK_END.match(line) or _LOG_LINE.match(line):
            break
    return "\n".join(out) + "\n"


def run_scenario(scenario: dict, root: Path) -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        (work / "breakme.nf").write_text(
            nf(scenario["script"], scenario.get("directives", ""))
        )
        try:
            subprocess.run(
                ["nextflow", "-log", ".nextflow.log", "run", "breakme.nf"]
                + scenario.get("args", []),
                cwd=work,
                capture_output=True,
                timeout=RUN_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            print(f"  {scenario['id']}: timed out after {RUN_TIMEOUT}s")
            return None

        log = work / ".nextflow.log"
        if not log.is_file():
            print(f"  {scenario['id']}: no log produced")
            return None
        block = excerpt(log.read_text(errors="replace"))
        if block is None:
            print(f"  {scenario['id']}: no task-failure block in log")
            return None

    if marker := scenario.get("truncate_after"):
        head, sep, _ = block.partition(marker)
        block = head + sep + "\n" if sep else block

    case_dir = root / "cases" / scenario["id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "log.txt").write_text(scrub(block))
    (case_dir / "label.json").write_text(
        json.dumps(
            {
                "id": scenario["id"],
                "origin": "injected",
                "split": scenario["split"],
                "cause_category": scenario["cause_category"],
                "resolving_check_id": scenario["resolving_check_id"],
            },
            indent=2,
        )
        + "\n"
    )
    return scenario["id"]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    made, skipped = [], []
    for scenario in SCENARIOS:
        if not available(scenario.get("requires")):
            print(f"  {scenario['id']}: skipped, {scenario['requires']} unavailable")
            skipped.append(scenario["id"])
            continue
        print(f"running {scenario['id']}")
        if run_scenario(scenario, root):
            made.append(scenario["id"])
        else:
            skipped.append(scenario["id"])
    print(f"\n{len(made)} injected cases written, {len(skipped)} skipped")
    if skipped:
        print("skipped: " + ", ".join(skipped))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
