# SPDX-License-Identifier: MIT OR Apache-2.0
"""Immutable DWG project trees shared by independent and reference adapters.

No vendor discovery, registry, assembly or executable dependency is imported.
"""
from dataclasses import dataclass
from hashlib import sha256
import math
import os
from pathlib import Path
import shutil
import tempfile
from fcst_app.persistence import encode
from .core import reject
from .vendor_paths import path_name,checked_path
from .export import rename_new

@dataclass(frozen=True)
class ProjectLimits:
    files:int=2048
    file_bytes:int=67108864
    total_bytes:int=268435456
    include_depth:int=32
    timeout_seconds:float=180
    log_bytes:int=1048576
    memory_mb:int=4096

    def __post_init__(self):
        if (any(type(getattr(self,k)) is not int or getattr(self,k)<=0 for k in ('files','file_bytes','total_bytes','include_depth','log_bytes','memory_mb'))
                or not math.isfinite(self.timeout_seconds) or not 0<self.timeout_seconds<=1800 or self.memory_mb>16384):reject('td_limits')


@dataclass(frozen=True)
class ProjectCopy:
    root:Path
    entry:str
    files:tuple
    directories:tuple=()

    @property
    def source_hash(self):return sha256(encode({'files':[{'path':name,'sha256':sha256(raw).hexdigest()} for name,raw in self.files],'directories':list(self.directories)})).hexdigest()

    @property
    def drawing_hash(self):return sha256(dict(self.files)[self.entry]).hexdigest()

    def check_current(self,limits=ProjectLimits()):
        current=capture_project(self.root,self.entry,limits=limits)
        if current.files!=self.files or current.directories!=self.directories:reject('stale_td_project')

    def copy_to(self,destination,limits=ProjectLimits(),*,replacements=None,additions=None):
        destination=Path(destination).absolute()
        if destination.exists() or destination.resolve().is_relative_to(self.root.resolve()) or self.root.resolve().is_relative_to(destination.resolve()):reject('td_requires_new_tree')
        self.check_current(limits)
        replacements={} if replacements is None else replacements
        if (not isinstance(replacements,dict) or set(replacements)-set(dict(self.files))
                or any(not isinstance(v,bytes) or len(v)>limits.file_bytes for v in replacements.values())):reject('td_invalid_replacements')
        additions={} if additions is None else additions
        if not isinstance(additions,dict):reject('td_invalid_additions')
        seen={name.casefold() for name,_ in self.files}|{name.casefold() for name in self.directories}
        for name,raw in additions.items():
            path_name(name)
            if name.casefold() in seen or not isinstance(raw,bytes) or len(raw)>limits.file_bytes:reject('td_invalid_additions')
            seen.add(name.casefold())
        expected=tuple(sorted([(name,replacements.get(name,raw)) for name,raw in self.files]+list(additions.items())))
        if len(expected)>limits.files:reject('td_file_limit')
        directories=set(self.directories)
        for name in additions:
            directories.update(p.as_posix() for p in Path(name).parents if p.as_posix()!='.')
        directories=tuple(sorted(directories))
        if sum(len(raw) for _,raw in expected)>limits.total_bytes:reject('td_byte_limit')
        if not destination.parent.is_dir():reject('td_destination_parent')
        checked_path(destination.parent,destination.name)
        temporary=Path(tempfile.mkdtemp(prefix='.fcst-td-',dir=destination.parent))
        try:
            for name in directories:(temporary/path_name(name)).mkdir(parents=True,exist_ok=True)
            for name,raw in expected:
                path=temporary/path_name(name);path.parent.mkdir(parents=True,exist_ok=True)
                with path.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            current=capture_project(temporary,self.entry,limits=limits)
            if current.files!=expected or current.directories!=directories:reject('td_copy_verification')
            self.check_current(limits)
            rename_new(temporary,destination)
        finally:
            if temporary.exists():
                if temporary.resolve().parent!=destination.parent.resolve() or not temporary.name.startswith('.fcst-td-'):reject('unsafe_cleanup')
                shutil.rmtree(temporary)
        return destination


def capture_project(root,entry,limits=ProjectLimits()):
    root=Path(root).absolute();path_name(entry)
    entry_path=checked_path(root,entry)
    if not entry_path.is_file() or entry_path.suffix.lower()!='.dwg':reject('td_drawing_required')
    files=[];directories=[];total=0;seen=set();pending=[(root,0)];count=0
    while pending:
        parent,depth=pending.pop()
        if depth>limits.include_depth:reject('td_tree_depth')
        with os.scandir(parent) as entries:
            for entry_data in entries:
                count+=1
                if count>limits.files*4:reject('td_file_limit')
                path=Path(entry_data.path);name=path.relative_to(root).as_posix();checked_path(root,name)
                if name.casefold() in seen:reject('td_path_collision')
                seen.add(name.casefold())
                if entry_data.is_dir(follow_symlinks=False):directories.append(name);pending.append((path,depth+1));continue
                if not entry_data.is_file(follow_symlinks=False):reject('td_unsafe_entry')
                if len(files)>=limits.files:reject('td_file_limit')
                with path.open('rb') as stream:raw=stream.read(limits.file_bytes+1)
                total+=len(raw)
                if len(raw)>limits.file_bytes or total>limits.total_bytes:reject('td_byte_limit')
                files.append((name,raw))
    entry=next((name for name,_ in files if name.casefold()==entry.casefold()),None)
    if entry is None or not dict(files)[entry].startswith(b'AC10'):reject('dwg_container_signature')
    return ProjectCopy(root,entry,tuple(sorted(files)),tuple(sorted(directories)))


