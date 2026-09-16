# Codex governed-development training conversation

This document preserves the project-relevant, user-visible conversation and reusable prompts from the beginning of `retail_billing_new` through its role-specific profiles, invoice enhancements, governance automation, and long-term traceability discussion. It is written for another coder joining the project.

It is a faithful chronological handoff, not a word-for-word export. Repeated questions and spelling variations are normalized for readability. Hidden system instructions, private model reasoning, tool payloads, secrets, and unrelated machine information are intentionally excluded. Earlier project history is also available in [conversation-handoff.md](conversation-handoff.md).

## 1. Initial project orientation

The user established that all work must point specifically to `retail_billing_new`. Early questions focused on:

- Which project instructions Codex loads automatically.
- Whether `AGENTS.md` is the first project instruction file Codex reads.
- What permissions the active Codex agent has.
- How profiles differ from skills and specialized subagents.
- How to prevent a general-purpose agent from modifying this project.

The durable result is [AGENTS.md](../AGENTS.md), which directs every project task to a named project-local profile and records the retail billing invariants and safety boundaries.

## 2. Read-only defect diagnosis methodology

The user introduced an evidence-first diagnostic structure:

```text
Run read-only. Do not modify files or run migrations.

Steps, in order:
1. Locate the relevant code and cite file:line.
2. Identify how gaps, nulls, failures, or resource issues are handled.
3. Build a minimal deterministic reproduction.
4. State the root cause, separating CONFIRMED from HYPOTHESIS.

Report as:
ROOT CAUSE / EVIDENCE / REPRO / PROPOSED TEST / RISK

Do not write the fix. I will review the diagnosis first.
```

This became the basis for `profile_codex` plus the read-only `bug_finder` subagent. Diagnosis and implementation were deliberately separated.

## 3. Project profiles, skill, and specialized agents

The project now uses three selectable profiles and two bounded subagents:

| Profile | Permission | Required skill | Allowed subagent | Responsibility |
| --- | --- | --- | --- | --- |
| `profile_codex` | Read-only | `retail-coding-standards` | `bug_finder` | Diagnosis, review, and evidence gathering |
| `profile_coder` | Read-only | Project guidance | None | Decision-complete guidance for a human coder |
| `profile_sse` | Workspace write | `retail-coding-standards` | `feature_implementer` | Coordinate approved enhancements, review, and validation |

| Specialized subagent | Permission | Parent profile | Result |
| --- | --- | --- | --- |
| `bug_finder` | Read-only | `profile_codex` | Evidence-backed defect findings |
| `feature_implementer` | Workspace write | `profile_sse` | Bounded implementation and focused validation |

The project skill is [.agents/skills/retail-coding-standards/SKILL.md](../.agents/skills/retail-coding-standards/SKILL.md). It contains naming rules, API and persistence expectations, Decimal and integer-cent requirements, transaction boundaries, browser safety, and test/evidence practices.

The conceptual division is:

```text
Profile     = authority, permission, role, and stopping boundaries
Skill       = reusable project-specific engineering method
Subagent    = one bounded specialist executing a delegated task
AGENTS.md   = durable project context and routing rules
Tests       = executable behavioral evidence
Governance  = enforcement, audit trail, mistakes, and approvals
```

## 4. Reusable bug-finder prompt

```text
Role: Read-only retail billing investigator
Project: retail_billing_new

Use profile_codex and the retail-coding-standards skill.
Delegate only the bounded investigation to bug_finder.

Investigate: <specific symptom or code path>

Do not modify files, databases, or migrations.
Provide severity, file:line, trigger, expected behavior, actual behavior,
business impact, and reproducible evidence. Separate CONFIRMED findings
from HYPOTHESES. Report the proposed regression test, but do not fix it.
```

## 5. Duplicate-invoice and concurrency implementation

The user approved a concrete implementation plan to:

- Require a UUID `Idempotency-Key` for invoice creation.
- Return `201` for the first successful request.
- Return the original invoice with `200` for an exact replay.
- Return `409` when the same key is reused for different content.
- Persist invoice header, lines, and request mapping atomically.
- Reuse the browser key for an unchanged retry.
- Bound HTTP request handlers to 16 concurrent workers.
- Test with temporary SQLite databases only.

The implementation preserved loopback binding, server-owned monetary calculations, historical data, and controlled failures. Persistent `billing.sqlite3` was not used as test data.

## 6. Reusable SSE enhancement prompt

The following prompt pattern was developed for an approved enhancement:

```text
Role: Senior Software Engineer (SSE)
Project: retail_billing_new

Use profile_sse and the retail-coding-standards skill.
Delegate one concrete, bounded implementation task to feature_implementer.

Enhancement:
<business capability>

Expected outcome:
<observable user outcome>

Acceptance criteria:
1. <success behavior>
2. <validation and failure behavior>
3. <persistence and compatibility behavior>
4. <UI/API behavior>
5. <unit and HTTP integration evidence>

Preserve existing invoices, idempotency, monetary calculations, and
transaction atomicity. Use temporary databases only. Do not modify
billing.sqlite3 or run persistent migrations. Review delegated changes,
run required tests, record actual evidence, and leave release pending
human approval.
```

