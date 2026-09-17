# Handoff: whole-word keyword matching

## What was claimed
`docs/agent-claim.txt`: keyword matching now compares whole words; all routing behavior is
preserved; 16 tests pass.

## What was true
16 tests passed. Routing behavior was not preserved. Running the August batch against the
previous state showed five requests falling to `other`:

- REQ-1009 ("locked out") and REQ-1031 ("stopped working"): two-word keywords never match a
  set of single words.
- REQ-1020 ("shipping.") and REQ-1036 ("package."): punctuation stuck to the word.
- REQ-1030 ("leaks"): plural of a keyword.

The suite did not catch any of this because every routing test used a single lowercase keyword
surrounded by spaces. The smoke test added with the change tested the one case that worked.

## What changed
- `routing.py`: keywords match with word boundaries (`\b...\b`) instead of set membership, so
  multi-word keywords and punctuation work while "reset" still does not match "preset".
  Added `leaks` to the product keywords.
- `tests/test_contract_routing.py`: 15 real batch requests with their expected category,
  covering multi-word keywords, punctuation, hyphens, and tie-breaking.

## Evidence
- Before the repair: 16 passed; 4 of the 15 new contract cases fail; 5 batch requests
  misrouted versus the previous release.
- After the repair: 31 passed; `python3 -m support_assistant.cli data/requests.jsonl` matches
  the previous release line for line.

## Still unverified
- Keywords are still hand-maintained; a new phrasing the list does not contain goes to `other`.
- No test covers the knowledge-base lookup choosing between two articles in one category.
- Draft wording has not been reviewed by the support team.
