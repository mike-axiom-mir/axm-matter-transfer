from __future__ import annotations

import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from tools import generate_public_capabilities as discovery


ROOT = Path(__file__).resolve().parents[1]


class PublicCapabilityDiscoveryTests(unittest.TestCase):
    def _provider_copy(self, destination: Path) -> Path:
        for relative in (
            discovery.MARKER_PATH,
            discovery.BUILDER_PATH,
            discovery.EXPERIMENT_PATH,
            discovery.FIXTURE_PATH,
            discovery.LICENSE_PATH,
        ):
            source = ROOT / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return destination

    def test_committed_generated_artifacts_are_exact(self) -> None:
        ok, mismatches, artifacts = discovery.check_artifacts(ROOT)
        self.assertTrue(ok, mismatches)
        self.assertEqual(
            set(artifacts),
            {discovery.REGISTRY_PATH, discovery.RECEIPT_PATH},
        )

    def test_public_record_preserves_portable_truth_boundary(self) -> None:
        artifacts = discovery.build_artifacts(ROOT)
        record = json.loads(artifacts[discovery.REGISTRY_PATH])
        self.assertEqual(record["schema"], "axm.public-capability/v1")
        self.assertEqual(record["id"], discovery.CAPABILITY_ID)
        self.assertIsNone(record["status"])
        self.assertEqual(record["providers"], [discovery.REPOSITORY])
        self.assertEqual(record["runtime"]["python"], ">=3.11")
        self.assertEqual(record["runtime"]["dependencies"], 0)
        self.assertFalse(record["runtime"]["network"])
        self.assertFalse(record["runtime"]["account"])
        self.assertFalse(record["runtime"]["aiModel"])
        self.assertEqual(record["truth"]["claimCeiling"], discovery.CLAIM_CEILING)
        self.assertFalse(record["truth"]["physicalMacroscopicMatterTransferEstablished"])
        self.assertTrue(record["authority"]["discoveryOnly"])
        for key in (
            "execution",
            "automaticSelection",
            "automaticInstall",
            "scientificPromotion",
            "engineering",
            "merge",
            "canon",
        ):
            self.assertFalse(record["authority"][key])

    def test_registry_is_derived_from_real_portable_builder_output(self) -> None:
        admitted = discovery.provider_contract(ROOT)
        artifact = admitted["builder"].build_bytes(admitted["source"])
        with zipfile.ZipFile(io.BytesIO(artifact), "r") as archive:
            metadata = json.loads(archive.read("AXM_PORTABLE.json"))
            packaged_source = archive.read("ellis_wormhole.py")
        self.assertEqual(packaged_source, admitted["source"])
        self.assertEqual(metadata, admitted["metadata"])
        self.assertEqual(metadata["capability_id"], discovery.CAPABILITY_ID)
        self.assertEqual(metadata["authority"], discovery.SAFE_AUTHORITY)

    def test_public_marker_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._provider_copy(Path(temporary))
            marker_path = root / discovery.MARKER_PATH
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            marker["public"] = False
            marker_path.write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaisesRegex(discovery.DiscoveryError, "marker drift"):
                discovery.build_artifacts(root)

    def test_source_symlink_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._provider_copy(Path(temporary))
            experiment_path = root / discovery.EXPERIMENT_PATH
            external = root.parent / f"{root.name}-external-ellis.py"
            external.write_bytes(experiment_path.read_bytes())
            experiment_path.unlink()
            try:
                experiment_path.symlink_to(external)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            try:
                with self.assertRaisesRegex(discovery.DiscoveryError, "non-symlink"):
                    discovery.build_artifacts(root)
            finally:
                external.unlink(missing_ok=True)

    def test_authority_widening_in_builder_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._provider_copy(Path(temporary))
            builder_path = root / discovery.BUILDER_PATH
            source = builder_path.read_text(encoding="utf-8")
            marker = '"automatic_execution": False'
            self.assertIn(marker, source)
            builder_path.write_text(
                source.replace(marker, '"automatic_execution": True', 1),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(discovery.DiscoveryError, "authority drift"):
                discovery.build_artifacts(root)

    def test_generated_registry_drift_is_reported_without_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = self._provider_copy(Path(temporary))
            discovery.write_artifacts(root)
            registry_path = root / discovery.REGISTRY_PATH
            original_receipt = (root / discovery.RECEIPT_PATH).read_bytes()
            registry_path.write_text(
                registry_path.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
            ok, mismatches, _ = discovery.check_artifacts(root)
            self.assertFalse(ok)
            self.assertEqual(mismatches, [discovery.REGISTRY_PATH])
            self.assertEqual(
                (root / discovery.RECEIPT_PATH).read_bytes(),
                original_receipt,
            )


if __name__ == "__main__":
    unittest.main()
