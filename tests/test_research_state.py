import copy
import json
import unittest
from pathlib import Path

from tools.research_state import ROOT, resolve_profile, validate, validation_receipt


class ResearchStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract_raw = (ROOT / "contracts/research_state_contract_v1.json").read_bytes()
        cls.focus_raw = (ROOT / "data/current_focus_v0_2.json").read_bytes()
        cls.registry_raw = (ROOT / "provenance/factual-space-pr2/data/matter_transfer_organ_registry_v0_1.json").read_bytes()
        cls.contract = json.loads(cls.contract_raw)
        cls.focus = json.loads(cls.focus_raw)
        cls.registry = json.loads(cls.registry_raw)

    def test_repository_baseline_validates(self):
        self.assertEqual([], validate(self.focus, self.registry, self.contract))

    def test_validation_receipt_is_deterministic(self):
        first = validation_receipt(
            self.focus, self.registry, self.contract,
            self.focus_raw, self.registry_raw, self.contract_raw,
        )
        second = validation_receipt(
            self.focus, self.registry, self.contract,
            self.focus_raw, self.registry_raw, self.contract_raw,
        )
        self.assertEqual(first, second)
        self.assertTrue(first["valid"])

    def test_observer_profile_is_dependency_closed(self):
        plan = resolve_profile(
            "observer_game_layer", self.focus, self.registry, self.contract,
            self.focus_raw, self.registry_raw, self.contract_raw,
        )
        ids = [organ["id"] for organ in plan["resolved_organs"]]
        positions = {organ_id: index for index, organ_id in enumerate(ids)}
        self.assertEqual(24, len(ids))
        self.assertIn("MT-O40", plan["added_transitive_dependencies"])
        self.assertIn("MT-O41", plan["added_transitive_dependencies"])
        for organ in plan["resolved_organs"]:
            for dependency in organ["depends_on"]:
                self.assertLess(positions[dependency], positions[organ["id"]])

    def test_unknown_dependency_fails_closed(self):
        registry = copy.deepcopy(self.registry)
        registry["organs"][0]["depends_on"] = ["MT-DOES-NOT-EXIST"]
        problems = validate(self.focus, registry, self.contract)
        self.assertIn("unknown_dependency", {problem.code for problem in problems})

    def test_dependency_cycle_fails_closed(self):
        registry = copy.deepcopy(self.registry)
        registry["organs"][0]["depends_on"] = ["MT-O44"]
        problems = validate(self.focus, registry, self.contract)
        self.assertIn("dependency_cycle", {problem.code for problem in problems})

    def test_summary_cannot_drift_from_status_bits(self):
        focus = copy.deepcopy(self.focus)
        focus["current_status"]["summary"] = "PHYSICAL_TRANSFER_PROVEN"
        problems = validate(focus, self.registry, self.contract)
        self.assertIn("derived_summary_mismatch", {problem.code for problem in problems})

    def test_current_target_cannot_reference_unknown_legacy_mode(self):
        focus = copy.deepcopy(self.focus)
        focus["primary_target"]["closest_legacy_modes"].append("MT-99")
        problems = validate(focus, self.registry, self.contract)
        self.assertIn("unknown_legacy_mode", {problem.code for problem in problems})


if __name__ == "__main__":
    unittest.main()
