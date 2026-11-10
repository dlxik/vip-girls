# Project Status

## Shared repository baseline — 2026-11-10

- The latest AGORA V4 state was migrated from `dlxik/AGORA` commit `2e1dce0cfe7fb7113c8c720e568f1983efb44a45` to `dlxik/vip-girls`.
- V1, V2, V3 and V4 remain independently runnable.
- The full regression suite passes: 65/65 tests.
- The pre-existing hierarchical architecture HTML is preserved under `docs/architecture/`.
- Documentation is grouped by architecture, research and project records for two-person collaboration.

The detailed CTQ status below is an inherited research snapshot and should be refreshed separately when canonical data work resumes.

## Completed

- Phase 0 repository inspection.
- Initial functional repository skeleton.
- Lightweight project and research documentation placeholders.
- Git repository initialization with `main` as the default branch.
- Private GitHub repository baseline at `dlxik/AGORA`.
- CTQ batch 1 coverage review of all 17 supervisor-provided seed URLs.
- Five additional CTQ sources recorded in the first source-expansion batch; all records have since been migrated to the approved taxonomy.
- First five CTQ candidate arguments extracted and provisionally scored.
- CTQ planning and candidate schema updated for six timestamps, nine ranking criteria, and an exact final target of 27 arguments.
- CTQ batch 2 added eight verified sources focused on official evidence and the `t2`, `t5`, and `t6` gaps.
- Ten additional CTQ candidate arguments were extracted with temporal roles, potential relations, and provisional R1-R9 scores.
- Source taxonomy migrated to `official_document`, `authority_statement`, `news`, and `social`, with source type explicitly separated from status.
- CTQ batch 3 added ten verified sources and ten candidates focused on `t1`, `t2`, `t3`, and `t4`.
- `transition_targets` added and populated for all candidate arguments.
- CTQ batch 4 added seven verified sources and ten candidates focused on `t1`, `t2`, `t4`, and `t6`, including the official consolidated 2026 examination regulation.
- CTQ batch 5, the final pool-expansion batch, added nine verified sources and ten candidates focused on `t3`, `t5`, admission rules, counterinterpretations, and transition value.
- The CTQ candidate pool has reached the approved pre-selection floor of 45 without selecting the final 27.
- Source-based language normalization audited all 56 source records and all 45 candidate records.
- Thirty-seven candidates were re-extracted directly from accessible Vietnamese sources; eight unresolved candidates were subsequently rejected because essential sources could not be reopened.
- Accessible Vietnamese source titles and source-derived notes were normalized in place; nine inaccessible source records remain explicitly flagged for review.
- The eight unresolved candidates were rejected in the final pass and their English P/R/C fields were cleared rather than back-translated.
- Exactly 27 final arguments were selected and assigned stable IDs CTQ-A001 through CTQ-A027 in `data/annotations/ctq_arguments.csv`.

## In progress

- Human review of the completed CTQ final-27 dataset on `data/ctq-source-pool`.

## Pending

- CTQ information-availability timeline.
- Temporal argument schema finalization.
- Manual argument and relation annotation.
- Temporal graph snapshots.
- Household business taxation validation subset.

## Need human review

- Data serialization format and identifier conventions.
- Final research question wording.
- CTQ batch 1 source classifications, candidates, provisional scores, and proposed relations.
- Treatment of institutional news reporting as secondary evidence for official decisions.
- Initial `introduced_at` mapping and recalculated R1-R9 scores for the first five candidates.
- CTQ batch 2 source classifications, reconstructed bridging rules, candidate relations, and provisional scores.
- Whether the reviewed Circular 13/2026 text is sufficient to close the consolidated-regulation uncertainty.
- CTQ batch 3 taxonomy assignments, A_K-to-A_D reclassifications, transition targets, reconstructed rules, and provisional scores.
- Authenticity handling for the secondary full-text copy of Official Letter 5157/BGDĐT-QLCL.
- CTQ batch 4 proportionality arguments, temporal conflicts between early assurances and later evidence, and prosecution-status qualifications.
- Final human approval of the diversity-aware CTQ-A001 through CTQ-A027 selection.
- Relation-dataset construction and graph snapshots using the reviewed final 27.

## Files changed

- CTQ sources, candidate annotations, final selected arguments, selection methodology, decisions, uncertainties, source review, and status documentation.

## Current counts

| Artifact | Count |
| --- | ---: |
| Sources | 56 |
| Timeline timestamps | 0 |
| Arguments | 45 |
| Final selected arguments | 27 |
| Relations | 0 |
| Graph snapshots | 0 |

Potential relations are recorded inside the candidate table only; no relation dataset or graph has been created.
