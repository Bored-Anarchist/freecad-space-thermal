# SPDX-License-Identifier: MIT OR Apache-2.0
"""Authority is supplied by the launcher, never by tools, model text or URIs."""
from dataclasses import dataclass
from pathlib import Path
from fcst_app.persistence import reject, is_link
from fcst_exchange.core import checked_path


@dataclass(frozen=True)
class Policy:
    project_id: str
    case_ids: frozenset[str]
    root: Path
    actor: str
    provider: str | None = None
    max_wall_s: float = 120
    max_memory_mb: int = 512
    max_artifact_bytes: int = 8388608
    max_active_jobs: int = 2
    max_response_bytes: int = 131072
    allow_edits: bool = True
    allow_export: bool = False
    allow_source_export: bool = False

    def __post_init__(self):
        import math
        import re
        import uuid
        uuid.UUID(self.project_id)
        for case in self.case_ids: uuid.UUID(case)
        if (not isinstance(self.case_ids,frozenset) or not self.case_ids
                or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',self.actor)
                or self.provider is not None and not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',self.provider)):
            reject('policy_identity')
        for value in (self.max_wall_s,self.max_memory_mb,self.max_artifact_bytes,self.max_active_jobs,self.max_response_bytes):
            if type(value) not in (int,float) or not math.isfinite(value) or value<=0: reject('policy_budget')
        if (self.max_wall_s>86400 or not 32<=self.max_memory_mb<=16384
                or self.max_artifact_bytes>8388608 or not 16384<=self.max_response_bytes<=1048576):
            reject('policy_budget')
        if (any(type(v) is not bool for v in (self.allow_edits,self.allow_export,self.allow_source_export))
                or any(type(v) is not int for v in (self.max_memory_mb,self.max_artifact_bytes,self.max_active_jobs,self.max_response_bytes))):
            reject('policy_budget')
        root=Path(self.root).absolute()
        if not root.is_dir() or any(is_link(p) for p in (root,*root.parents)): reject('policy_root')
        object.__setattr__(self,'root',root.resolve())

    def path(self, name, *, new=False):
        path=checked_path(self.root,name)
        if new and path.exists(): reject('new_destination_required')
        return path

    def case(self, case_id):
        if case_id not in self.case_ids: reject('case_scope')

    def budget(self, requested=None):
        value=requested or dict(wall_s=self.max_wall_s,cancel_s=2,memory_mb=self.max_memory_mb,
                                artifact_bytes=self.max_artifact_bytes)
        if (value['wall_s']>self.max_wall_s or value['memory_mb']>self.max_memory_mb
                or value['artifact_bytes']>self.max_artifact_bytes or value['cancel_s']>60):
            reject('resource_budget')
        return value
