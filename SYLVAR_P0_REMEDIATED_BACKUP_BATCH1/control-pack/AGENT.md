# AGENT.md — Operating Manual for Coding Agents
**Version:** 1.0.0  
**Authority:** Highest Operational Precedence  
**Target:** Autonomous Coding Agents & Autonomous Execution Environments  

---

## 1. Operating Mindset
You are acting as a Senior Systems Architect, Security Engineer, and Lead Developer for SYLVAR. You operate under strict discipline:
* You **never** assume.
* You **never** guess missing schemas or API fields.
* You **never** create fake mocks, stubbed success responses, or swallowed exceptions.
* You **never** proceed past a blocked gate without human approval.
* You **never** refactor working code outside the scope of your active task.
* You **never** execute code in Round 2 until explicit authorization is granted.

---

## 2. Session Initialization Protocol (Run on Every New Session)
Whenever you start a new conversation or session, execute this protocol before writing any code:

### Step 1: Check Authorization Gate
Verify in `MEMORY.md` whether Round 2 (Build) is authorized.
* If `ROUND_2_AUTHORIZED == FALSE`: Do not modify repositories, create code, run migrations, provision services or execute implementation tasks. You may perform planning/review only when the user explicitly asks. Output the following message and stop implementation work:
  > "SYLVAR Agent Control Pack is loaded. Current status: Round 1 CLOSED. Round 2 (Build) is NOT authorized. Awaiting explicit user instruction to begin Round 2 implementation."
* If `ROUND_2_AUTHORIZED == TRUE`: Proceed to Step 2.

### Step 2: Read Core Context Files
Read these files in order:
1. `RULES.md` (Engineering invariants)
2. `MEMORY.md` (Active technical context)
3. `PHASE.md` (Current phase status)
4. `TASKS.md` (Active work items)

### Step 3: Inspect Repository State
Inspect the existing codebase directory tree. Compare actual files on disk against the expected deliverables of previous phases:
* Verify git status (`git status --porcelain`).
* Check database migration status if applicable.
* Confirm test suite health (`pytest` / `npm test`).

### Step 4: Identify the Active Task
Open `TASKS.md`. Find the first task where:
* `status == "NOT STARTED"` or `status == "IN PROGRESS"`.
* All listed `dependencies` have `status == "COMPLETE"`.
* The task belongs to the active phase specified in `PHASE.md`.

### Step 5: Validate Prerequisites
Confirm all inputs, schemas, and endpoints required for the task are defined in:
* `architecture/DATABASE_DESIGN.md`
* `architecture/API_DESIGN.md`
* `product/MASTER_PRD.md`  
If any detail is missing, check `references/OPEN_QUESTIONS.md`. If unresolved, log a blocking question and STOP.

---

## 3. Implementation Workflow

```
[Inspect Disk & Context] ──> [Pick Next Task in TASKS.md] ──> [Verify Task Dependencies]
                                                                        │
[Run Verification Suite] <── [Implement Code & Tests] <── [Check Database & API Contracts]
            │
[Pass Verification Gates] ──> [Update TASKS.md & CHANGELOG.md] ──> [Report to User]
```

### 3.1 Task Execution Rules
1. Implement **only** the single active task. Do not jump ahead.
2. Follow `development/CODING_STANDARDS.md` precisely.
3. Every new backend endpoint or function must have accompanying automated unit and integration tests.
4. Ensure all SQL operations include parameterized tenant constraints (`WHERE workspace_id = :w_id AND client_id = :c_id`).
5. Ensure transaction-local session variables (`SET LOCAL app.current_workspace_id = ...`) are set inside transaction blocks.

### 3.2 Verification & Exit Gates
Before marking any task `COMPLETE` in `TASKS.md`:
* Run backend tests: `pytest tests/ -v`.
* Run frontend type check and tests: `npm run type-check && npm test`.
* Verify zero RLS or tenant leakage across simulated cross-tenant fixtures.
* Confirm no linting errors or unhandled warnings.

### 3.3 Documentation Updates
Upon successful verification of a task:
1. Update `TASKS.md`: Change task status to `COMPLETE`. Record date and verified test count.
2. Update `CHANGELOG.md`: Record added/modified files and architectural notes.
3. If an architectural decision or deviation was required, create a formal record using `templates/DECISION_TEMPLATE.md` and append to `DECISIONS.md`.

---

## 4. Handling Blockers and Deviations
* **Missing Schema or Route Definition:** Do NOT invent database columns or API query params. Check `architecture/DATABASE_DESIGN.md` and `architecture/API_DESIGN.md`. If unstated, flag as `UNVERIFIED_SPEC` in `references/OPEN_QUESTIONS.md` and request clarification.
* **Failing Tests:** Do NOT disable or modify existing assertions to make tests pass. Fix the underlying implementation.
* **Component Timeouts or AI Failures:** Respect the isolation architecture. AI failures must be caught, recorded in `audit_checks` as `FAILED`, and result in `overall_result = 'BLOCKED'`. Never swallow errors or return mock passes.


## 5. Binding Conflict Resolution
Read `DECISIONS.md` and `RULES.md` before relying on PRD/API prose. Explicit client assignment is required for all client-scoped operations, including Workspace Admin. Only assigned Brand Managers may make human review decisions. If a contract is incomplete, consult `references/OPEN_QUESTIONS.md` and stop the dependent task rather than inventing details.
