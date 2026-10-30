# SPDX-License-Identifier: MIT OR Apache-2.0
"""Direct DWG inspection and complete immutable source copies without vendor APIs.

Typed versioned payloads permit guarded source-field edits. Whole-model
semantic closure is assessed separately and is never inferred from parsing.
"""
from dataclasses import dataclass
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

    @property
    def report(self):
        inventory=decode_drawing(self.snapshot)
        properties=[]
        for name,raw in self.original.files:
            if Path(name).suffix.lower() in {'.tdp','.rco'}:
                try:properties.append(parse_properties(raw,Path(name).suffix.lower()[1:]).report)
                except ExchangeError as error:properties.append({'status':'retained-opaque','limitation':error.code})
        return {**self.snapshot.report,'source_revision':self.original.source_hash,
                'thermal_payloads':inventory.report,'property_databases':properties,
                'files':len(self.original.files),'directories':len(self.original.directories),
                'operations':{'inspect':True,'unchanged-source-export':True,
                              'thermal-native-reconstruction':False,'thermal-controlled-edit':False,
                              'guarded-source-field-export':bool(inventory.payloads or properties)},
                'limitations':['required_td_class_semantics_incomplete','semantic_dependency_closure_unqualified']}

    def require_native(self):reject('independent_td_required_class_semantics_unmapped')


class IndependentTdAdapter:
    profile='td-independent-payloads/2'

    def __init__(self,runtime):
        if not isinstance(runtime,NativeRuntime):reject('independent_dwg_backend_required')
        self.runtime=runtime

    def preview(self,root,entry,work,*,limits=ProjectLimits()):
        original=capture_project(root,entry,limits=limits);work=Path(work).absolute()
        if (work.resolve().is_relative_to(original.root.resolve())
                or original.root.resolve().is_relative_to(work.resolve())
                or self.runtime.executable.resolve().is_relative_to(original.root.resolve())):
            reject('independent_td_control_source_overlap')
        decoded,_,_=self.runtime.run('inspect',dict(original.files)[original.entry],work)
        original.check_current(limits)
        return DwgPreview(original,decoded)

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
                seen.add(handle);payload=payloads[handle];row,report=payload.edited_record(edit['changes'])
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
        work.mkdir();verdict={'edited_roundtrip_verified':True,'edited_objects':0}
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
        staged.original.copy_to(destination,limits=limits,replacements=replacements)
        return {'operation':'td-export-source-fields','profile':self.profile,'status':'source-fields-edited',
                'source_revision':staged.original.source_hash,'files':len(staged.original.files),
                'edited_files':len(replacements),'edits':reports,**verdict,
                'unrequested_source_files_preserved':True,'vendor_runtime_required':False,
                'native_ready':False,'qualified':False,
                'scope':'Guarded serialized scalar fields; full thermal model execution remains unqualified'}

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
