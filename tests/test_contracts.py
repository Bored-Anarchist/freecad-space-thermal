# SPDX-License-Identifier: MIT OR Apache-2.0
import copy
from hashlib import sha256
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

from fcst_contracts import (BUNDLE, ContractError, canonical, frame, inspect, loads, read,
                            snapshot, unframe, verify_artifact)
from fcst_contracts.worker import Transcript

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/contracts"


def fixture(name):
    return json.loads((FIXTURES / (name + ".json")).read_text())


class ContractTests(unittest.TestCase):
    def test_generated_bundle_and_native_table_cannot_drift(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/generate_contracts.py"), "--check"],
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0)

    def test_frozen_positive_and_negative_vectors(self):
        sys.path.insert(0, str(ROOT / "tools"))
        from check_contracts import check
        records = check()
        self.assertGreaterEqual(len(records), 63)
        self.assertTrue(all(r["status"] == "passed" for r in records))

    def test_independent_standard_schema_reader(self):
        from jsonschema import Draft202012Validator
        for schema in BUNDLE["schemas"].values():
            Draft202012Validator.check_schema(schema)
        for case in fixture("cases")["cases"]:
            if case["status"] == "passed":
                Draft202012Validator(BUNDLE["schemas"][case["kind"]]).validate(fixture(case["id"]))

    def test_hash_preserves_identity_topology_ordered_arrays_and_exact_artifacts(self):
        base = fixture("all-entities")
        original = canonical(snapshot(base))
        for mutate in [lambda m: m["entities"][2].update(label="changed"),
                       lambda m: m["entities"][15]["ast"]["args"].reverse(),
                       lambda m: m["entities"][6]["artifact"].update(sha256="f" * 64)]:
            changed = copy.deepcopy(base)
            mutate(changed)
            self.assertNotEqual(canonical(snapshot(changed)), original)
        self.assertEqual(canonical(-0.0), canonical(0))
        self.assertEqual(canonical(1.0), canonical(1))
        self.assertNotEqual(canonical(True), canonical(1))
        self.assertNotEqual(sha256(b"{}").digest(), sha256(b"{ }").digest())

    def test_quantities_diagnostics_and_source_context(self):
        value = read("model", fixture("all-entities"))
        self.assertEqual(value["entities"][2]["temperature"], {"unit": "K", "value": 293.15})
        self.assertEqual(value["entities"][5]["origin"][0]["value"], .0254)
        with self.assertRaises(ContractError) as caught:
            read("model", fixture("dimension-mismatch"))
        self.assertEqual(caught.exception.diagnostic.entity_id, value["entities"][2]["id"])
        self.assertEqual(caught.exception.diagnostic.source_map_id, value["source_maps"][0]["id"])
        # The conversion of absolute Fahrenheit uses its declared affine transform.
        f = copy.deepcopy(fixture("network"))
        f["entities"][2]["temperature"] = {"value": 32, "unit": "degF"}
        self.assertAlmostEqual(read("model", f)["entities"][2]["temperature"]["value"], 273.15)

    def test_native_snapshot_retains_independent_analytic_seed(self):
        model = read("model", fixture("analytic-seed-native"))
        seed = json.loads((ROOT / "tests/fixtures/public/two-node-analytic.json").read_text())
        capacitive = next(e for e in model["entities"] if e["kind"] == "node" and e["classification"] == "capacitive")
        boundary = next(e for e in model["entities"] if e["kind"] == "node" and e["classification"] == "prescribed")
        conductor = next(e for e in model["entities"] if e["kind"] == "conductor")
        load = next(e for e in model["entities"] if e["kind"] == "load")
        self.assertEqual(capacitive["capacity"]["value"], seed["capacity_J_per_K"])
        self.assertEqual(capacitive["temperature"]["value"], seed["initial_K"])
        self.assertEqual(boundary["temperature"]["value"], seed["boundary_K"])
        self.assertEqual(conductor["conductance"]["value"], seed["conductance_W_per_K"])
        self.assertEqual(load["power"]["value"], seed["power_W"])
        self.assertEqual(model["source_maps"], [])

    def test_bounded_control_frames_and_no_trailing_bytes(self):
        message = fixture("worker-progress")
        encoded = frame(message)
        self.assertEqual(unframe(encoded), message)
        for raw in [b"", encoded[:3], encoded[:-1], encoded + b"x", struct.pack("<I", 65537), struct.pack("<I", 0)]:
            self.assertEqual(inspect("worker-frame", raw), {"status": "failed", "code": "invalid_json"})
        with self.assertRaises(ContractError):
            loads(b" " * 1048577)

    def test_transcript_cancel_terminal_checkpoint_and_replay(self):
        transcript = Transcript()
        for seq, name in enumerate(("handshake", "submit", "checkpoint", "progress", "cancel", "terminal")):
            message = fixture("worker-" + name)
            message["sequence"] = seq
            transcript.accept(message)
        self.assertEqual(transcript.state, "terminal")
        with self.assertRaises(ContractError):
            transcript.accept(message)
        with self.assertRaises(ContractError):
            Transcript().accept(fixture("worker-submit"))
        transcript = Transcript()
        transcript.accept(fixture("worker-handshake"))
        submit = fixture("worker-submit")
        submit["sequence"] = 2
        with self.assertRaises(ContractError):
            transcript.accept(submit)
        submit["sequence"] = 1
        transcript.accept(submit)
        checkpoint = fixture("worker-checkpoint")
        checkpoint["sequence"] = 2
        checkpoint["payload"]["snapshot_hash"] = "f" * 64
        with self.assertRaises(ContractError):
            transcript.accept(checkpoint)

    def test_exact_artifact_bytes_and_metadata_are_verified(self):
        raw = b"synthetic public array payload"
        reference = {"path": "arrays/test.h5", "byte_length": len(raw), "sha256": sha256(raw).hexdigest()}
        verify_artifact(reference, raw)
        for changed in [raw + b" ", b"x" * len(raw)]:
            with self.assertRaises(ContractError):
                verify_artifact(reference, changed)

    def test_versioned_operations_do_not_claim_runtime_execution(self):
        from fcst_app import capabilities
        self.assertFalse(capabilities()["solver_available"])
        self.assertEqual(set(BUNDLE["operations"]), {c["properties"]["operation"]["const"] for c in BUNDLE["schemas"]["operation"]["oneOf"]})
        self.assertEqual(set(BUNDLE["operations"]), {c["properties"]["operation"]["const"] for c in BUNDLE["schemas"]["response"]["oneOf"] if "operation" in c["properties"]})

    def test_json_parser_unicode_numbers_duplicates_and_depth(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":Infinity}', b'{"a":1e999}', b'{"a":1e-999}', b'{"a":"\xff"}', b'{"a":"\\ud800"}', b'[' * 66 + b']' * 66]:
            with self.assertRaises(ContractError):
                loads(raw)
        escaped_pair = chr(92) + "ud83d" + chr(92) + "ude80"
        self.assertEqual(loads('{"x":"' + escaped_pair + '"}')["x"], "\U0001f680")
