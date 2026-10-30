# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fcst_exchange import ExchangeError
from fcst_exchange.dwg_bits import Bits
from fcst_exchange.dwg_native import NativeRuntime,NativeSnapshot,Fields,_one,compare_edits,edit_packet
from fcst_exchange.td_node import decode_node
from fcst_exchange.td_conductor import decode_conductor
from fcst_exchange.td_load import decode_load
from fcst_exchange.td_decode import decode_drawing
from fcst_exchange.td_writer import node_payload,conductor_payload,load_payload,network_packet,render_model,verify_network,export_model
from fcst_exchange.independent_td import IndependentTdAdapter
from td_fixture import envelope,drawing,PATCH
from test_sinda_writer import model


def records():
    return [node_payload('MAIN',1,300,10,'capacitive','owned \u03b1'),node_payload('MAIN',2,310,0,'prescribed'),
            conductor_payload('MAIN',1,0,1,2),load_payload(0,1)]


class TdPayloadTests(unittest.TestCase):
    def test_bit_primitives_use_independent_known_vectors_and_reject_bad_tags(self):
        self.assertEqual(Bits(bytes.fromhex('8000'),0,2).bl(),0)
        self.assertEqual(Bits(bytes.fromhex('4040'),0,10).bl(),1)
        self.assertEqual(Bits(b'\xc0',0,2).bs(),256)
        self.assertEqual(Bits(b'\x40',0,2).bd(),1)
        self.assertEqual(Bits(b'\x80',0,2).bd(),0)
        self.assertEqual(Bits(bytes.fromhex('4101')).handle(100)['target'],1)
        self.assertEqual(Bits(bytes.fromhex('60')).handle(100)['target'],101)
        self.assertEqual(Bits(bytes.fromhex('a102')).handle(100)['target'],102)
        for raw in (b'\xc0',):
            with self.assertRaises(ExchangeError):Bits(raw).bl()
            with self.assertRaises(ExchangeError):Bits(raw).bd()
        with self.assertRaises(ExchangeError):Bits(b'\x00',end=9)
        with self.assertRaises(ExchangeError):Bits(b'\x00').raw(2)
        with self.assertRaises(ExchangeError):Bits(b'\x69\x00').handle(1)

    def test_complete_profiles_decode_unicode_quantities_ids_and_handle_closure(self):
        s=drawing(records());inventory=decode_drawing(s)
        self.assertEqual(len(inventory.payloads),4);self.assertEqual(inventory.report['retained_objects'],0)
        a,b,c,d=inventory.payloads
        self.assertEqual((a.fields['initial_temperature'],a.fields['mass_value'],a.fields['comment']),(300,10,'owned \u03b1'))
        self.assertEqual((b.fields['node_type'],b.fields['mass_value']),(2,0))
        self.assertEqual(c.fields['from'][0]['reference']['target'],101)
        self.assertEqual(c.fields['to'][0]['reference']['target'],102)
        self.assertEqual(d.fields['connections'][0]['reference']['target'],101)
        self.assertEqual(verify_network(s,records()),[101,102,103,104])
        self.assertFalse(inventory.report['native_ready']);self.assertFalse(inventory.report['qualified'])

    def test_split_stream_metadata_truncation_and_future_versions_fail_closed(self):
        row,standard=envelope(records()[0])
        for field,value in [('data_bits',0),('string_bits',1),('handle_bits',0),('object_bits',0),('bits',row['bits']-8)]:
            with self.assertRaises(ExchangeError):decode_node(dict(row,**{field:value}),Fields(standard.items()))
        raw=bytearray.fromhex(row['data']);raw[1]^=64
        with self.assertRaises(ExchangeError):decode_node(dict(row,data=raw.hex()),Fields(standard.items()))
        for size in range(0,len(bytes.fromhex(row['data'])),17):
            with self.assertRaises(ExchangeError):decode_node(dict(row,data=bytes.fromhex(row['data'])[:size].hex()),Fields(standard.items()))

    def test_scalar_edits_expand_compressed_values_and_preserve_every_other_field(self):
        inventory=decode_drawing(drawing(records()))
        for payload,changes,decoder in [(inventory.payloads[1],{'mass_value':12,'initial_temperature':320},decode_node),
                                         (inventory.payloads[2],{'value':.75},decode_conductor),
                                         (inventory.payloads[3],{'value':-5},decode_load)]:
            row,receipt=payload.edited_record(changes);after=decoder(row,payload.standard)
            self.assertEqual(after.fields,{**payload.fields,**changes});self.assertEqual(row['bits']-payload.record['bits'],64)
            self.assertFalse(receipt['bit_length_preserved']);self.assertFalse(receipt['qualified'])
            self.assertEqual(row['handle_bits'],payload.record['handle_bits']);self.assertEqual(row['string_bits'],payload.record['string_bits'])
            self.assertTrue(edit_packet([(payload.record,row)]).startswith(b'FCSTEDIT2'))

    def test_dynamic_logic_expression_and_negative_or_nonfinite_edits_are_refused(self):
        inventory=decode_drawing(drawing(records()))
        for payload in inventory.payloads:
            key='initial_temperature' if 'initial_temperature' in payload.fields else 'value'
            for value in (float('nan'),float('inf'),True,'secret-value'):
                with self.assertRaises(ExchangeError) as e:payload.edited_record({key:value})
                self.assertNotIn('secret-value',str(e.exception))
            if 'logic' in payload.fields:
                f=deepcopy(payload.fields);f['logic']['condition']='CALL untrusted()'
            else:
                f=deepcopy(payload.fields);f['expression']['text']='CALL untrusted()'
            with self.assertRaises(ExchangeError):replace(payload,fields=f).edited_record({key:12})
        with self.assertRaises(ExchangeError):inventory.payloads[0].edited_record({'initial_temperature':0})
        with self.assertRaises(ExchangeError):inventory.payloads[2].edited_record({'value':-1})

    def test_partial_tail_encoding_class_names_and_duplicate_edits_are_checked(self):
        from test_native_dwg import packet,standard
        from fcst_exchange.dwg_native import snapshot
        p=packet();p['objects'][0]['data']='aa81'
        with self.assertRaisesRegex(ExchangeError,'tail'):snapshot(json.dumps(p).encode(),standard(),PATCH)
        p=packet();p['classes'][0]['cppname']='F'
        with self.assertRaisesRegex(ExchangeError,'class_text'):snapshot(json.dumps(p).encode(),standard(),PATCH)
        payload=decode_drawing(drawing(records())).payloads[2];row,_=payload.edited_record({'value':1})
        with self.assertRaises(ExchangeError):edit_packet([(payload.record,row)]*2)
        with self.assertRaises(ExchangeError):edit_packet([(payload.record,dict(row,handle=100))])

    def test_unmapped_classes_and_unknown_payload_versions_keep_source_and_block_native(self):
        s=drawing(records());native=deepcopy(s.native);native['classes'][0]['cppname']='UnknownThermalClass'
        report=decode_drawing(NativeSnapshot(native,s.standard,'')).report
        self.assertEqual(report['retained_objects'],2);self.assertFalse(report['native_ready'])
        self.assertNotIn('UnknownThermalClass',json.dumps(report))
        self.assertNotIn('owned',json.dumps(decode_drawing(s).report))

    def test_generated_inventory_missing_objects_wrong_references_or_values_cannot_pass(self):
        for other in (records()[:-1],records()[:2]+[conductor_payload('MAIN',1,0,2,1),records()[3]],
                      [node_payload('MAIN',1,301,10,'capacitive','owned \u03b1')]+records()[1:]):
            with self.assertRaises(ExchangeError):verify_network(drawing(other),records())

    def test_new_model_writer_is_deterministic_and_rejects_unmapped_content_or_empty_submodels(self):
        a=model();b=deepcopy(a);b['entities'].reverse()
        self.assertEqual(render_model(a),render_model(b));self.assertEqual(a,model())
        a['entities'].append({'id':'00000000-0000-4000-8000-000000000099','kind':'submodel'})
        with self.assertRaisesRegex(ExchangeError,'empty_submodel'):render_model(a)
        a=model();a['entities'][0]['parent_id']=a['entities'][1]['id']
        with self.assertRaises(ExchangeError):render_model(a)
        for bad in ([],[None]):
            with self.assertRaises(ExchangeError):network_packet(bad)

    def test_failed_native_reopen_and_unsafe_targets_never_publish_a_new_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=NativeRuntime(root/'converter.exe','b'*64,PATCH)
            with patch.object(NativeRuntime,'run',side_effect=[({'derived.dwg':b'AC1032-owned'},{}),(drawing(records()[:-1]),None,{})]):
                with self.assertRaises(ExchangeError):export_model(model(),runtime,root/'failed',root/'work')
            self.assertFalse((root/'failed').exists());self.assertFalse(list(root.glob('.fcst-td-new-*')))
            with self.assertRaises(ExchangeError):export_model(model(),runtime,root/'nested',root/'nested/work')

    def test_source_field_exports_preserve_unrequested_files_and_refuse_stale_or_unmapped_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();(source/'main.dwg').write_bytes(b'AC1032-owned')
            (source/'unmapped.bin').write_bytes(b'private-source-preserved');(source/'empty').mkdir()
            runtime=NativeRuntime(root/'converter.exe','b'*64,PATCH);adapter=IndependentTdAdapter(runtime);before=drawing(records())
            with patch.object(NativeRuntime,'run',return_value=(before,None,{})):staged=adapter.preview(source,'main.dwg',root/'preview')
            payload=decode_drawing(before).payloads[2];replacement,_=payload.edited_record({'value':.75});after_native=deepcopy(before.native)
            after_native['objects'][2]=replacement;after_standard=deepcopy(before.standard)
            obj=_one(after_standard,'OBJECTS')[2]
            obj[:]=[(k,replacement['data'] if k=='unknown_bits' else replacement['bits'] if k=='num_unknown_bits' else v) for k,v in obj]
            after=NativeSnapshot(after_native,after_standard,'')
            self.assertTrue(compare_edits(before,after,[(payload.record,replacement)])['edited_roundtrip_verified'])
            with patch.object(NativeRuntime,'run',side_effect=[(after,b'AC1032-edited',{}),(after,None,{})]):
                result=adapter.export_source(staged,root/'export',[{'handle':103,'changes':{'value':.75}}],work=root/'edit')
            self.assertTrue(result['edited_roundtrip_verified']);self.assertFalse(result['native_ready'])
            self.assertEqual((root/'export/unmapped.bin').read_bytes(),b'private-source-preserved');self.assertTrue((root/'export/empty').is_dir())
            self.assertEqual((source/'main.dwg').read_bytes(),b'AC1032-owned')
            with self.assertRaises(ExchangeError):adapter.export_source(staged,root/'bad',[{'handle':999,'changes':{'value':1}}],work=root/'bad-work')
            (source/'unmapped.bin').write_bytes(b'changed')
            with self.assertRaises(ExchangeError):adapter.export_source(staged,root/'stale',[{'handle':103,'changes':{'value':1}}],work=root/'stale-work')
            self.assertFalse((root/'stale').exists())

    def test_unrequested_logical_changes_prevent_source_field_export(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();(source/'main.dwg').write_bytes(b'AC1032-owned')
            runtime=NativeRuntime(root/'converter.exe','b'*64,PATCH);adapter=IndependentTdAdapter(runtime);before=drawing(records())
            with patch.object(NativeRuntime,'run',return_value=(before,None,{})):staged=adapter.preview(source,'main.dwg',root/'preview')
            with patch.object(NativeRuntime,'run',return_value=(before,b'AC1032-wrong',{})):
                with self.assertRaises(ExchangeError):adapter.export_source(staged,root/'failed',[{'handle':103,'changes':{'value':9}}],work=root/'edit')
            self.assertFalse((root/'failed').exists())

    def test_malformed_filer_fuzz_and_declared_budgets_never_execute_source(self):
        import random
        rng=random.Random(808);row,standard=envelope(records()[0]);raw=bytes.fromhex(row['data'])
        with patch('subprocess.Popen',side_effect=AssertionError('source execution forbidden')):
            for _ in range(200):
                data=bytearray(raw);index=rng.randrange(len(data));data[index]^=1<<rng.randrange(8)
                try:payload=decode_node(dict(row,data=data.hex()),Fields(standard.items()))
                except ExchangeError:continue
                self.assertFalse(payload.report['native_ready']);self.assertFalse(payload.report['qualified'])
        for record in (replace(records()[0],data_bits=0),replace(records()[0],string_bits=32768),
                       replace(records()[0],references=(999,)),replace(records()[0],data=b'')):
            with self.assertRaises(ExchangeError):network_packet([record])
