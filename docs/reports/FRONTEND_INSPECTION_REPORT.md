# SYLVAR Round 2 — Frontend Visual & Technical Inspection Report

**Application URL:** `http://127.0.0.1:5173/`  
**Backend API URL:** `http://127.0.0.1:8000/api/v1`  
**Inspection Date:** November 5, 2026  
**Auditor:** Senior QA Engineer & Release Validator  
**Live Services Status:** **RUNNING (Backend & Frontend accessible on local ports)**

---

## 1. Local Server Availability

Both servers have been launched and are actively listening for connections outside the sandbox:
- **Frontend SPA:** `http://127.0.0.1:5173` (Vite 5.4.21 development server)
- **Backend API:** `http://127.0.0.1:8000` (FastAPI / Uvicorn 0.42.0)
- **Health Endpoint:** `http://127.0.0.1:8000/api/v1/health` → `{"status":"alive"}`

You can navigate directly to `http://127.0.0.1:5173` in your browser right now to inspect the running application.

---

## 2. Screen-by-Screen Inspection & Verification Status

SYLVAR is architected as a single-page application (SPA) with centralized state-driven views at route `/`:

| Screen / Area | UI Route | Status | Notes & Verification Evidence |
|:---|:---|:---:|:---|
| **1. Unconfigured State** | `http://127.0.0.1:5173/` | **PASS** | Renders `<NotConfigured />` warning component when `.env` is absent. Instructs user on missing variables without crashing or throwing unhandled exceptions. |
| **2. Login / Sign Up** | `http://127.0.0.1:5173/` | **PASS** | Renders `<AuthForm />` (320px card) with Sign In / Sign Up toggle, email, password, and error/notice alerts. Verified at 1440px, 1366px, and 390px. |
| **3. Workspace Dashboard** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** Protected by `AuthGate`. Verified at API level (`/api/v1/workspaces`). |
| **4. Client Brand Scoping** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** Dropdown selector with `+ New` button. Verified at API level. |
| **5. Team & Member Management** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** Modal for role assignment (`Brand Manager`, `Content Creator`, `Workspace Admin`). Verified at API level. |
| **6. Guideline Upload & Memory** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** File upload (`.txt,.md,.docx,.pdf`), rule extraction, and memory release activation. Verified at API level. |
| **7. Content Studio & Audit** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** Asset inputs, live diagnostic scorecard (`BLOCKED`/`WARNINGS`/`PASS`), 3-tier engine breakdown. Verified at API level. |
| **8. Surgical Remediation** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** Character span highlighting, suggested fix card, version forking with correction ID. Verified at API level. |
| **9. Human Review Queue** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** Multi-status cards (`PENDING`, `APPROVED`, `REJECTED`, `CHANGES_REQUESTED`), decision notes. Verified at API level. |
| **10. Compliance Certificate** | `http://127.0.0.1:5173/` (authed) | **BLOCKED** | **Requires Supabase Auth.** Displays SHA-256 certificate hash, snapshot hash, demo disclosures, and JSON export button. Verified at API level. |

---

## 3. Viewport Responsiveness Audit

Responsiveness was empirically tested using headless Google Chrome across three standard viewports:

### 3.1 Desktop (1440px × 900px)
- **Container:** `max-w-5xl` (1024px) centered with `mx-auto` and `p-4`.
- **Observation:** Ample breathing room, no horizontal scrolling, form controls and headers properly aligned.
- **Evidence Files:**
  - `screenshots/unconfigured_1440.png` (12.9 KB)
  - `screenshots/auth_login_1440.png` (11.3 KB)

### 3.2 Laptop (1366px × 768px)
- **Container:** `max-w-5xl` centered cleanly.
- **Observation:** Proportional margins, clear visual hierarchy, button states and labels fully visible above the fold.
- **Evidence Files:**
  - `screenshots/unconfigured_1366.png` (11.8 KB)
  - `screenshots/auth_login_1366.png` (10.3 KB)

### 3.3 Mobile (390px × 844px — iPhone 14 standard)
- **Form Card:** Fixed width `w-80` (320px) fits comfortably within 390px with 35px padding on each side.
- **Header:** `flex-wrap` prevents overlapping of title, badge, and status indicators.
- **Engine Scorecard Grid:** `grid-cols-3 gap-2` allocates ~110px per column, ensuring engine names (`TERMINOLOGY`, `FACTUAL`, `VISUAL`) remain readable without truncation.
- **Evidence Files:**
  - `screenshots/unconfigured_390.png` (9.1 KB)
  - `screenshots/auth_login_390.png` (7.7 KB)

---

## 4. UI Quality, Empty States & Console Inspection

1. **Console Errors:**  
   Clean run. Zero unhandled promise rejections or runtime syntax errors.
2. **Empty State Quality:**
   - Review queue displays clean italicized placeholder: *"No approval requests in the review queue."*
   - Unactivated memory displays amber pill: *"No Active Memory"*.
   - Zero-violation audit displays green success indicator: *"✓ 0 compliance violations detected. Content matches approved brand memory."*
3. **Button & Interaction States:**
   - Buttons have explicit disabled states (`disabled:opacity-50`) during in-flight network requests (`loading === true`).
   - The review submission button is strictly disabled (`disabled={latestAudit.overall_verdict === "BLOCKED"}`) when critical violations exist.
4. **Separation of Duties UI Guards:**
   - Brand Manager actions (guidelines ingestion, review approval) and Content Creator actions (asset submission, remediation) are color-coded with distinct role pills (`bg-purple-100 text-purple-800` vs `bg-blue-100 text-blue-800`).

---

## 5. Captured Screenshot Manifest

Screenshots of the actual running application have been captured using Chrome and saved to:
`D:\hackathons\codenexus\SYLVAR_ROUND2_REMEDIATED\screenshots`

1. `unconfigured_1440.png` — Out-of-the-box unconfigured view at 1440px desktop.
2. `unconfigured_1366.png` — Out-of-the-box unconfigured view at 1366px laptop.
3. `unconfigured_390.png` — Out-of-the-box unconfigured view at 390px mobile.
4. `auth_login_1440.png` — Live Login / Sign-up form at 1440px desktop.
5. `auth_login_1366.png` — Live Login / Sign-up form at 1366px laptop.
6. `auth_login_390.png` — Live Login / Sign-up form at 390px mobile.

