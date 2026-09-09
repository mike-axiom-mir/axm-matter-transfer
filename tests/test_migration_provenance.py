from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import verify_migration_provenance as verifier  # noqa: E402


class MigrationProvenanceTests(unittest.TestCase):
    def _fixture(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        base = root / "provenance" / "factual-space-pr2"
        exact_specs = [
            ("docs/research/a.md", b"alpha\n"),
            ("docs/research/b.md", b"beta\n"),
            ("docs/report.md", b"gamma\n"),
        ]
        rows = []
        for rel, data in exact_specs:
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            rows.append(
                f"| `{rel}` | `{verifier.git_blob_sha1(data)}` | "
                "copied as human-readable provenance |"
            )

        semantic_rel = "data/registry.json"
        semantic_target = base / semantic_rel
        semantic_target.parent.mkdir(parents=True, exist_ok=True)
        semantic_target.write_text(json.dumps({"migrated": True}), encoding="utf-8")
        rows.append(
            f"| `{semantic_rel}` | `{'0' * 40}` | "
            "semantically migrated; source SHA retained because bytes may differ |"
        )

        notes = (
            "# Migration Notes\n\n"
            "**Source repository:** `owner/source`\n"
            f"**Source head:** `{'1' * 40}`\n\n"
            "| Source path | Source blob SHA | Migration treatment |\n"
            "|---|---|---|\n"
            + "\n".join(rows)
            + "\n"
        )
        (base / "MIGRATION_NOTES.md").write_text(notes, encoding="utf-8")
        return temp, root

    def test_git_blob_sha_matches_known_git_identity(self) -> None:
        self.assertEqual(
            verifier.git_blob_sha1(b"hello\n"),
            "ce013625030ba8dba906f756967f9e9ca394464a",
        )

    def test_exact_copies_pass_while_semantic_migration_may_differ(self) -> None:
        temp, root = self._fixture()
        self.addCleanup(temp.cleanup)
        receipt = verifier.verify_repository(root)
        self.assertEqual(receipt["overall"], "PASS")
        self.assertEqual(receipt["exactCopyCount"], 3)
        self.assertEqual(receipt["semanticMigrationCount"], 1)
        semantic = [r for r in receipt["records"] if not r["byteIdenticalRequired"]][0]
        self.assertNotEqual(semantic["currentBlobSha"], semantic["sourceBlobSha"])
        self.assertEqual(semantic["status"], "PASS_SEMANTIC_BOUNDARY")

    def test_tampered_exact_copy_fails_closed(self) -> None:
        temp, root = self._fixture()
        self.addCleanup(temp.cleanup)
        target = root / "provenance/factual-space-pr2/docs/research/a.md"
        target.write_text("tampered\n", encoding="utf-8")
        receipt = verifier.verify_repository(root)
        self.assertEqual(receipt["overall"], "FAIL")
        self.assertTrue(any("exact-copy provenance drift" in e for e in receipt["errors"]))

    def test_unsafe_path_is_rejected_before_file_access(self) -> None:
        temp, root = self._fixture()
        self.addCleanup(temp.cleanup)
        notes = root / "provenance/factual-space-pr2/MIGRATION_NOTES.md"
        text = notes.read_text(encoding="utf-8")
        text = text.replace(
            "| `docs/research/a.md` |",
            "| `../outside.md` |",
            1,
        )
        notes.write_text(text, encoding="utf-8")
        receipt = verifier.verify_repository(root)
        self.assertEqual(receipt["overall"], "FAIL")
        self.assertTrue(any("unsafe or non-canonical source path" in e for e in receipt["errors"]))


if __name__ == "__main__":
    unittest.main()
