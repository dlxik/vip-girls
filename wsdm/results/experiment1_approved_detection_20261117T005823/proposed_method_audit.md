# Proposed-method execution audit

No LLM inference was run in this preparation phase.

## Input isolation

- Model inputs contain no `final_steering`, binary label, review status, adjudication reason, evidence span, prediction or score column.
- Human-segmented input contains argument boundaries only; approved evidence spans are excluded.
- Gold labels are stored separately and are accepted only by evaluation commands.

## Exact proposed commands for researcher approval

Primary human-segmented extraction:

```powershell
.\.venv\Scripts\python.exe wsdm\approved_detection_experiment.py extract-proposed --inputs wsdm\results\experiment1_approved_detection_20261117T005823\prepared\model_inputs_human_segmented.csv --model ollama:<approved-model> --out wsdm\results\experiment1_approved_detection_20261117T005823\proposed_human_segmented
```

Primary evaluation after extraction:

```powershell
.\.venv\Scripts\python.exe wsdm\approved_detection_experiment.py evaluate-proposed --predictions wsdm\results\experiment1_approved_detection_20261117T005823\proposed_human_segmented\proposed_predictions.csv --gold wsdm\results\experiment1_approved_detection_20261117T005823\prepared\gold_labels.csv --out wsdm\results\experiment1_approved_detection_20261117T005823\proposed_human_segmented_evaluation
```

Secondary raw-comment diagnostic:

```powershell
.\.venv\Scripts\python.exe wsdm\approved_detection_experiment.py extract-proposed --inputs wsdm\results\experiment1_approved_detection_20261117T005823\prepared\model_inputs_raw_comment.csv --model ollama:<approved-model> --out wsdm\results\experiment1_approved_detection_20261117T005823\proposed_raw_comment
```

Replace `<approved-model>` only after inspecting installed models and choosing the model/version to report. Do not compare conditions unless the same model, decoding settings and extraction validation policy are used.

Runtime inspection on 2026-11-17 returned `ollama: command not found`; no installed local model could be enumerated from the current shell. Real local extraction therefore requires making the approved Ollama executable/model available or selecting an approved API model first.
