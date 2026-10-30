# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fcst_exchange import ExchangeError
from fcst_exchange.dwg_native import NativeSnapshot,Fields,_one
from fcst_exchange.td_geometry import decode_rectangle,decode_rectangle_complete,decode_brick,rectangle_payload,brick_payload,SENTINEL
from fcst_exchange.td_writer import FilerWriter
from fcst_exchange.td_decode import decode_drawing
from fcst_exchange.td_model import convert_network
from fcst_exchange.sinda import SindaUnits
from td_fixture import drawing,envelope,PATCH
from td_geometry_fixture import rectangle_fields,brick_fields


def rectangle():
    f=FilerWriter();b=f.data;b.bd(SENTINEL);b.bl(7)
    for value in (0,1,0,2,0,0):b.bd(value)
    for point in ((1,2,3),(1,0,0),(0,1,0),(0,0,1)):b.point(point)
    # Independently authored opaque attributes. They are never treated as TD
    # surface/mesh/material semantics or made eligible for thermal edits.
    b.bl(99);f.text('owned opaque attributes');return f.result(1)


class TdGeometryTests(unittest.TestCase):
    def test_complete_rectangle_and_brick_preserve_all_attribute_mesh_and_advection_fields(self):
        for build,decode,fields in ((rectangle_payload,decode_rectangle_complete,rectangle_fields()),(brick_payload,decode_brick,brick_fields())):
            before=deepcopy(fields);row,common=envelope(build(fields));actual=decode(row,Fields(common.items()))
            native=dict(actual.fields);native.pop('common_handles')
            self.assertEqual(native,before);self.assertEqual(fields,before);self.assertTrue(actual.report['payload_decoded'])
            self.assertFalse(actual.report['thermal_semantics_decoded']);self.assertFalse(actual.report['native_ready'])
            self.assertFalse(actual.report['qualified']);self.assertNotIn('OWNED',str(actual.report))

    def test_complete_geometry_does_not_enable_native_network_or_drop_unknown_physics(self):
        snap=drawing([rectangle_payload(rectangle_fields()),brick_payload(brick_fields())]);inventory=decode_drawing(snap)
        self.assertEqual(inventory.report['decoded_objects'],2);self.assertEqual(inventory.report['partial_objects'],0)
        result=convert_network(snap,SindaUnits('K','J/K','W/K','W','s'),'a'*64)
        self.assertIsNone(result.model);self.assertEqual(sum(d['code']=='td_native_geometry_semantics_unmapped' for d in result.diagnostics),2)
        native=deepcopy(snap.native);next(c for c in native['classes'] if c['cppname']=='RcFdBrick')['dxfname']='RCFDBRICK'
        held=decode_drawing(NativeSnapshot(native,snap.standard,''))
        self.assertEqual(held.report['decoded_objects'],1);self.assertEqual(held.report['retained_objects'],1)
        self.assertEqual(next(r['limitation'] for r in held.records if r['status']=='retained-opaque'),'td_geometry_class_identity_unmapped')

    def test_complete_geometry_scalar_splices_expand_and_preserve_all_other_fields_and_streams(self):
        for build,decode,fields in ((rectangle_payload,decode_rectangle_complete,rectangle_fields()),(brick_payload,decode_brick,brick_fields())):
            row,common=envelope(build(fields));p=decode(row,Fields(common.items()));values=list(fields['serialized_parameters']);values[:2]=[1.25,2.5]
            changed,report=p.edited_record({'serialized_parameters':values});after=decode(changed,Fields(common.items()))
            self.assertEqual(changed['bits']-row['bits'],128);self.assertFalse(report['bit_length_preserved']);self.assertFalse(report['native_ready'])
            self.assertEqual(after.fields,{**p.fields,'serialized_parameters':tuple(values)});self.assertEqual(p.record,row)
            for invalid in ({'serialized_parameters':values[:-1]},{'origin':(2,3,4)},
                    {'serialized_parameters':[True,*values[1:]]},{'serialized_parameters':[float('nan'),*values[1:]]},
                    {'serialized_parameters':[10]*len(values)}):
                with self.assertRaises(ExchangeError):p.edited_record(invalid)

    def test_geometry_parameter_expressions_block_edits_but_other_source_expressions_stay_inert(self):
        fields=rectangle_fields();fields['parameter_expressions'][0]['text']='PARAMETER_FROM_SOURCE()'
        row,common=envelope(rectangle_payload(fields));payload=decode_rectangle_complete(row,Fields(common.items()))
        self.assertTrue(payload.report['payload_decoded'])
        with self.assertRaises(ExchangeError):payload.edited_record({'serialized_parameters':(2,1,0,2,0,0)})
        self.assertEqual(payload.fields['attributes']['expressions_a'][0]['text'],'SOURCE_EXPRESSION')

    def test_full_profiles_reject_truncation_extra_data_unknown_shapes_and_future_versions(self):
        from fcst_exchange.td_writer import network_packet
        for build,decode,fields in ((rectangle_payload,decode_rectangle_complete,rectangle_fields()),(brick_payload,decode_brick,brick_fields())):
            row,common=envelope(build(fields))
            for size in range(0,len(bytes.fromhex(row['data'])),31):
                with self.assertRaises(ExchangeError):decode({**row,'data':bytes.fromhex(row['data'])[:size].hex()},Fields(common.items()))
            bad=deepcopy(fields);bad['future_required_field']=1
            with self.assertRaises(ExchangeError):build(bad)
            bad=deepcopy(fields);bad['axes']=((1,0,0),)
            with self.assertRaises(ExchangeError):build(bad)
            self.assertTrue(network_packet([build(fields)]).startswith(b'FCSTNEW2'))
        fields=rectangle_fields();fields['attributes']['subdivision'][0]['intervals']=10001
        with self.assertRaises(ExchangeError):rectangle_payload(fields)
        fields=brick_fields();fields['attributes']['advection']['future_mode']=True
        with self.assertRaises(ExchangeError):brick_payload(fields)

    def test_geometry_duplicate_map_entries_references_and_unicode_are_not_flattened(self):
        fields=rectangle_fields();fields['attributes']['name_maps']=((('same','first'),('same','second')),())
        fields['attributes']['references_a']=((1,),(0,))
        row,common=envelope(rectangle_payload(fields),targets=(123,));actual=decode_rectangle_complete(row,Fields(common.items()))
        self.assertEqual(actual.fields['attributes']['name_maps'],fields['attributes']['name_maps'])
        self.assertEqual(actual.fields['attributes']['references_a'][0][0]['target'],123)
        self.assertEqual(actual.fields['attributes']['references_a'][1][0]['target'],0)
        self.assertIn('\u03b1',actual.fields['attributes']['property_label'])

    def test_source_edit_handles_survive_uint64_json_strings_and_reject_rounded_numeric_aliases(self):
        from fcst_exchange.independent_td import IndependentTdAdapter
        from fcst_exchange.dwg_native import NativeRuntime
        from fcst_contracts import loads
        import json
        handle=2**63+111;fields=rectangle_fields();before=drawing([rectangle_payload(fields)],[handle])
        changed=deepcopy(fields);changed['serialized_parameters']=(1.25,*changed['serialized_parameters'][1:])
        after=drawing([rectangle_payload(changed)],[handle]);request=loads(json.dumps([{'handle':str(handle),'changes':{'serialized_parameters':changed['serialized_parameters']}}]))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();raw=b'AC1032-owned';(source/'main.dwg').write_bytes(raw)
            runtime=NativeRuntime(root/'backend.exe','b'*64,PATCH);adapter=IndependentTdAdapter(runtime)
            with patch.object(NativeRuntime,'run',return_value=(before,None,{})):staged=adapter.preview(source,'main.dwg',root/'preview')
            with patch.object(NativeRuntime,'run',side_effect=[(after,b'AC1032-derived',{}),(after,None,{})]):
                report=adapter.export_source(staged,root/'export',request,work=root/'edit')
            self.assertTrue(report['edited_roundtrip_verified']);self.assertEqual((source/'main.dwg').read_bytes(),raw)
            for bad in (float(handle),True,str(2**64),'01','1e2',-1,float('nan')):
                with self.assertRaises(ExchangeError):adapter.export_source(staged,root/'bad',[{'handle':bad,'changes':request[0]['changes']}],work=root/'bad-work')
            with self.assertRaises(ExchangeError):adapter.export_source(staged,root/'duplicate',request*2,work=root/'duplicate-work')

    def test_rectangle_prefix_preserves_unknown_attributes_and_never_claims_thermal_mapping(self):
        row,common=envelope(rectangle());payload=decode_rectangle(row,Fields(common.items()))
        self.assertEqual(payload.fields['serialized_parameters'],(0,1,0,2,0,0));self.assertEqual(payload.fields['origin'],(1,2,3))
        self.assertEqual(payload.record,row);self.assertFalse(payload.report['payload_decoded']);self.assertFalse(payload.report['native_ready'])
        self.assertTrue(payload.report['geometric_envelope_decoded']);self.assertNotIn('owned',str(payload.report))
        self.assertLess(*payload.fields['opaque_data_range']);self.assertLess(*payload.fields['opaque_text_range'])
        with self.assertRaises(ExchangeError):payload.edited_record({'serialized_parameters':(0,2,0,2,0,0)})

    def test_future_version_bad_marker_and_truncated_streams_refuse_geometry_decoding(self):
        record=rectangle();row,common=envelope(record)
        from fcst_exchange.dwg_bits import replace_bits
        raw=bytes.fromhex(row['data'])
        for data in [bytes([raw[0]^64])+raw[1:],replace_bits(raw,66,10,264),raw[:-8]]:
            with self.assertRaises(ExchangeError):decode_rectangle(dict(row,data=data.hex()),Fields(common.items()))

    def test_partial_geometry_inventory_cannot_be_promoted_to_a_native_constant_network(self):
        snap=drawing([rectangle()]);native=deepcopy(snap.native);native['classes'][0].update(cppname='RcRectangle',dxfname='RCRECTANGLE')
        snapshot=NativeSnapshot(native,snap.standard,'');inventory=decode_drawing(snapshot)
        self.assertEqual(inventory.report['decoded_objects'],0);self.assertEqual(inventory.report['partial_objects'],1)
        self.assertEqual(inventory.report['retained_objects'],1)
        result=convert_network(snapshot,SindaUnits('K','J/K','W/K','W','s'),'a'*64)
        self.assertIsNone(result.model);self.assertFalse(result.report['native_ready'])
