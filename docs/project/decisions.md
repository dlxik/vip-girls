# Decisions

## D-001: Functional repository organization

- Status: approved
- Decision: Organize the repository by project function rather than by week.
- Rationale: Research artifacts should remain stable as work continues across reporting periods.

## D-002: Minimal initial setup

- Status: approved
- Decision: Create documentation, data, graph, and audit-note locations required for data preparation. Defer source-code, scripts, experiments, and output trees until their components begin.
- Rationale: Avoid empty or premature implementation structure.

## D-003: No research data during setup

- Status: approved
- Decision: Do not collect sources, create timelines, annotate arguments, build graphs, or implement agents or solver logic during setup.
- Rationale: Preserve the supervisor review boundary between repository setup and research work.

## D-004: Private GitHub baseline

- Status: approved
- Decision: Initialize Git with `main` as the default branch and publish the setup baseline to the former private repository.
- Rationale: Establish version control while keeping unpublished research preparation non-public by default.

## D-005: CTQ source identifier assignment

- Status: active
- Decision: Assign `CTQ-S001` through `CTQ-S017` to the supervisor-provided seed sources in their given order. Assign newly discovered sources from `CTQ-S018` onward and never renumber them.
- Rationale: Preserve stable references across future batches.

## D-006: Official reporting versus original official documents

- Status: active
- Decision: Classify government or institutional news reports as `news` and `secondary` unless the URL is itself an original decision, regulation, directive, or administrative record.
- Rationale: Institutional publication does not by itself make a report the original legal instrument.

## D-007: Candidate consolidation in batch 1

- Status: active
- Decision: Consolidate repeated reports of the August 5 all-subject resolution into CTQ-C004 using CTQ-S002 and CTQ-S004 rather than creating one candidate per outlet. Consolidate recurring VOZ objections into CTQ-C005 without reproducing abusive or unsupported allegations.
- Rationale: Avoid duplicate arguments while preserving provenance diversity.

## D-008: Provisional relation interpretation in batch 1

- Status: pending human review
- Decision: Treat CTQ-C001 and CTQ-C004 as a scope conflict; CTQ-C002 and CTQ-C005 as attacks on blanket or renewed testing; and CTQ-C003 as authority support for CTQ-C004.
- Rationale: The claims differ through conclusion, applicability, or authority rather than mere wording.

## D-009: Candidate scoring representation

- Status: active
- Decision: Store `R1` through `R9` in dedicated columns and calculate `selection_score` as their sum, with a maximum of 45.
- Rationale: The updated schema requires all nine dimensions to remain directly auditable, including timestamp transition value.

## D-010: CTQ temporal segmentation

- Status: approved
- Decision: Use six information states: `t1` initial suspicion, `t2` misconduct evidence, `t3` Math-retest proposal, `t4` official resolution, `t5` retest evidence, and `t6` broadened investigation.
- Rationale: These states represent meaningful changes in available information rather than every event date.

## D-011: Final CTQ selection size and method

- Status: approved
- Decision: Build approximately 45-50 candidates and later select exactly 27 using score, temporal coverage, provenance diversity, conflict diversity, and non-redundancy.
- Rationale: A global numerical top-27 would risk losing arguments that are methodologically necessary for temporal transitions or underrepresented perspectives.

## D-012: Initial timestamp migration

- Status: pending human review
- Decision: Map CTQ-C003 to `t1` because the pre-existing regulation is available as a stable reference from the first case state; map CTQ-C001, CTQ-C002, and CTQ-C005 to `t3`; and map CTQ-C004 to `t4`.
- Rationale: `introduced_at` means first availability or relevance within the CTQ information-state model, not the publication date of a pre-existing rule.

## D-013: Four-value source taxonomy

- Status: approved
- Decision: Use only `official_document`, `authority_statement`, `news`, and `social`; remove the former `public`, `official`, and `commentary` values.
- Rationale: Provenance form must remain separate from argument status. Official statements and journalism do not become accepted merely because of institutional origin.

## D-014: Accepted-reference constraint

- Status: approved
- Decision: Only a valid and applicable `official_document` may ground an accepted reference. Authenticity, jurisdiction, validity interval, and applicability remain explicit checks.
- Rationale: This prevents authority statements or secondary reporting from being silently promoted into binding knowledge.

## D-015: Transition-target annotation

- Status: approved
- Decision: Record one or more `transition_targets` for every candidate using the five adjacent transitions from `t1->t2` through `t5->t6`.
- Rationale: Transition coverage must be auditable before formal relation annotation or graph construction.

