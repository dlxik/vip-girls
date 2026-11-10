# Problem Definition

## Research objective

AGORA studies how argument structures change as public claims, case-specific evidence, and authoritative information become available over time.

The current formulation is:

```text
I = (K, D, C)
A = A_K union A_D
a_i = (P_i, R_i, C_i)
status(a_i, t) in {accepted, rejected, undecided}
G_t = (A_t, E_t)
```

Where:

- `K` is a legal or official knowledge source or knowledge graph.
- `D` contains external information such as public claims, news, social content, and case-specific information.
- `C` is context.
- `A_K` contains legal or official-grounded arguments.
- `A_D` contains arguments constructed from external information.
- `E_t` contains support or attack relations active at time `t`.

## Cases

- Master case: THPT Chuyen Tuyen Quang (CTQ).
- Validation case: household business taxation.

## Current boundary

The current stage covers data preparation and temporal representation only. It does not include solver implementation, ASP encoding, or a multi-agent system.
