from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from verify_migration_source import verify_source_checkout  # noqa: E402


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


class MigrationSourceWitnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        self.source.mkdir()
        self.destination.mkdir()

        run_git(self.source, "init", "-q")
        run_git(self.source, "config", "user.email", "fixture@example.invalid")
        run_git(self.source, "config", "user.name", "Fixture")
        run_git(
            self.source,
            "remote",
            "add",
            "origin",
            "https://github.com/example/source-repo.git",
        )

        self.files = {
            "docs/research/A.md": b"alpha research\n",
            "docs/research/B.md": b"beta research\n",
            "docs/C.md": b"action report\n",
            "data/registry.json": b'{"source":true}\n',
        }
        for relative, data in self.files.items():
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        run_git(self.source, "add", ".")
        run_git(self.source, "commit", "-qm", "source fixture")
        self.recorded_head = run_git(self.source, "rev-parse", "HEAD")
        self.blobs = {
            relative: run_git(self.source, "rev-parse", f"{self.recorded_head}:{relative}")
            for relative in self.files
        }

        notes_dir = self.destination / "provenance" / "factual-space-pr2"
        notes_dir.mkdir(parents=True)
        self.notes_path = notes_dir / "MIGRATION_NOTES.md"
        self._write_notes()

        for relative in ("docs/research/A.md", "docs/research/B.md", "docs/C.md"):
            target = notes_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.files[relative])

        semantic = notes_dir / "data/registry.json"
        semantic.parent.mkdir(parents=True, exist_ok=True)
        semantic.write_text('{"destination":"semantic migration"}\n', encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_notes(
        self,
        *,
        head: str | None = None,
        semantic_blob: str | None = None,
    ) -> None:
        head = head or self.recorded_head
        semantic_blob = semantic_blob or self.blobs["data/registry.json"]
        self.notes_path.write_text(
            "\n".join(
                [
                    "# Migration Notes — fixture",
                    "",
                    "**Source repository:** `example/source-repo`",
                    f"**Source head:** `{head}`",
                    "",
                    "## Source files",
                    "",
                    "| Source path | Source blob SHA | Migration treatment |",
                    "|---|---|---|",
                    f"| `docs/research/A.md` | `{self.blobs['docs/research/A.md']}` | copied as human-readable provenance |",
                    f"| `docs/research/B.md` | `{self.blobs['docs/research/B.md']}` | copied as human-readable provenance |",
                    f"| `docs/C.md` | `{self.blobs['docs/C.md']}` | copied as human-readable provenance |",
                    f"| `data/registry.json` | `{semantic_blob}` | semantically migrated; source SHA retained |",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    def test_passes_exact_recorded_source_history_without_requiring_semantic_destination_identity(self) -> None:
        receipt = verify_source_checkout(
            self.destination,
            self.source,
            require_origin=True,
            require_head=True,
        )
        self.assertEqual(receipt["overall"], "PASS")
        self.assertTrue(receipt["destinationProvenanceVerified"])
        self.assertTrue(receipt["sourceHistoryPresenceProven"])
        self.assertTrue(receipt["sourceCheckout"]["originMatches"])
        self.assertTrue(receipt["sourceCheckout"]["checkedOutHeadMatches"])
        self.assertEqual(
            [record["status"] for record in receipt["sourceRecords"]],
            ["PASS_SOURCE_BLOB"] * 4,
        )
        self.assertFalse(receipt["authority"]["sourceAuthenticationProven"])
        self.assertFalse(receipt["authority"]["mergeAuthority"])
        self.assertFalse(receipt["authority"]["canonAuthority"])

    def test_fails_when_recorded_source_commit_is_absent(self) -> None:
        missing = "f" * 40
        self._write_notes(head=missing)
        receipt = verify_source_checkout(self.destination, self.source)
        self.assertEqual(receipt["overall"], "FAIL")
        self.assertFalse(receipt["sourceCheckout"]["recordedCommitPresent"])
        self.assertIn(f"recorded source commit is absent: {missing}", receipt["errors"])

    def test_catches_source_blob_drift_on_semantic_migration_row(self) -> None:
        wrong = "0" * 40
        self._write_notes(semantic_blob=wrong)
        receipt = verify_source_checkout(self.destination, self.source)
        self.assertEqual(receipt["overall"], "FAIL")
        semantic = next(
            record for record in receipt["sourceRecords"]
            if record["sourcePath"] == "data/registry.json"
        )
        self.assertEqual(semantic["status"], "FAIL_SOURCE_BLOB_DRIFT")
        self.assertEqual(semantic["observedBlobSha"], self.blobs["data/registry.json"])

    def test_default_can_verify_recorded_commit_after_checkout_moves_but_strict_head_gate_holds(self) -> None:
        later = self.source / "later.txt"
        later.write_text("later\n", encoding="utf-8")
        run_git(self.source, "add", "later.txt")
        run_git(self.source, "commit", "-qm", "later checkout")

        relaxed = verify_source_checkout(self.destination, self.source)
        self.assertEqual(relaxed["overall"], "PASS")
        self.assertFalse(relaxed["sourceCheckout"]["checkedOutHeadMatches"])
        self.assertTrue(relaxed["sourceHistoryPresenceProven"])

        strict = verify_source_checkout(
            self.destination,
            self.source,
            require_head=True,
        )
        self.assertEqual(strict["overall"], "FAIL")
        self.assertTrue(strict["sourceHistoryPresenceProven"])
        self.assertTrue(
            any("checked-out source HEAD does not match" in error for error in strict["errors"])
        )

    def test_required_origin_rejects_repository_identity_metadata_drift(self) -> None:
        run_git(
            self.source,
            "remote",
            "set-url",
            "origin",
            "https://github.com/example/other-repo.git",
        )
        receipt = verify_source_checkout(
            self.destination,
            self.source,
            require_origin=True,
        )
        self.assertEqual(receipt["overall"], "FAIL")
        self.assertFalse(receipt["sourceCheckout"]["originMatches"])
        self.assertTrue(
            any("source origin does not match" in error for error in receipt["errors"])
        )

    def test_destination_provenance_failure_blocks_source_upgrade(self) -> None:
        copied = (
            self.destination
            / "provenance"
            / "factual-space-pr2"
            / "docs"
            / "research"
            / "A.md"
        )
        copied.write_text("drifted destination\n", encoding="utf-8")
        receipt = verify_source_checkout(self.destination, self.source)
        self.assertEqual(receipt["overall"], "FAIL")
        self.assertFalse(receipt["destinationProvenanceVerified"])
        self.assertEqual(receipt["sourceRecords"], [])
        self.assertIn("destination migration provenance gate did not pass", receipt["errors"])


if __name__ == "__main__":
    unittest.main()