## D-016: Canonical Vietnamese re-extraction

- Status: active
- Decision: For Vietnamese sources, store source-derived titles, premises, rules, conclusions, and research notes in Vietnamese by reopening the original source. Existing English annotations may be used only as a consistency check and must never be back-translated.
- Rationale: Canonical research content must preserve the language and meaning of the original evidence while Git history remains the audit trail for replaced English text.

## D-017: Source-access boundary during normalization

- Status: pending human review
- Decision: Re-extract 37 candidates directly from accessible Vietnamese sources. Keep CTQ-C012, CTQ-C019, CTQ-C023, CTQ-C024, CTQ-C030, CTQ-C032, CTQ-C037, and CTQ-C043 unchanged in English and mark them `NEEDS_HUMAN_REVIEW` because an essential social post or attached official PDF could not be reopened.
- Rationale: Translating the existing English record would violate the source-first policy. The affected records must wait for direct source access.

## D-018: Narrow CTQ-C035 to accessible evidence

- Status: active
- Decision: Remove the inaccessible public-reaction clause from the premise of CTQ-C035 and ground the candidate only in the accessible Ministry of Public Security briefing and its textual news corroboration.
- Rationale: CTQ-S047 could not be reopened. The institutional-accountability conclusion remains supported by the verified breadth of roles reported in CTQ-S029 and CTQ-S030; R1-R9 were reconsidered and retained because the core argument did not change.

## D-019: Mark reconstructed bridging rules explicitly

- Status: active
- Decision: Prefix every non-null normalized bridging rule that is not quoted directly from the governing regulation with `NGẦM ĐỊNH —`. Keep CTQ-C001 null and retain CTQ-C003 as the directly extracted regulatory rule.
- Rationale: This prevents analytical warrants from being misrepresented as wording stated by a source.

## D-020: Final CTQ argument selection

- Status: approved by execution request
- Decision: Select exactly 27 arguments as CTQ-A001 through CTQ-A027 from 37 source-verified candidates. Use score together with timestamp, provenance, viewpoint, conflict, transition, and non-redundancy coverage rather than numerical rank alone.
- Rationale: The selected set keeps four or five arguments at every timestamp, all four approved source types, both A_K and A_D, balanced support/attack potential, and every adjacent temporal transition.

## D-021: Reject unresolved English candidates

- Status: active
- Decision: Reject CTQ-C012, CTQ-C019, CTQ-C023, CTQ-C024, CTQ-C030, CTQ-C032, CTQ-C037, and CTQ-C043 because their essential original Vietnamese source content could not be fully reopened and verified. Clear their English premise, rule, and conclusion fields instead of back-translating them.
- Rationale: Git history preserves the former annotations, while the canonical dataset no longer contains unverifiable English source-derived content.

## D-022: Shared repository migration

- Status: active
- Decision: Use `https://github.com/dlxik/vip-girls.git` as the shared collaboration repository from 2026-11-10. Import the latest legacy state at commit `2e1dce0cfe7fb7113c8c720e568f1983efb44a45`, preserve the existing architecture HTML, and organize documentation under `docs/architecture`, `docs/research`, and `docs/project`.
- Rationale: The project now has two active collaborators and needs a single, clearly indexed shared asset base without losing the provenance of the former repository.

## D-023: Source preservation boundary

- Status: approved by implementation request
- Decision: Commit full source artifacts only when redistribution is clearly permitted. Otherwise retain required metadata and a SHA-256 manifest in the repository while storing any lawful research copy in a private controlled archive. Minimize social-media and personal data and retain only abstracted claims where possible.
- Rationale: This preserves auditability without treating Git as an unrestricted archive of copyrighted, private, or harmful material.

## D-024: Functional layer names

- Status: approved by implementation request
- Decision: Use `core`, `society`, and `hierarchy` in public APIs, configuration, trace fields, tests, and UI instead of historical numbered software-version names.
- Rationale: The names describe responsibility and remain meaningful as the implementation evolves.

## D-025: CTQ scope and runtime viewpoint structure

- Status: approved by implementation request
- Decision: The current implementation serves CTQ only. An argument may belong to multiple viewpoints. Runtime split/merge retires active overlay viewpoints and creates derived replacements after a candidate persists for the configured number of steps; the canonical base mapping remains immutable for audit.
- Rationale: Multi-membership better represents overlapping positions, while an immutable base plus mutable runtime overlay preserves provenance. Primary-owner routing remains a documented deterministic implementation constraint.
