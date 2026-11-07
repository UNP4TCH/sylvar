# SYLVAR — MASTER PRODUCT REQUIREMENTS DOCUMENT
**Document Title:** Master Product Requirements Document (PRD)  
**Product Identity:** SYLVAR — The Pre-Publication CI/CD for Brand Integrity
**Naming Status:** Working name; trademark, domain, and software-name clearance pending.
**Challenge Provider:** Inkloom AI (problem-statement provider; not the product owner or product name).  
**Document Version:** 1.0.0 (Master Baseline — Single Source of Truth)  
**Date:** November 2026  
**Status:** PLANNING BASELINE — CONTROL-PACK FREEZE CANDIDATE; ROUND 2 NOT STARTED; IMPLEMENTATION AUTHORIZATION PENDING  
**Author:** Senior Product Architect, Technical Product Manager & Software Systems Analyst  
**Target Audience:** Hackathon Development Team, AI Coding Agents, Architecture Reviewers  

---

## 1. Document Metadata and Version

### 1.1 Metadata
* **Product Name:** SYLVAR (working name; clearance pending)
* **Internal Code Identifier:** SYLVAR-CORE
* **Positioning:** The Pre-Publication CI/CD for Brand Integrity
* **Document Status:** Master Baseline Specification (Frozen for Round 2 Build)
* **Creation Date:** November 2, 2026
* **Target Release:** MVP (Round 2 Build Sprint)
* **Architectural Style:** Modular Monolith (FastAPI + Supabase PostgreSQL)
* **Primary Constraints:** Exactly 3 Roles, Direct PostgreSQL Access with Least-Privilege Application Role (`sylvar_app_user`), Defense-in-Depth RLS, Pinned Immutable Memory Snapshots, 8 GB RAM / Intel i3-1215U Local Dev Environment, Zero Unnecessary Infrastructure.

### 1.2 Version Control History
| Version | Date | Author / Role | Status | Description of Change |
| :--- | :--- | :--- | :--- | :--- |
| **v0.1.0** | 2026-10-15 | System Analyst | Draft | Initial problem framing, user persona hypotheses, and functional scope. |
| **v0.5.0** | 2026-10-22 | Product Architect | Revision | Harmonization of 3-role authorization, living brand memory models, and audit states. |
| **v0.9.0** | 2026-10-29 | AppSec & Backend Lead | Review | Alignment with Task 3 Data Arch v1.5, Task 4 AI v1.5, and Task 5 Security v1.6. |
| **v1.0.0** | 2026-11-02 | Lead Product Architect | Approved Master | Complete consolidation of all 32 required sections into the single source of truth for Round 2. |

### 1.3 Precedence and Hierarchy of Truth
In the event of ambiguity across documentation artifacts, the following strict hierarchy of truth governs implementation:
1. **This Master PRD (v1.0.0):** Authoritative over all functional workflows, business rules, lifecycle state machines, role permissions, and scope boundaries.
2. **Data Architecture Specification (Task 3 v1.5):** Authoritative over PostgreSQL 25-table relational schema definitions, composite foreign keys, columns, types, and constraints.
3. **Security, Authentication & API Design Specification (Task 5 v1.6):** Authoritative over endpoint contracts, DTO schemas, HTTP status codes, error problem details (RFC 9457), and JWT verification mechanics.
4. **AI & Visual Intelligence Architecture Specification (Task 4 v1.5):** Authoritative over mathematical formulations (sRGB to linear-light, CIEDE2000 $\Delta E_{00}$), prompt templates, NLI verification logic, and normalization rules.
5. **System Architecture Specification (Task 2 v1.2):** Authoritative over high-level component topologies and hosting infrastructure.

---

## 2. Executive Summary

SYLVAR is an intelligent, multi-tenant brand governance platform engineered specifically for mid-sized creative and marketing agencies that produce collateral across multiple client brands simultaneously. 

In distributed agency workflows, creative teams constantly alternate between client accounts with distinct brand manuals, prohibited competitors, approved factual claims, and visual color guidelines. This rapid context switching, compounded by the widespread use of ungrounded generative AI drafting tools, creates a severe operational control gap: unverified promotional claims, deprecated terminology, off-brand color palettes, and accessibility failures routinely bypass manual reviews and reach client-facing or public channels.

SYLVAR addresses this crisis by establishing **"The Pre-Publication CI/CD for Brand Integrity."** Borrowing the proven discipline of continuous integration and continuous delivery from software engineering, SYLVAR acts as an automated, deterministic-first quality gate that intercepts marketing copy and visual graphics before publication. Submitted drafts are systematically audited against **Living Brand Memory**—an active, versioned, and human-approved knowledge repository compiled directly from client brand manuals.

The platform provides deterministic lexical scanning, model-assisted atomic factual claim extraction, tri-state natural language inference (`SUPPORTED`, `CONTRADICTED`, `UNVERIFIED`), linear-light visual palette analysis ($\Delta E_{00}$), bounded intent-preserving corrections, and a human-in-the-loop sign-off state machine. Crucially, SYLVAR enforces a **Zero-Action AI Boundary**: AI models analyze, verify, and suggest, but humans retain exclusive authority over approving collateral or activating brand knowledge.

---

## 3. Product Vision and Positioning

### 3.1 Product Vision Statement
To establish the universal pre-publication verification layer for marketing operations, ensuring that every published creative asset is factually grounded, terminologically compliant, and visually faithful to verified brand guidelines.

### 3.2 Product Positioning
* **Category:** Pre-Publication Brand Governance & Content Integrity Platform.
* **Core Positioning:** The Pre-Publication CI/CD for Brand Integrity.
* **What SYLVAR Is:** An automated validation pipeline that parses marketing copy and graphics, audits them against immutable snapshots of verified client knowledge, surfaces evidence-backed diagnostics, and facilitates structured human review.
* **What SYLVAR Is NOT:** 
  * It is **NOT** a generic AI writing chatbot (it does not generate long-form marketing prose from scratch).
  * It is **NOT** an unconstrained marketing generation tool (it restricts, audits, and corrects content).
  * It is **NOT** a full Digital Asset Management (DAM) system (it does not handle raw video storage or distribution).

### 3.3 Core Strategic Tenets
1. **Deterministic-First Priority:** Deterministic algorithms handle lexical matching and color math in native Python, using deterministic algorithms for baseline checks; these checks do not invoke an LLM, but latency must be measured and no blanket zero-error or performance guarantee is implied.
2. **Epistemic Honesty:** Absence of evidence is not proof of contradiction. Factual claims resolve into `SUPPORTED`, `CONTRADICTED`, or `UNVERIFIED`. The system never labels unverified claims as false.
3. **Snapshot-Pinned Historical Auditability:** Every audit run is permanently pinned to an immutable memory snapshot hash. Changes to brand guidelines take effect strictly for future audits, ensuring historical compliance records remain reproducible.
4. **Surgical, Intent-Preserving Remediation:** Proposed AI corrections modify only non-compliant token spans, strictly minimizing edit distance while preserving authorial voice.
5. **Zero-Trust Multi-Tenancy:** Workspaces and client brands are isolated at the database engine level through composite keys, query parameters, and Row-Level Security.

---

## 4. Problem Statement

### 4.1 The Agency Context-Switching Breakdown
Creative and marketing agencies managing 10 to 50 client retainers face an inherent structural challenge: copywriters, graphic designers, and account managers switch between disparate client brand identities daily. A creator may write highly technical, compliance-heavy white papers for an enterprise B2B cloud client in the morning, then switch to playful, slang-infused social posts for a direct-to-consumer beverage brand in the afternoon.

