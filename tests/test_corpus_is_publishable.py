"""The corpus ships in a public repository, so it gets checked like one."""

import json
import re
from pathlib import Path

import pytest

from nfdx.notes import CHECKS
from nfdx.schema import CauseCategory

CASES = Path(__file__).resolve().parents[1] / "cases"
LEAKS = re.compile(r"/Users/|/home/|\b(?:\d{1,3}\.){3}\d{1,3}\b|[\w.+-]+@[\w-]+\.[\w.-]+")

CASE_DIRS = sorted(p for p in CASES.iterdir() if p.is_dir())


@pytest.mark.parametrize("case", CASE_DIRS, ids=lambda p: p.name)
def test_no_local_paths_or_contact_details(case):
    found = LEAKS.findall((case / "log.txt").read_text())
    assert not found, f"{case.name} leaks {found[:3]}"


@pytest.mark.parametrize("case", CASE_DIRS, ids=lambda p: p.name)
def test_label_is_well_formed(case):
    label = json.loads((case / "label.json").read_text())
    assert label["split"] in {"dev", "test"}
    assert label["origin"] in {"real", "injected"}
    CauseCategory(label["cause_category"])
    assert label["resolving_check_id"] in CHECKS


def test_no_cause_family_spans_both_splits():
    """Tuning on a family then testing on it would leak; the real cases are the probe."""
    splits = {}
    for case in CASE_DIRS:
        label = json.loads((case / "label.json").read_text())
        splits.setdefault(label["cause_category"], set()).add(label["split"])
    spanning = {k: v for k, v in splits.items() if len(v) > 1}
    assert not spanning, f"families in both splits: {spanning}"
