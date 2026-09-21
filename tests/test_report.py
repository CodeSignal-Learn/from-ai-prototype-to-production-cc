"""The comparison report refuses unlike runs and recomputes everything from the rows."""
import json

import pytest

from evals.report import ProtocolError, compare, load_side, render


def item(id_, category, acceptable, verdicts=None, article="a", expected="a"):
    v = verdicts or {"R1": "pass", "R2": "pass", "R3": "pass", "R4": "pass", "R5": "pass"}
    return {"id": id_, "expected_category": category, "tags": ["t"], "acceptable": acceptable, "verdicts": v,
            "draft": "d", "article": article, "expected_article": expected}


def write_run(root, run_id, items, prompt, variant, sha="abc", split="held_out", judge=None):
    d = root / run_id
    d.mkdir(parents=True)
    (d / "items.jsonl").write_text("\n".join(json.dumps(i) for i in items) + "\n")
    (d / "summary.json").write_text(json.dumps({
        "run_id": run_id, "dataset": "v1", "dataset_sha256": sha, "split": split, "unjudged": 0,
        "versions": {"prompt": prompt, "prompt_variant": variant}, "judge": judge or {"model": "m", "prompt": "j"},
    }))


@pytest.fixture
def runs(tmp_path):
    fail = {"R1": "fail", "R2": "missed", "R3": "pass", "R4": "pass", "R5": "pass"}
    write_run(tmp_path, "b1", [item("a", "billing", True), item("b", "billing", False, fail), item("c", "other", True)], "p1", "v1")
    write_run(tmp_path, "b2", [item("a", "billing", True), item("b", "billing", False, fail), item("c", "other", False, fail)], "p1", "v1")
    write_run(tmp_path, "c1", [item("a", "billing", True), item("b", "billing", True), item("c", "other", True)], "p2", "v2")
    write_run(tmp_path, "c2", [item("a", "billing", False, fail), item("b", "billing", True), item("c", "other", True)], "p2", "v2")
    return tmp_path


def test_means_deltas_and_paired_lists(runs):
    report = compare(load_side(["b1", "b2"], runs), load_side(["c1", "c2"], runs))
    assert report["baseline"]["spread"]["acceptable"] == {"mean": 1.5, "min": 1, "max": 2, "values": [2, 1]}
    assert report["candidate"]["spread"]["acceptable"]["mean"] == 2.5
    assert report["delta_mean"]["acceptable"] == 1.0
    assert report["delta_mean"]["R2_missed"] == -1.0
    paired = report["paired"]
    assert [r["id"] for r in paired["improved"]] == ["b", "c"] or {r["id"] for r in paired["improved"]} == {"b", "c"}
    assert [r["id"] for r in paired["regressed"]] == ["a"]
    assert set(paired["unstable_across_repeats"]) == {"a", "c"}
    assert report["by_category"]["candidate"]["billing"] == {"cases": 2, "acceptable_mean": 1.5}
    text = render(report)
    assert "regressed a:" in text and "| acceptable |" in text


def test_different_datasets_are_refused(runs):
    write_run(runs, "x", [item("a", "billing", True)], "p3", "v2", sha="other")
    with pytest.raises(ProtocolError, match="different datasets"):
        compare(load_side(["b1"], runs), load_side(["x"], runs))


def test_mixed_prompts_on_one_side_are_refused(runs):
    write_run(runs, "b3", [item("a", "billing", True), item("b", "billing", True), item("c", "other", True)], "p9", "v1")
    with pytest.raises(ProtocolError, match="one prompt version"):
        compare(load_side(["b1", "b3"], runs), load_side(["c1"], runs))


def test_same_prompt_on_both_sides_is_refused(runs):
    with pytest.raises(ProtocolError, match="same prompt"):
        compare(load_side(["b1"], runs), load_side(["b2"], runs))


def test_different_case_sets_are_refused(runs):
    write_run(runs, "short", [item("a", "billing", True)], "p2", "v2")
    with pytest.raises(ProtocolError, match="same cases"):
        compare(load_side(["b1"], runs), load_side(["short"], runs))


def test_a_different_judge_is_refused(runs):
    write_run(runs, "j", [item("a", "billing", True), item("b", "billing", True), item("c", "other", True)], "p2", "v2", judge={"model": "m", "prompt": "other"})
    with pytest.raises(ProtocolError, match="different judges"):
        compare(load_side(["b1"], runs), load_side(["j"], runs))
