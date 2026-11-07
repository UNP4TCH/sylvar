# DATA_FLOW.md — End-to-End System Data Flow Diagrams

## 1. Ingestion & Memory Compilation Flow
```
Client Brand Manual (DOCX/PDF)
            │
            ▼
[File Signature & Archive Decompression Guard]
            │
            ▼
[Sectional Text Parser (pdfplumber / python-docx)]
            │
            ▼
[guideline_documents & document_sections]
            │
            ▼
[Gemini Structured Candidate Extractor]
            │
            ▼
[extracted_candidates (PENDING_REVIEW)]
            │
            ▼ (Brand Manager Approval)
[brand_rules & brand_rule_revisions]
            │
            ▼ (Memory Activation Release)
[brand_memory_versions & brand_memory_snapshots (JSONB + SHA-256)]
            │
            ▼
[client_brands.active_memory_version_id (Updated Authoritative Pointer)]
```

## 2. Pre-Flight Content Audit Execution Flow
```
Draft Copy & Visual Graphic (Content Creator)
            │
            ▼
[FastAPI 5-Gate Authorization & Client Scoping]
            │
            ▼
[Create audit_runs pinned to active memory_snapshot_id]
            │
            ▼
[Allocate Physical Attempt in audit_execution_attempts (idx_single_running lock)]
            │
      ┌─────┴─────────────────────────┐
      ▼                               ▼                               ▼
[Branch 1: Terminology]     [Branch 2: Factual NLI]         [Branch 3: Visual Math]
Regex Scanner (<10ms)       Gemini JSON NLI (~1.5s)         Pillow/NumPy ΔE00 (~200ms)
      │                               │                               │
      └─────┬─────────────────────────┘                               │
            ▼                                                         │
[Substring Citation Assertion Gate]                                   │
            │                                                         │
            └─────────────────────────┬───────────────────────────────┘
                                      ▼
                        [Scorecard Aggregator Engine]
                                      │
                        [Commit to audit_checks & audit_findings]
                                      │
                        [Compute Overall Outcome: PASS / WARNINGS / BLOCKED]
                                      │
                        [Return Consolidated Diagnostic Scorecard]
```
