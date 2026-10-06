from pathlib import Path

from nfdx.evidence import from_log

CASES = Path(__file__).resolve().parents[1] / "cases"


def test_parses_a_full_failure_block():
    evidence = from_log(CASES / "real-corrupt-gzip" / "log.txt", read_work_dir=False)
    assert evidence is not None
    assert evidence.process.startswith("fastp")
    assert evidence.exit_status == "255"
    assert "invalid gzip header" in evidence.command_error


def test_every_section_is_optional():
    # Conda env creation fails before the task runs: only Caused by is emitted.
    evidence = from_log(CASES / "real-conda-solve" / "log.txt", read_work_dir=False)
    assert evidence is not None
    assert evidence.command_executed is None
    assert evidence.work_dir is None
    assert "PackagesNotFoundError" in evidence.caused_by


def test_empty_sections_become_none():
    evidence = from_log(CASES / "inj-silent-exit255" / "log.txt", read_work_dir=False)
    assert evidence is not None
    assert evidence.command_output is None  # logged as "(empty)"
    assert evidence.exit_status == "255"


def test_log_without_a_failure_returns_none(tmp_path):
    log = tmp_path / "clean.log"
    log.write_text("Sep-01 10:00:00.000 [main] DEBUG nextflow.Session - all good\n")
    assert from_log(log) is None


def test_truncated_block_loses_later_sections():
    evidence = from_log(CASES / "inj-truncated-log" / "log.txt", read_work_dir=False)
    assert evidence is not None
    assert evidence.command_error is None
