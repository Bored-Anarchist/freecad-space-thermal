# SPDX-License-Identifier: MIT OR Apache-2.0
"""Declared SINDA 6.3 constant-network grammar. No imported Fortran is executed."""
from dataclasses import dataclass
from hashlib import sha256
import ast
import math
from pathlib import Path, PurePosixPath
import re

from fcst_contracts import BUNDLE, ContractError, loads, read, dependency_order
from fcst_app.persistence import encode
from .core import (ExchangeError, Limits, Preview, Source, target_id, fidelity, reject)
from .syntax import Record
from .vendor_paths import path_name, checked_path, preservation_check

PROFILE="sinda-6.3-network/1"
NUMBER=re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?")
HEADER=re.compile(r"HEADER\s+([A-Z][A-Z 0-9]*?)(?:\s*,\s*([A-Z][A-Z0-9_]{0,31}))?\s*$",re.I)
INSERT=re.compile(r"INSERT\s+(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z0-9_.() /\\-]+))\s*$",re.I)
DATA_SECTIONS={"NODE DATA","CONDUCTOR DATA","SOURCE DATA","REGISTER DATA","ARRAY DATA","CONTROL DATA"}


def source_text(line):
    quote=None
    for index,char in enumerate(line):
        if char in {'\"',"'"}:
            quote=None if quote==char else char if quote is None else quote
        elif char=='$' and quote is None:return line[:index].strip()
    return line.strip()


@dataclass(frozen=True)
class SindaUnits:
    temperature: str
    capacity: str
    conductance: str
    power: str
    time: str

    def __post_init__(self):
        for field,dimension in (("temperature","temperature"),("capacity","capacity"),("conductance","conductance"),("power","power"),("time","time")):
            unit=getattr(self,field)
            if not isinstance(unit,str) or unit not in BUNDLE['units'] or BUNDLE['units'][unit][0]!=dimension:
                reject("sinda_units")

    def quantity(self,value,dimension):
        return {"value":value,"unit":getattr(self,dimension)}


def scalar(text,registers):
    """Static scalar register arithmetic with SINDA D exponents, never eval()."""
    if not isinstance(text,str) or len(text)>2048:reject("sinda_expression_limit")
    text=re.sub(r'(?<=\d)[dD]([+-]?\d+)',r'e\1',text.strip()).upper()
    try:tree=ast.parse(text,mode='eval')
    except (ValueError,SyntaxError,RecursionError):reject("sinda_expression")
    if sum(1 for _ in ast.walk(tree))>128:reject("sinda_expression_limit")
    def visit(node,depth=0):
        if depth>12:reject("sinda_expression_limit")
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            try:value=float(node.value)
            except OverflowError:reject("sinda_expression_range")
        elif isinstance(node,ast.Name) and node.id in registers:value=registers[node.id]
        elif isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=visit(node.operand,depth+1)*(-1 if isinstance(node.op,ast.USub) else 1)
        elif isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=visit(node.left,depth+1),visit(node.right,depth+1)
            if isinstance(node.op,ast.Add):value=a+b
            elif isinstance(node.op,ast.Sub):value=a-b
            elif isinstance(node.op,ast.Mult):value=a*b
            else:
                if b==0:reject("sinda_expression_domain")
                value=a/b
        else:reject("sinda_dynamic_or_unknown_expression")
        if not math.isfinite(value):reject("sinda_expression_range")
        return value
    return visit(tree.body)


