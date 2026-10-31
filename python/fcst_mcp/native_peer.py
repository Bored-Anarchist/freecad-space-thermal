# SPDX-License-Identifier: MIT OR Apache-2.0
"""Job-protocol adapter to the compiled thermal CLI; no Python thermal solver."""
from hashlib import sha256
import os
from pathlib import Path
import struct
import subprocess
import sys
import threading
import uuid

if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fcst_contracts import VERSION, frame, unframe, loads, read
from fcst_app.persistence import encode, reject
from fcst_app.jobs import reference
from fcst_app.arrays import write_arrays
from fcst_host import review


def run(worker,expected_hash,root,job_id):
    root=Path(root); worker=Path(worker)
    if sha256(worker.read_bytes()).hexdigest()!=expected_hash: reject('backend_build_changed')
    job=loads((root/'request.json').read_bytes())['job']
    from fcst_mcp.service import runtime_identity
    if runtime_identity(worker)!=job['execution']['dependencies']:reject('backend_build_changed')
    model=read('model',loads((root/'snapshots/model.json').read_bytes()))
    sequence=0
    def emit(kind,payload):
        nonlocal sequence
        sys.stdout.buffer.write(frame(dict(contract_version=VERSION,type=kind,job_id=job_id,sequence=sequence,payload=payload)))
        sys.stdout.buffer.flush(); sequence+=1
    emit('handshake',dict(capabilities=dict(contract_version=VERSION,minimum_reader=VERSION,
        operations=['job.submit','job.cancel'],solver_available=False,execution_mode='fcst_native')))
    header=sys.stdin.buffer.read(4)
    submit=unframe(header+sys.stdin.buffer.read(struct.unpack('<I',header)[0]))
    if submit['job_id']!=job_id or submit['sequence']!=1: reject('snapshot_binding')
    sequence=2
    flag,request=review.request(model,job['execution']['settings'],job['case_id'])
    # Drain both pipes continuously; a noisy or hostile binary cannot exhaust memory.
    process=subprocess.Popen([str(worker),flag],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env={**{k:os.environ[k] for k in ('SystemRoot','WINDIR') if k in os.environ},'PATH':str(worker.parent)},
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    output=bytearray(); exceeded=threading.Event()
    def drain(pipe,keep):
        count=0
        while data:=pipe.read(8192):
            count+=len(data)
            if count>job['budget']['artifact_bytes']:
                exceeded.set();process.kill();break
            if keep: output.extend(data)
    readers=[threading.Thread(target=drain,args=(process.stdout,True)),threading.Thread(target=drain,args=(process.stderr,False))]
    for thread in readers: thread.start()
    try:
        process.stdin.write(encode(request));process.stdin.close()
        process.wait(timeout=job['budget']['wall_s'])
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)
        for thread in readers:thread.join(timeout=5)
        process.stdout.close();process.stderr.close()
    if process.returncode or exceeded.is_set():
        emit('terminal',dict(outcome='failed'));return
    result=review.validate_result(loads(bytes(output)),model)
    samples=result['samples']; ids=result['node_ids']
    arrays={'index/node_uuid':[list(uuid.UUID(i).bytes) for i in ids],
        'time':[s['time_s'] for s in samples], 'temperature':[s['temperature_K'] for s in samples]}
    if all('boundary_power_W' in s for s in samples):arrays['power']=[s['boundary_power_W'] for s in samples]
    # Residual vectors can exclude prescribed nodes. Map by native equation UUID.
    if all('residual_W' in s for s in samples):
        equation_ids=result['native']['equation_node_ids']
        arrays['residual']=[[dict(zip(equation_ids,s['residual_W'])).get(i,0) for i in ids] for s in samples]
    data=write_arrays('result',job['semantic_hash'],arrays)
    (root/'output.h5').write_bytes(data)
    manifest=dict(contract_version=VERSION,minimum_reader=VERSION,id=job_id,project_id=job['project_id'],
        case_id=job['case_id'],revision=job['revision'],semantic_hash=job['semantic_hash'],build_hash=job['execution']['build_hash'],
        execution_mode='fcst_native',adapter=job['execution']['backend'],outcome='succeeded',data=reference('output.h5',data),
        node_ids=ids,time_count=len(samples),quantities=sorted(k for k in arrays if k not in {'index/node_uuid','time'}),diagnostics=[])
    raw=encode(read('result',manifest));(root/'result.json').write_bytes(raw)
    emit('terminal',dict(outcome='succeeded',result=reference('result.json',raw)))


if __name__=='__main__':
    try:run(*sys.argv[1:])
    except (OSError,ValueError,subprocess.SubprocessError):raise SystemExit(2)
