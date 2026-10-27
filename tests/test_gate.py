# SPDX-License-Identifier: MIT OR Apache-2.0
import unittest
from fcst_app import capabilities
from fcst_tools.gate import evaluate


class GateTests(unittest.TestCase):
    def test_missing_and_zero_cases_rejected(self):
        self.assertEqual(evaluate([], [])["status"], "failed")
        self.assertEqual(evaluate(["required"], [])["status"], "failed")

    def test_skipped_blocked_and_failed_rejected(self):
        for status in ["skipped", "blocked", "failed", "interrupted", "cancelled"]:
            self.assertEqual(evaluate(["required"], [{"id": "required", "status": status}])["status"], "failed")

    def test_duplicate_and_substituted_coverage_rejected(self):
        record = {"id": "required", "status": "passed"}
        self.assertEqual(evaluate(["required"], [record, record])["status"], "failed")
        self.assertEqual(evaluate(["other"], [record])["status"], "failed")

    def test_correct_coverage_passes(self):
        self.assertEqual(evaluate(["required"], [{"id": "required", "status": "passed"}])["status"], "passed")

    def test_skeleton_never_claims_solver_implementation(self):
        self.assertFalse(capabilities()["solver_available"])
        self.assertFalse(capabilities()["vendor_runtime_required"])
