# Exploratory CMV STEP 3B baseline diagnostics — 2026-11-16

**NOT a WSDM paper result, NOT A1/A2 ranking, NOT final human-adjudicated gold.**

Input: Person B's **actual 50 direct-reply CMV pairs**, 50 different threads (STEP 3B seed 42). The metric calculation was executed locally using the 50-source-pair snapshot and the current proposed review labels on the primary argument alignment, with uncertainty/N/A excluded.

Label distribution for primary alignment: YES=24, NO=9, UNCLEAR=8, NOT_APPLICABLE=9. Binary ranking/diagnostic metrics computed on 33 YES/NO comment pairs only.

| Baseline | AUROC | Average Precision |
|---|---:|---:|
| TF-IDF word 1–2gram cosine | 0.546 | 0.721 |
| TF-IDF character 3–5gram cosine | 0.565 | 0.740 |
| Token Jaccard | 0.514 | 0.717 |
| Reply-structure only | 0.500 | 0.727 |

AP must be interpreted against positive prevalence 24/33 = 0.727. Every STEP3B pair is a direct reply; the structure-only score is **constant** by design. Similarity features were fitted on this very pilot without labels, so these numbers cannot support held-out generalization.

Local verified calculation produced `edge_predictions.csv` and `edge_results.json`. The repo contains `wsdm/evaluate_edge_pilot.py` for replay with STEP3B and `wsdm/pilot/cmv_edge_proposed_review.csv` (the proposed review snapshot). If the STEP3B CSV is located elsewhere, adjust --pairs.

Run:
```sh
pip install pandas numpy scikit-learn
python wsdm/evaluate_edge_pilot.py --pairs dataset/pilot/cmv_pilot_50.csv --labels wsdm/pilot/cmv_edge_proposed_review.csv --out wsdm/results_edge_pilot
```

For real unlabeled A1/A2 ranking **inference**, run `python wsdm/score_unlabeled.py --items wsdm/pilot/items_unlabeled.jsonl --out wsdm/results_unlabeled.csv` from repo root, noting Python imports from the script's own directory. This generates predictions, **not** accuracy; gold ranking labels remain missing.

Scientific limitations: 50 source pairs are comment-level; 60 review rows include multiple argument alignments for some pairs. The real dataset joins by A_id and B_id; labels are provisional. The main proposed SteeringProxy G/U/D requires fresh model extraction (NOT the original annotation features), and the ranking evaluation `evaluate.py` expects reviewed labels `A1>A2/A1<A2/tie/insufficient` for its own candidate items.

Next: (i) review and freeze the adjudication sheet, (ii) build a ranking annotation batch keyed by exactly the repository's item_id, (iii) obtain independently verified ranking labels, (iv) extract G/U/D from unannotated text and run proper split-by-thread evaluation.
