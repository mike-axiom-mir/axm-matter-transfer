#!/usr/bin/env python3
"""Build and verify a deterministic single-file Ellis experiment runner.

The portable artifact copies the already-reviewed experiment bytes into a
stdlib-only Python zipapp. Packaging changes distribution only: it does not
change the model, promote scientific claims, or grant execution/merge/CANON
authority.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

PORTABLE_SCHEMA = "axm.matter-transfer.ellis-wormhole.portable/v1"
RECEIPT_SCHEMA = "axm.matter-transfer.ellis-wormhole.portable-receipt/v1"
VERIFICATION_SCHEMA = "axm.matter-transfer.ellis-wormhole.portable-verification/v1"
CAPABILITY_ID = "axm.matter-transfer.ellis-wormhole.experiment/v1"
CLAIM_CEILING = "NO_PHYSICAL_MACROSCOPIC_MATTER_TRANSFER_MECHANISM_ESTABLISHED"
SOURCE_RELATIVE = "experiments/ellis_wormhole.py"
MAX_RECEIPT_BYTES = 65_536
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MEMBERS = ("__main__.py", "AXM_PORTABLE.json", "ellis_wormhole.py")
ENTRYPOINT = b"from ellis_wormhole import main\nraise SystemExit(main())\n"
AUTHORITY = {
    "automatic_execution": False,
    "scientific_promotion": False,
    "engineering_authority": False,
    "merge_authority": False,
    "canon_authority": False,
}


class PortableError(ValueError):
    """Raised when build or verification evidence is not admissible."""


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PortableError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _read_regular(path: Path, *, limit: int | None = None) -> bytes:
    if path.is_symlink():
        raise PortableError(f"refusing symlink input: {path}")
    if not path.is_file():
        raise PortableError(f"required regular file missing: {path}")
    try:
        with path.open("rb") as stream:
            data = stream.read() if limit is None else stream.read(limit + 1)
    except OSError as exc:
        raise PortableError(f"cannot read {path}: {exc}") from exc
    if limit is not None and len(data) > limit:
        raise PortableError(f"{path} exceeds {limit}-byte limit")
    return data


def _read_receipt(path: Path) -> dict[str, Any]:
    data = _read_regular(path, limit=MAX_RECEIPT_BYTES)
    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=_strict_object)
    except PortableError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PortableError(f"invalid receipt JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PortableError("receipt must be a JSON object")
    return raw


def _metadata(source: bytes) -> dict[str, Any]:
    return {
        "schema": PORTABLE_SCHEMA,
        "capability_id": CAPABILITY_ID,
        "source": {
            "path": SOURCE_RELATIVE,
            "sha256": sha256(source),
            "relationship": "byte-exact packaged copy",
        },
        "runtime": {
            "python": ">=3.11",
            "standard_library_only": True,
            "network_required": False,
            "account_required": False,
            "ai_model_required": False,
        },
        "commands": ["run", "verify"],
        "claim_ceiling": CLAIM_CEILING,
        "authority": AUTHORITY,
    }


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    return info


def build_bytes(source: bytes) -> bytes:
    try:
        source.decode("utf-8")
    except UnicodeError as exc:
        raise PortableError("experiment source must be UTF-8 text") from exc
    if b"INPUT_SCHEMA = \"axm.matter-transfer.ellis-wormhole.input/v1\"" not in source:
        raise PortableError("experiment source contract marker missing")
    if b"RECEIPT_SCHEMA = \"axm.matter-transfer.ellis-wormhole.receipt/v1\"" not in source:
        raise PortableError("experiment receipt contract marker missing")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.writestr(_zip_info("__main__.py"), ENTRYPOINT)
        archive.writestr(_zip_info("AXM_PORTABLE.json"), canonical_bytes(_metadata(source)))
        archive.writestr(_zip_info("ellis_wormhole.py"), source)
    return buffer.getvalue()


def _receipt(artifact: bytes, source: bytes) -> dict[str, Any]:
    return {
        "schema": RECEIPT_SCHEMA,
        "capability_id": CAPABILITY_ID,
        "artifact": {
            "format": "python-zipapp",
            "sha256": sha256(artifact),
            "bytes": len(artifact),
            "members": list(MEMBERS),
        },
        "source": {
            "path": SOURCE_RELATIVE,
            "sha256": sha256(source),
        },
        "claim_ceiling": CLAIM_CEILING,
        "authority": AUTHORITY,
    }


def build(root: Path, artifact_path: Path, receipt_path: Path) -> dict[str, Any]:
    source_path = root / SOURCE_RELATIVE
    source = _read_regular(source_path)
    artifact = build_bytes(source)
    receipt = _receipt(artifact, source)

    if artifact_path.exists() or artifact_path.is_symlink():
        raise PortableError(f"refusing to overwrite artifact: {artifact_path}")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise PortableError(f"refusing to overwrite receipt: {receipt_path}")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact)
    receipt_path.write_bytes(canonical_bytes(receipt))
    return receipt


def _validate_receipt(receipt: dict[str, Any]) -> None:
    if set(receipt) != {"schema", "capability_id", "artifact", "source", "claim_ceiling", "authority"}:
        raise PortableError("receipt fields mismatch")
    if receipt["schema"] != RECEIPT_SCHEMA or receipt["capability_id"] != CAPABILITY_ID:
        raise PortableError("receipt identity mismatch")
    if receipt["claim_ceiling"] != CLAIM_CEILING or receipt["authority"] != AUTHORITY:
        raise PortableError("receipt truth/authority boundary mismatch")
    artifact = receipt["artifact"]
    source = receipt["source"]
    if not isinstance(artifact, dict) or set(artifact) != {"format", "sha256", "bytes", "members"}:
        raise PortableError("artifact receipt fields mismatch")
    if artifact["format"] != "python-zipapp" or artifact["members"] != list(MEMBERS):
        raise PortableError("artifact format/member contract mismatch")
    if not isinstance(artifact["bytes"], int) or artifact["bytes"] <= 0:
        raise PortableError("artifact byte count invalid")
    if not isinstance(artifact["sha256"], str) or len(artifact["sha256"]) != 64:
        raise PortableError("artifact SHA-256 invalid")
    if not isinstance(source, dict) or set(source) != {"path", "sha256"}:
        raise PortableError("source receipt fields mismatch")
    if source["path"] != SOURCE_RELATIVE or not isinstance(source["sha256"], str) or len(source["sha256"]) != 64:
        raise PortableError("source identity invalid")


def verify(artifact_path: Path, receipt_path: Path, source_path: Path | None = None) -> dict[str, Any]:
    artifact = _read_regular(artifact_path)
    receipt = _read_receipt(receipt_path)
    _validate_receipt(receipt)

    if len(artifact) != receipt["artifact"]["bytes"]:
        raise PortableError("artifact byte count mismatch")
    if sha256(artifact) != receipt["artifact"]["sha256"]:
        raise PortableError("artifact SHA-256 mismatch")

    try:
        with zipfile.ZipFile(io.BytesIO(artifact), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names != list(MEMBERS) or len(set(names)) != len(names):
                raise PortableError("zip member inventory/order mismatch")
            for info in infos:
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise PortableError(f"zip member is a symlink: {info.filename}")
                if info.compress_type != zipfile.ZIP_STORED:
                    raise PortableError(f"zip member compression drift: {info.filename}")
            entrypoint = archive.read("__main__.py")
            metadata_bytes = archive.read("AXM_PORTABLE.json")
            packaged_source = archive.read("ellis_wormhole.py")
    except PortableError:
        raise
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        raise PortableError(f"invalid zipapp: {exc}") from exc

    if entrypoint != ENTRYPOINT:
        raise PortableError("zipapp entrypoint drift")
    if sha256(packaged_source) != receipt["source"]["sha256"]:
        raise PortableError("packaged source SHA-256 mismatch")
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"), object_pairs_hook=_strict_object)
    except PortableError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise PortableError(f"invalid embedded metadata: {exc}") from exc
    if metadata != _metadata(packaged_source):
        raise PortableError("embedded metadata does not match packaged source")

    if source_path is not None:
        provider_source = _read_regular(source_path)
        if provider_source != packaged_source:
            raise PortableError("portable artifact source differs from provider source")

    return {
        "schema": VERIFICATION_SCHEMA,
        "status": "PASS",
        "capability_id": CAPABILITY_ID,
        "artifact_sha256": receipt["artifact"]["sha256"],
        "source_sha256": receipt["source"]["sha256"],
        "claim_ceiling": CLAIM_CEILING,
        "authority": AUTHORITY,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="build deterministic zipapp and receipt")
    build_parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    build_parser.add_argument("--output", type=Path, required=True)
    build_parser.add_argument("--receipt", type=Path, required=True)

    verify_parser = subparsers.add_parser("verify", help="verify a portable zipapp and receipt")
    verify_parser.add_argument("--artifact", type=Path, required=True)
    verify_parser.add_argument("--receipt", type=Path, required=True)
    verify_parser.add_argument("--source", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            result = build(args.root.resolve(), args.output, args.receipt)
        else:
            result = verify(args.artifact, args.receipt, args.source)
    except PortableError as exc:
        print(canonical_bytes({"status": "HOLD", "error": str(exc)}).decode("utf-8"), end="", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
