# SPDX-License-Identifier: MIT OR Apache-2.0
"""New constant ESATAN D-decks, verified against canonical quantities and topology."""
from hashlib import sha256
import math
import os
from pathlib import Path
import shutil
import tempfile

from fcst_app.persistence import encode
from .core import Limits, reject
from .esatan import EsatanAdapter, EsatanUnits, PROFILE
from .export import rename_new
from .sinda_writer import _model, _number
from .vendor_paths import checked_path, path_name


def render(model, units, *, limits=Limits()):
    if not isinstance(units, EsatanUnits): reject('explicit_esatan_units_required')
    model = _model(model)
    if 'Required ESATAN source semantics unresolved' in model['limitations']:
        reject('esatan_writer_unresolved_source_semantics')
    if len(model['entities']) > limits.records: reject('esatan_writer_entity_limit')
    entities = {e['id']:e for e in model['entities']}
    groups = {e['id']:'S'+str(i+1) for i,e in enumerate(sorted(
        (e for e in entities.values() if e['kind']=='submodel'),key=lambda e:e['id']))}
    if any(e['kind']=='submodel' and 'parent_id' in e for e in entities.values()):
        reject('esatan_writer_nested_submodels')
    # Each declared submodel is nested in an explicit root. An implicit group is
    # used for nodes without submodels; unsupported hierarchy is never flattened.
    identity = {}; rows = {k:[] for k in groups}; rows[None] = []
    for i,node in enumerate(sorted((e for e in entities.values() if e['kind']=='node'),key=lambda e:e['id']),1):
        group = node.get('submodel_id')
        if group not in rows: reject('esatan_writer_submodel')
        identity[node['id']] = ('ESA.MAIN'+('.'+groups[group] if group else ''),'node.'+str(i))
        label = node.get('label','')
        if any(c in label for c in ('\r','\n','\x00')): reject('esatan_writer_label')
        # Source labels have no model authority and remain literal quoted data.
        label = label.replace("'","''")
        typ = {'capacitive':'D','algebraic':'D','prescribed':'B'}[node['classification']]
        rows[group].append((node['id'],f"{typ}{i} = '{label}', T={_number(node['temperature'],units.temperature)}, C={_number(node['capacity'],units.capacity)};"))
    for group,name in groups.items(): identity[group] = ('ESA.MAIN.'+name,'submodel.submodel')
    lines = ['# FCST independent constant D-deck export v1', '$MODEL MAIN']
    loaded = set(); pairs = set()
    def reference(identifier):
        namespace, handle = identity[identifier]
        return namespace.removeprefix('ESA.')+'.'+handle.removeprefix('node.')
    def emit(group):
        context = 'MAIN'+('.'+groups[group] if group else '')
        if group: lines.append('$MODEL '+groups[group])
        lines.append('$NODES'); lines.extend(line for _,line in rows[group])
        conductors = []; loads = []
        for e in sorted(entities.values(),key=lambda e:e['id']):
            if e['kind']=='conductor' and entities[e['from_node_id']].get('submodel_id')==group:
                pair = tuple(sorted((e['from_node_id'],e['to_node_id'])))
                if pair in pairs: reject('esatan_writer_duplicate_conductor')
                pairs.add(pair)
                a,b = reference(e['from_node_id']),reference(e['to_node_id'])
                handle = ':'.join(sorted((
                    # Recreate the reader's endpoint identities for stable source handles.
                    _import_id(identity[e['from_node_id']]),_import_id(identity[e['to_node_id']]))))
                identity[e['id']] = ('ESA.'+context,'conductor.'+sha256(handle.encode()).hexdigest()[:32])
                conductors.append(f'GL({a},{b})={_number(e["conductance"],units.conductance)};')
            elif e['kind']=='load' and entities[e['node_id']].get('submodel_id')==group:
                if e['node_id'] in loaded: reject('esatan_writer_multiple_loads')
                loaded.add(e['node_id'])
                number = identity[e['node_id']][1].removeprefix('node.')
                identity[e['id']] = ('ESA.'+context,'load.'+number)
                loads.append(f'QI{number}={_number(e["power"],units.power)};')
        if conductors: lines.append('$CONDUCTORS'); lines.extend(conductors)
        if loads: lines.append('$INITIAL'); lines.extend(loads)
        if group: lines.append('$ENDMODEL')
    emit(None)
    for group in groups: emit(group)
    lines.append('$ENDMODEL')
    raw = ('\r\n'.join(lines)+'\r\n').encode('utf-8')
    if len(raw)>limits.file_bytes or any(len(l)>limits.line_bytes for l in raw.splitlines()):
        reject('esatan_writer_byte_limit')
    return raw, identity


def _import_id(source):
    from .core import target_id
    namespace,handle = source
    return target_id((PROFILE,namespace.removeprefix('ESA.'),'node',handle.removeprefix('node.')))


def _verify(normalized, staged, identity):
    actual = staged.require_native()
    entries = {(r['namespace'],r['handle']):r['entity_id'] for m in actual['source_maps'] for r in m['entries']}
    mapped = {key:entries[value] for key,value in identity.items()}
    index = {e['id']:e for e in actual['entities']}
    if len(index) != len(normalized['entities'])+1: reject('esatan_writer_inventory')
    for e in normalized['entities']:
        reopened = index[mapped[e['id']]]
        for k,v in e.items():
            if k == 'id': continue
            if k.endswith('_id'):
                if reopened.get(k)!=mapped[v]: reject('esatan_writer_reference')
            elif isinstance(v,dict) and set(v)=={'value','unit'}:
                other = reopened.get(k,{})
                if other.get('unit')!=v['unit'] or abs(v['value']-other.get('value',math.inf))>4*max(math.ulp(v['value']),math.ulp(other.get('value',math.inf))):
                    reject('esatan_writer_quantity')
            elif k=='label' and e['kind']=='submodel':
                # Submodel display labels are not represented by this D-deck subset.
                reject('esatan_writer_submodel_label')
            elif reopened.get(k)!=v: reject('esatan_writer_field')
    return mapped


def export_model(model, units, destination, *, source_version, entry='network.d', limits=Limits()):
    adapter = EsatanAdapter(units,source_version=source_version)
    normalized = _model(model); raw,identity = render(normalized,units,limits=limits)
    entry = path_name(entry); destination = Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir(): reject('esatan_writer_new_target')
    checked_path(destination.parent,destination.name)
    temporary = Path(tempfile.mkdtemp(prefix='.fcst-esatan-',dir=destination.parent))
    try:
        path = temporary/entry; path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        staged = adapter.preview(temporary,entry,limits=limits)
        mapped = _verify(normalized,staged,identity)
        receipt = {'operation':'esatan-write-model','profile':PROFILE,'source_version':source_version,
                   'source_sha256':sha256(raw).hexdigest(),'canonical_input_sha256':sha256(encode(normalized)).hexdigest(),
                   'vendor_runtime_required':False,'roundtrip_verified':True,'qualified':False,
                   'identities':[{'entity_id':k,'namespace':v[0],'handle':v[1],'reimported_entity_id':mapped[k]} for k,v in sorted(identity.items())]}
        rename_new(temporary,destination)
        return receipt
    finally:
        if temporary.exists():
            if temporary.resolve().parent!=destination.parent.resolve() or not temporary.name.startswith('.fcst-esatan-'):
                reject('esatan_writer_cleanup')
            shutil.rmtree(temporary)
