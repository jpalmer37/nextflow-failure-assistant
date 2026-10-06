import json

import pytest

from nfdx.diagnose import ModelOutputError, parse_model_output
from nfdx.schema import CauseCategory, Diagnosis

VALID = {
    "cause_category": "corrupt_input",
    "explanation": "not valid gzip",
    "supporting_lines": ["ERROR: igzip: Error invalid gzip header found: a.fq.gz"],
    "suggested_check_ids": ["corrupt_input.0"],
    "confidence": 0.8,
}


def test_recovers_json_wrapped_in_prose():
    result = parse_model_output(f"Here you go:\n```json\n{json.dumps(VALID)}\n```")
    assert result.cause_category is CauseCategory.CORRUPT_INPUT


def test_rejects_invented_check_ids():
    payload = VALID | {"suggested_check_ids": ["corrupt_input.0", "made.up.99"]}
    with pytest.raises(ModelOutputError, match="invented check ids"):
        parse_model_output(json.dumps(payload))


def test_rejects_unknown_category():
    with pytest.raises(ModelOutputError):
        parse_model_output(json.dumps(VALID | {"cause_category": "gremlins"}))


def test_rejects_extra_fields():
    with pytest.raises(ModelOutputError):
        parse_model_output(json.dumps(VALID | {"severity": "high"}))


def test_rejects_out_of_range_confidence():
    with pytest.raises(ModelOutputError):
        parse_model_output(json.dumps(VALID | {"confidence": 1.5}))


def test_rejects_text_without_json():
    with pytest.raises(ModelOutputError):
        parse_model_output("I could not work it out, sorry.")


def test_diagnosis_forbids_extra_fields():
    with pytest.raises(Exception):
        Diagnosis(**VALID, unexpected="x")
