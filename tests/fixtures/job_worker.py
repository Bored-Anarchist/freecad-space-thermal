# SPDX-License-Identifier: MIT OR Apache-2.0
"""Synthetic lifecycle peer. Never a thermal solver or owned-physics evidence."""
import json
import os
from pathlib import Path
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "python"))
from fcst_contracts import VERSION, frame, unframe
from fcst_app.jobs import reference
from fcst_app.persistence import encode

scenario, root, job_id = sys.argv[1:]
root = Path(root)
(root / "worker.pid").write_text(str(os.getpid()))
request = json.loads((root / "request.json").read_bytes())
job = request["job"]
if job["resume"]:
    scenario = "resume"
sequence = 0


def emit(kind, payload):
    global sequence
    sys.stdout.buffer.write(frame({"contract_version":VERSION, "type":kind, "job_id":job_id,
                                  "sequence":sequence,"payload":payload}))
    sys.stdout.buffer.flush()
    sequence += 1


emit("handshake", {"capabilities":{"contract_version":VERSION,"minimum_reader":VERSION,
     "operations":["job.submit","job.cancel"],"solver_available":False,"execution_mode":"fcst_native"}})
header = sys.stdin.buffer.read(4)
submit = unframe(header+sys.stdin.buffer.read(struct.unpack("<I",header)[0]))
assert submit["job_id"] == job_id and submit["sequence"] == 1
sequence = 2
if scenario == "crash":
    os._exit(17)
if scenario == "memory":
    bytearray(1024*1024*1024)
    raise SystemExit(19)
if scenario == "oversize":
    sys.stdout.buffer.write(struct.pack("<I",65537))
    sys.stdout.buffer.flush()
    os._exit(0)
if scenario in {"hang", "cancel", "race", "checkpoint"}:
    emit("progress",{"stage":"solve","fraction":.5})
    if scenario == "checkpoint":
        data = encode({"format":1,"time":1,"event_index":2,"control":True,"seed":job["seeds"][0],
                       "backend":job["execution"],"state":[3,4]})
        (root / "checkpoint.json").write_bytes(data)
        emit("checkpoint",{"snapshot_hash":job["semantic_hash"],"build_hash":job["execution"]["build_hash"],
             "case_id":job["case_id"],"time":{"value":1,"unit":"s"},"state":reference("checkpoint.json",data),
             "sequence":sequence})
    if scenario == "race":
        while not (root / "cancel.frame").exists():
            time.sleep(.01)
    else:
        while True:
            if scenario != "hang" and (root / "cancel.frame").exists():
                unframe((root / "cancel.frame").read_bytes())
                emit("cancel",{})
                emit("terminal",{"outcome":"cancelled"})
                raise SystemExit(0)
            time.sleep(.01)
if scenario == "failed":
    emit("terminal",{"outcome":"failed"})
    raise SystemExit(0)
if scenario == "resume":
    checkpoint = json.loads((root / "resume/state").read_bytes())
    assert checkpoint["time"] == 1 and checkpoint["event_index"] == 2 and checkpoint["control"]
    assert checkpoint["seed"] == job["seeds"][0] and checkpoint["backend"] == job["execution"]

# The acceptance driver supplies a prevalidated synthetic HDF5 fixture; this
# standard-library peer only tests lifecycle transport and never computes physics.
data = (root / "fixture/result.h5").read_bytes()
(root / "output.h5").write_bytes(data)
manifest = json.loads((root / "fixture/result.json").read_bytes())
manifest.update(id=job_id, project_id=job["project_id"],case_id=job["case_id"],
                revision=job["revision"],semantic_hash=job["semantic_hash"],build_hash=job["execution"]["build_hash"],
                execution_mode=job["execution"]["mode"],adapter=job["execution"]["backend"],data=reference("output.h5",data))
if scenario == "mismatch":
    manifest["revision"] += 1
if scenario == "partial":
    (root / "output.h5").write_bytes(data[:20])
raw = encode(manifest)
(root / "result.json").write_bytes(raw)
emit("terminal",{"outcome":"succeeded","result":reference("result.json",raw)})
if scenario == "late":
    emit("progress",{"stage":"write","fraction":1})
if scenario == "trailing":
    sys.stdout.buffer.write(b"x")
    sys.stdout.buffer.flush()
if scenario == "badexit":
    raise SystemExit(3)
