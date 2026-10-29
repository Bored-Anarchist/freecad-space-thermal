# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pinned source preparation for the separate GPL native DWG executable."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tarfile


def digest(path):
    h=sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(1048576):h.update(block)
    return h.hexdigest()


def safe_name(name):
    value=PurePosixPath(name)
    if (value.is_absolute() or not name or '..' in value.parts or '\\' in name
            or ':' in name or any(p in {'','.'} or p.endswith((' ','.'))
                                 or p.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
                                 for p in name.split('/'))):
        raise ValueError('unsafe_backend_source_path')
    return value


def linked(path):
    return path.is_symlink() or bool(getattr(path.lstat(),'st_file_attributes',0)&0x400)


def apply_patch(root,raw,images):
    """Apply only the exact reviewed pre/post images, without a shell or git."""
    lines=raw.decode('utf-8').splitlines(keepends=True);position=0;seen=set()
    while position<len(lines):
        if not lines[position].startswith('--- a/'):raise ValueError('backend_patch_header')
        name=lines[position][6:].rstrip('\r\n');safe_name(name);position+=1
        if position>=len(lines) or lines[position].rstrip('\r\n')!='+++ b/'+name or name in seen or name not in images:
            raise ValueError('backend_patch_paths')
        position+=1;seen.add(name);path=Path(root)/name
        if any(linked(p) for p in (path,*path.parents)) or digest(path)!=images[name]['before']:raise ValueError('backend_patch_preimage')
        source=path.read_text(encoding='utf-8').splitlines(keepends=True);result=[];cursor=0
        while position<len(lines) and lines[position].startswith('@@ '):
            m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[position])
            if not m:raise ValueError('backend_patch_hunk')
            start=int(m[1])-1;old_count=int(m[2] or 1);new_count=int(m[4] or 1)
            if start<cursor or start>len(source):raise ValueError('backend_patch_range')
            result.extend(source[cursor:start]);cursor=start;position+=1;old=0;new=0
            while position<len(lines) and not lines[position].startswith(('@@ ','--- a/')):
                line=lines[position];position+=1
                if not line or line[0] not in ' +-':raise ValueError('backend_patch_line')
                if line[0] in ' -':
                    if cursor>=len(source) or source[cursor]!=line[1:]:raise ValueError('backend_patch_context')
                    cursor+=1;old+=1
                if line[0] in ' +':result.append(line[1:]);new+=1
            if old!=old_count or new!=new_count:raise ValueError('backend_patch_counts')
        result.extend(source[cursor:]);data=''.join(result).encode()
        if sha256(data).hexdigest()!=images[name]['after']:raise ValueError('backend_patch_postimage')
        path.write_bytes(data)
    if seen!=set(images):raise ValueError('backend_patch_missing_file')


def prepare_source(archive,destination,patch,images):
    """Hash every source member; cached additions/modifications never get built."""
    destination=Path(destination);expected={};names=set();total=0;members=[]
    if any(linked(p) for p in (destination,*destination.parents) if p.exists()):raise ValueError('backend_source_link')
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            name=member.name.rstrip('/');safe_name(name)
            if not name.startswith('libredwg-0.14/'):continue
            name=name[len('libredwg-0.14/'):]
            if not name:continue
            safe_name(name)
            if name.casefold() in names:raise ValueError('backend_source_alias')
            names.add(name.casefold())
            if not (member.isfile() or member.isdir()) or member.size>67108864:raise ValueError('backend_source_type')
            total+=member.size
            if len(names)>30000 or total>536870912:raise ValueError('backend_source_budget')
            if member.isfile():
                data=stream.extractfile(member).read();expected[name]=sha256(data).hexdigest()
            members.append((name,member))
        if not destination.exists():
            destination.mkdir(parents=True)
            for name,member in members:
                path=destination/name
                if member.isdir():path.mkdir(parents=True,exist_ok=True)
                else:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with path.open('xb') as out:out.write(stream.extractfile(member).read())
            apply_patch(destination,Path(patch).read_bytes(),images)
    for name,image in images.items():
        if expected.get(name)!=image['before']:raise ValueError('backend_archive_preimage')
        expected[name]=image['after']
    actual={}
    for path in destination.rglob('*'):
        if linked(path) or path.stat().st_nlink>1 and path.is_file():raise ValueError('backend_source_link')
        if path.is_file():actual[path.relative_to(destination).as_posix()]=digest(path)
    if actual!=expected:raise ValueError('backend_cached_source_changed')
    return sha256(json.dumps(expected,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def seal_tree(root):
    result={}
    for path in Path(root).rglob('*'):
        if linked(path):raise ValueError('backend_toolchain_link')
        if path.is_file():result[path.relative_to(root).as_posix()]=digest(path)
    return result
