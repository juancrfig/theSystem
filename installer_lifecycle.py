#!/usr/bin/env python3
"""Ownership-based distribution cleanup; retain user edits and untracked knowledge."""
import hashlib
import json
import os
import sys
from pathlib import Path

# Keep the legacy glossary name valid for ownership manifests from older installations.
ALLOWED = ("AGENTS.md", "GLOSSARY.md", "GLOSSARY-MAP.md", "CONTEXT.md", "MANUAL.md", "README.md", "orchestrator",
           "the_system_orchestrator.py", "installer_lifecycle.py", "bootstrap", "install",
           "company_cli.py", "agents", ".githooks", "docs")

def identity(path):
    if path.is_symlink(): return ["symlink", os.readlink(path)]
    if path.is_file(): return ["file", hashlib.sha256(path.read_bytes()).hexdigest()]
    return None

def walk(root):
    for name in ALLOWED:
        start=root/name
        if not start.exists() and not start.is_symlink(): continue
        if start.is_file() or start.is_symlink():
            yield name, start
            continue
        for directory, subdirs, files in os.walk(start, followlinks=False):
            base=Path(directory)
            subdirs[:]=[d for d in subdirs if d not in (".git", "__pycache__")]
            for name2 in subdirs + files:
                if name2 in (".git", ".gitignore") or name2.endswith(".pyc"): continue
                item=base/name2
                if item.is_file() or item.is_symlink(): yield str(item.relative_to(root)), item

def manifest_path(root): return root/".thesystem"/"managed.json"

def snapshot(source,target):
    managed={}
    for rel,item in walk(source):
        actual=target/rel
        mark=identity(item)
        if mark is not None and mark==identity(actual): managed[rel]=mark
    path=manifest_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version":1,"entries":managed},sort_keys=True,indent=2)+"\n")
    os.replace(tmp,path)
    print(f"tracked {len(managed)} managed files")

def clean(target):
    path=manifest_path(target)
    if not path.is_file(): raise SystemExit("refusing removal without ownership manifest")
    data=json.loads(path.read_text())
    if data.get("version")!=1 or not isinstance(data.get("entries"),dict): raise SystemExit("invalid ownership manifest")
    removed=0; retained=[]
    for rel,expected in data["entries"].items():
        parts=Path(rel).parts
        if not parts or parts[0] not in ALLOWED or ".." in parts or Path(rel).is_absolute():
            raise SystemExit("unsafe ownership manifest path")
        item=target/rel
        if not item.parent.resolve().is_relative_to(target.resolve()): raise SystemExit("unsafe symlink parent")
        if identity(item)==expected:
            item.unlink();removed+=1
        elif item.exists() or item.is_symlink(): retained.append(rel)
    # Never delete a non-empty or untracked directory.
    for name in ALLOWED:
        item=target/name
        if item.is_dir() and not item.is_symlink():
            dirs=sorted((p for p in item.rglob('*') if p.is_dir() and not p.is_symlink()),key=lambda x:len(x.parts),reverse=True)
            for directory in [*dirs,item]:
                try: directory.rmdir()
                except OSError: pass
    print(json.dumps({"removed":removed,"retained_modified":retained},sort_keys=True))

if __name__=="__main__":
    if len(sys.argv) not in (3,4): raise SystemExit("usage: installer_lifecycle.py snapshot SOURCE TARGET | clean TARGET")
    action=sys.argv[1]
    if action=="snapshot" and len(sys.argv)==4: snapshot(Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())
    elif action=="clean" and len(sys.argv)==3: clean(Path(sys.argv[2]).resolve())
    else: raise SystemExit("invalid lifecycle action")
