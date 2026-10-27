# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fcst_tools.profiles import HOST_CASES, BUILD_STAGES, assess_dependencies, assess_host, validate_locks

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from profile_support import verified_download
from project_files import markdown_files


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.host = json.loads((ROOT / "ci/host-profile.json").read_text(encoding="utf-8"))
        self.sources = json.loads((ROOT / "ci/probe-sources.json").read_text(encoding="utf-8"))["sources"]

    def test_pins_require_immutable_sources_and_license_hashes(self):
        self.assertEqual(validate_locks(self.host, self.sources), [])
        damaged = copy.deepcopy(self.sources)
        damaged[0]["revision"] = "main"
        damaged[1]["license_sha256"] = ""
        self.assertIn("unfrozen_source", validate_locks(self.host, damaged))
        self.assertIn("unfrozen_license", validate_locks(self.host, damaged))

    def test_host_rejects_missing_cases_wrong_abi_and_substituted_binary(self):
        report = {"status": "passed", "scope": "foundation_host_smoke", "freecad_version": ["1", "1", "4"],
                  "python_abi": "cp311", "asset_sha256": self.host["platforms"]["Windows"]["sha256"],
                  "cases": sorted(HOST_CASES), "solver_available": False, "gui_qualified": False}
        self.assertTrue(assess_host(report, self.host, "Windows"))
        for key, value in [("cases", ["create_geometry"]), ("python_abi", "cp312"),
                           ("asset_sha256", "0" * 64), ("gui_qualified", True)]:
            damaged = dict(report, **{key: value})
            self.assertFalse(assess_host(damaged, self.host, "Windows"))

    def test_dependency_missing_install_substituted_source_and_skips_rejected(self):
        records = [{"id": s["id"], "version": s["version"], "source_sha256": s["sha256"],
                    "license_sha256": s["license_sha256"], "adopted": False, "status": "passed",
                    "stages": sorted(BUILD_STAGES), "installed_bytes": 100} for s in self.sources]
        report = {"platform": "Linux", "candidates": records}
        self.assertTrue(assess_dependencies(report, self.sources, "Linux"))
        for mutation in [lambda r: r["candidates"].pop(),
                         lambda r: r["candidates"][0].update(status="skipped"),
                         lambda r: r["candidates"][0].update(source_sha256="0" * 64),
                         lambda r: r["candidates"][0]["stages"].remove("installed_consumer")]:
            damaged = copy.deepcopy(report)
            mutation(damaged)
            self.assertFalse(assess_dependencies(damaged, self.sources, "Linux"))
        records[-1].update(status="unsupported", reason_code="petsc_native_msvc_unsupported")
        report["platform"] = "Windows"
        self.assertTrue(assess_dependencies(report, self.sources, "Windows"))
        self.assertFalse(assess_dependencies(report, self.sources, "Linux"))

    def test_corrupt_cached_sources_never_execute_or_download(self):
        with tempfile.TemporaryDirectory() as directory, patch("profile_support.urlopen") as network:
            path = Path(directory) / "source.tar.gz"
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verified_download("https://github.com/example/release", path, 4, hashlib.sha256(b"safe").hexdigest())
            network.assert_not_called()
            for url in ("http://github.com/example", "https://untrusted.invalid/example"):
                with self.assertRaises(ValueError):
                    verified_download(url, path, 4, hashlib.sha256(b"safe").hexdigest())
            network.assert_not_called()

    def test_link_validation_excludes_ignored_originals_but_checks_project_docs(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
            (root / ".gitignore").write_text(".local/\n", encoding="utf-8")
            (root / ".local").mkdir()
            (root / ".local/original.md").write_bytes(b"\xff[private](unresolved)")
            (root / "tracked.md").write_text("[target](unresolved)", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.md", ".gitignore"], cwd=root, check=True, capture_output=True)
            (root / "new.md").write_text("[target](unresolved)", encoding="utf-8")
            self.assertEqual({p.name for p in markdown_files(root)}, {"tracked.md", "new.md"})
            (root / "tracked.md").unlink()
            self.assertEqual({p.name for p in markdown_files(root)}, {"new.md"})
