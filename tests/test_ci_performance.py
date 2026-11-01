# SPDX-License-Identifier: MIT OR Apache-2.0
"""CI acceleration cannot bypass coverage, candidate identity or cache privacy."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "python"), str(ROOT / "tools")]
from fcst_tools.gate import evaluate
from fcst_tools.verification import check_unit_report, check_native_inventory, schedule
import cache_downloads
import check_workflows

SCRATCH = ROOT / ".local/test-scratch"
SCRATCH.mkdir(parents=True, exist_ok=True)


class CiPerformanceTests(unittest.TestCase):
    def test_unit_receipts_reject_stale_inputs_candidates_and_incomplete_results(self):
        expected = ["synthetic.one", "synthetic.two"]
        records = [dict(id=case, status="passed") for case in expected]
        receipt = dict(scope="unit-tests", candidate="a"*40, input_sha256={"source.py": "1"*64},
                       coverage_manifest_sha256="2"*64, cases=records, gate=evaluate(expected, records))
        def check(value):
            return check_unit_report(value, "a"*40, {"source.py": "1"*64}, "2"*64, expected)
        self.assertEqual(check(receipt), records)
        for change in ("candidate", "source", "manifest", "missing", "duplicate", "failed", "gate", "scope"):
            value = deepcopy(receipt)
            if change == "candidate": value["candidate"] = "b"*40
            if change == "source": value["input_sha256"]["source.py"] = "3"*64
            if change == "manifest": value["coverage_manifest_sha256"] = "4"*64
            if change == "missing": value["cases"].pop()
            if change == "duplicate": value["cases"].append(deepcopy(value["cases"][0]))
            if change == "failed": value["cases"][0]["status"] = "failed"
            if change == "gate": value["gate"]["status"] = "failed"
            if change == "scope": value["scope"] = "security-tests"
            with self.subTest(change=change), self.assertRaises(ValueError): check(value)

    def test_scheduler_bounds_concurrency_and_serializes_reference_builds(self):
        barrier = threading.Barrier(2, timeout=10)
        guard = threading.Lock()
        active = set()
        observed = []
        stages = ["thermal-reference-comparison", "numerical-checkpoint", "radiation-acceptance"]
        def execute(stage):
            with guard:
                active.add(stage)
                observed.append(set(active))
            if stage != "numerical-checkpoint": barrier.wait()
            with guard: active.remove(stage)
            return {"status": "failed" if stage == "radiation-acceptance" else "passed"}
        results = dict(schedule(stages, execute, 2))
        self.assertEqual(set(results), set(stages))
        self.assertEqual(results["radiation-acceptance"]["status"], "failed")
        self.assertEqual(max(map(len, observed)), 2)
        self.assertFalse(any({"thermal-reference-comparison", "numerical-checkpoint"} <= s for s in observed))
        for stages, jobs in ((["duplicate", "duplicate"], 2), (["one"], 0), (["one"], 5)):
            with self.assertRaises(ValueError): list(schedule(stages, execute, jobs))

    def test_native_deduplication_rejects_new_cases_and_changed_commands(self):
        root = Path("synthetic-checkout").absolute()
        build = root / "out/Debug"
        fixture = root / "tests/fixtures/thermal"
        inventory = {"tests": [
            dict(name="native-build-info", command=[str(build / "fcst-worker.exe"), "--build-info"]),
            dict(name="native-self-test", command=[str(build / "fcst-worker.exe"), "--self-test"]),
            dict(name="thermal-constant-law", command=[str(build / "fcst-thermal-tests.exe"), "constant-law", str(fixture / "material-network.json")]),
            dict(name="radiation-intersections", command=[str(build / "fcst-radiation-tests.exe"), "intersections", str(fixture)]),
        ]}
        def check(value):
            return check_native_inventory(value, {"required_cases": ["native-constant-law"]},
                                          {"native_cases": ["intersections"]}, build, root)
        self.assertTrue(check(inventory))
        for change in ("extra", "missing", "duplicate", "command", "case-sensitive-argument"):
            value = deepcopy(inventory)
            if change == "extra": value["tests"].append(dict(name="new-regression", command=["new"]))
            if change == "missing": value["tests"].pop()
            if change == "duplicate": value["tests"][-1] = deepcopy(value["tests"][0])
            if change == "command": value["tests"][-1]["command"][1] = "different-case"
            if change == "case-sensitive-argument": value["tests"][-1]["command"][1] = "INTERSECTIONS"
            with self.subTest(change=change), self.assertRaises(ValueError): check(value)

    def cache_fixture(self, root):
        raw = b"synthetic public upstream distribution"
        value = hashlib.sha256(raw).hexdigest()
        lock = root / "requirements.lock"
        lock.write_text("synthetic==1.0 \\\n    --hash=sha256:" + value + "\n", encoding="utf-8")
        cache = root / "cache"
        (cache / "wheels").mkdir(parents=True)
        (cache / "wheels/synthetic-1.0-py3-none-any.whl").write_bytes(raw)
        source = root / "source.zip"
        source.write_bytes(raw)
        return cache, [lock], [(source, value, len(raw))]

    def test_cache_seals_only_exact_upstream_bytes_and_restores_them(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            cache, locks, archives = self.cache_fixture(Path(directory))
            cache_downloads.seal(cache, locks, archives)
            source, value, size = archives[0]
            source.unlink()
            cache_downloads.validate(cache, locks, archives)
            cache_downloads.restore(cache, archives)
            self.assertEqual(cache_downloads.digest(source), value)
            self.assertEqual(source.stat().st_size, size)
            source.write_bytes(b"locally modified")
            with self.assertRaises(ValueError): cache_downloads.seal(cache, locks, archives)

    def test_cache_rejects_tampered_wheels_unlisted_files_and_objects(self):
        for change in ("wheel-bytes", "wheel-pin", "log", "nested", "object", "object-size", "hard-link"):
            with self.subTest(change=change), tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
                cache, locks, archives = self.cache_fixture(Path(directory))
                cache_downloads.seal(cache, locks, archives)
                wheel = cache / "wheels/synthetic-1.0-py3-none-any.whl"
                if change == "wheel-bytes": wheel.write_bytes(b"locally generated")
                if change == "wheel-pin":
                    wheel.with_name("different-1.0-py3-none-any.whl").write_bytes(wheel.read_bytes())
                    wheel.unlink()
                if change == "log": (cache / "raw.log").write_text("local compiler output")
                if change == "nested": (cache / "wheels/build").mkdir()
                if change == "object": (cache / "objects" / archives[0][1]).write_bytes(b"changed")
                if change == "object-size": archives = [(archives[0][0], archives[0][1], 1)]
                if change == "hard-link": os.link(wheel, Path(directory) / "outside.whl")
                with self.assertRaises(ValueError): cache_downloads.validate(cache, locks, archives)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            cache = Path(directory) / "cache"
            cache.write_bytes(b"unexpected root file")
            with self.assertRaises(ValueError):
                cache_downloads.validate(cache, [ROOT / "ci/requirements.lock"], [])

    def test_workflow_cache_uploads_require_exact_path_and_immediate_clearance(self):
        check_workflows.validate()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as directory:
            root = Path(directory)
            (root / ".github/workflows").mkdir(parents=True)
            for source in (ROOT / ".github/workflows").glob("*.yml"):
                (root / ".github/workflows" / source.name).write_bytes(source.read_bytes())
            path = root / ".github/workflows/ci.yml"
            original = path.read_text()
            for replacement in (original.replace("path: .local/public-download-cache", "path: .local"),
                                original.replace("cache_downloads.py seal", "cache_downloads.py prepare"),
                                original.replace("steps.cache-clear.outcome == 'success'", "true")):
                path.write_text(replacement, encoding="utf-8")
                with patch.object(check_workflows, "ROOT", root), self.assertRaises(AssertionError):
                    check_workflows.validate()
