# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pinned OpenTD 6.3 sidecar, discovery-only probes and guarded source operations."""
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from fcst_contracts import ContractError, loads, read
from fcst_app.persistence import encode,is_link,Package
from fcst_app.process_limits import WorkerLimits
from .core import ExchangeError, reject, target_id
from .tools import bounded_tree
from .vendor_paths import path_name,checked_path

PROFILE='opentd-6.3/1'
ASSEMBLY_SHA256='9c63befc118c3be5c4d518e7f458827b28fce8b4b0e60e06aa6821e8e3b72e5b'
EDIT_FIELDS={'Node':{'InitialTemp','MassVol'},'Conductor':{'Value'},'HeatLoad':{'Value'},
             'Rectangle':{'XMax','YMax','TopThickness','BotThickness'},'ThermoProps':{'Density','SpecificHeat','Conductivity'},
             'OpticalProps':{'Alph','Emis'}}


@dataclass(frozen=True)
class TdLimits:
    files:int=2048
    file_bytes:int=67108864
    total_bytes:int=268435456
    include_depth:int=32
    timeout_seconds:float=180
    log_bytes:int=1048576
    memory_mb:int=4096

    def __post_init__(self):
        if (any(type(getattr(self,k)) is not int or getattr(self,k)<=0 for k in ('files','file_bytes','total_bytes','include_depth','log_bytes','memory_mb'))
                or not math.isfinite(self.timeout_seconds) or not 0<self.timeout_seconds<=1800 or self.memory_mb>16384):reject('td_limits')


@dataclass(frozen=True)
class Runtime:
    assembly:Path|None=None
    compiler:Path|None=None
    host:Path|None=None
    sinda:Path|None=None
    profile:str=PROFILE

    def probe(self):
        blockers=[]
        if self.profile!=PROFILE:blockers.append('unsupported_version_profile')
        def installed(path):
            return path is not None and path.is_absolute() and path.is_file() and not any(is_link(p) for p in (path,*path.parents))
        api=installed(self.assembly)
        if not api:blockers.append('opentd_assembly_missing')
        elif sha256(self.assembly.read_bytes()).hexdigest()!=ASSEMBLY_SHA256:blockers.append('opentd_assembly_hash_mismatch')
        compiler=installed(self.compiler)
        if not compiler:blockers.append('framework_compiler_missing')
        host=installed(self.host)
        if not host:blockers.append('licensed_autocad_host_missing')
        sinda=installed(self.sinda)
        if not sinda:blockers.append('sinda_runtime_missing')
        return {'profile':self.profile,'api_available':api and 'opentd_assembly_hash_mismatch' not in blockers,
                'compiler_available':compiler,'host_installed':host,'sinda_installed':sinda,
                'available':not blockers,'license_verified':False,'qualified':False,
                'target_framework':'.NETFramework,Version=v4.6','blockers':blockers}


