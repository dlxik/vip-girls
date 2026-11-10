# CTQ Data Selection Plan

## Objective

Build a diverse pool of approximately 45-50 candidate arguments before selecting exactly 27 arguments for the CTQ temporal argumentation case study.

The final set is selected for methodological value. A high score does not mean that an argument is true, legally correct, or authoritative.

## Six information states

The timestamps represent changes in the information available to the system, not every event date.

| Timestamp | Approximate date | Information state | Research role |
| --- | --- | --- | --- |
| `t1` | 2026-07-01 to 2026-07-02 | Unusual results and high Mathematics scores become visible; a Ministry working group investigates; no misconduct conclusion exists. | Initial suspicion, competing explanations, and undecided claims. |
| `t2` | 2026-07-05 to 2026-07-07 | Printing, transport, and grading checks do not explain the anomaly; attention shifts to invigilation; misconduct evidence and a criminal case appear. | Transition from statistical suspicion to evidence-based misconduct suspicion. |
| `t3` | 2026-07-09 | The provincial education authority proposes a Mathematics retest for 328 candidates. | Competing remedies, fairness, proportionality, and one-subject versus broader treatment. |
| `t4` | 2026-08-04 to 2026-08-05 | The Ministry cancels the original results and decides that all previously taken subjects must be retaken. | Authoritative intervention that overrides or challenges earlier proposals without erasing public disagreement. |
| `t5` | 2026-08-19 | Retest results are announced; no perfect scores remain and the Mathematics average is substantially lower. | New empirical evidence and reinterpretation, without treating score decline as proof of individual fraud. |
| `t6` | 2026-10-01 | The investigation reports 41 defendants and misconduct across all examination rooms and subjects. | Later official evidence that may support the earlier broad remedy and attack limited-scope explanations. |

## Argument-time model

Each candidate is represented once and includes:

- `introduced_at`: the first CTQ information state in which the argument is available or relevant.
- `active_until`: the last information state in which the argument remains active, when a meaningful endpoint is known.

Argument status is stored separately and remains time-dependent. Later work may record different statuses for the same argument at `t1` through `t6`; arguments must not be duplicated merely because their status changes.

## Candidate schema

The candidate table contains:

```text
candidate_id
case_id
arg_type
premise
premise_sources
premise_time
rule
rule_sources
valid_from
valid_to
conclusion
conclusion_sources
conclusion_time
introduced_at
active_until
source_type
argument_theme
temporal_role
potential_relation_type
potential_relation_targets
transition_targets
extraction_confidence
R1
R2
R3
R4
R5
R6
R7
R8
R9
selection_score
selection_status
notes
```

## Source taxonomy

`source_type` records provenance form, not argument status. It uses only:

- `official_document`: laws, regulations, circulars, decisions, official notices, administrative documents, and examination regulations.
- `authority_statement`: an attributable statement by an official or a person speaking in an institutional or authoritative role.
- `news`: professional journalistic reporting, including reported expert commentary.
- `social`: user-generated posts, comments, threads, or discussions on social platforms or forums.

The former `public`, `official`, and `commentary` values are not used. Public user-generated claims are `social`; professional commentary is `news`; an official-portal news account is an `authority_statement` unless the record is the underlying document itself.

Source type does not determine whether a claim is accepted. Only a valid and applicable `official_document` may ground an accepted reference, and even an official document must be checked for authenticity, validity interval, jurisdiction, and applicability. `authority_statement`, `news`, and `social` claims remain defeasible.

`transition_targets` records one or more transitions supported by a candidate, using values such as `t1->t2` separated by semicolons.

## Ranking criteria

Each criterion is scored from 0 to 5:

1. `R1`: argument completeness.
2. `R2`: source traceability.
3. `R3`: conflict value.
4. `R4`: temporal value.
5. `R5`: authority or provenance value.
6. `R6`: non-redundancy.
7. `R7`: case centrality.
8. `R8`: methodological diversity.
9. `R9`: timestamp transition value.

`selection_score` is the sum of `R1` through `R9`, with a maximum of 45. Individual criteria remain visible for audit and review.

## Final selection constraints

The final output must contain exactly 27 arguments, but it must not be a mechanical global top-27 ranking.

Selection must jointly consider score, temporal coverage, source diversity, conflict diversity, and non-redundancy.

Soft candidate-pool coverage targets before final selection are:

| Introduced or transitionally central at | Approximate final count |
| --- | ---: |
| `t1` | 6-8 |
| `t2` | 6-8 |
| `t3` | 7-9 |
| `t4` | 7-9 |
| `t5` | 7-9 |
| `t6` | 6-8 |

Arguments may remain relevant across multiple timestamps, so these are coverage targets rather than mutually exclusive quotas.

The candidate pool must contain meaningful provenance from all four source types and must not be dominated by news. Evidence quality must not be lowered merely to satisfy source or timestamp coverage.

The final set must include multiple support and attack relations, at least three conflict types, all six timestamps, authoritative rules and decisions, public or social claims, real competing viewpoints, and arguments whose status or interpretation can change.

## Workflow

```text
Sources
-> Six-timestamp timeline
-> Candidate arguments
-> Temporal tracking
-> Candidate relations
-> Nine-criterion scoring
-> Diversity-aware selection
-> Exactly 27 final arguments
```

Final selection must wait until the candidate pool and source coverage are sufficiently diverse.
