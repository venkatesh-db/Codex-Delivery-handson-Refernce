# Evidence report

Working-state record for `retail_billing_new`. Source: attached project brief (`pasted-text.txt`); older folders were inspected as references, not treated as agreed behavior.

## Scope and decisions before implementation

A single local cashier enters a customer and one or more free-text products, quantities, and prices, then saves an invoice. The API owns validation, half-up cent rounding, and the SQLite transaction. The saved invoice is final for this version; recent invoices can be retrieved and printed. Product names and prices are captured on each line, with no catalog dependency. The browser does not supply totals.

| Unknown | Classification and temporary decision | Effect of later change |
| --- | --- | --- |
| Currency | Safe first-version assumption: USD display | Historical invoices need a stored currency code before multi-currency use. |
| Tax jurisdiction and rates | Safe first-version assumption: cashier supplies one invoice-level percentage | Jurisdiction-specific rules would change calculation and require tax metadata on new invoices. |
| Catalog versus line reuse | Safe first-version assumption: reusable line logic and free-text products; catalog deferred | A catalog would add selection and price ownership; saved snapshots remain valid. |
| Discounts | Invoice-level percentage, applied before tax; 0–100% with two decimal places | Jurisdiction-specific discount and tax interaction may require a future policy/version change. |
| Numbering | Safe first-version assumption: database-generated sequential local ID | Legal numbering may require a separate immutable series and migration. |
| Corrections, cancellation, returns | Deferred | Need immutable adjustment or status history, not edits to final invoices. |
| Multiple users or stores | Deferred | Requires authentication, authorization, store-specific series, and concurrency policy. |

Acceptance: create a multi-product invoice, retrieve the same persisted lines and totals in a fresh request, reject invalid input without storage, and verify rounding at line and tax boundaries.

## Traceability

| ID | Retail requirement and source | Acceptance criterion | Implementation reference | Verification check | Observed evidence | Status | Remaining gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R1 | UI submission; brief §Domain | Enter multiple products and save | `index.html` form and submit handler; `app.py` POST | Browser entry and save on 2026-09-14 | Invoice #1 displayed Notebook and Coffee beans; $16.24 total | Verified | None for first-version scope |
| R2 | API validation/calculation; brief §Implementation | Server totals and invalid input | `app.py` `prepare_invoice`, `Handler.do_POST` | 10-test suite, HTTP integration test | POST returned 201 with authoritative totals; exact retry returned 200; conflicting key returned 409; invalid keys and bad quantity returned 400 | Verified | Jurisdiction tax policy remains a requirement gap |
| R3 | Database persistence; brief §Domain | Atomic save and fresh retrieval | `app.py` `create_invoice`, `fetch_invoice`, schema | Fresh-connection retrieval and rollback tests | Stored rows matched calculated amounts; forced line and idempotency-record failures left no partial invoice data | Verified | No backup or operational recovery plan |
| R4 | Reusable different products; brief §Domain | Different names/prices without code changes | Free-text `index.html` rows; `app.py` invoice line snapshot | Browser two-product entry | Notebook and Coffee beans with distinct prices saved on one invoice | Verified | Persistent catalog deferred by assumption |
| R5 | Print/retrieve; brief §Requirement gap | Saved bill visible and printable | `index.html` lookup and print button | Reloaded page; opened invoice #1; inspected screen | Same two lines and $16.24 rendered; print button present | Partial | Printed page/PDF not inspected |
| R6 | Approved invoice discount enhancement | Validate, calculate, persist, retrieve, display, and safely retry an invoice-level percentage | `app.py` discount validation/calculation and companion table; `index.html` form and totals | 16-test suite using temporary SQLite databases | Verified discount-before-tax totals, half-up boundaries, validation, legacy retrieval/fingerprints, replay/conflict, HTTP behavior, and atomic rollback | Verified | Jurisdiction-specific policy and print preview remain unverified |

## Requirement gaps

