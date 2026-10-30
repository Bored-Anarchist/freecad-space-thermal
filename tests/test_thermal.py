# SPDX-License-Identifier: MIT OR Apache-2.0
"""Prevent missing, stale or inflated native preparation evidence passing CI."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'python'))
from fcst_tools.gate import evaluate
from fcst_tools.thermal import assess, input_hashes, IMPLEMENTED_SUBSTEPS


class ThermalEvidenceTests(unittest.TestCase):
    def test_missing_duplicate_failed_and_false_solver_claims_are_rejected(self):
        policy = json.loads((ROOT/'ci/thermal-acceptance.json').read_bytes())
        hashes = input_hashes(ROOT)
        cases = [{'id':c,'status':'passed'} for c in policy['required_cases']]
        report = {'schema_version':4,'candidate':'synthetic','input_sha256':hashes,
                  'work_packages':IMPLEMENTED_SUBSTEPS,'solver_available':False,'steady_available':True,'transient_available':True,
                  'worker_build':{'engine':'fcst_native','solver_available':False,'steady_available':True,'transient_available':True,'source_revision':'synthetic'},
                  'binary_sha256':{key:'1'*64 for key in ('worker','preparation_acceptance','assembly_acceptance','steady_acceptance','transient_acceptance')},
                  'backend_capabilities':{'execution_mode':'fcst_native','external_reference':False,'durable_job_solver':False,'source_revision':'synthetic',
                                          'linear':'fcst_sparse_lu','nonlinear':'fcst_damped_newton','transient':'fcst_enthalpy_backward_euler_step_doubling',
                                          **{k:True for k in ('stiff','index_one_dae','enthalpy','events','checkpoint')}},
                  'native_profile':{**{k:1 for k in ('residual_evaluations','jacobian_evaluations','linear_solves','newton_iterations')},
                                    **{k:.01 for k in ('assembly_seconds','linear_seconds','total_seconds')}},
                  'gate':evaluate(policy['required_cases'],cases),'cases':cases}
        self.assertTrue(assess(report,policy,hashes,'synthetic'))
        for change in ('missing','duplicate','failed','skipped','extra','solver','candidate','hash','scope','binary','stale-build','old-schema','steady','transient','reference-mode','capability-mode','profile'):
            value = deepcopy(report)
            if change == 'missing': value['cases'].pop()
            if change == 'duplicate': value['cases'].append(deepcopy(value['cases'][0]))
            if change in ('failed','skipped'): value['cases'][0]['status'] = change
            if change == 'extra': value['cases'].append({'id':'unreviewed','status':'passed'})
            if change == 'solver': value['solver_available'] = True
            if change == 'candidate': value['candidate'] = 'stale'
            if change == 'hash': value['input_sha256']['engine/src/thermal.cpp'] = '0'*64
            if change == 'scope': value['work_packages'] = ['WP-11']
            if change == 'binary': del value['binary_sha256']['assembly_acceptance']
            if change == 'stale-build': value['worker_build']['source_revision'] = 'stale'
            if change == 'old-schema': value['schema_version'] = 1
            if change == 'steady': value['steady_available'] = False
            if change == 'transient': value['transient_available'] = False
            if change == 'reference-mode': value['worker_build']['engine'] = 'external_reference'
            if change == 'capability-mode': value['backend_capabilities']['external_reference'] = True
            if change == 'profile': value['native_profile']['linear_solves'] = 0
            with self.subTest(change=change), self.assertRaises(ValueError):
                assess(value,policy,hashes,'synthetic')

    def test_ci_requires_native_preparation_and_clears_exact_report(self):
        sys.path.insert(0,str(ROOT/'tools'))
        import verify
        self.assertIn('thermal-preparation',verify.STEPS)
        workflow = (ROOT/'.github/workflows/ci.yml').read_text()
        self.assertIn('--file .local/${{ matrix.preset }}/thermal.json',workflow)
        self.assertIn('            .local/${{ matrix.preset }}/thermal.json\n',workflow)
        handoff = (ROOT/'tools/check_foundation_handoff.py').read_text()
        self.assertIn("assess_thermal(load(path.parent/'thermal.json')",handoff)
