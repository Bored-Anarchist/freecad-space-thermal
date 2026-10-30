# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fcst_exchange import ExchangeError
from fcst_exchange.opentd import Runtime,HostAuthorization,TdLimits,PROFILE,ASSEMBLY_SHA256,validate_edits
from fcst_exchange.td_project import capture_project,inventory,OpenTdAdapter,verify_edited_inventory,validate_project_edits
from fcst_exchange.td_qualification import assess,REQUIRED
from fcst_exchange.sinda import SindaAdapter
from fcst_exchange.sinda_results import read_print
from fcst_exchange.results import query
from test_sinda import UNITS,NETWORK


def api_inventory():
    def node(handle,number,node_type,temp,capacity):
        return {'Handle':handle,'Id':number,'Submodel':{'Name':'MAIN'},'NodeType':node_type,'InitialTemp':{'dimension':'Temp','si_value':temp},
                'MassVol':capacity,'UseMaterial':0,'UseVersusTime':0,'InitialTempExp':{'Value':''},'TCode':{}}
    return {'profile':PROFILE,'api':{'assembly_version':'6.3.0.0','assembly_sha256':ASSEMBLY_SHA256,'qualified':False},
            'units':'SI','qualified':False,'execution_mode':'reference_external','dependency_paths':{},
            'collections':{'Nodes':[node('A1',1,'DIFFUSION',293.15,100),node('A2',2,'BOUNDARY',300,0)],
                           'Conductors':[{'Handle':'B1','From':{'Handle':'A1','Marker':0},'To':[{'Handle':'A2','Marker':0}],
                                          'Value':2,'OneWay':'NONE'}],
                           'HeatLoads':[{'Handle':'C1','Type':'LOAD','ApplyConnections':[{'Handle':'A1','Marker':0}],'Value':5}]}}


class OpenTdTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        (self.source/'model (1).dwg').write_bytes(b'AC1032 public synthetic DWG signature; not a real drawing')
        (self.source/'properties (1).tdp').write_bytes(b'public synthetic property bytes')
        self.project=capture_project(self.source,'model (1).dwg')

    def test_discovery_is_inert_and_missing_runtime_does_not_start_processes(self):
        with patch('subprocess.Popen',side_effect=AssertionError('discovery executed code')):
            result=Runtime().probe()
        self.assertFalse(result['available']);self.assertIn('licensed_autocad_host_missing',result['blockers'])
        adapter=OpenTdAdapter(Runtime(),self.root/'absent.exe')
        with self.assertRaisesRegex(ExchangeError,'licensed_runtime_prerequisite'):
            adapter.inspect(self.project,self.root/'copy',None)
        self.assertFalse((self.root/'copy').exists())

    def test_complete_copied_project_preserves_bytes_and_rejects_stale_or_original_targets(self):
        (self.source/'empty output').mkdir()
        self.project=capture_project(self.source,'model (1).dwg')
        copied=self.project.copy_to(self.root/'copy')
        self.assertEqual((copied/'model (1).dwg').read_bytes(),dict(self.project.files)['model (1).dwg'])
        self.assertEqual((copied/'properties (1).tdp').read_bytes(),b'public synthetic property bytes')
        self.assertTrue((copied/'empty output').is_dir())
        with self.assertRaisesRegex(ExchangeError,'td_requires_new_tree'):self.project.copy_to(self.source/'nested')
        (self.source/'properties (1).tdp').write_bytes(b'changed')
        with self.assertRaisesRegex(ExchangeError,'stale_td_project'):self.project.copy_to(self.root/'stale')

    def test_network_inventory_maps_actual_api_dimensions_classes_and_connections(self):
        staged=inventory(self.project,api_inventory())
        self.assertTrue(staged.report['runnable'],staged.report)
        self.assertFalse(staged.report['qualified']);self.assertFalse(staged.report['native_execution_available'])
        self.assertEqual(len(staged.model['entities']),5)
        self.assertEqual(next(e for e in staged.model['entities'] if e['kind']=='conductor')['conductance']['value'],2)
        snapshot=staged.inventory;snapshot['units']='guessed';self.assertEqual(staged.inventory['units'],'SI')

    def test_geometry_cases_tables_procedures_and_gmm_are_inventoried_not_silently_dropped(self):
        raw=api_inventory()
        for name in ('Rectangles','CaseSets','LogicObjects','Domains','ThermoPropss','OpticalPropss'):
            raw['collections'][name]=[{'Handle':'D1','Name':'synthetic','BaseTrans':[[1,0,0],[0,1,0],[0,0,1]],'TopOpticalProp':'public'}]
        staged=inventory(self.project,raw)
        self.assertFalse(staged.report['runnable'])
        self.assertEqual(len(staged.report['records']),10)
        self.assertEqual(staged.inventory['collections']['Rectangles'],raw['collections']['Rectangles'])
        with self.assertRaisesRegex(ExchangeError,'required_td_semantics_unresolved'):staged.require_native()
        raw['collections']={'Rectangles':[{'Handle':'D1'}]}
        self.assertEqual(inventory(self.project,raw).report['source_kind'],'geometry-only')

    def test_dynamic_source_expressions_and_external_databases_block_native_readiness(self):
        raw=api_inventory();raw['collections']['Nodes'][0]['InitialTempExp']['Value']='arbitrary_source_procedure()'
        self.assertFalse(inventory(self.project,raw).report['runnable'])
        raw=api_inventory();raw['dependency_paths']['thermal_properties']='unresolved-external-property-database.tdp'
        self.assertIn('td_external_dependency_unresolved',[e['code'] for e in inventory(self.project,raw).report['diagnostics']])
        raw=api_inventory();raw['units']='drawing units not declared'
        with self.assertRaisesRegex(ExchangeError,'td_inventory_contract'):inventory(self.project,raw)
        for field,value in [('NodeType',[]),('InitialTempExp',{'Value':[]})]:
            raw=api_inventory();raw['collections']['Nodes'][0][field]=value
            self.assertFalse(inventory(self.project,raw).report['runnable'])

    def test_controlled_edit_validation_and_every_unrequested_field_are_checked(self):
        before=api_inventory();after=deepcopy(before);after['collections']['Conductors'][0]['Value']=4
        edits=[{'kind':'Conductor','handle':'B1','field':'Value','value':4}]
        self.assertTrue(verify_edited_inventory(before,after,edits))
        after['collections']['Nodes'][0]['InitialTemp']['si_value']=290
        with self.assertRaisesRegex(ExchangeError,'td_export_semantics_changed'):verify_edited_inventory(before,after,edits)
        for edit in ({'kind':'Node','handle':'A1','field':'TCode','value':1},
                     {'kind':'Node','handle':'A1','field':'InitialTemp','value':-1},
                     {'kind':'OpticalProps','handle':'public material','field':'Alph','value':1.1}):
            with self.assertRaises(ExchangeError):validate_edits([edit])
        with self.assertRaisesRegex(ExchangeError,'td_edit_collision'):validate_edits(edits*2)
        raw=api_inventory();raw['collections']['Conductors'][0]['ValueExp']={'Value':'UNREVIEWED_SOURCE'}
        with self.assertRaisesRegex(ExchangeError,'td_dynamic_field_edit'):
            validate_project_edits(inventory(self.project,raw),edits)

    def test_authorization_binds_candidate_source_and_reviewed_execution_kind(self):
        source='1'*64;candidate='2'*64
        auth=HostAuthorization('public synthetic decision',candidate,source,'3'*64,'reviewed-source-copy/1')
        auth.validate(source,candidate)
        with self.assertRaisesRegex(ExchangeError,'td_authorization'):auth.validate('4'*64,candidate)
        with self.assertRaisesRegex(ExchangeError,'td_source_execution_not_reviewed'):auth.validate(source,candidate,creating=True)
        with self.assertRaises(ExchangeError):TdLimits(timeout_seconds=float('inf'))

    def test_tprint_results_map_source_nodes_time_units_and_quantity_without_guessing(self):
        (self.source/'network.inp').write_bytes(NETWORK)
        model=SindaAdapter(UNITS).preview(self.source,'network.inp').model
        raw=(b'PRINT AT TIMEN = 0.0D0\nSUBMODEL NAME = MAIN\n T 1=20.0  T 2=30.0\n'
             b'PRINT AT TIMEN = 1.0D0\nSUBMODEL NAME = MAIN\n T 1=30.0  T 2=40.0\n')
        result=read_print(raw,model,quantity='temperature',unit='degC',time_unit='min',interpolation='linear')
        self.assertEqual(result.time,(0,60));self.assertEqual(query(result,30)['values'],[298.15,308.15])
        self.assertEqual(result.source_sha256,sha256(raw).hexdigest())
        for bad in (raw.replace(b'T 2=30.0',b'T 99=30.0'),raw.replace(b'T 2=30.0',b''),raw.replace(b'T 2=30.0',b'T 1=30.0')):
            with self.assertRaises(ExchangeError):read_print(bad,model,quantity='temperature',unit='degC',time_unit='s')

    def test_qualification_rejects_missing_stale_mock_external_and_unpaired_evidence(self):
        self.assertFalse(assess([],candidate='candidate')['qualified'])
        from fcst_exchange.td_qualification import PROFILE as INDEPENDENT_PROFILE,FILE_CASES
        records=[{'id':name,'status':'passed','candidate':'candidate','profile':INDEPENDENT_PROFILE,'fixture_kind':'owned-source',
                  'execution_mode':'fcst_native','native_engine_sha256':'1'*64,'source_reference_sha256':'2'*64,
                  'criteria_sha256':'3'*64,'observations_sha256':'4'*64,'independent_edit_receipt_sha256':'5'*64,
                  'vendor_absent':True,'vendor_call_attempts':0,'unresolved_required':0,
                  'codec_sha256':'6'*64,'input_sha256':'7'*64,'output_sha256':'8'*64} for name in REQUIRED]
        for record in records:
            if record['id'] in FILE_CASES:record['execution_mode']='fcst_independent_file_codec'
        self.assertTrue(assess(records,candidate='candidate')['qualified'])
        for field,value in [('execution_mode','fallback_external'),('fixture_kind','sdk-shim'),('candidate','stale')]:
            changed=deepcopy(records);next(r for r in changed if r['id']=='owned_thermal_comparison')[field]=value
            self.assertFalse(assess(changed,candidate='candidate')['qualified'])
        self.assertFalse(assess(records[:-1],candidate='candidate')['qualified'])
        self.assertFalse(assess(records+[records[0]],candidate='candidate')['qualified'])
        self.assertFalse(assess(records,candidate='candidate',profile=PROFILE)['qualified'])
        for name,field,value in [('vendor_absent_import_export','vendor_absent',False),
                                 ('vendor_absent_import_export','vendor_call_attempts',1),
                                 ('independent_td_class_coverage','unresolved_required',1),
                                 ('new_model_export_reopen','output_sha256','')]:
            changed=deepcopy(records);next(r for r in changed if r['id']==name)[field]=value
            self.assertFalse(assess(changed,candidate='candidate')['qualified'])

    def test_managed_sidecar_source_is_text_but_private_values_and_binary_payloads_are_not_cleared(self):
        from fcst_tools.privacy import Scanner,POLICY_PATH
        import json
        policy=json.loads(POLICY_PATH.read_bytes());self.assertIn('.cs',policy['text_extensions'])
        scanner=Scanner(policy);scanner.scan('bridge.cs',b'// public source\nclass Bridge {}\n')
        self.assertFalse(scanner.findings)
        scanner=Scanner(policy);scanner.scan('bridge.cs',b'MZ\x00\x01\xff\x00binary')
        self.assertTrue(scanner.findings)
        scanner=Scanner(policy)
        private_path='C:'+chr(92)+'Users'+chr(92)+'example-private-account'+chr(92)+'file'
        scanner.scan('bridge.cs',('// '+private_path).encode())
        self.assertTrue(scanner.findings)

    def test_invalid_api_versions_and_unmapped_connections_cannot_gain_native_status(self):
        raw=api_inventory();raw['api']['assembly_version']='6.2.0.0'
        with self.assertRaisesRegex(ExchangeError,'td_inventory_version'):inventory(self.project,raw)
        raw=api_inventory();raw['collections']['Conductors'][0]['To'][0]['Handle']='BAD'
        self.assertFalse(inventory(self.project,raw).report['runnable'])
        raw=api_inventory();raw['collections']['Nodes'][0]['InitialTemp']['si_value']=float('nan')
        with self.assertRaisesRegex(ExchangeError,'td_inventory_contract'):inventory(self.project,raw)

    def test_empty_sdk_logic_units_metadata_is_inert_but_nonempty_source_code_blocks(self):
        raw=api_inventory();logic={'Variables0':'','Operations':'','Output':'','TranslateCodeUnits':{'SindaUidOrNonFlocad':'UID','NonFlocadUnitsValues':{'temp':'K'}}}
        raw['collections']['Nodes'][0]['TCode']=logic
        self.assertTrue(inventory(self.project,raw).report['runnable'])
        logic['Operations']='CALL UNREVIEWED_SOURCE'
        self.assertFalse(inventory(self.project,raw).report['runnable'])

    def test_external_synthetic_reference_oracle_checks_identity_time_and_thermal_curve(self):
        import json,math
        from fcst_exchange.td_reference import compare
        from fcst_exchange.results import read_results
        model=inventory(self.project,api_inventory()).model
        entries=[e for e in model['source_maps'][0]['entries'] if 'node_number' in e]
        identities=[[e['namespace'],e['handle']] for e in entries]
        criteria=json.loads((Path(__file__).resolve().parents[1]/'ci/td-reference-criteria-v1.json').read_bytes())
        def table(values,times):
            from fcst_app.persistence import encode
            return read_results(encode({'version':'fcst-results/1','identities':identities,'quantity':'temperature','unit':'K',
                                       'time_unit':'s','sign':'absolute','time':times,'values':values,'interpolation':'none','discontinuities':[]}),model)
        transient=[[302.5+(293.15-302.5)*math.exp(-t/50),300] for t in (0,50,100)]
        results={'steady':table([[302.5,300]],[0]),'transient':table(transient,[0,50,100])}
        self.assertEqual(compare(results,model,criteria)['status'],'passed')
        self.assertFalse(compare(results,model,criteria)['qualified'])
        results['steady']=table([[301,300]],[0])
        with self.assertRaisesRegex(ExchangeError,'reference_temperature_mismatch'):compare(results,model,criteria)
