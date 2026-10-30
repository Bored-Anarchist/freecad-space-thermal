# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded source trees with Windows vendor filenames; never shell commands."""
import os
from pathlib import Path, PurePosixPath
import re
from .core import reject, Limits
from fcst_app.persistence import is_link


def path_name(name):
    if (not isinstance(name,str) or not 0 < len(name) <= 240 or '\\' in name
            or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_ .()/-]*",name)):
        reject("unsafe_path")
    reserved = {"CON","PRN","AUX","NUL",*[f"COM{i}" for i in range(1,10)],*[f"LPT{i}" for i in range(1,10)]}
    if any(p in {"",".",".."} or p.endswith(("."," ")) or p.split(".")[0].upper() in reserved for p in name.split('/')):
        reject("unsafe_path")
    return name


def checked_path(root,name):
    path_name(name)
    root=Path(root).absolute(); path=root/name
    if any(is_link(p) for p in (path,*path.parents)) or not path.resolve().is_relative_to(root.resolve()):
        reject("linked_or_unsafe_path")
    if path.is_file() and path.stat().st_nlink != 1:
        reject("linked_path")
    return path


def preservation_check(root,sources,limits=Limits()):
    root=Path(root).absolute(); expected={s.path for s in sources}
    expected_dirs={str(p) for n in expected for p in PurePosixPath(n).parents if str(p)!='.'}
    files=set(); dirs=set(); pending=[(root,0)]; count=0
    try:
        while pending:
            parent,depth=pending.pop()
            if depth>limits.include_depth:return "preservation_limit"
            with os.scandir(parent) as entries:
                for entry in entries:
                    count+=1
                    if count>limits.files*4:return "preservation_limit"
                    p=Path(entry.path); name=path_name(p.relative_to(root).as_posix())
                    if is_link(p):return "linked_path"
                    if entry.is_dir(follow_symlinks=False):
                        dirs.add(name);pending.append((p,depth+1))
                    elif entry.is_file(follow_symlinks=False):
                        files.add(name)
                        if name not in expected:return "undeclared_source_content"
                    else:return "unsupported_source_entry"
    except (OSError,ValueError):return "preservation_unavailable"
    return "" if files==expected and dirs==expected_dirs else "undeclared_source_content"
