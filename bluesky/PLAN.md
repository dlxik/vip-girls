# Blue Sky Temporal Demo Plan

## Pipeline

`Arguments -> Temporal Argument Graph -> Viewpoint Clusters -> Viewpoint Agents -> Agentic Public Deliberation`

## Implemented scope

1. Read and validate the canonical CTQ CSV files.
2. Build six causally ordered snapshots `t1` through `t6`.
3. Render one evolving, interactive argument graph.
4. Preserve source, status and relation provenance in the detail panel.
5. Group all 27 selected arguments into seven documented viewpoint agents.
6. Aggregate cross-viewpoint edges while retaining their underlying relation IDs.
7. Generate one offline HTML artifact with a single command.

## Modeling decisions

- Timestamp states replace the former artificial simulation rounds.
- No status, relation or missing rule is inferred.
- Arguments respect `introduced_at` and `active_until`.
- Manual viewpoint mapping is preferred to unreliable automatic clustering in version 1.
- No numerical strength score is used; active argument and status counts remain transparent.
- Institutional information is recognized from real source types, not from a hardcoded agent.

## Non-goals

- LLM role-play or chatbot debate
- Automatic clustering
- Reinforcement learning
- Belief-revision solver
- Backend API or production deployment

## Validation target

All six snapshots must build without missing status records or dangling source/relation IDs. Both visualization modes, the time slider, filters, node details and relation details must operate from the same embedded canonical payload.
