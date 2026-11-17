# Experiment 1 structured-extraction hardening

This change hardens the existing human-segmented detection pipeline. It does not change the annotation data, the
ranking task, or `S(A→B|C) = Temporal × G × U × D` and its existing ablations.

## Diagnostic evidence

The completed five-item Kaggle run used Qwen2.5-7B-Instruct Q4_K_M with `num_ctx=8192`, temperature 0, and seed 0.
It produced three valid extractions and two schema/span failures. The subset was deliberately selected for diagnosis;
no accuracy estimate should be calculated from it.

- `CMV-020-ARG01`: the model returned `they score *so often*`, but the source contains
  `they score *so often.*`. The omitted period is inside the Markdown emphasis, so the output is not a verbatim
  substring. The validator correctly rejected it.
- `CMV-038-ARG01`: the model returned `uptake_type="indirect_reply"`, which is outside the declared enum. The
  validator correctly rejected it.
- `CMV-020-ARG02`: the response claimed `uptake_level="indirect_specific"` and `uptake_type="indirect"` while also
  setting `span_pair_ok=false` and `specific_reference=false`. The old validator accepted this contradiction. The
  scorer then set `G=0` because the verified span pair was absent. The new validator rejects the extraction and sends
  it to a bounded correction retry instead of treating the contradictory fields as usable features.
- `CMV-017-ARG01`: the response described A's lens as property rights/personal freedom and B's lens as Kantian
  universal ethics/social welfare, but assigned `d_lens=0.5`. This indicates ambiguity in the old frame instructions:
  it did not emphasize strongly enough that a change of evaluative criterion is 0 rather than a compatible widening.
- `CMV-017-ARG02`: the zero score followed the extracted fields (`span_pair_ok=false`, uptake `none`, retention 0) and
  was not a schema failure. The diagnostic alone cannot establish whether that semantic judgment is correct.

These observations explain the mechanics of the outputs; they are not item-specific rules and do not use gold labels
as model features.

## Changes

`llm.py` now:

- requires exact, case-sensitive, contiguous spans, including Markdown punctuation;
- asks for the shortest sufficient evidence clause/sentence and rejects spans longer than 320 characters;
- distinguishes a compatible widening of the same lens from switching to another evaluative criterion;
- validates cross-field consistency among `span_pair_ok`, `specific_reference`, `uptake_level`, and `uptake_type`;
- provides `extract_pair_with_retry`, with a configurable bounded retry count;
- preserves each attempt's raw response, parse status, validation errors, and validity;
- never fuzzy-matches, repairs, normalizes, or invents an evidence span.

`approved_detection_experiment.py` now uses the bounded retry path (default: one correction retry) and writes:

- `extractions.jsonl`: only final valid extractions;
- `extraction_errors.jsonl`: terminal failures with attempt counts;
- `extraction_attempts.jsonl`: every initial/retry raw response and its validation outcome;
- `proposed_predictions.csv`: scores only for valid extractions;
- `run_manifest.json`: retry configuration and attempt counts.

Invalid extractions remain excluded rather than being assigned score zero. Gold labels, adjudication notes, and gold
evidence spans are not accepted by the extraction command.

## Regression coverage

`test_real_pipeline.py` covers non-verbatim spans, overlong spans without normalization, contradictory uptake fields,
frame-shift prompt guidance, preservation of the initial invalid raw response, acceptance of a valid correction retry,
and the existing score variants. Tests are offline and do not call an LLM.

## Kaggle rerun

`notebooks/experiment1_kaggle.ipynb` is patched to rerun the same five rows (the same CSV SHA-256), model,
quantization, context length, temperature, seed, and CUDA device. It uses `--max-extraction-retries 1`, writes to a new
`experiment1_diagnostic5_qwen2_5_7b_retry1` directory, prints every attempt, and exports the attempt log.

The notebook checks out `origin/data/cmv-edge-review-20261116` and refuses to run unless that branch contains
`extract_pair_with_retry`. Because this review intentionally does not commit or push, the notebook becomes remotely
executable only after the researcher approves a commit containing these changes.

## Remaining risks

- Schema validity does not guarantee semantic correctness. Frames, evidence alignment, and D still require qualitative
  inspection and, ultimately, evaluation beyond this selected subset.
- The 320-character cap is a transparent engineering constraint. It improves auditability but may reject a rare case
  whose minimal sufficient evidence is genuinely longer; such cases remain logged rather than truncated.
- A correction retry is not an independent sample. Report initial-valid coverage, final-valid coverage, retry rate, and
  terminal failures separately.
- The primary condition remains `human_segmented`; results cannot be described as raw-comment extraction performance.
- Historical context is unavailable in the approved source, and the adapter uses verified ordinal precedence rather
  than raw timestamps. These limitations are unchanged.
