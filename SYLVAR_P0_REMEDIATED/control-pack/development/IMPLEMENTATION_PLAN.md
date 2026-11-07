# Implementation Plan

**State:** Prepared only. Round 2 is not authorized.

## Delivery sequence
1. Phase 1 — repository/tooling, configuration, Supabase Auth integration, JWT verification, health endpoint.
2. Phase 2 — schema specification gate, migrations, least-privilege DB role, tenant context, RLS, authorization and isolation tests.
3. Phase 3 — secure guideline ingestion, extraction staging, Brand Manager approval, immutable memory releases.
4. Phase 4 — content/version intake, persisted audit orchestration, terminology/factual/visual checks, findings, corrections and re-audit.
5. Phase 5 — Brand Manager review, advisory acknowledgement, immutable history/export, hardening, deployment and demo rehearsal.

## Mandatory pre-implementation gates
- Verify exact supported package/runtime versions and Gemini model IDs.
- Complete the full 25-table schema and all RLS policies before migrations.
- Complete API DTO/OpenAPI contracts and align role authorization.
- Define crash/restart behavior for in-process tasks; persisted attempts must be reconciled safely.
- Establish test strategy, secrets handling, private storage and upload validation.
- Benchmark performance; do not use aspirational targets as guarantees.

## Execution discipline
Implement one task at a time in dependency order. Each task must include code, tests, documentation updates and evidence. Never mark a task complete based only on compilation or a mocked response. Stop on unresolved schema, security or API contract gaps.
