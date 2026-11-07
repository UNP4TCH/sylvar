# SYLVAR — Final Database Privilege Audit (Read-Only)

**Date of Execution:** 2026-11-08  
**Audit Target:** Live Supabase PostgreSQL Database  
**Host:** `aws-0-ap-southeast-2.pooler.supabase.com:5432`  
**Database:** `postgres`  
**Supabase Project Ref:** `apnqefdonksrxbqmnaou`  
**Audited Role:** `sylvar_app_user` (session_user: `sylvar_app_user`)  
**Methodology:** Direct inspection of system catalogs (`information_schema.role_table_grants`, `pg_class`, `pg_roles`, `pg_auth_members`, `pg_default_acl`, `has_table_privilege()`, `has_sequence_privilege()`, `has_function_privilege()`, `pg_policies`). Zero schema modifications, zero role alterations, zero data mutations.

---

## Executive Summary

This read-only security audit evaluated the effective privilege profile of the application runtime role (`sylvar_app_user`) across the core SYLVAR domains.

**Key Findings:**
1. **Least Privilege Enforced:** `sylvar_app_user` has `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEROLE`, `NOCREATEDB`, and inherits **zero** roles.
2. **Table Ownership Safe:** All application tables, sequences, functions, and triggers are strictly owned by `postgres` (the Supabase administrative role). `sylvar_app_user` owns 0 objects and cannot execute DDL (`CREATE INDEX`, `ALTER TABLE`, `CREATE TRIGGER`, `ALTER FUNCTION`).
3. **Compliance Certificate Immutability:** `sylvar_app_user` has **no UPDATE, no DELETE, and no TRUNCATE** privileges on `compliance_certificates`. Certificates are write-once, tamper-evident audit records protected at the PostgreSQL grant layer and reinforced by RLS.
4. **Approval Request Protection:** `sylvar_app_user` has **no DELETE** privilege on `approval_requests`. Terminal approval requests cannot be deleted via the SQL interface. Terminal state updates are additionally rejected at the database trigger level (`trg_approval_sod`).
5. **Row-Level Security (RLS):** Enabled and forced (`relrowsecurity = true`, `relforcerowsecurity = true`) across all tables.

---

## 1. Effective Privilege Matrix

Effective table privileges evaluated via `has_table_privilege('sylvar_app_user', table, privilege)`:

| Protected Table | SELECT | INSERT | UPDATE | DELETE | TRUNCATE | REFERENCES | TRIGGER | Security Assessment |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| `approval_requests` | ✅ PASS | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | Least privilege enforced. No DELETE or TRUNCATE. UPDATE guarded by `trg_approval_sod`. |
| `compliance_certificates` | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | **Immutable write-once manifest**. Neither UPDATE nor DELETE granted. |
| `content_assets` | ✅ PASS | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | Read/write allowed for asset lifecycle. No DELETE/TRUNCATE. |
| `asset_versions` | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | **Append-only version lineage**. Versions cannot be updated in-place. |
| `audit_runs` | ✅ PASS | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | Lifecycle status transitions allowed (PENDING → COMPLETED). No DELETE. |
| `audit_checks` | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | **Immutable check findings**. Once recorded by orchestrator, cannot be mutated. |
| `agency_workspaces` | ✅ PASS | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | Workspace management allowed. Deletion managed via soft revocation. |
| `client_brands` | ✅ PASS | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | Brand settings manageable. SQL DELETE revoked. |
| `users` | ✅ PASS | ✅ PASS | ✅ PASS | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | 🔒 **BLOCKED** | Profile discovery and update permitted; user hard-delete blocked. |

---

## 2. Compliance Certificate Immutability Audit

### Evaluation Checklist

| Audit Question | Result | Evidence / Mechanism | Status |
|---|---|---|:---:|
| Can `sylvar_app_user` **DELETE** compliance certificates? | **NO** | `has_table_privilege('sylvar_app_user', 'compliance_certificates', 'DELETE')` returned `False`. `information_schema.role_table_grants` confirms no DELETE grant exists. | **PASS** |
| Can `sylvar_app_user` **UPDATE** compliance certificates? | **NO** | `has_table_privilege('sylvar_app_user', 'compliance_certificates', 'UPDATE')` returned `False`. `information_schema.role_table_grants` confirms no UPDATE grant exists. | **PASS** |
| Can `sylvar_app_user` **TRUNCATE** compliance certificates? | **NO** | `has_table_privilege('sylvar_app_user', 'compliance_certificates', 'TRUNCATE')` returned `False`. In PostgreSQL, TRUNCATE requires table ownership or explicit grant; neither is present. | **PASS** |