def parse(path,raw,limits=Limits(),initial=("","MAIN")):
    if len(raw)>limits.file_bytes:reject("file_limit")
    section,submodel=initial; offset=0; records=[];ended=False
    for number,content in enumerate(raw.splitlines(keepends=True),1):
        if len(records)>=limits.records or len(content)>limits.line_bytes:reject("record_limit")
        kind="OPAQUE"; code=""; value=None
        try:
            original=content.decode('ascii')
            # SINDA fixed-form comments begin in column 1; dollar suffixes are comments.
            text=source_text(original)
            if not text or original[0:1].upper() in {'C','*','!'} and not text.upper().startswith(('CALL ','CONTROL ')):
                # A bare COLUMN-1 CALL is executable source, never a comment.
                kind="COMMENT"
            elif ended:
                kind='OPAQUE';code='sinda_data_after_end';value={'section':section,'submodel':submodel,'text':text}
            else:
                header=HEADER.fullmatch(text)
                include=INSERT.fullmatch(text)
                if header:
                    section=' '.join(header[1].upper().split());submodel=(header[2] or 'GLOBAL').upper()
                    kind="HEADER";value={"section":section,"submodel":submodel}
                    if section in {'NODE DATA','CONDUCTOR DATA','SOURCE DATA','ARRAY DATA'} and header[2] is None:code='sinda_submodel_required'
                elif include:
                    kind="INCLUDE";value={"path":next(x for x in include.groups() if x is not None).replace('\\','/'),"section":section,"submodel":submodel}
                elif text.upper().startswith('INSERT '):
                    kind="INCLUDE";code="malformed_insert"
                elif re.fullmatch(r'END\s+OF\s+DATA',text,re.I):kind="END";value={};ended=True
                else:
                    kind={"NODE DATA":"NODE","CONDUCTOR DATA":"CONDUCTOR","SOURCE DATA":"LOAD","REGISTER DATA":"REGISTER","ARRAY DATA":"ARRAY","CONTROL DATA":"CONTROL"}.get(section,"OPAQUE")
                    value={"section":section,"submodel":submodel,"text":text}
                    if kind=="OPAQUE":code="sinda_untranslated_section_or_logic"
        except UnicodeError:code="unsupported_encoding"
        records.append(Record(path,offset,offset+len(content),number,kind,content,encode(value) if value is not None else None,code))
        offset+=len(content)
    return tuple(records)


def _resolve(root,entry,limits):
    sources={};graph={};contexts={};errors=[];aliases={};total=0;count=0
    def walk(name,context,stack):
        nonlocal total,count
        path_name(name)
        for i in range(1,len(name.split('/'))+1):
            prefix='/'.join(name.split('/')[:i])
            if aliases.get(prefix.casefold(),prefix)!=prefix:reject("path_collision")
            aliases[prefix.casefold()]=prefix
        if name in stack:reject("include_cycle")
        if len(stack)>=limits.include_depth:reject("include_depth")
        if name in sources:
            reject("repeated_or_ambiguous_insert")
        if len(sources)>=limits.files:reject("file_count")
        path=checked_path(root,name)
        try:
            if not path.is_file():reject("missing_dependency")
            with path.open('rb') as stream:raw=stream.read(limits.file_bytes+1)
        except OSError:reject("source_unavailable")
        total+=len(raw)
        if total>limits.total_bytes:reject("total_bytes")
        records=parse(name,raw,limits,context);count+=len(records)
        if count>limits.records:reject("record_limit")
        sources[name]=Source(name,raw,records);contexts[name]=context;graph[name]=set()
        for position,record in enumerate(records):
            if record.kind!='INCLUDE' or record.code:continue
            try:
                value=record.value
                child=str(PurePosixPath(name).parent/path_name(value['path']))
                graph[name].add(child)
                walk(child,(value['section'],value['submodel']),(*stack,name))
                if any(r.kind=='END' for r in sources[child].records):reject('nested_end_of_data_requires_review')
                if any(r.kind=='HEADER' for r in sources[child].records):
                    following=next((r for r in records[position+1:] if r.kind!='COMMENT'),None)
                    if following is not None and following.kind not in {'HEADER','INCLUDE','END'}:reject('insert_section_transition_requires_review')
            except ExchangeError as error:errors.append({"code":error.code,"source_id":record.source_id})
    walk(path_name(entry),("","MAIN"),())
    if not errors:
        try:
            heights={}
            for name in dependency_order(graph,"include_depth"):
                heights[name]=1+max((heights[c] for c in graph[name]),default=0)
            if max(heights.values())>limits.include_depth:reject("include_depth")
        except ContractError:reject("include_cycle_or_depth")
    # Includes are parsed in their source section, but declaration semantics are
    # order-independent: registers cannot be mutated by imported procedures.
    return tuple(sources[k] for k in sorted(sources)),graph,errors


