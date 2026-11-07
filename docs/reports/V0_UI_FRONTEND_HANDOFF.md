# SYLVAR — v0-inspired Vite frontend handoff

## Scope

This is an isolated frontend update based on the original SYLVAR Vite + React 18 application. The v0 Next.js project was used only as a visual reference. No Next.js runtime, routing, server actions, or Next.js environment conventions were introduced.

## UI changes

- Replaced the horizontal pipeline stepper with a persistent sidebar.
- Added real navigation for Overview, Living Memory, Governance Studio, and Review Queue.
- Added an Overview page using live frontend state already loaded by the existing API layer (active memory, approved/pending rules, review counts, latest audit verdict).
- Added a v0-inspired dark charcoal visual system with warm amber/orange accents, responsive sidebar behavior, typography, cards, inputs, and status styling.
- Updated the authentication screen to the v0-inspired split layout while retaining the existing Supabase sign-in/sign-up callbacks, error/notice handling, and busy state.

## Preserved

- React 18 + Vite + TypeScript + Tailwind + Zustand.
- Existing Supabase authentication and authenticated API client.
- Existing API paths/contracts and backend authorization boundaries.
- Existing workspace/client creation, renaming, selection, membership and team-scoping flows.
- Existing guideline upload, extraction, candidate review and memory activation workflow.
- Existing content authoring, audit, remediation/diff, review decision, separation-of-duties and certificate workflows.
- Existing environment variable names and frontend `.env` / `.env.example` files.

## Environment contract

The existing frontend variables are unchanged:

- `VITE_API_BASE_URL`
- `VITE_SUPABASE_URL`
- `VITE_SUPABASE_ANON_KEY`

The populated `.env` file is retained in this local handoff because the project owner requested configuration continuity. Treat it as sensitive. Do not commit it or send it to public repositories. Only browser-safe Supabase URL/anon key and API URL belong in Vite client configuration. Never put service-role keys, Gemini keys, Postmark tokens, database credentials, or backend secrets in `VITE_*` variables.

## Verification performed in this environment

- `npm run type-check`: PASS (TypeScript no errors).
- Tailwind CSS compilation via `./node_modules/.bin/tailwindcss -i ./src/index.css -o /tmp/sylvar-ui-check.css --minify`: PASS.
- `npm test -- --run`: BLOCKED before test execution because the supplied `node_modules` lacks the Linux optional package `@rollup/rollup-linux-x64-gnu` required by Rollup/Vitest.
- `npm run build`: BLOCKED by the same missing Rollup Linux optional dependency. TypeScript stage of the build command passed before Vite launched.
- Attempted `npm ci --include=optional`; package installation did not complete within the available network timeout. Offline install also could not complete because some package tarballs (including Zustand) were not cached.
- No live Supabase, backend, Gemini, Postmark, or real-browser verification is claimed.

## Run locally

From `frontend/` on the developer's Windows machine:

```powershell
npm install
npm run type-check
npm test -- --run
npm run build
npm run dev
```

Use the existing local `.env`. If dependencies were copied from another operating system, remove `node_modules` and reinstall dependencies on the target OS using the existing `package-lock.json`.

## Integration note for Antigravity

Use this frontend as the visual/interaction update, but merge it into the latest canonical SYLVAR source rather than replacing backend or database code. Preserve the current API/auth implementation and compare the frontend `.env.example`, package manifest, and lockfile before resolving any conflicts. Do not copy `node_modules` or `dist` into the main project. Do not introduce Next.js or simulated DemoDashboard workflows into production.
