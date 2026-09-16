import json
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import governance_check


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.policy_path = self.root / "policy.json"
        self.evidence_dir = self.root / "evidence"
        self.evidence_dir.mkdir()
        self.policy = {
            "schema_version": 1,
            "required_skill": "retail-coding-standards",
            "profiles": {"profile_sse": {"permission": "workspace-write", "allowed_agents": ["feature_implementer"]}, "profile_codex": {"permission": "read-only", "allowed_agents": ["bug_finder"]}},
            "agents": {
                "feature_implementer": {"permission": "workspace-write", "parent_profile": "profile_sse", "required_skill": "retail-coding-standards"},
                "bug_finder": {"permission": "read-only", "parent_profile": "profile_codex", "required_skill": "retail-coding-standards"},
            },
            "protected_paths": ["billing.sqlite3"],
            "required_checks": {
                "governance-policy": "safe governance-policy",
                "python-compile": "safe python-compile",
                "unit-and-http-tests": "safe unit-and-http-tests",
            },
            "prohibited_command_fragments": ["billing.sqlite3", "rm -rf"]
        }
        self.policy_path.write_text(json.dumps(self.policy), encoding="utf-8")
        self.record = {
            "schema_version": 1,
            "change_id": "change-1",
            "title": "Test change",
            "profile": "profile_sse",
            "skill": "retail-coding-standards",
            "agent": "feature_implementer",
            "scope": {"outcome": "Test governance", "allowed_paths": ["app.py", "governance/evidence/"], "forbidden_paths": ["billing.sqlite3"]},
            "actions": [{"actor": "feature_implementer", "operation": "implement", "target": "app.py", "outcome": "completed"}],
            "checks": [{"name": name, "command": f"safe {name}", "status": "passed"} for name in self.policy["required_checks"]],
            "exceptions": [],
            "human_approval": {"status": "pending", "approver": None, "reference": None},
            "corrective_actions": [],
            "state": "ready-for-review"
        }

    def tearDown(self):
        self.temp.cleanup()

    def write_record(self):
        (self.evidence_dir / "change.json").write_text(json.dumps(self.record), encoding="utf-8")

    def validate(self, stage="review", human_approved=False):
        self.write_record()
        return governance_check.validate(stage, human_approved, self.policy_path, self.evidence_dir)

    def test_review_accepts_authorized_pending_change(self):
        self.assertEqual(self.validate(), [])

    def test_rejects_read_only_write_action(self):
        self.record["profile"] = "profile_codex"
        self.record["agent"] = "bug_finder"
        self.record["actions"][0]["actor"] = "profile_codex"
        self.assertTrue(any("attempts a write" in error for error in self.validate()))

    def test_rejects_unauthorized_agent_and_protected_path(self):
        self.record["agent"] = "bug_finder"
        self.record["actions"][0]["target"] = "billing.sqlite3"
        errors = self.validate()
        self.assertTrue(any("not allowed" in error for error in errors))
        self.assertTrue(any("protected path" in error for error in errors))

    def test_rejects_action_outside_scope_and_path_traversal(self):
        self.record["actions"][0]["target"] = "README.md"
        self.assertTrue(any("outside allowed_paths" in error for error in self.validate()))
        self.record["actions"][0]["target"] = "../app.py"
        self.assertTrue(any("without traversal" in error for error in self.validate()))

    def test_rejects_wrong_or_duplicate_required_check(self):
        self.record["checks"][0]["command"] = "python3 anything.py"
        self.record["checks"].append(dict(self.record["checks"][1]))
        errors = self.validate()
        self.assertTrue(any("policy command" in error for error in errors))
        self.assertTrue(any("duplicate check" in error for error in errors))

    def test_actual_changed_paths_must_be_scoped_and_unprotected(self):
        self.write_record()
        errors = governance_check.validate(
            "review", False, self.policy_path, self.evidence_dir,
            changed_paths=["governance/evidence/change.json", "app.py", "README.md", "billing.sqlite3"],
        )
        self.assertTrue(any("outside the current evidence scope" in error for error in errors))
        self.assertTrue(any("is protected" in error for error in errors))

    def test_changed_paths_require_current_evidence_and_recorded_action(self):
        self.write_record()
        no_evidence = governance_check.validate(
            "review", False, self.policy_path, self.evidence_dir, changed_paths=["app.py"],
        )
        self.assertTrue(any("same change" in error for error in no_evidence))
        self.record["scope"]["allowed_paths"].append("README.md")
        self.write_record()
        unrecorded = governance_check.validate(
            "review", False, self.policy_path, self.evidence_dir,
            changed_paths=["governance/evidence/change.json", "README.md"],
        )
        self.assertTrue(any("no recorded action" in error for error in unrecorded))

    def test_release_requires_passed_checks_and_human_approval(self):
        self.record["checks"][0]["status"] = "failed"
        errors = self.validate("release")
        self.assertTrue(any("requires passed checks" in error for error in errors))
        self.assertTrue(any("human approval" in error for error in errors))

    def test_protected_environment_approval_unlocks_clean_release(self):
        self.record["state"] = "ready-for-release"
        self.assertEqual(self.validate("release", human_approved=True), [])

    def test_exception_requires_corrective_action_before_release(self):
        self.record["state"] = "ready-for-release"
        self.record["exceptions"] = [{"category": "test", "impact": "Observed failure", "evidence": "test output"}]
        errors = self.validate("release", human_approved=True)
        self.assertTrue(any("corrective_actions" in error for error in errors))

    def test_profile_may_record_no_subagent(self):
        self.record["agent"] = None
        self.record["actions"][0]["actor"] = "profile_sse"
        self.assertEqual(self.validate(), [])


if __name__ == "__main__":
    unittest.main()
