# AI governance and observability

This project treats AI output as proposed engineering work that must be constrained, evidenced, tested, and reviewed. Profiles and skills guide behavior; the policy checker and CI provide independent, reproducible enforcement for recorded work. They do not replace operating-system permissions, branch protection, or human judgment.

## Automated flow

```text
Request
  -> policy gate: profile, permission, skill, agent, scope, protected paths
  -> bounded implementation or read-only investigation
  -> structured evidence record in governance/evidence/
  -> policy validation, compilation, tests, dashboard artifact
  -> protected GitHub environment: production-approval
  -> release-policy validation
  -> deployment remains separately configured and authorized

Exceptions or mistakes
  -> evidence.exceptions[]
  -> CI dashboard artifact
  -> evidence.corrective_actions[]
  -> profile, skill, test, or policy update
```

## Evidence record

Every AI-assisted change must have one JSON record changed in the same Git change. It identifies the business outcome, selected profile and skill, optional specialized agent, allowed and forbidden paths, performed actions, actual checks, exceptions, corrective actions, and approval state. CI compares the actual changed paths with that current record: every path must be in scope and represented by an action, while protected paths are always rejected. Historical evidence records cannot authorize a new change. Do not store prompts, secrets, personal invoice data, database contents, access tokens, or unnecessary source excerpts.

Check status is one of `pending`, `passed`, `failed`, or `blocked`. Record only observed results. A release requires every policy-required check to be `passed`. Human approval can be recorded with an approver and durable reference, or supplied by the protected `production-approval` GitHub environment after its required reviewer approves the run.

## Commands

```sh
python3 tools/governance_check.py validate --stage review
python3 tools/governance_check.py dashboard
python3 tools/governance_check.py validate --stage release
```

The release command intentionally fails while human approval is pending. CI uses `--human-approved` only after the protected environment has granted approval. That flag must not be used as a local substitute for review.

Pull-request and push validation supplies a Git base revision with `--base-ref`, which checks the committed diff against the evidence scope and actions. A local review command without `--base-ref` validates the evidence structure only; it does not inspect working-tree changes.

## Mistake handling

When an AI mistake or policy exception is found, add a concise entry to `exceptions` with category, impact, and evidence. Add a corrective action naming its owner, change, and verification status. Do not erase the incident when corrected. Update a profile, skill, policy, or regression test only when the evidence shows that control would prevent recurrence.

## Repository setup required

In GitHub, protect the default branch, require the `policy-and-tests` job, require pull-request review, and create a protected environment named `production-approval` with required human reviewers. The workflow deliberately does not deploy this local prototype; deployment needs a separately approved target, rollback procedure, and operational controls.