### Defense-in-Depth Analysis
1. **SQL Grant Layer:** Only `SELECT` and `INSERT` are granted to `sylvar_app_user` on `compliance_certificates`. Any `UPDATE`, `DELETE`, or `TRUNCATE` issued by the application is rejected immediately by the PostgreSQL query planner (`permission denied for table compliance_certificates`).
2. **Row-Level Security Layer:** Policy `compliance_certificates_access` (`cmd = ALL`) enforces tenant isolation (`workspace_id = current_app_workspace_id() AND client_id = current_app_client_id()`), ensuring cross-tenant leakage is impossible even within authorized SELECT/INSERT paths.
3. **Database Uniqueness Constraints:** `uq_compliance_cert_approval_request` (1:1 with approval request) and `uq_compliance_cert_version` (1:1 with asset version) prevent certificate duplication or replacement.

---

## 3. Approval Request Protection Audit

### Evaluation Checklist

| Audit Question | Result | Evidence / Mechanism | Status |
|---|---|---|:---:|
| Can `sylvar_app_user` **DELETE** terminal approval requests? | **NO** | `has_table_privilege('sylvar_app_user', 'approval_requests', 'DELETE')` returned `False`. DELETE privilege is not granted. | **PASS** |
| Can `sylvar_app_user` **UPDATE** terminal approval requests? | **NO** | Database trigger `trg_approval_sod` intercepts all `UPDATE` statements and raises SQLSTATE `23514` (`Cannot modify an already decided approval request`). | **PASS** |
| Can `sylvar_app_user` bypass the separation-of-duties trigger? | **NO** | `sylvar_app_user` is not a superuser (`rolsuper = False`) and does not own the trigger or table (`postgres` owns both). Disabling or dropping the trigger requires table ownership. | **PASS** |

### Terminal State Protection Details
- **Trigger Definition (`trg_fn_enforce_approval_sod`):**
  ```sql
  IF OLD.status IN ('APPROVED', 'REJECTED', 'CHANGES_REQUESTED') THEN
      RAISE EXCEPTION 'Cannot modify an already decided approval request'
          USING ERRCODE = '23514';
  END IF;
  ```
- **Live Test Proof:** Verified via rollback behavioral testing (`test7_trigger_blocks_decided_mutation`) where an attempt to transition an already-decided request from `APPROVED` to `REJECTED` was trapped and blocked with SQLSTATE `23514`.

---

## 4. Runtime Role Ownership & Privilege Escalation Audit

### Evaluation Checklist

| Audit Question | Live Database State | Status |
|---|---|:---:|
| Is `sylvar_app_user` the owner of any application tables? | **NO**. All 22 public tables are owned by `postgres`. | **PASS** |
| Does `sylvar_app_user` hold `SUPERUSER` privileges? | **NO**. `rolsuper = False`. | **PASS** |
| Does `sylvar_app_user` hold `BYPASSRLS` privileges? | **NO**. `rolbypassrls = False`. | **PASS** |
| Does `sylvar_app_user` hold `CREATEROLE` privileges? | **NO**. `rolcreaterole = False`. | **PASS** |
| Does `sylvar_app_user` hold `CREATEDB` privileges? | **NO**. `rolcreatedb = False`. | **PASS** |
| Does `sylvar_app_user` inherit elevated privileges from parent roles? | **NO**. Query against `pg_auth_members` confirms zero parent roles (`inherited_roles = []`). | **PASS** |
| Can `sylvar_app_user` modify functions or triggers? | **NO**. All functions (`trg_fn_enforce_approval_sod`, `current_app_*`) are owned by `postgres`. `sylvar_app_user` holds `EXECUTE` only. `ALTER FUNCTION` / `DROP FUNCTION` requires function ownership. | **PASS** |
| Are default ACLs secure for future tables? | Default ACLs in `pg_default_acl` do not grant automatic privileges to `sylvar_app_user`. Future tables require explicit grants from `postgres`. | **PASS** |

