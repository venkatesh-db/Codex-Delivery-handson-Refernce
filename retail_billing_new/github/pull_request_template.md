## Business outcome and scope

- Change/evidence ID:
- User-visible outcome:
- Explicit non-goals:

## AI governance

- [ ] Evidence record added or updated under `governance/evidence/`.
- [ ] Profile, skill, agent, allowed paths, and actual actions are recorded.
- [ ] Every changed path is inside the evidence scope and represented by a recorded action.
- [ ] Exceptions or mistakes have corrective actions, or are explicitly unresolved.
- [ ] No persistent database, migration, deployment, destructive action, or secret access occurred without specific authorization.

## Verification

- [ ] `python3 tools/governance_check.py validate --stage review`
- [ ] `python3 -m py_compile app.py tools/governance_check.py`
- [ ] `python3 -m unittest discover -s tests -v`
- [ ] Human reviewer checked the diff and evidence rather than relying on the AI summary.
