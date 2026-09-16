# New bugs evidence report

This report began as a read-only diagnosis of `retail_billing_new`. The confirmed duplicate-invoice defect and the concurrency risk were subsequently addressed and verified on 2026-09-15.

## ROOT CAUSE

### CONFIRMED — RESOLVED

The original invoice-creation workflow had no idempotency protection. Every valid `POST /api/invoices` executed a new invoice-header insert and new line-item inserts, even when the request was an exact retry.

Resolution: the API now requires a UUID `Idempotency-Key`, stores the key and request fingerprint atomically with the invoice, replays matching requests, and rejects conflicting reuse. The browser retains its key across retries of unchanged content.

### HYPOTHESIS — MITIGATED AND BOUND VERIFIED

The original `ThreadingHTTPServer` had no application-level concurrency limit. It has been replaced with a bounded implementation capped at 16 simultaneous handlers. A deterministic 17-request test verified the handler bound; process-level memory load testing remains outside the current evidence.

## EVIDENCE

Principal code-quality and business-logic locations:

- Validation and calculation: `app.py:80`
- Idempotency validation and fingerprinting: `app.py:123-146`
- Atomic invoice persistence and replay handling: `app.py:149-172`
- Bounded server concurrency: `app.py:175-195`
- HTTP input and response handling: `app.py:228-245`
- Browser submission control: `index.html:127`

Gap and null handling:

- Missing or null `customer_name` is rejected.
- Missing or null `items` is rejected.
- Null product, quantity, and unit-price values are rejected.
- A missing `tax_rate` defaults to zero at `app.py:86`.
- An explicitly null `tax_rate` is rejected rather than defaulted.
- Request bodies are capped at 64 KiB at `app.py:234-236`.
- Invoice item count is capped at 100 at `app.py:89-91`.
- Recent-history results are capped at 50 at `app.py:217-220`.
- Simultaneously active request handlers are capped at 16 at `app.py:175-195`.

The original schema contained only an auto-generated invoice ID. The current schema stores a unique idempotency key, request fingerprint, and invoice association (`app.py:56-60`). The creation transaction checks that mapping before insertion and returns the stored invoice for an exact replay (`app.py:149-172`).

## REPRO

Call `create_invoice()` twice with the same deterministic retail payload:

```json
{
  "customer_name": "Ada",
  "tax_rate": "10",
  "items": [
    {
      "product_name": "Widget",
      "quantity": "1",
      "unit_price": "10.00"
    }
  ]
}
```

The investigation used a database test double, so it did not create or modify a file, SQLite database, or schema. The observed result was:

```text
first_result:             {"id": 1}
second_result:            {"id": 2}
invoice_header_inserts:   2
line_insert_batches:      2
```

This reproduction records the original defect. The regression test now verifies that the same key and payload produce one stored invoice and that the replay returns the original invoice.

## IMPLEMENTED TESTS

The automated suite now verifies the following:

1. A valid invoice with a stable idempotency key returns `201`.
2. Repeating exactly the same request returns the original invoice with `200`.
3. Sequential and simultaneous retries leave one invoice header and one set of lines.
4. Reusing the identifier with different invoice content returns `409`.
5. Missing and malformed identifiers return `400` without writing an invoice.
6. Failed line or idempotency-record insertion rolls back the whole invoice transaction.

The suite also runs 17 blocked requests and verifies that no more than 16 handlers run simultaneously and that all requests complete after release. Measuring process memory under sustained load remains a separate operational test.

## RISK

Duplicate submission was a **high business-integrity risk** for this billing system. The implemented API and persistence controls mitigate retry-driven duplication for clients that use the required key.

The thread count is now bounded at 16. Overall memory behavior under sustained hostile or slow-client load remains an operational limitation rather than a production-readiness guarantee.
