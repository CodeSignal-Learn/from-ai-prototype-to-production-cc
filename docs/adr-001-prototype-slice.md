# ADR 001: shape of the POC prototype

## Status
Accepted for the POC. To be revisited before any production work.

## Context
The rules-based assistant classifies with keywords and drafts from templates. The charter asks
whether a model does better on the same requests without giving up the two properties the team
relies on: nothing is sent without a person, and drafts stay inside the knowledge base.

## Decision
Build a vertical slice that reuses the existing pipeline and swaps two steps:

1. Classification. The model reads the request and returns a category and a confidence value.
   Requests with low confidence go to a person.
2. Drafting. The model writes the reply from the article the existing keyword lookup selects,
   and is instructed to use nothing outside it.

Everything else stays as it is: intake and normalization, the knowledge lookup by category, the
escalation rules for hostile language, legal threats, and short bodies, the never-sent result,
and the CLI batch runner. A `--mode` switch selects rules or model so both can run on the same
requests for the comparison the charter requires.

## Alternatives considered
- Model chooses the article as well as the category. Rejected for the POC: it doubles the
  surface to evaluate and the keyword lookup already works when the category is right.
- Rules first, model only for requests the rules send to `other`. Rejected: it hides the
  model's behavior on the requests the rules get quietly wrong, which is the sponsor's complaint.
- Retrieval over passages instead of whole articles. Deferred: the articles are short and the
  charter excludes changing the knowledge base.

## Consequences
- The comparison is fair: same requests, same lookup, same guards, only the two steps differ.
- The `Result` gains a `confidence` field, `None` in rules mode. `CLAUDE.md` is updated.
- The trial runner in `scripts/run_trial.py` measures both modes against the labels.

## Deliberate shortcuts, to be removed before production
These are accepted for a three-week POC and are listed so nobody mistakes them for design.

- The model name, the confidence threshold, and the token limits are constants in the code.
- No timeouts, retries, or fallback around model calls; a failed call fails the batch.
- Prompts are built by concatenating strings with the request text. Nothing separates
  instructions from customer content.
- The model's JSON answer is parsed and trusted without validation.
- Requests are processed one at a time.
- There is no configuration layer; nothing can change between environments without editing code.
- Token usage is counted in a module-level global for the trial report.
