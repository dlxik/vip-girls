# CMV STEP 3B → WSDM handoff (Person B)

Snapshot: 2026-11-16. **Provisional, approval required before publication-quality evaluation.**

## Artifacts

- `cmv_edge_proposed_review.csv`: 60 argument alignment records, obtained by reconciling the 50 **real, direct-reply** comment pairs from Person B's STEP 3B sample (seed 42; 50 separate threads).
- Review Google Sheet: https://docs.google.com/spreadsheets/d/1hQaAy_Ho1EqPGy3mrHYDDXhBTr8J36AfU3kyGtCSbK8/edit
- Source: `dataset/pilot/cmv_pilot_50.csv` and `dataset/processed/{cmv_utterances,cmv_reply_edges,cmv_direct_pairs}.parquet` in Person B's data project; verify originals before merging.

There are **60 records** because the first annotation contains 10 additional argument alignments for some comments. Every `argument_pair_id` is unique; `original_pair_id` is **not unique**. No rows should be dropped by treating original_pair_id as a unique key.

### Labels and approval contract

- `PROPOSED steering` is a **review suggestion**, not final ground truth.
- `status` is currently REVIEW for all 60 rows.
- `human final label` and `human rationale` are empty until adjudication. A human reviewer should approve argument boundaries and verify supporting evidence against original source comments.
- `argument validity (Hà)`, `uptake (Hà)`, `aspect retention (Hà)`, `lens retention (Hà)` are the *original annotation's component decisions*; they need not be consistent with the newly proposed steering suggestion. Never pass them to the evaluation method as input features from gold annotation.
- The raw AI-assisted annotations were reviewed by team members according to the project workflow. **Do not report AI–AI agreement as human–human inter-annotator reliability** without documenting who independently judged each example.

### Mapping to Person A's current code

`wsdm/build_items.py`, `wsdm/merge_labels.py`, `wsdm/evaluate.py` currently implement **pairwise ranking** instances `(A1,A2,B,C)` with labels `1/2/t/i`.

The STEP 3B dataset here instead contains **per-edge** `(A,B)` with YES/NO/UNCLEAR/NOT_APPLICABLE and parent A directly replied to by B. Thus it can support a *secondary, exploratory relation-detection evaluation*, but **cannot be read directly by `merge_labels.py`** and cannot establish the ranking method's accuracy.

The repo's own `wsdm/pilot/items_unlabeled.jsonl` is a separate CMV ranking candidate sample (seed 13) and **its item IDs do not align by construction with STEP 3B's 50 CMV pairs**.

### Required actions to run meaningful ranking experiments

1. Export/approve adjudicated relation labels from Google Sheet. Preserve the argument units and source IDs.
2. Use Person B's canonical Parquet tables to build `A1,A2,B` candidate sets with reproducible timestamp/reply constraints; do not silently reuse labels from unrelated `A,B` pairs.
3. Label the **same ranking items** independently using A1>A2 / A1<A2 / tie / insufficient, with evidence spans and permitted pre-B context.
4. Only then run `merge_labels.py` and `evaluate.py` on the exact annotated ranking item IDs.
5. For a secondary detection check, split this edge dataset by `thread_id`, and do not feed component gold labels (uptake, frame retention, steering) into `ProposedScorer`. Extract those components solely from texts/metadata via `llm.py` or other models.
6. All `wsdm/toy/results` are toy/smoke-test results and must **not** be described as results on independently adjudicated real CMV gold labels.

### Recommended immediate division

- **B:** adjudicate reviewed 60 edge records, export approved CSV; prepare a small ranking-item annotation batch from the *actual* `wsdm/pilot/items_unlabeled.jsonl` for human judgment.
- **A:** run `smoke_test.py`, produce real LLM extractions for a verified ranking batch, execute baseline comparison and ablations; do not train/tune on test.

## Provenance

STEP 1–3B profiling, canonical graph, direct-reply pairs, sampling validation and reply-time audit are **Person B's data pipeline**. This handoff does not replace those artifacts or alter the main branch.
