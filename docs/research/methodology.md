# Methodology

## Current workflow

1. Collect and verify a source pool for each case.
2. Organize the CTQ case into the six approved information states `t1` through `t6` rather than daily event slices.
3. Build a pool of approximately 45-50 candidate arguments represented as premises, rules, and conclusions with source and temporal provenance.
4. Track each argument once using `introduced_at` and, when meaningful, `active_until`; store time-dependent status separately.
5. Add candidate support or attack relations only when their conflict or support basis is explainable.
6. Score candidates on nine methodological criteria, including timestamp transition value, for a maximum of 45.
7. Apply temporal, provenance, conflict, and non-redundancy constraints to select exactly 27 final CTQ arguments; do not select a mechanical global top 27.
8. Construct temporal graph snapshots from information available at each timestamp.
9. Validate the representation on a small second case.

The detailed CTQ timestamp and selection specification is recorded in `docs/research/ctq-data-selection-plan.md`.

CTQ source provenance uses only `official_document`, `authority_statement`, `news`, and `social`. Source type is not argument status. Only a valid and applicable `official_document` can ground an accepted reference; all statements and reports remain defeasible unless independently supported.

Each candidate records `transition_targets` so its role in `t1->t2`, `t2->t3`, `t3->t4`, `t4->t5`, or `t5->t6` can be audited before relation annotation.

## Audit principles

- Do not invent sources, quotations, dates, decisions, or rules.
- Use `null` for unknown values and document the uncertainty.
- Do not use later information to characterize an earlier information state.
- Trace material factual claims and annotations to source identifiers.
- Review argument annotations in batches of no more than ten new arguments.

## Current exclusions

Automated reasoning, ASP encoding, agent implementation, and large-scale evaluation are not part of the current phase.
