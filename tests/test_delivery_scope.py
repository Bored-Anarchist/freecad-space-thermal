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

    def test_stretch_goals_cannot_become_work_packages_or_release_gates(self):
        for field, value in [("work_package", "WP-22"), ("completion_gate", "Q2"), ("blocks_delivery", True)]:
            changed = copy.deepcopy(self.args)
            changed[0]["stretch_goals"]["SG-PLATFORMS"][field] = value
            self.assertIn("stretch_goal_in_committed_delivery", validate_scope(*changed))
        changed = copy.deepcopy(self.args)
        changed[1].append({"id": "WP-22"})
        self.assertIn("stretch_goal_in_committed_delivery", validate_scope(*changed))

    def test_inventory_closure_cannot_claim_qualification_or_lose_gap_owner(self):
        changed = copy.deepcopy(self.args)
        changed[0]["wp01"]["qualification_claim"] = True
        changed[3]["gaps"][0]["owner_work_package"] = "WP-01"
        errors = validate_scope(*changed)
        self.assertIn("inventory_completion_or_qualification_claim_invalid", errors)
        self.assertIn("qualification_gap_not_assigned", errors)
