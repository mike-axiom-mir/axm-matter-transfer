#!/usr/bin/env python3
"""Generate source-backed public discovery evidence for the portable Ellis experiment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import stat
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

REPOSITORY = "mike-axiom-mir/axm-matter-transfer"
DISPLAY_NAME = "AXM Matter Transfer"
DISCOVERY_BUDDY_REF = "565c38ecf93a9d563b02211258d8d36fcb1162b5"
PATTERN_REPOSITORY = "mike-axiom-mir/axm-casual-loop"
PATTERN_REF = "f561a8a325444be30ad0b4fee412b3958aa1f1ee"

MARKER_PATH = ".axm/discovery-public.json"
BUILDER_PATH = "tools/build_ellis_zipapp.py"
EXPERIMENT_PATH = "experiments/ellis_wormhole.py"
FIXTURE_PATH = "experiments/fixtures/ellis_zero_mass_v1.json"
LICENSE_PATH = "LICENSE"
REGISTRY_PATH = "registry/capabilities.jsonl"
RECEIPT_PATH = "registry/capabilities.receipt.json"

SOURCE_PATHS = (BUILDER_PATH, EXPERIMENT_PATH, FIXTURE_PATH, LICENSE_PATH)
CAPABILITY_ID = "axm.matter-transfer.ellis-wormhole.experiment/v1"
CLAIM_CEILING = "NO_PHYSICAL_MACROSCOPIC_MATTER_TRANSFER_MECHANISM_ESTABLISHED"
SAFE_AUTHORITY = {
    "automatic_execution": False,
    "scientific_promotion": False,
    "engineering_authority": False,
    "merge_authority": False,
    "canon_authority": False,
}


class DiscoveryError(ValueError):
    """Raised when public discovery evidence cannot be admitted."""


def canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise DiscoveryError(f"value is not portable canonical JSON: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DiscoveryError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> None:
    raise DiscoveryError(f"non-standard JSON constant: {token}")


def strict_json_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except DiscoveryError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise DiscoveryError(f"invalid JSON: {exc}") from exc


def regular_file(root: Path, relative_path: str) -> Path:
    root = root.resolve()
    candidate = root / relative_path
    try:
        info = candidate.lstat()
    except FileNotFoundError as exc:
        raise DiscoveryError(f"required source missing: {relative_path}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise DiscoveryError(f"source must be a regular non-symlink file: {relative_path}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except ValueError as exc:
        raise DiscoveryError(f"source escapes repository root: {relative_path}") from exc
    return resolved


def read_json_file(root: Path, relative_path: str) -> Any:
    path = regular_file(root, relative_path)
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except UnicodeError as exc:
        raise DiscoveryError(f"source is not UTF-8: {relative_path}") from exc


def source_record(root: Path, relative_path: str) -> dict[str, str]:
    data = regular_file(root, relative_path).read_bytes()
    return {"path": relative_path, "git_blob_sha1": git_blob_sha1(data)}


def validate_marker(root: Path) -> None:
    expected = {
        "schema": "axm.discovery-public/v1",
        "public": True,
        "repo": REPOSITORY,
        "display_name": DISPLAY_NAME,
    }
    if read_json_file(root, MARKER_PATH) != expected:
        raise DiscoveryError("public discovery marker drift")


def _load_module(root: Path, relative_path: str, name: str) -> ModuleType:
    path = regular_file(root, relative_path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DiscoveryError(f"cannot load provider module: {relative_path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise DiscoveryError(f"provider module load failed: {relative_path}: {exc}") from exc
    return module


def _portable_metadata(root: Path, builder: ModuleType, source: bytes) -> dict[str, Any]:
    if getattr(builder, "CAPABILITY_ID", None) != CAPABILITY_ID:
        raise DiscoveryError("portable builder capability id drift")
    if getattr(builder, "CLAIM_CEILING", None) != CLAIM_CEILING:
        raise DiscoveryError("portable builder claim ceiling drift")
    if getattr(builder, "AUTHORITY", None) != SAFE_AUTHORITY:
        raise DiscoveryError("portable builder authority drift")
    try:
        artifact = builder.build_bytes(source)
    except Exception as exc:
        raise DiscoveryError(f"portable builder could not build provider bytes: {exc}") from exc
    try:
        with zipfile.ZipFile(io.BytesIO(artifact), "r") as archive:
            names = archive.namelist()
            if names != ["__main__.py", "AXM_PORTABLE.json", "ellis_wormhole.py"]:
                raise DiscoveryError("portable artifact member contract drift")
            metadata_bytes = archive.read("AXM_PORTABLE.json")
            packaged_source = archive.read("ellis_wormhole.py")
    except DiscoveryError:
        raise
    except (KeyError, OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise DiscoveryError(f"cannot inspect portable provider artifact: {exc}") from exc
    if packaged_source != source:
        raise DiscoveryError("portable builder changed experiment source bytes")
    try:
        metadata = strict_json_loads(metadata_bytes.decode("utf-8"))
    except UnicodeError as exc:
        raise DiscoveryError("portable metadata is not UTF-8") from exc
    if not isinstance(metadata, dict):
        raise DiscoveryError("portable metadata must be an object")
    return metadata


def provider_contract(root: Path) -> dict[str, Any]:
    validate_marker(root)
    builder = _load_module(root, BUILDER_PATH, "_axm_ellis_portable_builder")
    experiment = _load_module(root, EXPERIMENT_PATH, "_axm_ellis_experiment")
    source = regular_file(root, EXPERIMENT_PATH).read_bytes()
    metadata = _portable_metadata(root, builder, source)

    expected_runtime = {
        "python": ">=3.11",
        "standard_library_only": True,
        "network_required": False,
        "account_required": False,
        "ai_model_required": False,
    }
    if metadata.get("schema") != getattr(builder, "PORTABLE_SCHEMA", None):
        raise DiscoveryError("portable schema drift")
    if metadata.get("capability_id") != CAPABILITY_ID:
        raise DiscoveryError("portable metadata capability id drift")
    if metadata.get("commands") != ["run", "verify"]:
        raise DiscoveryError("portable command contract drift")
    if metadata.get("runtime") != expected_runtime:
        raise DiscoveryError("portable runtime/offline contract drift")
    if metadata.get("claim_ceiling") != CLAIM_CEILING:
        raise DiscoveryError("portable metadata claim ceiling drift")
    if metadata.get("authority") != SAFE_AUTHORITY:
        raise DiscoveryError("portable metadata authority drift")
    source_meta = metadata.get("source")
    if not isinstance(source_meta, dict):
        raise DiscoveryError("portable source metadata missing")
    if source_meta != {
        "path": EXPERIMENT_PATH,
        "sha256": sha256_bytes(source),
        "relationship": "byte-exact packaged copy",
    }:
        raise DiscoveryError("portable source binding drift")

    fixture = read_json_file(root, FIXTURE_PATH)
    if not isinstance(fixture, dict):
        raise DiscoveryError("example fixture must be an object")
    if fixture.get("schema") != getattr(experiment, "INPUT_SCHEMA", None):
        raise DiscoveryError("fixture input schema drift")
    if fixture.get("model") != getattr(experiment, "MODEL_ID", None):
        raise DiscoveryError("fixture model id drift")
    if getattr(experiment, "RECEIPT_SCHEMA", None) != "axm.matter-transfer.ellis-wormhole.receipt/v1":
        raise DiscoveryError("experiment receipt schema drift")
    if getattr(experiment, "CLAIM_CEILING", None) != CLAIM_CEILING:
        raise DiscoveryError("experiment claim ceiling drift")

    license_text = regular_file(root, LICENSE_PATH).read_text(encoding="utf-8")
    if "Apache License" not in license_text[:120] or "Version 2.0" not in license_text[:160]:
        raise DiscoveryError("license identity drift")

    return {
        "builder": builder,
        "experiment": experiment,
        "metadata": metadata,
        "source": source,
    }


def build_artifacts(root: Path | str = Path.cwd()) -> dict[str, str]:
    root = Path(root)
    admitted = provider_contract(root)
    builder = admitted["builder"]
    experiment = admitted["experiment"]
    metadata = admitted["metadata"]

    record = {
        "schema": "axm.public-capability/v1",
        "id": CAPABILITY_ID,
        "version": "v1",
        "status": None,
        "providers": [REPOSITORY],
        "consumers": [],
        "summary": (
            "Portable offline reproduction of the bounded Ellis zero-mass wormhole "
            "toy-geometry experiment; no physical macroscopic matter-transfer mechanism is established."
        ),
        "license": "Apache-2.0",
        "runtime": {
            "language": "python",
            "python": metadata["runtime"]["python"],
            "dependencies": 0,
            "network": False,
            "account": False,
            "aiModel": False,
        },
        "entrypoints": {
            "builder": BUILDER_PATH,
            "portableArtifact": "ellis-wormhole.pyz",
            "operations": list(metadata["commands"]),
            "exampleFixture": FIXTURE_PATH,
        },
        "contracts": {
            "portable": builder.PORTABLE_SCHEMA,
            "portableReceipt": builder.RECEIPT_SCHEMA,
            "portableVerification": builder.VERIFICATION_SCHEMA,
            "input": experiment.INPUT_SCHEMA,
            "runReceipt": experiment.RECEIPT_SCHEMA,
            "modelId": experiment.MODEL_ID,
        },
        "truth": {
            "claimCeiling": CLAIM_CEILING,
            "modelOnly": True,
            "physicalMacroscopicMatterTransferEstablished": False,
        },
        "source": {
            "builder": BUILDER_PATH,
            "experiment": EXPERIMENT_PATH,
            "fixture": FIXTURE_PATH,
            "license": LICENSE_PATH,
        },
        "authority": {
            "discoveryOnly": True,
            "execution": False,
            "automaticSelection": False,
            "automaticInstall": False,
            "scientificPromotion": False,
            "engineering": False,
            "merge": False,
            "canon": False,
        },
    }
    registry_text = canonical_json(record) + "\n"
    receipt_body = {
        "schema": "axm.public-capability-registry-receipt/v1",
        "repository": REPOSITORY,
        "registry": {
            "path": REGISTRY_PATH,
            "sha256": sha256_bytes(registry_text.encode("utf-8")),
            "capability_count": 1,
            "capability_ids": [CAPABILITY_ID],
        },
        "sources": [source_record(root, path) for path in SOURCE_PATHS],
        "compatibility": {
            "consumer": "mike-axiom-mir/axm-discovery-buddy",
            "pinned_ref": DISCOVERY_BUDDY_REF,
            "portable_boundary": "discovery-buddy.pyz",
            "marker_contract": "axm.discovery-public/v1",
            "registry_contract": "registry/*capabilit*.jsonl",
        },
        "pattern_provenance": {
            "adapted_from_repository": PATTERN_REPOSITORY,
            "adapted_from_ref": PATTERN_REF,
            "adapted_paths": [
                ".axm/discovery-public.json",
                "tools/generate_public_capabilities.py",
                ".github/workflows/public-capability-discovery.yml",
            ],
            "copied_runtime_code": False,
        },
        "truth_boundary": {
            "source_backed": True,
            "public_export_intent": True,
            "runtime_distribution_proven": True,
            "scientific_validation_beyond_declared_model": False,
            "physical_macroscopic_matter_transfer_established": False,
            "execution_authority": False,
            "automatic_selection_authority": False,
            "automatic_install_authority": False,
            "scientific_promotion_authority": False,
            "engineering_authority": False,
            "merge_authority": False,
            "canon_authority": False,
        },
    }
    receipt = dict(receipt_body)
    receipt["receipt_sha256"] = sha256_bytes(canonical_json(receipt_body).encode("utf-8"))
    return {
        REGISTRY_PATH: registry_text,
        RECEIPT_PATH: json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
    }


def check_artifacts(root: Path | str = Path.cwd()) -> tuple[bool, list[str], dict[str, str]]:
    root = Path(root)
    expected = build_artifacts(root)
    mismatches: list[str] = []
    for relative_path, expected_text in expected.items():
        target = root / relative_path
        if target.is_symlink():
            raise DiscoveryError(f"generated output must not be a symlink: {relative_path}")
        try:
            actual = target.read_text(encoding="utf-8")
        except FileNotFoundError:
            actual = None
        if actual != expected_text:
            mismatches.append(relative_path)
    return not mismatches, mismatches, expected


def write_artifacts(root: Path | str = Path.cwd()) -> dict[str, str]:
    root = Path(root)
    artifacts = build_artifacts(root)
    for relative_path, text in artifacts.items():
        target = root / relative_path
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_file():
                raise DiscoveryError(f"generated output must be a regular file: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate source-backed public capability discovery evidence for the Ellis portable experiment."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify committed generated artifacts")
    mode.add_argument("--write", action="store_true", help="write generated artifacts")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        if args.check:
            ok, mismatches, _ = check_artifacts(args.root)
            if not ok:
                print("public capability registry is stale: " + ", ".join(mismatches), file=sys.stderr)
                return 1
            print("public capability registry: PASS")
            return 0
        artifacts = write_artifacts(args.root)
        print("public capability registry: wrote " + ", ".join(artifacts))
        return 0
    except (DiscoveryError, OSError) as exc:
        print(f"public capability registry: ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
