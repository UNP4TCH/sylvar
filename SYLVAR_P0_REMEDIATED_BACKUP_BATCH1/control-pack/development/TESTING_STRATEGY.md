# Testing Strategy

## Required layers
1. Unit: normalizers/offset maps, terminology matching, CIEDE2000, alpha compositing, state transitions, evidence validation.
2. API: DTO validation, status/error contracts, authentication and authorization.
3. Database integration: constraints, transaction-local context, RLS policies, composite tenant FKs, immutability and concurrent activation.
4. Security: cross-workspace/client access attempts, revoked membership, unassigned Workspace Admin, upload spoofing/archive bombs, prompt injection, secret/log leakage.
5. Workflow: guideline ingestion → human approval → memory activation → audit → correction/version fork → re-audit → Brand Manager review → export.
6. Resilience: model timeout/429, component exception isolation, DB failure, process restart, stale attempt reconciliation and duplicate dispatch.
7. Frontend: key user journeys, form validation, loading/error/empty states and accessibility basics.

## Release evidence
Record command, environment, test count, pass/fail and known exclusions. No claim of 100% accuracy or reliability. Use deterministic fixtures for expected results and a small explicitly labelled model-evaluation set for probabilistic factual checks.
