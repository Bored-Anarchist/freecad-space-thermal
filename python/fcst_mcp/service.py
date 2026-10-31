# SPDX-License-Identifier: MIT OR Apache-2.0
"""Independent durable scheduler: stdio cancellation/EOF has no job authority."""
from copy import deepcopy
from hashlib import sha256
import os
import importlib.metadata
import platform
from pathlib import Path
import subprocess
import sys
import time

from fcst_contracts import loads
from fcst_app.jobs import JobStore, Scheduler
from fcst_app.persistence import reject
from fcst_app.store import ProjectStore
from .policy import Policy


def runtime_identity(worker):
    root=Path(__file__).resolve().parents[1]
    files=[*Path(__file__).parent.glob('*.py'),root/'fcst_host/review.py',
        *[root/'fcst_app'/name for name in ('jobs.py','store.py','persistence.py','arrays.py','process_limits.py')],
        root/'fcst_contracts/__init__.py',root/'fcst_contracts/bundle.json']
    from fcst_app.persistence import encode
    sources={p.relative_to(root).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    return dict(native_worker_sha256=sha256(Path(worker).read_bytes()).hexdigest(),
        adapter_source_sha256=sha256(encode(sources)).hexdigest(),python=platform.python_version(),
        **{name:importlib.metadata.version(name) for name in ('h5py','numpy','jsonschema')})


def backend(worker):
    worker=Path(worker).resolve(); peer=Path(__file__).with_name('native_peer.py')
    return dict(command=[sys.executable,str(peer),str(worker),sha256(worker.read_bytes()).hexdigest()],
        identity_file=str(peer),resume_supported=False,
        execution=dict(profile='native-thermal-cli/1',features=['steady','transient'],mode='fcst_native',backend='native-thermal',
            build_hash=sha256(peer.read_bytes()).hexdigest(),settings={},dependencies=runtime_identity(worker)))


def configuration(path):
    value=loads(Path(path).read_bytes())
    if not isinstance(value,dict) or set(value)-{'database','worker','policy'} or not {'database','policy'}<=value.keys():reject('configuration')
    settings=dict(value['policy']);settings['root']=Path(settings['root']);settings['case_ids']=frozenset(settings['case_ids'])
    for key in ('max_memory_mb','max_artifact_bytes','max_active_jobs','max_response_bytes'):
        if key in settings:
            if type(settings[key]) not in (int,float) or int(settings[key])!=settings[key]:reject('policy_budget')
            settings[key]=int(settings[key])
    policy=Policy(**settings)
    # Database is trusted launch config, but must still lie inside the authorized root.
    database=policy.path(value['database'])
    return value,database,policy,backend(value['worker']) if value.get('worker') else None


def wake(config):
    # No visible window, no inherited stdio, no shell, no model-supplied argv.
    process=subprocess.Popen([sys.executable,'-m','fcst_mcp','service','--config',str(Path(config).resolve())],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=(subprocess.CREATE_NO_WINDOW|subprocess.DETACHED_PROCESS) if os.name=='nt' else 0)
    return process


def run(config):
    _,database,policy,base=configuration(config)
    if base is None:reject('backend_unavailable')
    with ProjectStore(database) as store:
        jobs=JobStore(store)
        with Scheduler(jobs,policy.root/'mcp-runs',{}) as scheduler:
            idle=time.monotonic()
            while time.monotonic()-idle<3:
                rows=[loads(r[0]) for r in store.db.execute('SELECT record FROM jobs ORDER BY rowid')]
                job=next((j for j in rows if j['state']=='queued'),None)
                if job is None:time.sleep(.05);continue
                if job['actor']!=policy.actor or job['case_id'] not in policy.case_ids:
                    reject('case_scope')
                expected=deepcopy(base);expected['execution']['settings']=job['execution']['settings']
                from fcst_host.review import settings
                settings(job['execution']['settings']);policy.budget(job['budget'])
                if expected['execution']!=job['execution']:
                    jobs.finish(job['id'],'failed','backend_build_changed');continue
                scheduler.backends={job['execution']['backend']:expected}
                scheduler.run_next();idle=time.monotonic()
