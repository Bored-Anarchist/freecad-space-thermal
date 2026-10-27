# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_github import assess_validation


class ValidationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.repo = {"private": True}
        self.runners = {"total_count": 0}
        self.policy = {"enabled": False, "public_pr_execution": False, "reviewed_candidate_required": True,
                       "fixture_storage": "runner_local_only"}
        self.workflow = {"on": ["workflow_dispatch"], "permissions": {"contents": "read"}, "jobs": {
            "prerequisites": {"runs-on": "ubuntu-24.04", "steps": [
                {"uses": "actions/checkout@11d5960a326750d5838078e36cf38b85af677262", "with": {"persist-credentials": "false"}},
                {"run": "echo 'blocked: exact licensed profiles and reviewed candidate promotion not configured'\nexit 1\n"}]}}}
        self.permissions = {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": False}

    def assess(self, workflow=None, policy=None):
        return assess_validation(self.repo, self.runners, policy or self.policy, workflow or self.workflow, self.permissions)

    def test_closed_boundary_and_privileged_trigger_rejection(self):
        self.assertEqual(self.assess(), [])
        for trigger in (["pull_request"], ["pull_request_target"], ["workflow_run"]):
            changed = copy.deepcopy(self.workflow)
            changed["on"] = trigger
            self.assertIn("validation_untrusted_trigger_or_jobs", self.assess(workflow=changed))
        self.runners["total_count"] = 1
        self.assertIn("unqualified_validation_boundary", self.assess())

    def test_guard_bypass_policy_activation_and_write_permissions_rejected(self):
        for mutation in (lambda w: w["jobs"]["prerequisites"].update({"runs-on": "self-hosted"}),
                         lambda w: w["jobs"]["prerequisites"]["steps"][1].update(run="exit 0"),
                         lambda w: w["jobs"]["prerequisites"]["steps"][1].update({"if": "false"})):
            changed = copy.deepcopy(self.workflow)
            mutation(changed)
            self.assertIn("validation_deny_guard_changed", self.assess(workflow=changed))
        self.assertIn("validation_policy_not_fail_closed", self.assess(policy=dict(self.policy, enabled=True)))
        self.permissions["default_workflow_permissions"] = "write"
        self.assertIn("validation_excessive_permissions", self.assess())
