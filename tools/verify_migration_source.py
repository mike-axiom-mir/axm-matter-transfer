#!/usr/bin/env python3
"""Verify the recorded migration source history from an explicit local Git checkout.

This is a consumer-side companion to verify_migration_provenance.py. The existing
migration verifier proves the destination still honors its recorded exact-copy
and semantic-migration boundaries. This verifier additionally proves that the
recorded source commit exists in a caller-selected local Git checkout and that
every recorded source path resolves to the exact blob identity named by the
migration notes.

Git history and remote metadata are integrity/lineage evidence, not author
authentication. This tool never fetches, checks out, or mutates a repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from verify_migration_provenance import verify_repository

GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=env,
    )


def _normalize_github_origin(value: str) -> str | None:
    value = value.strip()
    prefixes = (
        "https://github.com/",
        "http://github.com/",
        "ssh://git@github.com/",
        "git://github.com/",
    )
    path: str | None = None
    for prefix in prefixes:
        if value.startswith(prefix):
            path = value[len(prefix):]
            break
    if path is None and value.startswith("git@github.com:"):
        path = value[len("git@github.com:"):]
    if path is None:
        return None

    path = path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]
    return path if GITHUB_REPO_RE.fullmatch(path) else None


def _origin(repo: Path) -> tuple[str | None, str | None]:
    result = _git(repo, "remote", "get-url", "origin")
    if result.returncode != 0:
        return None, None
    raw = result.stdout.strip()
    return raw or None, _normalize_github_origin(raw)


def _tree_entry(repo: Path, commit: str, source_path: str) -> dict[str, str] | None:
    result = _git(repo, "ls-tree", "-z", commit, "--", source_path)
    if result.returncode != 0 or not result.stdout:
        return None

    entries = [entry for entry in result.stdout.split("\0") if entry]
    if len(entries) != 1 or "\t" not in entries[0]:
        return None

    meta, path = entries[0].split("\t", 1)
    parts = meta.split()
    if len(parts) != 3:
        return None
    mode, object_type, object_sha = parts
    return {
        "mode": mode,
        "type": object_type,
        "sha": object_sha,
        "path": path,
    }


def verify_source_checkout(
    destination_repo: Path,
    source_repo: Path,
    *,
    require_origin: bool = False,
    require_head: bool = False,
) -> dict[str, Any]:
    destination_repo = destination_repo.resolve()
    source_repo = source_repo.resolve()

    destination_receipt = verify_repository(destination_repo)
    errors: list[str] = []
    source_records: list[dict[str, Any]] = []

    receipt: dict[str, Any] = {
        "schema": "axm.matter-transfer.migration-source-witness/v1",
        "overall": "FAIL",
        "destinationProvenanceVerified": destination_receipt.get("overall") == "PASS",
        "sourceRepository": destination_receipt.get("sourceRepository"),
        "sourceHead": destination_receipt.get("sourceHead"),
        "sourceCheckout": {
            "gitRepository": False,
            "recordedCommitPresent": False,
            "checkedOutHead": None,
            "checkedOutHeadMatches": False,
            "originRepository": None,
            "originMatches": None,
            "originRequired": require_origin,
            "checkedOutHeadRequired": require_head,
        },
        "sourceRecords": source_records,
        "errors": errors,
        "authority": {
            "sourceAuthenticationProven": False,
            "scientificValidationProven": False,
            "mergeAuthority": False,
            "canonAuthority": False,
        },
    }

    if destination_receipt.get("overall") != "PASS":
        errors.append("destination migration provenance gate did not pass")
        receipt["destinationErrors"] = destination_receipt.get("errors", [])
        return receipt

    source_repository = destination_receipt["sourceRepository"]
    source_head = destination_receipt["sourceHead"]

    inside = _git(source_repo, "rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        errors.append("source checkout is not a Git work tree")
        return receipt
    receipt["sourceCheckout"]["gitRepository"] = True

    current_head = _git(source_repo, "rev-parse", "HEAD")
    if current_head.returncode == 0:
        checked_out_head = current_head.stdout.strip()
        receipt["sourceCheckout"]["checkedOutHead"] = checked_out_head
        receipt["sourceCheckout"]["checkedOutHeadMatches"] = checked_out_head == source_head
    elif require_head:
        errors.append("could not resolve checked-out source HEAD")

    if require_head and not receipt["sourceCheckout"]["checkedOutHeadMatches"]:
        errors.append(
            f"checked-out source HEAD does not match recorded source head {source_head}"
        )

    origin_raw, origin_repo = _origin(source_repo)
    receipt["sourceCheckout"]["originRepository"] = origin_repo
    if origin_repo is not None:
        receipt["sourceCheckout"]["originMatches"] = origin_repo == source_repository

    if require_origin and receipt["sourceCheckout"]["originMatches"] is not True:
        if origin_raw:
            errors.append(
                f"source origin does not match recorded repository {source_repository}"
            )
        else:
            errors.append("source origin is unavailable but --require-origin was requested")

    commit = _git(source_repo, "rev-parse", "--verify", f"{source_head}^{{commit}}")
    if commit.returncode != 0 or commit.stdout.strip() != source_head:
        errors.append(f"recorded source commit is absent: {source_head}")
        return receipt
    receipt["sourceCheckout"]["recordedCommitPresent"] = True

    for destination_record in destination_receipt.get("records", []):
        source_path = destination_record["sourcePath"]
        expected_blob = destination_record["sourceBlobSha"]
        record: dict[str, Any] = {
            "sourcePath": source_path,
            "expectedBlobSha": expected_blob,
            "treatment": destination_record["treatment"],
        }

        entry = _tree_entry(source_repo, source_head, source_path)
        if entry is None:
            record["status"] = "FAIL_SOURCE_PATH_MISSING"
            errors.append(f"recorded source path is absent at source head: {source_path}")
            source_records.append(record)
            continue

        record.update(
            {
                "mode": entry["mode"],
                "objectType": entry["type"],
                "observedBlobSha": entry["sha"],
            }
        )

        if entry["path"] != source_path:
            record["status"] = "FAIL_SOURCE_PATH_IDENTITY"
            errors.append(f"source path identity drift: {source_path}")
        elif entry["type"] != "blob" or not entry["mode"].startswith("100"):
            record["status"] = "FAIL_SOURCE_OBJECT_TYPE"
            errors.append(
                f"source path is not a regular Git file at recorded head: {source_path}"
            )
        elif entry["sha"] != expected_blob:
            record["status"] = "FAIL_SOURCE_BLOB_DRIFT"
            errors.append(
                f"source blob mismatch for {source_path}: "
                f"expected {expected_blob}, got {entry['sha']}"
            )
        else:
            record["status"] = "PASS_SOURCE_BLOB"

        source_records.append(record)

    receipt["sourceHistoryPresenceProven"] = (
        receipt["sourceCheckout"]["recordedCommitPresent"]
        and bool(source_records)
        and all(record.get("status") == "PASS_SOURCE_BLOB" for record in source_records)
    )
    receipt["overall"] = "PASS" if not errors else "FAIL"
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Matter Transfer migration source history from a local Git checkout."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="destination axm-matter-transfer repository root",
    )
    parser.add_argument(
        "--source-repo",
        type=Path,
        required=True,
        help="explicit local checkout of the recorded source repository",
    )
    parser.add_argument(
        "--require-origin",
        action="store_true",
        help="require origin metadata to match the recorded GitHub repository",
    )
    parser.add_argument(
        "--require-head",
        action="store_true",
        help="require the checkout's current HEAD to equal the recorded source head",
    )
    parser.add_argument("--json", action="store_true", help="emit full verification receipt")
    args = parser.parse_args()

    receipt = verify_source_checkout(
        args.repo_root,
        args.source_repo,
        require_origin=args.require_origin,
        require_head=args.require_head,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(
            f"{receipt['overall']}: "
            f"source history {'present' if receipt.get('sourceHistoryPresenceProven') else 'not proven'}"
        )
        for record in receipt.get("sourceRecords", []):
            print(f"- {record.get('status')}: {record.get('sourcePath')}")
        for error in receipt.get("errors", []):
            print(f"ERROR: {error}")

    return 0 if receipt["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
