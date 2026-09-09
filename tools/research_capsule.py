#!/usr/bin/env python3
"""Build and independently verify portable AXM matter-transfer research capsules."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts/research_state_contract_v1.json"
CAPSULE_SCHEMA = "axm.matter-transfer-research-capsule.v1"
VERIFY_SCHEMA = "axm.matter-transfer-research-capsule-verification.v1"
PLAN_SCHEMA = "axm.matter-transfer-resolved-assembly.v1"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PATTERN_PROVENANCE = {
    "inspired_by": "mike-axiom-mir/axm-factual-space-simulator#5",
    "donor_head": "bf8e3e92cdf4e7b0b9dbafa0c569a4e0b0036c8f",
    "reuse": "concept_only_no_source_code_copied",
}


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return value, raw


def _safe_rel_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("capsule file path must be non-empty text")
    if "\\" in value or "\x00" in value:
        raise ValueError(f"unsafe capsule path: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or value != pure.as_posix():
        raise ValueError(f"capsule path must be canonical relative POSIX text: {value!r}")
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"capsule path contains an unsafe component: {value!r}")
    return value


def _manifest_digest(manifest: dict[str, Any]) -> str:
    body = dict(manifest)
    body.pop("capsule_sha256", None)
    return _sha256(_canonical_bytes(body))


def _file_record(path: str, raw: bytes, role: str, *, schema: str | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": path,
        "role": role,
        "bytes": len(raw),
        "sha256": _sha256(raw),
    }
    if schema is not None:
        record["schema"] = schema
    return record


def _write_file(root: Path, rel: str, raw: bytes) -> None:
    target = root / _safe_rel_path(rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)


def _build(profile: str, output: Path, contract_path: Path) -> dict[str, Any]:
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError(f"output must not exist or must be an empty directory: {output}")
    if output.is_symlink():
        raise ValueError("output directory may not be a symbolic link")

    try:
        from tools.research_state import resolve_profile
    except ModuleNotFoundError:
        from research_state import resolve_profile  # type: ignore

    contract, contract_raw = _load_json_bytes(contract_path)
    focus_path = ROOT / contract["inputs"]["focus"]["path"]
    registry_path = ROOT / contract["inputs"]["registry"]["path"]
    focus, focus_raw = _load_json_bytes(focus_path)
    registry, registry_raw = _load_json_bytes(registry_path)

    plan = resolve_profile(
        profile,
        focus,
        registry,
        contract,
        focus_raw,
        registry_raw,
        contract_raw,
    )
    plan_raw = _pretty_bytes(plan)
    verifier_raw = Path(__file__).read_bytes()

    output.mkdir(parents=True, exist_ok=True)
    payloads = [
        ("resolved-plan.json", plan_raw, "resolved_plan", plan.get("schema")),
        ("sources/research_state_contract_v1.json", contract_raw, "source_contract", contract.get("schema")),
        ("sources/current_focus.json", focus_raw, "source_focus", focus.get("schema")),
        ("sources/organ_registry.json", registry_raw, "source_registry", registry.get("schema")),
        ("verify.py", verifier_raw, "standalone_verifier", None),
    ]
    records: list[dict[str, Any]] = []
    for rel, raw, role, schema in payloads:
        _write_file(output, rel, raw)
        records.append(_file_record(rel, raw, role, schema=schema))

    manifest: dict[str, Any] = {
        "schema": CAPSULE_SCHEMA,
        "version": 1,
        "profile": profile,
        "authority": "evidence_only_no_execution_authority",
        "plan_sha256": plan["plan_sha256"],
        "source_authority": plan["source_authority"],
        "pattern_provenance": PATTERN_PROVENANCE,
        "files": sorted(records, key=lambda item: item["path"]),
        "truth_boundary": {
            "portable_integrity_is_not_scientific_validation": True,
            "portable_integrity_is_not_authentication": True,
            "capsule_does_not_execute_organs": True,
            "capsule_does_not_grant_merge_or_canon_authority": True,
        },
    }
    manifest["capsule_sha256"] = _manifest_digest(manifest)
    _write_file(output, "manifest.json", _pretty_bytes(manifest))
    return verify_capsule(output)


def _walk_regular_files(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symbolic links are not allowed in a capsule: {path.relative_to(root)}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"non-regular capsule entry: {path.relative_to(root)}")
        rel = path.relative_to(root).as_posix()
        found.append(_safe_rel_path(rel))
    return found


def _verify_plan(plan: dict[str, Any], manifest: dict[str, Any], role_records: dict[str, dict[str, Any]], root: Path) -> None:
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("resolved plan schema mismatch")
    if plan.get("profile") != manifest.get("profile"):
        raise ValueError("manifest/profile does not match resolved plan")
    stated_plan_hash = plan.get("plan_sha256")
    if not isinstance(stated_plan_hash, str) or not HEX64.fullmatch(stated_plan_hash):
        raise ValueError("resolved plan has malformed plan_sha256")
    plan_body = dict(plan)
    plan_body.pop("plan_sha256", None)
    if _sha256(_canonical_bytes(plan_body)) != stated_plan_hash:
        raise ValueError("resolved plan deterministic hash mismatch")
    if manifest.get("plan_sha256") != stated_plan_hash:
        raise ValueError("manifest plan hash does not match resolved plan")

    source_hashes = plan.get("source_hashes")
    if not isinstance(source_hashes, dict):
        raise ValueError("resolved plan source_hashes missing")
    role_to_key = {
        "source_contract": "contract_sha256",
        "source_focus": "focus_sha256",
        "source_registry": "registry_sha256",
    }
    for role, key in role_to_key.items():
        record = role_records[role]
        raw = (root / record["path"]).read_bytes()
        if source_hashes.get(key) != _sha256(raw):
            raise ValueError(f"resolved plan source lineage mismatch for {role}")


def verify_capsule(capsule: Path) -> dict[str, Any]:
    capsule = capsule.resolve()
    if not capsule.is_dir():
        raise ValueError(f"capsule directory not found: {capsule}")
    manifest_path = capsule / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("manifest.json must be a regular file")
    manifest, _ = _load_json_bytes(manifest_path)
    if manifest.get("schema") != CAPSULE_SCHEMA or manifest.get("version") != 1:
        raise ValueError("unsupported capsule schema/version")
    digest = manifest.get("capsule_sha256")
    if not isinstance(digest, str) or not HEX64.fullmatch(digest):
        raise ValueError("capsule_sha256 is malformed")
    if _manifest_digest(manifest) != digest:
        raise ValueError("capsule manifest digest mismatch")
    if manifest.get("authority") != "evidence_only_no_execution_authority":
        raise ValueError("capsule authority boundary drift")

    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("capsule files inventory must be non-empty")
    declared: list[str] = []
    roles: list[str] = []
    role_records: dict[str, dict[str, Any]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("capsule file records must be objects")
        rel = _safe_rel_path(record.get("path"))
        if rel == "manifest.json":
            raise ValueError("manifest.json may not declare itself")
        if rel in declared:
            raise ValueError(f"duplicate capsule path: {rel}")
        declared.append(rel)
        role = record.get("role")
        if not isinstance(role, str) or not role:
            raise ValueError(f"missing role for {rel}")
        if role in roles:
            raise ValueError(f"duplicate capsule role: {role}")
        roles.append(role)
        role_records[role] = record
        if not isinstance(record.get("bytes"), int) or record["bytes"] < 0:
            raise ValueError(f"invalid byte count for {rel}")
        sha = record.get("sha256")
        if not isinstance(sha, str) or not HEX64.fullmatch(sha):
            raise ValueError(f"invalid sha256 for {rel}")

    required_roles = {
        "resolved_plan",
        "source_contract",
        "source_focus",
        "source_registry",
        "standalone_verifier",
    }
    if set(roles) != required_roles:
        raise ValueError(f"capsule roles mismatch: expected {sorted(required_roles)}, got {sorted(roles)}")

    actual = _walk_regular_files(capsule)
    expected = sorted(["manifest.json", *declared])
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise ValueError(f"capsule inventory mismatch; missing={missing}, extra={extra}")

    for record in records:
        path = capsule / record["path"]
        raw = path.read_bytes()
        if len(raw) != record["bytes"]:
            raise ValueError(f"byte count mismatch: {record['path']}")
        if _sha256(raw) != record["sha256"]:
            raise ValueError(f"sha256 mismatch: {record['path']}")

    plan_path = capsule / role_records["resolved_plan"]["path"]
    plan, _ = _load_json_bytes(plan_path)
    _verify_plan(plan, manifest, role_records, capsule)

    return {
        "schema": VERIFY_SCHEMA,
        "valid": True,
        "profile": manifest["profile"],
        "capsule_sha256": digest,
        "plan_sha256": manifest["plan_sha256"],
        "files_verified": len(records),
        "authority": "integrity_and_lineage_evidence_only",
        "scientific_validation": False,
        "authentication": False,
        "execution_authority": False,
        "merge_or_canon_authority": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build a portable capsule from one resolved profile")
    build.add_argument("profile")
    build.add_argument("--output", required=True)
    build.add_argument("--contract", default=str(DEFAULT_CONTRACT))

    verify = subparsers.add_parser("verify", help="verify a received capsule without repository imports")
    verify.add_argument("capsule")

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            receipt = _build(args.profile, Path(args.output).resolve(), Path(args.contract).resolve())
        else:
            receipt = verify_capsule(Path(args.capsule))
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
