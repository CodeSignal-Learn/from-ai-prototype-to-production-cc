"""The evaluation dataset is a fixture other code trusts: it must validate, stay split, and
carry nothing that looks like real customer data."""
import dataclasses
import json

import pytest

from evals.dataset import (
    SPLITS, DatasetError, build_manifest, dataset_dir, load_cases, read_cases, sensitive_problems, validate_cases,
)


@pytest.fixture(scope="module")
def slugs(articles):
    return {a.slug for a in articles}


@pytest.fixture(scope="module")
def cases(slugs):
    return load_cases("v1", article_slugs=slugs)


def test_v1_loads_and_matches_its_manifest(cases):
    assert len(cases) > 150


def test_every_case_becomes_a_request(cases):
    for case in cases:
        assert case.request.id == case.id


def test_splits_are_disjoint_and_both_present(cases):
    by_split = {split: {c.id for c in cases if c.split == split} for split in SPLITS}
    assert by_split["development"] and by_split["held_out"]
    assert not (by_split["development"] & by_split["held_out"])
    held_out_share = len(by_split["held_out"]) / len(cases)
    assert 0.25 <= held_out_share <= 0.45, held_out_share


def test_trial_cases_are_all_development(cases):
    trial = [c for c in cases if c.source.startswith("trial:")]
    assert len(trial) == 25
    assert {c.split for c in trial} == {"development"}


def test_every_category_and_route_appears_in_both_splits(cases):
    for split in SPLITS:
        subset = [c for c in cases if c.split == split]
        assert {c.expected_category for c in subset} == {"billing", "account_access", "returns_refunds", "orders_shipping", "product_issue", "other"}
        assert {c.expected_route for c in subset} == {"draft", "human_review"}


def test_load_by_split(slugs):
    held_out = load_cases("v1", split="held_out", article_slugs=slugs)
    assert held_out and all(c.split == "held_out" for c in held_out)


def test_a_card_number_that_is_not_the_test_number_is_rejected(cases):
    case = dataclasses.replace(cases[0], record=dict(cases[0].record, body="my card 5500 0000 0000 0004 was charged"))
    assert any("card-like" in p for p in sensitive_problems(case))
    with pytest.raises(DatasetError, match="card-like"):
        validate_cases([case], {case.expected_article} if case.expected_article else set())


def test_the_synthetic_test_card_is_allowed(cases):
    with_card = [c for c in cases if "sensitive" in c.tags]
    assert with_card
    for case in with_card:
        assert sensitive_problems(case) == []
        assert case.expected_route == "human_review"


def test_an_email_outside_example_com_is_rejected(cases):
    case = dataclasses.replace(cases[0], record=dict(cases[0].record, email="someone@gmail.com"))
    assert any("example.com" in p for p in sensitive_problems(case))


def test_a_draft_case_must_name_its_article(cases, slugs):
    case = dataclasses.replace(next(c for c in cases if c.expected_route == "draft"), expected_article=None)
    with pytest.raises(DatasetError, match="needs the article"):
        validate_cases([case], slugs)


def test_a_stale_manifest_is_detected(slugs, tmp_path, monkeypatch):
    version_dir = tmp_path / "v9"
    version_dir.mkdir()
    lines = (dataset_dir("v1") / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    (version_dir / "cases.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr("evals.dataset.DATASETS_DIR", tmp_path)
    (version_dir / "manifest.json").write_text(json.dumps(build_manifest("v9", read_cases("v9"))), encoding="utf-8")
    load_cases("v9", article_slugs=slugs)
    (version_dir / "cases.jsonl").write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="does not describe"):
        load_cases("v9", article_slugs=slugs)