This constant context switching leads to:
* **Brand Contamination:** Terminology, tone rules, or competitor references from Client A inadvertently bleed into collateral for Client B.
* **Factual Hallucination & Drift:** Specifications, SLA metrics, uptime figures, and partner certifications are quoted from memory or obsolete desktop files.
* **Visual Palette Drift:** Graphic designers accidentally export graphics with uncalibrated display colors, leading to noticeable color shifts that breach brand guidelines.
* **Review Bottlenecks:** Senior account directors spend up to 40% of their billable hours manually cross-referencing copy against 80-page static PDF brand manuals.

### 4.2 Passive Brand Guidelines Failure
Enterprises invest tens of thousands of dollars developing comprehensive brand guideline documents. However, these guidelines exist as passive, static PDFs stored in fragmented cloud drives. Creatives do not read or search 80-page documents under tight deadlines. Furthermore, when guidelines are updated, outdated copies persist on local desktops, causing knowledge decay across the agency.

### 4.3 Generative AI Content Risks
The widespread adoption of generative AI tools (ChatGPT, Claude, Jasper) has amplified drafting velocity while dramatically increasing brand compliance risks. Generative models produce convincing, articulate prose that frequently invents nonexistent product capabilities, fabricates legal guarantees, or uses unapproved superlatives.

---

## 5. Target Users and Personas

SYLVAR operates on an **exact three-role model** at the agency workspace level, supplemented by client-brand assignment scoping.

```
Agency Workspace Tenant
 ├── Workspace Admin (Full Workspace Access & Tenant Configuration)
 ├── Brand Manager (Scoped to Assigned Client Brands; Knowledge Gatekeeper & Review Authority)
 └── Content Creator (Scoped to Assigned Client Brands; Collateral Submissions & Audit Remediation)
```

### 5.1 Persona 1: Workspace Admin (`WORKSPACE_ADMIN`)
* **Archetype:** Agency Operations Director / Managing Partner.
* **Responsibilities:** Agency workspace setup, seat provisioning, team onboarding, client brand provisioning, and role assignment.
* **Needs:** Complete administrative control over workspace security, visibility into seat usage, and tenant-level access isolation across clients.
* **Pain Points:** Fear of cross-client data contamination leading to client contract termination; high unbillable hours spent resolving client escalations over compliance errors.

### 5.2 Persona 2: Brand Manager (`BRAND_MANAGER`)
* **Archetype:** Account Director / Senior Brand Strategist.
* **Responsibilities:** Maintaining verified client brand knowledge, ingesting client guideline manuals, reviewing staged candidate rules, publishing Living Brand Memory releases, and rendering final approval/rejection decisions on content.
* **Needs:** An authoritative, centralized gatekeeper tool to ensure all agency output complies with client briefs before external delivery; fast review queues with explainable findings.
* **Pain Points:** Reviewing dozens of drafts manually under severe time pressure; tracking conflicting guideline rules across successive client rebrands.

### 5.3 Persona 3: Content Creator (`CONTENT_CREATOR`)
* **Archetype:** Copywriter / Content Specialist / Visual Designer.
* **Responsibilities:** Drafting marketing copy, social ad collateral, and visual graphics; running pre-flight audits; applying surgical corrections.
* **Needs:** Fast, automated feedback during drafting without waiting days for editorial review; clear citations explaining why a term or claim was flagged; one-click intent-preserving rewrites.
* **Pain Points:** Memorizing dozens of distinct client terminology blacklists; vague, subjective rejection feedback from managers (e.g., "doesn't feel on-brand").

---

## 6. User Pain Points and Use Cases

### 6.1 Pain Point to Solution Mapping
| Pain Point | SYLVAR Architectural Solution |
| :--- | :--- |
| Creators mix up rules across accounts | Mandatory client-context selection barrier with strict server-side dual-tenant authorization. |
| AI tools invent plausible but false claims | Atomic claim extraction evaluated against approved factual memory via cross-encoder NLI entailment. |
| Rules buried in 80-page static PDFs are ignored | Living Brand Memory: guideline parsing into machine-checkable rules with exact section anchors. |
| Reviewers provide vague, subjective feedback | Deterministic diagnostic finding cards citing exact rule revisions and approved source quotes. |
| Editors completely rewrite non-compliant copy | Bounded, minimal-edit rewriting that swaps only non-compliant spans while preserving voice. |
| Graphics exported with incorrect accent colors | Pure-Python Pillow/NumPy CIEDE2000 color comparison against approved brand swatches. |

### 6.2 Primary Use Cases

#### UC-1: Brand Guideline Ingestion & Living Memory Publication
* **Actor:** Brand Manager.
* **Flow:** Brand Manager uploads `Client_Guidelines_2026.docx`. The ingestion engine validates file integrity, strips path traversal risks, and parses structured text sections. The Gemini extraction pipeline identifies candidate terminology, factual assertions, and hex swatches into an unapproved staging queue (`extracted_candidates`). The Brand Manager reviews candidates, modifies wording, approves 28 rules, rejects 2 duplicates, and publishes Memory Version v1.0. The system commits an immutable JSONB snapshot with a SHA-256 hash and updates `client_brands.active_memory_version_id`.

#### UC-2: Pre-Flight Content Submission & Multi-Modal Auditing
* **Actor:** Content Creator.
* **Flow:** Creator confirms active client context, inputs a 450-word ad copy draft, uploads a promotional banner PNG, and clicks "Run Pre-Flight Audit." The backend initiates an asynchronous audit run (`HTTP 202 Accepted`) pinned to active Memory v1.0. The audit orchestrator executes three concurrent branches: (1) Regex scans text in 8ms, detecting a prohibited competitor term; (2) Factual engine segments sentences and calls Gemini NLI, identifying a contradicted SLA claim; (3) Visual engine clusters colors and calculates $\Delta E_{00}$, flagging an off-palette accent swatch. Overall outcome resolves to `BLOCKED` (2 blocking, 1 advisory).

#### UC-3: Interactive Surgical Remediation & Version Forking
* **Actor:** Content Creator.
* **Flow:** Creator reviews diagnostic findings. On the contradicted SLA claim card, creator clicks "Generate Fix." The model generates a minimal-edit rewrite replacing only the contradicted span. The UI renders a visual side-by-side diff. Creator accepts the fix. The system forks a new immutable content version (v1.1) linked via `created_from_correction_id`, preserves original v1.0, and triggers an automated delta re-audit. Factual claim now resolves to `SUPPORTED`. Overall outcome transitions to `WARNINGS` (0 blocking, 1 advisory).

#### UC-4: Human Review & Exportable Compliance Certification
* **Actor:** Brand Manager.
* **Flow:** Creator submits v1.1 for review. Asset enters Brand Manager review queue (`READY_FOR_REVIEW` $
ightarrow$ `UNDER_REVIEW`). Brand Manager inspects audit findings, reviews creator's note regarding the visual accent warning, checks the advisory acknowledgment box, and clicks "Approve Deliverable." Asset transitions to `APPROVED`. System persists a permanent, tamper-evident compliance audit record in `audit_history` and generates a downloadable JSON/PDF compliance manifest.

---

## 7. Product Goals and Measurable Success Criteria

