# SPDX-License-Identifier: MIT OR Apache-2.0
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fcst_exchange import ExchangeError,Limits
from fcst_exchange.td_properties import parse_properties,read_properties
from fcst_exchange.dwg_native import NativeRuntime
from fcst_exchange.independent_td import IndependentTdAdapter
from td_fixture import drawing,PATCH
from test_td_payloads import records

TDP=b'\xef\xbb\xbf[UNICODE]\r\n[START]\r\n[NAME]\r\nOWNED MATERIAL\r\n[TYPE]\r\n0\r\n[CONDUCT]\r\n 12.5D+0 \r\n[DENSITY]\r\n2500\r\n[SPECHEAT]\r\n800\r\n[COMMENT_MULTILINE]\r\n[END] is inert text\r\nprivate-marker\r\n[ENDCOMMENT]\r\n[END]\r\n'
RCO=b'[UNICODE]\n[START]\n[NAME]\nOWNED OPTICS\n[ALPHA]\n0.2\n[EMISS]\n0.8\n[USEVSA]\n0\n[USEVIE]\n0\n[END]\n'


class TdPropertyTests(unittest.TestCase):
    def test_direct_material_and_optical_readers_preserve_original_bytes_and_inert_comments(self):
        for raw,kind in ((TDP,'tdp'),(RCO,'rco')):
            with patch('subprocess.Popen',side_effect=AssertionError('no runtime')):doc=parse_properties(raw,kind)
            self.assertEqual(doc.raw,raw);self.assertEqual(len(doc.entries),1);self.assertFalse(doc.report['qualified'])
            self.assertFalse(doc.report['vendor_runtime_required']);self.assertNotIn('private-marker',json.dumps(doc.report))
        self.assertEqual(parse_properties(TDP,'tdp').entries[0].get('CONDUCT').scalar(),12.5)

    def test_scalar_edits_only_replace_selected_numeric_spans_and_reopen(self):
        doc=parse_properties(TDP,'tdp');raw,receipt=doc.edited([{'entry':'OWNED MATERIAL','field':'CONDUCT','value':20}])
        self.assertEqual(raw,TDP.replace(b'12.5D+0',b'20'));self.assertTrue(receipt['reopen_verified'])
        self.assertEqual(doc.raw,TDP)
        raw,_=parse_properties(RCO,'rco').edited([{'entry':'OWNED OPTICS','field':'ALPHA','value':.5}])
        self.assertEqual(raw,RCO.replace(b'0.2',b'0.5'))

    def test_invalid_ranges_duplicate_requests_variable_modes_and_composites_refuse_edits(self):
        for raw,kind,change in [(TDP,'tdp',{'entry':'OWNED MATERIAL','field':'CONDUCT','value':0}),
                                (RCO,'rco',{'entry':'OWNED OPTICS','field':'ALPHA','value':1.2}),
                                (RCO,'rco',{'entry':'OWNED OPTICS','field':'USEVSA','value':1}),
                                (RCO.replace(b'[USEVSA]\n0',b'[USEVSA]\n1'),'rco',{'entry':'OWNED OPTICS','field':'ALPHA','value':.3}),
                                (TDP.replace(b'[TYPE]\r\n0',b'[TYPE]\r\n2'),'tdp',{'entry':'OWNED MATERIAL','field':'CONDUCT','value':1})]:
            with self.assertRaises(ExchangeError):parse_properties(raw,kind).edited([change])
        doc=parse_properties(TDP,'tdp');change={'entry':'OWNED MATERIAL','field':'DENSITY','value':1000}
        with self.assertRaises(ExchangeError):doc.edited([change,change])
        for value in (True,float('nan'),float('inf'),'source_code()'):
            with self.assertRaises(ExchangeError):doc.edited([{**change,'value':value}])

    def test_future_fields_and_nested_blocks_are_retained_while_malformed_structures_reject(self):
        raw=TDP.replace(b'[END]\r\n',b'[FUTURE]\r\nkeep\r\n[AGGREGATE]\r\n[COMPONENT]\r\n[WEIGHT]\r\n1\r\n[ENDCOMPONENT]\r\n[ENDAGGREGATE]\r\n[END]\r\n')
        doc=parse_properties(raw,'tdp');self.assertEqual(doc.raw,raw);self.assertEqual(doc.report['unknown_root_fields'],1)
        for bad in (TDP[:-7],TDP+b'[END]\r\n',TDP.replace(b'[ENDCOMMENT]',b'[UNKNOWN]'),
                    TDP.replace(b'[DENSITY]',b'[CONDUCT]'),TDP.replace(b'[UNICODE]',b'[ANSI]'),TDP+b'\x00'):
            with self.assertRaises(ExchangeError):parse_properties(bad,'tdp')

    def test_bounded_reads_unsafe_paths_and_encoding_errors_never_start_a_process(self):
        with self.assertRaises(ExchangeError):parse_properties(TDP,'tdp',limits=Limits(file_bytes=10))
        with self.assertRaises(ExchangeError):parse_properties(TDP,'tdp',limits=Limits(line_bytes=8))
        with self.assertRaises(ExchangeError):parse_properties(TDP+b'\xff','tdp')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'owned.tdp').write_bytes(TDP)
            self.assertEqual(read_properties(root,'owned.tdp').raw,TDP)
            with self.assertRaises(ExchangeError):read_properties(root,'../owned.tdp')

    def test_property_only_project_export_needs_no_native_writer_and_keeps_other_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();(source/'main.dwg').write_bytes(b'AC1032-owned')
            (source/'owned.tdp').write_bytes(TDP);runtime=NativeRuntime(root/'converter.exe','b'*64,PATCH)
            adapter=IndependentTdAdapter(runtime)
            with patch.object(NativeRuntime,'run',return_value=(drawing(records()),None,{})):staged=adapter.preview(source,'main.dwg',root/'preview')
            with patch.object(NativeRuntime,'run',side_effect=AssertionError('no writer for text edits')):
                receipt=adapter.export_source(staged,root/'new',[{'path':'owned.tdp','changes':[{'entry':'OWNED MATERIAL','field':'SPECHEAT','value':900}]}],work=root/'work')
            self.assertEqual((root/'new/owned.tdp').read_bytes(),TDP.replace(b'800',b'900'))
            self.assertEqual((root/'new/main.dwg').read_bytes(),b'AC1032-owned');self.assertEqual((source/'owned.tdp').read_bytes(),TDP)
            self.assertFalse(receipt['native_ready']);self.assertTrue(receipt['unrequested_source_files_preserved'])

    def test_one_dimensional_tables_parse_with_explicit_ir_binding_and_bounded_shapes(self):
        raw=TDP.replace(b'[END]\r\n',b'[USEVARSPECHEAT]\r\n1\r\n[VARSPECHEAT]\r\n2\r\n100\r\n700\r\n500\r\n900\r\n[END]\r\n')
        doc=parse_properties(raw,'tdp');table=doc.entries[0].get('VARSPECHEAT').table()
        self.assertEqual(table.points,((100,700),(500,900)));self.assertEqual(doc.report['unknown_root_fields'],0)
        ast=table.as_ast({'op':'literal','quantity':{'value':300,'unit':'K'}},x_unit='K',y_unit='J/(kg*K)',interpolation='linear',extrapolation='error')
        self.assertEqual(ast['y'][1],{'value':900,'unit':'J/(kg*K)'})
        for body in (b'10001\r\n',b'2\r\n100\r\n700\r\n',b'1\r\n100\r\n1E-999\r\n'):
            field=doc.entries[0].get('VARSPECHEAT')
            from dataclasses import replace
            with self.assertRaises(ExchangeError):replace(field,value=body).table()

    def test_table_source_edits_preserve_other_bytes_and_refuse_mode_shape_or_axis_changes(self):
        body=b'2\r\n100\r\n700\r\n500\r\n900\r\n';raw=TDP.replace(b'[END]\r\n',b'[USEVARSPECHEAT]\r\n1\r\n[VARSPECHEAT]\r\n'+body+b'[END]\r\n')
        doc=parse_properties(raw,'tdp');changed,report=doc.edited([{'entry':'OWNED MATERIAL','field':'VARSPECHEAT','points':[[100,750],[500,950]]}])
        self.assertEqual(changed,raw.replace(body,b'2\r\n100\r\n750\r\n500\r\n950\r\n'));self.assertTrue(report['reopen_verified'])
        with self.assertRaises(ExchangeError):doc.edited([{'entry':'OWNED MATERIAL','field':'SPECHEAT','value':900}])
        for points in ([[100,750]],[[500,750],[100,950]],[[100,-1],[500,900]],[[100,float('nan')],[500,900]]):
            with self.assertRaises(ExchangeError):doc.edited([{'entry':'OWNED MATERIAL','field':'VARSPECHEAT','points':points}])
