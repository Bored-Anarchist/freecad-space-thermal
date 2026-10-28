# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from fcst_tools.gate import evaluate
from fcst_tools.numerical import (assess_attempt, canonical, compare, digest, oracle,
                                  compare_restart, compare_steady, native_cache_root, steady_oracle, validate_policy, within)

ROOT = Path(__file__).resolve().parents[1]


class NumericalTests(unittest.TestCase):
    def setUp(self):
        self.criteria = json.loads((ROOT / "ci/numerical-criteria-v1.json").read_bytes())
        self.fixture = json.loads((ROOT / "tests/fixtures/numerical/checkpoint-v1.json").read_bytes())
        self.case = copy.deepcopy(self.fixture["cases"]["stiff-nonlinear-heater"])
        self.case["end_s"] = 2
        self.reference = oracle(self.case, .002)
        self.observation = {**copy.deepcopy(self.reference), "status":"completed", "jacobian_error":0}

    def test_independent_oracle_energy_events_and_steady_balance(self):
        errors, metrics = compare(self.case, self.observation, self.reference, self.criteria)
        self.assertEqual(errors, [])
        self.assertGreater(metrics["events"], 1)
        p = self.case["parameters"]
        t1, t2, a = steady_oracle(p)
        q = p[4]*(1+p[7]*(t1+a-2*p[9]))*(t1-a)
        self.assertAlmostEqual(q, p[10], places=10)
        self.assertAlmostEqual(p[5]*(a-t2), p[6]*(t2-p[9]), places=10)
        self.assertAlmostEqual(q, p[6]*(t2-p[9])+p[8]*(a**4-p[9]**4), places=10)

    def test_critical_node_and_energy_errors_cannot_hide_in_averages(self):
        broken = copy.deepcopy(self.observation)
        broken["samples"][2]["state"][1] += .01
        errors, _ = compare(self.case, broken, self.reference, self.criteria)
        self.assertIn("temperature_error", errors)
        self.assertIn("energy_balance", errors)

    def test_missing_events_samples_or_wrong_control_fail(self):
        broken = copy.deepcopy(self.observation)
        broken["events_s"].pop()
        self.assertIn("event_error", compare(self.case, broken, self.reference, self.criteria)[0])
        broken = copy.deepcopy(self.observation)
        broken["samples"].pop()
        self.assertIn("sample_coverage", compare(self.case, broken, self.reference, self.criteria)[0])
        broken = copy.deepcopy(self.observation)
        broken["samples"][0]["heater"] = False
        self.assertIn("sample_or_control_mismatch", compare(self.case, broken, self.reference, self.criteria)[0])

    def test_nonfinite_short_states_and_cancelled_results_fail(self):
        for state in ([300], [300, math.nan, 0], [300, 300, math.inf]):
            broken = copy.deepcopy(self.observation)
            broken["samples"][0]["state"] = state
            self.assertEqual(compare(self.case, broken, self.reference, self.criteria)[0], ["invalid_sample"])
        self.observation["status"] = "cancelled"
        self.assertEqual(compare(self.case, self.observation, self.reference, self.criteria)[0], ["execution_incomplete"])
        self.assertFalse(within(math.nan, 0, self.criteria["temperature_K"]))

    def test_required_cases_and_ensemble_cannot_be_silently_reduced(self):
        validate_policy(self.criteria, self.fixture)
        for change in ("coverage", "seed", "tolerance"):
            broken = copy.deepcopy(self.criteria)
            if change == "coverage":
                broken["required_cases"].pop()
            elif change == "seed":
                broken["statistical_policy"]["seeds"][0] = broken["statistical_policy"]["seeds"][1]
            else:
                broken["temperature_K"]["atol"] = math.inf
            with self.assertRaises(ValueError):
                validate_policy(broken, self.fixture)

    def seal(self, path, status="passed"):
        cases = [{"id": name, "status":status} for name in self.criteria["required_cases"]]
        assessment = {"cases": cases, "gate":evaluate(self.criteria["required_cases"], cases)}
        artifacts = {"criteria.json":self.criteria, "fixture.json":self.fixture,
                     "observations.json":self.observation, "assessment.json":assessment}
        for name, value in artifacts.items():
            (path / name).write_bytes(canonical(value))
        manifest = {"state":"completed", "artifacts": {name:digest((path/name).read_bytes()) for name in artifacts}}
        (path / "manifest.json").write_bytes(canonical(manifest))
        (path / "seal.json").write_bytes(canonical({"manifest_sha256":digest(canonical(manifest))}))

    def test_criteria_observations_and_manifest_tampering_invalidate_evidence(self):
        for name in ("criteria.json", "observations.json", "manifest.json", "assessment.json", "fixture.json"):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                self.seal(path)
                self.assertEqual(assess_attempt(path)["status"], "passed")
                (path/name).write_bytes((path/name).read_bytes()+b" ")
                with self.assertRaises(ValueError):
                    assess_attempt(path)

    def test_failed_attempt_is_preserved_when_new_criteria_are_assessed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            before, after = path/"before", path/"after"
            before.mkdir(); after.mkdir()
            self.seal(before, "failed")
            original = (before/"manifest.json").read_bytes()
            self.criteria["temperature_K"]["atol"] *= 2
            self.seal(after)
            self.assertEqual(assess_attempt(before)["status"], "failed")
            self.assertEqual(assess_attempt(after)["status"], "passed")
            self.assertEqual((before/"manifest.json").read_bytes(), original)
            self.assertNotEqual(json.loads((before/"manifest.json").read_bytes())["artifacts"]["criteria.json"],
                                json.loads((after/"manifest.json").read_bytes())["artifacts"]["criteria.json"])

    def test_missing_prerequisites_report_exact_ids(self):
        result = evaluate(["fixture-a", "runner-b"], [{"id":"fixture-a", "status":"blocked"}])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["missing"], ["runner-b"])

    def test_restart_rejects_truncation_wrong_time_controls_and_nonfinite_state(self):
        full = self.observation
        split = 1
        partial = {**copy.deepcopy(full), "status": "cancelled",
                   "samples": copy.deepcopy([r for r in full["samples"] if r["time_s"] <= split]),
                   "events_s": [t for t in full["events_s"] if t <= split]}
        resumed = {**copy.deepcopy(full), "samples": copy.deepcopy([r for r in full["samples"] if r["time_s"] >= split]),
                   "events_s": [t for t in full["events_s"] if t > split]}
        self.assertEqual(compare_restart(partial, resumed, full, split, self.criteria)[0], [])
        for mutation in ("short_rows", "short_state", "time", "heater", "nonfinite", "algebraic", "energy", "events", "status", "jacobian"):
            broken = copy.deepcopy(resumed)
            if mutation == "short_rows": broken["samples"].pop()
            elif mutation == "short_state": broken["samples"][0]["state"].pop()
            elif mutation == "time": broken["samples"][0]["time_s"] += .01
            elif mutation == "heater": broken["samples"][0]["heater"] = not broken["samples"][0]["heater"]
            elif mutation == "nonfinite": broken["samples"][0]["state"][0] = math.nan
            elif mutation == "algebraic": broken["samples"][0]["algebraic_K"] += .01
            elif mutation == "energy": broken["samples"][0]["state"][2] += .01
            elif mutation == "events": broken["events_s"].append(2)
            elif mutation == "jacobian": broken["jacobian_error"] = .1
            else: broken["status"] = "cancelled"
            with self.subTest(mutation=mutation):
                self.assertTrue(compare_restart(partial, broken, full, split, self.criteria)[0])
        partial["samples"].pop()
        self.assertTrue(compare_restart(partial, resumed, full, split, self.criteria)[0])

    def test_native_build_cache_is_short_stable_and_checkout_scoped(self):
        base = Path("synthetic-local-data")
        checkout = Path("synthetic-checkout") / ("long-folder/" * 12)
        cache = native_cache_root(checkout, base)
        self.assertEqual(cache.parent, base/"fcst-q0")
        self.assertEqual(cache, native_cache_root(checkout, base))
        self.assertNotEqual(cache, native_cache_root(checkout/"another", base))
        self.assertEqual(len(cache.name), 12)
        self.assertLess(len(str(cache)), len(str(checkout)))

    def test_steady_requires_finite_nonnegative_norm_and_independent_balance(self):
        reference = steady_oracle(self.case["parameters"])
        observed = {"status": "completed", "residual": 0, "samples": [{"time_s": 0,
                    "state": reference[:2] + [0], "algebraic_K": reference[2], "heater": True}]}
        self.assertTrue(compare_steady(self.case["parameters"], observed, reference, self.criteria))
        for residual in (-1, -math.inf, math.nan, True):
            with self.subTest(residual=residual):
                self.assertFalse(compare_steady(self.case["parameters"], {**observed, "residual": residual}, reference, self.criteria))
        broken = copy.deepcopy(observed)
        broken["samples"][0]["state"][0] += 1e-5  # Within temperature tolerance, outside heat-balance tolerance.
        self.assertFalse(compare_steady(self.case["parameters"], broken, reference, self.criteria))


if __name__ == "__main__":
    unittest.main()
