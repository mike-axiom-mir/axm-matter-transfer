import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.research_capsule import _manifest_digest, _sha256, verify_capsule
from tools.research_state import ROOT


class ResearchCapsuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.capsule = self.work / "capsule"
        command = [
            sys.executable,
            str(ROOT / "tools/research_capsule.py"),
            "build",
            "observer_game_layer",
            "--output",
            str(self.capsule),
        ]
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["valid"])

    def tearDown(self):
        self.temp.cleanup()

    def _manifest(self, capsule=None):
        path = (capsule or self.capsule) / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_manifest(self, manifest, capsule=None):
        path = (capsule or self.capsule) / "manifest.json"
        manifest["capsule_sha256"] = _manifest_digest(manifest)
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_repository_built_capsule_verifies(self):
        receipt = verify_capsule(self.capsule)
        self.assertTrue(receipt["valid"])
        self.assertEqual("observer_game_layer", receipt["profile"])
        self.assertEqual(5, receipt["files_verified"])
        self.assertFalse(receipt["execution_authority"])
        self.assertFalse(receipt["scientific_validation"])

    def test_received_capsule_verifies_outside_source_tree(self):
        received = self.work / "received" / "matter-transfer-capsule"
        received.parent.mkdir()
        shutil.copytree(self.capsule, received)
        isolated_cwd = self.work / "consumer"
        isolated_cwd.mkdir()
        completed = subprocess.run(
            [sys.executable, str(received / "verify.py"), "verify", str(received)],
            cwd=isolated_cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        receipt = json.loads(completed.stdout)
        self.assertTrue(receipt["valid"])
        self.assertEqual("integrity_and_lineage_evidence_only", receipt["authority"])

    def test_tampered_plan_bytes_fail_closed(self):
        plan_path = self.capsule / "resolved-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["enabled"] = not plan["enabled"]
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
            verify_capsule(self.capsule)

    def test_resealed_source_substitution_still_breaks_plan_lineage(self):
        focus_path = self.capsule / "sources/current_focus.json"
        raw = focus_path.read_bytes() + b"\n"
        focus_path.write_bytes(raw)
        manifest = self._manifest()
        focus_record = next(record for record in manifest["files"] if record["role"] == "source_focus")
        focus_record["bytes"] = len(raw)
        focus_record["sha256"] = _sha256(raw)
        self._write_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "source lineage mismatch"):
            verify_capsule(self.capsule)

    def test_undeclared_file_fails_closed(self):
        (self.capsule / "surprise.txt").write_text("not declared\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            verify_capsule(self.capsule)

    def test_resealed_traversal_path_is_rejected_before_read(self):
        manifest = self._manifest()
        manifest["files"][0]["path"] = "../escape.json"
        self._write_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "unsafe component"):
            verify_capsule(self.capsule)

    def test_symlink_substitution_is_rejected(self):
        target = self.capsule / "resolved-plan.json"
        original = target.read_bytes()
        target.unlink()
        outside = self.work / "outside-plan.json"
        outside.write_bytes(original)
        try:
            target.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            verify_capsule(self.capsule)


if __name__ == "__main__":
    unittest.main()
