# SYLVAR — Batch 3.1 Database Verification Report

**Generated:** 2026-11-07  
**Task:** Focused diagnosis and recovery of Migration 008  
**Project:** SYLVAR — Multi-Tenant Brand Governance Platform  
**Supabase Project Ref:** `apnqefdonksrxbqmnaou`

---

## Executive Summary

Migration 008 (`008_batch3_1_governance_hardening.sql`) was **NOT applied** to the live Supabase database. All Batch 3.1 governance constraints, partial unique indexes, the decision-metadata CHECK constraint, and the separation-of-duties trigger remain absent from the live PostgreSQL schema. The migration SQL is correct and ready for manual application by a user with the `postgres` superuser role via the Supabase SQL Editor or Supabase CLI.

All 38 Batch 3.1 local regression tests (in-memory SQLite) pass and enforce the same logic at the application layer.

---

## 1. Original Failure — Exact PostgreSQL Errors

Two migration execution attempts were made and both failed.

### Attempt 1 — SQLAlchemy `text()` / `conn.execute()`

**Script:** `backend/app/db/apply_migration_008.py`  
**Error:**
```
asyncpg.exceptions.PostgresSyntaxError: cannot insert multiple commands into a prepared statement
```

**Root Cause:**  
The SQLAlchemy asyncpg dialect internally calls `prepare()` on SQL passed through `text()`. PostgreSQL's wire-protocol `prepare` does not accept multi-statement SQL scripts. Each `CREATE INDEX`, `ALTER TABLE`, and `DO $$...$$` block must be separated into individual execute calls or run via a raw asyncpg connection. This is an asyncpg/SQLAlchemy compatibility constraint, not a schema error.

---

### Attempt 2 — Raw `asyncpg.connect().execute()`

**Script:** `backend/app/db/apply_migration_008_asyncpg.py`  
**Connected as:** `sylvar_app_user`  
**Error:**
```
asyncpg.exceptions.InsufficientPrivilegeError: must be owner of table approval_requests
```

**Root Cause:**  
`sylvar_app_user` has DML privileges (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) on `approval_requests` and `compliance_certificates`, but it does **not own** those tables. In PostgreSQL, DDL operations — including `CREATE INDEX`, `ALTER TABLE ... ADD CONSTRAINT`, and `CREATE TRIGGER` — require the executing role to be either the table owner or a superuser.

The `approval_requests` table is owned by `postgres` (the Supabase admin role). `sylvar_app_user` has `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`, and cannot perform any DDL on tables it does not own.

---

## 2. Root Cause

| Factor | Detail |
|--------|--------|
| Table owner | `postgres` (Supabase admin role) |
| App runtime role | `sylvar_app_user` |
| App runtime privileges | DML only (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) |
| `sylvar_app_user` superuser | NO (`NOSUPERUSER`) |
| Migrations 001–007 applied by | `postgres` (Supabase SQL Editor / CLI) |
| Migration 008 attempt by | `sylvar_app_user` (only credentials in `.env`) |
| `postgres` credentials in `.env` | NOT PRESENT — must be obtained from Supabase Dashboard |

All prior migrations were applied by a user with the `postgres` superuser role via the Supabase CLI or SQL Editor. Migration 008 requires the same approach. The app's `.env` only carries `sylvar_app_user` credentials, which is correct for a least-privilege runtime role and should **not** be granted DDL privileges.

---

## 3. Live Database State — Verified 2026-11-07

Verification was performed by connecting as `sylvar_app_user` and querying `pg_indexes`, `pg_constraint`, `pg_trigger`, `pg_proc`, and `pg_policies`.

```
Connected as: sylvar_app_user (session_user=sylvar_app_user)
Host: aws-0-ap-southeast-2.pooler.supabase.com:5432
Database: postgres
```

### 3.1 Indexes on `approval_requests`

| Index Name | Type | Present |
|------------|------|---------|
| `approval_requests_pkey` | PK (btree on `id`) | EXISTS |
| `idx_approval_requests_client` | btree on `(workspace_id, client_id, status, created_at)` | EXISTS |
| `uq_approval_requests_pending_version` | Partial unique WHERE `status='PENDING'` | **MISSING** |
| `uq_approval_requests_approved_version` | Partial unique WHERE `status='APPROVED'` | **MISSING** |

### 3.2 Indexes on `compliance_certificates`

| Index Name | Type | Present |
|------------|------|---------|
| `compliance_certificates_pkey` | PK (btree on `id`) | EXISTS |
| `compliance_certificates_certificate_hash_key` | UNIQUE btree on `certificate_hash` | EXISTS |
| `idx_compliance_cert_lookup` | btree on `(workspace_id, client_id, asset_version_id)` | EXISTS |
| `uq_compliance_cert_approval_request` | UNIQUE btree on `approval_request_id` | EXISTS (from Migration 004) |
| `uq_compliance_cert_version` | UNIQUE on `asset_version_id` | **MISSING** |

