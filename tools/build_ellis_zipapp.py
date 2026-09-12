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
import os
import secrets
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


def _stat_signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _read_regular(path: Path, *, limit: int | None = None) -> bytes:
    try:
        admitted = path.lstat()
    except FileNotFoundError as exc:
        raise PortableError(f"required regular file missing: {path}") from exc
    except OSError as exc:
        raise PortableError(f"cannot inspect input {path}: {exc}") from exc

    if stat.S_ISLNK(admitted.st_mode):
        raise PortableError(f"refusing symlink input: {path}")
    if not stat.S_ISREG(admitted.st_mode):
        raise PortableError(f"required regular file missing: {path}")
    if limit is not None and admitted.st_size > limit:
        raise PortableError(f"{path} exceeds {limit}-byte limit")

    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PortableError(f"cannot open admitted input {path}: {exc}") from exc

    try:
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise PortableError(f"opened input is not a regular file: {path}")
            if _stat_signature(opened) != _stat_signature(admitted):
                raise PortableError(f"input changed before open: {path}")
            if limit is not None and opened.st_size > limit:
                raise PortableError(f"{path} exceeds {limit}-byte limit")

            data = stream.read() if limit is None else stream.read(limit + 1)
            after = os.fstat(stream.fileno())
    except PortableError:
        raise
    except OSError as exc:
        raise PortableError(f"cannot read {path}: {exc}") from exc

    if _stat_signature(after) != _stat_signature(opened) or len(data) != after.st_size:
        raise PortableError(f"input changed during read: {path}")
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


def _occupied(path: Path) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise PortableError(f"cannot inspect output path {path}: {exc}") from exc
    return True


def _stage_bytes(path: Path, data: bytes, label: str) -> Path:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        for _attempt in range(64):
            stage = path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"
            try:
                descriptor = os.open(stage, flags, 0o644)
                break
            except FileExistsError:
                continue
        else:
            raise PortableError(f"cannot allocate private {label} stage for {path}")
    except PortableError:
        raise
    except OSError as exc:
        raise PortableError(f"cannot create {label} stage for {path}: {exc}") from exc

    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as exc:
        try:
            stage.unlink()
        except OSError:
            pass
        raise PortableError(f"cannot write {label} stage for {path}: {exc}") from exc
    return stage


def _cleanup_stage(stage: Path | None) -> None:
    if stage is None:
        return
    try:
        stage.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        # Private stages have no bundle authority. Cleanup is best effort after
        # the create-only publication decision.
        pass


def _publish_stage(stage: Path, path: Path, label: str) -> bool:
    try:
        os.link(stage, path)
    except FileExistsError:
        return False
    except OSError as exc:
        raise PortableError(f"cannot publish {label} {path}: {exc}") from exc
    return True


def build(root: Path, artifact_path: Path, receipt_path: Path) -> dict[str, Any]:
    source_path = root / SOURCE_RELATIVE
    source = _read_regular(source_path)
    artifact = build_bytes(source)
    receipt = _receipt(artifact, source)
    receipt_bytes = canonical_bytes(receipt)

    if artifact_path.absolute() == receipt_path.absolute():
        raise PortableError("artifact and receipt paths must be distinct")
    if _occupied(receipt_path):
        raise PortableError(f"refusing to overwrite receipt: {receipt_path}")

    artifact_ready = _occupied(artifact_path)
    if artifact_ready:
        if _read_regular(artifact_path) != artifact:
            raise PortableError(f"refusing to replace conflicting artifact: {artifact_path}")

    artifact_stage: Path | None = None
    receipt_stage: Path | None = None
    try:
        if not artifact_ready:
            artifact_stage = _stage_bytes(artifact_path, artifact, "artifact")
        receipt_stage = _stage_bytes(receipt_path, receipt_bytes, "receipt")

        if artifact_stage is not None and not _publish_stage(artifact_stage, artifact_path, "artifact"):
            if _read_regular(artifact_path) != artifact:
                raise PortableError(f"refusing to replace conflicting artifact: {artifact_path}")

        # The artifact is derived, restart-recoverable state. Recheck its exact
        # identity before the receipt becomes the bundle's commit marker.
        if _read_regular(artifact_path) != artifact:
            raise PortableError(f"artifact changed before receipt commit: {artifact_path}")
        if not _publish_stage(receipt_stage, receipt_path, "receipt"):
            raise PortableError(f"refusing to overwrite receipt: {receipt_path}")
        return receipt
    finally:
        _cleanup_stage(artifact_stage)
        _cleanup_stage(receipt_stage)


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
