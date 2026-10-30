# SPDX-License-Identifier: MIT OR Apache-2.0
"""Owned ESATAN D-deck constant-network conversion, with explicit source profiles.

No source program, vendor API, environment discovery or subprocess is evaluated.
Unsupported geometry/procedures/arrays remain required and block reconstruction.
"""
from pathlib import Path, PurePosixPath
from dataclasses import dataclass
from hashlib import sha256
import re

from fcst_app.persistence import encode
from fcst_contracts import ContractError, read, loads
from .core import (ExchangeError, Limits, Preview, Source, fidelity, reject, target_id)
from .esatan_syntax import NAME, statements, assignments, split
from .sinda import SindaUnits, scalar
from .vendor_paths import path_name, checked_path, preservation_check

PROFILE = 'esatan-d-constant/1'
VERSIONS = ('2018-sp1', '2020')
ESATAN_LIMITS = Limits(file_bytes=16777216, total_bytes=67108864, records=100000)


class EsatanUnits(SindaUnits):
    """Caller-declared units; a filename or release cannot establish units."""


@dataclass(frozen=True)
class EsatanPreview(Preview):
    units: EsatanUnits
    source_version: str


def _scan(root, entry, limits):
    sources = {}; graph = {}; errors = []; aliases = {}; total = 0; count = 0
    def visit(name, depth, ancestors):
        nonlocal total, count
        path_name(name)
        folded = name.casefold()
        # Include both file aliases and aliases of ancestor directories.
        for p in (PurePosixPath(name), *PurePosixPath(name).parents):
            key = p.as_posix()
            if key == '.': continue
            if key.casefold() in aliases and aliases[key.casefold()] != key:
                reject('esatan_path_alias')
            aliases[key.casefold()] = key
        if name in ancestors: reject('esatan_include_cycle')
        if depth > limits.include_depth: reject('esatan_include_depth')
        if name in sources: return
        if len(sources) >= limits.files: reject('esatan_file_count')
        path = checked_path(root, name)
        try:
            with path.open('rb') as stream: raw = stream.read(limits.file_bytes+1)
        except OSError: reject('esatan_missing_dependency')
        total += len(raw)
        if len(raw) > limits.file_bytes or total > limits.total_bytes: reject('esatan_byte_limit')
        records = statements(name, raw, limits=limits)
        count += len(records)
        if count > limits.records: reject('esatan_record_limit')
        sources[name] = Source(name, raw, records); graph[name] = set()
        for record in records:
            text = record.value['text']
            if not text.upper().startswith('$INCLUDE'): continue
            m = re.fullmatch(r'\$INCLUDE\s+[\'\"]([^\'\"]+)[\'\"]\s*;?', text, re.I)
            if not m:
                errors.append({'source_id':record.source_id, 'code':'esatan_include_syntax'}); continue
            child = (PurePosixPath(name).parent / m[1].replace('\\','/')).as_posix()
            try:
                path_name(child); graph[name].add(child); visit(child, depth+1, ancestors+(name,))
            except ExchangeError as error:
                errors.append({'source_id':record.source_id, 'code':error.code})
    visit(entry, 0, ())
    return tuple(sources.values()), graph, errors


