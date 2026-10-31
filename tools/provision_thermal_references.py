# SPDX-License-Identifier: MIT OR Apache-2.0
"""Provision the isolated Windows Pycanha reference from exact public artifacts.

Third-party bytes and license notices stay in the local verification cache.
No vendor input, credentials, host installation or global Python is consulted.
"""
import base64
import csv
import hashlib
import io
import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def fetch(url, target, expected, size=None):
    if not url.startswith(("https://www.python.org/ftp/python/", "https://files.pythonhosted.org/")):
        raise ValueError("reference_download_origin")
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
        with urllib.request.urlopen(url, timeout=120) as stream: raw=stream.read((size or 800_000_000)+1)
        if (size is not None and len(raw)!=size) or hashlib.sha256(raw).hexdigest()!=expected:raise ValueError("reference_download_digest")
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    if size is not None and target.stat().st_size!=size:raise ValueError("reference_download_size")
    return target


def extract(archive, destination):
    with zipfile.ZipFile(archive) as stream:
        for name in stream.namelist():
            if not (destination/name).resolve().is_relative_to(destination.resolve()):raise ValueError("reference_archive_path")
        stream.extractall(destination)


def provision(work):
    policy=json.loads((ROOT/"ci/pycanha-reference-runtime.json").read_bytes())
    runtime=ROOT/".local/pycanha-reference";cache=ROOT/".local/pycanha-wheelhouse"
    cache.mkdir(parents=True,exist_ok=True)
    py=policy["python"];archive=fetch(py["url"],cache/"python-3.13.2-embed-amd64.zip",py["sha256"],py["bytes"])
    # Re-extract the small standard runtime each run, validating actual bytes.
    runtime.mkdir(parents=True,exist_ok=True);extract(archive,runtime)
    site=runtime/"Lib/site-packages";site.mkdir(parents=True,exist_ok=True)
    (runtime/"python313._pth").write_text("python313.zip\n.\nLib/site-packages\nimport site\n",encoding="ascii",newline="\n")
    pip=policy["bootstrap_pip"];wheel=fetch(pip["url"],cache/"pip-25.0.1-py3-none-any.whl",pip["sha256"]);extract(wheel,site)
    for item in policy["wheels"]:
        target=cache/item["filename"]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item["sha256"] and target.stat().st_size==item["bytes"]:continue
        with urllib.request.urlopen("https://pypi.org/pypi/"+item["name"]+"/"+item["version"]+"/json",timeout=60) as stream:metadata=json.load(stream)
        candidates=[a for a in metadata["urls"] if a["filename"]==item["filename"] and a["digests"]["sha256"]==item["sha256"] and a["size"]==item["bytes"] and not a.get("yanked")]
        if len(candidates)!=1:raise ValueError("reference_wheel_identity")
        fetch(candidates[0]["url"],target,item["sha256"],item["bytes"])
    executable=runtime/"python.exe"
    with (work/"pycanha-install.log").open("wb") as log:
        subprocess.run([str(executable),"-I","-m","pip","install","--no-index","--find-links",str(cache),"--only-binary=:all:","--require-hashes","-r",str(ROOT/"ci/pycanha-reference.lock")],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=300,check=True)
    return executable


def installed_digest(names):
    """Verify installed wheel RECORD hashes, then fingerprint the actual runtime.

    Called inside each interpreter; paths in the fingerprint never leave it.
    """
    import importlib.metadata
    records=[]
    for name in names:
        distribution=importlib.metadata.distribution(name)
        text=distribution.read_text("RECORD")
        if not text:raise ValueError("reference_record_missing")
        for entry,expected,size in csv.reader(io.StringIO(text)):
            # Derived interpreter caches are not wheel source. Reference children
            # use a fresh pycache prefix and -B, so these bytes are never loaded.
            if entry.endswith((".pyc",".pyo")):continue
            if not expected:continue
            algorithm,value=expected.split("=",1)
            if algorithm!="sha256":raise ValueError("reference_record_algorithm")
            path=distribution.locate_file(entry)
            raw=path.read_bytes();digest=hashlib.sha256(raw).digest()
            if base64.urlsafe_b64encode(digest).decode().rstrip("=")!=value or len(raw)!=int(size):raise ValueError("reference_installed_bytes_changed")
            records.append([name,distribution.version,entry,digest.hex()])
    return hashlib.sha256(json.dumps(sorted(records),separators=(",",":")).encode()).hexdigest()


if __name__=="__main__":
    if sys.argv[1:2]==["fingerprint"]:
        print(installed_digest(sys.argv[2:]))
    else:
        p=ROOT/".local/thermal-reference-provision";p.mkdir(exist_ok=True);provision(p)
