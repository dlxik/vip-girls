# Architecture

## Conceptual layers

1. Source collection and preservation
2. Source metadata and review
3. Information-availability timelines
4. Argument and relation annotation
5. Temporal graph snapshots
6. Grounding and conflict detection
7. Symbolic reasoning
8. Supporting agent capabilities
9. Experiments, evaluation, and reporting

Only the first five layers are relevant to the current data-preparation phase, and this setup does not populate them with research data.

## Separation of concerns

- Data artifacts are organized by their research function.
- Argument definitions are separate from time-dependent status records.
- Source evidence is separate from derived annotations.
- Graph snapshots contain only arguments and relations available or valid at their timestamp.
- Supporting agents remain conceptually separate from the future symbolic reasoning core.

Implementation choices and detailed schemas remain open until reviewed.
