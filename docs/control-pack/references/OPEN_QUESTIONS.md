# Open Questions and Implementation Verification Gates

These are not permission to improvise. Resolve and record evidence before the dependent implementation task.

## Blocking
1. Complete executable definitions for all 25 tables: columns, constraints, composite FKs, indexes, triggers, delete semantics and immutable-history protections.
2. Complete RLS policies for every tenant-scoped table and verify with the actual runtime role, including workspace-level tables.
3. Confirm Supabase direct PostgreSQL connection configuration, role creation/privileges, TLS and pool/transaction semantics.
4. Define durable-enough in-process audit dispatch/restart reconciliation. No Redis/Celery is approved; document the accepted limitation and safe recovery protocol.
5. Complete endpoint request/response DTOs, status codes, pagination and RFC 9457 error catalogue; reconcile `/auth/session` with Supabase Auth ownership.
6. Verify supported Gemini model IDs, structured-output support, rate limits and data-use terms for the selected account.
7. Define how large snapshots are filtered and retrieved, and validate evidence references against immutable pinned snapshots.

## Non-blocking but required before release
- Empirically benchmark latency, cost and model quality.
- Verify exact compatible package versions and hosting limits.
- Define backup/restore and migration rollback procedures.
