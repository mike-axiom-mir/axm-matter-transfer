#!/usr/bin/env python3
"""Validate and deterministically resolve AXM matter-transfer research state."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts/research_state_contract_v1.json"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


@dataclass(frozen=True, order=True)
class Problem:
    path: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "code": self.code, "message": self.message}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value, raw


def _duplicates(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    duplicate: set[Any] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return sorted(duplicate)


def _require_nonempty_text(
    obj: dict[str, Any], key: str, path: str, problems: list[Problem]
) -> None:
    if not isinstance(obj.get(key), str) or not obj[key].strip():
        problems.append(Problem(f"{path}.{key}", "nonempty_text_required", "must be non-empty text"))


def _check_unique_list(value: Any, path: str, problems: list[Problem], *, allow_empty: bool = False) -> None:
    if not isinstance(value, list) or (not allow_empty and not value):
        problems.append(Problem(path, "nonempty_list_required", "must be a non-empty list"))
        return
    duplicates = _duplicates(value)
    if duplicates:
        problems.append(Problem(path, "duplicate_values", f"duplicates: {duplicates}"))


def _validate_focus(focus: dict[str, Any], contract: dict[str, Any], problems: list[Problem]) -> None:
    input_contract = contract["inputs"]["focus"]
    rules = contract["focus"]
    if focus.get("schema") != input_contract["schema"]:
        problems.append(Problem("focus.schema", "schema_mismatch", f"expected {input_contract['schema']}"))
    if focus.get("status") not in rules["allowed_statuses"]:
        problems.append(Problem("focus.status", "status_not_allowed", "status is outside the contract"))
    _require_nonempty_text(focus, "claim_ceiling", "focus", problems)

    target = focus.get("primary_target")
    if not isinstance(target, dict):
        problems.append(Problem("focus.primary_target", "object_required", "must be an object"))
    else:
        expected = rules["primary_target"]
        if target.get("id") != expected["id"]:
            problems.append(Problem("focus.primary_target.id", "target_drift", f"expected {expected['id']}"))
        for key in expected["requires_true"]:
            if target.get(key) is not True:
                problems.append(Problem(f"focus.primary_target.{key}", "required_true", "must remain true"))
        for key in expected["requires_false"]:
            if target.get(key) is not False:
                problems.append(Problem(f"focus.primary_target.{key}", "required_false", "must remain false"))
        _check_unique_list(target.get("closest_legacy_modes"), "focus.primary_target.closest_legacy_modes", problems)

    for key in ("required_distinctions", "research_gates", "near_term_scope", "disabled_scope"):
        _check_unique_list(focus.get(key), f"focus.{key}", problems)

    for key, required in (
        ("research_gates", rules["required_research_gates"]),
        ("disabled_scope", rules["required_disabled_scope"]),
    ):
        present = set(focus.get(key, [])) if isinstance(focus.get(key), list) else set()
        missing = sorted(set(required) - present)
        if missing:
            problems.append(Problem(f"focus.{key}", "required_values_missing", f"missing: {missing}"))

    status = focus.get("current_status")
    if not isinstance(status, dict):
        problems.append(Problem("focus.current_status", "object_required", "must be an object"))
        return
    for key, value in status.items():
        if key != "summary" and not isinstance(value, bool):
            problems.append(Problem(f"focus.current_status.{key}", "boolean_required", "must be boolean"))
    matches = [rule for rule in rules["status_rules"] if all(status.get(k) == v for k, v in rule["when"].items())]
    if len(matches) != 1:
        problems.append(Problem("focus.current_status", "unsupported_status_combination", "no single versioned status rule matches"))
    elif status.get("summary") != matches[0]["summary"]:
        problems.append(Problem("focus.current_status.summary", "derived_summary_mismatch", f"expected {matches[0]['summary']}"))


def _organ_map(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    organs = registry.get("organs")
    if not isinstance(organs, list):
        return {}
    return {organ.get("id"): organ for organ in organs if isinstance(organ, dict) and isinstance(organ.get("id"), str)}


def _find_cycle(by_id: dict[str, dict[str, Any]]) -> list[str] | None:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(organ_id: str) -> list[str] | None:
        if organ_id in visiting:
            start = visiting.index(organ_id)
            return visiting[start:] + [organ_id]
        if organ_id in visited:
            return None
        visiting.append(organ_id)
        for dependency in by_id[organ_id].get("depends_on", []):
            if dependency in by_id:
                cycle = visit(dependency)
                if cycle:
                    return cycle
        visiting.pop()
        visited.add(organ_id)
        return None

    for organ_id in by_id:
        cycle = visit(organ_id)
        if cycle:
            return cycle
    return None


def _validate_registry(registry: dict[str, Any], contract: dict[str, Any], problems: list[Problem]) -> None:
    input_contract = contract["inputs"]["registry"]
    rules = contract["registry"]
    if registry.get("schema") != input_contract["schema"]:
        problems.append(Problem("registry.schema", "schema_mismatch", f"expected {input_contract['schema']}"))
    if not isinstance(registry.get("registry_version"), str) or not SEMVER.fullmatch(registry["registry_version"]):
        problems.append(Problem("registry.registry_version", "semver_required", "must be semantic version text"))
    _require_nonempty_text(registry, "canonical_claim_ceiling", "registry", problems)

    boundary = registry.get("truth_boundary")
    if not isinstance(boundary, dict):
        problems.append(Problem("registry.truth_boundary", "object_required", "must be an object"))
    else:
        for key in rules["required_truth_boundary_true"]:
            if boundary.get(key) is not True:
                problems.append(Problem(f"registry.truth_boundary.{key}", "truth_boundary_open", "must fail closed as true"))

    modes = registry.get("transfer_modes")
    if not isinstance(modes, list) or not modes:
        problems.append(Problem("registry.transfer_modes", "nonempty_list_required", "must be a non-empty list"))
        modes = []
    mode_ids = [mode.get("id") for mode in modes if isinstance(mode, dict)]
    for duplicate in _duplicates(mode_ids):
        problems.append(Problem("registry.transfer_modes", "duplicate_mode_id", f"duplicate: {duplicate}"))
    modes_by_id = {mode.get("id"): mode for mode in modes if isinstance(mode, dict)}
    for mode_id, expected_class in rules["transfer_mode_classes"].items():
        mode = modes_by_id.get(mode_id)
        if not mode:
            problems.append(Problem(f"registry.transfer_modes.{mode_id}", "required_mode_missing", "mode is required"))
        elif mode.get("class") != expected_class:
            problems.append(Problem(f"registry.transfer_modes.{mode_id}.class", "mode_class_drift", f"expected {expected_class}"))
        else:
            _require_nonempty_text(mode, "claim_ceiling", f"registry.transfer_modes.{mode_id}", problems)

    organs = registry.get("organs")
    if not isinstance(organs, list) or not organs:
        problems.append(Problem("registry.organs", "nonempty_list_required", "must be a non-empty list"))
        return
    ids = [organ.get("id") for organ in organs if isinstance(organ, dict)]
    for duplicate in _duplicates(ids):
        problems.append(Problem("registry.organs", "duplicate_organ_id", f"duplicate: {duplicate}"))
    by_id = _organ_map(registry)

    list_fields = {"inputs", "outputs", "depends_on", "hard_gates", "tests"}
    for index, organ in enumerate(organs):
        path = f"registry.organs[{index}]"
        if not isinstance(organ, dict):
            problems.append(Problem(path, "object_required", "organ must be an object"))
            continue
        for field in rules["required_organ_fields"]:
            if field not in organ:
                problems.append(Problem(f"{path}.{field}", "required_field_missing", "field is required"))
            elif field in list_fields:
                _check_unique_list(organ[field], f"{path}.{field}", problems, allow_empty=field == "depends_on")
            else:
                _require_nonempty_text(organ, field, path, problems)
        for dependency in organ.get("depends_on", []):
            if dependency not in by_id:
                problems.append(Problem(f"{path}.depends_on", "unknown_dependency", f"unknown organ: {dependency}"))

    cycle = _find_cycle(by_id)
    if cycle:
        problems.append(Problem("registry.organs", "dependency_cycle", " -> ".join(cycle)))

    profiles = registry.get("assembly_profiles")
    if not isinstance(profiles, dict) or not profiles:
        problems.append(Problem("registry.assembly_profiles", "nonempty_object_required", "must define profiles"))
    else:
        for name, profile in profiles.items():
            path = f"registry.assembly_profiles.{name}"
            if not isinstance(profile, dict):
                problems.append(Problem(path, "object_required", "profile must be an object"))
                continue
            _require_nonempty_text(profile, "purpose", path, problems)
            _check_unique_list(profile.get("required_organs"), f"{path}.required_organs", problems)
            for organ_id in profile.get("required_organs", []):
                if organ_id not in by_id:
                    problems.append(Problem(f"{path}.required_organs", "unknown_profile_root", f"unknown organ: {organ_id}"))
            if profile.get("enabled") is False:
                _check_unique_list(profile.get("activation_requirements"), f"{path}.activation_requirements", problems)


def validate(focus: dict[str, Any], registry: dict[str, Any], contract: dict[str, Any]) -> list[Problem]:
    problems: list[Problem] = []
    if contract.get("schema") != "axm.matter-transfer-validation-contract.v1":
        problems.append(Problem("contract.schema", "schema_mismatch", "unsupported validation contract"))
        return sorted(problems)
    if not isinstance(contract.get("contract_version"), str) or not SEMVER.fullmatch(contract["contract_version"]):
        problems.append(Problem("contract.contract_version", "semver_required", "must be semantic version text"))
        return sorted(problems)
    try:
        _validate_focus(focus, contract, problems)
        _validate_registry(registry, contract, problems)
        mode_ids = {mode.get("id") for mode in registry.get("transfer_modes", []) if isinstance(mode, dict)}
        target = focus.get("primary_target", {})
        for mode_id in target.get("closest_legacy_modes", []) if isinstance(target, dict) else []:
            if mode_id not in mode_ids:
                problems.append(Problem("focus.primary_target.closest_legacy_modes", "unknown_legacy_mode", f"unknown mode: {mode_id}"))
    except (KeyError, TypeError) as exc:
        problems.append(Problem("contract", "invalid_contract", f"missing or invalid contract field: {exc}"))
    return sorted(set(problems))


def _closure(registry: dict[str, Any], roots: list[str]) -> list[str]:
    by_id = _organ_map(registry)
    resolved: list[str] = []
    seen: set[str] = set()

    def add(organ_id: str) -> None:
        if organ_id in seen:
            return
        for dependency in by_id[organ_id]["depends_on"]:
            add(dependency)
        seen.add(organ_id)
        resolved.append(organ_id)

    for root in roots:
        add(root)
    return resolved


def validation_receipt(
    focus: dict[str, Any], registry: dict[str, Any], contract: dict[str, Any],
    focus_raw: bytes, registry_raw: bytes, contract_raw: bytes,
) -> dict[str, Any]:
    problems = validate(focus, registry, contract)
    return {
        "schema": "axm.matter-transfer-validation-receipt.v1",
        "valid": not problems,
        "contract_version": contract.get("contract_version"),
        "sources": {
            "contract": {"schema": contract.get("schema"), "sha256": _sha256(contract_raw)},
            "focus": {"schema": focus.get("schema"), "sha256": _sha256(focus_raw)},
            "registry": {"schema": registry.get("schema"), "sha256": _sha256(registry_raw)},
        },
        "counts": {
            "organs": len(registry.get("organs", [])),
            "profiles": len(registry.get("assembly_profiles", {})),
            "problems": len(problems),
        },
        "problems": [problem.as_dict() for problem in problems],
    }


def resolve_profile(
    profile_name: str, focus: dict[str, Any], registry: dict[str, Any], contract: dict[str, Any],
    focus_raw: bytes, registry_raw: bytes, contract_raw: bytes,
) -> dict[str, Any]:
    problems = validate(focus, registry, contract)
    if problems:
        raise ValueError(json.dumps([problem.as_dict() for problem in problems], sort_keys=True))
    profiles = registry["assembly_profiles"]
    if profile_name not in profiles:
        raise KeyError(f"unknown assembly profile: {profile_name}")
    profile = profiles[profile_name]
    roots = profile["required_organs"]
    ordered_ids = _closure(registry, roots)
    by_id = _organ_map(registry)
    payload = {
        "schema": "axm.matter-transfer-resolved-assembly.v1",
        "profile": profile_name,
        "enabled": profile.get("enabled", True),
        "authority": "derived_execution_plan",
        "source_authority": contract["inputs"]["registry"]["authority"],
        "contract_version": contract["contract_version"],
        "source_hashes": {
            "contract_sha256": _sha256(contract_raw),
            "focus_sha256": _sha256(focus_raw),
            "registry_sha256": _sha256(registry_raw),
        },
        "declared_roots": roots,
        "added_transitive_dependencies": [organ_id for organ_id in ordered_ids if organ_id not in roots],
        "resolved_organs": [
            {
                "id": organ_id,
                "layer": by_id[organ_id]["layer"],
                "depends_on": by_id[organ_id]["depends_on"],
                "inputs": by_id[organ_id]["inputs"],
                "outputs": by_id[organ_id]["outputs"],
            }
            for organ_id in ordered_ids
        ],
    }
    payload["plan_sha256"] = _sha256(_canonical_bytes(payload))
    return payload


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    contract_path = Path(args.contract).resolve()
    contract, _ = _load(contract_path)
    focus_path = Path(args.focus).resolve() if args.focus else ROOT / contract["inputs"]["focus"]["path"]
    registry_path = Path(args.registry).resolve() if args.registry else ROOT / contract["inputs"]["registry"]["path"]
    return focus_path, registry_path, contract_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", default=str(DEFAULT_CONTRACT))
    parser.add_argument("--focus")
    parser.add_argument("--registry")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")
    resolve = subparsers.add_parser("resolve-profile")
    resolve.add_argument("profile")
    args = parser.parse_args(argv)

    try:
        focus_path, registry_path, contract_path = _paths(args)
        focus, focus_raw = _load(focus_path)
        registry, registry_raw = _load(registry_path)
        contract, contract_raw = _load(contract_path)
        if args.command == "validate":
            receipt = validation_receipt(focus, registry, contract, focus_raw, registry_raw, contract_raw)
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return 0 if receipt["valid"] else 1
        plan = resolve_profile(args.profile, focus, registry, contract, focus_raw, registry_raw, contract_raw)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
