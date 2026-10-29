# SPDX-License-Identifier: MIT OR Apache-2.0
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from fcst_app.persistence import Package, encode, save_package
from fcst_exchange import ExchangeError, Limits
from fcst_exchange.sinda import SindaAdapter, SindaUnits
from fcst_exchange.sinda_writer import export_model, render

ROOT=Path(__file__).resolve().parents[1]
SI=SindaUnits('K','J/K','W/K','W','s')


def model():
    value=json.loads((ROOT/'tests/fixtures/contracts/analytic-seed-native.json').read_bytes())
    value['entities']=[e for e in value['entities'] if e['kind'] in {'submodel','node','conductor','load'}]
    value.update(source_maps=[],mappings=[],attachments=[])
    return value


class SindaWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_source_free_native_network_exports_and_independently_reopens_without_processes(self):
        original=model();before=deepcopy(original)
        with patch('subprocess.Popen',side_effect=AssertionError('no process allowed')):
            receipt=export_model(original,SI,self.root/'new')
        self.assertTrue(receipt['roundtrip_verified']);self.assertFalse(receipt['vendor_runtime_required'])
        self.assertFalse(receipt['qualified']);self.assertEqual(original,before)
        staged=SindaAdapter(SI).preview(self.root/'new','network.sin')
        self.assertTrue(staged.report['runnable']);self.assertEqual(len(staged.model['entities']),len(original['entities']))
        self.assertEqual(len(receipt['identities']),len(original['entities']))
        self.assertIn(b'F000002.1',(self.root/'new/network.sin').read_bytes())

    def test_target_units_preserve_temperatures_capacities_loads_and_boundary_classification(self):
        units=SindaUnits('degC','J/K','W/K','W','min')
        receipt=export_model(model(),units,self.root/'converted')
        staged=SindaAdapter(units).preview(self.root/'converted','network.sin')
        nodes=[e for e in staged.model['entities'] if e['kind']=='node']
        self.assertEqual([e['classification'] for e in nodes],['capacitive','prescribed'])
        self.assertEqual([e['temperature']['value'] for e in nodes],[300,300])
        self.assertTrue(receipt['roundtrip_verified'])

    def test_unknown_entity_fields_associations_and_ambiguous_multiple_loads_reject(self):
        source=model();extra=json.loads((ROOT/'tests/fixtures/contracts/analytic-seed-native.json').read_bytes())
        variants=[]
        a=deepcopy(source);a['entities'].append(next(e for e in extra['entities'] if e['kind']=='frame'));variants.append(a)
        a=deepcopy(source);a['entities'][0]['parent_id']=a['entities'][1]['id'];variants.append(a)
        a=deepcopy(source);load=deepcopy(next(e for e in a['entities'] if e['kind']=='load'));load['id']='00000000-0000-4000-8000-000000000099';a['entities'].append(load);variants.append(a)
        for index,a in enumerate(variants):
            with self.assertRaises(ExchangeError):export_model(a,SI,self.root/str(index))
            self.assertFalse((self.root/str(index)).exists())

    def test_limits_invalid_units_existing_targets_and_precision_loss_fail_before_publication(self):
        target=self.root/'existing';target.mkdir();(target/'keep.txt').write_text('unchanged')
        with self.assertRaises(ExchangeError):export_model(model(),SI,target)
        self.assertEqual((target/'keep.txt').read_text(),'unchanged')
        for units,limits in ((None,Limits()),(SI,Limits(file_bytes=10)),(SI,Limits(records=1))):
            with self.assertRaises(ExchangeError):export_model(model(),units,self.root/'failed',limits=limits)
            self.assertFalse((self.root/'failed').exists())
        a=model();next(e for e in a['entities'] if e['kind']=='node')['temperature']={'value':1e-20,'unit':'K'}
        with self.assertRaisesRegex(ExchangeError,'reopen_quantity'):
            export_model(a,SindaUnits('degC','J/K','W/K','W','s'),self.root/'lossy')
        self.assertFalse((self.root/'lossy').exists())

    def test_labels_are_inert_escaped_annotations_and_entity_order_is_deterministic(self):
        a=model();a['entities'][2]['label']='named\nHEADER OPERATIONS\n CALL source_code()'
        first,identity=render(a,SI);a['entities'].reverse();second,other=render(a,SI)
        self.assertEqual(first,second);self.assertEqual(identity,other)
        self.assertIn(b'\\nHEADER OPERATIONS',first)
        self.assertNotIn(b'\nHEADER OPERATIONS\n',first)
        export_model(a,SI,self.root/'annotated')
        self.assertTrue(SindaAdapter(SI).preview(self.root/'annotated','network.sin').report['runnable'])

    def test_failed_reopen_does_not_publish_a_partial_tree(self):
        with patch('fcst_exchange.sinda_writer._check_roundtrip',side_effect=ExchangeError('synthetic_reopen_failure')):
            with self.assertRaisesRegex(ExchangeError,'synthetic_reopen_failure'):
                export_model(model(),SI,self.root/'not-published')
        self.assertFalse((self.root/'not-published').exists())
        self.assertFalse(list(self.root.glob('.fcst-sinda-*')))

    def test_cli_exports_native_package_with_vendor_and_site_imports_absent(self):
        from fcst_exchange.core import target_id
        from hashlib import sha256
        native=model();data=encode(native);identifier=target_id(('writer','model'))
        manifest={'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':native['project_id'],'revision':0,
                  'model_artifact_id':identifier,'artifacts':[{'id':identifier,'role':'model',
                  'artifact':{'path':'model.json','sha256':sha256(data).hexdigest(),'byte_length':len(data)},'dependencies':[]}]}
        save_package(Package(manifest,{'model.json':data}),self.root/'native.fcst')
        script='''import importlib.abc,sys
class DenyVendor(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'winreg','clr','fcst_exchange.opentd','fcst_exchange.td_project'}:
   raise ImportError('vendor forbidden')
sys.meta_path.insert(0,DenyVendor())
from fcst_cli.__main__ import main
raise SystemExit(main())
'''
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'))
        args=['sinda-write-model',str(self.root/'native.fcst'),str(self.root/'exported'),
              '--temperature-unit','K','--capacity-unit','J/K','--conductance-unit','W/K','--power-unit','W','--time-unit','s']
        result=subprocess.run([sys.executable,'-S','-c',script,*args],env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertTrue(json.loads(result.stdout)['roundtrip_verified'])
