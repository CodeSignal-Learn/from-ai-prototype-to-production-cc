# Judge calibration

Can the model judge in `evals/judge.py` be trusted to apply R3 (factual support) and R4
(completeness) the way a person applies them? Measured on 43 drafts from the baseline run
`v1-development-baseline`: every other drafted development case, chosen before any verdict was
read. A support reviewer read each draft next to its article and the case notes and recorded a
verdict and evidence per criterion in `evals/datasets/v1/human_judgments.jsonl`. Each judgment
carries a checksum of the draft it was made on; `evals/calibration.py` compares nothing else.

## Two rounds

| | R3 agreement | R3 kappa | R3 judge stricter / lenient | R4 agreement | R4 kappa | R4 judge stricter / lenient |
| --- | --- | --- | --- | --- | --- | --- |
| Round 1, rubric v1 | 0.81 | 0.10 | 4 / 4 | 0.79 | 0.62 | 2 / 7 |
| Round 2, rubric v1.1 | 0.84 | 0.13 | 3 / 4 | 0.79 | 0.62 | 2 / 7 |

Raw reports: `results/evals/calibration/round1.json` and `round2.json`. Kappa is agreement
beyond what two raters would reach by chance; 0.10 and 0.13 are slight, 0.62 substantial.
Agreement alone flatters R3: most drafts pass under both raters, so a judge that passed
everything would score 0.88, more than this judge scored in either round.

### What round 1 found

The R3 disagreements split evenly, and none of the eight was about a deferral:

- **Judge stricter, 4 drafts.** Twice the judge quoted advice as an unsupported claim: "make sure
  you're using the email address the account was created with" (EV-3003) and "look for a
  delivery photo or note on the carrier's tracking page" (EV-3075). Twice it failed a stated rule
  read against the customer's facts, which the reviewer accepts: "it would leave the warehouse
  the next business day, which is Monday" (EV-3072) and the hedged "that could be part of the
  issue" (EV-3021).
- **Judge more lenient, 4 drafts.** The judge passed statements that go one step past the
  article: a summed "roughly three to six business days" to Toronto (EV-3090), "update your email
  address or account details" where the article names only the email (EV-3069), an invoice
  "which shows the charges in detail" (EV-3044), and "a specialist will follow up with where to
  ship it" for a claim the article starts with photos (EV-3139). The reviewer counts each as a
  claim the article does not make. The judge caught one of the reviewer's five R3 fails (EV-3057).

R4 disagreed mostly in the lenient direction. Five drafts the reviewer scored `partial` were
`pass` to the judge: each says plainly that the question is not covered and defers, then pads
with policy the customer did not ask about or answers a neighboring question (EV-3011, EV-3038,
EV-3057, EV-3087, EV-3131). Two `fail` verdicts were `partial` (EV-3003, EV-3079). The judge was
stricter twice, with a `partial` where the reviewer passed: EV-3094 and EV-3119.

One rubric ambiguity surfaced as well. R4 v1 said "with what the article offers"; on a draft
grounded in the wrong article, that reading passes a deferral the customer should never have
received. The reviewer judged against what the knowledge base answers, and the judge mostly
followed the reviewer notes, failing eight of the ten such deferrals in the sample. The text was
wrong, and on two drafts (EV-3003, EV-3079) so were the verdicts it allowed.

### What changed for round 2

Rubric v1.1 spells out the deferral rule in R3 (a deferral is supported however worded; a
deferral that names an outcome, or a reassurance stated as fact, is not; a hedged reading of a
stated rule is) and rewrites R4 to judge against what the knowledge base answers. The judge
prompt carries the same R3 rules, and lists "statements of concern" with greetings and thanks
as not statements of fact. Its R4 `fail` rule covers a deferral when the reviewer notes
show the knowledge base answers, including from the wrong article; its `pass` rule still reads
"with what the article offers", and the rubric text it quotes above the rules is v1.1. The 85 drafts were re-judged; the drafts themselves did not change.

### What round 2 still gets wrong

R3 barely moved. The hedged-reading rule settled the two rules read against the customer's
facts (EV-3021 and EV-3072 now agree), but the judge still quotes advice as unsupported
(EV-3003, EV-3075), and it newly fails a plain deferral, EV-3106's "a specialist will need to
help locate the purchase and follow up with you on your options", despite the rule that names
those phrasings. It still passes all four stretched statements, so it catches one of the
reviewer's five fails, and the one it catches is EV-3057, the merge offered to two people. Kappa
rose from 0.10 to 0.13: two strict calls fewer, one more, and the misses did not move.

R4, nine disagreements again, seven in the lenient direction, and the same agreement and kappa
by a different mix. The rewritten R4 settled EV-3003 (now `fail`, as the reviewer has it) and
two of the padded deferrals (EV-3038, EV-3057), and passed two others it had scored like the
reviewer (EV-3060, EV-3146), so it still passes five. It still scores EV-3079's wrong-article
deferral `partial`, and it scores EV-3106 `partial` where the reviewer fails the draft for
explaining the ordinary return flow to a gift with no order number. The two strict calls are
unchanged: EV-3119, and EV-3094, where the judge wanted the draft to warn against sending card
numbers, which the notes ask of a person, not of the draft.

The runner also counts quotes that do not appear in the draft (`judge_quotes_not_in_draft` in
every summary; none on this run), and a verdict with such a quote is treated as a flag to read,
not as evidence. The red-team probe runs have none either.

## How the judge is used, given this

- **R3 fail from the judge is a flag, not a verdict, and its pass is not a clearance.** Every
  judged R3 fail is read by a person before it counts against a release decision. The judge's job
  is to make sure no fail is missed (recall); on this sample it misses four in five, all of them a
  stated rule stretched one step.
  Nothing deterministic catches that shape: the outcome-deferral patterns added after the
  red-team review (`docs/failure-taxonomy.md`) look for promises, and a stretched rule states none.
  A person reading every draft is the control.
- **Acceptable rates from a judged run lean optimistic.** The judge is more lenient than the
  reviewer more often than it is stricter: on this sample it passed four R3 fails and scored two
  R4 fails `partial`, which makes three results acceptable that the reviewer does not accept
  (EV-3079, EV-3090, EV-3139), and none the other way. Two versions judged the same way share these
  tendencies only while they produce the same kinds of drafts; a new drafting prompt produces
  new sentence shapes, so its judged R3 fails are read by a person before they count.
- **The judge is never used where the deterministic checks apply.** R1, R2, and R5 are counted
  by code, and a disagreement there is a bug or a label error, not a matter of judgment.
- **Recalibrate when anything on either side changes**: the judge prompt, the model behind it,
  the rubric, or the kind of drafts (a new drafting prompt produces new sentence shapes). The
  human judgments are tied to draft checksums, so a changed draft is skipped rather than
  compared, and the sample has to be re-read.

## Limits
43 drafts from one reviewer, all development cases, five of them R3 fails. With so few fails
the R3 kappa moves by up to half a point when three verdicts change, so round 2 is "slight
agreement, judge more lenient", not a number to report to two decimals. A second reviewer has
not labeled the set; disagreement between two people would set the ceiling any judge can reach.
Round 2 is measured on the same 43 drafts the rubric was sharpened on, so even its small gain
may not hold on others; a separately reviewed sample would show whether it does.
