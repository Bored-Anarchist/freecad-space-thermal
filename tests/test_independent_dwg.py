# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned synthetic decoder fixtures; never copies of restricted TD payloads."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fcst_exchange import ExchangeError
from fcst_exchange.dwg_container import DwgAuditLimits, audit, compare, document


def drawing():
    return {'FILEHEADER':{'version':'AC1032'}, 'HEADER':{'INSUNITS':6},
            'CLASSES':[{'number':500,'cppname':'FcstOwnedFixture','dwg_version':0}],
            'OBJECTS':[{'entity':'UNKNOWN_ENT','type':500,'handle':[0,1,1],
                        'size':20,'bitsize':100,'index':0,'layer':[5,1,2],
                        'num_unknown_bits':9,'unknown_bits':'AA80'},
                       {'object':'LAYER','type':51,'handle':[0,1,2],
                        'material':[5,1,3],'name':'synthetic'}]}


def raw(data):
    return json.dumps(data).encode()


class IndependentDwgTests(unittest.TestCase):
    def test_container_agreement_never_claims_thermal_semantics_or_qualification(self):
        a=drawing(); b=deepcopy(a)
        b['OBJECTS'].reverse(); b['OBJECTS'][1].update(size=25,bitsize=120,index=7)
        report=compare(raw(a),raw(b))
        self.assertTrue(report['decoded_inventory_preserved'])
        self.assertTrue(report['opaque_inventory_equal'])
        self.assertFalse(report['native_ready']); self.assertFalse(report['qualified'])
        self.assertEqual(audit(raw(a))['thermal_mapping'],'not_implemented')

    def test_missing_final_opaque_bits_cannot_pass_even_when_both_decoders_agree(self):
        a=drawing(); a['OBJECTS'][0]['unknown_bits']='AA'
        report=compare(raw(a),raw(a))
        self.assertTrue(report['opaque_inventory_equal'])
        self.assertFalse(report['opaque_bit_lengths_valid'])
        self.assertFalse(report['decoded_inventory_preserved'])
        self.assertEqual(audit(raw(a))['opaque_bit_length_mismatches'],1)

    def test_changes_to_classes_handles_references_materials_headers_or_payloads_fail(self):
        a=drawing()
        for section,field,value in (('class','dwg_version',1),('opaque','unknown_bits','AB80'),
                                    ('opaque','num_unknown_bits',8),('opaque','layer',[5,1,9]),
                                    ('layer','material',[5,1,4]),('layer','name','changed')):
            b=deepcopy(a)
            target=b['CLASSES'][0] if section=='class' else b['OBJECTS'][0 if section=='opaque' else 1]
            target[field]=value
            self.assertFalse(compare(raw(a),raw(b))['decoded_inventory_preserved'],(section,field))
        b=deepcopy(a); b['HEADER']['INSUNITS']=4
        self.assertFalse(compare(raw(a),raw(b))['decoded_inventory_preserved'])
        b=deepcopy(a); b['OBJECTS'].pop()
        self.assertFalse(compare(raw(a),raw(b))['decoded_inventory_preserved'])

    def test_decoder_duplicates_ambiguous_identities_bad_payloads_and_nonfinite_values_reject(self):
        with self.assertRaisesRegex(ExchangeError,'duplicate_key'):
            document(b'{"FILEHEADER":{},"FILEHEADER":{}}')
        for mode in ('class','handle','type','bits','hex','infinite'):
            a=drawing()
            if mode=='class': a['CLASSES'].append(deepcopy(a['CLASSES'][0]))
            elif mode=='handle': a['OBJECTS'].append(deepcopy(a['OBJECTS'][0]))
            elif mode=='type': a['OBJECTS'][0]['type']=501
            elif mode=='bits': a['OBJECTS'][0]['num_unknown_bits']=True
            elif mode=='hex': a['OBJECTS'][0]['unknown_bits']='not hex'
            else: a['OBJECTS'][0]['value']=float('inf')
            with self.assertRaises(ExchangeError,msg=mode):document(raw(a))

    def test_decoder_structure_and_byte_budgets_are_enforced(self):
        for limits in (DwgAuditLimits(bytes=10),DwgAuditLimits(objects=1),
                       DwgAuditLimits(values=5),DwgAuditLimits(depth=1)):
            with self.assertRaises(ExchangeError):document(raw(drawing()),limits=limits)
        for value in (b'[]',b'null',b'{',b'\xff',b'{"x":1e999}'):
            with self.assertRaises(ExchangeError):document(value)

    def test_verdicts_do_not_echo_private_decoder_names_values_or_paths(self):
        a=drawing(); b=deepcopy(a)
        a['CLASSES'][0]['cppname']='private-marker'; b['OBJECTS'][1]['name']='private-marker'
        a['SummaryInfo']={'AUTHOR':'private-marker'}
        text=json.dumps(compare(raw(a),raw(b)))+json.dumps(audit(raw(a)))
        self.assertNotIn('private-marker',text)

    def test_sinda_cli_import_export_and_package_work_with_vendor_imports_forbidden(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source'; source.mkdir()
            (source/'main.inp').write_bytes(b'HEADER NODE DATA, MAIN\n1,293.15,100\n-2,300,0\nHEADER CONDUCTOR DATA, MAIN\n1,1,2,2\nHEADER SOURCE DATA, MAIN\n1,5\nEND OF DATA\n')
            script='''import importlib.abc,sys
class DenyVendor(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'winreg','clr','fcst_exchange.opentd','fcst_exchange.td_project','fcst_exchange.td_reference'}:
   raise ImportError('vendor modules forbidden')
sys.meta_path.insert(0,DenyVendor())
from fcst_cli.__main__ import main
raise SystemExit(main())
'''
            units=['--temperature-unit','K','--capacity-unit','J/K','--conductance-unit','W/K','--power-unit','W','--time-unit','s']
            for command,destination in (('sinda-preview',None),('sinda-export',root/'exported'),('sinda-package',root/'portable.fcst')):
                args=[command,str(source),'main.inp']+([str(destination)] if destination else [])+units
                result=subprocess.run([sys.executable,'-c',script,*args],capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual((root/'exported/main.inp').read_bytes(),(source/'main.inp').read_bytes())
            self.assertTrue((root/'portable.fcst').is_file())
