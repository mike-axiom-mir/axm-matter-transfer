from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "ellis_wormhole.py"
FIXTURE = ROOT / "experiments" / "fixtures" / "ellis_zero_mass_v1.json"
sys.path.insert(0, str(EXPERIMENT.parent))

from ellis_wormhole import ContractError, run_experiment, verify_receipt  # noqa: E402


class EllisWormholeExperimentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_fixture_reproduces_declared_geometry_and_exposes_nec_cost(self) -> None:
        receipt = run_experiment(self.fixture)
        self.assertEqual(receipt["status"], "PASS")
        self.assertTrue(all(gate["status"] == "PASS" for gate in receipt["gates"]))
        self.assertLessEqual(receipt["results"]["numeric_absolute_error"], self.fixture["tolerance"])
        throat = receipt["results"]["samples"][2]
        self.assertEqual(throat["areal_radius"], 2.0)
        self.assertEqual(throat["shape_b"], 2.0)
        self.assertEqual(throat["scaled_radial_nec_8pi_a2_rho_plus_pr"], -2.0)
        self.assertFalse(receipt["truth_boundary"]["engineering_feasibility_established"])
        self.assertFalse(receipt["truth_boundary"]["matter_transfer_demonstrated"])

    def test_repeated_execution_is_byte_stable(self) -> None:
        first = json.dumps(run_experiment(self.fixture), sort_keys=True, separators=(",", ":"))
        second = json.dumps(run_experiment(self.fixture), sort_keys=True, separators=(",", ":"))
        self.assertEqual(first, second)

    def test_predeclared_prediction_miss_holds_instead_of_promoting(self) -> None:
        changed = copy.deepcopy(self.fixture)
        changed["predictions"]["right_station_areal_radius"] = 7.0
        receipt = run_experiment(changed)
        self.assertEqual(receipt["status"], "HOLD")
        prediction_gate = next(gate for gate in receipt["gates"] if gate["name"] == "predeclared_predictions")
        self.assertEqual(prediction_gate["status"], "HOLD")

    def test_input_contract_rejects_unknown_model_and_unbounded_work(self) -> None:
        changed = copy.deepcopy(self.fixture)
        changed["model"] = "engineering-portal"
        with self.assertRaisesRegex(ContractError, "model must be"):
            run_experiment(changed)
        changed = copy.deepcopy(self.fixture)
        changed["integration_intervals"] = 1_000_002
        with self.assertRaisesRegex(ContractError, "between 32 and 1000000"):
            run_experiment(changed)

    def test_cli_rejects_duplicate_input_keys_before_model_admission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            duplicate_input = Path(temporary) / "duplicate-input.json"
            receipt_path = Path(temporary) / "receipt.json"
            fixture_text = FIXTURE.read_text(encoding="utf-8")
            duplicate_input.write_text(
                fixture_text.replace(
                    '  "model": "ellis-zero-mass-wormhole",',
                    '  "model": "engineering-portal",\n  "model": "ellis-zero-mass-wormhole",',
                    1,
                ),
                encoding="utf-8",
            )
            run = subprocess.run(
                [sys.executable, str(EXPERIMENT), "run", "--input", str(duplicate_input), "--output", str(receipt_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertIn("duplicate JSON object key: model", run.stderr)
            self.assertFalse(receipt_path.exists())

    def test_cli_rejects_oversized_json_before_semantic_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            oversized_input = Path(temporary) / "oversized-input.json"
            receipt_path = Path(temporary) / "receipt.json"
            oversized_input.write_text(
                (" " * (1024 * 1024 + 1)) + FIXTURE.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            run = subprocess.run(
                [sys.executable, str(EXPERIMENT), "run", "--input", str(oversized_input), "--output", str(receipt_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertIn("exceeds 1048576-byte limit", run.stderr)
            self.assertFalse(receipt_path.exists())

    def test_cli_verify_rejects_duplicate_keys_in_receipt_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            ambiguous_receipt = Path(temporary) / "ambiguous-receipt.json"
            run = subprocess.run(
                [sys.executable, str(EXPERIMENT), "run", "--input", str(FIXTURE), "--output", str(receipt_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            receipt_text = receipt_path.read_text(encoding="utf-8")
            marker = '"status":"PASS"'
            marker_index = receipt_text.rfind(marker)
            self.assertGreaterEqual(marker_index, 0)
            ambiguous_receipt.write_text(
                receipt_text[:marker_index]
                + '"status":"HOLD","status":"PASS"'
                + receipt_text[marker_index + len(marker):],
                encoding="utf-8",
            )
            verify = subprocess.run(
                [sys.executable, str(EXPERIMENT), "verify", "--input", str(FIXTURE), "--receipt", str(ambiguous_receipt)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verify.returncode, 2, verify.stderr)
            self.assertIn("duplicate JSON object key: status", verify.stderr)

    def test_receipt_tampering_and_resealed_false_result_fail_reexecution(self) -> None:
        receipt = run_experiment(self.fixture)
        tampered = copy.deepcopy(receipt)
        tampered["results"]["analytic_station_to_station_proper_distance"] = 1.0
        with self.assertRaisesRegex(ContractError, "digest mismatch"):
            verify_receipt(self.fixture, tampered)

        tampered["receipt_sha256"] = receipt["receipt_sha256"]
        del tampered["receipt_sha256"]
        import hashlib

        data = (json.dumps(tampered, sort_keys=True, separators=(",", ":")) + "\n").encode()
        tampered["receipt_sha256"] = hashlib.sha256(data).hexdigest()
        with self.assertRaisesRegex(ContractError, "deterministic re-execution"):
            verify_receipt(self.fixture, tampered)

    def test_cli_run_verify_and_no_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            receipt_path = Path(temporary) / "receipt.json"
            run = subprocess.run(
                [sys.executable, str(EXPERIMENT), "run", "--input", str(FIXTURE), "--output", str(receipt_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            verify = subprocess.run(
                [sys.executable, str(EXPERIMENT), "verify", "--input", str(FIXTURE), "--receipt", str(receipt_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verify.returncode, 0, verify.stderr)
            self.assertEqual(json.loads(verify.stdout)["status"], "PASS")
            refused = subprocess.run(
                [sys.executable, str(EXPERIMENT), "run", "--input", str(FIXTURE), "--output", str(receipt_path)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(refused.returncode, 2)
            self.assertIn("refusing to overwrite", refused.stderr)

    def test_cli_run_refuses_dangling_symlink_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            redirected = root / "redirected-receipt.json"
            output = root / "requested-receipt.json"
            try:
                output.symlink_to(redirected)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            run = subprocess.run(
                [sys.executable, str(EXPERIMENT), "run", "--input", str(FIXTURE), "--output", str(output)],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(run.returncode, 2)
            self.assertIn("refusing to overwrite", run.stderr)
            self.assertTrue(output.is_symlink())
            self.assertFalse(redirected.exists())


if __name__ == "__main__":
    unittest.main()
