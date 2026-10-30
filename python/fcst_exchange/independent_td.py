# SPDX-License-Identifier: MIT OR Apache-2.0
"""Direct DWG inspection and complete immutable source copies without vendor APIs.

Typed versioned payloads permit guarded source-field edits. Whole-model
semantic closure is assessed separately and is never inferred from parsing.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from fcst_app.persistence import is_link

from .core import reject
from .source_tree import capture_project,ProjectCopy,ProjectLimits
from .dwg_native import NativeRuntime,NativeSnapshot,compare,compare_edits
from .td_decode import decode_drawing
from .td_properties import parse_properties
from .core import ExchangeError


@dataclass(frozen=True)
class DwgPreview:
    original:ProjectCopy
    snapshot:NativeSnapshot
    units:object=None

    @property
    def conversion(self):
        from .td_model import convert_network,restore_annotations
        from fcst_contracts import loads,read
        from fcst_app.persistence import encode
        files=dict(self.original.files);holds=[];model=None;receipt=None
        annotations={'canonical.json','identity-map.json'}
        others=set(files)-{self.original.entry}
        if others & annotations:
            try:
                if not annotations<=others:reject('td_native_annotation_pair')
                model=read('model',loads(files['canonical.json']));receipt=loads(files['identity-map.json'])
                if (receipt.get('operation')!='td-write-model' or receipt.get('profile')!='td-constant-network-writer/1'
                        or receipt.get('canonical_input_sha256')!=sha256(encode(model)).hexdigest()
                        or receipt.get('drawing_sha256')!=self.original.drawing_hash):reject('td_native_annotation_binding')
            except (ValueError,TypeError,AttributeError):holds.append('td_native_annotation_binding')
        for name in others-annotations:
            if Path(name).suffix.lower() in {'.tdp','.rco'}:
                try:parse_properties(files[name],Path(name).suffix.lower()[1:])
                except ExchangeError:holds.append('td_native_property_dependency_unreadable')
            else:holds.append('td_native_companion_unmapped')
        result=convert_network(self.snapshot,self.units,self.original.source_hash,closure_holds=holds)
        return restore_annotations(result,model,receipt) if model is not None and receipt is not None and not holds else result

    @property
    def report(self):
        inventory=decode_drawing(self.snapshot)
        properties=[]
        for name,raw in self.original.files:
            if Path(name).suffix.lower() in {'.tdp','.rco'}:
                try:properties.append(parse_properties(raw,Path(name).suffix.lower()[1:]).report)
                except ExchangeError as error:properties.append({'status':'retained-opaque','limitation':error.code})
        conversion=self.conversion.report
        from .td_property_model import dependency_catalog
        return {**self.snapshot.report,**conversion,'source_revision':self.original.source_hash,
                'thermal_mapping':'canonical-constant-network' if conversion['native_ready'] else 'unmapped',
                'thermal_payloads':inventory.report,'property_databases':properties,
                'property_dependencies':dependency_catalog(self.snapshot,self.original.files),
                'files':len(self.original.files),'directories':len(self.original.directories),
                'operations':{'inspect':True,'unchanged-source-export':True,
                              'thermal-native-reconstruction':conversion['native_ready'],'thermal-controlled-edit':conversion['native_ready'],
                              'guarded-source-field-export':any(p.report['payload_decoded'] for p in inventory.payloads) or any('entries' in p for p in properties)},
                'limitations':[] if conversion['native_ready'] else ['required_td_class_semantics_incomplete','semantic_dependency_closure_unqualified']}

    def require_native(self):
        if self.units is None:reject('independent_td_required_class_semantics_unmapped')
        return self.conversion.require_native()

    @property
    def fidelity(self):
        """WP-07 fidelity contract; binary locations conservatively cover the file."""
        from .td_model import DRAWING_KINDS
        conversion=self.conversion;ready=conversion.model_bytes is not None
        mapped={r['handle']:r['entity_id'] for r in conversion.identities if 'handle' in r};records=[]
        for row in self.snapshot.native['objects']:
            supported=ready and (row['handle'] in mapped or row['kind'] in DRAWING_KINDS)
            records.append({'source_id':'DWG.'+str(row['handle']),'target_id':mapped.get(row['handle']),
                'category':'entity' if row['handle'] in mapped or row['kind'] not in DRAWING_KINDS else 'dependency',
                'operation':'import','status':'native-reconstructed' if supported else 'retained-opaque','required':True,
                'location':{'path':self.original.entry,'line':1,'start':0,'end':len(dict(self.original.files)[self.original.entry])},
                'evidence':{'sha256':self.original.drawing_hash,'regressions':['TD-NATIVE-NETWORK-001']},
                'limitations':[] if supported else ['closed_profile_semantics_or_units_unresolved']})
        for name,raw in self.original.files:
            if name==self.original.entry:continue
            inactive=ready and Path(name).suffix.lower() in {'.tdp','.rco'}
            records.append({'source_id':'FILE.'+sha256(name.encode()).hexdigest(),'target_id':None,'category':'dependency',
                'operation':'import','status':'native-reconstructed' if ready and not inactive else 'retained-opaque',
                'required':not inactive,'location':{'path':name,'line':1,'start':0,'end':len(raw)},
                'evidence':{'sha256':sha256(raw).hexdigest(),'regressions':['TD-PORTABLE-SOURCE-001']},
                'limitations':['inactive_property_definitions_retained'] if inactive else [] if ready else ['dependency_unresolved']})
        for row in conversion.identities:
            if row['kind']!='submodel':continue
            records.append({'source_id':'SUBMODEL.'+sha256(row['submodel'].encode()).hexdigest(),'target_id':row['entity_id'] if ready else None,
                'category':'entity','operation':'import','status':'native-reconstructed' if ready else 'retained-opaque','required':True,
                'location':{'path':self.original.entry,'line':1,'start':0,'end':len(dict(self.original.files)[self.original.entry])},
                'evidence':{'sha256':self.original.drawing_hash,'regressions':['TD-NATIVE-NETWORK-001']},
                'limitations':[] if ready else ['closed_profile_semantics_or_units_unresolved']})
        operations=[]
        for name,supported in [('native-reconstruction',ready),('unchanged-export',True),('controlled-edit',ready),('vendor-qualification',False)]:
            operations.append({'operation':name,'status':'retained-opaque' if name=='unchanged-export' else 'native-reconstructed' if supported else 'unsupported',
                'supported':supported,'source_id':'project','target_id':conversion.model['project_id'] if ready else None,
                'profile':'td-independent-network/1','evidence':{'source_revision':self.original.source_hash},
                'limitations':['constant_scalar_fields_only'] if name=='controlled-edit' and supported else [] if supported else ['operation_unqualified_or_unmapped']})
        return {'schema_version':'1.0.0','adapter':'td-independent-network/1','profile':'td-independent-network/1',
                'source_revision':self.original.source_hash,'runnable':ready,'qualified':False,'records':records,
                'operations':operations,'diagnostics':[{'code':r['code'],'source_id':'DWG.'+str(r['handle']) if 'handle' in r else 'project'} for r in conversion.diagnostics],
                'dependencies':[{'path':name,'includes':[n for n,_ in self.original.files if n!=name] if name==self.original.entry else []} for name,_ in self.original.files]}


class IndependentTdAdapter:
    profile='td-independent-payloads/2'

    def __init__(self,runtime,units=None):
        if not isinstance(runtime,NativeRuntime):reject('independent_dwg_backend_required')
        self.runtime=runtime
        if units is not None:
            from .sinda import SindaUnits
            if not isinstance(units,SindaUnits):reject('td_native_explicit_units_required')
        self.units=units

    def preview(self,root,entry,work,*,limits=ProjectLimits()):
        original=capture_project(root,entry,limits=limits);work=Path(work).absolute()
        if (work.resolve().is_relative_to(original.root.resolve())
                or original.root.resolve().is_relative_to(work.resolve())
                or self.runtime.executable.resolve().is_relative_to(original.root.resolve())):
            reject('independent_td_control_source_overlap')
        decoded,_,_=self.runtime.run('inspect',dict(original.files)[original.entry],work)
        original.check_current(limits)
        return DwgPreview(original,decoded,self.units)

    def export_source(self,staged,destination,edits=(),*,work=None,limits=ProjectLimits()):
        if not isinstance(staged,DwgPreview):reject('independent_td_preview_required')
        if edits:return self._export_fields(staged,destination,edits,work,limits)
        staged.original.check_current(limits)
        target=staged.original.copy_to(destination,limits=limits)
        reopened=capture_project(target,staged.original.entry,limits=limits)
        if (reopened.files!=staged.original.files or reopened.directories!=staged.original.directories):
            reject('independent_td_source_copy_changed')
        return {'operation':'td-export-source','status':'retained-opaque','profile':self.profile,
                'source_revision':staged.original.source_hash,'files':len(reopened.files),
                'directories':len(reopened.directories),'exact_source_bytes_preserved':True,
                'vendor_runtime_required':False,'thermal_mapping':'unmapped','native_ready':False,'qualified':False}

    def _export_fields(self,staged,destination,edits,work,limits):
        replacements,reports,verdict,_=self._prepare_fields(staged,destination,edits,work,limits)
        staged.original.copy_to(destination,limits=limits,replacements=replacements)
        return {'operation':'td-export-source-fields','profile':self.profile,'status':'source-fields-edited',
                'source_revision':staged.original.source_hash,'files':len(staged.original.files),
                'edited_files':len(replacements),'edits':reports,**verdict,
                'unrequested_source_files_preserved':True,'vendor_runtime_required':False,
                'native_ready':False,'qualified':False,
                'scope':'Guarded serialized scalar fields; full thermal model execution remains unqualified'}

    def _prepare_fields(self,staged,destination,edits,work,limits):
        if not isinstance(edits,(list,tuple)) or not 1<=len(edits)<=10000:reject('td_source_edit_shape')
        if work is None:reject('td_source_edit_work_required')
        work=Path(work).absolute();destination=Path(destination).absolute()
        for a,b in ((work,staged.original.root),(work,destination),(destination,staged.original.root)):
            if a.resolve().is_relative_to(b.resolve()) or b.resolve().is_relative_to(a.resolve()):reject('td_source_edit_overlap')
        if (work.exists() or destination.exists() or not work.parent.is_dir()
                or any(is_link(p) for p in (work,*work.parents))):reject('td_source_edit_new_tree')
        staged.original.check_current(limits)
        payloads={p.record['handle']:p for p in decode_drawing(staged.snapshot).payloads}
        replacements={};pairs=[];reports=[];seen=set();property_changes={}
        for edit in edits:
            if not isinstance(edit,dict):reject('td_source_edit_shape')
            if set(edit)=={'handle','changes'}:
                handle=edit['handle']
                if type(handle) is not int or handle not in payloads or handle in seen:reject('td_source_edit_handle')
                seen.add(handle);payload=payloads[handle]
                options={'temperature_unit':staged.units.temperature} if staged.units is not None and 'initial_temperature' in payload.fields else {}
                row,report=payload.edited_record(edit['changes'],**options)
                pairs.append((payload.record,row));reports.append(report)
            elif set(edit)=={'path','changes'}:
                name=edit['path']
                if not isinstance(name,str) or name not in dict(staged.original.files) or name in property_changes:reject('td_source_edit_property_path')
                if Path(name).suffix.lower() not in {'.tdp','.rco'}:reject('td_source_edit_property_kind')
                property_changes[name]=edit['changes']
            else:reject('td_source_edit_shape')
        for name,changes in property_changes.items():
            raw,report=parse_properties(dict(staged.original.files)[name],Path(name).suffix.lower()[1:]).edited(changes)
            replacements[name]=raw;reports.append(report)
        work.mkdir();verdict={'edited_roundtrip_verified':True,'edited_objects':0};reopened=staged.snapshot
        if pairs:
            before,derived,_=self.runtime.run('rewrite-edited',dict(staged.original.files)[staged.original.entry],work/'write',edits=pairs)
            if not compare_edits(staged.snapshot,before,pairs)['edited_roundtrip_verified']:reject('td_source_edit_request_mismatch')
            reopened,_,_=self.runtime.run('inspect',derived,work/'reopen')
            verdict=compare_edits(staged.snapshot,reopened,pairs)
            if not verdict['edited_roundtrip_verified']:reject('td_source_edit_unrequested_change')
            actual={p.record['handle']:p for p in decode_drawing(reopened).payloads}
            for original,row in pairs:
                expected=payloads[original['handle']]
                if original['handle'] not in actual:reject('td_source_edit_reopen_profile')
                requested=next(e['changes'] for e in edits if e.get('handle')==original['handle'])
                if actual[original['handle']].fields!={**expected.fields,**requested}:reject('td_source_edit_reopen_values')
            replacements[staged.original.entry]=derived
        staged.original.check_current(limits)
        return replacements,reports,verdict,reopened

    def export_native(self,staged,model,destination,work,*,limits=ProjectLimits()):
        from fcst_contracts import BUNDLE
        from fcst_app.persistence import encode
        from .sinda_writer import _model
        from .td_model import convert_network,equivalent_entities
        if not isinstance(staged,DwgPreview):reject('independent_td_preview_required')
        original=staged.require_native();target=_model(model)
        before={e['id']:e for e in original['entities']};after={e['id']:e for e in target['entities']}
        if set(before)!=set(after):reject('td_native_edit_topology')
        conversion=staged.conversion;identities={r['entity_id']:r for r in conversion.identities};edits=[]
        fields={'node':{'temperature':('initial_temperature','temperature'),'capacity':('mass_value','capacity')},
                'conductor':{'conductance':('value','conductance')},'load':{'power':('value','power')},'submodel':{}}
        for identifier,entity in after.items():
            prior=before[identifier];allowed=fields[prior['kind']]
            if {k:v for k,v in entity.items() if k not in allowed}!={k:v for k,v in prior.items() if k not in allowed}:reject('td_native_edit_unmapped_field')
            changes={}
            for key,(source,dimension) in allowed.items():
                if entity[key]!=prior[key]:
                    _,scale,offset=BUNDLE['units'][getattr(staged.units,dimension)]
                    changes[source]=(entity[key]['value']-offset)/scale
            if changes:edits.append({'handle':identities[identifier]['handle'],'changes':changes})
        if edits:replacements,reports,verdict,reopened=self._prepare_fields(staged,destination,edits,work,limits)
        else:
            # Use the same overlap/new-tree checks without requesting a rewrite.
            destination=Path(destination).absolute();work=Path(work).absolute()
            if work.exists() or not work.parent.is_dir() or any(is_link(p) for p in (work,*work.parents)):reject('td_source_edit_new_tree')
            for a,b in ((work,staged.original.root),(work,destination),(destination,staged.original.root)):
                if a.resolve().is_relative_to(b.resolve()) or b.resolve().is_relative_to(a.resolve()):reject('td_source_edit_overlap')
            staged.original.check_current(limits);replacements={};reports=[];verdict={'edited_roundtrip_verified':True,'edited_objects':0};reopened=staged.snapshot
        drawing=replacements.get(staged.original.entry,dict(staged.original.files)[staged.original.entry])
        converted=convert_network(reopened,staged.units,sha256(drawing).hexdigest());actual=converted.require_native()
        keys=lambda row:('submodel',row['submodel']) if row['kind']=='submodel' else (row['kind'],row['handle'])
        actual_keys={keys(r):r['entity_id'] for r in converted.identities}
        mapping={r['entity_id']:actual_keys[keys(r)] for r in conversion.identities}
        equivalent_entities(target,actual,mapping,annotations=True)
        # Preserve the edited canonical annotations in explicitly identified
        # companion files; they never override freshly decoded thermal values.
        canonical=encode(target)
        receipt={'operation':'td-write-model','profile':'td-constant-network-writer/1',
                 'canonical_input_sha256':sha256(canonical).hexdigest(),'drawing_sha256':sha256(drawing).hexdigest(),
                 'identities':[{**row,**({'handle':str(row['handle'])} if 'handle' in row else {})} for row in conversion.identities],
                 'independent_reopen_verified':True,
                 'vendor_runtime_required':False,'qualified':False,'native_ready':True}
        additions={}
        for name,raw in {'canonical.json':canonical,'identity-map.json':encode(receipt)}.items():
            (replacements if name in dict(staged.original.files) else additions)[name]=raw
        staged.original.copy_to(destination,limits=limits,replacements=replacements,additions=additions)
        return {'operation':'td-export-native','profile':'td-independent-network/1',**verdict,
                'canonical_roundtrip_verified':True,'changed_entities':len(edits),'native_ready':True,
                'original_unchanged':True,'vendor_runtime_required':False,'qualified':False,
                'scope':'Closed constant network; scalar edits and retained canonical annotations; full TD qualification pending'}

    def audit_rewrite(self,staged,work,*,limits=ProjectLimits()):
        if not isinstance(staged,DwgPreview):reject('independent_td_preview_required')
        work=Path(work).absolute()
        if (work.exists() or not work.parent.is_dir() or any(is_link(p) for p in (work,*work.parents))
                or work.resolve().is_relative_to(staged.original.root.resolve())
                or staged.original.root.resolve().is_relative_to(work.resolve())):
            reject('independent_td_new_audit_tree')
        staged.original.check_current(limits);work.mkdir()
        before,derived,_=self.runtime.run('rewrite',dict(staged.original.files)[staged.original.entry],work/'write')
        after,_,_=self.runtime.run('inspect',derived,work/'reopen')
        staged.original.check_current(limits)
        return {'operation':'td-audit-rewrite','profile':self.profile,'source_revision':staged.original.source_hash,
                **compare(before,after),'promoted_to_user_export':False,
                'scope':'Private container preservation experiment; no TD thermal edit or native qualification'}
