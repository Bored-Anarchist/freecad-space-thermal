# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent, explicitly bound ESATAN AnalysisSet TMD temperature/power reader.

The observed TMD producer is 2025, independently of the 2018-SP1 source deck.
This is a frozen inspected dataset profile, not a universal HDF5 schema claim.
"""
from dataclasses import dataclass
from hashlib import sha256
import io
import math
import re

from fcst_app.persistence import encode
from fcst_contracts import BUNDLE, ContractError, read
from .core import reject
from .esatan import EsatanUnits
from .results import Results, read_results

ATTRIBUTES = ('Temperature','Capacitance','Total_Albedo_Heat_Source','Total_Earth_Heat_Source',
              'Total_Internal_Heat_Source','Total_Rest_Heat_Source','Total_Solar_Heat_Source','Area',
              'Solar_Absorptivity','Infra-Red_Emissivity','Incident_Albedo_Heat_Source',
              'Incident_Earth_Heat_Source','Incident_Solar_Heat_Source','X_Coordinate','Y_Coordinate','Z_Coordinate')


@dataclass(frozen=True)
class TmdBinding:
    source_sha256: str
    model_sha256: str
    case: str
    # Exact numeric model index, modelName, modelPath and canonical source namespace.
    models: tuple
    analysis: str = 'AnalysisSet1'
    solution: str = 'DataGroup1'
    producer: str = '2025'
    inactive_nodes: tuple = ()

    def __post_init__(self):
        if (not all(isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x) for x in (self.source_sha256,self.model_sha256))
                or not isinstance(self.case,str) or not self.case or len(self.case)>256
                or self.producer!='2025' or not isinstance(self.analysis,str) or not re.fullmatch(r'AnalysisSet[1-9]\d{0,3}',self.analysis)
                or not isinstance(self.solution,str) or not re.fullmatch(r'DataGroup[1-9]\d{0,3}',self.solution)
                or not isinstance(self.models,tuple) or not 0<len(self.models)<=10000):
            reject('esatan_tmd_binding')
        indexes = set(); namespaces = set()
        for row in self.models:
            if (not isinstance(row,tuple) or len(row)!=4 or type(row[0]) is not int or row[0]<1
                    or any(not isinstance(x,str) or len(x)>4096 for x in row[1:])
                    or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}',row[3])
                    or row[0] in indexes or row[3] in namespaces): reject('esatan_tmd_model_binding')
            indexes.add(row[0]); namespaces.add(row[3])
        if (not isinstance(self.inactive_nodes,tuple) or len(self.inactive_nodes)>10000
                or any(not isinstance(row,tuple) or len(row)!=2 or any(type(v) is not int for v in row)
                       or row[0] not in indexes or not 0<row[1]<=999999999 for row in self.inactive_nodes)
                or len(set(self.inactive_nodes))!=len(self.inactive_nodes)):
            reject('esatan_tmd_inactive_binding')


@dataclass(frozen=True)
class TmdResults(Results):
    binding_sha256: str
    model_sha256: str
    case_sha256: str
    inactive_count: int

    @property
    def provenance(self):
        return {**super().provenance,'schema':'esatan-tmd-analysisset/1',
                'binding_sha256':self.binding_sha256,'model_sha256':self.model_sha256,
                'case_sha256':self.case_sha256,'inactive_count':self.inactive_count}


def _safe_hdf(f, h5py, *, max_bytes):
    """Inspect links/layout/logical allocation before reading any array."""
    seen = set(); total = 0; pending = [(f,0)]; count = 0
    while pending:
        group,depth = pending.pop()
        if depth>16: reject('esatan_tmd_depth')
        for name in group:
            count += 1
            if count>256: reject('esatan_tmd_object_limit')
            link = group.get(name,getlink=True)
            if not isinstance(link,h5py.HardLink): reject('esatan_tmd_link')
            obj = group[name]; address = h5py.h5o.get_info(obj.id).addr
            if address in seen: reject('esatan_tmd_alias')
            seen.add(address)
            if isinstance(obj,h5py.Group): pending.append((obj,depth+1))
            elif isinstance(obj,h5py.Dataset):
                if obj.is_virtual or obj.external or obj.dtype.hasobject or obj.shape is None:
                    reject('esatan_tmd_external_or_variable_data')
                if obj.ndim>4 or any(d>1000000 for d in obj.shape): reject('esatan_tmd_shape_limit')
                total += math.prod(obj.shape)*obj.dtype.itemsize
                if total>max_bytes: reject('esatan_tmd_allocation_limit')
                layout = obj.id.get_create_plist()
                for i in range(layout.get_nfilters()):
                    if layout.get_filter(i)[0] not in {1,2,3}: reject('esatan_tmd_filter')
            else: reject('esatan_tmd_object_type')
            if len(obj.attrs)>32: reject('esatan_tmd_attribute_limit')
            for attr in obj.attrs:
                attr_id = obj.attrs.get_id(attr)
                if attr_id.dtype.hasobject or math.prod(attr_id.shape)*attr_id.dtype.itemsize>65536:
                    reject('esatan_tmd_attribute_limit')


def _string(value):
    if hasattr(value,'shape') and value.shape==(1,): value=value[0]
    if not isinstance(value,(str,bytes)): reject('esatan_tmd_string')
    try: return value.decode('utf-8').rstrip('\x00') if isinstance(value,bytes) else value
    except UnicodeError: reject('esatan_tmd_encoding')


def inspect_tmd(raw, *, max_bytes=67108864):
    """Safe structure inventory, without interpreting or publishing model values."""
    if type(max_bytes) is not int or not 0<max_bytes<=268435456: reject('esatan_tmd_limit')
    if not isinstance(raw,bytes) or len(raw)>max_bytes: reject('esatan_tmd_source_limit')
    try: import h5py
    except ImportError: reject('esatan_tmd_hdf5_unavailable')
    try:
        with h5py.File(io.BytesIO(raw),'r') as f:
            _safe_hdf(f,h5py,max_bytes=max_bytes)
            groups=0; datasets=0
            def count(name,obj):
                nonlocal groups,datasets
                if isinstance(obj,h5py.Group): groups+=1
                else: datasets+=1
            f.visititems(count)
            return {'profile':'esatan-tmd-structure/1','source_sha256':sha256(raw).hexdigest(),
                    'groups':groups,'datasets':datasets,'runnable':False,'qualified':False,
                    'limitations':['Result interpretation requires an exact schema, case and model binding']}
    except (OSError,ValueError,KeyError,TypeError) as error:
        from .core import ExchangeError
        if isinstance(error,ExchangeError): raise
        reject('esatan_tmd_invalid_container')


def read_tmd(raw, model, binding, units, *, attribute='Temperature', interpolation='none',
             discontinuities=(), max_bytes=67108864):
    if not isinstance(binding,TmdBinding) or not isinstance(units,EsatanUnits): reject('esatan_tmd_binding')
    if type(max_bytes) is not int or not 0<max_bytes<=268435456: reject('esatan_tmd_limit')
    if not isinstance(raw,bytes) or len(raw)>max_bytes or sha256(raw).hexdigest()!=binding.source_sha256:
        reject('esatan_tmd_source_binding')
    try: model=read('model',model)
    except ContractError: reject('esatan_tmd_model_contract')
    if sha256(encode(model)).hexdigest()!=binding.model_sha256: reject('esatan_tmd_model_binding')
    if not isinstance(attribute,str) or attribute not in {'Temperature','Total_Internal_Heat_Source'}: reject('esatan_tmd_quantity')
    try: import h5py
    except ImportError: reject('esatan_tmd_hdf5_unavailable')
    try:
        with h5py.File(io.BytesIO(raw),'r') as f:
            _safe_hdf(f,h5py,max_bytes=max_bytes)
            if set(f)!= {binding.analysis}: reject('esatan_tmd_analysis')
            a=f[binding.analysis]
            if not isinstance(a,h5py.Group): reject('esatan_tmd_layout')
            if _string(a.attrs.get('Description'))!=binding.case: reject('esatan_tmd_case_binding')
            offset=a.attrs.get('TAbs')
            if type(offset) is bool or not hasattr(offset,'__float__') or not math.isfinite(float(offset)) or float(offset)!=BUNDLE['units'][units.temperature][2]:
                reject('esatan_tmd_temperature_offset')
            required={'models','thermalNodes','thermalNodesRealAttributes','thermalNodesStringAttributes',binding.solution}
            allowed=required|{'conductorsGL','conductorsGR','controlConstantsInteger','controlConstantsReal',
                              'controlConstantsString','userConstantsInteger','userConstantsReal','userConstantsString'}
            if not required<=set(a) or set(a)-allowed: reject('esatan_tmd_schema')
            def dataset(group,name,ndim,kind):
                obj=group.get(name)
                if not isinstance(obj,h5py.Dataset) or obj.ndim!=ndim or obj.dtype.kind not in kind:
                    reject('esatan_tmd_dataset')
                return obj
            models=dataset(a,'models',1,'V')
            if models.dtype.names!=('modelName','parentId','modelPath') or len(models)!=len(binding.models):
                reject('esatan_tmd_models')
            if any(models.dtype.fields[k][0].kind not in ({'S'} if k!='parentId' else {'i','u'}) for k in models.dtype.names):
                reject('esatan_tmd_models')
            model_rows=models[:]; mapping={}
            for model_id,name,path,namespace in binding.models:
                if model_id>len(model_rows): reject('esatan_tmd_model_binding')
                source=model_rows[model_id-1]
                if _string(source['modelName'])!=name or _string(source['modelPath'])!=path:
                    reject('esatan_tmd_model_binding')
                # Only the acquired root-model form is frozen in this profile.
                if int(source['parentId'])!=0: reject('esatan_tmd_model_hierarchy')
                mapping[model_id]=namespace
            attrs=dataset(a,'thermalNodesRealAttributes',1,'S')
            names=tuple(_string(v) for v in attrs[:])
            if names!=ATTRIBUTES: reject('esatan_tmd_attribute_schema')
            string_attrs=dataset(a,'thermalNodesStringAttributes',1,'S')
            if tuple(_string(v) for v in string_attrs[:])!=('Type','Label'): reject('esatan_tmd_attribute_schema')
            nodes=dataset(a,'thermalNodes',2,'iu')
            if nodes.shape[1]!=2 or not 0<nodes.shape[0]<=10000: reject('esatan_tmd_nodes')
            refs=[]; node_keys=[]
            for number,model_id in nodes[:]:
                if not 0<int(number)<=999999999 or int(model_id) not in mapping: reject('esatan_tmd_node_identity')
                refs.append([mapping[int(model_id)],'node.'+str(int(number))])
                node_keys.append((int(model_id),int(number)))
            if len(set(node_keys))!=len(node_keys): reject('esatan_tmd_node_identity')
            d=a[binding.solution]
            if not isinstance(d,h5py.Group) or _string(d.attrs.get('ESATAN_version'))!=binding.producer:
                reject('esatan_tmd_producer')
            required_data={'times','thermalNodesRealData','thermalNodesStringData'}
            allowed_data=required_data|{'conductorDataGL','conductorDataGR','controlConstantsIntegerData',
                'controlConstantsRealData','controlConstantsStringData','userConstantsIntegerData','userConstantsRealData','userConstantsStringData'}
            if not required_data<=set(d) or set(d)-allowed_data: reject('esatan_tmd_schema')
            times=dataset(d,'times',1,'f'); values=dataset(d,'thermalNodesRealData',3,'f')
            types=dataset(d,'thermalNodesStringData',3,'S')
            if (not 0<len(times)<=10000 or values.shape!=(len(times),len(refs),len(names))
                    or types.shape!=(len(times),len(refs),2)): reject('esatan_tmd_data_shape')
            source_entries={(r['namespace'],r['handle']):r['entity_id'] for m in model['source_maps'] for r in m['entries']}
            index={e['id']:e for e in model['entities']}
            if not set(binding.inactive_nodes)<=set(node_keys): reject('esatan_tmd_inactive_binding')
            active=[j for j,key in enumerate(node_keys) if key not in binding.inactive_nodes]
            active_refs=[refs[j] for j in active]
            expected_nodes={e['id'] for e in model['entities'] if e['kind']=='node'}
            actual_nodes={source_entries.get(tuple(ref)) for ref in active_refs}
            if actual_nodes!=expected_nodes or len(actual_nodes)!=len(active_refs): reject('esatan_tmd_node_coverage')
            classifications=types[:,:,0]
            for j,ref in enumerate(refs):
                if node_keys[j] in binding.inactive_nodes:
                    if any(_string(v)!='X' for v in classifications[:,j]): reject('esatan_tmd_inactive_type')
                    continue
                entity=index[source_entries[tuple(ref)]]
                expected={'capacitive':'D','algebraic':'D','prescribed':'B'}[entity['classification']]
                if any(_string(v)!=expected for v in classifications[:,j]): reject('esatan_tmd_node_type')
            quantity='temperature' if attribute=='Temperature' else 'power'
            selected=values[:,:,names.index(attribute)]
            table={'version':'fcst-results/1','identities':active_refs,'quantity':quantity,
                   'unit':units.temperature if quantity=='temperature' else units.power,'time_unit':units.time,
                   'sign':'absolute' if quantity=='temperature' else 'positive_into_node',
                   'time':times[:].tolist(),'values':selected[:,active].tolist(),
                   'interpolation':interpolation,'discontinuities':list(discontinuities)}
            result=read_results(encode(table),model)
            return TmdResults(**{**result.__dict__,'source_sha256':binding.source_sha256},
                              binding_sha256=sha256(encode(binding.__dict__)).hexdigest(),
                              model_sha256=binding.model_sha256,case_sha256=sha256(binding.case.encode()).hexdigest(),
                              inactive_count=len(binding.inactive_nodes))
    except (OSError,ValueError,KeyError,TypeError,OverflowError) as error:
        from .core import ExchangeError
        if isinstance(error,ExchangeError): raise
        reject('esatan_tmd_invalid_container')