def _convert(sources, graph, diagnostics, units, version):
    source_by_name = {s.path:s for s in sources}
    rows = []; entities = []; entries = []; keys = {}; stack = []; section = ''; local = ''
    constants = {}; pending = []; work = []; seen = set(); visited = set(); model_count = 0
    def add(kind, model, handle, fields):
        key = (model, kind, str(handle))
        if key in keys: reject('esatan_source_collision')
        identifier = target_id((PROFILE, *key)); keys[key] = identifier
        entities.append({'id':identifier, 'kind':kind, **fields})
        entries.append({'namespace':'ESA.'+model, 'handle':kind+'.'+str(handle), 'entity_id':identifier})
        return identifier
    def walk(name):
        # Reusing a data include in a different context is ambiguous, never skipped.
        nonlocal section, local, model_count
        if name in visited: reject('esatan_include_reuse')
        visited.add(name)
        for record in source_by_name[name].records:
            if record.kind == 'COMMENT': continue
            row = fidelity(record, 'native-reconstructed'); rows.append(row)
            text = record.value['text'].strip().removesuffix(';').strip()
            try:
                if record.code: reject(record.code)
                if text.startswith('$'):
                    fields = text.split(None, 1); directive = fields[0].upper()
                    arg = fields[1].strip() if len(fields) == 2 else ''
                    row['category'] = 'dependency'
                    if directive == '$MODEL':
                        if not re.fullmatch(NAME, arg) or len(stack) >= 16: reject('esatan_model_identity')
                        stack.append(arg.upper()); model_count += 1
                        name_key = '.'.join(stack)
                        if len('ESA.'+name_key) > 64: reject('esatan_model_identity')
                        parent = keys.get(('.'.join(stack[:-1]),'submodel','submodel'))
                        row['target_id'] = add('submodel', name_key, 'submodel', {'parent_id':parent} if parent else {})
                        section = ''; local = ''
                    elif directive == '$ENDMODEL':
                        if arg or not stack: reject('esatan_model_balance')
                        stack.pop(); section = ''; local = ''
                    elif directive == '$INCLUDE':
                        m = re.fullmatch(r'[\'\"]([^\'\"]+)[\'\"]', arg)
                        if not m: reject('esatan_include_syntax')
                        child = (PurePosixPath(record.path).parent / m[1].replace('\\','/')).as_posix()
                        error = next((e['code'] for e in diagnostics if e['source_id']==record.source_id), None)
                        if error: reject(error)
                        walk(child)
                    elif directive in {'$REAL', '$INTEGER'}:
                        if section != '$LOCALS' or arg: reject('esatan_local_declaration')
                        local = directive
                    else:
                        if arg or not stack: reject('esatan_section_context')
                        section = directive; local = ''
                        if directive not in {'$LOCALS','$NODES','$CONDUCTORS','$INITIAL'}:
                            reject('esatan_untranslated_section')
                    continue
                if not stack: reject('esatan_model_context')
                context = '.'.join(stack)
                if section == '$LOCALS' and local in {'$REAL','$INTEGER'}:
                    m = re.fullmatch('('+NAME+r')\s*=\s*(.+)', text, re.S)
                    if not m: reject('esatan_local_declaration')
                    key = (context, m[1].upper())
                    if key in seen: reject('esatan_constant_collision')
                    seen.add(key); pending.append((key,m[2],local,row)); continue
                work.append((record,row,context,section,text))
            except ExchangeError as error:
                row.update(status='unsupported', limitations=[error.code])
    walk(sources[0].path)
    if stack or model_count == 0: diagnostics.append({'source_id':'project','code':'esatan_model_balance'})
    unresolved = list(pending)
    for _ in range(min(len(pending)+1, 64)):
        changed = False
        for item in list(unresolved):
            key, expression, kind, row = item
            env = {k[1]:v for k,v in constants.items() if k[0]==key[0]}
            try:
                value = scalar(expression, env)
                if kind == '$INTEGER' and not value.is_integer(): reject('esatan_integer_value')
            except ExchangeError: continue
            constants[key] = value; unresolved.remove(item); changed = True
        if not changed: break
    for _,_,_,row in unresolved:
        row.update(status='unsupported', limitations=['esatan_unresolved_constant'])
    deferred = []
    for record,row,context,section,text in work:
        try:
            env = {k[1]:v for k,v in constants.items() if k[0]==context}
            if section == '$NODES':
                m = re.fullmatch(r'([DBX])\s*(\d{1,9})\s*(.*)', text, re.S|re.I)
                if not m or int(m[2]) == 0: reject('esatan_node_syntax')
                rest=m[3].strip(); label="''"
                if rest.startswith('='):
                    fields=split(rest[1:]); label=fields.pop(0)
                    if not re.fullmatch(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"",label): reject('esatan_node_label')
                else: fields=split(rest.removeprefix(','))
                attrs = assignments(','.join(fields))
                if 'T' not in attrs: reject('esatan_missing_node_attributes')
                t,c = scalar(attrs['T'],env),scalar(attrs.get('C','0'),env)
                typ = m[1].upper()
                if typ=='X': reject('esatan_inactive_node_retained')
                if c<0 or typ=='B' and c!=0: reject('esatan_node_capacity')
                row['target_id'] = add('node',context,int(m[2]),{
                    **({'label':label[1:-1].replace(label[0]*2,label[0])} if label[1:-1] else {}),
                    'submodel_id':keys[(context,'submodel','submodel')],
                    'classification':'prescribed' if typ=='B' else 'capacitive' if c>0 else 'algebraic',
                    'temperature':units.quantity(t,'temperature'), 'capacity':units.quantity(c,'capacity')})
                if set(attrs)-{'T','C'}: reject('esatan_unmapped_node_attributes')
            elif section in {'$CONDUCTORS','$INITIAL'}:
                deferred.append((row,context,section,text,env))
            else: reject('esatan_untranslated_logic_or_section')
        except ExchangeError as error: row.update(status='unsupported', limitations=[error.code])
    def node(ref,context):
        m = re.fullmatch(r'(?:(('+NAME+r')(?:\.'+NAME+r')*)\.)?(\d{1,9})',ref.strip())
        if not m: reject('esatan_node_reference')
        key = ((m[1] or context).upper(),'node',str(int(m[3])))
        if key not in keys: reject('esatan_missing_node')
        return keys[key]
    load_nodes = set(); initial_t = set()
    for row,context,section,text,env in deferred:
        try:
            if section == '$CONDUCTORS':
                m = re.fullmatch(r'(GL|GR)\s*\((.+)\)\s*=\s*(.+)',text,re.S|re.I)
                if not m or m[1].upper() != 'GL': reject('esatan_radiative_or_unknown_conductor')
                refs = split(m[2])
                if len(refs) != 2: reject('esatan_conductor_nodes')
                a,b = (node(r,context) for r in refs)
                handle = ':'.join(sorted((a,b)))
                row['target_id'] = add('conductor',context,handle,{
                    'from_node_id':a,'to_node_id':b,'conductance':units.quantity(scalar(m[3],env),'conductance')})
                # Canonical source handles must fit the shared identity vocabulary.
                entries[-1]['handle'] = 'conductor.'+sha256(handle.encode()).hexdigest()[:32]
            else:
                m = re.fullmatch(r'(QI|T)(\d{1,9})\s*=\s*(.+)',text,re.S|re.I)
                if not m: reject('esatan_initial_runtime_logic')
                target = node(m[2],context); value = scalar(m[3],env)
                if m[1].upper() == 'T':
                    if target in initial_t: reject('esatan_duplicate_initial_temperature')
                    initial_t.add(target)
                    next(e for e in entities if e['id']==target)['temperature'] = units.quantity(value,'temperature')
                    row['target_id'] = target
                else:
                    if target in load_nodes: reject('esatan_duplicate_load')
                    load_nodes.add(target)
                    row['target_id'] = add('load',context,m[2],{'node_id':target,'power':units.quantity(value,'power')})
        except ExchangeError as error: row.update(status='unsupported', limitations=[error.code])
    revision = sha256(encode([{'path':s.path,'sha256':sha256(s.content).hexdigest()} for s in sources])).hexdigest()
    model = {'contract_version':'1.0.0','minimum_reader':'1.0.0','project_id':target_id((PROFILE,'project',revision)),
             'revision':0,'entities':entities,'source_maps':[{'id':target_id((PROFILE,'map',revision)),
             'version':'1.0.0','source_revision':revision,'source_tool':'ESATAN-TMS','source_version':version,'entries':entries}],
             'mappings':[],'attachments':[],'assumptions':['Explicit source units; reviewed constant D-deck subset'],
             'limitations':['Native-project and solver qualification remain separate'],
             'audit':{'timestamp':'source-import'},'gui':{'selection':[]}}
    try: model = read('model',loads(encode(model)))
    except ContractError:
        model = None; diagnostics.append({'source_id':'model','code':'esatan_model_contract'})
    diagnostics += [{'source_id':r['source_id'],'code':r['limitations'][0]} for r in rows if r['limitations']]
    if model is not None and diagnostics:
        model['limitations'].append('Required ESATAN source semantics unresolved')
    runnable = model is not None and any(e['kind']=='node' for e in entities) and not diagnostics
    closure = all(v <= set(graph) for v in graph.values()) and not any('include' in e['code'] or
                    e['code'] in {'unsafe_path','linked_path','esatan_missing_dependency'} for e in diagnostics)
    operations = []
    for op,supported in [('native-reconstruction',runnable),('unchanged-export',closure),
                         ('controlled-edit',runnable and closure),('vendor-qualification',False)]:
        operations.append({'operation':op,'status':('retained-opaque' if op=='unchanged-export' else 'native-reconstructed') if supported else 'unsupported',
                           'supported':supported,'source_id':'project','target_id':model['project_id'] if model else None,
                           'profile':PROFILE,'evidence':{'source_revision':revision},
                           'limitations':[] if supported else ['operation_not_supported']})
    return {'schema_version':'1.0.0','adapter':PROFILE,'profile':PROFILE,'source_revision':revision,
            'runnable':runnable,'qualified':False,'records':rows,'operations':operations,'diagnostics':diagnostics,
            'dependencies':[{'path':k,'includes':sorted(v)} for k,v in sorted(graph.items())]}, model


