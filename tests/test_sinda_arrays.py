# SPDX-License-Identifier: MIT OR Apache-2.0
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from fcst_exchange import ExchangeError,Limits
from fcst_exchange.sinda import SindaAdapter,SindaUnits,scalar,parse
from fcst_exchange.sinda_arrays import parse_arrays,table_ast
from fcst_exchange.core import Source
from fcst_exchange.export import Patch
from test_sinda import NETWORK,extend

SI=SindaUnits('K','J/K','W/K','W','s')


def arrays(raw,registers=None,limits=Limits()):
    records=parse('owned.sin',raw,limits);return parse_arrays((Source('owned.sin',raw,records),),registers or {},limits=limits)


class SindaArrayTests(unittest.TestCase):
    def test_numbered_arrays_continue_across_lines_and_keep_storage_kind_and_submodel(self):
        raw=b'HEADER ARRAY DATA, A\n  7=1.0,2.0,\n   3.0,4.0\n  8=1,2,3\nHEADER ARRAY DATA, B\n  7=5,6\n'
        actual,records,errors=arrays(raw);self.assertFalse(errors);self.assertEqual(actual['A',7].values,(1,2,3,4))
        self.assertEqual(actual['A',7].storage,'real');self.assertEqual(actual['A',8].storage,'integer')
        self.assertEqual(actual['B',7].values,(5,6));self.assertEqual(len(records),4)

    def test_static_registers_space_and_allsame_are_bounded_and_do_not_execute(self):
        with patch('subprocess.Popen',side_effect=AssertionError('no execution')):
            actual,_,errors=arrays(b'HEADER ARRAY DATA, A\n  1=SPACE,2,ALLSAME,3,X+1\n',{'X':2})
        self.assertFalse(errors);self.assertEqual(actual['A',1].values,(0,0,3,3,3));self.assertEqual(actual['A',1].storage,'real')
        for body in [b'1=ALLSAME,1000000,0',b'1=SPACE,-1',b'1=SPACE,1.5',b'1=ALLSAME,3',b'1=__import__("os")']:
            _,_,errors=arrays(b'HEADER ARRAY DATA, A\n '+body+b'\n');self.assertTrue(errors)

    def test_mixed_storage_duplicate_ids_orphans_future_syntax_and_budgets_block(self):
        for body in [b'1=1.0,2',b'1=1,2\n 1=3,4',b'1,2,3 END',b'1=1,,2',b'0=1',b'1=2147483648']:
            _,_,errors=arrays(b'HEADER ARRAY DATA, A\n '+body+b'\n');self.assertTrue(errors)
        _,_,errors=arrays(b'HEADER ARRAY DATA, A\n 1=1,2,3,4\n',limits=Limits(records=3));self.assertTrue(errors)

    def test_unreferenced_static_arrays_preserve_bytes_and_allow_constant_network_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();raw=extend(b'HEADER ARRAY DATA, MAIN\n 1=0.0,1.0,2.0,3.0\n')
            (source/'owned.sin').write_bytes(raw);adapter=SindaAdapter(SI);staged=adapter.preview(source,'owned.sin')
            self.assertTrue(staged.report['runnable'],staged.report);self.assertEqual(staged.report['static_arrays'][0]['values'],4)
            adapter.export(staged,root/'export');self.assertEqual((root/'export/owned.sin').read_bytes(),raw)

    def test_array_consumers_and_untranslated_control_logic_still_block_native(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=extend(b'HEADER ARRAY DATA, MAIN\n 1=0.0,1.0,2.0,3.0\nHEADER OPERATIONS\n CALL SOME_ROUTINE(A1)\n')
            (root/'owned.sin').write_bytes(raw);staged=SindaAdapter(SI).preview(root,'owned.sin')
            self.assertFalse(staged.report['runnable']);self.assertFalse(staged.report['qualified'])

    def test_explicit_table_binding_has_units_interpolation_extrapolation_and_discontinuities(self):
        actual,_,_=arrays(b'HEADER ARRAY DATA, MAIN\n 1=0.0,2.0,10.0,4.0\n');a=actual['MAIN',1]
        table=table_ast(a,{'op':'literal','quantity':{'value':5,'unit':'s'}},x_unit='s',y_unit='W',interpolation='linear',extrapolation='error')
        self.assertEqual([q['value'] for q in table['x']],[0,10]);self.assertEqual([q['value'] for q in table['y']],[2,4])
        with self.assertRaises(ExchangeError):table_ast(a,table['input'],x_unit='s',y_unit='W',interpolation='linear',extrapolation='error',discontinuities=(1,))
        with self.assertRaises(ExchangeError):table_ast(a,table['input'],x_unit='unknown',y_unit='W',interpolation='linear',extrapolation='error')

    def test_array_preservation_edits_reopen_and_refuse_shape_storage_or_identity_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();(source/'owned.sin').write_bytes(extend(b'HEADER ARRAY DATA, MAIN\n 7=1.0,2.0\n'))
            adapter=SindaAdapter(SI);staged=adapter.preview(source,'owned.sin');r=next(r for s in staged.sources for r in s.records if r.kind=='ARRAY')
            patch_value=Patch(r.path,r.start,r.end,r.digest,b' 7=3.0,4.0\n');adapter.export(staged,root/'export',[patch_value])
            self.assertTrue(SindaAdapter(SI).preview(root/'export','owned.sin').report['runnable'])
            for replacement in (b' 8=3.0,4.0\n',b' 7=3.0\n',b' 7=3,4\n'):
                with self.assertRaises(ExchangeError):adapter.validate_patch(r,replacement,Limits())

    def test_reviewed_intrinsics_and_small_integer_powers_are_static_and_bounded(self):
        self.assertEqual(scalar('MAX(2, SQRT(16)) + 2**3',{}),12)
        self.assertEqual(scalar('SIN(0)+COS(0)+LOG(EXP(1))',{}),2)
        for text in ['2**100','2**0.5','SQRT(-1)','EXP(10000)','ABS(1,2)','A.B(1)','SUM([1,2])']:
            with self.assertRaises(ExchangeError):scalar(text,{})
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=NETWORK.replace(b'20,100',b'MAX(20,10),SQRT(10000)')
            (root/'owned.sin').write_bytes(raw);self.assertTrue(SindaAdapter(SI).preview(root,'owned.sin').report['runnable'])

    def test_source_numeric_literals_register_names_and_function_shadowing_are_unambiguous(self):
        self.assertEqual(scalar('X1D3+1D0',{'X1D3':2}),3)
        self.assertEqual(scalar('2**N',{'N':3}),8)
        for text in ['1E-999','1D-999','0x10','1_000']:
            with self.assertRaises(ExchangeError):scalar(text,{})
        with self.assertRaises(ExchangeError):scalar('ABS(2)',{'ABS':3})
        with self.assertRaises(ExchangeError):scalar('X',{'X':True})
        row=parse('owned.sin',b'HEADER NODE DATA, MAIN\n MAX(1,2),300,10\n')[1]
        with self.assertRaisesRegex(ExchangeError,'identity_edit'):
            SindaAdapter(SI).validate_patch(row,b' MAX(1,3),300,10\n',Limits())