### 7.1 Quantitative Engineering Targets
* **Audit Execution Latency:** Target complete pre-flight audit execution (terminology regex + NLI factual claim verification + image color extraction) within $\le 3.5	ext{ seconds}$ for standard drafts ($\le 800	ext{ words}$, image $\le 5	ext{ MB}$) on normal cloud network connections.
* **Deterministic Terminology Precision:** $100\%$ precision on configured exact-match prohibited terminology patterns and mandatory trademark suffixes.
* **Zero Silent Factual Approvals:** $100\%$ of detected contradictory or unsupported factual claims must be flagged as either `CONTRADICTED` or `UNVERIFIED`; zero unverified claims may be automatically marked as `SUPPORTED`.
* **Minimal Token Distortion:** Bounded correction prompts must maintain a Levenshtein edit distance ratio $\le 0.25$ relative to the surrounding paragraph context.
* **Zero Tenant Cross-Contamination:** $100\%$ isolation of client guidelines, rules, factual assertions, and audit histories across tenant boundaries, verified via continuous automated cross-tenant security integration tests.

### 7.2 Business Impact Metrics
* **Review Cycle Turnaround:** Decrease internal agency review turnaround times by at least $50\%$ within 30 days of deployment.
* **Client Deliverable Rejections:** Reduce client-initiated deliverable rejections due to brand guideline violations to zero.
* **Audit Traceability:** $100\%$ of approved campaign deliverables possess a verifiable, exportable audit manifest linked to an immutable brand memory snapshot.

---

## 8. Non-Goals and Scope Boundaries

### 8.1 Explicit Non-Goals for the Core MVP
* **NO Autonomous Publishing:** SYLVAR will never directly publish content to social platforms, CMS systems (WordPress, Webflow), or ad managers. Workflows strictly conclude with human approval and exportable audit records.
* **NO Full Digital Asset Management (DAM):** The platform is not an enterprise asset warehouse. It does not support nested folder trees, video transcoding, or creative rights management.
* **NO Video or Audio Analysis:** Video frame-by-frame analysis and audio transcription are strictly excluded from the MVP.
* **NO Scanned PDF OCR:** The ingestion engine parses digital text layouts using `pdfplumber` and `python-docx`. It does not execute optical character recognition on scanned paper manuals.
* **NO Custom Model Training / Fine-Tuning:** The platform relies on hosted foundation models (Google Gemini API) and deterministic Python algorithms.
* **NO Vector Databases:** The MVP implements a PostgreSQL-first architecture. Standard snapshots ($\le 100	ext{ facts}$) are injected directly into the Gemini context window; larger snapshots utilize PostgreSQL full-text search with cover-density ranking (`ts_rank_cd`).

