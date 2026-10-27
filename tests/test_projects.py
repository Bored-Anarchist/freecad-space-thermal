# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_github import assess_project


class ProjectEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.config = {"repository": "sample/project", "projects_title": "Sample implementation", "work_package_count": 21}
        self.project = {"project_id": "synthetic-project", "url": "https://github.com/users/sample/projects/1",
                        "items": [{"issue": f"https://github.com/sample/project/issues/{i}", "state": "Planned"} for i in range(1, 22)]}
        self.snapshot = {"id": "synthetic-project", "title": "Sample implementation", "url": self.project["url"],
                         "closed": False, "public": True, "repositories": {"nodes": [{"nameWithOwner": "sample/project"}]},
                         "fields": {"nodes": [{"name": "Status", "options": [{"name": value} for value in
                                                 ["Planned", "Ready", "In progress", "Blocked", "Complete"]]}]},
                         "items": {"nodes": [{"content": {"url": item["issue"]}, "fieldValues": {"nodes": [
                             {"name": "Planned", "field": {"name": "Status"}}]}} for item in self.project["items"]]}}

    def test_local_link_cannot_replace_remote_evidence(self):
        self.assertIn("project_evidence_unavailable", assess_project(self.config, self.project, None))
        self.assertEqual(assess_project(self.config, self.project, self.snapshot), [])

    def test_missing_item_and_falsely_completed_state_rejected(self):
        missing = copy.deepcopy(self.snapshot)
        missing["items"]["nodes"].pop()
        self.assertIn("project_backlog_or_states_mismatch", assess_project(self.config, self.project, missing))
        stale = copy.deepcopy(self.snapshot)
        stale["items"]["nodes"][0]["fieldValues"]["nodes"][0]["name"] = "Complete"
        self.assertIn("project_backlog_or_states_mismatch", assess_project(self.config, self.project, stale))

    def test_wrong_repository_and_missing_delivery_states_rejected(self):
        wrong = copy.deepcopy(self.snapshot)
        wrong["repositories"]["nodes"] = []
        wrong["fields"]["nodes"][0]["options"].pop()
        findings = assess_project(self.config, self.project, wrong)
        self.assertIn("project_not_linked_to_repository", findings)
        self.assertIn("project_delivery_states_incomplete", findings)
