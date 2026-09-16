# AI-assisted development conversation and decision journal

This file is a shareable learning record for `retail_billing_new`. It captures the user-visible prompt sequence, available assistant responses, engineering decisions, evidence, and corrections through 2026-09-15.

It does **not** contain private chain-of-thought, hidden system/developer instructions, security credentials, or internal tool payloads. Those are not project artifacts and must not be exposed. Earlier responses that are not available verbatim in the retained task context are explicitly recorded as concise response summaries. Recent responses are preserved more closely.

For a structured workflow explanation, see [docs/codex-governed-workflow-training.md](docs/codex-governed-workflow-training.md). For the earlier project handoff, see [docs/conversation-handoff.md](docs/conversation-handoff.md).

## How to learn from this journal

Do not treat an assistant response as proof. Follow the evidence chain:

```text
Prompt
  -> interpreted outcome and constraints
  -> selected profile / skill / agent
  -> permitted action
  -> source or test evidence
  -> review and correction
  -> human decision
```

## Conversation ledger

### 1. Project selection and automatic context

**User prompts**

> Day2 training

> retail_billing_new -> In this Project which file is loaded automatically?

> We know AGENTS.md is the first file Codex will read?

> Make sure you point to this project folder: retail_billing_new. We are going to work on this project only.

> Currently for the Codex agent, which permission is set on this project?

**Assistant response summary**

The work was scoped to `retail_billing_new`. `AGENTS.md` was identified as durable repository guidance, while the active sandbox/permission profile was distinguished from documentation. A Markdown instruction cannot grant filesystem authority beyond the active sandbox.

**Learning point**

Repository instructions guide behavior; sandbox permissions enforce filesystem access. Both must agree.

### 2. Evidence-first, read-only diagnosis

**User prompt**

> Run read-only. Do not modify files or run migrations. Locate code quality issues, identify gaps and memory issues, build a minimal deterministic retail reproduction, and state root cause with CONFIRMED separated from HYPOTHESIS. Report as ROOT CAUSE / EVIDENCE / REPRO / PROPOSED TEST / RISK. Do not write the fix.

**Assistant response summary**

Codex inspected the project read-only, reported evidence-backed findings, separated confirmed behavior from hypotheses, and avoided implementing fixes. The user then requested the root-cause evidence in a new `bugs.md`-style document.

**Learning point**

Diagnosis should establish reproduction and cause before implementation. A role label does not authorize writes when the prompt is read-only.

### 3. Initial profile separation

**User prompts**

> Profile_coder is write and read operation on this code base and Profile_codex should have only read operation. Profile_codex is operated by AI; Profile_coder is focused by the human coder to implement code.

> Now modify the code.

> Use profile_coder to implement plan.md.

> List all profiles.

> Install Profile_coder at Codex.

**Assistant response summary**

The conversation refined profile responsibilities several times. The final project policy differs from the early proposal: `profile_coder` is read-only guidance for the human coder, `profile_codex` is read-only diagnosis/review, and `profile_sse` is the project’s write-enabled enhancement coordinator.

**Correction retained**

Early role descriptions were not treated as permanent truth. The current source of truth is [AGENTS.md](AGENTS.md) and `.codex/agents/*.toml`.

### 4. Duplicate invoices and bounded concurrency

**User prompt**

> Implement the approved plan: require a UUID Idempotency-Key, persist request mappings atomically, replay matching requests with 200, reject conflicting reuse with 409, return 400 for missing/invalid keys, preserve existing invoices, and cap concurrent HTTP request threads at 16. Update browser behavior, tests, README, and evidence. Use temporary databases only.

**Assistant response summary**

The application gained idempotent invoice creation and a bounded 16-handler server. Tests covered replay, conflict, malformed keys, atomic rollback, fresh database connections, and concurrency slot recovery. The persistent database was not used as a test fixture.

**Learning point**

