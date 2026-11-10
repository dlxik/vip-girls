# Uncertainties

## U-001: Data serialization format

- Status: open
- Question: Should source, timeline, argument, status, and relation records use CSV, JSON, JSONL, YAML, or a combination?
- Impact: Determines schema files, validation tooling, and handling of list-valued fields.

## U-002: Identifier conventions

- Status: open
- Question: What exact formats should be used for `source_id`, `timestamp_id`, `arg_id`, and `relation_id`?
- Impact: Affects cross-file references and long-term stability.

## U-003: Source preservation policy

- Status: open
- Question: Which source types should be archived locally, and what metadata such as access time or checksum is required?
- Impact: Affects reproducibility, copyright handling, privacy, and resilience to link disappearance.

## U-004: Git baseline workflow

- Status: resolved
- Resolution: The project was initially hosted at `https://github.com/dlxik/AGORA.git`. On 2026-11-10, the latest V4 state was migrated into the shared repository `https://github.com/dlxik/vip-girls.git`; the former repository remains the historical source.
- Impact: Component branches can now be created from the reviewed setup baseline.

## U-005: Original Ministry cancellation decision

- Status: open
- Question: Where is the original, publicly accessible text of Ministry Decision 2288/QD-BGDDT dated 2026-08-04?
- Impact: CTQ-C004 currently relies on institutional reports of the decision rather than the original instrument.
- Batch 3 update: Official Letter 5157 and provincial Plan 305 both cite Decision 2288 and corroborate its operative effect, but the original Decision 2288 file is still not publicly located.

## U-006: Consolidated 2026 examination regulation

- Status: resolved
- Resolution: CTQ-S042 records official Consolidated Document 02/VBHN-BGDDT dated 2026-04-17 from the Government document portal, with attached consolidated regulation text.
- Impact: The consolidation gap is closed. Provision-level validity, material applicability, and interpretation must still be checked for each A_K argument.

## U-007: Public-forum provenance and persistence

- Status: open
- Question: Should public forum posts be archived with post-level URLs, timestamps, and snapshots, subject to privacy and copyright constraints?
- Impact: Thread pagination and edits may weaken future reproducibility.
- Batch 2 note: CTQ-S028 contains abusive language and unsupported allegations. Only abstracted claims are retained; a future preservation policy must address ethical quotation, deletion, and post-level timestamps.

## U-008: Seed-source metadata gaps

- Status: open
- Question: What are the verified publication date for CTQ-S008 and the missing bylines for several seed articles?
- Impact: The source table leaves unverified metadata null rather than guessing.

## U-009: Scope of the Math-only proposal

- Status: open
- Question: Was there an original provincial proposal document that supplied an explicit rule for limiting the remedy to Math?
- Impact: CTQ-C001 currently has no explicit rule component and is classified as A_D despite reporting an official provincial position.

## U-010: Introduction time for pre-existing legal rules

- Status: open
- Question: Should a legal rule published before the CTQ case use `introduced_at = t1`, or should pre-case availability be represented by a separate value outside `t1` through `t6`?
- Impact: The current migration assigns CTQ-C003 to `t1` for coverage reporting, pending supervisor review.

## U-011: Secondary copy of Official Letter 5157

- Status: open
- Question: Is the complete legal-database reproduction of Official Letter 5157/BGDĐT-QLCL sufficient for accepted-reference use, or must the Ministry-hosted original be retained first?
- Impact: CTQ-C023 is provisionally A_K because the document is identifiable, applicable, and complete, but its hosting provenance is secondary and explicitly qualified.
- Batch 5 update: CTQ-S039 now points to an official public-university document repository with the identifiable record and attached PDF, improving provenance over the former legal-database copy. A Ministry-hosted original is still preferred.

## U-012: Sources unavailable during Vietnamese re-extraction

- Status: open
- Question: Can the original content for CTQ-S028, CTQ-S034, CTQ-S040, CTQ-S049, and the attached PDF of CTQ-S039 be recovered or supplied for direct inspection?
- Impact: CTQ-C012, CTQ-C019, CTQ-C023, CTQ-C024, CTQ-C030, CTQ-C032, CTQ-C037, and CTQ-C043 remain in English with `selection_status = needs_human_review`; they must not enter final selection before source-first normalization.
- Additional source-table review: CTQ-S006, CTQ-S016, CTQ-S019, CTQ-S036, and CTQ-S047 also failed direct access in this audit and are marked `needs_human_review`.
- Final-selection resolution: The eight dependent candidates were rejected rather than translated or selected. Source recovery remains useful for archival completeness but no longer blocks the final 27 dataset.
