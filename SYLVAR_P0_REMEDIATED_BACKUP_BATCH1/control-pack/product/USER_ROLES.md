# USER_ROLES.md — User Roles & Authority Invariants
**Status:** Invariant (Task 5 v1.6 & Master PRD v1.0.0)  

---

## 1. The Three Approved Roles
The system supports exactly three roles. No auxiliary roles exist in the MVP.

### 1.1 Workspace Admin (`WORKSPACE_ADMIN`)
* **Scope:** Agency Workspace level.
* **Privileges:** Workspace settings, billing, member invites, role changes, client brand provisioning, client assignments.
* **Authority Limits:** Does not have ambient access to client assets without being explicitly assigned or selecting an explicit client context.

### 1.2 Brand Manager (`BRAND_MANAGER`)
* **Scope:** Client Brand level (assigned).
* **Privileges:** Guideline document upload, candidate rule review/editing, knowledge approval, memory version publication, review queue inspection, advisory warning acknowledgment, final asset approval/rejection.
* **Authority Limits:** Cannot modify workspace-level billing or seats; cannot access unassigned client brands.

### 1.3 Content Creator (`CONTENT_CREATOR`)
* **Scope:** Client Brand level (assigned).
* **Privileges:** Collateral draft submission, pre-flight audit execution, scorecard inspection, AI correction generation, fix acceptance, submission for review.
* **Authority Limits:** Cannot approve assets, cannot acknowledge advisories on behalf of management, cannot modify or activate brand memory rules.

---

## 2. Independent Client Scoping Rule
* Workspace membership establishes an active account in an agency.
* Client brand access requires an active record in `client_memberships`.
* Removing a user from `agency_workspaces` immediately terminates access to all client brands.
* Removing a user from `client_memberships` revokes access only to that specific client brand.
