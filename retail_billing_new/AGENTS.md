# Retail billing project guidance

These instructions apply to work inside `retail_billing_new`, regardless of the development role assigned in a prompt. The user is the principal architect and retains business and architecture decision authority. Follow the current user request first; use this file for durable project context, and verify code that is relevant to the task rather than treating this summary as proof of current behavior.

## Required project profiles

All Codex work in this project must use one of the three project-local profiles in `.codex/agents`. Do not use a general Codex agent, the parent workspace's `bug_finder`, or any unlisted agent/subagent for project work.

- Use `profile_codex` for investigation, diagnosis, review, explanation, and evidence gathering. It is technically restricted to `sandbox_mode = "read-only"`, must apply `.agents/skills/retail-coding-standards/SKILL.md`, and may delegate only a concrete bounded investigation to the project-local read-only `bug_finder` subagent.
- Use `profile_coder` for read-only implementation planning and guidance provided to the human coder. It is also technically restricted to `sandbox_mode = "read-only"`; the human coder alone applies code, test, configuration, documentation, and database changes.
- Use `profile_sse` only for a user-approved enhancement that requires implementation. It uses `sandbox_mode = "workspace-write"`, must apply `.agents/skills/retail-coding-standards/SKILL.md`, and may delegate implementation only to the project-local write-enabled `feature_implementer` subagent.

The project-local `bug_finder` is a subagent, not a user-selectable profile. It may be invoked only by `profile_codex`, must apply the retail coding standards skill, must return evidence to `profile_codex`, and may not delegate further. `profile_coder` may not use subagents.

The project-local `feature_implementer` is a subagent, not a user-selectable profile. It may be invoked only by `profile_sse` for a concrete, bounded, explicitly approved enhancement, must apply the retail coding standards skill, must return implementation and validation evidence to `profile_sse`, and may not delegate further. `profile_sse` owns review and integration of its work.

If a developer starts project work without selecting a profile, direct them to `profile_codex` for investigation/review, `profile_coder` for read-only implementation guidance, or `profile_sse` for an approved enhancement requiring implementation. Only `profile_sse` and its `feature_implementer` may modify project files, and only within the explicitly approved enhancement scope. Persistent-database migrations, deployment, merge, destructive operations, and external communication require separate explicit authorization.

## Project and boundaries

- This is a local, single-user retail billing prototype built with Python's standard library, a browser UI, and SQLite. It has no third-party package requirements.
- `app.py` serves the UI and JSON API, validates inputs, calculates money with `Decimal`, and persists invoice headers and line snapshots in one SQLite transaction. `index.html` contains the cashier form, invoice lookup, and print action. `tests/test_app.py` contains unit and HTTP integration tests.
- Read `README.md` for the current run/API contract and `docs/evidence-report.md` for verified behavior, assumptions, and open gaps. `docs/conversation-handoff.md` is historical context; check current code before relying on it.
- Keep the server bound to loopback by default. The app has no authentication and is not approved as a production point-of-sale system.

## Business invariants in the current version

- The server validates invoice input and owns all calculated totals. Never trust totals sent by the browser.
- Store the invoice and all its lines atomically. Preserve historical product names, quantities, prices, rates, currency, and cent amounts as invoice snapshots.
- Use decimal arithmetic and the documented half-up rounding policy for monetary calculations. Validate quantity, price, tax precision, and bounds at the API boundary.
- Saved invoices are final in this version. Do not silently introduce editing, deletion, or cancellation semantics that rewrite historical bills.

## Open business decisions

USD, a cashier-entered invoice-level tax rate, and database IDs as invoice numbers are first-version assumptions, not approved legal or retail policies. Duplicate-submission handling is decided: invoice creation requires a UUID idempotency key, exact retries return the original invoice, and conflicting key reuse is rejected. Discounts, returns, payments, a product catalog, and multiple users or stores remain undecided or deferred. Ask the user when a task depends on one of these open rules; otherwise keep changes within the established first-version scope. Do not claim production readiness from the existing tests.

## Working and verification expectations

- For every task that creates or changes application or test code, read and apply `.agents/skills/retail-coding-standards/SKILL.md`, regardless of the assigned development role. Documentation-only work and read-only reviews do not require it. This project instruction makes the skill's use explicit even when automatic skill selection is unavailable.
- Check repository state and inspect the relevant implementation, callers, and tests before editing. Preserve unrelated work and use the simplest change that meets the request.
- Run focused checks for changed behavior. The standard suite is `python3 -m unittest discover -s tests -v` from this directory; its HTTP test needs permission to bind a local loopback socket. Use a temporary database for validation and do not modify `billing.sqlite3` as test data.
- For billing behavior changes, update `README.md` and `docs/evidence-report.md` as needed. Distinguish unresolved requirements, missing implementation, and unverified outcomes. Report actual checks and remaining limits; a passing suite covers only its tested cases.
- For reviews, give actionable findings with file references and impact. For implementation, deliver the code and verification without routine approval pauses. Escalate only decisions that materially change business meaning or require authorization beyond the task.
