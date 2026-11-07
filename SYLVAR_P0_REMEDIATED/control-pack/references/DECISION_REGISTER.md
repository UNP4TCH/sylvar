# Decision Register

Binding decisions are recorded in `../DECISIONS.md`. This file is an index, not a competing source of truth.

- ADR-001: Modular monolith.
- ADR-002: Exactly three roles; Brand Manager alone holds human review authority.
- ADR-003: Explicit client assignment required for all client-scoped operations, including Workspace Admin.
- ADR-004: Direct PostgreSQL access through least-privilege runtime role; RLS defense-in-depth.
- ADR-005: Factual outcomes are SUPPORTED / CONTRADICTED / UNVERIFIED.
- ADR-006: Audits pin immutable memory snapshots.
- ADR-007: Logical audit, physical attempt and component check are separate tiers.
- ADR-008: Linear-light alpha compositing; visual deviations advisory.

Do not infer unrecorded decisions. Propose changes for explicit user approval.
