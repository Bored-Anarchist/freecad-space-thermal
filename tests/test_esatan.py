# SPDX-License-Identifier: MIT OR Apache-2.0
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

from fcst_app.persistence import encode, save_package, recover_package
from fcst_contracts import read
from fcst_exchange import ExchangeError, Limits, Patch, source_package
from fcst_exchange.esatan import EsatanAdapter, EsatanUnits
from fcst_exchange.esatan_native import inspect_native, inspect_project_xml
from fcst_exchange.esatan_syntax import statements
from fcst_exchange.esatan_writer import export_model
from esatan_fixture import NETWORK, UNITS


class EsatanTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.source=self.root/'source'; self.source.mkdir()
        (self.source/'main.d').write_bytes(NETWORK)
        self.adapter=EsatanAdapter(UNITS,source_version='2018-sp1')

    def stage(self,raw=None,**kwargs):
        if raw is not None: (self.source/'main.d').write_bytes(raw)
        return self.adapter.preview(self.source,'main.d',**kwargs)

    def test_constant_network_real_grammar_maps_quantities_and_source_identity(self):
        staged=self.stage(); model=staged.require_native(); self.assertFalse(staged.report['qualified'])
        bykind={e['kind']:e for e in model['entities']}
        self.assertEqual(bykind['conductor']['conductance'],{'value':2,'unit':'W/K'})
        self.assertEqual(bykind['load']['power']['value'],5)
        nodes=[e for e in model['entities'] if e['kind']=='node']
        self.assertEqual([e['temperature']['value'] for e in nodes],[293.15,303.15])
        self.assertEqual(nodes[0]['capacity']['value'],100)
        self.assertEqual(len({r['source_id'] for r in staged.report['records']}),len(staged.report['records']))
        self.assertEqual(b''.join(r.content for r in staged.sources[0].records),NETWORK)
        self.assertEqual(read('model',model),model)

    def test_units_and_release_are_explicit_and_validated(self):
        for units,version in [(None,'2018-sp1'),(UNITS,'future')]:
            with self.assertRaises(ExchangeError): EsatanAdapter(units,source_version=version)
        with self.assertRaises(ExchangeError): EsatanUnits('W','J/K','W/K','W','s')
        self.assertFalse(self.adapter.probe()['vendor_runtime_required'])

    def test_reviewed_d_node_zero_capacity_default_and_inactive_nodes_are_explicit(self):
        staged=self.stage(NETWORK.replace(b'C=100*SCALE',b'C=0'))
        self.assertTrue(staged.report['runnable'])
        self.assertEqual(next(e for e in staged.model['entities'] if e.get('label')=='first; node')['classification'],'algebraic')
        staged=self.stage(NETWORK.replace(b'T=20, C=100*SCALE',b'T=20'))
        self.assertTrue(staged.report['runnable'])
        staged=self.stage(NETWORK.replace(b'D1',b'X1'))
        self.assertFalse(staged.report['runnable'])
        self.assertIn('esatan_inactive_node_retained',[r['code'] for r in staged.report['diagnostics']])

    def test_multiline_unicode_quotes_comments_and_byte_offsets_are_preserved(self):
        raw=NETWORK.replace(b"'first; node'", "'café # node''s'".encode()).replace(b'T=20, C=100*SCALE',b'T=20, # comment\r\n C=100*SCALE')
        staged=self.stage(raw); self.assertTrue(staged.report['runnable'],staged.report['diagnostics'])
        for r in staged.sources[0].records: self.assertEqual(raw[r.start:r.end],r.content)
        self.assertIn("café # node's",[e.get('label') for e in staged.model['entities']])

    def test_nodes_collisions_missing_references_and_invalid_values_fail_closed(self):
        for before,after in [(b'B2',b'D1'),(b'GL(1,2)',b'GL(1,99)'),(b'C=100*SCALE',b'C=-1'),
                             (b'T=20',b'T=-300'),(b'BASE=2D0',b'BASE=1D999'),(b'B2',b'B0')]:
            staged=self.stage(NETWORK.replace(before,after)); self.assertFalse(staged.report['runnable'])
            with self.assertRaises(ExchangeError): staged.require_native()

    def test_unknown_required_node_attributes_logic_arrays_and_radiation_are_not_dropped(self):
        for before,after in [(b'C=100*SCALE',b'C=100*SCALE, A=1'),(b'GL(1,2)',b'GR(1,2)'),
                             (b'QI1=5;',b'CALL SOLVER();'),(b'$INITIAL',b'$ARRAYS')]:
            staged=self.stage(NETWORK.replace(before,after)); self.assertFalse(staged.report['runnable'])
            self.assertTrue(any(r['status']=='unsupported' for r in staged.report['records']))
            with self.assertRaises(ExchangeError): self.adapter.export(staged,self.root/'bad',[Patch('main.d',0,1,'x',b'x')])

    def test_constants_are_bounded_pure_and_cycles_or_executable_text_block(self):
        for value in (b'OTHER',b'BASE',b'__import__("os")',b'1/0',b'2**999'):
            staged=self.stage(NETWORK.replace(b'BASE=2D0',b'BASE='+value)); self.assertFalse(staged.report['runnable'])
        self.assertFalse(self.stage(NETWORK.replace(b'BASE=2D0',b'BASE=2D0; base=3')).report['runnable'])

    def test_nested_submodels_keep_same_numbered_nodes_distinct(self):
        raw=NETWORK.replace(b'$ENDMODEL',b"$MODEL INNER\n$NODES\nD1='nested', T=0, C=1;\n$CONDUCTORS\nGL(1,MAIN.1)=3;\n$ENDMODEL\n$ENDMODEL")
        staged=self.stage(raw); self.assertTrue(staged.report['runnable'],staged.report['diagnostics'])
        nodes=[e['id'] for e in staged.model['entities'] if e['kind']=='node']; self.assertEqual(len(nodes),len(set(nodes)))

    def test_includes_resolve_in_context_and_roundtrip_exact_source_bytes(self):
        self.stage(NETWORK.replace(b"D1 = 'first; node', T=20, C=100*SCALE;",b'$INCLUDE "nodes (1).inc"'))
        (self.source/'nodes (1).inc').write_bytes(b"D1='included', T=20, C=100;\n")
        staged=self.stage(); self.assertTrue(staged.report['runnable'],staged.report['diagnostics'])
        self.adapter.export(staged,self.root/'copy')
        self.assertEqual((self.root/'copy/nodes (1).inc').read_bytes(),(self.source/'nodes (1).inc').read_bytes())

    def test_missing_recursive_traversal_and_reused_includes_block(self):
        for path in ('missing.inc','../outside.inc','C:/outside.inc','NUL','//server/file','$(command)'):
            staged=self.stage(NETWORK.replace(b'$NODES',('$INCLUDE "'+path+'"\n$NODES').encode()))
            self.assertFalse(staged.report['runnable'])
            with self.assertRaises(ExchangeError): self.adapter.export(staged,self.root/'bad')
        staged=self.stage(NETWORK.replace(b'$NODES',b'$INCLUDE "main.d"\n$NODES'))
        self.assertFalse(staged.report['runnable'])
        with self.assertRaises(ExchangeError): self.adapter.export(staged,self.root/'bad')

    def test_links_hardlinks_and_undeclared_siblings_cannot_be_exported(self):
        outside=self.root/'other'; outside.write_bytes(NETWORK)
        (self.source/'main.d').unlink(); os.link(outside,self.source/'main.d')
        with self.assertRaises(ExchangeError): self.stage()
        (self.source/'main.d').unlink(); self.stage(NETWORK)
        (self.source/'extra.dat').write_bytes(b'inert')
        with self.assertRaises(ExchangeError): self.adapter.export(self.stage(),self.root/'bad')

    def test_limits_balance_and_unterminated_syntax_fail_closed(self):
        for limits in (Limits(file_bytes=10),Limits(line_bytes=4),Limits(records=2),Limits(total_bytes=8)):
            with self.assertRaises(ExchangeError): self.stage(limits=limits)
        for raw in (NETWORK.replace(b'$ENDMODEL',b''),NETWORK+b'$ENDMODEL\n',NETWORK.replace(b'GL(1,2)',b'GL(1,2')):
            try: self.assertFalse(self.stage(raw).report['runnable'])
            except ExchangeError: pass

    def test_scalar_edit_reopens_preserves_untouched_bytes_and_original(self):
        staged=self.stage(); r=next(r for r in staged.sources[0].records if r.value['text']=='GL(1,2)=BASE;')
        replacement=r.content.replace(b'BASE',b'4D0')
        receipt=self.adapter.export(staged,self.root/'edited',[Patch(r.path,r.start,r.end,r.digest,replacement)])
        self.assertEqual(receipt['operation'],'controlled-edit')
        output=(self.root/'edited/main.d').read_bytes()
        self.assertEqual(output,NETWORK[:r.start]+replacement+NETWORK[r.end:])
        self.assertEqual((self.source/'main.d').read_bytes(),NETWORK)
        new=self.adapter.preview(self.root/'edited','main.d').require_native()
        self.assertEqual(next(e for e in new['entities'] if e['kind']=='conductor')['conductance']['value'],4)

    def test_patch_identity_injection_stale_sources_and_existing_target_reject(self):
        staged=self.stage(); r=next(r for r in staged.sources[0].records if r.value['text']=='GL(1,2)=BASE;')
        for value in (b'GL(2,1)=2;',b'GL(1,2)=2; QI1=8;',b'$INCLUDE "x"\n'):
            with self.assertRaises(ExchangeError): self.adapter.export(staged,self.root/'bad',[Patch(r.path,r.start,r.end,r.digest,value)])
        self.assertFalse((self.root/'bad').exists())
        self.stage(NETWORK+b'# changed\n')
        with self.assertRaises(ExchangeError): self.adapter.export(staged,self.root/'bad')
        staged=self.stage(NETWORK)
        with self.assertRaises(ExchangeError): self.adapter.export(staged,self.source)

    def test_imported_package_retains_every_original_and_reopens(self):
        staged=self.stage(); package=source_package(staged)
        save_package(package,self.root/'model.fcst'); reopened=recover_package(self.root/'model.fcst')
        self.assertEqual(reopened.files['source/main.d'],NETWORK)
        self.assertEqual(reopened.model,staged.model)

    def test_new_model_writer_roundtrips_quantities_topology_loads_and_labels(self):
        model=self.stage().require_native()
        receipt=export_model(model,UNITS,self.root/'new',source_version='2018-sp1')
        new=self.adapter.preview(self.root/'new','network.d').require_native()
        self.assertTrue(receipt['roundtrip_verified']); self.assertFalse(receipt['qualified'])
        self.assertEqual(sorted(e['temperature']['value'] for e in model['entities'] if e['kind']=='node'),
                         sorted(e['temperature']['value'] for e in new['entities'] if e['kind']=='node'))
        self.assertIn(b"'first; node'",(self.root/'new/network.d').read_bytes())
        self.assertEqual((self.source/'main.d').read_bytes(),NETWORK)

    def test_writer_has_an_independent_literal_and_topology_oracle(self):
        import re
        from decimal import Decimal
        model=self.stage().require_native()
        receipt=export_model(model,UNITS,self.root/'oracle',source_version='2020')
        source=(self.root/'oracle/network.d').read_text(encoding='utf-8')
        # Independently inspect generated literal fields rather than reparsing
        # through the adapter whose output the writer already checks internally.
        matches=re.findall(r"([DBA])(\d+) = '(?:[^']|'')*', T=([^,;]+), C=([^;]+);",source)
        self.assertEqual(len(matches),2)
        self.assertEqual(sorted(Decimal(m[2]) for m in matches),[Decimal(20),Decimal(30)])
        self.assertEqual(sorted(Decimal(m[3]) for m in matches),[Decimal(0),Decimal(100)])
        numbering={r['entity_id']:r['handle'].removeprefix('node.') for r in receipt['identities'] if r['handle'].startswith('node.')}
        conductor=next(e for e in model['entities'] if e['kind']=='conductor')
        left,right,value=re.search(r'GL\(([^,]+),([^\)]+)\)=([^;]+);',source).groups()
        self.assertEqual(left.rsplit('.',1)[-1],numbering[conductor['from_node_id']])
        self.assertEqual(right.rsplit('.',1)[-1],numbering[conductor['to_node_id']])
        self.assertEqual(Decimal(value),Decimal(2))

    def test_initial_line_statements_map_without_running_fortran(self):
        staged=self.stage(NETWORK.replace(b'QI1=5;',b'T1=25\r\nQI1=7'))
        model=staged.require_native()
        self.assertEqual(next(e for e in model['entities'] if e['kind']=='load')['power']['value'],7)
        self.assertEqual(next(e for e in model['entities'] if e.get('label')=='first; node')['temperature']['value'],298.15)
        staged=self.stage(NETWORK.replace(b'QI1=5;',b'CALL UNKNOWN\r\nQI1=5'))
        self.assertFalse(staged.report['runnable'])

    def test_directive_and_initial_comments_do_not_swallow_following_records(self):
        raw=NETWORK.replace(b'$MODEL MAIN',b'$MODEL MAIN # inert comment').replace(b'QI1=5;',b'QI1=5 # inert comment')
        staged=self.stage(raw); self.assertTrue(staged.report['runnable'],staged.report['diagnostics'])
        r=next(r for r in staged.sources[0].records if r.value['text']=='QI1=5')
        replacement=r.content.replace(b'QI1=5',b'QI1=7')
        self.adapter.export(staged,self.root/'comment-edit',[Patch(r.path,r.start,r.end,r.digest,replacement)])
        self.assertIn(b'# inert comment',(self.root/'comment-edit/main.d').read_bytes())
        self.assertEqual(next(e for e in self.adapter.preview(self.root/'comment-edit','main.d').model['entities'] if e['kind']=='load')['power']['value'],7)

    def test_partial_node_mapping_cannot_be_written_as_a_complete_model(self):
        staged=self.stage(NETWORK.replace(b'C=100*SCALE',b'C=100*SCALE,A=1'))
        self.assertFalse(staged.report['runnable']); self.assertIsNotNone(staged.model)
        self.assertEqual(sum(e['kind']=='node' for e in staged.model['entities']),2)
        with self.assertRaisesRegex(ExchangeError,'unresolved_source_semantics'):
            export_model(staged.model,UNITS,self.root/'bad',source_version='2020')

    def test_export_cannot_reinterpret_a_preview_with_different_units_or_version(self):
        staged=self.stage()
        for adapter in (EsatanAdapter(UNITS,source_version='2020'),
                        EsatanAdapter(EsatanUnits('K','J/K','W/K','W','s'),source_version='2018-sp1')):
            with self.assertRaisesRegex(ExchangeError,'profile_mismatch'): adapter.export(staged,self.root/'bad')

    def test_cli_preview_package_edit_and_writer_are_real_commands(self):
        import contextlib
        import io
        from unittest.mock import patch
        from fcst_cli.__main__ import main
        flags=['--source-version','2018-sp1','--temperature-unit','degC','--capacity-unit','J/K',
               '--conductance-unit','W/K','--power-unit','W','--time-unit','s']
        def command(args):
            out=io.StringIO()
            with patch.object(sys,'argv',['fcst',*map(str,args)]),contextlib.redirect_stdout(out): code=main()
            return code,json.loads(out.getvalue())
        code,report=command(['esatan-preview',self.source,'main.d',*flags])
        self.assertEqual(code,0); self.assertTrue(report['runnable']); self.assertNotIn(str(self.root),json.dumps(report))
        code,_=command(['esatan-package',self.source,'main.d',self.root/'cli.fcst',*flags]); self.assertEqual(code,0)
        code,report=command(['esatan-write-model',self.root/'cli.fcst',self.root/'cli-new',*flags])
        self.assertEqual(code,0); self.assertTrue(report['roundtrip_verified'])
        code,_=command(['esatan-export',self.source,'main.d',self.root/'cli-copy',*flags]); self.assertEqual(code,0)
        self.assertEqual((self.root/'cli-copy/main.d').read_bytes(),NETWORK)
        code,report=command(['esatan-export',self.source,'main.d',self.source,*flags])
        self.assertEqual(code,2); self.assertNotIn(str(self.root),json.dumps(report))

    def test_writer_rejects_unmapped_features_and_duplicate_links_or_loads(self):
        model=self.stage().require_native()
        for kind in ('conductor','load'):
            bad=json.loads(encode(model)); e=next(e for e in bad['entities'] if e['kind']==kind)
            bad['entities'].append({**e,'id':'5e335241-1822-48f2-a54f-e8111c82eb44'})
            with self.assertRaises(ExchangeError): export_model(bad,UNITS,self.root/'bad',source_version='2018-sp1')
            self.assertFalse((self.root/'bad').exists())

    def test_native_erg_ere_erk_are_direct_inert_syntax_inventories(self):
        for family,body in [('erg',b'BULK Alloy; Alloy=[2000,800,5]; GEOMETRY Plate; Plate=SHELL_SCS_DISC(rmax=1, bulk=Alloy);'),
                            ('ere',b'BOUNDARY_CONDITION Heater; Heater=TOTAL_AREA_HEAT_LOAD(reference="Plate", value=2);'),
                            ('erk',b'RADIATIVE_CASE Orbit; DEFINE_MISSION(radiative_case=Orbit, planet_radius=1);')]:
            raw=b'BEGIN_MODEL MODEL\n/* inert ; */\n'+body+b'\nEND_MODEL\n'
            doc=inspect_native(raw,family=family,source_version='2020')
            self.assertTrue(doc.inventory['syntax_complete'],doc.inventory['diagnostics'])
            self.assertFalse(doc.inventory['runnable']); self.assertFalse(doc.inventory['qualified'])
            self.assertEqual(b''.join(r.content for r in doc.records),raw)
            changed=doc.inventory; changed['runnable']=True; self.assertFalse(doc.inventory['runnable'])

    def test_native_unknown_symbols_expressions_and_future_syntax_remain_explicit(self):
        raw=b'BEGIN_MODEL MODEL\nREAL X; X=TAN(30); FUTURE THING;\nEND_MODEL\n'
        doc=inspect_native(raw,family='erg',source_version='2020')
        self.assertFalse(doc.inventory['syntax_complete'])
        self.assertIn('unresolved_expression',json.dumps(doc.inventory))
        self.assertFalse(doc.inventory['runnable'])

    def test_xml_dtd_entities_xinclude_processing_instructions_and_lfs_are_rejected(self):
        for raw in (b'<!DOCTYPE model [<!ENTITY x SYSTEM "file:///invalid">]><model>&x;</model>',
                    b'<?xml version="1.0"?><!DOCTYPE model><model/>',
                    b'<model xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="invalid"/></model>',
                    b'<?execute invalid?><model/>',b'version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n'):
            with self.assertRaises(ExchangeError): inspect_project_xml(raw)
        result=inspect_project_xml(b'<?xml version="1.0"?><model><case/></model>')
        self.assertEqual(result['elements'],2); self.assertFalse(result['runnable'])
        with self.assertRaises(ExchangeError): inspect_project_xml(b'<x>'*40+b'</x>'*40)

    def test_bounded_parser_fuzzing_never_executes_or_loses_original_bytes(self):
        randomizer=random.Random(910)
        for _ in range(200):
            raw=bytes(randomizer.randrange(256) for _ in range(randomizer.randrange(256)))
            try:
                records=statements('fuzz.d',raw)
                self.assertEqual(b''.join(r.content for r in records),raw)
            except ExchangeError: pass

    def test_fresh_process_import_edit_new_export_reopen_without_vendor_calls(self):
        script=Path(__file__).with_name('esatan_offline_peer.py')
        result=subprocess.run([sys.executable,str(script),str(self.source),str(self.root/'peer')],capture_output=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
        self.assertEqual(json.loads(result.stdout),{'status':'passed','vendor_calls':0})


if __name__=='__main__': unittest.main()
