# Error Handling

- Use RFC 9457 Problem Details with stable `type`, `title`, `status`, `detail`, `instance`; include documented application `code` and `request_id` extensions consistently.
- Never expose stack traces, SQL, secrets, provider credentials or cross-tenant resource existence.
- Distinguish validation (400/422), authentication (401), authorization (403 or deliberate non-disclosing 404), conflict (409), rate limit (429), upstream timeout/unavailability (502/503/504) and unexpected server failure (500).
- Persist component-level audit failures with component, status, safe error code/message and retryability. Never convert a failed required check into a pass.
- Separate execution status from audit outcome. A required component failure results in execution failure and a blocked audit outcome according to the canonical contract.
- Retry only transient failures with bounded backoff and idempotency controls. A retry is a new physical attempt; preserve prior attempts/findings.
