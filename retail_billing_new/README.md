# Retail billing — first version

A local, single-user Python billing app with a browser form, JSON API, and SQLite storage. No third-party packages are required.

## Run

```sh
cd retail_billing_new
python3 app.py
```

Open <http://127.0.0.1:8000>. The database is created at `retail_billing_new/billing.sqlite3`. Set `BILLING_DB`, `BILLING_HOST`, or `BILLING_PORT` to override the defaults. Bind to localhost for this unauthenticated version.

## Test

```sh
cd retail_billing_new
python3 -m unittest discover -s tests -v
```

## AI governance

AI-assisted changes use project profiles, the `retail-coding-standards` skill, bounded specialized agents, structured evidence records, and automated policy/test gates. Validate a change and view its local governance summary with:

```sh
python3 tools/governance_check.py validate --stage review
python3 tools/governance_check.py dashboard
```

The GitHub Actions workflow compares committed changed paths with the current evidence scope and recorded actions, runs policy validation, compilation, and the complete test suite, then publishes the governance dashboard as an artifact. A manually dispatched release gate additionally requires approval through the protected `production-approval` environment. It does not deploy this prototype. See [AI governance and observability](docs/ai-governance.md) for evidence, incident, privacy, and repository-setup requirements.

## Workflow and rules

Enter a customer, invoice-level discount and tax percentages, and at least one product name, quantity, and unit price. Product names and prices are entered for each sale; there is no persistent catalog. Review the form, then save. The backend validates and calculates totals, saves the invoice and all snapshots together, and returns the final bill. Find an older bill by invoice number or the recent list, then use the browser's print action.

The currency is **assumed USD**, pending a business decision. Unit prices have at most two decimal places, quantities three, and discount and tax rates two. Quantities must be positive; prices may be zero; discount and tax are each 0–100%. Each line's `quantity × unit price` is rounded half-up to cents. The invoice discount is calculated on the summed rounded lines and rounded half-up to cents. Tax is then calculated on the discounted subtotal and rounded half-up to cents. This discount-before-tax order is a first-version product assumption, not a jurisdiction-specific tax guarantee. The API ignores browser-supplied totals and discount amounts. Product names, quantities, prices, rates, and calculated cents remain on the saved invoice. Database IDs are local invoice numbers, not a legal numbering scheme.

Saved invoices cannot be edited or cancelled. Returns, payments, a product catalog, statutory tax rules, multiple currencies, users, and stores are outside this first version. Invoice creation requires an idempotency key so exact retries do not create duplicate invoices. Do not use this as a production point-of-sale system without deciding the other open business rules in [the evidence report](docs/evidence-report.md).

## API

`POST /api/invoices` accepts `application/json` and requires a UUID in the `Idempotency-Key` header:

```http
Idempotency-Key: 672300a7-a464-457e-8a2e-d0e672cc8c3a
```

```json
{"customer_name":"Avery Lee","discount_rate":"10","tax_rate":"8.25","items":[{"product_name":"Notebook","quantity":"2","unit_price":"4.50"},{"product_name":"Coffee beans","quantity":"0.5","unit_price":"12.00"}]}
```

The first successful submission returns `201` with the stored invoice and server-calculated `subtotal_cents`, `discount_cents`, `tax_cents`, and `total_cents`. The `discount_rate` field is optional and defaults to zero; an explicit zero and an omitted value are equivalent. Repeating the same key and invoice returns the original invoice with `200`; reusing a key for different invoice content, including a different nonzero discount, returns `409`. Missing or malformed keys and other invalid input return `400` and `{"error":"..."}` without saving anything. Storage failures return `503`. `GET /api/invoices/{id}` retrieves a full invoice; older invoices without a discount snapshot return `"discount_rate":"0"` and `"discount_cents":0` while retaining their stored historical totals. `GET /api/invoices` lists the 50 newest summaries. Invoices carry a `currency` field; the current value is `USD`.

## Design

One standard-library server handles static UI delivery and JSON endpoints with at most 16 concurrent request handlers. `prepare_invoice` owns validation and monetary calculation. SQLite owns atomic persistence of each invoice, its lines, discount snapshot, and idempotency record in one transaction. Invoice lines and discounts are snapshots, so later product or pricing features do not change historical bills. This keeps setup small, but the server has no authentication or broader operational controls. See [docs/evidence-report.md](docs/evidence-report.md) for requirement and outcome gaps.