Retries, transaction boundaries, and concurrency limits are business-reliability behavior and require deterministic tests—not only code inspection.

### 5. Profiles, skills, and specialized subagents

**User prompts**

> Codex, tell me the number of profiles in this project. When a developer uses this project, direct the developer to use these profiles only; general Codex agents should not be involved.

> Both profiles need to be configured at project level.

> Project-level configuration: Codex should not modify code, only read—even Markdown.

> Show a sandbox diagram of this project.

> Explain each profile in depth with a diagram.

> profile_codex is mapped to which skill?

> Use profile_codex with the existing retail-coding-standards skill.

> How many skills are in this project?

> Explain the difference between profiles and skills and their benefits with a diagram.

> We map profiles with skills and subagents so each role performs a specific task with specialized skill.

**Assistant response summary**

The project established profiles for authority and permissions, a retail-specific skill for engineering method, and bounded subagents for specialized execution. General-agent use was prohibited by project guidance.

```text
Profile  -> what the role may do
Skill    -> how the work should be performed
Subagent -> one bounded delegated responsibility
Evidence -> what demonstrates the result
```

### 6. Read-only bug-finder subagent

**User prompt**

> Create a bug_finder subagent: profile_codex / Read-only / retail-coding-standards / bug_finder / Evidence-backed diagnosis.

**Assistant response summary**

The project-local `bug_finder` was defined as a read-only subagent used only by `profile_codex`. It cannot implement fixes or delegate further.

**Reusable prompt requested by the user**

```text
Use profile_codex and the retail-coding-standards skill.
Delegate the bounded investigation to bug_finder.
Investigate <specific issue> read-only.
Report severity, file:line, trigger, expected behavior, actual behavior,
impact, and evidence. Separate CONFIRMED from HYPOTHESIS.
Do not modify files, databases, or migrations.
```

### 7. SSE enhancement role

**User prompts**

> For the developer role SSE and a new enhancement, create a prompt that uses a profile, skill, and agent to complete the task.

> Can you implement now?

> Can we create a new read/write profile with a subagent to accomplish the task?

> profile_sse workspace-write implements approved enhancements; add a subagent that performs code implementation.

> profile_sse / workspace-write / retail-coding-standards / feature_implementer / coordinates approved enhancements. Create it.

**Assistant response summary**

`profile_sse` became the only write-enabled project profile for explicitly approved enhancements. It may delegate only to `feature_implementer`, owns review/integration, uses temporary test databases, and cannot deploy, merge, run persistent migrations, or perform destructive operations without separate authorization.

### 8. Invoice discount plan and implementation

**User prompt**

> Role: Senior Software Engineer. Project: retail_billing_new. Use profile_sse and retail-coding-standards. Add an invoice-level discount percentage. Accept 0–100% with at most two decimal places, use Decimal and half-up rounding, reject invalid values atomically, preserve existing invoices and idempotency, display and print the discount, and add unit and HTTP tests. Codex must remain read-only while planning.

**Assistant response summary**

A decision-complete plan was prepared in [document.md](document.md). The user later changed the project-level configuration to allow `profile_sse` implementation and explicitly authorized implementation through `feature_implementer`.

**User implementation prompt**

> Use profile_sse with the retail-coding-standards skill. Implement the approved invoice-discount plan in document.md. Delegate the bounded code implementation to feature_implementer, review its changes, and run the required tests. Do not modify billing.sqlite3 or run persistent migrations.

**Assistant response**

The enhancement was implemented with server validation, Decimal half-up calculations, discount-before-tax behavior, an additive snapshot table, legacy invoice compatibility, zero-discount fingerprint compatibility, browser display/printing support, tests, and documentation.

Observed validation:

```text
python3 -m py_compile app.py: passed
python3 -m unittest discover -s tests -v: 16 tests passed
git diff --check: passed
```

The persistent database timestamp and size remained unchanged. Browser print-preview appearance remained unverified.

