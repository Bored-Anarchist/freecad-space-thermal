# SPDX-License-Identifier: MIT OR Apache-2.0
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fcst_exchange import ExchangeError, Limits
from fcst_exchange.tools import Tool, ToolRunner, Authorization

FIXTURE = Path(__file__).parent/"fixtures/exchange_converter.py"


class ExchangeToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = Path(sys.executable).resolve()
        self.auth = Authorization("synthetic/1","convert","synthetic-reviewed-decision")

    def runner(self, scenario="success", **kwargs):
        return ToolRunner([Tool("synthetic/1",self.exe,sha256(self.exe.read_bytes()).hexdigest(),
                                (str(FIXTURE.resolve()),scenario),
                                ((FIXTURE.resolve(),sha256(FIXTURE.read_bytes()).hexdigest()),),**kwargs)])

    def run_tool(self, runner, name="work", auth=None):
        return runner.run("synthetic/1",self.root/name,{"input.txt":b"synthetic input"},["result.txt"],self.auth if auth is None else auth)

    def test_tool_registration_hashes_and_authorization_fail_before_mutation(self):
        runner = self.runner()
        for auth in ("imported approval",Authorization("other","convert","x"),Authorization("synthetic/1","read","x")):
            with self.assertRaisesRegex(ExchangeError,"tool_authorization"):
                self.run_tool(runner,auth=auth)
        self.assertFalse((self.root/"work").exists())
        with self.assertRaisesRegex(ExchangeError,"tool_unregistered"): runner.probe("unknown")
        broken = ToolRunner([Tool("synthetic/1",self.exe,"0"*64,())])
        with self.assertRaisesRegex(ExchangeError,"tool_hash"): self.run_tool(broken)
        self.assertFalse((self.root/"work").exists())
        with self.assertRaisesRegex(ExchangeError,"duplicate_tool"):
            ToolRunner([runner.tools["synthetic/1"]]*2)

    def test_real_converter_is_bounded_and_records_tool_and_authorization_provenance(self):
        if os.name != "nt":
            # Platform policy is tested, never silently skipped by the suite.
            with self.assertRaisesRegex(ExchangeError,"unsupported_tool_platform"): self.run_tool(self.runner())
            return
        with patch.dict(os.environ,{"SECRET_TEST_VALUE":"withheld"}):
            files, report = self.run_tool(self.runner())
        self.assertEqual(files,{"result.txt":b"SYNTHETIC INPUT"})
        self.assertEqual(report["status"],"bridged-executable")
        self.assertEqual(report["authorization_sha256"],sha256(self.auth.decision_id.encode()).hexdigest())
        self.assertNotIn(str(self.exe),str(report))
        self.assertNotIn("synthetic-reviewed-decision",str(report))

    def test_real_timeout_log_disk_and_descendant_limits_terminate_tree(self):
        if os.name != "nt":
            with self.assertRaisesRegex(ExchangeError,"unsupported_tool_platform"): self.run_tool(self.runner())
            return
        for scenario,code in (("timeout","tool_timeout"),("flood","tool_log_limit"),("disk","tool_output_limit"),("child","tool_timeout")):
            with self.assertRaisesRegex(ExchangeError,code):
                self.run_tool(self.runner(scenario,timeout_seconds=.8,output_bytes=8192),name=scenario)
        time.sleep(2.2)
        self.assertFalse((self.root/"child/escaped.txt").exists())

    def test_undeclared_outputs_and_modified_inputs_never_become_results(self):
        if os.name != "nt":
            with self.assertRaisesRegex(ExchangeError,"unsupported_tool_platform"): self.run_tool(self.runner())
            return
        for scenario,code in (("undeclared","undeclared_tool_output"),("mutate","tool_modified_input")):
            with self.assertRaisesRegex(ExchangeError,code): self.run_tool(self.runner(scenario),name=scenario)
