# Requirement Traceability

| Requirement area | Source of truth | Implementation evidence required |
|---|---|---|
| Product scope and workflows | `product/MASTER_PRD.md`, `product/USER_WORKFLOWS.md` | End-to-end workflow tests |
| Role and client assignment | `RULES.md`, `DECISIONS.md`, `product/USER_ROLES.md` | Positive/negative authorization tests for all roles |
| Database and tenant isolation | `architecture/DATABASE_DESIGN.md` plus schema gate | Migration review, RLS integration tests, FK/index tests |
| API contracts | `architecture/API_DESIGN.md` | OpenAPI/DTO validation and endpoint tests |
| Audit epistemics | `RULES.md`, `architecture/AI_INTELLIGENCE.md` | Deterministic fixtures, evidence validation and model evaluation |
| Audit execution/recovery | `DECISIONS.md`, `architecture/SYSTEM_COMPONENTS.md` | Restart, timeout, retry and duplicate-attempt tests |
| Security | `architecture/SECURITY_ARCHITECTURE.md` | Security test report |
| Deployment | `development/DEPLOYMENT.md` | Staging smoke-test evidence |

A requirement is not complete merely because it appears in documentation.