## 7. Invoice-level discount enhancement

The user approved an invoice-level discount percentage with these rules:

- Rate from 0% through 100%, with at most two decimal places.
- Server-side `Decimal` arithmetic and half-up rounding.
- Discount applied to subtotal before tax.
- Original subtotal, discount, tax, and final total preserved.
- Invalid discounts rejected without partial writes.
- Existing invoice retrieval and idempotency compatibility preserved.
- Discount displayed and included in printed invoice content.
- Unit and HTTP integration tests added.

The approved plan is [document.md](../document.md). The implementation added an additive `invoice_discounts` snapshot table, legacy zero-discount behavior, nonzero-discount fingerprinting, UI support, tests, and documentation.

Observed validation at completion:

```text
python3 -m py_compile app.py
Exit: 0

python3 -m unittest discover -s tests -v
Ran 16 tests
OK
```

The persistent database timestamp and size were checked before and after and remained unchanged. Browser print preview remained explicitly unverified.

## 8. Governance and AI mistake observability

The user requested this lifecycle:

```text
Request
  -> policy gate: reject unauthorized operations
  -> profile + skill + specialized agent
  -> structured activity and evidence log
  -> tests + policy checks + change review
  -> human approval
  -> CI/deployment gate

Exceptions and mistakes
  -> governance dashboard
  -> corrective action / skill update
```

The project now implements that model through:

- [governance/policy.json](../governance/policy.json)
- [tools/governance_check.py](../tools/governance_check.py)
- [.github/workflows/governance.yml](../.github/workflows/governance.yml)
- [.github/pull_request_template.md](../.github/pull_request_template.md)
- [docs/ai-governance.md](ai-governance.md)
- Machine-readable records under `governance/evidence/`
- Governance regression tests in `tests/test_governance.py`

The gate validates profile and agent mappings, required skill, permissions, repository-relative scope, protected paths, exact required commands, lifecycle state, exceptions, corrective actions, and human approval. CI can compare actual Git changes with the evidence record supplied in the same change.

During its own implementation, review found that the first draft trusted declared paths without comparing them with the actual Git diff. That mistake was recorded, corrected with `--base-ref` diff validation, and covered by regression tests instead of being erased from history.

Observed validation after governance implementation:

```text
Governance tests: 11 passed
Complete project suite: 27 passed
Governance review gate: passed
Dashboard: 3/3 checks passed
Release gate: correctly blocked pending human approval
```

Repository administrators still need to configure branch protection, required CI status checks, required pull-request review, and required reviewers for the `production-approval` environment. The workflow deliberately does not deploy this local prototype.

## 9. Invoice-notes governed pre-implementation record

For the next end-to-end demonstration, invoice notes were selected because they exercise UI, validation, persistence, retrieval, printing, idempotency, testing, evidence, and review without introducing payment-processing or tax-policy complexity.

Proposed behavior:

- Optional invoice note.
- Maximum 500 characters after server-side trimming.
- Immutable invoice snapshot.
- Returned by the API and displayed/printed only when present.
- Included in idempotency identity.
- Existing invoices return an empty note.
- Invalid input returns `400` and stores nothing.

The pre-implementation contract is [2026-09-15-invoice-notes.json](../governance/evidence/2026-09-15-invoice-notes.json). Its current state is deliberately:

```text
State: draft
Checks: 0/3 passed
Human approval: pending
Application implementation: not started
```

The policy review passed, and focused tests demonstrated rejection of read-only writes, unauthorized agents, protected paths, and unrecorded changes. This JSON file is both future documentation and machine-readable policy input; it is not evidence that the feature already exists.

## 10. Long-term traceability

Codex cannot rely on a five-year-old conversation remaining available. Durable traceability must live in version-controlled project records:

```text
Feature ID
  -> evidence record
  -> requirement and decision
  -> profile / skill / agent
  -> source and tests
  -> commit and pull request
  -> human approval
  -> release
  -> later incidents and corrections
```

For each completed feature, update—not fabricate—the observed checks, changed files, deviations, approval reference, commit hash, pull request, and release tag. Completed historical records should not be silently rewritten; corrections should remain visible and linked.

## 11. Guidance for another coder

Before starting work:

1. Read [AGENTS.md](../AGENTS.md).
2. Select the correct profile.
3. Read the required skill completely.
4. Inspect current source, callers, tests, documentation, and Git state.
5. Create or update the feature evidence record with a narrow allowed-path scope.
6. Keep `billing.sqlite3` protected and use temporary databases for tests.
7. Record actions and observed results accurately.
8. Run the governance review gate and required project checks.
9. Record exceptions and corrective actions rather than hiding mistakes.
10. Require human review before the release gate.

Useful local commands:

```sh
python3 tools/governance_check.py validate --stage review
python3 tools/governance_check.py dashboard
python3 -m py_compile app.py tools/governance_check.py
python3 -m unittest discover -s tests -v
```

Do not run the release gate with `--human-approved` as a substitute for an actual protected-environment approval. Do not claim deployment, production readiness, print acceptance, or business correctness beyond the evidence actually collected.