### 8.2 Scope Boundaries Matrix
| Capability Domain | Core MVP Scope (Round 2 Build) | Round 2 Committed Enhancements | Future Scope (Post-Hackathon) |
| :--- | :--- | :--- | :--- |
| **User Roles** | Exactly 3 roles (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`). | Refined multi-creator assignment queues. | Enterprise SAML/SSO (Okta, Azure AD), SCIM. |
| **Knowledge Engine** | Structured rule tables, staging queue, JSONB snapshots, manual activation. | **Automated Guideline Contradiction Scanner** (Pairwise NLI conflict linter). | Autonomous multi-document reconciliation graphs. |
| **Text Auditing** | Regex terminology linter, atomic claim extraction, tri-state NLI verification. | Enhanced contextual exception evaluation. | Continuous semantic brand voice vector scoring. |
| **Visual Auditing** | Pillow/NumPy dominant color extraction, CIEDE2000 ($\Delta E_{00}$) distance, advisory warnings. | **Multimodal WCAG 2.1 Contrast Engine** (Relative luminance calculations on image text). | Logo clear-space bounding box detection. |
| **Analytics** | Relational audit history, asset version logs, exportable JSON compliance manifests. | **Longitudinal Mistake Intelligence** (SQL aggregation & root-cause clustering). | Predictive compliance risk forecasting dashboards. |
| **Integrations** | Standalone responsive React 18 SPA, RESTful FastAPI backend. | Exportable JSON/PDF compliance certificates. | Headless Model Context Protocol (MCP) server, Figma/Google Docs plugins. |

---

## 9. User Roles and Permission Matrix

SYLVAR enforces an **exact three-role model** at the agency workspace level, augmented by explicit client-brand assignment scoping.

### 9.1 Role Definitions
1. **Workspace Admin (`WORKSPACE_ADMIN`):** Agency executive or operations lead. Manages agency workspace configuration, billing, team member invitations, role assignments, and client brand provisioning. Manages workspace-level operations and provisions client brands. Client-scoped operations require an active explicit `client_memberships` assignment; workspace-admin status does not bypass client assignment.
2. **Brand Manager (`BRAND_MANAGER`):** Senior account lead or creative director. Manages assigned client brand spaces. Ingests guideline documents, edits candidate rules, approves and publishes Living Brand Memory releases, inspects submitted assets, reviews advisory warnings, and makes final approval/rejection decisions.
3. **Content Creator (`CONTENT_CREATOR`):** Copywriter, visual designer, or agency contractor. Accesses assigned client brand spaces. Submits draft copy and visual graphics, triggers pre-flight audits, reviews diagnostic scorecards, accepts or dismisses surgical AI rewrites, and submits cleared assets for Brand Manager review. Restricted from modifying brand memory or approving deliverables.

### 9.2 Complete RBAC Permission Matrix
| Functional Capability / API Scope | Workspace Admin | Brand Manager (Assigned) | Content Creator (Assigned) | Unassigned Workspace Member |
| :--- | :---: | :---: | :---: | :---: |
| **Manage Agency Workspace Settings** | Allowed | Denied | Denied | Denied |
| **Invite / Remove Workspace Members** | Allowed | Denied | Denied | Denied |
| **Update User Workspace Roles** | Allowed | Denied | Denied | Denied |
| **Create New Client Brand Spaces** | Allowed | Denied | Denied | Denied |
| **Assign Users to Client Brands** | Allowed | Denied | Denied | Denied |
| **Upload Guideline Documents** | Allowed | Allowed | Denied | Denied |
| **Review / Edit Staged Candidate Rules** | Allowed | Allowed | Denied | Denied |
| **Approve & Publish Brand Memory Versions** | Allowed | Allowed | Denied | Denied |
| **View Active Brand Guidelines & Swatches** | Allowed | Allowed | Allowed | Denied |
| **Submit Content Collateral (Text/Images)** | Allowed | Allowed | Allowed | Denied |
| **Trigger Pre-Flight Content Audits** | Allowed | Allowed | Allowed | Denied |
| **View Diagnostic Scorecards & Lineage** | Allowed | Allowed | Allowed | Denied |
| **Request / Apply AI Correction Suggestions** | Allowed | Allowed | Allowed | Denied |
| **Submit Asset for Human Review** | Allowed | Allowed | Allowed | Denied |
| **Acknowledge Advisory Warnings** | Allowed | Allowed | Denied | Denied |
| **Approve / Reject Asset Deliverable** | Allowed | Allowed | Denied | Denied |
| **Export Verifiable Audit Compliance Records** | Allowed | Allowed | Allowed | Denied |
| **View Longitudinal Mistake Analytics** | Allowed | Allowed | Denied | Denied |

---

## 10. Functional Requirements

### 10.1 Workspace & Client Tenancy Management
* **FR-001 (Workspace Provisioning):** The system shall allow an authenticated user to create an isolated agency workspace, automatically assigning the creator the `WORKSPACE_ADMIN` role.
* **FR-002 (Client Brand Partitioning):** The system shall permit a `WORKSPACE_ADMIN` to provision multiple isolated client brand spaces within their agency workspace, partitioned by composite foreign keys.
* **FR-003 (Member Invitations):** The system shall permit a `WORKSPACE_ADMIN` to invite team members via email and assign them one of the three approved roles (`WORKSPACE_ADMIN`, `BRAND_MANAGER`, `CONTENT_CREATOR`).
* **FR-004 (Client Assignment Scoping):** The system shall require explicit assignment of `BRAND_MANAGER` and `CONTENT_CREATOR` users to specific client brands before access is granted. Unassigned members receive `HTTP 403 Forbidden`.
* **FR-005 (Real-Time Membership Revocation):** The system shall permit a `WORKSPACE_ADMIN` to revoke workspace membership (`status = 'REVOKED'`, `revoked_at = NOW()`), immediately terminating authorization on subsequent API requests regardless of JWT expiration.
* **FR-006 (Client Assignment Revocation):** The system shall permit a `WORKSPACE_ADMIN` to revoke a user's client brand assignment without altering their agency workspace membership.
* **FR-007 (Client Context Selection Barrier):** The frontend shall enforce a mandatory client-context selection barrier, ensuring all asset submissions and audits explicitly bind to an active `client_id`.
* **FR-008 (Last Admin Protection):** The system shall reject any request attempting to revoke, demote, or delete the sole remaining `WORKSPACE_ADMIN` of an agency workspace (`HTTP 409 Conflict`).

### 10.2 Guideline Ingestion & Living Brand Memory
* **FR-009 (Multi-Format Document Intake):** The system shall ingest brand guideline files in TXT, Markdown (.md), DOCX, and text-based PDF formats up to a maximum size of 20 MB.
* **FR-010 (Decompression Bomb Protection):** The ingestion pipeline shall inspect DOCX ZIP structures, immediately rejecting archives with $> 500	ext{ entries}$, uncompressed size $> 50	ext{ MB}$, compression ratios $> 100:1$, or path traversal sequences (`..`).
* **FR-011 (Automated Candidate Extraction):** The system shall asynchronously parse ingested guidelines, invoking Gemini in Structured JSON mode to extract candidate terminology, facts, and color swatches into the `extracted_candidates` staging table.
* **FR-012 (Zero-Action Knowledge Activation):** Extracted candidate rules shall remain strictly unapproved and inactive until an authorized Brand Manager reviews and approves them. Autonomous AI rule activation is prohibited.
* **FR-013 (Candidate Staging Dashboard):** The system shall provide a management interface for Brand Managers to edit candidate rule text, assign severity tags (`BLOCKING` vs. `ADVISORY`), and mark candidates as `APPROVED` or `REJECTED`.
* **FR-014 (Immutable Rule Revisions):** When an approved brand rule is modified, the system shall insert a new immutable row in `brand_rule_revisions` rather than updating existing records in place.
* **FR-015 (Materialized Snapshot Compilation):** When a Brand Manager publishes a memory release, the system shall compile all approved rules into a formal version, commit an immutable JSONB snapshot to `brand_memory_snapshots`, and record its SHA-256 hash.
* **FR-016 (Authoritative Active Memory Pointer):** The system shall maintain exactly one active memory version pointer per client brand space (`client_brands.active_memory_version_id`), updated transactionally upon release.
* **FR-017 (Document Supersession):** When an updated brand manual is uploaded, older versions transition to status `REPLACED` without deleting historical sections or files.

### 10.3 Content Submission & Pre-Flight Auditing
* **FR-018 (Multi-Modal Intake):** The system shall allow Content Creators to submit marketing copy ($\le 50,000	ext{ characters}$) and an optional static visual graphic (PNG/JPG $\le 10	ext{ MB}$, max dimension $4096	ext{px}$).
* **FR-019 (Asynchronous Audit Initialization):** Triggering an audit shall create a logical audit run (`audit_runs`), pin the client's current `active_memory_version_id`, initiate a physical execution attempt (`audit_execution_attempts`), and return an immediate `HTTP 202 Accepted` response.
* **FR-020 (Pinned Memory Snapshot Invariant):** All execution attempts and retries under a logical audit run shall evaluate collateral strictly against the memory snapshot pinned at audit creation time.
* **FR-021 (Deterministic Terminology Linter):** The system shall execute lexical screening across submitted copy using compiled word-boundary regular expressions loaded from the pinned memory snapshot, generating diagnostic cards for prohibited terms.
* **FR-022 (Typographic Normalization):** The terminology engine shall apply Unicode NFC canonical normalization and whitespace standardization while maintaining an explicit normalized-offset-to-raw-source-offset mapping for UI highlighting; NFC normalization may change string length and offsets.
* **FR-023 (Contextual Exception Evaluation):** Prohibited terminology checks shall evaluate configured rule exceptions without treating unconfigured quotation marks or blockquotes as automatic exemptions.
* **FR-024 (Atomic Factual Claim Extraction):** The factual engine shall segment prose into sentences and utilize Gemini to extract atomic factual propositions, classifying them into `OBJECTIVE_FACTUAL`, `SUBJECTIVE_MARKETING`, `CREATIVE_OR_OPINION`, or `EXTERNAL_EVIDENCE_REQUIRED`.
* **FR-025 (Tri-State NLI Verification):** The system shall evaluate extracted objective factual propositions against the pinned memory snapshot and assign exactly one of three epistemic statuses: `SUPPORTED`, `CONTRADICTED` (`BLOCKING`), or `UNVERIFIED` (`ADVISORY`).
* **FR-026 (Verbatim Substring Citation Verification):** The backend shall verify that every evidence quote returned by the model exists as an exact verbatim substring within the referenced rule revision of the pinned snapshot; fabricated citations are downgraded to `UNVERIFIED`.
* **FR-027 (CIEDE2000 Visual Palette Analysis):** The visual engine shall resize uploaded graphics, extract dominant color clusters using Pillow and NumPy, convert to CIELAB, and calculate perceptual distance ($\Delta E_{00}$) against approved brand swatches.
* **FR-028 (Linear-Light Alpha Compositing):** When processing images with partial transparency ($0 < A < 255$), the visual engine shall convert sRGB values to linear-light RGB before compositing against the client's configured background canvas. Fully transparent pixels ($A = 0$) are excluded from color extraction.

### 10.4 Remediation, Review & Reporting
* **FR-029 (Diagnostic Scorecard Compilation):** The audit orchestrator shall compile independent component findings into a unified scorecard displaying overall outcome (`PASS`, `WARNINGS`, `BLOCKED`), blocking count, advisory count, and categorized diagnostic cards.
* **FR-030 (Surgical AI Correction Suggestions):** Upon explicit creator request, the system shall generate minimal-edit text corrections that resolve detected violations while preserving surrounding authorial voice (Levenshtein edit ratio $\le 0.25$).
* **FR-031 (Correction Acceptance Version Forking):** Accepting an AI correction shall fork a new immutable asset version, update draft text inline, link `created_from_correction_id`, and immediately trigger a fresh pre-flight audit.
* **FR-032 (Review Submission Gating):** The system shall strictly prevent Content Creators from submitting an asset for review if unresolved `BLOCKING` issues exist or if a required audit check failed (`HTTP 422 Unprocessable Entity`).
* **FR-033 (Human Review State Transitions):** An asset with zero blocking issues enters state `READY_FOR_REVIEW`. An assigned Brand Manager can claim it (`UNDER_REVIEW`) and render a decision: `APPROVED`, `CHANGES_REQUESTED`, or `REJECTED`.
* **FR-034 (Advisory Warning Acknowledgment):** A Brand Manager may approve an asset containing non-blocking advisory warnings only by explicitly acknowledging them with a recorded justification in `human_review_advisory_acknowledgements`.
* **FR-035 (Post-Approval Invalidation):** Editing an already `APPROVED` asset version shall fork a new draft version, revoking approved status for the new iteration while preserving the historical approved record.
* **FR-036 (Verifiable Audit Manifest Export):** The system shall generate an exportable JSON/PDF compliance certificate for any `APPROVED` asset version, documenting complete verification provenance.

---

## 11. Detailed End-to-End Workflows

### 11.1 Workflow WF-1: Client Onboarding and Brand Memory Activation
```
[Workspace Setup] ──> [Client Creation] ──> [Guideline Upload] ──> [Candidate Staging] ──> [Memory Publication]
   (Admin)               (Admin)              (Brand Manager)        (Brand Manager)        (Brand Manager)
```
1. **Workspace Setup:** Workspace Admin logs into SYLVAR via Supabase Auth and initializes agency workspace.
2. **Client Creation:** Workspace Admin provisions client brand space (*Apex Cloud Security*) and assigns Brand Manager and Content Creator users.
3. **Guideline Upload:** Brand Manager uploads `Apex_Brand_Manual_2026.docx`. The document pipeline validates file signatures, stores the file in private storage, and extracts structured sections into `document_sections`.
4. **Candidate Staging:** Asynchronous Gemini extraction extracts candidate terms, facts, and color swatches into `extracted_candidates` in state `PENDING_REVIEW`.
5. **Memory Publication:** Brand Manager reviews staging, edits ambiguous terms, approves candidates, and clicks "Publish Memory Release." The system commits `brand_memory_versions` (v1.0), materializes an immutable JSONB snapshot in `brand_memory_snapshots` with a SHA-256 hash, and updates `client_brands.active_memory_version_id`.

### 11.2 Workflow WF-2: Content Pre-Flight Auditing, Remediation, and Human Sign-Off
```
[Draft Submission] ──> [Concurrent Auditing] ──> [Diagnostic Scorecard] ──> [Surgical Fix] ──> [Human Sign-Off]
    (Creator)              (Engines)                 (Creator)             (Creator)        (Brand Manager)
```
1. **Draft Submission:** Content Creator confirms active client context (*Apex Cloud Security*), inputs draft social copy, uploads a promotional banner PNG, and clicks "Run Pre-Flight Audit."
2. **Concurrent Auditing:** System initializes `audit_runs` pinned to Memory v1.0 snapshot. Orchestrator executes three parallel branches via `asyncio.gather`: (1) Terminology regex catches prohibited competitor name (`BLOCKING`); (2) Factual engine segments sentences and calls Gemini NLI, flagging a contradicted SLA uptime metric (`BLOCKING`); (3) Visual engine clusters colors and calculates CIEDE2000 distance, flagging an off-palette accent swatch (`ADVISORY`).
3. **Diagnostic Scorecard:** Orchestrator aggregates results, marks attempt `COMPLETED`, and sets overall outcome to `BLOCKED` (2 blocking, 1 advisory). Asset transitions to `ISSUES_FOUND`.
4. **Surgical Fix:** Creator clicks "Generate Fix" on the SLA claim card. Gemini returns a minimal-edit rewrite. Creator inspects the visual diff and clicks "Accept Fix & Re-Audit."
5. **Version Forking & Delta Re-Audit:** System forks asset version v1.1 (`created_from_correction_id` linked), preserving v1.0. Re-audit executes: terminology and factual claims resolve to `SUPPORTED`; visual accent warning remains as sole advisory. Overall outcome transitions to `WARNINGS`. Asset moves to `READY_FOR_REVIEW`.
6. **Human Sign-Off:** Creator submits asset. Brand Manager claims review (`UNDER_REVIEW`), checks advisory acknowledgment for the accent color, and clicks "Approve Asset." Asset moves to `APPROVED`. System persists a permanent compliance audit record in `audit_history` and generates an exportable certificate.

---

## 12. Brand Knowledge and Approval Lifecycle

```
Uploaded (File) ──> Extracted (Staged) ──> Reviewed (Human Edited) ──> Approved (Eligible) ──> Active (Published Snapshot)
```

### 12.1 State Machine Lifecycle Stages
1. **Uploaded:** Raw guideline file stored in private Supabase Storage with SHA-256 hash. Document sections parsed into PostgreSQL. Inactive.
2. **Extracted:** AI extraction outputs staged candidate rules in `extracted_candidates` in state `PENDING_REVIEW`. Inactive.
3. **Reviewed:** Brand Manager adjusts rule text, severity tags, or contextual exceptions. Staged candidate in state `MODIFIED_APPROVED`. Inactive.
4. **Approved:** Brand Manager formally approves candidate. Promoted to `brand_rules` and `brand_rule_revisions`. Eligible for release, but pending version activation.
5. **Active:** Compiled into published release version (`brand_memory_versions`). Denormalized JSONB snapshot committed to `brand_memory_snapshots`. Referenced by `client_brands.active_memory_version_id`. Directly queried by pre-flight audits.

### 12.2 Knowledge Entity Data Schemas
* **Terminology Rule Payload:** `{ "term": "cheap alternative", "match_type": "TOKEN_BOUNDARY", "preferred_replacement": "cost-effective solution", "contextual_exceptions": ["ALLOW_WITHIN_CUSTOMER_TESTIMONIAL"], "explanation": "Mandates enterprise positioning." }`
* **Factual Assertion Payload:** `{ "claim_text": "Delivers 1.2M events/sec throughput.", "factual_domain": "TECHNICAL_SPEC", "temporal_validity": {"valid_from": "2026-01-01", "valid_until": null}, "source_quote": "System benchmarks prove 1.2M events/sec sustained throughput.", "section_anchor": "Whitepaper Section 3.2" }`
* **Brand Color Swatch Payload:** `{ "swatch_name": "Apex Primary Navy", "hex_code": "#0A192F", "srgb": {"r": 10, "g": 25, "b": 47}, "cielab": {"l": 9.8, "a": 0.8, "b": -16.4}, "palette_role": "PRIMARY", "delta_e_tolerance": 5.0 }`

---

## 13. Content Versioning and Lifecycle

```
Draft ──> Auditing ──> Issues Found ──> Ready for Review ──> Under Review ──> Approved / Rejected / Changes Requested
  ▲          │
  └──────────┴── (Creator Edits / Delta Re-Audit)
```

### 13.1 Finite State Machine Matrix
| State | Permitted Transitions | Trigger / Condition | Permitted User Roles |
| :--- | :--- | :--- | :--- |
| **`DRAFT`** | `AUDITING` | Creator initiates pre-flight audit. | `CONTENT_CREATOR`, `BRAND_MANAGER` |
| **`AUDITING`** | `ISSUES_FOUND`, `READY_FOR_REVIEW` | Audit completes with blocking issues vs zero blocking issues. | System Execution Loop Only |
| **`ISSUES_FOUND`** | `DRAFT`, `AUDITING` | Creator edits draft copy, applies AI fix, or re-audits. | `CONTENT_CREATOR`, `BRAND_MANAGER` |
| **`READY_FOR_REVIEW`** | `UNDER_REVIEW`, `DRAFT` | Creator submits asset to review queue (requires 0 blocking issues). | `CONTENT_CREATOR`, `BRAND_MANAGER` |
| **`UNDER_REVIEW`** | `APPROVED`, `CHANGES_REQUESTED`, `REJECTED` | Brand Manager claims asset and renders review decision. | `BRAND_MANAGER`, `WORKSPACE_ADMIN` |
| **`CHANGES_REQUESTED`** | `DRAFT` | Creator reopens asset to implement reviewer feedback. | `CONTENT_CREATOR`, `BRAND_MANAGER` |
| **`APPROVED`** | *Terminal (Fork on Edit)* | Brand Manager approves deliverable; version permanently locked. | `BRAND_MANAGER`, `WORKSPACE_ADMIN` |
| **`REJECTED`** | *Terminal (Archived)* | Brand Manager rejects submission due to fundamental non-compliance. | `BRAND_MANAGER`, `WORKSPACE_ADMIN` |

---

## 14. Audit Engine Behaviour

### 14.1 The Three-Tier Execution Topology
```
Tier 1: Logical Audit Run (audit_runs)
 └── Pinned Asset Version & Memory Snapshot Hash
      │
      └── Tier 2: Physical Execution Attempt (audit_execution_attempts)
           ├── Attempt #1 (Interrupted / Failed)
           └── Attempt #2 (Active Successful Attempt: attempt_number = 2)
                │
                └── Tier 3: Component Checks (audit_checks)
                     ├── Terminology Check (COMPLETED)
                     ├── Factual Verification (COMPLETED)
                     └── Visual Palette Analysis (COMPLETED)
```

### 14.2 Execution Statuses vs. Audit Outcomes
* **Canonical Execution Statuses (`lifecycle_status` / `execution_status`):**
  * `PENDING`: Task initialized and queued in memory.
  * `RUNNING`: Active processing across concurrent audit engines.
  * `COMPLETED`: All required component checks finished execution.
  * `FAILED`: One or more required components encountered an unhandled exception or timeout.
  * `INTERRUPTED`: Worker process restarted or heartbeat timed out while running.
* **Audit Evaluation Outcomes (`overall_result`):**
  * `PASS`: Zero blocking violations, zero advisory warnings, all required checks completed.
  * `WARNINGS`: Zero blocking violations, one or more advisory warnings, all required checks completed.
  * `BLOCKED`: One or more blocking violations detected, OR one or more required audit checks failed.

### 14.3 Concurrency Control & Stale Attempt Recovery
* **Partial Unique Index:** Enforces exactly one running attempt per logical audit:
  ```sql
  CREATE UNIQUE INDEX idx_single_running_attempt_per_audit 
  ON audit_execution_attempts (audit_run_id) 
  WHERE execution_status = 'RUNNING';
  ```
* **Heartbeat Recovery:** During execution, workers update `heartbeat_at = NOW()` every 10 seconds. Attempts remaining in `RUNNING` with `heartbeat_at` older than 90 seconds are marked `INTERRUPTED`.

---

## 15. Terminology Checking Requirements

* **Deterministic Regex Compilation:** Compiled patterns enforce word boundaries and case sensitivity flags: `pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)`.
* **Unicode NFC Normalization:** Applied via `unicodedata.normalize('NFC', text)` to standardize canonical accents without mutating character positions.
* **Typographic Equivalence Classes:** Regex patterns match straight and curly quotes (`[''"]`) and hyphens/dashes (`[-—–]`) interchangeably.
* **Character Offset Precision:** Returned finding cards record `start_offset` and `end_offset` pointing directly to character indices in the creator's submitted raw draft for accurate visual UI highlighting.

---

## 16. Factual Verification Requirements

### 16.1 Proposition Extraction Schema
Marketing copy is segmented into sentences and parsed by the Gemini model using a strict Pydantic v2 schema:

```python
class AtomicClaim(BaseModel):
    claim_id: str
    sentence_index: int
    raw_sentence: str
    extracted_claim: str
    classification: Literal[
        "OBJECTIVE_FACTUAL", 
        "SUBJECTIVE_MARKETING", 
        "CREATIVE_OR_OPINION", 
        "EXTERNAL_EVIDENCE_REQUIRED"
    ]
    claim_type: Optional[Literal[
        "TECHNICAL_CAPABILITY", "INTEGRATION", "GEOGRAPHIC", 
        "PARTNERSHIP", "NUMERICAL", "CERTIFICATION", 
        "SLA_GUARANTEE", "OTHER"
    ]] = None

    @model_validator(mode='after')
    def validate_classification_and_claim_type(self) -> 'AtomicClaim':
        if self.classification == "OBJECTIVE_FACTUAL" and self.claim_type is None:
            raise ValueError("claim_type is mandatory for OBJECTIVE_FACTUAL claims.")
        if self.classification in ("SUBJECTIVE_MARKETING", "CREATIVE_OR_OPINION") and self.claim_type is not None:
            raise ValueError(f"claim_type must be null for {self.classification}.")
        return self
```

### 16.2 Tri-State NLI Verification Semantics
* `SUPPORTED`: Approved evidence explicitly corroborates the claim.
* `CONTRADICTED`: Approved evidence directly conflicts with the claim (triggers a `BLOCKING` violation).
* `UNVERIFIED`: Pinned memory snapshot contains no evidence confirming or denying the assertion (triggers an `ADVISORY` warning). **Unverified does not mean false.** Missing evidence is never marked as `SUPPORTED`.

### 16.3 Verbatim Substring Citation Invariant
The backend asserts that every cited `evidence_quote` exists as an exact verbatim substring within the referenced rule revision of the pinned snapshot (`assert evidence_quote in rule_revision.content`). If the quote does not exist verbatim, the citation is rejected, logged as `EVIDENCE_ATTRIBUTION_FAILED`, and the finding is automatically downgraded to `UNVERIFIED`.

---

## 17. Visual Analysis Requirements

### 17.1 Image Ingestion & Processing Pipeline
* **Validation:** PNG and JPG/JPEG files; magic-byte verified; max size 10 MB; max dimensions $4096 	imes 4096	ext{px}$.
* **Bilinear Downsampling:** Resized to a configurable max dimension of $400 	imes 400	ext{px}$ ($\le 160,000	ext{ pixels}$) to maintain sub-second CPU execution on constrained hardware.
* **Alpha Governance:** Fully transparent pixels ($A = 0$) are excluded from color extraction entirely. Semi-transparent pixels ($0 < A < 255$) undergo linear-light alpha compositing.

### 17.2 Mathematical Formulations
* **sRGB to Linear-Light RGB:**
  * If $V_{sRGB} \le 0.04045$: $V_{linear} = V_{sRGB} / 12.92$
  * Otherwise: $V_{linear} = ((V_{sRGB} + 0.055) / 1.055)^{2.4}$
* **Linear-Light Alpha Compositing:**
  * $C_{blended,linear} = lpha 	imes C_{fg,linear} + (1 - lpha) 	imes C_{bg,linear} \quad 	ext{where } lpha = A / 255$
* **Linear RGB to sRGB:**
  * If $V_{linear} \le 0.0031308$: $V_{sRGB} = 12.92 	imes V_{linear}$
  * Otherwise: $V_{sRGB} = 1.055 	imes V_{linear}^{1/2.4} - 0.055$
* **CIEDE2000 Formulation ($\Delta E_{00}$):** Evaluated against approved swatches in CIELAB space. Distances $> 5.0$ generate an `ADVISORY` potential visual deviation finding.

---

## 18. AI Correction Workflow

* **Surgical Remediation Prompt:** Instructs Gemini to replace *only* the non-compliant phrase, explicitly prohibiting rephrasing unaffected sentences or altering authorial tone.
* **Distance Constraint:** Backend asserts Levenshtein distance ratio $\le 0.25$ over the surrounding sentence context.
* **Visual Diff UI:** Interactive side-by-side diff modal highlights green insertions and red deletions.
* **Explicit Acceptance Invariant:** Applying a fix forks a new asset version (v1.1) and triggers a fresh pre-flight audit. Content is never silently approved.

---

## 19. Human Review and Approval Requirements

* **Exclusive Authority:** Only users holding `BRAND_MANAGER` or `WORKSPACE_ADMIN` assigned to the client can approve collateral.
* **Zero-Override Blocking Invariant:** If an asset version contains unresolved `BLOCKING` violations or failed required audit checks, the system physically blocks approval.
* **Advisory Acknowledgment:** Assets containing `ADVISORY` warnings can be approved only if the Brand Manager checks an explicit acknowledgment box and enters a recorded business justification in `human_review_advisory_acknowledgements`.

---

## 20. Audit History and Reporting

* **Immutable Compliance Lineage:** Persisted in `audit_history`, recording `asset_version_id`, `asset_sha256`, `memory_snapshot_id`, `memory_snapshot_hash`, `audit_run_id`, verified findings, applied corrections, reviewer `user_id`, and timestamp.
* **Exportable Compliance Certificate:** Standardized, downloadable JSON/PDF compliance certificate proving thorough pre-flight brand verification.

---

## 21. Non-Functional Requirements

### 21.1 Performance Targets (NFR-001 to NFR-005)
* **NFR-001:** Pre-flight audit pipeline completes execution in $\le 3.5	ext{ seconds}$ for standard drafts ($\le 800	ext{ words}$, image $\le 5	ext{ MB}$).
* **NFR-002:** Terminology linter scans 1,000 words against 100 compiled brand rules in $< 15	ext{ milliseconds}$.
* **NFR-003:** Dominant color extraction and CIEDE2000 distance calculations execute in $< 350	ext{ milliseconds}$ on an Intel i3-1215U CPU.
* **NFR-004:** Pinned memory snapshot lookups and tenant authorization checks execute in $< 50	ext{ milliseconds}$.
* **NFR-005:** React + Vite client bundle gzipped transfer size $< 350	ext{ KB}$, rendering initial dashboard in $< 800	ext{ milliseconds}$.

### 21.2 Security & Multi-Tenancy Invariants (NFR-006 to NFR-010)
* **NFR-006:** Every database query enforces parameterized tenant boundaries (`WHERE workspace_id = :w_id AND client_id = :c_id`).
* **NFR-007:** Backend connects to PostgreSQL using dedicated least-privilege role (`sylvar_app_user`) without superuser or `BYPASSRLS` rights.
* **NFR-008:** Backend cryptographically verifies Supabase JWT signatures using cached JWKS public keys.
* **NFR-009:** Membership revocation takes effect immediately upon the user's subsequent API request by checking active database membership status.
* **NFR-010:** Guidelines and collateral reside in private Supabase Storage buckets, accessible strictly via time-limited signed URLs (TTL $\le 15	ext{ minutes}$).

### 21.3 Reliability, Usability & Maintainability (NFR-011 to NFR-015)
* **NFR-011:** External AI service timeouts ($\ge 15	ext{s}$) are isolated to the factual check component, persisting `FAILED` status while preserving terminology and visual findings.
* **NFR-012:** Any failed required component check unconditionally sets overall audit outcome to `BLOCKED`.
* **NFR-013:** All API errors return standardized RFC 9457 Problem Details schemas, masking internal database errors and stack traces.
* **NFR-014:** Active local development consumes $< 5.5	ext{ GB}$ of system RAM on Windows 11.
* **NFR-015:** The platform operates reliably as a single-process FastAPI modular monolith without requiring external task queues (Celery/Redis).

---

## 22. Security and Tenant Isolation Requirements

```
[Inbound Request] ──> [Gate 1: Asymmetric JWT Verification (JWKS)]
                             │
                             ▼
                      [Gate 2: Active Workspace Membership Check]
                             │
                             ▼
                      [Gate 3: Explicit Client Brand Assignment Check]
                             │
                             ▼
                      [Gate 4: RBAC Role & Permission Verification]
                             │
                             ▼
                      [Gate 5: Parameterized Tenant SQL Execution]
```

### 22.1 The 5-Gate Server-Side Authorization Pipeline
1. **Gate 1 (Cryptographic Identity):** Asymmetric JWT verification against Supabase Auth JWKS public keys. Extracts `auth.uid()`.
2. **Gate 2 (Workspace Membership):** Queries `workspace_memberships` asserting user is an `ACTIVE` member of target `workspace_id`.
3. **Gate 3 (Client Brand Scoping):** Queries `client_memberships` asserting user is explicitly assigned to target `client_id` with status `ACTIVE`. (`WORKSPACE_ADMIN` users are subject to the same explicit client-assignment requirement for client-scoped operations).
4. **Gate 4 (Action RBAC):** Asserts user's role satisfies the required action tier.
5. **Gate 5 (Tenant-Scoped Data Access):** Injects validated `workspace_id` and `client_id` directly into parameterized SQL queries and session variables (`SET LOCAL app.current_workspace_id = ...`).

### 22.2 Service-Role Key Neutralization
Because the Supabase Service-Role key bypasses PostgreSQL Row-Level Security (RLS), FastAPI enforces strict application-level authorization and composite query scoping, treating RLS as secondary defense-in-depth.

### 22.3 AI Prompt Injection & Untrusted Data Governance
* **Untrusted Input Enclosure:** Guidelines and drafts are enclosed in XML tags (`<untrusted_draft>`, `<reference_facts>`) with explicit system instructions prohibiting instruction execution.
* **Security Signal Decoupling:** Prompt injection attempts detected during claim extraction are classified as security anomalies and rejected, rather than evaluated as `UNVERIFIED` factual assertions.
* **Zero-Action Model Boundary:** AI responses cannot mutate user permissions, activate brand rules, or approve collateral.

---

## 23. Data Management and Retention Expectations

* **25-Table Relational Schema:** Partitioned across 8 domains: Identity (`users`, `agency_workspaces`, `workspace_memberships`), Clients (`client_brands`, `client_memberships`), Documents (`guideline_documents`, `document_sections`, `extracted_candidates`), Memory (`brand_memory_versions`, `brand_memory_version_rules`, `brand_rules`, `brand_rule_revisions`, `brand_memory_snapshots`), Content (`content_assets`, `asset_versions`), Audits (`audit_runs`, `audit_execution_attempts`, `audit_checks`, `audit_findings`, `correction_suggestions`), Reviews (`human_reviews`, `human_review_advisory_acknowledgements`, `audit_history`), System (`system_audit_logs`, `knowledge_activation_history`).
* **Referential Integrity via `ON DELETE RESTRICT`:** Deleting an agency workspace, client brand, or source document is restricted if historical audit records, asset versions, or published memory snapshots reference it.
* **Soft Deactivation:** Workspaces and client brands use soft deactivation (`is_active = FALSE`).

---

## 24. Error Handling and Failure Scenarios

* **RFC 9457 Problem Details Standard:**
  ```json
  {
    "type": "https://api.sylvar.example/v1/errors/blocking-violations-present",
    "title": "Unresolved Blocking Violations",
    "status": 422,
    "detail": "Asset version contains 2 blocking violations. All blocking issues must be resolved before submitting for review.",
    "instance": "/api/v1/workspaces/w-123/clients/c-456/assets/a-789/versions/v-001/submit",
    "code": "BLOCKING_VIOLATIONS_EXIST",
    "invalid_params": [],
    "timestamp": "2026-11-02T15:04:05Z"
  }
  ```
* **Fault Isolation:** External API timeouts ($\ge 15.0	ext{s}$) are caught via `asyncio.wait_for`, marking the factual check `FAILED` while preserving terminology and visual findings. Attempt status is set to `FAILED`, and overall outcome is set to `BLOCKED`.

---

## 25. External Integrations and Dependencies

* **Google Gemini API:** Configurable Gemini model selected from model IDs verified as currently available at implementation time; do not assume a model identifier or fallback is valid without checking provider documentation/API access.
* **Supabase Managed PostgreSQL (v15+):** Relational storage, JSONB snapshots, RLS.
* **Supabase Auth (GoTrue):** User signup, session management, JWKS rotation.
* **Supabase Storage:** Private, tenant-isolated buckets for PDFs, DOCX, and images.
* **Vercel:** Edge hosting for the React 18 / Vite SPA.
* **Render:** Containerized web service runtime for the FastAPI backend.

---

## 26. Technology Stack

* **Frontend:** React 18.x, Vite 5.x, TypeScript 5.x, Tailwind CSS 3.x, shadcn/ui, Zustand 4.x.
* **Backend:** Python 3.11+, FastAPI 0.110+, Pydantic v2, SQLAlchemy 2.0+, asyncpg 0.29+.
* **Image Processing:** Pillow 10.x, NumPy 1.26+, pure-Python CIEDE2000 (Sharma 2005 formulation).
* **Document Processing:** `pdfplumber`, `python-docx`.

---

## 27. High-Level Architecture

The FastAPI backend is architected as a modular monolith organized into 12 domain packages: `auth`, `workspaces`, `clients`, `documents`, `memory`, `assets`, `orchestrator`, `engine_terminology`, `engine_factual`, `engine_visual`, `remediation`, and `reviews`. Concurrency is managed in-process via `asyncio.gather`.

---

## 28. Deployment Requirements

* **Environment Secret Separation:** Private keys (`DATABASE_URL`, `GEMINI_API_KEY`, `SUPABASE_URL`) reside strictly in Render vault; public anon keys reside in Vercel.
* **Cold-Start Mitigation:** Pre-demo warm-up script pinging `GET /api/v1/health` 5 minutes prior to live evaluation; local fallback environment ready on developer laptop.

---

## 29. Testing and Acceptance Criteria

* **Pytest Unit Tests:** Terminology regex boundary tests, linear-light alpha compositing math tests, Sharma (2005) CIEDE2000 validation tests, Pydantic cross-field validation tests.
* **Integration Tests:** RLS fail-closed tests, composite foreign key rejection tests, single-running-attempt partial index lock tests.
* **Security Tests:** Cross-tenant rejection tests (`HTTP 403`), forged JWT tests (`HTTP 401`), DOCX decompression bomb tests (`HTTP 422`), prompt injection containment tests.

---

## 30. MVP Implementation Milestones

* **Milestone 1 (Days 1–2):** Project initialization, Vite + FastAPI skeletons, Supabase Auth & JWKS verification.
* **Milestone 2 (Days 3–4):** 25-table database migration, least-privilege role setup, workspace/client management APIs.
* **Milestone 3 (Days 5–6):** Document ingestion pipeline, candidate extraction staging, memory snapshot publisher.
* **Milestone 4 (Days 7–9):** Audit orchestrator, regex terminology linter, Gemini factual NLI, Pillow CIEDE2000 engine, AI correction diffs.
* **Milestone 5 (Days 10–12):** Brand Manager review queue, verifiable audit manifest export, Vercel/Render deployment, demo seeding.

---

## 31. Risks, Assumptions, and Mitigations

| Risk | Probability | Impact | Mitigation Strategy | Contingency Fallback Plan |
| :--- | :---: | :---: | :--- | :--- |
| **Gemini Rate Limits (429)** | Medium | High | Exponential backoff retry; isolation-aware compound hash caching. | Fallback model `gemini-3.5-flash-lite`. |
| **Render Cold Starts** | High | Medium | Automated pre-demo warm-up script execution. | Localhost backup environment connected to cloud Supabase. |
| **Model Citation Hallucination** | Medium | High | Verbatim substring validation against pinned rule revision. | Downgrade claim to `UNVERIFIED` with `EVIDENCE_ATTRIBUTION_FAILED`. |
| **Cross-Tenant Data Leakage** | Low | Critical | Composite foreign keys `(workspace_id, client_id, id)` and 5-gate authorization. | Automated test suite verifying cross-tenant read/write rejections. |
| **Low-Power Dev RAM Exhaustion** | High | Medium | Cloud-first setup: Cloud Supabase database; lightweight Vite dev server. | Limit background apps; restart local servers periodically. |

---

## 32. Open Questions and Implementation-Time Verification Items

1. **Gemini 3.8 Flash vs. 3.5 Flash-Lite Verification:** Benchmark structured JSON schema stability, factual entailment reasoning accuracy, and latency across both models during Phase 1.
2. **Supabase Transaction-Local Variable Pooling Compatibility:** Verify that `asyncpg` connection poolers correctly scope `SET LOCAL app.current_workspace_id = ...` strictly within transaction blocks and do not leak session state across connection check-outs.
3. **Optimal Bilinear Downsampling Resolution:** Calibrate color extraction accuracy across $300 	imes 300$, $400 	imes 400$, and $500 	imes 500$ pixel resolutions on sample client display ads to identify the optimal balance between CIEDE2000 precision and CPU execution speed.
4. **DOCX Table Normalization Strategy:** Test `python-docx` extraction over complex nested tables in brand guidelines to ensure tabular terminology pairings are extracted as structured key-value text.

---
*End of Master Product Requirements Document. Approved for Round 2 Build Sprint.*


## Binding Control-Pack Addendum (2026-11-02)

This addendum resolves conflicts in this PRD and takes precedence over conflicting wording elsewhere in this PRD:
1. Round 2 implementation is NOT authorized. “Ready for Round 2”, “build sprint”, or similar wording is not authorization.
2. Workspace Admin has no ambient client access. All client-scoped reads and mutations require an active explicit client assignment, including Workspace Admin users.
3. Only an assigned Brand Manager may perform human review decisions (`APPROVED`, `REJECTED`, `CHANGES_REQUESTED`) and advisory acknowledgements. Workspace Admin may manage workspace membership, client provisioning and assignments, but is not a substitute reviewer.
4. NFC normalization requires a mapping from normalized offsets back to original source offsets. Do not assume character offsets remain unchanged.
5. Performance figures are benchmark targets only. No latency, accuracy, zero-hallucination, or cost guarantee may be claimed before measurement.
6. Gemini model IDs and fallback choices must be verified against the provider's currently available API models and the configured account at implementation time.
7. The 25-table catalogue is a conceptual inventory, not an executable schema. Exact columns, constraints, indexes, foreign keys, triggers and complete RLS policies remain implementation-time verification gates. Agents must not invent missing definitions.
8. In-process asyncio execution is not durable across process termination. Persist state before dispatch; on restart, reconcile stale RUNNING attempts as INTERRUPTED only after verifying the prior process/worker cannot still be executing. Do not claim guaranteed recovery or exactly-once execution.
