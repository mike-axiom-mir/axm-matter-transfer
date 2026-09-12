from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
sys.path.insert(0, str(EXPERIMENTS))

from ellis_wormhole import run_experiment  # noqa: E402
from ellis_geometry_viewer import ContractError, VIEWER_SCHEMA, render_html  # noqa: E402

FIXTURE = ROOT / "experiments" / "fixtures" / "ellis_zero_mass_v1.json"


class EllisGeometryViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_input = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.receipt = run_experiment(cls.raw_input)

    def test_html_is_bound_to_receipt_truth(self):
        page = render_html(self.receipt)
        self.assertIn(VIEWER_SCHEMA, page)
        self.assertIn(self.receipt["receipt_sha256"], page)
        self.assertIn(self.receipt["claim_ceiling"], page)
        self.assertIn("DISPLAY ≠ PROOF", page)
        self.assertIn("Lines between recorded sample points are visual guides only", page)

    def test_render_does_not_mutate_receipt(self):
        before = deepcopy(self.receipt)
        render_html(self.receipt)
        self.assertEqual(self.receipt, before)

    def test_missing_sample_field_holds(self):
        broken = deepcopy(self.receipt)
        del broken["results"]["samples"][0]["areal_radius"]
        with self.assertRaisesRegex(ContractError, "missing viewer fields"):
            render_html(broken)

    def test_non_numeric_sample_holds(self):
        broken = deepcopy(self.receipt)
        broken["results"]["samples"][0]["l"] = "left"
        with self.assertRaisesRegex(ContractError, "must be numeric"):
            render_html(broken)


if __name__ == "__main__":
    unittest.main()
