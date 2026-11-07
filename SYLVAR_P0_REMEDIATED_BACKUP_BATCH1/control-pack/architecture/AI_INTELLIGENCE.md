# AI_INTELLIGENCE.md — AI & Visual Intelligence Specification
**Reference:** Task 4 AI & Visual Intelligence Specification v1.5  

---

## 1. Terminology Compliance Engine
* **Execution:** 100% deterministic regular expressions in Python. Sub-10ms latency. Zero token expense.
* **Normalization:** Unicode NFC via `unicodedata.normalize('NFC', text)`. Character equivalence classes for quotes and hyphens.
* **Offsets:** Diagnostic cards return exact character indices (`start_offset`, `end_offset`) pointing to raw draft text.
* **Exceptions:** Rules evaluate `contextual_exceptions` (e.g., quotes in testimonials). Unconfigured quotes do not bypass rules.

---

## 2. Factual Verification Engine
* **Extraction:** Gemini in Structured JSON mode extracts `AtomicClaim` objects.
* **Classification:** Claims classified into `OBJECTIVE_FACTUAL`, `SUBJECTIVE_MARKETING`, `CREATIVE_OR_OPINION`, `EXTERNAL_EVIDENCE_REQUIRED`.
* **NLI Entailment:** Evaluated strictly against the pinned memory snapshot facts:
  * `SUPPORTED`: Corroborated by snapshot facts.
  * `CONTRADICTED`: Conflicts with snapshot facts (`BLOCKING`).
  * `UNVERIFIED`: Insufficient evidence in snapshot (`ADVISORY`).
* **Verbatim Substring Assertion:** Backend asserts `assert evidence_quote in rule_revision.content`. Failed citations fail closed to `UNVERIFIED`.

---

## 3. Visual Analysis Engine & Color Math
* **Downsampling:** Bilinear downscaling to max $400 \times 400\text{px}$ ($\le 160,000\text{ pixels}$).
* **Linear-Light Alpha Compositing:**
  * If $V_{sRGB} \le 0.04045$: $V_{linear} = V_{sRGB} / 12.92$
  * Otherwise: $V_{linear} = ((V_{sRGB} + 0.055) / 1.055)^{2.4}$
  * $C_{blended,linear} = \alpha \times C_{fg,linear} + (1 - \alpha) \times C_{bg,linear} \quad (\alpha = A / 255)$
  * If $V_{linear} \le 0.0031308$: $V_{sRGB} = 12.92 \times V_{linear}$
  * Otherwise: $V_{sRGB} = 1.055 \times V_{linear}^{1/2.4} - 0.055$
* **CIEDE2000 Formulation ($\Delta E_{00}$):** Pure-Python NumPy module verified against Sharma (2005) reference test vectors.
* **Advisory Governance:** $\Delta E_{00} > 5.0$ surfaces as `ADVISORY` potential deviation. Visual deviations never trigger blocking violations.