class EsatanAdapter:
    profile = PROFILE
    path_name = staticmethod(path_name)
    checked_path = staticmethod(checked_path)
    preservation_check = staticmethod(preservation_check)

    def __init__(self, units, *, source_version):
        if not isinstance(units,EsatanUnits): reject('explicit_esatan_units_required')
        if source_version not in VERSIONS: reject('esatan_source_version')
        self.units = units; self.source_version = source_version

    def probe(self):
        return {'profile':PROFILE,'available':True,'source_version':self.source_version,
                'vendor_runtime_required':False,'qualified':False,'native_solver_available':False}

    def preview(self,root,entry,*,limits=ESATAN_LIMITS):
        root = Path(root).absolute()
        sources,graph,errors = _scan(root,entry,limits)
        report,model = _convert(sources,graph,errors,self.units,self.source_version)
        issue = preservation_check(root,sources,limits)
        if issue:
            for op in report['operations']:
                if op['operation'] in {'unchanged-export','controlled-edit'}:
                    op.update(supported=False,status='unsupported',limitations=[issue])
        return EsatanPreview(root,entry,PROFILE,sources,encode(report),encode(model) if model is not None else None,self.units,self.source_version)

    def validate_patch(self,record,replacement,limits):
        if record.kind != 'STATEMENT': reject('esatan_patch_kind')
        before=record.value['text']
        initial=not before.endswith(';') and re.match(r'^(?:QI|T)\d+\s*=',before,re.I) is not None
        parsed = statements(record.path,replacement,limits=limits,line_statements=initial)
        if len(parsed)!=1 or parsed[0].code or parsed[0].kind!='STATEMENT': reject('esatan_patch_syntax')
        after = parsed[0].value['text']
        # Preserve assignment identity, conductor endpoints and all attribute names.
        def key(text):
            lhs,_,rhs = text.partition('=')
            node_record = re.fullmatch(r'[DBX]\s*\d{1,9}',lhs.strip(),re.I)
            attrs = tuple(assignments(','.join(split(rhs.removesuffix(';'))[1:])).keys()) if node_record else ()
            return re.sub(r'\s+','',lhs).upper(),attrs
        if key(before)!=key(after): reject('identity_edit')

    def export(self,staged,destination,patches=(),*,limits=ESATAN_LIMITS):
        from .export import export_tree
        if not isinstance(staged,EsatanPreview) or staged.units!=self.units or staged.source_version!=self.source_version:
            reject('esatan_preview_profile_mismatch')
        return export_tree(staged,destination,patches,limits=limits,adapter=self)
