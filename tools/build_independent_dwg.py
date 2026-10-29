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
    receipt={'protocol':'fcst-dwg-native/1','backend_profile':profile['runtime'],'executable':'bin/fcst-dwg.exe',
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
    checks={'owned-fixture-read':first.report['objects']>0 and first.report['read_warning_bits']==0,
            'fresh-native-reopen':verdict['structural_roundtrip_verified'],
            'class-identity-and-version-preservation':first.native['classes']==second.native['classes'],
            'vendor-free-runtime':first.report['vendor_runtime_required'] is False and cli_pass,
            'no-false-thermal-qualification':second.report['qualified'] is False and second.report['native_ready'] is False}
    records=[{'id':key,'status':'passed' if value else 'failed'} for key,value in checks.items()]
    report={'schema_version':1,'candidate':revision(),'profile':profile['runtime'],
            'gate':evaluate(profile['required_cases'],records),'cases':records,
            'input_sha256':profile['source_inputs'],'executable_sha256':receipt['executable_sha256'],
            'source_tree_sha256':source_tree_sha,'vendor_runtime_required':False,'qualified':False,
            'scope':'Independent container and owned synthetic DWG only; TD thermal class codecs remain unimplemented'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['gate']));return 0 if report['gate']['status']=='passed' else 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except (OSError,ValueError,subprocess.SubprocessError):
        print(json.dumps({'status':'failed','code':'independent_dwg_build_or_test_failed'}));raise SystemExit(1)
