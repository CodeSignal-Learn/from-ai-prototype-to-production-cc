# Evaluation dataset v1

`evals/datasets/v1/cases.jsonl`, 168 cases, described by `evals/datasets/v1/manifest.json`.
Loading through `evals.dataset.load_cases` validates every case and refuses a manifest that does
not match the file, so a run that names `v1` saw exactly these cases.

## What a case holds

| Field | Purpose |
| --- | --- |
| `request` | A complete support request record, as intake receives it |
| `expected.category`, `expected.route` | The labels R1 and R2 of the rubric compare against |
| `expected.article` | The article that grounds an acceptable draft; the nearest article for a request a person must handle; `null` for `other` |
| `reply_must`, `reply_must_not` | What an acceptable reply says and does not say, in words a reviewer or a judge applies under R3 and R4 |
| `must_not_mention` | Lowercase phrases that never belong in a draft for this request; checked deterministically |
| `kind` | `realistic`, `edge`, or `insufficient_information` |
| `tags` | Why the case is in the set: `keywordless`, `not-covered`, `action-required`, `hostile`, `legal`, `injection`, `sensitive`, `two-topics`, `overlap`, `oversized`, and so on |
| `split` | `development` or `held_out` |
| `source` | `trial:REQ-NNNN` for the 25 POC trial requests, `new` otherwise |

## How the cases were chosen

The 25 trial requests from the POC are carried over unchanged, with their labels. Every prompt
in the assistant was written and revised while looking at them, so they are development cases
by definition and the loader refuses to hold one out.

The new cases cover each category with requests the articles answer and requests they do not.
For every category there are requests phrased without the routing keywords, requests that ask
for an action on an order or account, requests the knowledge base does not cover, and one
request each with hostile language, a legal threat, and a pasted card number. Twelve cases are
too short or too empty to answer. Three cases sit on the overlap between two articles (shipping
estimates versus tracking updates; the return label fee versus refund timing; a peeling coating
under warranty versus care). Five ask two questions at once. One is in Spanish. One body is over
the intake size limit.

Each `reply_must` was written by reading the article before writing the request, so the labels
state what the article says, not what a good agent would know.

## Coverage

| Category | Development draft | Development person | Held-out draft | Held-out person | Total |
| --- | --- | --- | --- | --- | --- |
| billing | 11 | 8 | 4 | 4 | 27 |
| account_access | 10 | 7 | 4 | 4 | 25 |
| returns_refunds | 13 | 8 | 6 | 4 | 31 |
| orders_shipping | 11 | 12 | 6 | 6 | 35 |
| product_issue | 12 | 5 | 6 | 4 | 27 |
| other | 0 | 15 | 0 | 8 | 23 |
| **all** | 57 | 55 | 26 | 30 | 168 |

Kinds: realistic 72, edge 84, insufficient information 12. Held out: 56 of 168.

## The held-out split

The held-out cases are never used to choose a prompt, a threshold, or an article keyword. They
exist so that a comparison between two versions of the assistant is made on requests neither
version was tuned on. The split is stratified by category and route: within each stratum, the
second and fourth of every five new cases in authoring order are held out. Every category and
both routes appear in both splits.

A held-out case that is looked at while fixing a failure has been spent. When that happens the
case moves to development in the next dataset version and is replaced.

## What is not in the fixtures

All names, emails, order numbers, and amounts are invented. Emails are under `example.com` and
the loader rejects any other domain. The five requests that contain a card number use the
standard test number `4111 1111 1111 1111`, which is the only card-like digit run the loader
accepts; intake masks it before anything downstream sees it, and those cases expect a person.

## Gaps, and what they mean for conclusions

- No chat transcripts or multi-turn exchanges: every case is a single message. Results say
  nothing about follow-up questions.
- One non-English request. Results say nothing about language coverage.
- No requests that need the order system, beyond the ones labeled for a person because of it.
- The labels are one reviewer's reading of the articles. Cases where a second reader disagreed
  with a label would be a finding; no second reader has been through the set yet.
- 168 cases: a category-level rate is measured on 25 to 35 requests, so a difference of one or
  two requests between two versions is within noise. Comparisons state the counts, not only
  the rates, for that reason.
