# SPDX-License-Identifier: MIT OR Apache-2.0
from pathlib import Path
import tempfile
import os
import subprocess
import sys
import json
import random
import unittest
from fcst_exchange import ExchangeError, Limits, Patch
from fcst_exchange.sinda import SindaAdapter,SindaUnits,scalar,PROFILE

UNITS=SindaUnits('degC','J/K','W/K','W','s')
NETWORK=(b'C public synthetic SINDA 6.3 network\r\n'
         b'HEADER REGISTER DATA\r\n'
         b'  GBASE = 1.0D+0\r\n'
         b'HEADER NODE DATA, MAIN\r\n'
         b'  1,20.,100.\r\n'
         b'  -2,30.,0.\r\n'
         b'HEADER CONDUCTOR DATA, MAIN\r\n'
         b'  1,1,2,GBASE*2\r\n'
         b'HEADER SOURCE DATA, MAIN\r\n'
         b'  1,5.\r\n'
         b'END OF DATA\r\n')


def extend(extra):return NETWORK.replace(b'END OF DATA\r\n',extra+b'END OF DATA\r\n')


class SindaTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        (self.source/'network.inp').write_bytes(NETWORK)
        self.adapter=SindaAdapter(UNITS)
    def stage(self,**kw):return self.adapter.preview(self.source,'network.inp',**kw)

    def test_explicit_units_and_versioned_dialect_are_required(self):
        with self.assertRaisesRegex(ExchangeError,'explicit_sinda_units_required'):SindaAdapter(None)
        with self.assertRaisesRegex(ExchangeError,'sinda_units'):SindaUnits('W','J/K','W/K','W','s')
        self.assertEqual(self.adapter.probe()['profile'],PROFILE)
        self.assertFalse(self.adapter.probe()['vendor_qualified'])

    def test_real_sinda_grammar_maps_static_registers_nodes_conductors_and_loads(self):
        staged=self.stage();self.assertTrue(staged.report['runnable'],staged.report)
        nodes=[e for e in staged.model['entities'] if e['kind']=='node']
        self.assertEqual([e['classification'] for e in nodes],['capacitive','prescribed'])
        self.assertEqual(nodes[0]['temperature'],{'value':293.15,'unit':'K'})
        self.assertEqual(next(e for e in staged.model['entities'] if e['kind']=='conductor')['conductance']['value'],2)
        self.assertEqual(next(e for e in staged.model['entities'] if e['kind']=='load')['power']['value'],5)
        self.assertEqual(b''.join(r.content for r in staged.sources[0].records),NETWORK)
        self.assertFalse(staged.report['qualified'])

    def test_insert_sections_and_vendor_filenames_preserve_original_bytes(self):
        (self.source/'network.inp').write_bytes(b'HEADER NODE DATA, MAIN\nINSERT "thermal nodes (1).inc"\nEND OF DATA\n')
        raw=b'  1,20,100\n  -2,30,0\n'
        (self.source/'thermal nodes (1).inc').write_bytes(raw)
        staged=self.stage();self.assertTrue(staged.report['runnable'],staged.report)
        self.adapter.export(staged,self.root/'copied')
        self.assertEqual((self.root/'copied/thermal nodes (1).inc').read_bytes(),raw)
        self.assertEqual(len(staged.report['dependencies']),2)

    def test_unknown_logic_radiation_tables_and_controls_block_native_readiness(self):
        for extra in (b'HEADER OPERATIONS\n      CALL FWDBCK\n',
                      b'HEADER ARRAY DATA, MAIN\n  1=0.0,1,2,3\n',
                      b'HEADER CONTROL DATA, GLOBAL\n TIMEND=100\n',
                      b'HEADER CONDUCTOR DATA, MAIN\n -3,1,2,1e-8\n'):
            (self.source/'network.inp').write_bytes(extend(extra))
            staged=self.stage();self.assertFalse(staged.report['runnable'])
            self.assertTrue(any(r['status'] in {'retained-opaque','unsupported'} for r in staged.report['records']))
            with self.assertRaisesRegex(ExchangeError,'required_semantics_unresolved'):staged.require_native()

    def test_static_expression_translation_is_bounded_and_never_evaluates_source_code(self):
        self.assertEqual(scalar('2D0 + X/2',{'X':4}),4)
        for text in ('__import__("os").system("bad")','1/0','1e999','2**100','[x for x in []]','unknown+1'):
            with self.assertRaises(ExchangeError):scalar(text,{})
        (self.source/'network.inp').write_bytes(extend(b'HEADER REGISTER DATA\n X=Y+1\n Y=X+1\n'))
        self.assertFalse(self.stage().report['runnable'])

    def test_collisions_missing_references_bad_units_and_invalid_node_capacity_fail(self):
        for extra in (b'HEADER NODE DATA, MAIN\n 1,20,100\n',
                      b'HEADER CONDUCTOR DATA, MAIN\n 2,1,99,1\n',
                      b'HEADER NODE DATA, OTHER\n 1,20,-1\n',
                      b'HEADER NODE DATA, OTHER\n -1,20,3\n'):
            (self.source/'network.inp').write_bytes(extend(extra))
            self.assertFalse(self.stage().report['runnable'])

    def test_safe_controlled_edit_reopens_without_changing_original(self):
        staged=self.stage();record=next(r for r in staged.sources[0].records if r.kind=='CONDUCTOR')
        p=Patch(record.path,record.start,record.end,record.digest,b'  1,1,2,4.0\r\n')
        self.adapter.export(staged,self.root/'edited',[p])
        new=self.adapter.preview(self.root/'edited','network.inp')
        self.assertTrue(new.report['runnable'])
        self.assertEqual(next(e for e in new.model['entities'] if e['kind']=='conductor')['conductance']['value'],4)
        self.assertEqual((self.source/'network.inp').read_bytes(),NETWORK)
        with self.assertRaisesRegex(ExchangeError,'identity_edit'):
            self.adapter.export(staged,self.root/'bad',[Patch(record.path,record.start,record.end,record.digest,b'  2,1,2,4\r\n')])

    def test_malicious_insert_paths_depth_and_file_budgets_fail_closed(self):
        for path in ('../secret.inp','C:/secret.inp','NUL','$(command)','//server/file'):
            (self.source/'network.inp').write_bytes(('INSERT "'+path+'"\n').encode())
            staged=self.stage();self.assertFalse(staged.report['runnable'])
            with self.assertRaises(ExchangeError):self.adapter.export(staged,self.root/'bad')
        (self.source/'network.inp').write_bytes(NETWORK)
        with self.assertRaisesRegex(ExchangeError,'file_limit'):self.stage(limits=Limits(file_bytes=8))

    def test_duplicate_source_ids_across_submodels_and_d_exponents_are_distinct(self):
        raw=extend(b'HEADER NODE DATA, OTHER\n 1,2D1,1D2\nHEADER CONDUCTOR DATA, OTHER\n 1,OTHER.1,MAIN.1,1D0\n')
        (self.source/'network.inp').write_bytes(raw)
        staged=self.stage();self.assertTrue(staged.report['runnable'],staged.report)
        self.assertEqual(len({e['id'] for e in staged.model['entities']}),len(staged.model['entities']))

    def test_complete_reports_cover_malformed_and_future_source_records(self):
        raw=extend(b'HEADER NODE DATA, MAIN\n future,unknown,syntax\nFUTURE EXTRA\xff\n')
        (self.source/'network.inp').write_bytes(raw)
        staged=self.stage();self.assertFalse(staged.report['runnable'])
        self.assertEqual(staged.sources[0].content,raw)
        self.assertEqual(len(staged.report['records']),13)
        self.assertEqual({r['location']['path'] for r in staged.report['records']},{'network.inp'})

    def test_saved_package_preserves_vendor_filenames_in_a_private_alias_map(self):
        from fcst_exchange.source_package import package_sinda
        from fcst_app.persistence import save_package,recover_package
        (self.source/'network.inp').write_bytes(b'HEADER NODE DATA, MAIN\nINSERT "thermal nodes (1).inc"\nEND OF DATA\n')
        raw=b'  1,20,100\n -2,30,0\n';(self.source/'thermal nodes (1).inc').write_bytes(raw)
        package=package_sinda(self.stage());target=self.root/'portable.fcst';save_package(package,target)
        reopened=recover_package(target)
        mapping=json.loads(reopened.files['exchange/source-map.json'])['source_paths']
        self.assertEqual(reopened.files[mapping['thermal nodes (1).inc']],raw)
        self.assertTrue(all(' ' not in name for name in reopened.files))

    def test_sinda_cli_preview_export_package_and_discovery_are_unattended(self):
        root=Path(__file__).resolve().parents[1]
        env=dict(os.environ,PYTHONPATH=str(root/'python'))
        units=['--temperature-unit','degC','--capacity-unit','J/K','--conductance-unit','W/K','--power-unit','W','--time-unit','s']
        def run(command,*extra):
            args=[sys.executable,'-m','fcst_cli',command]
            if command!='td-probe':args += [str(self.source),'network.inp',*units,*map(str,extra)]
            return subprocess.run(args,env=env,capture_output=True,timeout=20)
        self.assertTrue(json.loads(run('sinda-preview').stdout)['runnable'])
        self.assertEqual(run('sinda-export',self.root/'cli-copy').returncode,0)
        self.assertEqual(run('sinda-package',self.root/'cli.fcst').returncode,0)
        self.assertEqual(json.loads(run('td-probe').stdout)['qualified'],False)

    def test_static_and_malformed_sinda_fuzz_never_executes_or_loses_bytes(self):
        rng=random.Random(8008)
        for index in range(120):
            extra=bytes(rng.randrange(256) for _ in range(rng.randrange(300)))
            raw=extend(b'HEADER SUBROUTINE\n'+extra+b'\n')
            (self.source/'network.inp').write_bytes(raw)
            staged=self.stage();self.assertEqual(staged.sources[0].content,raw)
            self.assertFalse(staged.report['qualified'])
        # A quoted dollar sign must not hide an invalid INSERT target as a comment.
        (self.source/'network.inp').write_bytes(extend(b'INSERT "$(command)"\n'))
        self.assertFalse(self.stage().plan('unchanged-export').supported)

    def test_static_gen_nodes_and_conductors_expand_with_full_identity_inventory(self):
        raw=(b'HEADER NODE DATA, MAIN\n GEN 10,3,5,20,100\n -99,30,0\n'
             b'HEADER CONDUCTOR DATA, MAIN\n GEN 1,2,1,10,5,15,5,2\n 3,20,99,2\nEND OF DATA\n')
        (self.source/'network.inp').write_bytes(raw)
        staged=self.stage();self.assertTrue(staged.report['runnable'],staged.report)
        self.assertEqual(len([e for e in staged.model['entities'] if e['kind']=='node']),4)
        self.assertEqual(len([e for e in staged.model['entities'] if e['kind']=='conductor']),3)
        self.assertEqual(len({r['source_id'] for r in staged.report['records']}),len(staged.report['records']))
        (self.source/'network.inp').write_bytes(raw.replace(b'10,3,5',b'10,10000000,5'))
        self.assertFalse(self.stage().report['runnable'])

    def test_insert_repetition_and_section_leakage_are_rejected(self):
        (self.source/'child.inc').write_bytes(b'1,20,100\n')
        (self.source/'network.inp').write_bytes(b'HEADER NODE DATA, MAIN\nINSERT child.inc\nINSERT child.inc\n')
        self.assertFalse(self.stage().report['runnable'])
        (self.source/'child.inc').write_bytes(b'HEADER NODE DATA, OTHER\n1,20,100\n')
        (self.source/'network.inp').write_bytes(b'HEADER NODE DATA, MAIN\nINSERT child.inc\n2,20,100\n')
        self.assertIn('insert_section_transition_requires_review',[x['code'] for x in self.stage().report['diagnostics']])

    def test_end_of_data_and_explicit_submodel_boundaries_cannot_be_bypassed(self):
        (self.source/'network.inp').write_bytes(NETWORK+b'HEADER NODE DATA, EXTRA\n 99,20,100\n')
        staged=self.stage();self.assertFalse(staged.report['runnable'])
        self.assertIn('sinda_data_after_end',[x['code'] for x in staged.report['diagnostics']])
        self.assertEqual(len([e for e in staged.model['entities'] if e['kind']=='node']),2)
        (self.source/'network.inp').write_bytes(NETWORK.replace(b'END OF DATA',b'END   OF  DATA')+b'C trailing comment\n')
        self.assertTrue(self.stage().report['runnable'])
        (self.source/'network.inp').write_bytes(b'HEADER NODE DATA\n 1,20,100\nEND OF DATA\n')
        self.assertFalse(self.stage().report['runnable'])
        (self.source/'child.inc').write_bytes(b'HEADER NODE DATA, MAIN\n 1,20,100\nEND OF DATA\n')
        (self.source/'network.inp').write_bytes(b'INSERT child.inc\nHEADER NODE DATA, OTHER\n 1,20,100\n')
        self.assertFalse(self.stage().report['runnable'])
