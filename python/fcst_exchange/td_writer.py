# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned new-model TD constant-network serialization, without source templates.

Canonical generation uses RcNode/Conductor v22 and HeatLoad v17. The separate
geometry module supplies complete rectangle/brick wire records to the same packet.
Unknown model fields cannot be omitted to obtain an export. Target-product and
full-physics qualification remain separate from independent codec round trips.
"""
from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import struct
from .core import reject
from .sinda_writer import _model
from .dwg_native import NativeRuntime
from .td_node import decode_node
from .td_conductor import decode_conductor
from .td_load import decode_load
from .dwg_native import Fields


class BitWriter:
    def __init__(self):self.bytes=bytearray();self.count=0
    def put(self,value,width):
        if type(width) is not int or not 0<=width<=64 or type(value) is not int or not 0<=value<(1<<width):reject('td_writer_bits')
        for i in range(width):
            if self.count%8==0:self.bytes.append(0)
            self.bytes[-1]|=((value>>(width-i-1))&1)<<(7-self.count%8);self.count+=1
        if len(self.bytes)>1048576:reject('td_writer_payload_limit')
    def raw(self,value):
        for byte in value:self.put(byte,8)
    def bl(self,value):
        if type(value) is not int or not -2147483648<=value<=2147483647:reject('td_writer_integer')
        if value==0:self.put(2,2)
        elif 0<value<256:self.put(1,2);self.put(value,8)
        else:self.put(0,2);self.raw(struct.pack('<i',value))
    def bs(self,value):
        if not 0<=value<=65535:reject('td_writer_short')
        if value==0:self.put(2,2)
        elif value<256:self.put(1,2);self.put(value,8)
        elif value==256:self.put(3,2)
        else:self.put(0,2);self.raw(struct.pack('<H',value))
    def bd(self,value):
        if type(value) not in (int,float) or not math.isfinite(value):reject('td_writer_number')
        if value==0:self.put(2,2)
        elif value==1:self.put(1,2)
        else:self.put(0,2);self.raw(struct.pack('<d',value))
    def point(self,value):
        if len(value)!=3:reject('td_writer_point')
        for x in value:self.bd(x)


@dataclass(frozen=True)
class EncodedPayload:
    kind:int
    data:bytes
    data_bits:int
    strings:bytes
    string_bits:int
    references:tuple


class FilerWriter:
    def __init__(self):self.data=BitWriter();self.strings=BitWriter();self.references=[]
    def text(self,value):
        if not isinstance(value,str) or '\0' in value:reject('td_writer_text')
        try:raw=value.encode('utf-16-le')
        except UnicodeError:reject('td_writer_text')
        size=len(raw)//2
        if size>16383:reject('td_writer_text_limit')
        self.data.bl(-size if size else 0)
        if size:self.strings.bs(size);self.strings.raw(raw)
    def integers(self,values):
        self.data.bl(len(values))
        for value in values:self.data.bl(value)
    def flags(self,values):
        self.data.bl(len(values))
        for value in values:self.data.put(int(value),1)
    def expression(self,dimension=-1,*,dimensional=None):
        b=self.data;b.bl(5)
        for value in (-1,0,0):b.bl(value)
        self.text('');self.text('');self.table();b.bl(0);b.bl(dimension)
        b.put(int(dimension!=-1 if dimensional is None else dimensional),1);self.table()
    def table(self):
        self.data.bl(1);self.integers(());self.integers(());self.flags(())
    def multi_expression(self,dimension):
        b=self.data;b.bl(3);b.bl(0);b.bl(-1);b.bl(0);b.bl(0);self.text('');self.table();b.bl(0);b.bl(dimension)
    def logic(self):
        b=self.data;b.bl(5);self.text('');b.bl(-1);self.text('GLOBAL');self.text('');b.bl(1);self.expression();self.text('')
        b.bl(3);b.bl(0);b.bl(1)
        for _ in range(4):b.bl(0)
        self.flags((0,)*7);self.integers((0,)*7);self.text('')
    def connection(self,index):
        b=self.data;b.bl(2);b.bl(1);b.bl(1);b.bl(1);self.references.append(index);b.bl(1)
    def result(self,kind):
        if self.strings.count>=32768:reject('td_writer_string_stream_limit')
        return EncodedPayload(kind,bytes(self.data.bytes),self.data.count,bytes(self.strings.bytes),self.strings.count,tuple(self.references))


def node_payload(submodel,identifier,temperature,capacity,classification,label=''):
    if classification not in {'capacitive','algebraic','prescribed'}:reject('td_writer_node_classification')
    f=FilerWriter();b=f.data;b.bl(22)
    for point in ((0,0,0),(1,0,0),(0,1,0),(0,0,1)):b.point(point)
    f.text(submodel);b.bl(identifier);b.bl({'capacitive':0,'algebraic':1,'prescribed':2}[classification])
    b.bd(capacity);b.bd(temperature);b.bl(0);f.text('UNDEFINED')
    b.bl(0);b.put(0,1);b.bl(0)
    for _ in range(3):b.put(0,1)
    b.bl(0);b.bl(0);b.bl(0);b.bd(-1)
    f.expression(13);f.expression(4);f.text(label);b.bl(0);b.bl(1);f.expression();b.bl(0);b.put(0,1);f.logic()
    for _ in range(3):b.bd(0)
    f.references.append(0);return f.result(1)


def conductor_payload(submodel,identifier,value,from_index,to_index,label=''):
    f=FilerWriter();b=f.data;b.bl(22);f.text(submodel);b.bl(identifier);b.bd(value);b.bl(0);f.text('');f.text(label)
    for _ in range(5):b.bl(0)
    b.bl(0);b.bl(0);b.bl(0);f.expression(15);b.bl(0);b.bl(0);b.bl(0);b.bl(0);b.bl(1)
    for value in (1,1,1,1,1,1,1,1,0,101325,0):b.bd(value)
    for dimension in (-1,1,1,1,1,1,9,-1,7,6,17):f.expression(dimension,dimensional=True)
    b.bl(identifier);f.logic();b.bl(1);f.expression();f.text('');f.connection(from_index);f.connection(to_index)
    for value,dimension in ((1,-1),(0,-1),(0,-1),(0,26)):b.bd(value);f.expression(dimension,dimensional=True)
    b.bl(1);b.bl(0);return f.result(2)


def load_payload(value,node_index,label=''):
    f=FilerWriter();b=f.data;b.bl(17);f.text(label or 'FCST load');f.text(label);b.bd(value)
    for _ in range(4):b.bl(0)
    b.bl(0);b.bl(1);f.expression(16);b.bd(1);f.expression();b.bl(0);b.bd(1);f.expression()
    for _ in range(3):b.bl(0)
    b.bl(0);f.text('')
    for value in (0,-1,-1,-1):b.bl(value)
    b.bd(1);f.expression();b.bl(0);b.bl(0);b.bl(0);f.text('')
    for value in (0,-1,-1):b.bl(value)
    b.bl(1);f.expression();f.connection(node_index);b.bl(0)
    for dimension in (2,27,2,4,27,4,27):f.multi_expression(dimension)
    b.bl(0);return f.result(3)


def network_packet(records):
    if not isinstance(records,(list,tuple)) or not 1<=len(records)<=10000:reject('td_writer_network_limit')
    out=bytearray(b'FCSTNEW2'+struct.pack('<I',len(records)))
    for record in records:
        if not isinstance(record,EncodedPayload) or record.kind not in {1,2,3,4,5}:reject('td_writer_record')
        if (type(record.data_bits) is not int or not 0<record.data_bits<=8388608
                or type(record.string_bits) is not int or not 0<=record.string_bits<32768
                or not isinstance(record.data,bytes) or not isinstance(record.strings,bytes)
                or len(record.data)!=(record.data_bits+7)//8 or len(record.strings)!=(record.string_bits+7)//8
                or not isinstance(record.references,tuple) or len(record.references)>10000):reject('td_writer_record_size')
        out.extend(struct.pack('<BIII',record.kind,record.data_bits,record.string_bits,len(record.references)))
        out.extend(record.data);out.extend(record.strings)
        for ref in record.references:
            if type(ref) is not int or not 0<=ref<=len(records):reject('td_writer_reference')
            out.extend(struct.pack('<I',ref))
        if len(out)>16777216:reject('td_writer_network_limit')
    return bytes(out)


def template_fields(payload,reference_handles,*,handle=1):
    """Decode an owned payload in a bounded synthetic filer envelope.

    This is also an independent expectation for a freshly reopened native
    object; no proprietary drawing bytes or source templates are used.
    """
    b=BitWriter()
    def append(raw,count):
        for i in range(count):b.put((raw[i//8]>>(7-i%8))&1,1)
    append(payload.data,payload.data_bits);append(payload.strings,payload.string_bits)
    if payload.string_bits:b.raw(struct.pack('<H',payload.string_bits))
    b.put(int(bool(payload.string_bits)),1);data_end=b.count
    b.put(5,4);b.put(0,4) # null common layer handle
    for ref in payload.references:
        target=reference_handles[ref-1] if ref else 0
        size=(target.bit_length()+7)//8;b.put(4,4);b.put(size,4)
        if size:b.raw(target.to_bytes(size,'big'))
    while b.count%8:b.put(1,1)
    row={'handle':handle,'data':bytes(b.bytes).hex(),'bits':b.count,'object_bits':b.count,
         'data_bits':data_end,'string_bits':payload.string_bits,'handle_bits':b.count-data_end}
    standard=Fields([('entmode',2),('is_xdic_missing',1),('layer',[5,0,0])])
    from .td_geometry import decode_rectangle_complete,decode_brick
    return {1:decode_node,2:decode_conductor,3:decode_load,4:decode_rectangle_complete,5:decode_brick}[payload.kind](row,standard).fields


def verify_network(snapshot,records):
    """Require every intended class, field, value and reference after reopen."""
    from .td_decode import decode_drawing
    inventory=decode_drawing(snapshot)
    if len(inventory.payloads)!=len(records) or len(inventory.records)!=len(records):reject('td_writer_reopen_inventory')
    expected_classes={'RcNode':'RCNODE','RcConductor':'RCCONDUCTOR','RcHeatLoad':'RCHEATLOAD','RcRectangle':'RCRECTANGLE','RcFdBrick':'RCTD_FDBRICK'}
    for row in snapshot.native['classes']:
        if row['cppname'] in expected_classes and (row['dxfname']!=expected_classes[row['cppname']] or row['dwg_version']!=21):reject('td_writer_reopen_class')
    payloads=sorted(inventory.payloads,key=lambda p:p.record['handle']);handles=[p.record['handle'] for p in payloads]
    all_handles={r['handle'] for r in snapshot.native['objects']}
    for expected,actual in zip(records,payloads):
        wanted=template_fields(expected,handles,handle=actual.record['handle'])
        observed=dict(actual.fields);wanted.pop('common_handles');common=observed.pop('common_handles')
        if observed!=wanted:reject('td_writer_reopen_fields_or_reference')
        if any(h['target'] and h['target'] not in all_handles for rows in common.values() for h in rows):reject('td_writer_reopen_common_closure')
    return handles


def model_records(model):
    model=_model(model);model['entities'].sort(key=lambda e:e['id'])
    entities={e['id']:e for e in model['entities']};nodes=sorted((e for e in entities.values() if e['kind']=='node'),key=lambda e:e['id'])
    submodels=sorted((e for e in entities.values() if e['kind']=='submodel'),key=lambda e:e['id'])
    if any('submodel_id' not in e for e in nodes):reject('td_writer_submodel_required')
    # Empty submodel declarations need a dedicated manager codec; never omit them.
    if any(not any(n['submodel_id']==e['id'] for n in nodes) for e in submodels):reject('td_writer_empty_submodel')
    groups={e['id']:'F'+str(i+1).zfill(6) for i,e in enumerate(submodels)};counts={k:0 for k in groups};records=[];identities={}
    for node in nodes:
        group=node['submodel_id'];counts[group]+=1
        records.append(node_payload(groups[group],counts[group],node['temperature']['value'],node['capacity']['value'],node['classification'],node.get('label','')))
        identities[node['id']]={'kind':'node','index':len(records),'submodel':groups[group],'identifier':counts[group]}
    for conductor in sorted((e for e in entities.values() if e['kind']=='conductor'),key=lambda e:e['id']):
        a,b=(identities[conductor[k]] for k in ('from_node_id','to_node_id'))
        records.append(conductor_payload(a['submodel'],len(records)+1,conductor['conductance']['value'],a['index'],b['index'],conductor.get('label','')))
        identities[conductor['id']]={'kind':'conductor','index':len(records)}
    for load in sorted((e for e in entities.values() if e['kind']=='load'),key=lambda e:e['id']):
        records.append(load_payload(load['power']['value'],identities[load['node_id']]['index'],load.get('label','')))
        identities[load['id']]={'kind':'load','index':len(records)}
    for identifier,name in groups.items():identities[identifier]={'kind':'submodel','submodel':name}
    return records,identities,model


def render_model(model):
    records,identities,model=model_records(model)
    return network_packet(records),identities,model


def export_model(model,runtime,destination,work,*,entry='network.dwg'):
    """Publish a new project only after fresh-process structural verification."""
    import os,shutil,tempfile
    from fcst_app.persistence import encode,is_link
    from .vendor_paths import path_name,checked_path
    from .export import rename_new
    if not isinstance(runtime,NativeRuntime):reject('independent_dwg_backend_required')
    records,identities,normalized=model_records(model);packet=network_packet(records)
    destination=Path(destination).absolute();work=Path(work).absolute();entry=path_name(entry)
    if Path(entry).suffix.lower()!='.dwg' or entry.casefold() in {'canonical.json','identity-map.json'}:reject('td_writer_entry')
    if (destination.exists() or work.exists() or not destination.parent.is_dir() or not work.parent.is_dir()
            or any(is_link(p) for p in (destination,*destination.parents,work,*work.parents))):reject('td_writer_new_target')
    if destination.resolve().is_relative_to(work.resolve()) or work.resolve().is_relative_to(destination.resolve()):reject('td_writer_work_overlap')
    checked_path(destination.parent,destination.name)
    work.mkdir();result,_=runtime.run('create-network',packet,work/'create')
    reopened,_,_=runtime.run('inspect',result['derived.dwg'],work/'reopen');handles=verify_network(reopened,records)
    for row in identities.values():
        if 'index' in row:row['handle']=handles[row['index']-1]
    receipt={'operation':'td-write-model','profile':'td-constant-network-writer/1',
             'canonical_input_sha256':sha256(encode(normalized)).hexdigest(),
             'drawing_sha256':sha256(result['derived.dwg']).hexdigest(),
             'independent_reopen_verified':True,'vendor_runtime_required':False,
             'objects':len(handles),'identities':[{'entity_id':key,**row} for key,row in sorted(identities.items())],
             'native_ready':False,'qualified':False,
             'scope':'Owned constant node/conductor/load serialization; companion canonical metadata retained; target-product and complete-model qualification pending'}
    temporary=Path(tempfile.mkdtemp(prefix='.fcst-td-new-',dir=destination.parent))
    try:
        files={entry:result['derived.dwg'],'canonical.json':encode(normalized),'identity-map.json':encode(receipt)}
        for name,raw in files.items():
            path=temporary/name;path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if any((temporary/name).read_bytes()!=raw for name,raw in files.items()):reject('td_writer_publication_bytes')
        rename_new(temporary,destination)
    finally:
        if temporary.exists():
            if temporary.parent.resolve()!=destination.parent.resolve() or not temporary.name.startswith('.fcst-td-new-'):reject('td_writer_cleanup')
            shutil.rmtree(temporary)
    return receipt
