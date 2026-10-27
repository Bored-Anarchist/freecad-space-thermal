# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fcst_tools.inventory import ROOT, include_references, load_inventory, rows, static_observations, validate_inventory, verify_local
from fcst_tools.privacy import POLICY_PATH, Scanner
sys.path.insert(0, str(ROOT / "tools"))
from acquire_corpus import acquire, safe_target


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.data = load_inventory()
        self.profiles = {row["profile_id"] for row in rows(ROOT / "spec/compatibility-profiles.csv")}
        self.requirements = {row["id"] for row in rows(ROOT / "spec/requirements.csv")}
        self.packages = {row["id"] for row in rows(ROOT / "plans/work-packages.csv")}

    def errors(self, data):
        return validate_inventory(data, self.profiles, self.requirements, self.packages)

    def test_all_profiles_and_features_have_dispositions(self):
        self.assertEqual(self.errors(self.data), [])
        damaged = copy.deepcopy(self.data)
        damaged["coverage"].pop()
        self.assertIn("profile_inventory_incomplete", self.errors(damaged))
        damaged = copy.deepcopy(self.data)
        damaged["features"][0]["work_package"] = "WP-99"
        self.assertIn("unassigned_feature", self.errors(damaged))

    def test_unpinned_or_missing_file_provenance_rejected(self):
        damaged = copy.deepcopy(self.data)
        damaged["catalog"]["sources"][0]["revision"] = "main"
        self.assertIn("unfrozen_source_revision", self.errors(damaged))
        damaged = copy.deepcopy(self.data)
        damaged["lock"]["files"].pop()
        self.assertIn("missing_or_duplicate_file_provenance", self.errors(damaged))

    def test_unknown_version_requires_explicit_blocker(self):
        damaged = copy.deepcopy(self.data)
        unknown = next(model for model in damaged["models"]["models"] if model["source_version"]["status"] == "unknown")
        unknown["blockers"] = []
        self.assertIn("unknown_version_without_blocker", self.errors(damaged))

    def test_missing_dependency_target_or_removed_reference_rejected(self):
        damaged = copy.deepcopy(self.data)
        file = next(row for row in damaged["lock"]["files"] if row["static_dependencies"])
        file["static_dependencies"][0]["target_path"] = "missing.inc"
        self.assertIn("dependency_target_missing", self.errors(damaged))
        file["static_dependencies"].pop()
        self.assertIn("dependency_reference_omitted", self.errors(damaged))

    def test_syntax_and_retained_originals_cannot_claim_qualification(self):
        damaged = copy.deepcopy(self.data)
        syntax = next(model for model in damaged["models"]["models"] if model["purpose"] == "syntax_only")
        syntax["reference_results"]["physical_oracle"] = True
        syntax["qualification"] = "qualified"
        damaged["lock"]["files"][0]["publication"] = "publish"
        errors = self.errors(damaged)
        self.assertIn("syntax_fixture_used_as_physics_oracle", errors)
        self.assertIn("unsupported_qualification_claim", errors)
        self.assertIn("uncleared_original_publication", errors)

    def test_operation_or_dependency_disposition_cannot_be_omitted(self):
        damaged = copy.deepcopy(self.data)
        damaged["models"]["models"][0]["required_operations"].pop()
        damaged["models"]["models"][0]["dependency_review"] = {}
        self.assertIn("operation_coverage_missing", self.errors(damaged))
        self.assertIn("missing_dependency_or_reference_disposition", self.errors(damaged))

    def test_imported_logic_is_inspected_without_execution(self):
        payload = b'$MODEL SYNTHETIC\n$NODES\n D1 = 1;\n B2 = 0;\n$SUBROUTINES\n CALL UNTRUSTED_ROUTINE\n'
        with patch("subprocess.run", side_effect=AssertionError("Imported code must stay inert")):
            result = static_observations("steady_deck", payload)
        self.assertFalse(result["can_execute"])
        self.assertTrue(result["logic_retained_inert"])
        self.assertEqual(result["node_declaration_counts"], {"D": 1, "B": 1, "A": 0})
        self.assertEqual(include_references('INSERT "part one.cc"\nINSERT part2.k\n'), ["part one.cc", "part2.k"])

    def test_acquisition_paths_cannot_escape_store(self):
        for value in ["../outside.txt", "/absolute.txt", "C:/outside.txt", "x\\outside.txt"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                safe_target(ROOT / ".local/corpus", "TEST-SOURCE", value)

    def test_missing_and_tampered_originals_fail_without_echoing_paths(self):
        scratch = ROOT / ".local/test-scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = Path(temporary)
            data = {"lock": {"files": [{"source_id": "SYNTHETIC", "path": "model.txt", "bytes": 4,
                                       "sha256": hashlib.sha256(b"safe").hexdigest()}]}}
            self.assertEqual(verify_local(data, root)[0]["category"], "missing_or_unsafe_original")
            folder = root / "SYNTHETIC"
            folder.mkdir()
            (folder / "model.txt").write_bytes(b"evil")
            findings = verify_local(data, root)
            self.assertEqual(findings[0]["category"], "original_hash_mismatch")
            self.assertNotIn(str(root), json.dumps(findings))

    def test_acquisition_never_overwrites_different_original_bytes(self):
        scratch = ROOT / ".local/test-scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = Path(temporary)
            target = safe_target(root, "SYNTHETIC", "data.txt")
            target.parent.mkdir()
            target.write_bytes(b"original")
            catalog = {"sources": [{"id": "SYNTHETIC", "repository": "sample/repo", "revision": "a" * 40,
                                     "files": [{"path": "data.txt", "role": "synthetic"}]}]}
            from unittest.mock import MagicMock
            response = MagicMock()
            response.__enter__.return_value = response
            response.geturl.return_value = "https://raw.githubusercontent.com/sample/repo/" + "a" * 40 + "/data.txt"
            response.read.return_value = b"changed"
            with patch("acquire_corpus.urlopen", return_value=response), self.assertRaises(ValueError):
                acquire(catalog, root)
            self.assertEqual(target.read_bytes(), b"original")

    def test_missing_vendor_licenses_and_schema_block_qualification(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/check_inventory.py"), "--qualify"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("GAP-LICENSES", {gap["id"] for gap in report["blockers"]})
        self.assertIn("GAP-STEP", {gap["id"] for gap in report["blockers"]})

    def test_public_metadata_and_analytic_seed_are_privacy_cleared(self):
        scanner = Scanner(json.loads(POLICY_PATH.read_text()))
        for path in sorted((ROOT / "inventory").glob("*")):
            if path.is_file():
                scanner.scan(path.name, path.read_bytes())
        seed = ROOT / "tests/fixtures/public/two-node-analytic.json"
        scanner.scan(seed.name, seed.read_bytes())
        self.assertEqual(scanner.report()["status"], "passed")

    def test_independent_seed_oracle_conserves_energy(self):
        case = json.loads((ROOT / "tests/fixtures/public/two-node-analytic.json").read_text())
        capacity, conductance, boundary, initial, power = (case[key] for key in
            ["capacity_J_per_K", "conductance_W_per_K", "boundary_K", "initial_K", "power_W"])
        steady = boundary + power / conductance
        self.assertEqual(steady, case["steady_reference_K"])
        self.assertEqual(capacity / conductance, case["time_constant_s"])
        for time in case["reference_times_s"]:
            deviation = (initial - steady) * math.exp(-conductance * time / capacity)
            temperature = steady + deviation
            derivative = -conductance * deviation / capacity
            self.assertAlmostEqual(capacity * derivative, power - conductance * (temperature - boundary), places=12)
