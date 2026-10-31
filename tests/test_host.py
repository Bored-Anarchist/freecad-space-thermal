# SPDX-License-Identifier: MIT OR Apache-2.0
"""Portable host contracts; real GUI acceptance is supervised separately."""
from copy import deepcopy
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
sys.path.insert(0,str(ROOT/'tools'))
from fcst_app.persistence import Package, PersistenceError, semantic_hash
from fcst_app.store import ProjectStore
from fcst_contracts import ContractError, normalize
from fcst_host import review
from check_host import assess


def synthetic(model):
    return dict(status='passed',valid=True,model_hash=semantic_hash(model),
        backend=dict(execution_mode='fcst_native',external_reference=False),
        node_ids=[review.uid(4),review.uid(5)],samples=[dict(time_s=t,temperature_K=[310-t,290+t],valid=True,
            conductive_in_W=[-4,4],duty_cycles={},run_energy=dict(defect_J=0)) for t in (0,1,2)])


class HostTests(unittest.TestCase):
    def test_host_import_is_independent_of_freecad_and_qt(self):
        import subprocess
        result=subprocess.run([sys.executable,'-c',"import sys;sys.path.insert(0,'python');import fcst_host,fcst_host.review;assert 'FreeCAD' not in sys.modules and 'PySide6' not in sys.modules"],cwd=ROOT,capture_output=True)
        self.assertEqual(result.returncode,0)

    def test_edits_use_shared_unit_validation_revision_and_inverse(self):
        with tempfile.TemporaryDirectory() as folder, ProjectStore.create(Path(folder)/'state.db',review.example_model()) as store:
            original=store.snapshot();node=deepcopy(original['entities'][1]);node['temperature']=dict(value=36.85,unit='degC')
            review.change(store,node,expected_revision=0)
            self.assertEqual(normalize(store.snapshot())['entities'][1]['temperature']['value'],310)
            with self.assertRaises(PersistenceError):review.change(store,node,expected_revision=0)
            store.apply('test',{'changes.undo'},original['project_id'],1,'undo',{'revision':1},operation='changes.undo')
            self.assertEqual(semantic_hash(store.snapshot()),semantic_hash(original))
            node['temperature']=dict(value=-1,unit='K')
            with self.assertRaises(ContractError):review.change(store,node,expected_revision=2)

    def test_solver_settings_reject_fractional_nonfinite_and_unbounded_samples(self):
        for key,value in (('mode','unsupported'),('samples',2.5),('samples',1002),('end',0),('start',-1),('absolute_temperature_tolerance',0),('relative_temperature_tolerance',-1),('end',float('nan')),('start',True)):
            bad={**review.DEFAULT_SETTINGS,key:value}
            with self.assertRaises(PersistenceError):review.settings(bad)
        with self.assertRaises(PersistenceError):review.settings({**review.DEFAULT_SETTINGS,'code':'inert'})

    def test_request_freezes_independent_model_and_sampling(self):
        model=review.example_model();flag,value=review.request(model,review.DEFAULT_SETTINGS)
        self.assertEqual(flag,'--thermal-transient');self.assertEqual(value['transient']['output_times'][::10],[0,1,2])
        model['entities'].clear();self.assertEqual(len(value['thermal_input']['model']['entities']),4)
        with self.assertRaises(PersistenceError):review.request(review.example_model(),review.DEFAULT_SETTINGS,review.uid(99))
        flag,value=review.request(review.example_model(),{**review.DEFAULT_SETTINGS,'mode':'steady'})
        self.assertEqual(flag,'--thermal-steady');self.assertEqual(value['model'],review.example_model())

    def test_reopen_configuration_is_closed_typed_and_cannot_rebind_unknown_entities(self):
        model=review.example_model()
        value=dict(sequence=0,options=review.DEFAULT_SETTINGS,case_id=None,bindings=[],spatial_id=None)
        self.assertEqual(review.configuration(value,model),value)
        for key,invalid in (('sequence','invalid'),('sequence',-1),('sequence',True),('sequence',float('inf')),
                            ('case_id',[]),('case_id',review.uid(4)),('bindings','inert'),('spatial_id','not-a-uuid')):
            with self.assertRaises(PersistenceError):review.configuration({**value,key:invalid},model)
        with self.assertRaises(PersistenceError):review.configuration({**value,'unknown':1},model)
        with self.assertRaises(PersistenceError):review.configuration({**value,'bindings':[dict(entity_id=review.uid(4),
            target_id=review.uid(5),subelement='Face1',source_revision='0'*64)]},model)

    def test_creation_templates_bind_existing_types_and_keep_distinct_conductor_ends(self):
        from fcst_host.workbench import template
        with tempfile.TemporaryDirectory() as folder, ProjectStore.create(Path(folder)/'state.db',review.new_model()) as store:
            for kind in ('submodel','node','node','conductor','material','optics','frame','environment','load','case'):
                entity=template(kind,store.snapshot())
                review.change(store,entity,expected_revision=store.snapshot()['revision'])
            entities=store.snapshot()['entities'];link=next(e for e in entities if e['kind']=='conductor')
            self.assertNotEqual(link['from_node_id'],link['to_node_id'])
            self.assertEqual(len({e['id'] for e in entities}),len(entities))

    def test_input_artifacts_are_immutable_validated_and_revision_bound(self):
        with tempfile.TemporaryDirectory() as folder, ProjectStore.create(Path(folder)/'state.db',review.new_model()) as store:
            identifier=review.uid(100)
            store.add_artifact(identifier,'evidence','review/input.json',b'{}',expected_revision=0)
            self.assertEqual(store.export_package().files['review/input.json'],b'{}')
            for path,revision in (('../escape.json',0),('review/other.json',1),('review/input.json',0)):
                with self.assertRaises((PersistenceError,ContractError)):
                    store.add_artifact(review.uid(101),'evidence',path,b'{}',expected_revision=revision)
            self.assertEqual(len(store._artifacts()),1)

    def test_partial_non_native_wrong_identity_and_invalid_results_reject(self):
        model=review.example_model();value=synthetic(model)
        for mutate in (lambda v:v.update(model_hash='0'*64),lambda v:v.update(status='failed'),
                       lambda v:v['backend'].update(execution_mode='reference_external'),
                       lambda v:v.update(node_ids=[review.uid(4)]*2),lambda v:v.update(valid=False),
                       lambda v:v['samples'][1].update(time_s=0),lambda v:v['samples'][1].update(temperature_K=[-1,290]),
                       lambda v:v['samples'][1].update(conductive_in_W=[1]),lambda v:v['samples'][1].update(duty_cycles={'heater':1.1})):
            bad=deepcopy(value);mutate(bad)
            with self.assertRaises(ValueError):review.validate_result(bad,model)

    def test_contour_history_units_and_fixed_scale_are_canonical_queries(self):
        model=review.example_model();result=review.validate_result(synthetic(model),model)
        value=review.display(result,1,review.uid(5),'degC')
        self.assertEqual(value['history'],[(0,290-273.15),(1,291-273.15),(2,292-273.15)])
        self.assertEqual(value['powers']['conductive_in_W'],[-4,4])
        self.assertEqual(value['energy'],dict(defect_J=0))
        self.assertEqual(review.display(result,0)['upper'],review.display(result,2)['upper'])
        self.assertEqual(value['colours'],review.display(result,1)['colours'])
        with self.assertRaises(PersistenceError):review.display(result,3)
        with self.assertRaises(PersistenceError):review.display(result,0,review.uid(99))

    def test_prescribed_boundaries_use_equation_residual_ids_without_padding(self):
        model=review.example_model();model['entities'][2].update(classification='prescribed',capacity=dict(value=0,unit='J/K'))
        result=synthetic(model);result['equation_node_ids']=[review.uid(4)]
        for sample in result['samples']:sample['residual_W']=[0]
        value=review.validate_result(result,model)
        self.assertEqual(review.display(value,1)['powers']['residual_W'],[0])
        result['equation_node_ids']=[review.uid(5)]
        with self.assertRaises(PersistenceError):review.validate_result(result,model)

    def test_result_publication_save_reopen_staleness_and_historical_queries(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            with ProjectStore.create(folder/'state.db',review.example_model()) as store:
                model=store.snapshot();result_id=review.attach_result(store,synthetic(model),model,{},'0'*64)
                store.save(folder/'result.fcst')
                self.assertFalse(review.query_result(store,result_id)['historical'])
                node=deepcopy(model['entities'][1]);node['capacity']['value']=4
                review.change(store,node,expected_revision=0)
                with self.assertRaises(PersistenceError):review.query_result(store,result_id)
                self.assertTrue(review.query_result(store,result_id,historical=True)['historical'])
                before=store.state()
                with self.assertRaises(PersistenceError):review.attach_result(store,synthetic(model),model,{},'0'*64)
                self.assertEqual(store.state(),before)
            with ProjectStore.create(folder/'reopen.db',package=Package.open(folder/'result.fcst')) as store:
                self.assertEqual(review.query_result(store,result_id)['samples'],synthetic(model)['samples'])

    def test_candidate_gate_rejects_missing_duplicate_skipped_and_substituted_evidence(self):
        policy=json.loads((ROOT/'ci/host-acceptance.json').read_bytes())
        report=dict(candidate='a'*40,input_sha256={'owned.py':'b'*64},host_version=['1','1','4'],python_abi='cp311',
            gate=dict(status='passed'),spatial_solver_qualified=False,cases=[dict(id=c,status='passed') for c in policy['required_cases']])
        assess(report,'a'*40,report['input_sha256'],policy)
        for change in ('missing','duplicate','skipped','candidate','inputs','spatial'):
            bad=deepcopy(report)
            if change=='missing':bad['cases'].pop()
            if change=='duplicate':bad['cases'].append(bad['cases'][0])
            if change=='skipped':bad['cases'][0]['status']='skipped'
            if change=='candidate':bad['candidate']='c'*40
            if change=='inputs':bad['input_sha256']={}
            if change=='spatial':bad['spatial_solver_qualified']=True
            with self.assertRaises(ValueError):assess(bad,'a'*40,report['input_sha256'],policy)


if __name__=='__main__':unittest.main()
