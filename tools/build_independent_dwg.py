# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build and test the pinned separate open-source DWG executable on Windows.

No vendor software, model corpus or licenses are read. Only bounded synthetic
test summaries may be published; binaries, source archives and raw logs stay local.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from profile_support import ROOT, verified_download, cmake_tools, revision
from dwg_build_support import digest,prepare_source,seal_tree,linked
sys.path.insert(0,str(ROOT/'python'))
from fcst_exchange.dwg_native import NativeRuntime,compare
from fcst_exchange.td_writer import model_records,verify_network
from fcst_exchange.td_decode import decode_drawing
from fcst_exchange.independent_td import IndependentTdAdapter
from fcst_app.persistence import Package,encode,save_package,recover_package
from fcst_exchange.core import target_id
from fcst_tools.gate import evaluate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'.local/dwg-backend')
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--report',type=Path,default=ROOT/'.local/dwg-backend.json')
    args=parser.parse_args()
    if os.name!='nt' or not 1<=args.jobs<=4:raise ValueError('backend_build_platform_or_jobs')
    profile=json.loads((ROOT/'ci/dwg-backend.json').read_bytes());work=args.root.absolute()
    if any(linked(p) for p in (work,*work.parents) if p.exists()):raise ValueError('backend_build_root_link')
    work.mkdir(parents=True,exist_ok=True)
    if any(linked(p) for p in work.rglob('*')):raise ValueError('backend_cached_tree_link')
    environment={key:value for key,value in os.environ.items() if key.upper() not in
                 {'CC','CXX','CFLAGS','CXXFLAGS','LDFLAGS','CPATH','CPLUS_INCLUDE_PATH','C_INCLUDE_PATH',
                  'LIBRARY_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','CMAKE_TOOLCHAIN_FILE','CMAKE_GENERATOR','MAKEFLAGS'}}
    def run(command,log,timeout=1200):
        with (work/log).open('wb') as stream:
            p=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,
                             timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW,env=environment)
        if p.returncode:raise ValueError('backend_build_step_failed')
    archives=work/'downloads';archives.mkdir(exist_ok=True)
    paths={}
    for key in ('source','compiler'):
        item=profile[key];paths[key]=verified_download(item['url'],archives/item['filename'],item['bytes'],item['sha256'])
    patch=ROOT/'adapters/libredwg/preservation.patch'
    if digest(patch)!=profile['runtime']['patch_sha256']:raise ValueError('backend_patch_lock')
    package_runtime=json.loads((ROOT/'python/fcst_exchange/dwg-profile.json').read_bytes())
    if profile['runtime']!=package_runtime:raise ValueError('backend_runtime_profile_drift')
    for name,value in profile['source_inputs'].items():
        if digest(ROOT/name)!=value:raise ValueError('backend_owned_source_changed')
    compiler=work/'compiler';seal=work/'compiler-seal.json'
    if not compiler.exists():
        compiler.mkdir()
        run([str(paths['compiler']),'-y','-o'+str(compiler)],'extract-compiler.log',180)
        seal.write_text(json.dumps(seal_tree(compiler),sort_keys=True),encoding='utf-8')
    if not seal.is_file() or json.loads(seal.read_bytes())!=seal_tree(compiler):raise ValueError('backend_cached_compiler_changed')
    tools=compiler/'w64devkit/bin'
    for name in ('gcc.exe','g++.exe','ninja.exe'):
        if not (tools/name).is_file():raise ValueError('backend_compiler_missing')
    environment['PATH']=str(tools)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32')
    source=work/'source'
    source_tree_sha=prepare_source(paths['source'],source,patch,profile['modified_files'])
    cmake,_=cmake_tools();build=work/'build'
    run([cmake,'-S',str(ROOT/'adapters/libredwg'),'-B',str(build),'-G','Ninja',
         '-DCMAKE_C_COMPILER='+str(tools/'gcc.exe'),'-DCMAKE_CXX_COMPILER='+str(tools/'g++.exe'),
         '-DCMAKE_MAKE_PROGRAM='+str(tools/'ninja.exe'),'-DDWG_SOURCE='+str(source),
         '-DFCST_PATCH_SHA256='+profile['runtime']['patch_sha256'],'-DCMAKE_BUILD_TYPE=Release'],'configure.log',180)
    run([cmake,'--build',str(build),'--parallel',str(args.jobs)],'build.log')
    install=work/'install';(install/'bin').mkdir(parents=True,exist_ok=True)
    shutil.copyfile(build/'fcst-dwg.exe',install/'bin/fcst-dwg.exe')
    license_dir=install/'share/fcst-dwg';license_dir.mkdir(parents=True,exist_ok=True)
    for name in ('LICENSE','README.md','preservation.patch'):
        shutil.copyfile(ROOT/'adapters/libredwg'/name,license_dir/name)
    receipt={'protocol':'fcst-dwg-native/2','backend_profile':profile['runtime'],'executable':'bin/fcst-dwg.exe',
             'executable_sha256':digest(install/'bin/fcst-dwg.exe'),'source_tree_sha256':source_tree_sha,
             'source_inputs':profile['source_inputs'],'license':'GPL-3.0-or-later'}
    receipt_path=install/'backend.json';receipt_path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    runtime=NativeRuntime.from_receipt(receipt_path)
    attempt=work/('test-'+revision()[:12]+'-'+os.urandom(5).hex());attempt.mkdir()
    records=[]
    fixture,_=runtime.run('fixture',None,attempt/'fixture')
    first,derived,_=runtime.run('rewrite',fixture['source.dwg'],attempt/'rewrite')
    second,_,_=runtime.run('inspect',derived,attempt/'reopen')
    verdict=compare(first,second)
    # Exercise the actual CLI and static executable with vendor Python imports
    # forbidden. No source-generated commands or proprietary fixtures are used.
    script="""import importlib.abc,sys
class DenyVendor(importlib.abc.MetaPathFinder):
 def find_spec(self,fullname,path=None,target=None):
  if fullname in {'winreg','clr','fcst_exchange.opentd','fcst_exchange.td_project','fcst_exchange.td_reference'}:
   raise ImportError('vendor modules forbidden')
sys.meta_path.insert(0,DenyVendor())
from fcst_cli.__main__ import main
raise SystemExit(main())
"""
    cli_env=dict(environment,PYTHONPATH=str(ROOT/'python'))
    cli=subprocess.run([sys.executable,'-S','-c',script,'td-export-source',str(attempt/'fixture'),'source.dwg',
                        str(attempt/'export'),'--backend',str(receipt_path),'--work',str(attempt/'cli-preview')],
                       stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       env=cli_env,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    cli_pass=(cli.returncode==0 and (attempt/'export/source.dwg').is_file()
              and (attempt/'export/source.dwg').read_bytes()==fixture['source.dwg'])
    model=json.loads((ROOT/'tests/fixtures/contracts/analytic-seed-native.json').read_bytes())
    model['entities']=[e for e in model['entities'] if e['kind'] in {'submodel','node','conductor','load'}]
    model.update(source_maps=[],mappings=[],attachments=[])
    first_node=next(e for e in model['entities'] if e['kind']=='node')
    first_node.update(classification='algebraic',temperature={'value':1,'unit':'K'},capacity={'value':0,'unit':'J/K'})
    for entity in model['entities']:
        if entity['kind']=='conductor':entity['conductance']['value']=0
        if entity['kind']=='load':entity['power']['value']=0
    data=encode(model);identifier=target_id(('dwg-selftest','model'))
    manifest={'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':model['project_id'],'revision':0,
              'model_artifact_id':identifier,'artifacts':[{'id':identifier,'role':'model',
              'artifact':{'path':'model.json','sha256':sha256(data).hexdigest(),'byte_length':len(data)},'dependencies':[]}]}
    save_package(Package(manifest,{'model.json':data}),attempt/'owned.fcst')
    new_cli=subprocess.run([sys.executable,'-S','-c',script,'td-write-model',str(attempt/'owned.fcst'),
                           str(attempt/'new-model'),'--backend',str(receipt_path),'--work',str(attempt/'new-cli')],
                          stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          env=cli_env,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
    if new_cli.returncode:raise ValueError('backend_new_model_cli_failed')
    adapter=IndependentTdAdapter(runtime)
    staged=adapter.preview(attempt/'new-model','network.dwg',attempt/'new-preview')
    intended,_,_=model_records(model);handles=verify_network(staged.snapshot,intended)
    edits=[]
    for payload in decode_drawing(staged.snapshot).payloads:
        if 'initial_temperature' in payload.fields:
            if payload.fields['initial_temperature']==1:
                edits.append({'handle':payload.record['handle'],'changes':{'initial_temperature':305,'mass_value':8}})
        else:edits.append({'handle':payload.record['handle'],'changes':{'value':.75}})
    edited=adapter.export_source(staged,attempt/'edited-model',edits,work=attempt/'edit-work')
    original_unchanged=all((attempt/'new-model'/name).read_bytes()==raw for name,raw in staged.original.files)
    companions_preserved=all((attempt/'edited-model'/name).read_bytes()==raw for name,raw in staged.original.files if name!='network.dwg')
    def invoke(arguments):
        process=subprocess.run([sys.executable,'-S','-c',script,*map(str,arguments)],stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=cli_env,timeout=240,creationflags=subprocess.CREATE_NO_WINDOW)
        return process.returncode==0
    import_cli=invoke(['td-package',attempt/'new-model','network.dwg',attempt/'imported.fcst',
        '--backend',receipt_path,'--work',attempt/'import-cli','--temperature-unit','K','--capacity-unit','J/K',
        '--conductance-unit','W/K','--power-unit','W','--time-unit','s'])
    if not import_cli:raise ValueError('backend_native_import_cli_failed')
    imported=recover_package(attempt/'imported.fcst');changed=imported.model
    for entity in changed['entities']:
        if entity['kind']=='node' and entity['classification']=='algebraic':entity['temperature']['value']=305
        if entity['kind']=='conductor':entity['conductance']['value']=.75
        if entity['kind']=='load':entity['power']['value']=2.5
    canonical_bytes=encode(changed);manifest=imported.manifest
    model_record=next(r for r in manifest['artifacts'] if r['id']==manifest['model_artifact_id'])
    model_record['artifact'].update(sha256=sha256(canonical_bytes).hexdigest(),byte_length=len(canonical_bytes))
    package_files=dict(imported.files);package_files[model_record['artifact']['path']]=canonical_bytes
    save_package(Package(manifest,package_files),attempt/'changed.fcst')
    native_export=invoke(['td-export-native',attempt/'changed.fcst',attempt/'native-export','--backend',receipt_path,'--work',attempt/'native-export-work'])
    if not native_export:raise ValueError('backend_native_export_cli_failed')
    from fcst_exchange.sinda import SindaUnits
    native_adapter=IndependentTdAdapter(runtime,SindaUnits('K','J/K','W/K','W','s'))
    native_reopened=native_adapter.preview(attempt/'native-export','network.dwg',attempt/'native-roundtrip')
    canonical_equal=native_reopened.require_native()['entities']==changed['entities']
    properties=dict(model);properties['entities']=[
        {'id':target_id(('dwg-selftest','material')),'kind':'material','label':'owned material',
         'density':{'value':1000,'unit':'kg/m3'},'specific_heat':{'value':800,'unit':'J/(kg*K)'},
         'conductivity':{'value':10,'unit':'W/(m*K)'},'valid_temperature':[{'value':150,'unit':'K'},{'value':450,'unit':'K'}]},
        {'id':target_id(('dwg-selftest','optics')),'kind':'optics','label':'owned optics',
         'solar_absorptivity':.2,'ir_emissivity':.8,'specular_fraction':0,'transmissivity':0}]
    properties['source_maps']=[];pbytes=encode(properties);pid=target_id(('dwg-selftest','properties'))
    pm={'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':properties['project_id'],'revision':0,'model_artifact_id':pid,
        'artifacts':[{'id':pid,'role':'model','artifact':{'path':'model.json','sha256':sha256(pbytes).hexdigest(),'byte_length':len(pbytes)},'dependencies':[]}]}
    save_package(Package(pm,{'model.json':pbytes}),attempt/'properties.fcst')
    property_cli=invoke(['td-write-properties',attempt/'properties.fcst',attempt/'property-library']) and invoke(['td-read-properties',attempt/'property-library',attempt/'properties-reopened.fcst'])
    properties_equal=property_cli and recover_package(attempt/'properties-reopened.fcst').model['entities']==recover_package(attempt/'properties.fcst').model['entities']
    original_property_cli=invoke(['td-import-properties',attempt/'property-library','materials.tdp',attempt/'original-materials.fcst',
        '--kind','tdp','--temperature-min','150','--temperature-max','450']) and invoke(['td-import-properties',attempt/'property-library','optics.rco',attempt/'original-optics.fcst','--kind','rco'])
    if original_property_cli:
        original_materials=recover_package(attempt/'original-materials.fcst');original_optics=recover_package(attempt/'original-optics.fcst')
        original_property_cli=(original_materials.model['entities'][0]['density']['value']==1000
            and original_optics.model['entities'][0]['solar_absorptivity']==.2
            and (attempt/'property-library/materials.tdp').read_bytes() in original_materials.files.values())
    if not original_property_cli:raise ValueError('backend_original_property_import_failed')
    changed_properties=original_materials.model;changed_properties['entities'][0]['specific_heat']['value']=850
    changed_bytes=encode(changed_properties);changed_manifest=original_materials.manifest
    changed_record=next(r for r in changed_manifest['artifacts'] if r['id']==changed_manifest['model_artifact_id'])
    changed_record['artifact'].update(sha256=sha256(changed_bytes).hexdigest(),byte_length=len(changed_bytes))
    changed_files=dict(original_materials.files);changed_files[changed_record['artifact']['path']]=changed_bytes
    save_package(Package(changed_manifest,changed_files),attempt/'changed-materials.fcst')
    property_source_edit=invoke(['td-export-property-source',attempt/'changed-materials.fcst',attempt/'property-source-edit'])
    if property_source_edit:
        from fcst_exchange.td_property_model import import_document
        reimported,_=import_document((attempt/'property-source-edit/materials.tdp').read_bytes(),'tdp',[150,450])
        property_source_edit=reimported['entities']==changed_properties['entities']
    held=native_adapter.preview(attempt/'edited-model','network.dwg',attempt/'held-preview')
    from fcst_exchange.td_writer import node_payload,conductor_payload,load_payload,network_packet
    offset_records=[node_payload('MAIN',1,-20,10,'capacitive'),node_payload('MAIN',2,20,0,'prescribed'),
                    conductor_payload('MAIN',1,2,1,2),load_payload(2500,1)]
    offset_created,_=runtime.run('create-network',network_packet(offset_records),attempt/'offset-create')
    (attempt/'offset-source').mkdir();(attempt/'offset-source/network.dwg').write_bytes(offset_created['derived.dwg'])
    offset_adapter=IndependentTdAdapter(runtime,SindaUnits('degC','J/K','W/K','mW','s'))
    offset_staged=offset_adapter.preview(attempt/'offset-source','network.dwg',attempt/'offset-preview');offset_model=offset_staged.require_native()
    for entity in offset_model['entities']:
        if entity['kind']=='node' and entity['classification']=='capacitive':entity['temperature']['value']=258.15
        if entity['kind']=='load':entity['power']['value']=3
    offset_export=offset_adapter.export_native(offset_staged,offset_model,attempt/'offset-export',attempt/'offset-edit')
    offset_reopen=offset_adapter.preview(attempt/'offset-export','network.dwg',attempt/'offset-reopen')
    checks={'owned-fixture-read':first.report['objects']>0 and first.report['read_warning_bits']==0,
            'fresh-native-reopen':verdict['structural_roundtrip_verified'],
            'class-identity-and-version-preservation':first.native['classes']==second.native['classes'],
            'vendor-free-runtime':first.report['vendor_runtime_required'] is False and cli_pass,
            'no-false-thermal-qualification':second.report['qualified'] is False and second.report['native_ready'] is False,
            'source-free-thermal-network-cli':new_cli.returncode==0,
            'new-network-all-fields-and-references':len(handles)==4,
            'compressed-scalar-edit-fresh-reopen':edited['edited_roundtrip_verified'] and len(edited['edits'])==3 and all(not e['bit_length_preserved'] for e in edited['edits']),
            'edited-source-and-companion-preservation':original_unchanged and companions_preserved,
            'native-import-cli-and-portable-source':import_cli,
            'native-edit-export-cli-roundtrip':native_export,
            'canonical-label-and-identity-roundtrip':canonical_equal,
            'native-property-library-cli-roundtrip':properties_equal,
            'unmapped-native-semantics-remain-held':held.report['native_ready'] is False,
            'original-property-document-cli-import':original_property_cli,
            'offset-unit-native-edit-roundtrip':offset_export['canonical_roundtrip_verified'] and offset_reopen.require_native()['entities']==offset_model['entities'],
            'native-property-source-cli-edit':property_source_edit}
    records=[{'id':key,'status':'passed' if value else 'failed'} for key,value in checks.items()]
    report={'schema_version':1,'candidate':revision(),'profile':profile['runtime'],
            'gate':evaluate(profile['required_cases'],records),'cases':records,
            'input_sha256':profile['source_inputs'],'executable_sha256':receipt['executable_sha256'],
            'source_tree_sha256':source_tree_sha,'vendor_runtime_required':False,'qualified':False,
            'scope':'Independent container and closed canonical-network import/portable/edit/export workflow; constant property libraries; complete TD model and target-product qualification pending'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['gate']));return 0 if report['gate']['status']=='passed' else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,subprocess.SubprocessError):
        print(json.dumps({'status':'failed','code':'independent_dwg_build_or_test_failed'}));raise SystemExit(1)
