# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import csv
import json
import unittest
from pathlib import Path
from fcst_tools.delivery import validate_scope

ROOT = Path(__file__).resolve().parents[1]


class DeliveryScopeTests(unittest.TestCase):
    def setUp(self):
        def read(name):
            return json.loads((ROOT / name).read_text(encoding="utf-8"))
        with (ROOT / "plans/work-packages.csv").open(encoding="utf-8", newline="") as stream:
            packages = list(csv.DictReader(stream))
        self.args = [read("plans/delivery-scope.json"), packages, read("plans/evidence/WP-01.json"),
                     read("inventory/gaps.json"), read("CMakePresets.json"), read("ci/host-profile.json")]

    def test_deferred_platform_cannot_enter_active_scope(self):
        self.assertEqual(validate_scope(*self.args), [])
        for platform in ["Linux", "macOS"]:
            changed = copy.deepcopy(self.args)
            changed[0]["active_platforms"].append(platform)
            self.assertIn("non_windows_active_platform", validate_scope(*changed))

    def test_ports_cannot_precede_windows_completion(self):
        changed = copy.deepcopy(self.args)
        port = next(p for p in changed[1] if p["id"] == "WP-22")
        port.update(completion_gate="Q1", depends_on="WP-02")
        self.assertIn("deferred_ports_scheduled_before_windows_completion", validate_scope(*changed))

    def test_inventory_closure_cannot_claim_qualification_or_lose_gap_owner(self):
        changed = copy.deepcopy(self.args)
        changed[0]["wp01"]["qualification_claim"] = True
        changed[3]["gaps"][0]["owner_work_package"] = "WP-01"
        errors = validate_scope(*changed)
        self.assertIn("inventory_completion_or_qualification_claim_invalid", errors)
        self.assertIn("qualification_gap_not_assigned", errors)