def expanded_fields(kind,text,registers,limit):
    fields=[x.strip() for x in text.split(',')]
    if not fields[0].upper().startswith('GEN '):return [fields]
    fields[0]=fields[0][4:].strip()
    length=5 if kind=='NODE' else 8 if kind=='CONDUCTOR' else 0
    if not length or len(fields)!=length:reject('sinda_gen_fields')
    numbers=[scalar(x,registers) for x in fields[:-2 if kind=='NODE' else -1]]
    if any(not value.is_integer() for value in numbers):reject('sinda_gen_identity')
    numbers=list(map(int,numbers));start,count,step=numbers[:3]
    if not 0<count<=limit or count>1 and step==0:reject('sinda_gen_limit')
    if kind=='NODE':return [[str(start+i*step),fields[3],fields[4]] for i in range(count)]
    fs,fi,ts,ti=numbers[3:]
    return [[str(start+i*step),str(fs+i*fi),str(ts+i*ti),fields[-1]] for i in range(count)]


def _convert(sources,graph,errors,units,limits):
    records=[r for s in sources for r in s.records if r.kind!='COMMENT']
    rows=[];registers={};pending={};entities=[];entries=[];ids={};submodels={}
    def source_key(submodel,handle):return ("SINDA63."+submodel,str(handle))
    def add(kind,submodel,handle,fields,record):
        key=(kind,submodel,str(handle))
        if key in ids:reject("source_collision")
        identifier=target_id((PROFILE,*key));ids[key]=identifier
        entities.append({"id":identifier,"kind":kind,**fields})
        entries.append({"namespace":source_key(submodel,handle)[0],"handle":kind+'.'+str(handle),"entity_id":identifier})
        return identifier
    def submodel(name):
        if name not in submodels:submodels[name]=add('submodel',name,'submodel',{},None)
        return submodels[name]
    for record in records:
        if record.kind=='REGISTER' and not record.code:
            match=re.fullmatch(r'([A-Za-z][A-Za-z0-9_]{0,31})\s*=\s*(.+)',record.value['text'])
            if match:
                name=match[1].upper()
                if name in pending:errors.append({"code":"register_collision","source_id":record.source_id})
                pending[name]=(match[2],record)
    unresolved=dict(pending)
    for _ in range(min(len(unresolved)+1,64)):
        changed=False
        for name,(expression,record) in list(unresolved.items()):
            try:registers[name]=scalar(expression,registers)
            except ExchangeError:continue
            del unresolved[name];changed=True
        if not changed:break
    staged=[]
    for record in records:
        value=record.value or {}; target=None; status='native-reconstructed';code=record.code
        try:
            if code:reject(code)
            if record.kind=='HEADER':
                if value['section'] not in DATA_SECTIONS and value['section']!='OPTIONS DATA':
                    # Headers themselves are inventoried; their unknown bodies stay opaque.
                    pass
            elif record.kind=='END':pass
            elif record.kind=='INCLUDE':
                error=next((e for e in errors if e['source_id']==record.source_id),None)
                if error:reject(error['code'])
            elif record.kind=='REGISTER':
                name=next((n for n,(_,r) in pending.items() if r.source_id==record.source_id),None)
                if name is None or name in unresolved:reject("unresolved_or_dynamic_register")
            elif record.kind in {'NODE','CONDUCTOR','LOAD'}:
                expanded=expanded_fields(record.kind,value['text'],registers,limits.records)
                if len(entities)+len(staged)+len(expanded)>limits.records:reject('sinda_gen_limit')
                for index,fields in enumerate(expanded):
                    required={'NODE':3,'CONDUCTOR':4,'LOAD':2}[record.kind]
                    if len(fields)!=required:reject("sinda_record_fields")
                    raw_id=scalar(fields[0],registers)
                    if not raw_id.is_integer() or raw_id==0 or abs(raw_id)>2147483647:reject("sinda_identity")
                    handle=int(abs(raw_id));sm=value['submodel'];submodel(sm)
                    source_id=record.source_id if index==0 else record.source_id+'/generated/'+str(index)
                    if record.kind=='NODE':
                        t,c=scalar(fields[1],registers),scalar(fields[2],registers)
                        if c<0:reject("sinda_node_capacity")
                        if raw_id<0 and c!=0:reject("boundary_capacity_not_zero")
                        classification='prescribed' if raw_id<0 else 'capacitive' if c>0 else 'algebraic'
                        generated=add('node',sm,handle,{"submodel_id":submodels[sm],"classification":classification,
                                   "temperature":units.quantity(t,'temperature'),"capacity":units.quantity(c,'capacity')},record)
                        if index==0:target=generated
                    else:
                        generated=None;staged.append((record,fields,sm,handle,raw_id,source_id))
                    if index:
                        generated_row=fidelity(record,'native-reconstructed',target=generated)
                        generated_row['source_id']=source_id;rows.append(generated_row)
            elif record.kind=='CONTROL':
                # Retain case/control semantics until a reviewed runtime translator owns them.
                reject("sinda_case_control_requires_runtime_mapping")
            elif record.kind=='ARRAY':reject("sinda_array_requires_declared_dimensions_and_interpolation")
            else:reject("sinda_untranslated_section_or_logic")
        except ExchangeError as error:
            status='retained-opaque' if record.kind in {'OPAQUE','ARRAY','CONTROL'} else 'unsupported';code=error.code
        rows.append(fidelity(record,status,category='dependency' if record.kind in {'HEADER','INCLUDE','END'} else 'procedure' if record.kind=='OPAQUE' else 'entity',target=target,code=code))
    by_source={r['source_id']:r for r in rows}
    def node(text,default):
        m=re.fullmatch(r'(?:(\w+)\.)?(\d+)',text.strip())
        if not m:reject("sinda_node_reference")
        key=('node',(m[1] or default).upper(),str(int(m[2])))
        if key not in ids:reject("sinda_missing_node")
        return ids[key]
    for record,fields,sm,handle,raw_id,source_id in staged:
        row=by_source[source_id]
        try:
            if record.kind=='CONDUCTOR':
                if raw_id<0:reject("sinda_radiative_conductor_requires_native_radiation")
                value=scalar(fields[3],registers)
                target=add('conductor',sm,handle,{"from_node_id":node(fields[1],sm),"to_node_id":node(fields[2],sm),"conductance":units.quantity(value,'conductance')},record)
            else:
                target=add('load',sm,handle,{"node_id":node(fields[0],sm),"power":units.quantity(scalar(fields[1],registers),'power')},record)
            row['target_id']=target
        except ExchangeError as error:row.update(status='unsupported',limitations=[error.code])
    revision=sha256(encode([{'path':s.path,'sha256':sha256(s.content).hexdigest()} for s in sources])).hexdigest()
    model={'contract_version':'1.0.0','minimum_reader':'1.0.0','project_id':target_id((PROFILE,'project',revision)),
           'revision':0,'entities':entities,'source_maps':[{'id':target_id((PROFILE,'map',revision)),'version':'1.0.0','source_revision':revision,
           'source_tool':'SINDA/FLUINT','source_version':'6.3','entries':entries}], 'mappings':[],'attachments':[],
           'assumptions':['Explicit caller-supplied source units; constant network subset only'],
           'limitations':['Native execution and Q1 comparison qualification remain separately gated'], 'audit':{'timestamp':'source-import'},'gui':{'selection':[]}}
    try:model=read('model',loads(encode(model)))
    except ContractError:errors.append({'code':'sinda_model_contract','source_id':'model'});model=None
    for row in rows:
        if row['status']!='native-reconstructed':errors.append({'code':row['limitations'][0],'source_id':row['source_id']})
    runnable=model is not None and bool(entities) and not errors
    closure=all(graph[k]<=set(graph) for k in graph) and all(by_source[r.source_id]['status']=='native-reconstructed' for r in records if r.kind=='INCLUDE')
    operations=[]
    for operation,supported in [('native-reconstruction',runnable),('unchanged-export',closure),('controlled-edit',runnable and closure),('vendor-qualification',False)]:
        operations.append({'operation':operation,'status':('retained-opaque' if operation=='unchanged-export' else 'native-reconstructed') if supported else 'unsupported',
                           'supported':supported,'source_id':'project','target_id':model['project_id'] if model else None,'profile':PROFILE,
                           'evidence':{'source_revision':revision},'limitations':[] if supported else ['operation_not_supported']})
    return {'schema_version':'1.0.0','adapter':PROFILE,'profile':PROFILE,'source_revision':revision,'runnable':runnable,'qualified':False,
            'records':rows,'operations':operations,'diagnostics':errors,'dependencies':[{'path':k,'includes':sorted(v)} for k,v in sorted(graph.items())]},model


