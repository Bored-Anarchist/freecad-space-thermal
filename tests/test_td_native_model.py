# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fcst_app.persistence import Package,encode,save_package,recover_package
from fcst_exchange import ExchangeError
from fcst_exchange.dwg_native import NativeRuntime,NativeSnapshot,_one
from fcst_exchange.sinda import SindaUnits
from fcst_exchange.td_model import convert_network,restore_annotations
from fcst_exchange.td_writer import node_payload,conductor_payload,load_payload
from fcst_exchange.td_decode import decode_drawing
from fcst_exchange.independent_td import IndependentTdAdapter
from fcst_exchange.source_package import package_td,restore_td,export_td_package
from td_fixture import drawing,PATCH

SI=SindaUnits('K','J/K','W/K','W','s')


def records(temperature=300,capacity=10,conductance=2,power=1):
    return [node_payload('A',1,temperature,capacity,'capacitive','owned node'),
            node_payload('B',1,310,0,'prescribed'),conductor_payload('A',1,conductance,1,2),load_payload(power,1,'owned load')]


def changed_snapshot(snapshot,handle,changes,**options):
    payload=next(p for p in decode_drawing(snapshot).payloads if p.record['handle']==handle)
    row,_=payload.edited_record(changes,**options);native=deepcopy(snapshot.native);standard=deepcopy(snapshot.standard)
    native['objects']=[row if r['handle']==handle else r for r in native['objects']]
    for fields in _one(standard,'OBJECTS'):
        if _one(fields,'handle')[2]==handle:
            fields[:]=[(k,row['data'] if k=='unknown_bits' else row['bits'] if k=='num_unknown_bits' else v) for k,v in fields]
    return NativeSnapshot(native,standard,'')


class TdNativeModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.source=self.root/'source';self.source.mkdir();(self.source/'main.dwg').write_bytes(b'AC1032-owned')
        self.runtime=NativeRuntime(self.root/'backend.exe','b'*64,PATCH);self.adapter=IndependentTdAdapter(self.runtime,SI)

    def stage(self,snapshot=None,adapter=None):
        with patch.object(NativeRuntime,'run',return_value=(snapshot or drawing(records()),None,{})):
            return (adapter or self.adapter).preview(self.source,'main.dwg',self.root/'preview')

    def test_explicit_units_map_discrete_identities_references_and_quantities(self):
        staged=self.stage();model=staged.require_native();entities=model['entities'];nodes=[e for e in entities if e['kind']=='node']
        self.assertTrue(staged.report['native_ready']);self.assertFalse(staged.report['qualified']);self.assertEqual(len(entities),6)
        self.assertEqual({e['temperature']['value'] for e in nodes},{300,310})
        conductor=next(e for e in entities if e['kind']=='conductor');self.assertEqual(conductor['conductance'],{'value':2,'unit':'W/K'})
        self.assertEqual({conductor['from_node_id'],conductor['to_node_id']},{e['id'] for e in nodes})
        self.assertEqual(len(model['source_maps'][0]['entries']),6)

    def test_missing_units_and_unresolved_companions_refuse_native_conversion(self):
        staged=self.stage(adapter=IndependentTdAdapter(self.runtime));self.assertFalse(staged.report['native_ready'])
        self.assertEqual(staged.conversion.diagnostics[0]['code'],'td_native_explicit_units_required')
        (self.source/'unknown.dat').write_bytes(b'uninterpreted dependency')
        staged=self.stage();self.assertFalse(staged.report['native_ready'])
        with self.assertRaises(ExchangeError):staged.require_native()

    def test_units_convert_offsets_and_scaled_power_without_guessing_from_dwg(self):
        units=SindaUnits('degC','J/K','W/K','mW','min');snap=drawing(records(temperature=-20,power=2500))
        converted=convert_network(snap,units,'a'*64).require_native()
        node=next(e for e in converted['entities'] if e.get('label')=='owned node')
        self.assertAlmostEqual(node['temperature']['value'],253.15)
        self.assertEqual(next(e for e in converted['entities'] if e['kind']=='load')['power']['value'],2.5)
        p=decode_drawing(snap).payloads[0]
        p.edited_record({'initial_temperature':-10},temperature_unit='degC')
        with self.assertRaises(ExchangeError):p.edited_record({'initial_temperature':-274},temperature_unit='degC')

    def test_opaque_objects_datastorage_extended_data_and_active_modes_block_native(self):
        base=drawing(records())
        for key in ['opaque','storage','eed','clone','mode']:
            native=deepcopy(base.native);standard=deepcopy(base.standard)
            if key=='opaque':native['objects'][0]['kind']='UNKNOWN_OBJ';native['classes'][0]['cppname']='UnmappedSourceClass'
            elif key=='storage':native['opaque_sections']=[{'name':'AcDsPrototype_1b','byte_length':1,'data':'00'}]
            elif key=='eed':_one(standard,'OBJECTS')[0].append(('eed',[{'unmapped':1}]))
            else:
                payload=decode_drawing(base).payloads[0];fields=deepcopy(payload.fields)
                fields['node_type' if key=='clone' else 'source_switches']=3 if key=='clone' else (True,False,False)
                from dataclasses import replace
                with patch('fcst_exchange.td_model.decode_drawing',return_value=replace(decode_drawing(base),payloads=(replace(payload,fields=fields),*decode_drawing(base).payloads[1:]))):
                    self.assertIsNone(convert_network(base,SI,'a'*64).model);continue
            self.assertIsNone(convert_network(NativeSnapshot(native,standard,''),SI,'a'*64).model)

    def test_missing_connections_duplicate_numbers_and_submodel_case_aliases_reject(self):
        variants=[records()[:2]+[conductor_payload('A',1,2,1,3),records()[3]],
                  [node_payload('A',1,300,10,'capacitive'),node_payload('A',1,310,0,'prescribed'),*records()[2:]],
                  [records()[0],node_payload('a',2,310,0,'prescribed'),*records()[2:]]]
        for variant in variants:self.assertIsNone(convert_network(drawing(variant),SI,'a'*64).model)

    def test_portable_package_roundtrip_retains_every_source_byte_and_empty_directory(self):
        (self.source/'empty').mkdir();staged=self.stage();package=package_td(staged);path=self.root/'native.fcst'
        save_package(package,path);restored=recover_package(path);entry,units=restore_td(restored,self.root/'restored')
        self.assertEqual(entry,'main.dwg');self.assertEqual(units,SI);self.assertTrue((self.root/'restored/empty').is_dir())
        self.assertEqual((self.root/'restored/main.dwg').read_bytes(),b'AC1032-owned')
        self.assertEqual(restored.model['entities'],staged.require_native()['entities'])

    def test_portable_metadata_traversal_aliases_and_stale_source_binding_fail_before_publication(self):
        package=package_td(self.stage());name='exchange/td-source-map.json'
        for case in ['path','alias','revision','depth']:
            files=dict(package.files);meta=json.loads(files[name]);aliases=meta['source_paths'];alias=next(iter(aliases.values()))
            if case=='path':meta['source_paths']={'../escape.dwg':alias};meta['entry']='../escape.dwg'
            elif case=='alias':meta['source_paths']['other.dwg']=alias
            elif case=='depth':meta['directories']=['/'.join(['nested']*40)]
            else:meta['source_revision']='f'*64
            files[name]=encode(meta);manifest=deepcopy(package.manifest);r=next(r for r in manifest['artifacts'] if r['artifact']['path']==name)
            r['artifact'].update(sha256=sha256(files[name]).hexdigest(),byte_length=len(files[name]));bad=Package(manifest,files)
            with self.assertRaises(ExchangeError):restore_td(bad,self.root/('bad-'+case))
            self.assertFalse((self.root/('bad-'+case)).exists())

    def test_native_edit_reopens_values_and_preserves_unrequested_source_bytes(self):
        before=drawing(records());staged=self.stage(before);target=staged.require_native()
        node=next(e for e in target['entities'] if e.get('label')=='owned node');node['temperature']['value']=305
        after=changed_snapshot(before,101,{'initial_temperature':305})
        with patch.object(NativeRuntime,'run',side_effect=[(after,b'AC1032-edited',{}),(after,None,{})]):
            result=self.adapter.export_native(staged,target,self.root/'edited',self.root/'edit')
        self.assertTrue(result['canonical_roundtrip_verified']);self.assertTrue(result['native_ready']);self.assertFalse(result['qualified'])
        with patch.object(NativeRuntime,'run',return_value=(after,None,{})):
            reopened=self.adapter.preview(self.root/'edited','main.dwg',self.root/'reopen')
        self.assertEqual(reopened.require_native()['entities'],target['entities'])
        self.assertEqual((self.source/'main.dwg').read_bytes(),b'AC1032-owned')

    def test_native_topology_or_label_edits_and_failed_reopen_leave_no_export(self):
        before=drawing(records());staged=self.stage(before);model=staged.require_native()
        for field in ['classification','label']:
            target=deepcopy(model);node=next(e for e in target['entities'] if e.get('label')=='owned node')
            if field=='classification':node[field]='algebraic';node['capacity']['value']=0
            else:node[field]='new annotation'
            with self.assertRaises(ExchangeError):self.adapter.export_native(staged,target,self.root/field,self.root/(field+'-work'))
            self.assertFalse((self.root/field).exists())
        target=deepcopy(model);next(e for e in target['entities'] if e.get('label')=='owned node')['temperature']['value']=305
        with patch.object(NativeRuntime,'run',return_value=(before,b'AC1032-wrong',{})):
            with self.assertRaises(ExchangeError):self.adapter.export_native(staged,target,self.root/'failed',self.root/'failed-work')
        self.assertFalse((self.root/'failed').exists())

    def test_owned_annotation_quantities_and_identity_inventory_are_verified_not_trusted(self):
        base=drawing(records());conversion=convert_network(base,SI,'a'*64);model=conversion.require_native()
        receipt={'identities':list(conversion.identities)}
        self.assertIsNotNone(restore_annotations(conversion,model,receipt).model)
        target=deepcopy(model);next(e for e in target['entities'] if e['kind']=='node')['temperature']['value']=999
        self.assertIsNone(restore_annotations(conversion,target,receipt).model)
        bad={'identities':list(conversion.identities)[:-1]}
        self.assertIsNone(restore_annotations(conversion,model,bad).model)

    def test_noop_native_export_preserves_drawing_and_existing_destinations_refuse(self):
        staged=self.stage();target=staged.require_native();result=self.adapter.export_native(staged,target,self.root/'copy',self.root/'copy-work')
        self.assertEqual(result['changed_entities'],0);self.assertEqual((self.root/'copy/main.dwg').read_bytes(),b'AC1032-owned')
        with self.assertRaises(ExchangeError):self.adapter.export_native(staged,target,self.root/'copy',self.root/'another-work')

    def test_portable_export_checks_workspace_overlap_without_starting_a_converter(self):
        package=package_td(self.stage())
        with patch.object(NativeRuntime,'run',side_effect=AssertionError('must not execute')):
            with self.assertRaises(ExchangeError):export_td_package(package,self.runtime,self.root/'work/export',self.root/'work')

    def test_large_native_handles_survive_json_companions_without_integer_precision_loss(self):
        handles=[9007199254740993+i for i in range(4)];snap=drawing(records(),handles);staged=self.stage(snap)
        target=staged.require_native();self.adapter.export_native(staged,target,self.root/'large',self.root/'work')
        metadata=json.loads((self.root/'large/identity-map.json').read_bytes())
        self.assertEqual({row['handle'] for row in metadata['identities'] if 'handle' in row},{str(h) for h in handles})
        with patch.object(NativeRuntime,'run',return_value=(snap,None,{})):
            reopened=self.adapter.preview(self.root/'large','main.dwg',self.root/'reopen')
        self.assertEqual(reopened.require_native()['entities'],target['entities'])

    def test_native_fidelity_distinguishes_canonical_import_from_structural_inspection(self):
        schema=json.loads((Path(__file__).resolve().parents[1]/'spec/schemas/exchange-fidelity-v1.schema.json').read_bytes())
        staged=self.stage();self.assertEqual(set(staged.fidelity),set(schema['required']))
        self.assertTrue(staged.fidelity['runnable']);self.assertEqual(staged.report['thermal_mapping'],'canonical-constant-network')
        self.assertTrue(all(r['status']=='native-reconstructed' for r in staged.fidelity['records']))
        self.assertEqual({r['target_id'] for r in staged.fidelity['records']},{e['id'] for e in staged.require_native()['entities']})
        untyped=self.stage(adapter=IndependentTdAdapter(self.runtime))
        self.assertFalse(untyped.fidelity['runnable']);self.assertFalse(untyped.fidelity['qualified'])
