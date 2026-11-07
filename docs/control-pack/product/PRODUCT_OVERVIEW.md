# PRODUCT_OVERVIEW.md — High-Level Product Architecture
**Product:** SYLVAR (working name; clearance pending)  
**Positioning:** The Pre-Publication CI/CD for Brand Integrity  

---

## 1. What is SYLVAR?

> Naming note: SYLVAR is the current working name. Trademark, domain, and software-name clearance have not yet been completed. Inkloom AI is the hackathon problem-statement provider, not the product name.
SYLVAR is an automated brand governance platform designed for creative marketing agencies. It acts as an automated inspection gate that audits creative collateral (text copy and visual graphics) against approved client brand knowledge prior to external publication.

## 2. The Core Workflow
```
[Brand Setup] ──> [Knowledge Ingestion] ──> [Human Review & Staging] ──> [Memory Activation]
                                                                                │
[Human Sign-Off] <── [Version Forking & Fix] <── [Pre-Flight Audit] <──────────┘
```
1. **Brand Setup:** Agency Admin provisions client brand space.
2. **Knowledge Ingestion:** Brand Manager uploads brand manuals (PDF, DOCX, TXT, MD). Text is parsed into structured sections.
3. **Staging & Approval:** Gemini extracts candidate rules (terms, facts, colors) into staging. Brand Manager reviews and approves rules. AI cannot activate rules.
4. **Memory Activation:** Approved rules are published into a versioned release, creating an immutable JSONB snapshot with a SHA-256 hash.
5. **Content Submission:** Content Creator submits copy and promotional graphic.
6. **Pre-Flight Audit:** Concurrent audit runs (Terminology regex, Factual Gemini NLI, Visual CIEDE2000 math).
7. **Scorecard & Fixes:** Violations surfaced. Creator can request minimal-edit surgical AI rewrites.
8. **Version Forking:** Accepting a fix forks a new immutable version and triggers a delta re-audit.
9. **Human Sign-Off:** Brand Manager inspects clean audit, acknowledges advisories, and approves. System exports compliance certificate.