class SindaAdapter:
    profile=PROFILE
    path_name=staticmethod(path_name)
    checked_path=staticmethod(checked_path)
    preservation_check=staticmethod(preservation_check)

    def __init__(self,units):
        if not isinstance(units,SindaUnits):reject("explicit_sinda_units_required")
        self.units=units

    def probe(self):
        return {'profile':self.profile,'available':True,'runtime':'python-standard-library','dialect':'SINDA 6.3 constant-network subset',
                'operations':['preview','unchanged-export','controlled-edit'],'vendor_qualified':False,'native_solver_available':False}

    def preview(self,root,entry,*,limits=Limits()):
        sources,graph,errors=_resolve(Path(root),entry,limits)
        report,model=_convert(sources,graph,errors,self.units,limits)
        issue=preservation_check(Path(root).absolute(),sources,limits)
        if issue:
            for operation in report['operations']:
                if operation['operation'] in {'unchanged-export','controlled-edit'}:operation.update(supported=False,status='unsupported',limitations=[issue])
        return Preview(Path(root).absolute(),entry,self.profile,sources,encode(report),encode(model) if model is not None else None)

    def validate_patch(self,record,replacement,limits):
        if record.kind not in {'NODE','CONDUCTOR','LOAD','REGISTER'}:reject("unsupported_sinda_patch")
        value=record.value
        parsed=parse(record.path,replacement,limits,(value['section'],value['submodel']))
        if len(parsed)!=1 or parsed[0].kind!=record.kind or parsed[0].code:reject("unsupported_sinda_patch")
        before,after=value['text'],parsed[0].value['text']
        if before.upper().startswith('GEN '):
            count=3 if record.kind=='NODE' else 7
            if [x.strip() for x in before.split(',')[:count]]!=[x.strip() for x in after.split(',')[:count]]:reject('identity_edit')
        if record.kind=='REGISTER':
            if before.split('=',1)[0].strip().upper()!=after.split('=',1)[0].strip().upper():reject("identity_edit")
        elif before.split(',',1)[0].strip()!=after.split(',',1)[0].strip():reject("identity_edit")

    def export(self,staged,destination,patches=(),*,limits=Limits()):
        from .export import export_tree
        return export_tree(staged,destination,patches,limits=limits,adapter=self)
