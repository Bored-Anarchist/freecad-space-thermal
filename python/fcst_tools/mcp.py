# SPDX-License-Identifier: MIT OR Apache-2.0
"""Dependency-free candidate-bound MCP receipt verification for the CI aggregate."""
from hashlib import sha256
import json
from pathlib import Path
from .gate import evaluate

ROOT=Path(__file__).resolve().parents[2]


def input_hashes():
    paths=[*(ROOT/'python/fcst_mcp').glob('*.py'),ROOT/'tools/check_mcp.py',ROOT/'tests/test_mcp.py',
        ROOT/'python/fcst_tools/mcp.py',ROOT/'python/fcst_app/jobs.py',ROOT/'python/fcst_host/review.py',
        ROOT/'engine/src/contracts.cpp',ROOT/'engine/src/thermal_execution.inc',
        ROOT/'ci/mcp-acceptance.json',ROOT/'ci/mcp-requirements.lock',ROOT/'spec/mcp/2026-07-28.schema.json',ROOT/'spec/mcp/LICENSE']
    return {p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def assess(report,candidate,worker_sha256):
    policy=json.loads((ROOT/'ci/mcp-acceptance.json').read_bytes())
    if (report.get('candidate')!=candidate or report.get('input_sha256')!=input_hashes()
            or report.get('native_worker_sha256')!=worker_sha256 or report.get('gate',{}).get('status')!='passed'
            or report.get('protocols')!=policy['protocols'] or report.get('sdk')!=policy['sdk']
            or evaluate(policy['required_cases'],report.get('cases',[]))['status']!='passed'):
        raise ValueError('mcp_acceptance_stale_or_incomplete')
