# Judge calibration

Can the model judge in `evals/judge.py` be trusted to apply R3 (factual support) and R4
(completeness) the way a person applies them? Measured on 44 drafts from the baseline run
`v1-development-baseline`: every other drafted development case, chosen before any verdict was
read. A support reviewer read each draft next to its article and the case notes and recorded a
verdict and evidence per criterion in `evals/datasets/v1/human_judgments.jsonl`. Each judgment
carries a checksum of the draft it was made on; `evals/calibration.py` compares nothing else.

## Two rounds

| | R3 agreement | R3 kappa | R3 judge stricter / lenient | R4 agreement | R4 kappa | R4 judge stricter / lenient |
| --- | --- | --- | --- | --- | --- | --- |
| Round 1, rubric v1 | 0.82 | 0.32 | 5 / 3 | 0.89 | 0.79 | 5 / 0 |
| Round 2, rubric v1.1 | 0.84 | 0.50 | 6 / 1 | 0.84 | 0.70 | 6 / 1 |

Raw reports: `results/evals/calibration/round1.json` and `round2.json`. Kappa is agreement
beyond what two raters would reach by chance; 0.32 is fair, 0.50 moderate, 0.70 substantial.
Agreement alone flatters R3: most drafts pass under both raters, so a judge that passed
everything would still score 0.86.

### What round 1 found

The R3 disagreements were not noise. They fell into two groups, both about the same sentence
shape, the deferral:

- **Judge stricter, 5 drafts.** The judge quoted deferrals as unsupported capability claims:
  "help find the best solution" (EV-3135), "find the best way forward" (EV-3138), "look into this
  matter and determine what happened" (EV-3038), even a plain "a specialist will follow up with
  you shortly" (EV-3094). The reviewer counts these as saying only that a person will look.
- **Judge more lenient, 3 drafts.** The judge passed deferrals that name an outcome: "get you the
  correct women's medium fleece" (EV-3007), "help you change your name in the system" (EV-3055),
  "process the return or exchange. We'll get this sorted" (EV-3106). The reviewer counts each as a
  claim the article does not make. Half the reviewer's R3 fails were missed.

R4 disagreed only in the judge's direction: four drafts the reviewer passed were `partial` to
the judge, where a correct answer came with material the customer had not asked about, and one
`partial` was a `fail`.

One rubric ambiguity surfaced as well. R4 v1 said "with what the article offers"; on a draft
grounded in the wrong article, that reading passes a deferral the customer should never have
received. The reviewer judged against what the knowledge base answers, and the judge followed
the reviewer notes, so both were already reading it that way. The text was wrong, not the
verdicts.

### What changed for round 2

Rubric v1.1 spells out the deferral rule in R3 (a deferral is supported however worded; a
deferral that names an outcome, or a reassurance stated as fact, is not; a hedged reading of a
stated rule is) and rewrites R4 to judge against what the knowledge base answers. The judge
prompt carries the same rules, and lists "statements of concern" with greetings and thanks as
not statements of fact. The 88 drafts were re-judged; the drafts themselves did not change.

### What round 2 still gets wrong

R3 moved in the right direction on the failures that matter: five of the reviewer's six fails
are now caught, among them the two outcome deferrals EV-3007 and EV-3106 that round 1 passed,
and the one still missed is EV-3055, "help you change your name in the system". The judge is now stricter more often, six
drafts: it still fails plain deferrals (EV-3094, EV-3119: "a specialist will follow up with you
shortly", "... separately to help resolve that") and one worded deferral (EV-3135), despite the
rule that names those phrasings, and it fails three hedged inferences the reviewer accepts
(EV-3021 "likely isn't ruined", EV-3028 "may indicate your order hasn't shipped yet", EV-3059
"points should update once the merge is fully complete"). Kappa rose from 0.32 to 0.50, mostly
because the misses fell.

R4, seven disagreements, six in the strict direction. Three `partial` verdicts on drafts the
reviewer passed (EV-3059, EV-3090, EV-3119); two `fail` on drafts the reviewer passed (EV-3023,
where the judge scored the cancellation extension under R4 as well as R3; EV-3094, where the
judge wanted the draft to warn against sending card numbers, which the notes ask of a person,
not of the draft); one `fail` the reviewer scored `partial` (EV-3046, a two-topic request
answered on the wrong topic); one `pass` the reviewer scored `partial` (EV-3138). The rewritten
R4 made the judge read the reviewer notes more literally, which is why kappa slipped from 0.79 to
0.70 while R3 improved.

A separate failure mode appeared on the adversarial set: on one draft the judge quoted the
reviewer notes as an unsupported statement instead of a sentence of the draft. The runner now
counts quotes that do not appear in the draft (`judge_quotes_not_in_draft` in every summary),
and a verdict with such a quote is treated as a flag to read, not as evidence.

## How the judge is used, given this

- **R3 fail from the judge is a flag, not a verdict.** Every judged R3 fail is read by a person
  before it counts against a release decision. The judge's job is to make sure no fail is missed
  (recall); on this sample it misses one in six, and the one it missed is the outcome-deferral
  shape, which the R5 promise patterns in `security.py` are the deterministic backstop for.
- **Acceptable rates from a judged run are a lower bound.** The judge is stricter than the
  reviewer on both criteria; on this sample six R3 fails and five R4 verdicts would be passes to
  a person. A comparison between two versions of the assistant judged the same way is fair; an
  absolute rate is pessimistic by roughly that margin.
- **The judge is never used where the deterministic checks apply.** R1, R2, and R5 are counted
  by code, and a disagreement there is a bug or a label error, not a matter of judgment.
- **Recalibrate when anything on either side changes**: the judge prompt, the model behind it,
  the rubric, or the kind of drafts (a new drafting prompt produces new sentence shapes). The
  human judgments are tied to draft checksums, so a changed draft is skipped rather than
  compared, and the sample has to be re-read.

## Limits
44 drafts from one reviewer, all development cases. The kappa on 44 items moves by about 0.1
when three verdicts change, so round 2 is "moderate agreement, judge stricter", not a number to
report to two decimals. A second reviewer has not labeled the set; disagreement between two
people would set the ceiling any judge can reach.
