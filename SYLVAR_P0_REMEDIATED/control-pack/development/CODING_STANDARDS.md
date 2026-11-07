# Coding Standards

- Use typed Python (Python 3.11+), FastAPI, Pydantic v2, SQLAlchemy 2.x async and asyncpg; verify exact compatible versions at setup.
- Use TypeScript strict mode in React/Vite. Keep API contracts typed and generated/validated from the agreed schema where practical.
- Keep a modular monolith; modules communicate through explicit interfaces, not circular imports.
- Validate all external input at boundaries. Reject unknown AI output fields (`extra='forbid'`) and validate IDs/tenant scope server-side.
- Use parameterized SQL and transaction-scoped tenant context. Never trust frontend tenant identifiers.
- Preserve immutable content versions, rule revisions, memory snapshots, audit attempts and findings.
- Normalize Unicode with an explicit raw-offset mapping. Never apply NFKC indiscriminately.
- Keep deterministic checks deterministic. Treat model output as untrusted and never let it directly mutate approval or activation state.
- No empty exception handlers, fake success, placeholder implementations presented as complete, hardcoded secrets or silent fallback behavior.
- Add tests with every behavior change; keep functions focused and error messages safe.