| Rule and evidence | Why it matters | Owner | Temporary assumption | Status |
| --- | --- | --- | --- | --- |
| Currency unspecified in brief | Display and historical meaning | User | USD | Open |
| Tax law unspecified in brief | Correct taxable amount | User | One manually entered rate | Open |
| Discount policy unspecified in original brief | Sale price and taxable amount | User | Invoice-level percentage applied before tax | Implemented as first-version product assumption |
| Correction/return policy unspecified | Legal audit trail | User | No modification after save | Deferred |
| Multi-store/users unspecified | Access and numbering | User | Single local user/store | Deferred |

## Implementation gaps

| Criterion and reference | User-visible effect | Next concrete change | Status |
| --- | --- | --- | --- |
| R5 printable invoice, `index.html` CSS and `window.print()` | Print action exists, but output layout has not been accepted | Inspect print preview against an agreed invoice template | Deferred pending invoice-format decision |

No other agreed first-version criterion is known to be missing. Catalog and corrections remain requirement decisions rather than defects against agreed scope. Jurisdiction-specific discount and tax treatment remains a policy gap.

## Outcome gaps

| Expected outcome | Exact check needed | Observed | Why insufficient | Status |
| --- | --- | --- | --- | --- |
| Retail-ready printed bill | Open print preview or save PDF and inspect the output against a supplied invoice format | Screen bill and print button inspected; print output not inspected | No approved format or printed-page evidence | Unverified |
| Production retail suitability | Agree currency/tax/numbering/corrections/access rules, then test against them | Only local first-version behavior tested | Business rules unresolved | Unverified |

## Verification record

Environment: macOS, Python 3.14.4, Python standard library, local loopback server, temporary SQLite database. Code state: `retail_billing_new` working files after final test edit on 2026-09-14; no commit created. Self-review only, not independent review.

- `python3 -m py_compile retail_billing_new/app.py`: exit 0.
- `python3 -m py_compile app.py`: exit 0 on 2026-09-15 after the idempotency and concurrency changes.
- `python3 -m unittest discover -s tests -v` from the project folder: exit 0, ten tests, `OK` on 2026-09-15. The sandboxed run could not bind loopback ports; the authorized rerun verified HTTP statuses 201, 200, 409, 400, and 404, transactional rollback, sequential and simultaneous retry handling, fresh-connection replay, and a 17-request scenario capped at 16 simultaneous handlers.
- `python3 -m py_compile app.py`: exit 0 on 2026-09-15 after the invoice-discount enhancement.
- `python3 -m unittest discover -s tests -v` from the project folder: exit 0, sixteen tests, `OK` on 2026-09-15 after the invoice-discount enhancement. The authorized loopback run verified discount validation and half-up calculation, discount-before-tax totals, 100% discount, legacy invoice retrieval and zero-discount fingerprint compatibility, normalized nonzero-discount replay and conflict, rollback on discount persistence failure, HTML elements, HTTP statuses, and the existing concurrency bound. All test databases were temporary.
- Browser on `http://127.0.0.1:8765/`: entered Notebook ×2 @ $4.50 and Coffee beans ×0.5 @ $12.00 with 8.25% tax. Save displayed invoice #1 with line totals $9.00 and $6.00, subtotal $15.00, tax $1.24, total $16.24. Reloaded page and opened invoice #1 by number; same values rendered. Screen view inspected; print output was not.
- Direct SQLite query of temporary database: invoice row `(1, USD, Test Customer, 1500, 124, 1624)` cents; lines `(Notebook, 2, 450, 900)` and `(Coffee beans, 0.5, 1200, 600)`. These match the browser bill. Unit test also reopened a fresh database connection.
- Forced trigger failure on line insertion: test observed zero invoice headers and zero lines afterward, demonstrating rollback for that case.

## Readiness

A local retail user can enter different products and an invoice-level discount, create a final USD-assumed invoice with retry protection, retrieve it by number, and use the print action. Currency, jurisdiction-specific discount/tax treatment, legal numbering, and correction rules still need business decisions. Catalog, returns, payments, authentication, and multi-store support are unimplemented. Idempotent invoice creation, the 16-handler concurrency bound, and the discount enhancement are verified by the automated results recorded above; the printed page remains unverified until a human inspects print preview.
