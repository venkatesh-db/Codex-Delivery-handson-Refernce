#!/usr/bin/env python3
"""Validate AI change evidence against the retail billing governance policy."""

import argparse
import fnmatch
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "governance" / "policy.json"
EVIDENCE_DIR = ROOT / "governance" / "evidence"
VALID_CHECK_STATUSES = {"passed", "failed", "blocked", "pending"}
VALID_APPROVAL_STATUSES = {"pending", "approved", "rejected"}
VALID_STATES = {"draft", "ready-for-review", "ready-for-release", "released", "blocked"}
WRITE_OPERATIONS = {"implement", "modify", "create", "delete", "migrate", "deploy"}


def load_json(path):
    try:
        with path.open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: cannot load JSON: {exc}") from exc


def normalize_repo_path(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("path must be a non-empty string")
    normalized = value.strip().replace("\\", "/").rstrip("/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"path must be repository-relative without traversal: {value!r}")
    return path.as_posix()


def path_is_allowed(target, patterns):
    target = normalize_repo_path(target)
    for raw_pattern in patterns:
        pattern = normalize_repo_path(raw_pattern)
        if target == pattern or target.startswith(pattern + "/") or fnmatch.fnmatchcase(target, pattern):
            return True
    return False


def path_errors(source, target, allowed_paths, forbidden_paths, label):
    try:
        normalized = normalize_repo_path(target)
    except ValueError as exc:
        return [f"{source}: {label} {exc}"]
    errors = []
    if not path_is_allowed(normalized, allowed_paths):
        errors.append(f"{source}: {label} {normalized!r} is outside allowed_paths")
    if path_is_allowed(normalized, forbidden_paths):
        errors.append(f"{source}: {label} targets protected path {normalized!r}")
    return errors


def validate_record(record, policy, source, stage, human_approved=False):
    errors = []
    required_fields = {
        "schema_version", "change_id", "title", "profile", "skill", "agent", "scope",
        "actions", "checks", "exceptions", "human_approval", "corrective_actions", "state",
    }
    if not isinstance(record, dict):
        return [f"{source}: evidence record must be an object"]
    missing = sorted(required_fields - set(record))
    if missing:
        return [f"{source}: missing fields: {', '.join(missing)}"]
    if record["schema_version"] != policy.get("schema_version"):
        errors.append(f"{source}: unsupported schema_version")

    profile_name = record["profile"]
    profile = policy.get("profiles", {}).get(profile_name)
    if profile is None:
        errors.append(f"{source}: unknown profile {profile_name!r}")
    if record["skill"] != policy.get("required_skill"):
        errors.append(f"{source}: required skill is {policy.get('required_skill')!r}")

    agent_name = record["agent"]
    agent = policy.get("agents", {}).get(agent_name) if agent_name is not None else None
    if agent_name is not None:
        if agent is None:
            errors.append(f"{source}: unknown agent {agent_name!r}")
        if profile is not None and agent_name not in profile.get("allowed_agents", []):
            errors.append(f"{source}: agent {agent_name!r} is not allowed for {profile_name!r}")
        if agent is not None and agent.get("parent_profile") != profile_name:
            errors.append(f"{source}: agent {agent_name!r} has the wrong parent profile")
        if agent is not None and agent.get("required_skill") != record["skill"]:
            errors.append(f"{source}: agent {agent_name!r} does not require the recorded skill")

    scope = record["scope"]
    if not isinstance(scope, dict):
        errors.append(f"{source}: scope must be an object")
        scope = {}
    allowed_paths = scope.get("allowed_paths", [])
    scope_forbidden = scope.get("forbidden_paths", [])
    if not isinstance(allowed_paths, list) or not allowed_paths or not scope.get("outcome"):
        errors.append(f"{source}: scope requires an outcome and non-empty allowed_paths")
        allowed_paths = []
    if not isinstance(scope_forbidden, list):
        errors.append(f"{source}: scope forbidden_paths must be a list")
        scope_forbidden = []
    forbidden_paths = list(policy.get("protected_paths", [])) + scope_forbidden
    for path_list, label in ((allowed_paths, "allowed path"), (forbidden_paths, "forbidden path")):
        for path in path_list:
            try:
                normalize_repo_path(path)
            except ValueError as exc:
                errors.append(f"{source}: invalid {label}: {exc}")
    for protected_path in policy.get("protected_paths", []):
        try:
            if allowed_paths and path_is_allowed(protected_path, allowed_paths):
                errors.append(f"{source}: protected path {protected_path!r} cannot be allowed")
        except ValueError:
            pass

    actions = record["actions"]
    if not isinstance(actions, list) or not actions:
        errors.append(f"{source}: actions must be a non-empty list")
        actions = []
    declared_actors = {profile_name}
    if agent_name is not None:
        declared_actors.add(agent_name)
    for index, action in enumerate(actions):
        prefix = f"{source}: action {index + 1}"
        if not isinstance(action, dict) or not all(action.get(field) for field in ("actor", "operation", "target", "outcome")):
            errors.append(f"{prefix} is incomplete")
            continue
        if action["actor"] not in declared_actors:
            errors.append(f"{prefix} has an undeclared actor")
        operation = action["operation"]
        if operation in WRITE_OPERATIONS:
            if action["actor"] == profile_name:
                permission = profile.get("permission") if profile else None
            else:
                permission = agent.get("permission") if agent else None
            if permission != "workspace-write":
                errors.append(f"{prefix} attempts a write with {permission or 'unknown'} permission")
        errors.extend(path_errors(prefix, action["target"], allowed_paths, forbidden_paths, "target"))

    checks_value = record["checks"]
    if not isinstance(checks_value, list):
        errors.append(f"{source}: checks must be a list")
        checks_value = []
    checks = {}
    for check in checks_value:
        if not isinstance(check, dict) or not check.get("name"):
            errors.append(f"{source}: malformed check entry")
            continue
        if check["name"] in checks:
            errors.append(f"{source}: duplicate check {check['name']!r}")
        checks[check["name"]] = check
    required_checks = policy.get("required_checks", {})
    for check_name, expected_command in required_checks.items():
        check = checks.get(check_name)
        if check is None:
            errors.append(f"{source}: missing required check {check_name!r}")
            continue
        if check.get("status") not in VALID_CHECK_STATUSES:
            errors.append(f"{source}: check {check_name!r} has invalid status")
        if check.get("command") != expected_command:
            errors.append(f"{source}: check {check_name!r} must use the policy command")
        command = check.get("command", "")
        if isinstance(command, str):
            for fragment in policy.get("prohibited_command_fragments", []):
                if fragment.casefold() in command.casefold():
                    errors.append(f"{source}: check {check_name!r} contains prohibited command fragment {fragment!r}")

    approval = record["human_approval"]
    if not isinstance(approval, dict) or approval.get("status") not in VALID_APPROVAL_STATUSES:
        errors.append(f"{source}: human_approval has invalid status")
        approval = {}
    if record["state"] not in VALID_STATES:
        errors.append(f"{source}: invalid state {record['state']!r}")

    exceptions = record["exceptions"]
    corrective_actions = record["corrective_actions"]
    if not isinstance(exceptions, list) or not isinstance(corrective_actions, list):
        errors.append(f"{source}: exceptions and corrective_actions must be lists")
        exceptions, corrective_actions = [], []
    for index, exception in enumerate(exceptions):
        if not isinstance(exception, dict) or not all(exception.get(field) for field in ("category", "impact", "evidence")):
            errors.append(f"{source}: exception {index + 1} is incomplete")
    for index, action in enumerate(corrective_actions):
        if not isinstance(action, dict) or not all(action.get(field) for field in ("owner", "action", "status")):
            errors.append(f"{source}: corrective action {index + 1} is incomplete")

    if stage == "release":
        failed_checks = [name for name in required_checks if checks.get(name, {}).get("status") != "passed"]
        if failed_checks:
            errors.append(f"{source}: release requires passed checks: {', '.join(failed_checks)}")
        recorded_approval = approval.get("status") == "approved" and approval.get("approver") and approval.get("reference")
        if not (recorded_approval or human_approved):
            errors.append(f"{source}: release requires recorded or protected-environment human approval")
        if exceptions and not corrective_actions:
            errors.append(f"{source}: release exceptions require corrective_actions")
        if record["state"] not in {"ready-for-release", "released"}:
            errors.append(f"{source}: release requires ready-for-release or released state")
    return errors


def evidence_paths(directory):
    return sorted(path for path in directory.glob("*.json") if not path.name.startswith("example"))


def git_changed_paths(base_ref, root=ROOT):
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base_ref}...HEAD"],
        cwd=root, check=False, capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError(f"git diff failed for base ref {base_ref!r}: {result.stderr.strip()}")
    return [line for line in result.stdout.splitlines() if line]


def validate_changed_paths(paths, records, policy):
    errors = []
    protected_paths = policy.get("protected_paths", [])
    normalized_paths = []
    for changed_path in paths:
        try:
            normalized_paths.append(normalize_repo_path(changed_path))
        except ValueError as exc:
            errors.append(f"changed path {changed_path!r} is invalid: {exc}")
    active_records = [
        (source, record) for source, record in records
        if f"governance/evidence/{source.name}" in normalized_paths
    ]
    if normalized_paths and not active_records:
        errors.append("changed files require a governance/evidence JSON record in the same change")
    for normalized in normalized_paths:
        try:
            if path_is_allowed(normalized, protected_paths):
                errors.append(f"changed path {normalized!r} is protected")
                continue
            matching_records = [
                (source, record) for source, record in active_records
                if path_is_allowed(normalized, record.get("scope", {}).get("allowed_paths", []))
            ]
            if not matching_records:
                errors.append(f"changed path {normalized!r} is outside the current evidence scope")
                continue
            if normalized.startswith("governance/evidence/"):
                continue
            recorded = any(
                path_is_allowed(normalized, [action.get("target")])
                for source, record in matching_records
                for action in record.get("actions", [])
                if isinstance(action, dict) and action.get("target")
            )
            if not recorded:
                errors.append(f"changed path {normalized!r} has no recorded action")
        except (ValueError, TypeError) as exc:
            errors.append(f"changed path {normalized!r} cannot be validated: {exc}")
    return errors


def validate(stage, human_approved, policy_path=POLICY_PATH, evidence_dir=EVIDENCE_DIR, changed_paths=None):
    policy = load_json(policy_path)
    paths = evidence_paths(evidence_dir)
    if not paths:
        return [f"{evidence_dir}: no evidence records found"]
    records = [(path, load_json(path)) for path in paths]
    errors = []
    for path, record in records:
        errors.extend(validate_record(record, policy, path, stage, human_approved))
    if changed_paths is not None:
        errors.extend(validate_changed_paths(changed_paths, records, policy))
    return errors


def dashboard(policy_path=POLICY_PATH, evidence_dir=EVIDENCE_DIR):
    policy = load_json(policy_path)
    records = [(path, load_json(path)) for path in evidence_paths(evidence_dir)]
    print("# AI Governance Dashboard\n")
    print("| Change | Profile | Agent | State | Checks | Exceptions | Human approval |")
    print("| --- | --- | --- | --- | --- | ---: | --- |")
    for path, record in records:
        checks = record.get("checks", [])
        passed = sum(check.get("status") == "passed" for check in checks if isinstance(check, dict))
        approval = record.get("human_approval", {}).get("status", "missing")
        agent = record.get("agent") or "none"
        print(f"| {record.get('change_id', path.stem)} | {record.get('profile', '?')} | {agent} | {record.get('state', '?')} | {passed}/{len(policy['required_checks'])} passed | {len(record.get('exceptions', []))} | {approval} |")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--stage", choices=("review", "release"), default="review")
    validate_parser.add_argument("--human-approved", action="store_true", help="Set only after an external protected-environment approval")
    validate_parser.add_argument("--base-ref", help="Git ref used to verify actual changed paths against evidence scopes")
    subparsers.add_parser("dashboard")
    args = parser.parse_args(argv)
    if args.command == "dashboard":
        dashboard()
        return 0
    try:
        changed_paths = git_changed_paths(args.base_ref) if args.base_ref else None
        errors = validate(args.stage, args.human_approved, changed_paths=changed_paths)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Governance {args.stage} validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
