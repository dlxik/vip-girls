# Local real-data WSDM pipeline (Windows PowerShell)

All commands below run from the repository root on branch
`data/cmv-edge-review-20261116`. Generated corpus/model artifacts and experiment
runs are ignored by Git.

## Setup

```powershell
Set-Location -LiteralPath 'D:\main\Full\documents\uni\Nam 2\DSKT\law\vip-girls'
$env:PYTHONUTF8 = '1'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-wsdm.txt
```

The canonical Person B artifacts located on this machine are:

```text
D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\processed\cmv_utterances.parquet
D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\processed\cmv_reply_edges.parquet
D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\processed\cmv_direct_pairs.parquet
D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\pilot\cmv_pilot_50.csv
```

They are read in place and are not copied into this repository.

## Verify

```powershell
.\.venv\Scripts\python.exe -m unittest wsdm/test_real_pipeline.py -v
.\.venv\Scripts\python.exe wsdm/smoke_test.py
```

## Build ranking candidates from canonical Parquet

The adapter never invents timestamps. Rows with missing timestamps remain in the
parent map for hop calculation but cannot become candidates, B, or visible context.

```powershell
.\.venv\Scripts\python.exe wsdm/build_items_from_parquet.py `
  --utterances 'D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\processed\cmv_utterances.parquet' `
  --edges 'D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\processed\cmv_reply_edges.parquet' `
  --out 'wsdm\results\parquet_adapter_seed13\items.jsonl' `
  --n 50 --seed 13
```

Outputs include `items.jsonl`, `build_summary.json`, and thread-grouped
`split/{train,dev,test}.jsonl`.

## Real unlabeled ranking baselines

```powershell
.\.venv\Scripts\python.exe wsdm/run_experiment.py `
  --mode baseline --source existing `
  --items wsdm/pilot/items_unlabeled.jsonl
```

Each versioned run contains self-contained items, JSONL/CSV predictions, summary
statistics, and a manifest. These runs are **UNLABELED**: prediction distributions
are inspectable, but accuracy, F1, and method-superiority claims are invalid.

## Proposed score extraction

Mock mode is only a wiring test and is never chosen silently:

```powershell
.\.venv\Scripts\python.exe wsdm/run_experiment.py `
  --mode proposed --source existing --model mock --limit 5
```

For a first real local run, install Ollama, start its service, and pull a quantized
7B model that fits the RTX 3060 experiment budget:

```powershell
ollama pull qwen2.5:7b
ollama serve
.\.venv\Scripts\python.exe wsdm/run_experiment.py `
  --mode proposed --source existing `
  --model ollama:qwen2.5:7b --limit 5
```

The client checks both the Ollama service and exact installed model before inference.
Invalid JSON/schema values or non-verbatim evidence spans are excluded and written to
`extraction_errors.jsonl`. Valid runs score gated U×D plus U-only, D-only, ungated
U×D, and D-mean ablations. Gold labels are not rendered into extraction prompts.

## Separate edge-pilot diagnostics

Approved human-final labels are used by default. With the current review file this
correctly produces no metrics because no approved labels exist:

```powershell
.\.venv\Scripts\python.exe wsdm/evaluate_edge_pilot.py `
  --pairs 'D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\pilot\cmv_pilot_50.csv' `
  --labels wsdm/pilot/cmv_edge_proposed_review.csv `
  --out wsdm/results/edge_pilot_approved
```

An explicitly provisional diagnostic is available, but it remains **NOT GOLD**:

```powershell
.\.venv\Scripts\python.exe wsdm/evaluate_edge_pilot.py `
  --pairs 'D:\main\Full\documents\uni\Nam 2\DSKT\law\WSDM2027_shortpp\dataset\pilot\cmv_pilot_50.csv' `
  --labels wsdm/pilot/cmv_edge_proposed_review.csv `
  --out wsdm/results/edge_pilot_provisional --use-provisional
```

The evaluator preserves all argument alignments, joins by `A_id`/`B_id`, excludes
`UNCLEAR`/`NOT_APPLICABLE` from binary metrics, and reports argument- and
comment-level results separately. Reply-only is constant because every pair is a
direct reply.

## Open the local viewer

```powershell
.\.venv\Scripts\streamlit.exe run wsdm/visualization/app.py
```

Open `http://localhost:8501`. Select a run, inspect A1/A2/B text, structure,
timestamps, scores, evidence components/spans, disagreements and zero-score cases,
or export filtered predictions to CSV.

## Scientific boundary

- `wsdm/pilot/items_unlabeled.jsonl` and canonical-adapter ranking items have no
  comparative A1/A2 gold label.
- `cmv_edge_proposed_review.csv` is a different, per-edge argument-alignment task.
- `PROPOSED steering` remains an AI-assisted review proposal until human approval.
- Reply edges encode conversation structure, never support/attack semantics.
- Toy and mock outputs prove execution only; they are not research results.

