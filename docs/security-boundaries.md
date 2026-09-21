# Application security boundaries

Threats the assistant faces, the control for each, and the test that proves the control. This
is application security: what the code does with untrusted text, and who may hand it text over
the network. Governance and data retention are outside this document.

| Threat | Control | Where | Proof |
| --- | --- | --- | --- |
| A request tells the assistant to change roles, ignore rules, or confirm an action | Detected by patterns after classification and before any draft is requested; the request goes to a person with `instruction_to_assistant`. Independent of the model's judgment | `security.detect_instruction`, `escalation.py` | `test_injection_request_is_escalated_before_any_draft`: REQ-2017 never reaches the draft step |
| Customer text mixed with instructions inside one prompt | Instructions live in the system prompt; the request is wrapped in `<request>` tags that customer text cannot close; the system prompt says tagged text is data | `model.py`, `security.escape_tag` | `test_customer_text_cannot_close_the_request_tag` |
| Card numbers sent to a third party or stored in results | Masked at intake, before anything else sees the text; the request is flagged | `intake.parse_request`, `security.mask_sensitive` | `test_card_numbers_are_masked_at_intake` |
| Malformed or hostile input records | Ids, emails, channels, and bodies validated; bad lines collected and reported, not fatal | `intake.py` | `test_invalid_records_are_rejected`, `test_bad_lines_are_collected_not_fatal` |
| Very long bodies | Kept whole, flagged `oversized`, sent to a person | `intake.py`, `escalation.py` | `test_oversized_body_is_kept_and_escalated` |
| The model returns a category outside the six, or a confidence outside 0..1 | `validate_verdict` raises; the retry policy asks again; then a person | `security.validate_verdict`, `model.classify` | `test_invalid_verdicts_are_rejected` |
| A draft commits the company to an action | Promise patterns flag the draft; the request goes to a person with the draft attached for reference | `security.check_draft` | `test_promises_are_flagged`, `test_flagged_draft_goes_to_a_person_but_is_kept` |
| A draft states a number or link the article does not contain | Numbers and links in the draft must appear in the article or the request | `security.check_draft` | `test_numbers_not_in_the_article_or_request_are_flagged` |
| An instruction paraphrased around the original patterns ("kindly forget the guidelines", "system notice to assistant", "note to the support agent", "I authorize you to", "include this link in your reply", tag markup) | Eight patterns added from the red-team probes; ordinary sentences with the same words are tested as not flagged | `security.detect_instruction` | `test_every_injection_probe_is_detected_and_never_drafted`, `test_red_team_phrasings_are_detected`, `test_ordinary_phrasings_with_the_same_words_are_not_flagged` |
| A request with a card number is answered by a draft | Masked at intake as before, and now routed to a person as `sensitive_data`, so an agent can tell the customer not to send card numbers | `escalation.py` | `test_a_masked_card_number_routes_to_a_person` |
| A draft defers but names the outcome ("get you the correct item", "help you change your name", "process the return", "we'll get this sorted") | Four promise patterns added; the draft goes to a person with the draft attached | `security.check_draft` | `test_outcome_deferrals_trip_the_commitment_check`, `test_plain_deferrals_and_article_facts_do_not_trip_it` |
| The model triggers an action | There is no action for it to trigger. The application has no send, refund, or account operation; a draft is text a person reads | Architecture | `test_result_is_never_sent`; no network call outside `llm/live.py` |
| Anyone who can reach the service hands it customer text | `POST /requests` and `POST /batches` require the service key from `ASSISTANT_API_KEY` in an `X-API-Key` header; `/health` stays open for operators; the served entry point refuses to start without a key | `api.py`, `config.py` | `test_requests_without_the_key_are_refused`, `test_a_wrong_key_is_refused_and_the_right_one_accepted`, `test_health_stays_open_and_serving_without_a_key_is_refused` |

## Limits
- The instruction patterns catch phrasing, not intent. The red-team probes in
  `evals/datasets/adv-v1` found six phrasings that went around the original list; those are
  closed, and the next paraphrase is not. The probes run offline on every evaluation and a new
  miss shows up as a missed escalation (`docs/failure-taxonomy.md`).
- Number and link checks are deterministic grounding. Invented policy stated in words is
  detected only by the rubric judge, whose agreement with a reviewer is measured in
  `docs/judge-calibration.md`.
- Masking covers card-like digit runs only.
- The service key is one shared secret, so the API knows that a caller is allowed, not who the
  caller is. Per-agent identity and audit are governance, outside this code.
- The service speaks plain HTTP. The key and the customer text are protected in transit only by
  TLS terminated in front of the process, which belongs to deployment; the commands in this
  repository are for localhost.
- Escalating on `sensitive_data` and on outcome deferrals costs over-escalation: one
  draft-expected development case (EV-3007) now reaches a person because its draft promised the
  correct item. Accepted: a promise in a draft is the agent's call, not the model's.
