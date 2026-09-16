# Fix duplicate invoices and bound server concurrency

## Summary

The human-operated `Profile_coder` will implement both changes. `Profile_codex` remains read-only. Prevent retry-driven duplicate invoices through a required UUID `Idempotency-Key`, and cap concurrent HTTP request threads at 16.

## Implementation Changes

- Add an `invoice_requests` SQLite table using `CREATE TABLE IF NOT EXISTS`, containing a unique idempotency key, request fingerprint, and associated invoice ID. This avoids altering existing invoice tables.
- Validate and normalize the `Idempotency-Key` header as a UUID. Missing or invalid keys return `400`.
- Hash the validated invoice business fields deterministically. Within one transaction, save the invoice, its lines, and request mapping.
- When the key already exists:
  - Matching fingerprint: return the original invoice with `200`.
  - Different fingerprint: return `409` without creating an invoice.
  - First successful submission continues returning `201`.
- Update the browser to generate a key with `crypto.randomUUID()`, retain it across failed retries, and reuse it when Save is clicked again without editing the submitted form. Clear it after the form changes so a changed sale receives a new key.
- Replace direct `ThreadingHTTPServer` use with a standard-library bounded server implementation using a 16-slot semaphore. Always release a slot when request processing finishes or fails.
- Preserve loopback binding, atomic invoice persistence, existing response bodies, monetary calculations, and historical invoice data.
- Update `README.md`, the evidence report, and `docs/new-bugs.md` to document the API contract and mark confirmed issues as fixed only after validation.

## Public Interface

- `POST /api/invoices` requires:

```http
Idempotency-Key: <UUID>
```

- Responses:
  - `201`: new invoice created.
  - `200`: matching request replayed; original invoice returned.
  - `400`: missing or malformed idempotency key.
  - `409`: key reused with different invoice content.
- No new dependency or external service is introduced.

## Test Plan

- Verify the same key and payload submitted twice produces one invoice and identical response data.
- Verify the replay remains correct through a fresh database connection.
- Verify the same key with different content returns `409` and preserves the first invoice.
- Verify missing and malformed keys return `400` without database writes.
- Verify a forced line or request-mapping failure rolls back headers, lines, and mapping atomically.
- Run 17 blocked requests against the bounded server and verify no more than 16 handlers execute concurrently; release them and verify all slots are recovered.
- Run `python3 -m py_compile app.py` and `python3 -m unittest discover -s tests -v`.
- Use temporary SQLite databases only; never use `billing.sqlite3` as test data.

## Assumptions

- Idempotency applies to invoice creation, not retrieval.
- Request mappings are retained for the lifetime of their invoices.
- Existing invoices require no backfill because they predate idempotency keys.
- Sixteen concurrent workers is the fixed local-server limit.
- Load testing beyond the deterministic concurrency test remains an operational follow-up.