### 3.3 CHECK Constraints on `approval_requests`

| Constraint Name | Definition | Present |
|----------------|------------|---------|
| `approval_requests_status_check` | `status IN ('PENDING','APPROVED','REJECTED','CHANGES_REQUESTED')` | EXISTS |
| `ck_approval_requests_decision_metadata` | PENDING → decided_at NULL; decided → decided_at NOT NULL | **MISSING** |

### 3.4 Triggers on `approval_requests`

| Trigger Name | Function | Present |
|-------------|----------|---------|
| `trg_approval_sod` | `trg_fn_enforce_approval_sod()` | **MISSING** |

### 3.5 Trigger Functions

| Function Name | Present |
|--------------|---------|
| `trg_fn_enforce_approval_sod` | **MISSING** |

### 3.6 RLS Policies

| Policy Name | Table | Command | Roles |
|-------------|-------|---------|-------|
| `approval_requests_access` | `approval_requests` | ALL | public |
| `compliance_certificates_access` | `compliance_certificates` | ALL | public |

RLS is enabled on both tables. PASS

### 3.7 Data Compatibility Check

| Check | Result |
|-------|--------|
| Duplicate PENDING approval requests | NONE — index-compatible |
| Duplicate compliance certificates per asset version | NONE — index-compatible |

No data cleanup is required before applying Migration 008.

---

## 4. Files Changed During Batch 3.1

| File | Change |
|------|--------|
| `backend/app/models/review.py` | Added `ck_approval_requests_decision_metadata` CHECK constraint in `__table_args__`; added `UniqueConstraint("asset_version_id", "uq_compliance_cert_version")` to `ComplianceCertificate`; fixed missing `literal_column` import |
| `backend/app/modules/reviews/router.py` | Accept only `APPROVED`, `REJECTED`, `CHANGES_REQUESTED` decisions; reject `PENDING`; full separation-of-duties (submitter, asset creator, version creator); fail-closed on missing ownership data |
| `backend/app/modules/remediation/engine.py` | Unicode NFC normalization; single-pass reconstruction; overlap/conflict detection (422 `SUGGESTION_CONFLICT`); ambiguous-match rejection; deduplication; `SELECT ... FOR UPDATE` locking; SHA-256 duplicate version reuse; `IntegrityError` → 409 `VERSION_CONFLICT` |
| `backend/app/modules/audits/router.py` | Explicit `await db.commit()` after flush; workspace+client scoped snapshot lookup; hardened suggestion validation (upfront ID validation, deterministic sort, no-op rejection) |
| `backend/app/modules/orchestrator/runner.py` | Sanitized engine crash messages; added structured logging |
| `backend/tests/test_batch3_1_hardening.py` | NEW — 9 tests covering PENDING rejection, SoD for submitter/asset-creator/version-creator, valid independent reviewer, remediation overlap, ambiguous span, certificate immutability |
| `backend/tests/test_phase4_audit.py` | Fixed mock patch path → `app.modules.orchestrator.runner.run_async_factual_check` |
| `backend/tests/test_phase5_review.py` | Fixed mock patch path → `app.modules.orchestrator.runner.run_async_factual_check` |
| `backend/tests/test_batch1_regression.py` | Fixed `snapshot_hash` length to 64 chars; added `AuditCheck` fixture entries for TERMINOLOGY and FACTUAL engines |
| `supabase/migrations/008_batch3_1_governance_hardening.sql` | NEW — DDL for all 5 governance constraints (ready for manual application) |

---

## 5. Verification Results Summary

| Check | Status | Notes |
|-------|--------|-------|
| **Migration 008 applied to live DB** | NOT APPLIED | Requires `postgres` superuser via Supabase SQL Editor |
| `uq_approval_requests_pending_version` index | FAIL | Not found in `pg_indexes` |
| `uq_approval_requests_approved_version` index | FAIL | Not found in `pg_indexes` |
| `uq_compliance_cert_version` constraint | FAIL | Not found in `pg_indexes` |
| `ck_approval_requests_decision_metadata` CHECK | FAIL | Not found in `pg_constraint` |
| `trg_approval_sod` trigger | FAIL | Not found in `pg_trigger` |
| `trg_fn_enforce_approval_sod()` function | FAIL | Not found in `pg_proc` |
| No duplicate PENDING requests (data check) | PASS | Zero records — migration-safe |
| No duplicate cert per asset version (data check) | PASS | Zero records — migration-safe |
| RLS enabled on `approval_requests` | PASS | Policy `approval_requests_access` present |
| RLS enabled on `compliance_certificates` | PASS | Policy `compliance_certificates_access` present |
| Local regression tests (38 tests) | PASS | In-memory SQLite; all 38 pass |
| Application-layer SoD enforcement | PASS | Enforced in `reviews/router.py` |
| Application-layer PENDING rejection | PASS | Enforced in `reviews/router.py` schema validation |
| Application-layer terminal state protection | PASS | Enforced in `reviews/router.py` pre-flight check |
| Remediation Unicode NFC normalization | PASS | Enforced in `remediation/engine.py` |
| Remediation overlap detection | PASS | Tested in `test_batch3_1_hardening.py` |
| Frontend build | PASS | 96 modules, no errors |

