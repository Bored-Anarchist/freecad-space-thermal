# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned thermal preparation acceptance identity, separate from solver qualification."""
from hashlib import sha256
from .gate import evaluate

IMPLEMENTED_SUBSTEPS = [f'WP-11.{n}' for n in range(1,7)]


def input_hashes(root):
    names = ['CMakeLists.txt', 'CMakePresets.json', 'engine/src/contracts.cpp',
             'engine/worker/main.cpp', 'engine/include/fcst/contract_bundle.hpp',
             'tools/generate_contracts.py', 'tools/thermal_schema.py', 'tools/check_thermal.py',
             'python/fcst_tools/thermal.py', 'ci/thermal-acceptance.json',
             'spec/schemas/thermal-input-v1.schema.json']
    for folder in ('engine/include/fcst', 'engine/src', 'engine/tests', 'tests/fixtures/thermal'):
        names += [p.relative_to(root).as_posix() for p in (root/folder).glob('*')
                  if p.is_file() and p.suffix in {'.cpp','.hpp','.inc','.in','.json'}]
    return {name: sha256((root/name).read_bytes()).hexdigest() for name in sorted(set(names))}


def assess(report, policy, hashes, candidate):
    binaries = report.get('binary_sha256', {})
    build = report.get('worker_build', {})
    if (report.get('schema_version') != 3 or report.get('candidate') != candidate
            or report.get('input_sha256') != hashes or report.get('solver_available') is not False
            or report.get('steady_available') is not True
            or report.get('work_packages') != IMPLEMENTED_SUBSTEPS or policy.get('work_packages') != IMPLEMENTED_SUBSTEPS
            or set(binaries) != {'worker','preparation_acceptance','assembly_acceptance','steady_acceptance'}
            or any(not isinstance(v,str) or len(v)!=64 or set(v)-set('0123456789abcdef') for v in binaries.values())
            or build.get('engine') != 'fcst_native' or build.get('solver_available') is not False
            or build.get('steady_available') is not True
            or build.get('source_revision') != candidate
            or report.get('gate', {}).get('status') != 'passed'
            or evaluate(policy['required_cases'], report.get('cases', []))['status'] != 'passed'):
        raise ValueError('thermal_engine_evidence_invalid')
    return True