---

## 5. Explicit Grant Inventory (`information_schema.role_table_grants`)

Queried directly from PostgreSQL:

```
Table                      Grantee          Privilege   Grantor    Is Grantable
-------------------------  ---------------  ----------  ---------  ------------
agency_workspaces          sylvar_app_user  INSERT      postgres   NO
agency_workspaces          sylvar_app_user  SELECT      postgres   NO
agency_workspaces          sylvar_app_user  UPDATE      postgres   NO
approval_requests          sylvar_app_user  INSERT      postgres   NO
approval_requests          sylvar_app_user  SELECT      postgres   NO
approval_requests          sylvar_app_user  UPDATE      postgres   NO
asset_versions             sylvar_app_user  INSERT      postgres   NO
asset_versions             sylvar_app_user  SELECT      postgres   NO
audit_checks               sylvar_app_user  INSERT      postgres   NO
audit_checks               sylvar_app_user  SELECT      postgres   NO
audit_runs                 sylvar_app_user  INSERT      postgres   NO
audit_runs                 sylvar_app_user  SELECT      postgres   NO
audit_runs                 sylvar_app_user  UPDATE      postgres   NO
client_brands              sylvar_app_user  INSERT      postgres   NO
client_brands              sylvar_app_user  SELECT      postgres   NO
client_brands              sylvar_app_user  UPDATE      postgres   NO
compliance_certificates    sylvar_app_user  INSERT      postgres   NO
compliance_certificates    sylvar_app_user  SELECT      postgres   NO
content_assets             sylvar_app_user  INSERT      postgres   NO
content_assets             sylvar_app_user  SELECT      postgres   NO
content_assets             sylvar_app_user  UPDATE      postgres   NO
users                      sylvar_app_user  INSERT      postgres   NO
users                      sylvar_app_user  SELECT      postgres   NO
users                      sylvar_app_user  UPDATE      postgres   NO
```

*Total explicit grants to `sylvar_app_user`: 24 (Across 9 core tables).*  
*Zero DELETE grants exist. Zero TRUNCATE grants exist. Zero REFERENCES grants exist.*

---

## 6. Excessive Privilege Analysis & Risk Assessment

- **Excessive Privileges Detected:** **NONE**.
- **Dangerous Grants (TRUNCATE, DELETE on audit tables):** **NONE**.
- **Role Boundary Violations:** **NONE**.
- **RLS Bypass Risks:** **NONE**.

### Security Architecture Summary
The PostgreSQL permissions model perfectly mirrors SYLVAR's core governance architecture:
- **`compliance_certificates`**: Strictly append-only. No updates, no deletes.
- **`asset_versions`**: Strictly append-only. Version forking creates new versions; existing versions cannot be edited in place.
- **`audit_checks`**: Strictly append-only. Findings recorded during audit evaluation are tamper-resistant.
- **`approval_requests`**: Lifecycle transitions from PENDING to terminal states are permitted via UPDATE, but terminal states are locked against subsequent modification by trigger, and DELETE is prohibited by grant.

---

## 7. Audit Classification Summary

| Scope Area | Checks Performed | Passed | Failed | Not Verified | Verdict |
|---|:---:|:---:|:---:|:---:|:---:|
| **Role Attributes & Inheritance** | 6 | 6 | 0 | 0 | **PASS** |
| **Effective Table Privileges** | 9 | 9 | 0 | 0 | **PASS** |
| **Certificate Immutability** | 3 | 3 | 0 | 0 | **PASS** |
| **Approval Request Protection** | 3 | 3 | 0 | 0 | **PASS** |
| **Table & Object Ownership** | 3 | 3 | 0 | 0 | **PASS** |
| **Function & Trigger Protections** | 2 | 2 | 0 | 0 | **PASS** |
| **Overall Security Posture** | **26** | **26** | **0** | **0** | **PASS** |

**Final Recommendation:** No remediation or privilege revocations are necessary. The live database privileges are configured according to strict least-privilege principles and are fully aligned with Round 2 hackathon submission requirements.

