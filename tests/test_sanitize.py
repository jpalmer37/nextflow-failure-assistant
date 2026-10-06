from nfdx.sanitize import scrub
from nfdx.schema import Evidence
from nfdx.sanitize import scrub_evidence


def test_directories_go_but_filenames_stay():
    # The filename carries the signal in a real case: the stray x is the bug.
    out = scrub("/Users/someone/work/run/SRR1_R2.trim.fastq.gzx: No such file")
    assert "/Users/" not in out
    assert "SRR1_R2.trim.fastq.gzx" in out


def test_urls_survive():
    text = "  - https://conda.anaconda.org/conda-forge/osx-64"
    assert scrub(text) == text


def test_email_and_ip_go():
    out = scrub("reach me at someone@example.org from 10.0.12.44")
    assert "someone@example.org" not in out and "10.0.12.44" not in out


def test_extra_patterns_applied():
    assert "BCC1234" not in scrub("sample BCC1234 failed", extra=(r"BCC\d+",))


def test_scrub_evidence_covers_every_field():
    dirty = Evidence(
        process="p",
        command_error="/Users/someone/x/err.txt missing",
        work_dir="/Users/someone/work/ab/cd",
    )
    clean = scrub_evidence(dirty)
    assert "/Users/" not in (clean.command_error or "")
    assert "/Users/" not in (clean.work_dir or "")
