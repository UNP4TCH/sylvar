# SYSTEM_COMPONENTS.md — Subsystem Component Specifications

## 1. Ingestion Subsystem (`modules.documents`)
* **Libraries:** `pdfplumber`, `python-docx`, `python-magic`.
* **Protections:** Rejects DOCX archives $>500\text{ entries}$, $>50\text{ MB uncompressed}$, or $>100:1\text{ ratio}$. Rejects PDFs $>100\text{ pages}$ or taking $>10\text{s}$ to parse.
* **Storage:** Files uploaded to private Supabase Storage buckets under path `{workspace_id}/{client_id}/{document_uuid}`.
* **Persistence:** Extracted text stored in `document_sections` with headings, paragraphs, and page references.

## 2. Terminology Subsystem (`modules.engine_terminology`)
* **Execution:** 100% deterministic in Python. Zero LLM calls.
* **Normalizer:** Applies Unicode NFC and character equivalence classes (`[''"]`, `[-—–]`).
* **Scanner:** Scans copy using pre-compiled regex with word boundaries: `(?<!\w){term}(?!\w)`.
* **Output:** Diagnostic cards with `start_offset`, `end_offset`, severity (`BLOCKING` / `ADVISORY`), and replacement.

## 3. Factual Verification Subsystem (`modules.engine_factual`)
* **Execution:** Hybrid model-assisted NLI.
* **Extraction:** Gemini Structured JSON mode decomposes prose into `AtomicClaim` objects.
* **Grounding:** Passes pinned memory snapshot facts into prompt context.
* **Classifier:** Evaluates claims to `SUPPORTED`, `CONTRADICTED`, or `UNVERIFIED`.
* **Citation Gate:** Backend asserts verbatim substring existence of cited quote in referenced rule revision. Downgrades failed citations to `UNVERIFIED`.

## 4. Visual Intelligence Subsystem (`modules.engine_visual`)
* **Execution:** Pure-Python CPU algorithms. Zero OpenCV binaries.
* **Downsampler:** Resizes raster graphics to max $400 \times 400\text{px}$ using Pillow bilinear interpolation.
* **Alpha Blender:** Composites semi-transparent pixels ($0 < A < 255$) in linear-light RGB space.
* **Color Matcher:** Calculates CIEDE2000 ($\Delta E_{00}$) distance against approved brand swatches. Distances $> 5.0$ generate advisory warnings.

## 5. Audit Orchestration Subsystem (`modules.orchestrator`)
* **Concurrency:** In-process non-blocking concurrency via `asyncio.gather(*checks, return_exceptions=True)`.
* **Attempt Tracking:** Allocates sequential attempt numbers in `audit_execution_attempts`. Partial unique index guards against duplicate running attempts.
* **Heartbeat:** Periodically updates `heartbeat_at = NOW()`. Interrupted attempts recover cleanly after 90s.