def discover_runtime():
    """Read installation locations only. No process, key/license read or connection."""
    if os.name!='nt':return Runtime()
    import winreg
    windows=Path(os.environ.get('WINDIR','C:/Windows'))
    assemblies=list((windows/'Microsoft.NET/assembly/GAC_MSIL/OpenTDv63').glob('*/*.dll'))
    assemblies=[p for p in assemblies if p.name=='OpenTDv63.dll']
    compiler=windows/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    host=None;sinda=None
    for hive in (winreg.HKEY_LOCAL_MACHINE,winreg.HKEY_CURRENT_USER):
        for flag in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\acad.exe',0,winreg.KEY_READ|flag) as key:
                    path=Path(winreg.QueryValueEx(key,None)[0].strip('"'))
                    if path.is_file():host=path
            except OSError:pass
            try:
                with winreg.OpenKey(hive,r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',0,winreg.KEY_READ|flag) as root:
                    for index in range(winreg.QueryInfoKey(root)[0]):
                        with winreg.OpenKey(root,winreg.EnumKey(root,index)) as key:
                            try:
                                name=winreg.QueryValueEx(key,'DisplayName')[0]
                                if 'SINDA' not in name.upper():continue
                                location=Path(winreg.QueryValueEx(key,'InstallLocation')[0])
                                candidates=[location/'sinda.exe',location/'bin/sinda.exe']
                                sinda=next((p for p in candidates if p.is_file()),sinda)
                            except OSError:pass
            except OSError:pass
    return Runtime(assemblies[0] if len(assemblies)==1 else None,compiler if compiler.is_file() else None,host,sinda)


def build_sidecar(runtime,source,output):
    if runtime.profile!=PROFILE:reject('unsupported_version_profile')
    probe=runtime.probe()
    if not probe['api_available'] or not probe['compiler_available']:reject('sidecar_build_prerequisite')
    source=Path(source).absolute();output=Path(output).absolute()
    if not source.is_file() or any(is_link(p) for p in (source,*source.parents)):reject('sidecar_source')
    output.parent.mkdir(parents=True,exist_ok=True)
    inputs={'profile':PROFILE,'source_sha256':sha256(source.read_bytes()).hexdigest(),
            'assembly_sha256':ASSEMBLY_SHA256,'compiler_sha256':sha256(runtime.compiler.read_bytes()).hexdigest(),
            'arguments_profile':'framework-x64-optimize-nodebug-v1'}
    seal=output.with_suffix('.build.json')
    if output.is_file() and seal.is_file():
        try:
            previous=json.loads(seal.read_bytes())
            if all(previous.get(k)==v for k,v in inputs.items()) and previous.get('sidecar_sha256')==sha256(output.read_bytes()).hexdigest():return previous
        except (ValueError,OSError):pass
    result=subprocess.run([str(runtime.compiler),'/nologo','/platform:x64','/optimize+','/debug-',
                           '/r:System.Web.Extensions.dll','/r:'+str(runtime.assembly),'/out:'+str(output),str(source)],
                          cwd=output.parent,capture_output=True,timeout=90)
    # Raw compiler text is local only; it may contain account paths.
    output.with_suffix('.build.log').write_bytes(result.stdout+result.stderr)
    if result.returncode or not output.is_file():reject('sidecar_build_failed')
    receipt={**inputs,'sidecar_sha256':sha256(output.read_bytes()).hexdigest(),'qualified':False}
    seal.write_bytes(encode(receipt))
    return receipt


@dataclass(frozen=True)
class HostAuthorization:
    decision_id:str
    candidate_sha256:str
    source_sha256:str
    source_open_policy_sha256:str
    fixture_kind:str

    def validate(self,source_bytes,candidate_hash,creating=False):
        digests=(self.candidate_sha256,self.source_sha256,self.source_open_policy_sha256)
        if (not self.decision_id or any(not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v) for v in digests)
                or self.candidate_sha256!=candidate_hash or self.source_sha256!=source_bytes):reject('td_authorization')
        if self.fixture_kind not in ({'fcst-synthetic-reference/1'} if creating else {'reviewed-source-copy/1'}):reject('td_source_execution_not_reviewed')