### 9. Assessment of the automation

**User prompts**

> We have accomplished great automation with Codex working with evidence and the right methodology.

> Rate the automation skill in this project for real production.

> Codex working effectively with evidence and role-specific upskilling can automate work and improve productivity and time efficiency.

**Assistant response**

The development automation was assessed as strong, while production readiness remained lower because profiles are not a complete security boundary and the application still lacked production authentication, operations, backup/recovery, legal retail rules, deployment, and rollback controls.

The reusable operating model was summarized as:

```text
Business request
  -> role profile
  -> project skill
  -> specialized agent
  -> tests and evidence
  -> human review and decision
```

### 10. Governance and AI mistake observability

**User prompt**

> We want governance in this project and observability of AI mistakes.

**Assistant response**

The proposed controls included profile/skill/agent identity, files read or modified, commands and database targets, acceptance evidence, policy violations, failed tests, unresolved risk, deviations, human approvals, and corrective actions—while excluding secrets and customer data.

**User implementation prompt**

> Implement this automated workflow:
> Request -> policy gate -> profile + skill + specialized agent -> structured activity and evidence log -> tests + policy checks + change review -> human approval -> CI/deployment gate. Exceptions and mistakes -> governance dashboard -> corrective action / skill update.

**Assistant response**

The project added:

- [governance/policy.json](governance/policy.json)
- [tools/governance_check.py](tools/governance_check.py)
- [.github/workflows/governance.yml](.github/workflows/governance.yml)
- [.github/pull_request_template.md](.github/pull_request_template.md)
- [docs/ai-governance.md](docs/ai-governance.md)
- `governance/evidence/*.json`
- `tests/test_governance.py`

The first checker draft trusted declared scope without comparing it to the actual Git diff. Review identified the weakness. It was recorded as an exception, corrected with same-change evidence and `--base-ref` diff validation, and protected with regression tests.

Observed validation:

```text
Governance tests: 11 passed
Complete project suite: 27 passed
Governance review gate: passed
Dashboard: 3/3 required checks passed
Release gate: blocked pending real human approval
```

**Learning point**

This is the core mistake loop:

```text
Observed defect in AI work
  -> evidence record
  -> impact classification
  -> correction
  -> regression test
  -> policy/profile/skill update when warranted
```

### 11. Project and SSE ratings

**User prompts**

> We are a great project, correct?

> Rate this project as an SSE developer.

**Assistant response**

The project was rated approximately 8/10 as a well-engineered local prototype and 6/10 for production deployment. Strong areas included correctness, automated tests, governance, architecture, and data integrity. Remaining gaps included authentication, authorization, monitoring, backups, recovery, deployment/rollback, tax jurisdiction, legal numbering, payments, returns, and corrections.

No rating was presented as objective proof or production certification.

### 12. Encoding senior experience into Codex

**User prompt**

> I am a developer with ten years of real-world experience. To map that understanding to Codex, we need agents, skills, subagents, and profiles so it becomes specialized rather than generalized.

**Assistant response**

The assistant agreed with an important qualification: a role label cannot transfer ten years of judgment. Experienced decision patterns must be encoded as explicit invariants, permissions, failure rules, evidence requirements, tests, and escalation boundaries.

```text
Human experience
  -> profile: authority and responsibility
  -> skill: reusable engineering judgment
  -> subagent: bounded execution
  -> tests/evidence/policy
  -> human decision
```

### 13. Choosing the next governed enhancement

**User prompt**

> Create a new enhancement with the complete structured process and an end-to-end demonstration for the coder.

**Assistant clarification**

> Which new retail enhancement should we implement—for example, invoice notes, cashier reference, or payment method?

**User repeated the options, and the assistant recommended invoice notes.**

Reason: invoice notes exercise UI, API validation, persistence, retrieval, printing, idempotency, tests, and governance without introducing payment or tax-policy complexity.

Proposed contract:

