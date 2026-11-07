# DATABASE_DESIGN.md — PostgreSQL Relational Schema & RLS Architecture
**Reference:** Task 3 Data Architecture Specification v1.5 (Frozen 25 Tables)  
**Database Engine:** Supabase Managed PostgreSQL 15+  
**Access Layer:** SQLAlchemy Async + asyncpg  

---

## 1. Application Database Role & Privileges
* **Runtime Role:** `sylvar_app_user`.
* **Privileges:** Explicit `SELECT, INSERT, UPDATE, DELETE` granted strictly on public application tables.
* **Security Invariants:**
  * Role is **NOT** a superuser.
  * Role does **NOT** own schema tables or database extensions.
  * Role does **NOT** possess `BYPASSRLS` privileges.
* **Migration Role:** Schema migrations run separately via a deployment CI/CD role (`supabase_admin` or direct postgres credentials), never by the runtime application role.

---

## 2. Transaction-Local Tenant Context & Connection Pooling
To prevent tenant context from leaking between requests sharing pooled `asyncpg` connections:
1. Upon acquiring a connection from the pool, the session manager initiates an explicit transaction.
2. Inside the transaction block, the session executes:
   ```sql
   SET LOCAL app.current_workspace_id = :authenticated_workspace_id;
   SET LOCAL app.current_client_id = :authorized_client_id;
   ```
3. Because `SET LOCAL` variables scope strictly to the active transaction block, they reset automatically upon `COMMIT` or `ROLLBACK`. Context leakage across pooled connections is structurally impossible.
4. If a query executes without valid tenant context, RLS policies evaluate to false (deny / fail closed).

---

## 3. Complete 25-Table Catalogue

### Domain A: Identity & Workspace
1. `users`: Profile metadata extending `auth.users`. PK: `id (UUID)`.
2. `agency_workspaces`: Top-level agency tenant entity. PK: `id (UUID)`. Unique: `slug`.
3. `workspace_memberships`: Associates users with workspaces and roles (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`). Enforces status (`INVITED`, `ACTIVE`, `SUSPENDED`, `REVOKED`) and `revoked_at (TIMESTAMPTZ, NULL)`.

### Domain B: Client Brand Management
4. `client_brands`: Client brand space. PK: `id (UUID)`. Unique: `(workspace_id, id)`. FK: `active_memory_version_id`.
5. `client_memberships`: Independent client assignment table. PK: `id (UUID)`. Composite FK: `(workspace_id, client_id) REFERENCES client_brands(workspace_id, id)`. Roles: `BRAND_MANAGER`, `CONTENT_CREATOR`. Status: `ACTIVE`, `REVOKED`.

### Domain C: Document Management
6. `guideline_documents`: Tracks uploaded brand books. Statuses: `PENDING`, `PARSING`, `EXTRACTED`, `REPLACED`, `FAILED`.
7. `document_sections`: Normalized headings, body paragraphs, and page offsets.
8. `extracted_candidates`: Staging queue for candidate rules awaiting human review (`PENDING_REVIEW`, `APPROVED`, `MODIFIED_APPROVED`, `REJECTED`).

### Domain D: Living Brand Memory
9. `brand_memory_versions`: Formal release headers (`DRAFT`, `ACTIVE`, `SUPERSEDED`, `ARCHIVED`).
10. `brand_memory_version_rules`: Association table linking memory versions to exact rule revisions.
11. `brand_rules`: Authoritative approved brand rules (Terminology, Fact, Color, Voice). Composite FK on `current_revision_id`.
12. `brand_rule_revisions`: Immutable historical record of modifications made to approved rules.
13. `brand_memory_snapshots`: Materialized JSONB snapshots storing frozen rulebooks with SHA-256 hashes.

### Domain E: Content Management
14. `content_assets`: Campaign collateral containers.
15. `asset_versions`: Immutable draft copy and image iterations tracking lifecycle states (`DRAFT` -> `APPROVED`) and `created_from_correction_id`.

### Domain F: Audit Management
16. `audit_runs`: Logical audit header pinned to `memory_snapshot_id`. Statuses: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `INTERRUPTED`. Outcomes: `PASS`, `WARNINGS`, `BLOCKED`.
17. `audit_execution_attempts`: Physical execution runs. Guarded by partial unique index `idx_single_running_attempt_per_audit` for `RUNNING` status. Tracks `heartbeat_at`.
18. `audit_checks`: Component check status (`TERMINOLOGY`, `FACTUAL`, `VISUAL`) and verification manifests.
19. `audit_findings`: Actionable compliance issues with evidence lineage pointers.
20. `correction_suggestions`: Minimal-edit AI rewrites with decision states (`PENDING`, `ACCEPTED`, `DISMISSED`).

### Domain G: Human Review
21. `human_reviews`: Brand Manager sign-off decisions (`APPROVED`, `REJECTED`, `CHANGES_REQUESTED`).
22. `human_review_advisory_acknowledgements`: Relational links between reviews and acknowledged advisory findings.
23. `audit_history`: Exportable compliance audit records compiled upon sign-off.

### Domain H: System History
24. `system_audit_logs`: Security-sensitive event log with sensitive-field masking (`[REDACTED]`).
25. `knowledge_activation_history`: Historical memory version activation and deactivation audit trail.

---

## 4. Row-Level Security (RLS) Policy Specifications
RLS is enabled on all tenant-scoped tables:
```sql
ALTER TABLE client_brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_brands FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_client_brands ON client_brands
    FOR ALL
    USING (workspace_id = NULLIF(current_setting('app.current_workspace_id', true), '')::uuid);
```


## 5. Schema Completeness and Implementation Gate
The catalogue above is a 25-table domain inventory only. It is NOT a migration-ready schema. Before migrations are written, produce and review a schema specification for every table containing: columns and exact SQL types; nullability/defaults; primary/unique/check constraints; all foreign keys (including composite tenant keys); indexes and partial-index predicates; delete/update behavior; immutable-history enforcement; triggers; and RLS enable/force statements plus complete SELECT/INSERT/UPDATE/DELETE policies.

The example policy above is illustrative and insufficient as a complete tenant-security implementation. Derive policies for every tenant-scoped table and test both allowed and denied paths using the actual runtime role. Validate how workspace/client context is established for every query and how workspace-level tables are protected. Do not infer that RLS is safe merely because `SET LOCAL` is used. Verify Supabase connection role capabilities and transaction/pool behavior in an integration environment.

Blocking implementation gate: no production migrations or claims of tenant isolation until schema and policy specifications are complete and automated cross-tenant tests pass.
