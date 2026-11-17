# Experiment 1 post-audit retry revision

## Status and scope

This is a retry-only engineering revision motivated by the Version 1 reliability audit. It is not an independently
validated method improvement. The initial extraction prompt, evidence rubric, strict verbatim rule, 320-character
limit, model settings, annotations, and `S(A→B|C) = Temporal × G × U × D` remain unchanged.

Version 1 outputs under `wsdm/results/kaggle_full41_version1/` are immutable comparison artifacts. A patched run must
use a new output directory and must not resume from Version 1 checkpoints because the implementation/configuration
hash is different.

## Exact retry-only change

The first attempt remains exactly:

```python
"\n\n".join([DEFINITION, EXTRACT_TASK, render_pair(item, key)])
```

Only a rejected extraction receives the revised correction prompt. It now contains:

- the complete previous raw response;
- validation errors as a JSON array;
- rejected fields and dependent fields that must be rechecked;
- the allowed uptake-field combinations;
- an instruction to preserve valid fields and repair only inconsistent fields, followed by full-output revalidation;
- clearly separated A and B sources, both as authoritative JSON strings and whitespace-visible diagnostics;
- explicit wrong-source, fuzzy matching, paraphrase, normalization, punctuation, case, Markdown, and whitespace
  prohibitions;
- the unchanged 320-character maximum.

Every attempt still records its raw response, parse status, validity, and validation errors. A retry additionally
records its field/dependency repair context. Invalid output is never normalized, coerced to zero, or included in
predictions. At most one correction retry is accepted by both the Python API and CLI.

## Ablation audit

- `proposed_d_only` is named historically but is **gated retention**, `Temporal × G × D`; it is not D alone.
- `proposed_ungated` removes the explicit `G` multiplier, but `U_raw` is extracted under the same evidence-consistency
  contract. With all-direct-reply inputs, positive uptake and the gate can collapse to the same indicator. It is a
  descriptive variant, not guaranteed to be an independent gate ablation.
- In Version 1, Proposed, gated-retention (`proposed_d_only`), and `proposed_ungated` were numerically identical on all
  19 valid items, not merely equal in AUROC/AP. This is a degeneracy of those observed component values.
- `proposed_u_only` is a valid removal of frame retention for the frozen score.
- `proposed_dmean` changes retention aggregation from minimum to mean; it is a sensitivity variant, not a component
  removal.

No scoring implementation is changed. Generated evaluation reports now state the two misleading-name limitations.

## Kaggle full-41 rerun after approval and commit

Use the existing Kaggle dataset containing exactly:

```text
model_inputs_human_segmented.csv
SHA-256: 52839A7E92C249FAEECAE491CB22167235A2F767E0E31486036468875AB466B1
```

Do not attach `gold_labels.csv` until extraction has completed and the prediction artifacts have been saved. Pin the
approved reliability-patch commit rather than the branch tip:

```bash
git clone --branch data/cmv-edge-review-20261116 --single-branch \
  https://github.com/dieulinhvuhoang/vip-girls.git /kaggle/working/vip-girls
cd /kaggle/working/vip-girls
git checkout --detach 20c3b40213e096c80875a73e52fe749e81e42e3b
git rev-parse HEAD
```

After the notebook's existing GPU/Ollama/model setup cells, verify and stage the input:

```bash
sha256sum /kaggle/input/wsdm2027-exp1/model_inputs_human_segmented.csv
cp /kaggle/input/wsdm2027-exp1/model_inputs_human_segmented.csv \
  /kaggle/working/model_inputs_human_segmented.csv
```

Run into a new directory. `--resume` safely skips only atomic checkpoints whose full configuration hash matches this
implementation, model, input, and retry configuration:

```bash
python /kaggle/working/vip-girls/wsdm/approved_detection_experiment.py extract-proposed \
  --inputs /kaggle/working/model_inputs_human_segmented.csv \
  --model ollama:qwen2.5:7b \
  --out /kaggle/working/experiment1_full41_qwen2_5_7b_retry_patch_v2 \
  --max-extraction-retries 1 \
  --expected-items 41 \
  --model-artifact-digest d5fba88ae850a27f8b368c634891ac9c640e6cc9a9d56ce9ccf4ec22cdb546f1 \
  --resume
```

Expected extraction outputs include `item_checkpoints/`, `extraction_attempts.jsonl`, `extractions.jsonl`,
`extraction_errors.jsonl`, `item_level_predictions_evidence.csv`, `proposed_predictions.csv`, and
`run_manifest.json`. Save a Kaggle Version with outputs before attaching gold and running evaluation.

This rerun must be reported as a post-audit engineering revision. Version 1 and patched coverage/results must be shown
side by side; they must not be pooled.
