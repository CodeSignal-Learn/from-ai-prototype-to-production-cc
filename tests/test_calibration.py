"""Judge calibration compares two raters on identical drafts and refuses anything else."""
from evals.calibration import cohens_kappa, compare, draft_checksum


def item(id_, draft, r3, r4, judged=True):
    return {"id": id_, "draft": draft, "judged": judged, "verdicts": {"R3": r3, "R4": r4}, "evidence": {"R3": ["q"], "R4": "e"}}


def human(id_, draft, r3, r4):
    return {"id": id_, "draft_sha": draft_checksum(draft), "R3": r3, "R4": r4, "R3_evidence": "h3", "R4_evidence": "h4"}


def test_perfect_agreement_has_kappa_one():
    assert cohens_kappa([("pass", "pass"), ("fail", "fail"), ("pass", "pass")]) == 1.0


def test_chance_agreement_has_kappa_zero():
    pairs = [("pass", "pass"), ("pass", "fail"), ("fail", "pass"), ("fail", "fail")]
    assert cohens_kappa(pairs) == 0.0


def test_kappa_needs_two_items():
    assert cohens_kappa([("pass", "pass")]) is None


def test_disagreements_carry_both_sides_evidence():
    items = [item("a", "draft a", "pass", "pass"), item("b", "draft b", "fail", "partial")]
    rows = [human("a", "draft a", "pass", "pass"), human("b", "draft b", "pass", "pass")]
    report = compare(items, rows)
    assert report["judged_by_both"] == 2
    r3 = report["criteria"]["R3"]
    assert r3["agreement"] == 0.5 and r3["judge_stricter"] == 1 and r3["judge_lenient"] == 0
    assert r3["disagreements"] == [{"id": "b", "human": "pass", "judge": "fail", "human_evidence": "h3", "judge_evidence": ["q"]}]
    assert report["criteria"]["R4"]["confusion"] == {"human=pass judge=partial": 1, "human=pass judge=pass": 1}


def test_a_changed_draft_is_never_compared():
    items = [item("a", "new draft", "pass", "pass")]
    rows = [human("a", "old draft", "fail", "fail")]
    report = compare(items, rows)
    assert report["judged_by_both"] == 0
    assert report["skipped"][0]["reason"].startswith("draft changed")


def test_an_unjudged_item_is_skipped():
    items = [item("a", "d", "pass", "pass", judged=False)]
    report = compare(items, [human("a", "d", "pass", "pass")])
    assert report["skipped"][0]["reason"] == "judge did not return a verdict"
