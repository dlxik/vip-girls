# Experiment 1 preparation report

## Scope

This run prepares the approved CMV pilot for binary evidence-grounded argumentative steering detection. It does not evaluate the separate A1/A2/B ranking task and does not contain LLM inference.

## Approved data

- Source records: 60, all `APPROVED`.
- Approved argument units: 44.
- Binary YES/NO units: 41, from 34 threads.
- YES: 32; NO: 9; positive prevalence: 0.7805.
- UNCLEAR excluded: 3.
- NOT_APPLICABLE / unapproved units excluded: 16.

Stable `argument_pair_id` values from the approved annotation are preserved. Model inputs and gold labels are stored in different files. Gold evidence spans are not included in either model-input condition.

## Is human segmentation required?

Yes, for the current 41-unit task. Six raw comment pairs contain multiple approved argument alignments. `CMV-020` is decisive: the same raw A/B comments produce one NO unit and one YES unit. Therefore a raw-comment classifier cannot distinguish all 41 labels from its permitted input.

The run reports two conditions:

1. `raw_comment`: diagnostic only. It preserves full A/B comments but contains repeated identical inputs and one mixed-label input group.
2. `human_segmented`: uses `A_argument_span` and `B_argument_span` as explicit human-provided argument boundaries. It does not use `A_evidence_span` or `B_evidence_span`.

The segmented condition is not an end-to-end result. It measures detection conditional on human segmentation.

## Non-LLM baseline results

| Input condition | Method | AUROC | Average Precision |
|---|---:|---:|---:|
| raw_comment | tfidf_char | 0.675 | 0.846 |
| raw_comment | tfidf_word | 0.658 | 0.833 |
| raw_comment | token_jaccard | 0.601 | 0.812 |
| raw_comment | reply_only | 0.500 | 0.780 |
| raw_comment | hash_random_sanity | 0.497 | 0.761 |
| human_segmented | tfidf_char | 0.667 | 0.890 |
| human_segmented | tfidf_word | 0.628 | 0.885 |
| human_segmented | token_jaccard | 0.505 | 0.831 |
| human_segmented | reply_only | 0.500 | 0.780 |
| human_segmented | hash_random_sanity | 0.497 | 0.761 |

Average Precision must be interpreted against the 0.780 positive prevalence. All vocabulary fitting is unsupervised on the same pilot. There is no held-out split, and the 41 units are correlated within 34 threads.

## Historical context limitation

The approved CSV contains raw A/B comments, source IDs, argument spans and `valid_order`, but no raw timestamps, parent records beyond the A/B edge, or historical thread context. Prepared inputs therefore use an empty permitted-context list. The adapter represents verified temporal precedence with ordinal A=0, B=1; these are not claimed as source timestamps.

## Proposed method adapter

`wsdm/approved_detection_experiment.py extract-proposed`:

- accepts only a model-input CSV and a model name; it has no gold-label argument;
- creates one edge item per stable `argument_pair_id`;
- passes only the selected A/B condition, empty permitted context, verified direct-reply structure and ordinal temporal order to `llm.extract_pair`;
- validates extracted spans as verbatim substrings;
- uses the existing `ProposedScorer` unchanged for `S = Temporal × G × U × D` and registered ablations;
- excludes and logs invalid/unparseable extraction records instead of silently assigning score zero;
- writes predictions without labels; a separate `evaluate-proposed` command joins predictions with `gold_labels.csv` afterward.

The primary scientifically interpretable pilot condition is `human_segmented`, with the explicit limitation that human segmentation is supplied. `raw_comment` should remain a secondary diagnostic because its unit labels are not fully determined by raw input.

## Scientific status

These numbers are approved-pilot descriptive diagnostics. They are not held-out generalization results and do not establish WSDM paper performance.
