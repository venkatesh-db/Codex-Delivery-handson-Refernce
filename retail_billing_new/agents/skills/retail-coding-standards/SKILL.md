---
name: retail-coding-standards
description: Apply shared coding and naming conventions when creating or changing Python, browser, SQL, or test code in retail_billing_new. Use for code-writing tasks in any assigned development role; skip documentation-only requests and read-only reviews.
---

# Retail billing coding standards

Apply these standards to the code being changed. Follow the user's task and `AGENTS.md`; inspect the relevant existing code and tests before choosing an implementation. Preserve established behavior unless the requested change intentionally alters it.

## Naming conventions across this project

- Choose names that express the billing concept and unit, not only the data type. Use `invoice_id`, `tax_rate`, `subtotal_cents`, and `unit_price_cents` as models. Add `_cents` to integer money amounts; do not use ambiguous names such as `amount` for values with different units.
- Python modules, functions, variables, and parameters use `snake_case`; classes use `PascalCase`; module constants use `UPPER_SNAKE_CASE`. Name actions with verbs (`prepare_invoice`, `fetch_invoice`) and stored values with nouns. Test methods use `test_<behavior_or_failure>`.
- JavaScript variables and functions use `camelCase` (`loadHistory`, `showInvoice`). HTML element IDs and CSS classes use `kebab-case` (`invoice-section`, `tax-label`). Keep UI labels meaningful to cashiers rather than exposing internal field names.
- SQL table and column names use `snake_case`. Keep established plural table names (`invoices`, `invoice_items`), singular identifiers (`invoice_id`), and explicit units (`total_cents`). Name new indexes or constraints for their table and purpose when they need a name.
- JSON API fields use `snake_case` to match the current contract (`customer_name`, `unit_price_cents`). HTTP paths use lowercase plural resources under `/api` (`/api/invoices`). Do not rename existing public fields, paths, database columns, or persisted meanings merely to improve style; treat such changes as compatibility or migration work.
- New Python and test filenames use `snake_case.py`; documentation filenames may use descriptive `kebab-case.md` as the existing docs do. Avoid one-letter names except short local iteration variables whose meaning is immediate.

## Design and interfaces

- Keep this small standard-library application simple. Add a dependency, service, or abstraction only for a concrete requirement; state the reason when doing so.
- Give validation, calculation, persistence, and presentation clear ownership. Treat HTTP input as untrusted; calculate billing totals on the server, never from client-supplied amounts.
- Keep API error behavior intentional and consistent. Do not expose database internals or exception details to clients. Maintain existing response shapes unless a contract change is part of the task.
- Design changes to saved invoice meaning explicitly: preserve historical snapshots and atomic header-plus-lines storage. Do not repurpose old columns or silently rewrite old invoices.

## Python and SQLite

- Follow the surrounding Python style: descriptive names, small focused functions, standard-library types, and explicit error handling where failures cross boundaries. Avoid broad exception catches that hide programming errors.
- Use `Decimal` for monetary and rate arithmetic, integer cents for persisted amounts, and the documented half-up rounding points. Do not calculate money through binary floats or trust formatted browser values.
- Validate type, range, precision, and collection size before writing. Use parameterized SQL, enforce foreign keys, and keep multi-row invoice writes in one transaction. Consider migration and compatibility before changing persisted schema.
- Keep the default server on loopback while unauthenticated. Do not add secrets or personal invoice data to logs or fixtures.

## Browser code

- Use the existing plain HTML, CSS, and JavaScript conventions for focused changes. Render customer and product values with text APIs, not HTML interpolation.
- Keep form labels, keyboard operation, error/status feedback, and print behavior usable. Let the server response be authoritative after save; handle failed requests without implying an invoice was saved.

## Verification and handoff

- Add or adjust tests for externally meaningful changed behavior, including failure and persistence paths when relevant. Prefer temporary SQLite databases; never use `billing.sqlite3` as a test fixture.
- Run focused checks and the applicable suite from the project directory: `python3 -m unittest discover -s tests -v`. If loopback binding is restricted, report that environment result and use the authorized mechanism to complete the HTTP test.
- Update `README.md` or `docs/evidence-report.md` when the API, billing rules, or verified outcomes change. Report what actually passed and what remains unverified.
