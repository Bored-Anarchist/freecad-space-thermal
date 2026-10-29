# SPDX-License-Identifier: MIT OR Apache-2.0
"""Vendor-free native DWG snapshots and conservative container comparison.

Repeated decoder fields are preserved as ordered occurrences, never converted
to a dictionary that discards values. Authoritative opaque bytes come from the
native API, including otherwise unparsed datastorage sections. No TD class
serialization layout is inferred from a container marker or a display proxy.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
from pathlib import Path
import re

from .core import reject, Limits
from .dwg_container import DwgAuditLimits
from .tools import Tool, ToolRunner, Authorization
from fcst_app.persistence import is_link

PROTOCOL='fcst-dwg-native/1'


class Fields(list):
    """A JSON object with every key occurrence retained in its original order."""


def _load(raw,ordered=False,limits=DwgAuditLimits()):
    if not isinstance(raw,bytes) or not raw or len(raw)>limits.bytes:reject('native_dwg_size')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:reject('native_dwg_duplicate_key')
            result[key]=value
        return result
    try:
        value=json.loads(raw,object_pairs_hook=Fields if ordered else unique,
                         parse_constant=lambda _:reject('native_dwg_number'))
    except (ValueError,UnicodeError,RecursionError) as error:
        if getattr(error,'code','').startswith('native_dwg_'):raise
        reject('native_dwg_json')
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1
        if count>limits.values or depth>limits.depth:reject('native_dwg_structure_limit')
        if isinstance(item,Fields):pending.extend((v,depth+1) for _,v in item)
        elif isinstance(item,dict):pending.extend((v,depth+1) for v in item.values())
        elif isinstance(item,list):pending.extend((v,depth+1) for v in item)
        elif isinstance(item,float) and not math.isfinite(item):reject('native_dwg_number')
    return value


def _one(fields,key):
    if not isinstance(fields,Fields):reject('native_dwg_field_object')
    values=[value for name,value in fields if name==key]
    if len(values)!=1:reject('native_dwg_ambiguous_identity')
    return values[0]


def _integer(value,maximum=2147483647):
    return type(value) is int and 0<=value<=maximum


def _bytes(text,count):
    if (not _integer(count,16777216) or not isinstance(text,str) or len(text)!=2*count
            or not re.fullmatch('(?:[0-9a-fA-F]{2})*',text)):reject('native_dwg_payload_length')
    return text.lower()


@dataclass(frozen=True)
class NativeSnapshot:
    native:dict=field(repr=False)
    standard:Fields=field(repr=False)
    digest:str

    @property
    def report(self):
        opaque=sum(row['bits']>0 or row['rest_bits']>0 for row in self.native['objects'])
        return {'protocol':PROTOCOL,'version':self.native['version'],
                'objects':len(self.native['objects']),'classes':len(self.native['classes']),
                'opaque_objects':opaque,'opaque_sections':sum(row['byte_length']>0 for row in self.native['opaque_sections']),
                'read_warning_bits':self.native['read_errors'],'snapshot_sha256':self.digest,
                'vendor_runtime_required':False,'mode':'container-staging',
                'thermal_mapping':'unmapped','native_ready':False,'qualified':False}


def snapshot(native_raw,standard_raw,patch_sha256,*,limits=DwgAuditLimits()):
    native=_load(native_raw,limits=limits);standard=_load(standard_raw,True,limits)
    if (not isinstance(native,dict) or set(native)!={'protocol','patch_sha256','version','read_errors','classes','objects','opaque_sections'}
            or native['protocol']!=PROTOCOL or native['version']!='AC1032'
            or native['patch_sha256']!=patch_sha256 or not re.fullmatch('[0-9a-f]{64}',patch_sha256)
            or not _integer(native['read_errors'],127)):
        reject('native_dwg_protocol')
    classes=native['classes'];objects=native['objects'];sections=native['opaque_sections']
    if (not isinstance(classes,list) or not isinstance(objects,list) or not isinstance(sections,list)
            or len(classes)>limits.objects or len(objects)>limits.objects or len(sections)>32):
        reject('native_dwg_inventory_limit')
    class_ids=set();handles=set();section_ids=set();total=0
    class_fields={'number','proxyflag','appname','cppname','dxfname','is_zombie','item_class_id','num_instances','dwg_version','maint_version','unknown_1','unknown_2'}
    for row in classes:
        if (not isinstance(row,dict) or set(row)!=class_fields or not _integer(row['number'],65535)
                or row['number']<500 or row['number'] in class_ids
                or any(not isinstance(row[key],str) or len(row[key])>65536 for key in ('appname','cppname','dxfname'))
                or any(not _integer(row[key],4294967295) for key in class_fields-{'appname','cppname','dxfname'})):
            reject('native_dwg_class')
        class_ids.add(row['number'])
    for row in objects:
        if (not isinstance(row,dict) or set(row)!={'handle','type','kind','bits','data','rest_bits','rest'}
                or not _integer(row['handle'],18446744073709551615) or not row['handle'] or row['handle'] in handles
                or not _integer(row['type'],65535) or row['type']>=500 and row['type'] not in class_ids
                or not isinstance(row['kind'],str) or len(row['kind'])>65536
                or not _integer(row['bits'],134217728) or not _integer(row['rest_bits'],134217728)):
            reject('native_dwg_object')
        handles.add(row['handle'])
        row['data']=_bytes(row['data'],(row['bits']+7)//8)
        row['rest']=_bytes(row['rest'],(row['rest_bits']+7)//8)
        total+=(row['bits']+7)//8+(row['rest_bits']+7)//8
    for row in sections:
        if (not isinstance(row,dict) or set(row)!={'name','byte_length','data'}
                or row['name']!='AcDsPrototype_1b' or row['name'] in section_ids):
            reject('native_dwg_section')
        section_ids.add(row['name']);row['data']=_bytes(row['data'],row['byte_length']);total+=row['byte_length']
    if total>16777216:reject('native_dwg_opaque_limit')
    if _one(_one(standard,'FILEHEADER'),'version')!='AC1032':reject('native_dwg_version')
    root_keys=[key for key,_ in standard]
    if len(set(root_keys))!=len(root_keys):reject('native_dwg_duplicate_section')
    standard_objects=_one(standard,'OBJECTS');standard_classes=_one(standard,'CLASSES')
    if (not isinstance(standard_objects,list) or isinstance(standard_objects,Fields)
            or not isinstance(standard_classes,list) or isinstance(standard_classes,Fields)):
        reject('native_dwg_standard_inventory')
    observed=[]
    for row in standard_objects:
        handle=_one(row,'handle')
        if (not isinstance(handle,list) or isinstance(handle,Fields) or len(handle)!=3
                or any(not _integer(value,18446744073709551615) for value in handle) or handle[0]!=0):
            reject('native_dwg_standard_identity')
        observed.append(handle[2])
    numbers=[_one(row,'number') for row in standard_classes]
    if (len(observed)!=len(handles) or set(observed)!=handles or len(numbers)!=len(class_ids) or set(numbers)!=class_ids):
        reject('native_dwg_standard_inventory')
    digest=sha256(native_raw+b'\0'+standard_raw).hexdigest()
    return NativeSnapshot(native,standard,digest)


def _normal(value):
    if isinstance(value,Fields):return {'fields':[[key,_normal(item)] for key,item in value]}
    if isinstance(value,list):return [_normal(item) for item in value]
    return value


def _filter(fields,physical):
    seen=set();result=Fields()
    for key,value in fields:
        if key in physical and key not in seen:seen.add(key);continue
        result.append((key,value))
    return result


def _standard(snapshot):
    result={}
    for name,value in snapshot.standard:
        if name=='OBJECTS':
            result[name]={_one(row,'handle')[2]:_normal(_filter(row,{'index','size','bitsize'})) for row in value}
        elif name=='FILEHEADER':result[name]=_normal(_filter(value,{'thumbnail_address'}))
        elif name=='R2004_Header':
            # Page/section locations, IDs, counts and checksum are regenerated.
            # Logical section contents are compared separately in full below.
            result[name]=_normal(_filter(value,{'last_section_address','crc32','section_map_address','secondheader_address',
                                               'section_info_id','section_array_size','last_section_id','section_map_id','numsections'}))
        else:result[name]=_normal(value)
    return result


def compare(before,after):
    if before.native['patch_sha256']!=after.native['patch_sha256']:reject('native_dwg_profile_changed')
    a,b=before.native,after.native
    classes=lambda data:{row['number']:row for row in data['classes']}
    objects=lambda data:{row['handle']:row for row in data['objects']}
    sections=lambda data:{row['name']:row for row in data['opaque_sections']}
    equal_native=(classes(a)==classes(b) and objects(a)==objects(b) and sections(a)==sections(b)
                  and a['read_errors']==b['read_errors'] and a['version']==b['version'])
    sa,sb=_standard(before),_standard(after)
    changed=sum(sa.get(key)!=sb.get(key) for key in sa.keys()|sb.keys())
    return {'native_records_preserved':equal_native,'standard_fields_preserved':changed==0,
            'changed_standard_sections':changed,'opaque_sections_preserved':sections(a)==sections(b),
            'structural_roundtrip_verified':equal_native and changed==0,
            'vendor_runtime_required':False,'thermal_mapping':'unmapped','native_ready':False,'qualified':False}


@dataclass(frozen=True)
class NativeRuntime:
    """Application-approved tool registration; never reconstructed from model data."""
    executable:Path
    executable_sha256:str
    patch_sha256:str

    def run(self,operation,raw,work):
        if operation not in {'inspect','rewrite','fixture'}:reject('native_dwg_operation')
        if not re.fullmatch('[0-9a-f]{64}',self.patch_sha256):reject('native_dwg_patch')
        if operation!='fixture' and (not isinstance(raw,bytes) or not raw.startswith(b'AC1032') or len(raw)>67108864):
            reject('independent_dwg_container_profile')
        outputs=('source.dwg',) if operation=='fixture' else ('native.json','standard.json')+(('derived.dwg',) if operation=='rewrite' else ())
        inputs={'fixture.json':b'{"kind":"fcst-owned-container-fixture/1"}'} if operation=='fixture' else {'source.dwg':raw}
        profile='fcst-native-dwg-'+operation
        tool=Tool(profile,self.executable,self.executable_sha256,(operation,),timeout_seconds=180,memory_mb=4096,output_bytes=1048576)
        result,receipt=ToolRunner([tool]).run(profile,Path(work).absolute(),inputs,outputs,
                                            Authorization(profile,'convert','independent-container-v1'),
                                            limits=Limits(files=16,file_bytes=67108864,total_bytes=268435456))
        if operation=='fixture':return result,receipt
        decoded=snapshot(result['native.json'],result['standard.json'],self.patch_sha256)
        return decoded,result.get('derived.dwg'),receipt

    @classmethod
    def from_receipt(cls,path):
        """Load an explicitly selected trusted installation receipt, not a source project manifest."""
        path=Path(path).absolute()
        if (not path.is_file() or path.stat().st_size>1048576 or any(is_link(p) for p in (path,*path.parents))):
            reject('native_dwg_receipt')
        receipt=_load(path.read_bytes())
        from importlib.resources import files
        profile=_load(files('fcst_exchange').joinpath('dwg-profile.json').read_bytes())
        if (not isinstance(receipt,dict) or receipt.get('protocol')!=PROTOCOL
                or receipt.get('backend_profile')!=profile or receipt.get('executable')!='bin/fcst-dwg.exe'
                or not isinstance(receipt.get('executable_sha256'),str) or not re.fullmatch('[0-9a-f]{64}',receipt['executable_sha256'])):
            reject('native_dwg_receipt_profile')
        runtime=cls(path.parent/'bin/fcst-dwg.exe',receipt['executable_sha256'],profile['patch_sha256'])
        tool=Tool('fcst-native-dwg-inspect',runtime.executable,runtime.executable_sha256,('inspect',),memory_mb=4096)
        ToolRunner([tool]).probe(tool.profile)
        return runtime