---

## 6. What Remains Blocked

The following checks **cannot be performed** until Migration 008 is applied to the live database:

| Blocked Check | Blocker |
|--------------|---------|
| Partial unique index prevents duplicate PENDING requests at DB level | Migration 008 not applied |
| Partial unique index prevents duplicate APPROVED requests at DB level | Migration 008 not applied |
| Unique constraint prevents multiple certs per asset version at DB level | Migration 008 not applied |
| CHECK constraint rejects PENDING records with `decided_at IS NOT NULL` at DB level | Migration 008 not applied |
| DB trigger rejects self-approval (submitter, asset creator, version creator) | Migration 008 not applied |
| DB trigger prevents mutation of decided requests | Migration 008 not applied |

**All the above are enforced at the application layer.** The database constraints would add defense-in-depth protection.

---

## 7. How to Apply Migration 008

Since `sylvar_app_user` cannot perform DDL, Migration 008 must be applied using the `postgres` superuser role.

### Option A — Supabase SQL Editor (Recommended)

1. Open: `https://supabase.com/dashboard/project/apnqefdonksrxbqmnaou/sql`
2. Copy the full contents of `supabase/migrations/008_batch3_1_governance_hardening.sql`
3. Paste into the SQL Editor and click **Run**
4. Re-run the verification script to confirm all 6 checks turn to PASS

### Option B — Supabase CLI

```bash
# From the SYLVAR_P0_REMEDIATED directory (requires Supabase CLI + project linkage)
supabase db push
```

The migration file is already at: `supabase/migrations/008_batch3_1_governance_hardening.sql`

---

## 8. Privilege and Security Verification

| Verification | Result |
|-------------|--------|
| `sylvar_app_user` has SUPERUSER | NO — correct |
| `sylvar_app_user` has BYPASSRLS | NO — correct |
| `sylvar_app_user` has CREATEROLE | NO — correct |
| `sylvar_app_user` has CREATEDB | NO — correct |
| Runtime role follows least-privilege | CONFIRMED |
| `.env` does NOT contain `postgres` superuser credentials | CONFIRMED |
| Migration 008 does NOT grant DDL privileges to `sylvar_app_user` | CONFIRMED |
| Migration 008 does NOT grant BYPASSRLS to `sylvar_app_user` | CONFIRMED |
| Credentials not exposed in this report | CONFIRMED |

---

## 9. Local Test Results (Confirmed)

```
Backend test suite (in-memory SQLite):
pytest tests/test_batch3_1_hardening.py tests/test_phase5_review.py
      tests/test_phase4_audit.py tests/test_batch1_regression.py
      tests/test_phase2_multi_tenancy.py tests/test_phase3_memory.py -v

Result: 38 passed, 5 warnings
Duration: ~38s
```

| Test File | Status |
|-----------|--------|
| `test_batch3_1_hardening.py` (9 tests) | PASS |
| `test_phase5_review.py` | PASS |
| `test_phase4_audit.py` | PASS |
| `test_batch1_regression.py` | PASS |
| `test_phase2_multi_tenancy.py` | PASS |
| `test_phase3_memory.py` | PASS |

---

## 10. Conclusion

**Migration 008 was NOT applied to the live database.**

The governance constraints defined in Migration 008 are enforced at the **application layer** (FastAPI router and SQLAlchemy models) and are comprehensively tested by the local regression suite (38/38 passing). The database-level constraints would provide defense-in-depth but are blocked by the `sylvar_app_user` privilege model — which is correct and must not be changed.

**Action Required:** Apply `008_batch3_1_governance_hardening.sql` via the Supabase SQL Editor (paste-and-run) using the `postgres` superuser account from the Supabase dashboard before claiming full database-level governance verification.

---

*Report generated by SYLVAR Batch 3.1 Database Verification · Project: apnqefdonksrxbqmnaou*

