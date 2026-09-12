#!/usr/bin/env python3
"""Verify preserved Factual Space migration provenance without rewriting it.

The migration notes are the contract. Rows marked as exact human-readable copies
must still have the same Git blob identity as the recorded source blob. Rows
marked as semantic migrations are intentionally *not* required to be byte
identical; they must remain present and parseable when JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

MIGRATION_NOTES = Path("provenance/factual-space-pr2/MIGRATION_NOTES.md")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _strip_code(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def _safe_relative_posix(path_text: str) -> bool:
    if not path_text or "\\" in path_text or "\x00" in path_text:
        return False
    path = PurePosixPath(path_text)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return False
    return path.as_posix() == path_text


def _metadata(notes_text: str) -> tuple[str | None, str | None]:
    repo = None
    head = None
    for line in notes_text.splitlines():
        if line.startswith("**Source repository:**"):
            repo = _strip_code(line[len("**Source repository:**"):])
        elif line.startswith("**Source head:**"):
            head = _strip_code(line[len("**Source head:**"):])
    return repo, head


def _source_rows(notes_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    in_table = False
    for line in notes_text.splitlines():
        if line.strip().startswith("| Source path | Source blob SHA |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.lstrip().startswith("|"):
            break
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if all(set(cell) <= {"-", ":", " "} for cell in cells[:3]):
            continue
        rows.append(
            {
                "source_path": _strip_code(cells[0]),
                "source_blob_sha": _strip_code(cells[1]),
                "treatment": _strip_code(cells[2]),
            }
        )
    return rows


def verify_repository(repo_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    notes_path = repo_root / MIGRATION_NOTES
    errors: list[str] = []
    records: list[dict[str, Any]] = []

    if not notes_path.is_file():
        return {
            "schema": "axm.matter-transfer.migration-provenance-verification/v1",
            "overall": "FAIL",
            "errors": [f"missing migration notes: {MIGRATION_NOTES.as_posix()}"],
            "records": [],
        }

    notes_text = notes_path.read_text(encoding="utf-8")
    source_repo, source_head = _metadata(notes_text)
    if not source_repo or not REPO_RE.fullmatch(source_repo):
        errors.append("invalid or missing Source repository metadata")
    if not source_head or not SHA1_RE.fullmatch(source_head):
        errors.append("invalid or missing 40-hex Source head metadata")

    rows = _source_rows(notes_text)
    if not rows:
        errors.append("migration notes contain no source-file rows")

    seen_paths: set[str] = set()
    exact_count = 0
    semantic_count = 0

    for row in rows:
        source_path = row["source_path"]
        expected_sha = row["source_blob_sha"]
        treatment = row["treatment"]
        lower_treatment = treatment.lower()

        record: dict[str, Any] = {
            "sourcePath": source_path,
            "sourceBlobSha": expected_sha,
            "treatment": treatment,
        }

        if source_path in seen_paths:
            errors.append(f"duplicate source path: {source_path}")
            record["status"] = "FAIL_DUPLICATE_PATH"
            records.append(record)
            continue
        seen_paths.add(source_path)

        if not _safe_relative_posix(source_path):
            errors.append(f"unsafe or non-canonical source path: {source_path}")
            record["status"] = "FAIL_UNSAFE_PATH"
            records.append(record)
            continue

        if not SHA1_RE.fullmatch(expected_sha):
            errors.append(f"invalid source blob SHA for {source_path}")
            record["status"] = "FAIL_INVALID_SOURCE_SHA"
            records.append(record)
            continue

        destination_rel = (MIGRATION_NOTES.parent / PurePosixPath(source_path)).as_posix()
        destination = repo_root / destination_rel
        record["destinationPath"] = destination_rel

        if not destination.is_file():
            errors.append(f"missing migrated file: {destination_rel}")
            record["status"] = "FAIL_MISSING_DESTINATION"
            records.append(record)
            continue

        data = destination.read_bytes()
        current_sha = git_blob_sha1(data)
        record["currentBlobSha"] = current_sha
        record["bytes"] = len(data)

        if "copied as human-readable provenance" in lower_treatment:
            exact_count += 1
            record["byteIdenticalRequired"] = True
            if current_sha != expected_sha:
                errors.append(
                    f"exact-copy provenance drift for {source_path}: "
                    f"expected {expected_sha}, got {current_sha}"
                )
                record["status"] = "FAIL_EXACT_COPY_DRIFT"
            else:
                record["status"] = "PASS_EXACT_COPY"
        elif "semantically migrated" in lower_treatment:
            semantic_count += 1
            record["byteIdenticalRequired"] = False
            if destination.suffix.lower() == ".json":
                try:
                    json.loads(data.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    errors.append(f"semantic JSON migration is not parseable: {source_path}: {exc}")
                    record["status"] = "FAIL_SEMANTIC_JSON"
                else:
                    record["status"] = "PASS_SEMANTIC_BOUNDARY"
            else:
                record["status"] = "PASS_SEMANTIC_BOUNDARY"
        else:
            errors.append(f"unsupported migration treatment for {source_path}: {treatment}")
            record["status"] = "FAIL_UNKNOWN_TREATMENT"

        records.append(record)

    # This migration is intentionally one semantic registry plus three exact
    # human-readable copies. A future change must update both contract and gate.
    if exact_count != 3:
        errors.append(f"expected 3 exact-copy provenance rows, found {exact_count}")
    if semantic_count != 1:
        errors.append(f"expected 1 semantic-migration row, found {semantic_count}")

    return {
        "schema": "axm.matter-transfer.migration-provenance-verification/v1",
        "overall": "PASS" if not errors else "FAIL",
        "sourceRepository": source_repo,
        "sourceHead": source_head,
        "exactCopyCount": exact_count,
        "semanticMigrationCount": semantic_count,
        "errors": errors,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Factual Space PR #2 migration provenance."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to parent of tools/)",
    )
    parser.add_argument("--json", action="store_true", help="emit the full receipt as JSON")
    args = parser.parse_args()

    receipt = verify_repository(args.repo_root)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(
            f"{receipt['overall']}: "
            f"{receipt.get('exactCopyCount', 0)} exact-copy rows, "
            f"{receipt.get('semanticMigrationCount', 0)} semantic row(s)"
        )
        for record in receipt.get("records", []):
            print(f"- {record.get('status')}: {record.get('sourcePath')}")
        for error in receipt.get("errors", []):
            print(f"ERROR: {error}")

    return 0 if receipt["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
