# SPDX-License-Identifier: MIT OR Apache-2.0
"""Recover the locked XML from its original public GitLab mirror, without altering the baseline."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request
import urllib.error
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from fcst_exchange.core import reject
from fcst_exchange.vendor_paths import checked_path
from fcst_exchange.export import rename_new
from fcst_exchange.esatan_xml import inspect_postprocess_xml


def acquire(destination):
    profile=json.loads((ROOT/'ci/esatan-acquisition.json').read_bytes())
    pointer=ROOT/profile['pointer_path']
    raw=pointer.read_bytes()
    if sha256(raw).hexdigest()!=profile['pointer_sha256']: reject('esatan_pointer_changed')
    match=re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\r?\noid sha256:([0-9a-f]{64})\r?\nsize (\d+)\r?\n',raw)
    if not match or match[1].decode()!=profile['payload_sha256'] or int(match[2])!=profile['payload_bytes']:
        reject('esatan_pointer_binding')
    destination=Path(destination).absolute()
    if destination.exists() or not destination.parent.is_dir(): reject('esatan_requires_new_target')
    checked_path(destination.parent,destination.name)
    fd,name=tempfile.mkstemp(prefix='.esatan-acquire-',dir=destination.parent); temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as output:
            with urllib.request.urlopen(profile['source_url'],timeout=60) as response:
                count=0; digest=sha256()
                while True:
                    chunk=response.read(1048576)
                    if not chunk: break
                    count+=len(chunk)
                    if count>profile['payload_bytes']: reject('esatan_acquisition_length')
                    digest.update(chunk); output.write(chunk)
            output.flush(); os.fsync(output.fileno())
        if count!=profile['payload_bytes'] or digest.hexdigest()!=profile['payload_sha256']:
            reject('esatan_acquisition_hash')
        with temporary.open('rb') as stream: result=inspect_postprocess_xml(stream)
        rename_new(temporary,destination)
        return {'status':'acquired','payload_sha256':digest.hexdigest(),'bytes':count,
                'family':'postprocessing-xml','elements':result['elements'],'qualified':False}
    finally:
        if temporary.exists(): temporary.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    try: result=acquire(args.destination)
    except (OSError,ValueError):
        print('{"status":"held","reason":"xml_acquisition_unavailable"}'); return 1
    print(json.dumps(result)); return 0


if __name__=='__main__': raise SystemExit(main())
