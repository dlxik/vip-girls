# System Architecture

## Runtime flow

```text
Canonical CSV + viewpoint mapping
→ validation
→ temporal snapshots
→ core belief/reasoning/interaction loop
→ society semantics and dynamics
→ hierarchical argument subagents
→ deterministic message propagation
→ conflict, steering and risk monitoring
→ JSON trace, evaluation report and HTML visualization
```

## Source layout

- `src/pipeline`: data loading, validation, temporal graph and viewpoint layers.
- `src/core`: beliefs, observations, reasoning, policy, interaction and revision.
- `src/society`: semantics, dynamics, institutional policy and risk monitoring.
- `src/hierarchy`: argument subagents, macro aggregation and propagation queue.
- `src/resources`: reviewed runtime mappings.
- `src/demo.py`: CLI entry point and output generation.

## Time model

- `t` is a reviewed real-world information snapshot (`t1` through `t6` for CTQ).
- `k` is a deterministic deliberation step inside one snapshot.
- Propagation delay is expressed only in `k` and can carry across snapshots.
- No calendar latency or real-world exposure is inferred by the simulation.

## Separation of concerns

- Canonical source, argument, status and relation records remain outside runtime state.
- Argument definitions are separate from time-dependent status records.
- Temporal snapshots contain only information available or valid at their timestamp.
- Core reasoning never creates factual claims or canonical relations.
- Society-level metrics aggregate runtime behavior but retain provenance.
- Hierarchical subagents reuse canonical argument ownership without changing it.
- Generated outputs are derived artifacts; canonical inputs are hashed before and after a run.

## Validation boundary

The loader checks identifier uniqueness, foreign keys, timestamp order, date intervals, status coverage, relation confidence and accepted-reference grounding. Trace validators separately check action, interaction, revision, event, message and risk provenance.

The system remains a deterministic research prototype. Its weights and risk scores are configurable heuristics rather than empirically calibrated legal or causal conclusions.
