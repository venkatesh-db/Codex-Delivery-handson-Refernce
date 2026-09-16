# Invoice-level discount implementation plan

## Objective

Allow a cashier to enter an invoice-level discount percentage. The server will validate and calculate the discount, store it as part of the immutable invoice snapshot, calculate tax on the discounted subtotal, and return the final amount. Existing invoices and idempotency records must remain compatible.

## Roles and scope

- Coordinating profile: `profile_sse`
- Implementation subagent: `feature_implementer`
- Required skill: `.agents/skills/retail-coding-standards/SKILL.md`
- Files expected to change: `app.py`, `index.html`, `tests/test_app.py`, `README.md`, and `docs/evidence-report.md`
- Persistent `billing.sqlite3` must not be used for tests or changed without separate migration authorization.

## Business calculation decision

For this enhancement, apply the discount before tax:

```text
subtotal_cents = sum of rounded invoice line totals
discount_cents = round_half_up(subtotal_cents × discount_rate / 100)
taxable_subtotal_cents = subtotal_cents − discount_cents
tax_cents = round_half_up(taxable_subtotal_cents × tax_rate / 100)
total_cents = taxable_subtotal_cents + tax_cents
```

Example:

```text
Subtotal:          $28.00
Discount (10%):    -$2.80
Taxable subtotal:  $25.20
Tax (10%):          $2.52
Total:             $27.72
```

This is a first-version product assumption, not a jurisdiction-specific tax guarantee.

## Storage design

Create an additive companion table during normal database initialization:

```sql
CREATE TABLE IF NOT EXISTS invoice_discounts (
    invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id),
    discount_rate TEXT NOT NULL,
    discount_cents INTEGER NOT NULL
);
```

Do not alter or rewrite existing invoice rows. Store one discount record for every new invoice, including a zero-rate discount. Insert the invoice header, invoice lines, discount record, and idempotency mapping in the same SQLite transaction so any failure rolls back the complete invoice.

Retrieve invoices using a left join to `invoice_discounts`. When an existing invoice has no discount record, expose:

```json
{
  "discount_rate": "0",
  "discount_cents": 0
}
```

Keep the historical invoice's stored subtotal, tax, and total unchanged; never recalculate old invoices.

## Server validation and calculation

Extend `prepare_invoice` to read `discount_rate` with a default of zero when the field is omitted.

Validation rules:

- Accept string, integer, or finite floating-point numeric input consistently with existing tax validation.
- Reject booleans, `null`, non-numeric values, NaN, and infinity.
- Accept values from 0 through 100 inclusive.
- Accept at most two decimal places.
- Reject invalid discounts before opening a write transaction.
- Ignore client-supplied discount amounts, tax amounts, subtotals, and totals.

Calculate all rates with `Decimal`, persist monetary amounts as integer cents, and use `ROUND_HALF_UP` at the discount and tax boundaries.

Add `discount_rate` and `discount_cents` to full invoice responses. The invoice-list endpoint does not need new fields because it currently returns summaries only.

## Idempotency compatibility

Include the validated `discount_rate` in the invoice fingerprint for nonzero discounts.

For an omitted or zero discount, retain the legacy fingerprint representation without a discount field. This preserves replay compatibility with idempotency records created before the enhancement.

Required behavior:

- Same key and same validated discount: return the original invoice.
- Same key and changed discount: return `409` without creating data.
- Omitted discount and zero discount: treat as equivalent.
- Never include server-calculated totals in the fingerprint.

## Cashier UI and printing

Add a required numeric Discount rate field with:

```text
minimum = 0
maximum = 100
step = 0.01
default = 0
```

Send the value as `discount_rate` in the invoice JSON request.

Render a discount row between subtotal and tax:

```text
Discount (10%)    -$2.80
```

Render values using text APIs and the existing currency formatter. Changing the discount changes the serialized request payload and must generate a new idempotency key; retrying unchanged content must reuse the existing key.

The current print CSS retains the invoice section, so the discount row should print automatically. A human must inspect print preview before marking printed layout verified.

## Failure behavior

- Invalid discount: return `400` and store nothing.
- Same idempotency key with a different discount: return `409` and preserve the original invoice.
- SQLite failure while inserting the discount snapshot: return the existing controlled storage error and roll back the invoice header, lines, discount, and idempotency mapping.
- Old invoice without a discount record: return it successfully with zero discount defaults.

## Test plan

Use temporary SQLite databases only.

1. Create an invoice with subtotal `2800`, discount `10%`, and tax `10%`; expect discount `280`, tax `252`, and total `2772` cents.
2. Verify discount half-up rounding with a five-cent subtotal and 10% discount; expect a one-cent discount.
3. Verify a tax half-cent boundary after the discount has been applied.
4. Accept discount rates `0`, `100`, and a valid two-decimal rate.
5. Reject `-0.01`, `100.01`, `1.001`, `null`, boolean, NaN, and infinity without storing any row.
6. Verify a 100% discount produces zero taxable subtotal, zero tax, and zero total.
7. Insert a legacy invoice without a discount row and verify retrieval returns zero discount while preserving its stored historical totals.
8. Verify old zero-discount idempotency fingerprints still replay successfully.
9. Verify the same key and nonzero discount replays the original invoice.
10. Verify changing the discount while reusing the key returns `409` and leaves row counts unchanged.
11. Force discount-row insertion failure and verify the header, lines, discount, and idempotency mapping all roll back.
12. Through HTTP, verify creation returns `201`, exact replay returns `200`, conflicting discount returns `409`, and invalid discount returns `400`.
13. Verify the served HTML contains the discount input and discount display elements.
14. Manually inspect browser entry, saved-invoice retrieval, and print preview.

## Validation commands

Run from `retail_billing_new`:

```sh
python3 -m py_compile app.py
python3 -m unittest discover -s tests -v
```

After implementation, update `README.md` with the request/response contract and tax-after-discount rule. Update `docs/evidence-report.md` only with checks actually run and results actually observed.

## Completion criteria

The enhancement is ready for human review when:

- All server, persistence, idempotency, UI, and failure behaviors above are implemented.
- Existing invoices remain readable without data rewriting.
- Existing zero-discount idempotency records remain replayable.
- The complete automated suite passes using temporary databases.
- Print preview is either inspected successfully or explicitly remains marked unverified.
- The final diff contains no unrelated changes.