- Optional note.
- Maximum 500 characters after server-side trimming.
- Immutable snapshot.
- Included in idempotency identity.
- Displayed and printed only when present.
- Legacy invoices return an empty note.
- Invalid notes return `400` and store nothing.

### 14. Invoice-notes policy gate and evidence log

**User prompt**

> Structured activity and evidence log, policy gate—reject unauthorized operations—for the above enhancement.

**Assistant response**

The pre-implementation evidence contract [2026-09-15-invoice-notes.json](governance/evidence/2026-09-15-invoice-notes.json) was created with:

```text
Profile: profile_sse
Skill: retail-coding-standards
Agent: feature_implementer
State: draft
Checks: 0/3 passed
Human approval: pending
Protected path: billing.sqlite3
```

The governance review passed. Focused policy tests demonstrated rejection of read-only writes, unauthorized agents, protected paths, and unrecorded changes. Invoice-note application code was not implemented, and no database or migration was changed.

### 15. Five-year feature traceability

**User prompt**

> In the future, after five years, I want Codex to trace the project features implemented.

**Assistant response**

Long-term traceability must live in version-controlled records rather than conversation memory:

```text
Feature ID
  -> evidence record
  -> architecture/business decision
  -> source and tests
  -> immutable commit and pull request
  -> approval and release
  -> incidents and corrections
```

Recommended durable additions were stable feature IDs, commit/PR/release references, append-only corrections, architecture decisions, tool/runtime versions, backups, retention policy, a generated feature index, and CI link validation.

### 16. Meaning of the invoice-notes JSON

**User prompt**

> 2026-09-15-invoice-notes.json is mostly documentation for future reference.

**Assistant response**

Correct—with an important distinction. Before implementation it is an authorization, scope, and acceptance contract. After implementation it should become evidence of actual actions, tests, deviations, corrections, approval, commit, PR, and release. Because CI reads it, it is also enforceable machine-readable policy input rather than prose alone.

### 17. Shareable conversation document

**User prompt**

> Save the beginning-to-end conversation chat so another coder can view the prompts and skills in a new Markdown file.

**Assistant response**

[docs/codex-governed-workflow-training.md](docs/codex-governed-workflow-training.md) was created as a 271-line training handoff. Its governance review passed. It excludes hidden reasoning, system instructions, secrets, and internal tool payloads. The persistent database remained unchanged.

### 18. This AI decision journal

**User prompt**

> Store every prompt in this conversation and response to learn the AI thinking in a new aithinking.md file.

**Assistant action and boundary**

This file was created to preserve the user-visible conversation, available responses, decisions, evidence, and corrections. It does not expose hidden chain-of-thought. Where early responses were unavailable verbatim, it records a clearly labelled summary rather than inventing quotations.

## Current project status at the end of this journal

Implemented and tested:

- Core invoice creation, persistence, retrieval, and browser UI.
- Server-owned Decimal monetary calculations.
- Atomic invoice snapshots.
- UUID idempotency behavior.
- Sixteen-handler concurrency bound.
- Invoice-level discount before tax.
- Project profiles, retail coding skill, and bounded subagents.
- Governance policy, evidence records, CI gates, dashboard, and mistake/correction tracking.

Pending or external:

- Invoice notes remain a governed draft, not an implemented feature.
- Human approval remains pending in current evidence records.
- GitHub branch protection and protected-environment reviewers require administrator configuration.
- The project is not deployed and is not production-ready.
- Authentication, authorization, monitoring, backup/recovery, deployment/rollback, and several legal retail rules remain unresolved.

## Final principle

The goal is not to imitate private AI thinking. The useful, auditable substitute is to preserve:

```text
What was requested
What was allowed
What was changed
Why the decision was made
What evidence was observed
What failed
How it was corrected
What remains for the human
```

That record can teach future coders, guide future Codex sessions, and expose mistakes without relying on unverifiable claims.

