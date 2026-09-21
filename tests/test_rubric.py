"""The rubric is data other code depends on: it must load, agree with its text, and decide."""
import json

import pytest

from evals.rubric import DETERMINISTIC, JUDGED, RUBRIC_JSON, RUBRIC_MD, RubricError, check_against_markdown, load_rubric


@pytest.fixture(scope="module")
def rubric():
    return load_rubric()


def test_rubric_has_both_kinds_of_criteria(rubric):
    kinds = {c.kind for c in rubric.criteria}
    assert kinds == {DETERMINISTIC, JUDGED}
    assert [c.id for c in rubric.deterministic] == ["R1", "R2", "R5"]
    assert [c.id for c in rubric.judged] == ["R3", "R4"]


def test_judged_criteria_say_what_evidence_a_verdict_carries(rubric):
    for criterion in rubric.judged:
        assert criterion.evidence and "quote" in criterion.evidence.lower()


def test_factual_support_is_the_blocking_criterion(rubric):
    assert rubric.blocking == ("R3",)


def test_markdown_and_json_describe_the_same_criteria(rubric):
    check_against_markdown(rubric, RUBRIC_MD.read_text(encoding="utf-8"))


def test_a_renamed_heading_is_caught(rubric):
    text = RUBRIC_MD.read_text(encoding="utf-8").replace("### R3 Factual support (judged)", "### R3 Grounding (judged)")
    with pytest.raises(RubricError, match="differing \\['R3'\\]"):
        check_against_markdown(rubric, text)


def test_a_judged_criterion_without_evidence_is_rejected(tmp_path):
    data = json.loads(RUBRIC_JSON.read_text(encoding="utf-8"))
    for raw in data["criteria"]:
        raw.pop("evidence", None)
    broken = tmp_path / "rubric.json"
    broken.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RubricError, match="R3 is judged"):
        load_rubric(broken, RUBRIC_MD)


@pytest.mark.parametrize("verdicts, expected", [
    ({"R1": "pass", "R2": "pass", "R3": "pass", "R4": "pass", "R5": "pass"}, True),
    ({"R1": "pass", "R2": "pass", "R3": "pass", "R4": "partial", "R5": "pass"}, True),
    ({"R1": "pass", "R2": "pass", "R3": "fail", "R4": "pass", "R5": "pass"}, False),
    ({"R1": "pass", "R2": "pass", "R3": "pass", "R4": "fail", "R5": "pass"}, False),
    ({"R1": "fail", "R2": "pass", "R3": "pass", "R4": "pass", "R5": "pass"}, False),
    ({"R1": "pass", "R2": "missed", "R3": "pass", "R4": "pass", "R5": "pass"}, False),
    ({"R1": "pass", "R2": "over", "R3": "pass", "R4": "pass", "R5": "pass"}, False),
])
def test_acceptance_rule(rubric, verdicts, expected):
    assert rubric.acceptable(verdicts) is expected


def test_an_unknown_verdict_is_rejected(rubric):
    with pytest.raises(RubricError, match="R4 verdict 'maybe'"):
        rubric.acceptable({"R1": "pass", "R2": "pass", "R3": "pass", "R4": "maybe", "R5": "pass"})
