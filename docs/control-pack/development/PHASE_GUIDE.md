# Phase Guide

See `../PHASE.md` for the authoritative phase gates and `../TASKS.md` for task IDs.

## Definition of Done for every task
- Acceptance criteria are met in the real implementation.
- Unit tests cover normal, boundary and failure cases.
- Authorization tests cover assigned and unassigned users, including Workspace Admin.
- No secrets or tenant data leak in logs/errors.
- Relevant integration tests pass against the real dependency or a faithful isolated test environment.
- Documentation and task status are updated with verification evidence.

## Phase gates
A phase may advance only when all its tasks are complete, its exit tests pass, no P0/P1 security issue remains, and the user accepts the phase report. A blocked prerequisite stops dependent tasks.
