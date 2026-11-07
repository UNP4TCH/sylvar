# SYLVAR (working name)
Monorepo: `backend/` (FastAPI), `frontend/` (React+Vite+TS), `supabase/` (migrations, empty until Phase 2).

Backend: `cd backend && pip install -e ".[dev]" && pytest -v && uvicorn app.main:app --reload`
Frontend: `cd frontend && npm install && npm run type-check && npm test && npm run dev`
Copy `.env.example` to `backend/.env`; copy `.env.frontend.example` to `frontend/.env`.

Status and next steps: `docs/PHASE1_HANDOFF.md`. Test figures: `docs/TEST_EVIDENCE.md`. Security notes: `docs/SECURITY_NOTES.md`. What you must do locally: `LOCAL_SETUP_AND_VERIFICATION.md`. Run backend commands from `backend/`.


## Current MVP content scope

The current audit execution path supports **TEXT assets only**. IMAGE and HYBRID asset
creation is rejected with `CONTENT_TYPE_NOT_SUPPORTED` until durable image upload,
private storage references, and visual audit input are implemented end to end. The
visual check is reported as `NOT_APPLICABLE` for text assets; it is never counted as
a successful visual inspection. Factual verification requires the live provider to
complete; offline heuristics are advisory and cannot authorize a compliance PASS.
