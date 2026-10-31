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
from fcst_tools.thermal_qualification import qualification,metrics_check,captured_reference,source_model
from hashlib import sha256
import tempfile


class ThermalEvidenceTests(unittest.TestCase):
    def test_missing_duplicate_failed_and_false_solver_claims_are_rejected(self):
        policy = json.loads((ROOT/'ci/thermal-acceptance.json').read_bytes())
        hashes = input_hashes(ROOT)
        cases = [{'id':c,'status':'passed'} for c in policy['required_cases']]
        register=json.loads((ROOT/'ci/thermal-qualification-v1.json').read_bytes())
        report = {'schema_version':5,'candidate':'synthetic','input_sha256':hashes,
                  'work_packages':IMPLEMENTED_SUBSTEPS,'solver_available':False,'steady_available':True,'transient_available':True,
                  'worker_build':{'engine':'fcst_native','solver_available':False,'steady_available':True,'transient_available':True,'source_revision':'synthetic'},
                  'binary_sha256':{key:'1'*64 for key in ('worker','preparation_acceptance','assembly_acceptance','steady_acceptance','transient_acceptance')},
                  'backend_capabilities':{'execution_mode':'fcst_native','external_reference':False,'durable_job_solver':False,'source_revision':'synthetic',
                                          'linear':'fcst_sparse_lu','nonlinear':'fcst_damped_newton','transient':'fcst_enthalpy_backward_euler_step_doubling',
                                          **{k:True for k in ('stiff','index_one_dae','enthalpy','events','checkpoint')}},
                  'native_profile':{**{k:1 for k in ('residual_evaluations','jacobian_evaluations','linear_solves','newton_iterations')},
                                    **{k:.01 for k in ('assembly_seconds','linear_seconds','total_seconds')}},
                  'gate':evaluate(policy['required_cases'],cases),'cases':cases}
        report['native_qualification']=qualification(register,cases)
        report['qualification_metrics']={
            'transient-event-refinement':{'coarse_error_s':.2,'medium_error_s':.1,'fine_error_s':.05,'fine_duty_error':.005,
                                          'coarse_steps':30,'medium_steps':55,'fine_steps':110},
            'transient-network-profile':{'equations':256,'nonzeros':766,'accepted_steps':6,'residual_evaluations':100,
                                         'jacobian_evaluations':50,'linear_solves':40,'assembly_seconds':.1,'linear_seconds':.1,
                                         'total_seconds':.3,'energy_defect_J':1e-10}}
        report['qualification_metrics']['transient-network-localized']=deepcopy(report['qualification_metrics']['transient-network-profile'])
        report['source_comparisons']={}
        for ecosystem in ('sinda','esatan'):
            name=f'tests/fixtures/thermal/source-{ecosystem}-network.json';definition=json.loads((ROOT/name).read_bytes())
            report['source_comparisons'][ecosystem]={'fixture_sha256':hashes[name],
                'source_sha256':sha256(definition['source_ascii'].encode('ascii')).hexdigest(),'model_hash':'1'*64,
                'maximum_temperature_error_K':.001,'maximum_boundary_power_error_W':.001,'maximum_storage_error_J':.002,
                'node_classes':3,'execution_mode':'fcst_native','vendor_qualified':False}
        self.assertTrue(assess(report,policy,hashes,'synthetic'))
        for change in ('missing','duplicate','failed','skipped','extra','solver','candidate','hash','scope','binary','stale-build','old-schema','steady','transient','reference-mode','capability-mode','profile','q1-claim','qualification-missing','event-refinement','network-size','source-hash','source-vendor','source-missing'):
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
            if change == 'q1-claim': value['native_qualification']['q1_qualified'] = True
            if change == 'qualification-missing': value['native_qualification']['requirements'].pop()
            if change == 'event-refinement': value['qualification_metrics']['transient-event-refinement']['fine_error_s']=.12
            if change == 'network-size': value['qualification_metrics']['transient-network-profile']['equations']=2
            if change == 'source-hash': value['source_comparisons']['sinda']['fixture_sha256']='0'*64
            if change == 'source-vendor': value['source_comparisons']['esatan']['vendor_qualified']=True
            if change == 'source-missing': del value['source_comparisons']['esatan']
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

    def test_captured_reference_binds_artifacts_modes_times_and_nodes_without_granting_qualification(self):
        definition=json.loads((ROOT/'tests/fixtures/thermal/source-sinda-network.json').read_bytes())
        model=source_model(definition);node_ids=[e['id'] for e in model['entities'] if e['kind']=='node']
        from fcst_tools.thermal_qualification import oracle_model
        criteria=json.loads((ROOT/'ci/thermal-qualification-v1.json').read_bytes());nodes=oracle_model(model,criteria['source_oracle'])
        printed=b'TIMEN = 0\nSUBMODEL NAME = MAIN\nT1=310 T2=305 T3=300\nTIMEN = 1\nSUBMODEL NAME = MAIN\nT1=308 T2=304 T3=300\n'
        values=[{nodes[1]:310,nodes[2]:305,nodes[3]:300},{nodes[1]:308,nodes[2]:304,nodes[3]:300}]
        expected={'status':'passed','valid':True,'backend':{'execution_mode':'fcst_native','external_reference':False},
                  'node_ids':node_ids,'samples':[{'time_s':t,'valid':True,'temperature_K':[row[i] for i in node_ids]} for t,row in zip((0,1),values)]}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            def artifact(name,raw):
                (root/name).write_bytes(raw);return {'path':name,'byte_length':len(raw),'sha256':sha256(raw).hexdigest()}
            source=artifact('network.inp',definition['source_ascii'].encode('ascii'));results=artifact('printed.txt',printed)
            receipt={'execution_mode':'reference_external','ecosystem':'sinda','source_version':'6.3',
                     'model_sha256':source['sha256'],'results_sha256':results['sha256'],
                     **{k:'1'*64 for k in ('executable_sha256','settings_sha256','run_id_sha256','review_decision_sha256')}}
            manifest={'version':'fcst-thermal-captured-reference/1','execution_mode':'reference_external','ecosystem':'sinda',
                      'source_version':'6.3','units':definition['units'],'model':source,'results':results,
                      'receipt':artifact('receipt.json',json.dumps(receipt).encode())}
            from fcst_contracts import loads
            result=captured_reference(loads(json.dumps(manifest)),root,lambda request:deepcopy(expected),criteria)
            self.assertEqual(result['status'],'passed');self.assertFalse(result['vendor_qualified']);self.assertFalse(result['q1_qualified'])
            for change in ('result-bytes','traversal','length','receipt-mode','native-mode','time','node','temperature','nan'):
                m=deepcopy(manifest);native=deepcopy(expected)
                (root/'printed.txt').write_bytes(printed)
                if change=='result-bytes':(root/'printed.txt').write_bytes(printed+b'changed')
                if change=='traversal':m['results']['path']='../printed.txt'
                if change=='length':m['results']['byte_length']+=1
                if change=='receipt-mode':
                    wrong=deepcopy(receipt);wrong['execution_mode']='fcst_native';m['receipt']=artifact('wrong.json',json.dumps(wrong).encode())
                if change=='native-mode':native['backend']['execution_mode']='reference_external'
                if change=='time':native['samples'].pop()
                if change=='node':native['node_ids'].pop()
                if change=='temperature':native['samples'][-1]['temperature_K'][0]+=1
                if change=='nan':native['samples'][-1]['temperature_K'][0]=float('nan')
                with self.subTest(change=change),self.assertRaises(ValueError):
                    captured_reference(m,root,lambda request:native,criteria)

    def test_native_requirement_coverage_fails_on_missing_duplicate_or_failed_cases(self):
        register=json.loads((ROOT/'ci/thermal-qualification-v1.json').read_bytes())
        cases=[{'id':c,'status':'passed'} for c in json.loads((ROOT/'ci/thermal-acceptance.json').read_bytes())['required_cases']]
        receipt=qualification(register,cases)
        self.assertEqual(receipt['native_status'],'passed');self.assertEqual(receipt['licensed_paired_status'],'blocked')
        self.assertFalse(receipt['q1_qualified'])
        for change in ('missing','duplicate','failed'):
            changed=deepcopy(cases);index=next(i for i,c in enumerate(changed) if c['id']=='transient-event-refinement')
            if change=='missing':changed.pop(index)
            if change=='duplicate':changed.append(changed[index])
            if change=='failed':changed[index]['status']='failed'
            self.assertEqual(qualification(register,changed)['native_status'],'failed')
