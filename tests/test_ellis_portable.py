from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_ellis_zipapp.py"
SOURCE = ROOT / "experiments" / "ellis_wormhole.py"
FIXTURE = ROOT / "experiments" / "fixtures" / "ellis_zero_mass_v1.json"

sys.path.insert(0, str(ROOT / "tools"))
import build_ellis_zipapp as builder  # noqa: E402


def run(*args: str | Path, cwd: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [str(arg) for arg in args],
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class EllisPortableTests(unittest.TestCase):
    def build(self, directory: Path, stem: str = "ellis") -> tuple[Path, Path]:
        artifact = directory / f"{stem}.pyz"
        receipt = directory / f"{stem}.receipt.json"
        result = run(
            sys.executable,
            BUILDER,
            "build",
            "--root",
            ROOT,
            "--output",
            artifact,
            "--receipt",
            receipt,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return artifact, receipt

    def test_build_is_byte_stable_and_provider_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, first_receipt = self.build(root, "first")
            second, second_receipt = self.build(root, "second")
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_receipt.read_bytes(), second_receipt.read_bytes())

            result = run(
                sys.executable,
                BUILDER,
                "verify",
                "--artifact",
                first,
                "--receipt",
                first_receipt,
                "--source",
                SOURCE,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            verification = json.loads(result.stdout)
            self.assertEqual(verification["status"], "PASS")
            self.assertFalse(verification["authority"]["merge_authority"])
            self.assertFalse(verification["authority"]["canon_authority"])

    def test_zipapp_run_and_verify_match_provider_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact, _ = self.build(root)
            source_receipt = root / "source-receipt.json"
            portable_receipt = root / "portable-receipt.json"

            source_run = run(sys.executable, SOURCE, "run", "--input", FIXTURE, "--output", source_receipt)
            portable_run = run(sys.executable, artifact, "run", "--input", FIXTURE, "--output", portable_receipt)
            self.assertEqual(source_run.returncode, 0, source_run.stderr.decode())
            self.assertEqual(portable_run.returncode, 0, portable_run.stderr.decode())
            self.assertEqual(source_receipt.read_bytes(), portable_receipt.read_bytes())

            verification = run(
                sys.executable,
                artifact,
                "verify",
                "--input",
                FIXTURE,
                "--receipt",
                portable_receipt,
            )
            self.assertEqual(verification.returncode, 0, verification.stderr.decode())
            self.assertEqual(json.loads(verification.stdout)["status"], "PASS")

    def test_zipapp_runs_from_unrelated_directory_without_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staging = Path(tmp) / "staging"
            consumer = Path(tmp) / "independent-consumer"
            staging.mkdir()
            consumer.mkdir()
            artifact, build_receipt = self.build(staging)
            copied_artifact = consumer / "ellis-wormhole.pyz"
            copied_build_receipt = consumer / "ellis-wormhole.build.json"
            copied_fixture = consumer / "input.json"
            shutil.copyfile(artifact, copied_artifact)
            shutil.copyfile(build_receipt, copied_build_receipt)
            shutil.copyfile(FIXTURE, copied_fixture)

            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            output = consumer / "receipt.json"
            run_result = run(
                sys.executable,
                copied_artifact,
                "run",
                "--input",
                "input.json",
                "--output",
                "receipt.json",
                cwd=consumer,
                env=env,
            )
            self.assertEqual(run_result.returncode, 0, run_result.stderr.decode())
            verify_result = run(
                sys.executable,
                copied_artifact,
                "verify",
                "--input",
                "input.json",
                "--receipt",
                "receipt.json",
                cwd=consumer,
                env=env,
            )
            self.assertEqual(verify_result.returncode, 0, verify_result.stderr.decode())
            self.assertEqual(json.loads(verify_result.stdout)["status"], "PASS")
            self.assertTrue(output.is_file())

    def test_artifact_byte_tamper_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact, receipt = self.build(root)
            data = bytearray(artifact.read_bytes())
            data[len(data) // 2] ^= 1
            artifact.write_bytes(data)
            result = run(
                sys.executable,
                BUILDER,
                "verify",
                "--artifact",
                artifact,
                "--receipt",
                receipt,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"artifact SHA-256 mismatch", result.stderr)

    def test_resealed_extra_member_still_fails_inventory_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact, receipt = self.build(root)
            with zipfile.ZipFile(artifact, "a", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("unexpected.txt", b"not admitted\n")
            raw_receipt = json.loads(receipt.read_text(encoding="utf-8"))
            import hashlib

            artifact_bytes = artifact.read_bytes()
            raw_receipt["artifact"]["bytes"] = len(artifact_bytes)
            raw_receipt["artifact"]["sha256"] = hashlib.sha256(artifact_bytes).hexdigest()
            receipt.write_text(
                json.dumps(raw_receipt, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            result = run(
                sys.executable,
                BUILDER,
                "verify",
                "--artifact",
                artifact,
                "--receipt",
                receipt,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"zip member inventory/order mismatch", result.stderr)

    def test_provider_source_drift_is_not_silently_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact, receipt = self.build(root)
            drifted = root / "drifted.py"
            drifted.write_bytes(SOURCE.read_bytes() + b"\n# drift\n")
            result = run(
                sys.executable,
                BUILDER,
                "verify",
                "--artifact",
                artifact,
                "--receipt",
                receipt,
                "--source",
                drifted,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"differs from provider source", result.stderr)

    def test_interrupted_bundle_publish_resumes_from_exact_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "ellis.pyz"
            receipt = root / "ellis.receipt.json"
            real_link = os.link
            link_count = 0

            def interrupt_before_receipt(source: Path, destination: Path) -> None:
                nonlocal link_count
                link_count += 1
                if link_count == 2:
                    raise OSError("injected interruption before receipt commit")
                real_link(source, destination)

            with mock.patch.object(os, "link", side_effect=interrupt_before_receipt):
                with self.assertRaisesRegex(builder.PortableError, "cannot publish receipt"):
                    builder.build(ROOT, artifact, receipt)

            self.assertTrue(artifact.is_file())
            self.assertFalse(receipt.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])

            recovered = builder.build(ROOT, artifact, receipt)
            verified = builder.verify(artifact, receipt, SOURCE)
            self.assertEqual(verified["status"], "PASS")
            self.assertEqual(verified["artifact_sha256"], recovered["artifact"]["sha256"])
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_concurrent_bundle_builders_report_one_commit_winner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "ellis.pyz"
            receipt = root / "ellis.receipt.json"
            barrier = threading.Barrier(2)
            real_write_bytes = Path.write_bytes

            def coordinate_old_artifact_writes(path: Path, data: bytes) -> int:
                if path == artifact:
                    barrier.wait()
                return real_write_bytes(path, data)

            def build_once() -> str:
                try:
                    builder.build(ROOT, artifact, receipt)
                except builder.PortableError:
                    return "HELD"
                return "COMMITTED"

            with mock.patch.object(Path, "write_bytes", coordinate_old_artifact_writes):
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                    outcomes = list(executor.map(lambda _index: build_once(), range(2)))

            self.assertEqual(sorted(outcomes), ["COMMITTED", "HELD"])
            self.assertEqual(builder.verify(artifact, receipt, SOURCE)["status"], "PASS")
            self.assertEqual(list(root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
