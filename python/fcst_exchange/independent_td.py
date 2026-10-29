# SPDX-License-Identifier: MIT OR Apache-2.0
"""Direct DWG inspection and complete immutable source copies without vendor APIs.

TD binary-class semantics are explicitly unresolved. No import or archive-copy
operation can turn an opaque drawing into a runnable canonical thermal model.
"""
from dataclasses import dataclass
from pathlib import Path
from fcst_app.persistence import is_link

from .core import reject
from .source_tree import capture_project,ProjectCopy,ProjectLimits
from .dwg_native import NativeRuntime,NativeSnapshot,compare


@dataclass(frozen=True)
class DwgPreview:
    original:ProjectCopy
    snapshot:NativeSnapshot

    @property
    def report(self):
        return {**self.snapshot.report,'source_revision':self.original.source_hash,
                'files':len(self.original.files),'directories':len(self.original.directories),
                'operations':{'inspect':True,'unchanged-source-export':True,
                              'thermal-native-reconstruction':False,'thermal-controlled-edit':False},
                'limitations':['td_class_serialization_layouts_unmapped','semantic_dependency_closure_unqualified']}

    def require_native(self):reject('independent_td_required_class_semantics_unmapped')


class IndependentTdAdapter:
    profile='td-independent-container/1'

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

    def export_source(self,staged,destination,edits=(),*,limits=ProjectLimits()):
        if not isinstance(staged,DwgPreview):reject('independent_td_preview_required')
        if edits:reject('independent_td_required_class_semantics_unmapped')
        staged.original.check_current(limits)
        target=staged.original.copy_to(destination,limits=limits)
        reopened=capture_project(target,staged.original.entry,limits=limits)
        if (reopened.files!=staged.original.files or reopened.directories!=staged.original.directories):
            reject('independent_td_source_copy_changed')
        return {'operation':'td-export-source','status':'retained-opaque','profile':self.profile,
                'source_revision':staged.original.source_hash,'files':len(reopened.files),
                'directories':len(reopened.directories),'exact_source_bytes_preserved':True,
                'vendor_runtime_required':False,'thermal_mapping':'unmapped','native_ready':False,'qualified':False}

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