def run_sidecar(runtime,sidecar,root,request,*,authorization=None,limits=TdLimits()):
    """Run only a fixed sidecar protocol inside a fresh caller-owned job directory.

    The caller has staged copied source files in root; no original path may be
    supplied as the drawing. The sidecar always starts a new hidden TD instance.
    """
    if os.name!='nt':reject('unsupported_tool_platform')
    if runtime.profile!=PROFILE:reject('unsupported_version_profile')
    probe=runtime.probe();sidecar=Path(sidecar).absolute();root=Path(root).absolute()
    if not sidecar.is_file() or any(is_link(p) for p in (sidecar,*sidecar.parents)):reject('sidecar_missing')
    if not root.is_dir() or any(is_link(p) for p in (root,*root.parents)):reject('unsafe_job_root')
    if not isinstance(request,dict) or request.get('profile')!=PROFILE:reject('td_profile')
    operation=request.get('operation')
    if operation not in {'probe','api-smoke','inspect','edit','create-reference','run-reference'}:reject('unsupported_operation')
    host_operation=operation not in {'probe','api-smoke'}
    payload=dict(request)
    if host_operation:
        if not probe['available']:reject('licensed_runtime_prerequisite')
        if not isinstance(authorization,HostAuthorization):reject('td_authorization')
        drawing=path_name(payload.get('drawing'))
        actual=checked_path(root,drawing)
        creating=operation in {'create-reference','run-reference'}
        if creating:
            if actual.exists():reject('reference_requires_new_drawing')
            source_hash=sha256(b'fcst-synthetic-reference/1').hexdigest()
        else:
            if not actual.is_file():reject('drawing_missing')
            source_hash=sha256(actual.read_bytes()).hexdigest()
        authorization.validate(source_hash,sha256(sidecar.read_bytes()).hexdigest(),creating)
        if operation=='edit':validate_edits(payload.get('edits'))
        payload.update(root=str(root),host=str(runtime.host),authorization_sha256=sha256(authorization.decision_id.encode()).hexdigest())
    elif set(payload)!={'profile','operation'}:reject('td_request_fields')
    if not probe['api_available']:reject('opentd_assembly_prerequisite')
    control=root/'fcst-control'
    if control.exists():reject('job_already_used')
    control.mkdir();input_path=control/'request.json';output_path=control/'response.json'
    input_path.write_bytes(encode(payload))
    environment={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','USERPROFILE','LOCALAPPDATA','APPDATA','PROGRAMDATA'}}
    temp=control/'tmp';temp.mkdir()
    environment.update(TEMP=str(temp),TMP=str(temp),PATH=str(sidecar.parent)+os.pathsep+str(Path(os.environ.get('WINDIR','C:/Windows'))/'System32'))
    process=subprocess.Popen([str(sidecar),str(input_path),str(output_path)],cwd=root,env=environment,stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=0x4|subprocess.CREATE_NO_WINDOW)
    containment=None;readers=[];counts=[0];lock=threading.Lock();overflow=threading.Event()
    def drain(pipe,file):
        with file.open('wb') as stream:
            while chunk:=pipe.read(4096):
                with lock:
                    counts[0]+=len(chunk)
                    if counts[0]>limits.log_bytes:overflow.set()
                if not overflow.is_set():stream.write(chunk)
    error=None
    try:
        containment=WorkerLimits(process,limits.memory_mb)
        for pipe,name in ((process.stdout,'stdout.log'),(process.stderr,'stderr.log')):
            reader=threading.Thread(target=drain,args=(pipe,control/name),daemon=True);reader.start();readers.append(reader)
        deadline=time.monotonic()+limits.timeout_seconds
        while process.poll() is None:
            if overflow.is_set():error='sidecar_log_limit';break
            if not bounded_tree(root,limits):error='sidecar_tree_limit';break
            if time.monotonic()>=deadline:error='sidecar_timeout';break
            time.sleep(.02)
        if error:containment.close()
        process.wait(timeout=10)
    finally:
        if containment:containment.close()
        if process.poll() is None:process.kill();process.wait(timeout=10)
        for reader in readers:reader.join(timeout=5)
        process.stdout.close();process.stderr.close()
    if error:reject(error)
    if overflow.is_set():reject('sidecar_log_limit')
    if process.returncode or not output_path.is_file():reject('sidecar_operation_failed')
    if not bounded_tree(root,limits):reject('sidecar_tree_limit')
    if output_path.stat().st_size>1048576:reject('sidecar_response_limit')
    try:response=loads(output_path.read_bytes())
    except ContractError:reject('sidecar_response_contract')
    api=response.get('api',response)
    if (response.get('profile')!=PROFILE or api.get('assembly_sha256')!=ASSEMBLY_SHA256 or api.get('assembly_version')!='6.3.0.0'
            or api.get('target_framework')!='.NETFramework,Version=v4.6' or api.get('qualified') is not False):reject('sidecar_version_or_identity')
    return response,{'profile':PROFILE,'operation':operation,'execution_mode':'reference_external','qualified':False,
                     'sidecar_sha256':sha256(sidecar.read_bytes()).hexdigest(),'response_sha256':sha256(output_path.read_bytes()).hexdigest(),
                     'assembly_sha256':ASSEMBLY_SHA256,'authorization_sha256':payload.get('authorization_sha256')}


def validate_edits(edits):
    if not isinstance(edits,list) or not 0<len(edits)<=1000:reject('td_edit_limit')
    seen=set()
    for edit in edits:
        if not isinstance(edit,dict) or set(edit)!={'kind','handle','field','value'}:reject('td_edit_fields')
        kind,handle,field,value=(edit[k] for k in ('kind','handle','field','value'))
        if not all(isinstance(x,str) for x in (kind,handle,field)):reject('td_edit_fields')
        identity=r'[A-Za-z0-9_][A-Za-z0-9_ .()-]{0,127}' if kind in {'ThermoProps','OpticalProps'} else r'[A-Fa-f0-9]{1,32}'
        if kind not in EDIT_FIELDS or field not in EDIT_FIELDS[kind] or not re.fullmatch(identity,handle):reject('unsupported_td_edit')
        if type(value) not in (int,float) or not math.isfinite(value):reject('td_edit_number')
        if (field in {'InitialTemp','MassVol','XMax','YMax','TopThickness','BotThickness','Density','SpecificHeat','Conductivity'} or kind=='Conductor' and field=='Value') and value<0:reject('td_edit_range')
        if field in {'Alph','Emis'} and not 0<=value<=1:reject('td_edit_range')
        key=(kind,handle.casefold(),field)
        if key in seen:reject('td_edit_collision')
        seen.add(key)
    return edits
