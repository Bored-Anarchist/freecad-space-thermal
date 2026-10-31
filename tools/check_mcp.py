# SPDX-License-Identifier: MIT OR Apache-2.0
"""WP-14 offline wire/SDK/native parity acceptance; raw logs remain local."""
import argparse
import asyncio
from copy import deepcopy
from hashlib import sha256
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'python'),str(ROOT/'tests')]
from fcst_app.persistence import encode, semantic_hash
from fcst_app.store import ProjectStore
from fcst_host import review
from fcst_mcp.server import PREFIX
from fcst_mcp import PROTOCOL
from fcst_tools.gate import evaluate
from test_mcp import MCPTests, fixture, metadata, CASE

WORKER=None


def input_hashes():
    paths=[*(ROOT/'python/fcst_mcp').glob('*.py'),ROOT/'tools/check_mcp.py',ROOT/'tests/test_mcp.py',
        ROOT/'python/fcst_app/jobs.py',ROOT/'python/fcst_host/review.py',ROOT/'engine/src/contracts.cpp',
        ROOT/'ci/mcp-acceptance.json',ROOT/'ci/mcp-requirements.lock',ROOT/'spec/mcp/2026-07-28.schema.json',ROOT/'spec/mcp/LICENSE']
    return {p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def assess(report,candidate,worker_sha256):
    policy=json.loads((ROOT/'ci/mcp-acceptance.json').read_bytes())
    if (report.get('candidate')!=candidate or report.get('input_sha256')!=input_hashes()
            or report.get('native_worker_sha256')!=worker_sha256 or report.get('gate',{}).get('status')!='passed'
            or report.get('protocols')!=policy['protocols'] or report.get('sdk')!=policy['sdk']
            or evaluate(policy['required_cases'],report.get('cases',[]))['status']!='passed'):
        raise ValueError('mcp_acceptance_stale_or_incomplete')


class Client:
    def __init__(self,config):
        env=dict(os.environ,PYTHONPATH=str(ROOT/'python'))
        self.process=subprocess.Popen([sys.executable,'-m','fcst_mcp','serve','--config',str(config)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.sequence=0;self.responses=queue.Queue()
        def read():
            for line in self.process.stdout:self.responses.put(json.loads(line))
        self.reader=threading.Thread(target=read,daemon=True);self.reader.start()

    def request(self,method,params=None):
        self.sequence+=1
        self.process.stdin.write(encode(dict(jsonrpc='2.0',id=self.sequence,method=method,
            params={'_meta':metadata(),**(params or {})}))+b'\n');self.process.stdin.flush()
        response=self.responses.get(timeout=30)
        if response.get('id')!=self.sequence:raise AssertionError('response_identity')
        if 'error' in response:raise AssertionError(response['error']['message'])
        return response['result']

    def call(self,name,args):
        result=self.request('tools/call',dict(name=name,arguments=args))
        if result.get('isError'):raise AssertionError(result['content'][0]['text'])
        return result['structuredContent']

    def close(self):
        self.process.stdin.close();self.process.wait(timeout=10);self.reader.join(timeout=5);self.process.stdout.close()
        if self.process.returncode:raise AssertionError('server_exit')


class MCPAcceptance(MCPTests):
    def setUp(self):
        super().setUp()
        # Detached schedulers close their database after a short idle lease.
        # Wait for that independently of stdio EOF before removing test storage.
        self.addCleanup(self.wait_service)

    def wait_service(self):
        time.sleep(3.5)

    def config(self,database='project.db'):
        config=self.root/'launch.json'
        config.write_bytes(encode(dict(database=database,worker=str(WORKER),policy=dict(
            project_id=self.policy.project_id,case_ids=[CASE],root=str(self.root),actor=self.policy.actor))))
        return config

    def test_modern_real_process_build_solve_reconnect_parity(self):
        # Build through a real client; the same review.change is used by the GUI.
        empty=fixture();empty['entities']=[]
        with ProjectStore.create(self.root/'client.db',empty):pass
        config=self.config('client.db');client=Client(config)
        try:
            self.assertEqual(client.request('server/discover')['resultType'],'complete')
            built=client.call('changes_apply',self.base|dict(idempotency_key='build',changes=dict(upsert=fixture()['entities'],delete=[])))
            self.assertEqual(built['semantic_hash'],semantic_hash(fixture()))
            node=deepcopy(next(e for e in fixture()['entities'] if e['kind']=='node'))
            node['temperature']['value']=315
            change=client.call('changes_apply',self.base|dict(expected_revision=1,idempotency_key='client-edit',changes=dict(upsert=[node],delete=[])))
            with ProjectStore.create(self.root/'gui.db',empty) as gui:
                gui.apply('local-workbench',{'changes.apply'},self.policy.project_id,0,'build',dict(upsert=fixture()['entities'],delete=[]))
                review.change(gui,node,expected_revision=1,key='client-edit')
                self.assertEqual(semantic_hash(gui.snapshot()),change['semantic_hash'])
                expected_model=gui.snapshot()
            options=review.DEFAULT_SETTINGS|dict(absolute_temperature_tolerance=1e-8,relative_temperature_tolerance=0)
            args=dict(project_id=self.policy.project_id,expected_revision=2,idempotency_key='native-solve',case_id=CASE,options=options)
            first=client.call('solve_submit',args)
            self.assertEqual(first['execution_mode'],'fcst_native')
            # EOF disconnect leaves durable work running in its separate service.
        finally:client.close()
        client=Client(config)
        try:
            replay=client.call('solve_submit',args)
            self.assertEqual(first['job_id'],replay['job_id'])
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                job=client.call('jobs_get',dict(project_id=self.policy.project_id,job_id=first['job_id']))
                if job['state'] in {'succeeded','failed','interrupted','cancelled'}:break
                time.sleep(.05)
            self.assertEqual(job['state'],'succeeded',job)
            ids=[e['id'] for e in expected_model['entities'] if e['kind']=='node']
            data=client.call('results_query',dict(project_id=self.policy.project_id,job_id=job['job_id'],quantity='temperature',entity_ids=ids))
            flag,payload=review.request(expected_model,options,CASE)
            native=subprocess.run([str(WORKER),flag],input=encode(payload),capture_output=True,timeout=30)
            self.assertEqual(native.returncode,0)
            expected=review.validate_result(json.loads(native.stdout),expected_model)
            self.assertFalse(expected['native']['step_records_included'])
            self.assertEqual(expected['native']['steps'],[])
            self.assertGreater(expected['native']['step_count'],0)
            self.assertEqual(data['values'],[s['temperature_K'] for s in expected['samples']])
            # Independent closed-form two-node conduction, conserved energy.
            for t,values in zip(data['time'],data['values']):
                equilibrium=(2*315+3*290)/5
                delta=25*math.exp(-4*(1/2+1/3)*t)
                self.assertAlmostEqual(values[0],equilibrium+3/5*delta,delta=3e-4)
                self.assertAlmostEqual(values[1],equilibrium-2/5*delta,delta=3e-4)
                self.assertAlmostEqual(2*values[0]+3*values[1],2*315+3*290,delta=1e-5)
            ref=client.call('balances_get',dict(project_id=self.policy.project_id,job_id=job['job_id']))
            self.assertIn('contents',client.request('resources/read',dict(uri=ref['uri'])))
            self.assertEqual(client.call('jobs_cancel',dict(project_id=self.policy.project_id,job_id=job['job_id']))['state'],'succeeded')
            # Transport-level cancellation notification cannot change job truth.
            client.process.stdin.write(encode(dict(jsonrpc='2.0',method='notifications/cancelled',params=dict(requestId=1)))+b'\n');client.process.stdin.flush()
            self.assertEqual(client.call('jobs_get',dict(project_id=self.policy.project_id,job_id=job['job_id']))['state'],'succeeded')
        finally:client.close()

    def test_official_sdk_legacy_real_client(self):
        self.assertEqual(importlib.metadata.version('mcp'),'1.26.0')
        config=self.config()
        async def workflow():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            parameters=StdioServerParameters(command=sys.executable,args=['-m','fcst_mcp','serve','--config',str(config)],
                env=dict(os.environ,PYTHONPATH=str(ROOT/'python')))
            with (self.root/'sdk.log').open('w') as log:
                async with stdio_client(parameters,errlog=log) as (reader,writer):
                    async with ClientSession(reader,writer) as session:
                        initialized=await session.initialize()
                        self.assertEqual(initialized.protocolVersion,'2025-11-25')
                        names=[];cursor=None
                        while True:
                            result=await session.list_tools(cursor=cursor);names += [t.name for t in result.tools]
                            cursor=result.nextCursor
                            if cursor is None:break
                        self.assertIn('solve_submit',names)
                        result=await session.call_tool('project_inspect',self.base)
                        self.assertFalse(result.isError)
                        self.assertEqual(result.structuredContent['semantic_hash'],semantic_hash(fixture()))
                        resources=await session.list_resources()
                        resource=await session.read_resource(resources.resources[0].uri)
                        self.assertEqual(len(resource.contents),1)
        asyncio.run(asyncio.wait_for(workflow(),timeout=25))

    def test_native_queued_cancel_and_service_restart_truth(self):
        from fcst_mcp.service import backend
        from fcst_mcp.gateway import Gateway
        gateway=Gateway(self.store,self.policy,backend=backend(WORKER))
        args=self.base|dict(case_id=CASE,idempotency_key='cancel',options=review.DEFAULT_SETTINGS)
        job=gateway.call('solve_submit',args)
        from fcst_mcp.server import Server
        server=Server(gateway)
        self.assertIsNone(server.handle(dict(jsonrpc='2.0',method='notifications/cancelled',params=dict(requestId=9))))
        self.assertEqual(gateway.job(job['job_id'])['state'],'queued')
        cancelled=gateway.call('jobs_cancel',dict(project_id=self.policy.project_id,job_id=job['job_id']))
        self.assertEqual(cancelled['state'],'cancelled')
        self.assertEqual(gateway.call('jobs_cancel',dict(project_id=self.policy.project_id,job_id=job['job_id'])),cancelled)
        from fcst_app.jobs import Scheduler
        with Scheduler(gateway.jobs,self.root/'runs',{}):pass
        self.assertEqual(gateway.job(job['job_id'])['state'],'cancelled')
        running=gateway.call('solve_submit',args|dict(idempotency_key='interrupted'))
        value=gateway.job(running['job_id']);value['state']='running';gateway.jobs._put(value)
        with Scheduler(gateway.jobs,self.root/'runs',{}):pass
        self.assertEqual(gateway.job(running['job_id'])['state'],'interrupted')

    def test_native_steady_case_uses_explicit_environment_and_publishes_results(self):
        node=deepcopy(next(e for e in fixture()['entities'] if e['id']==review.uid(5)))
        node['classification']='prescribed';node.pop('capacity')
        case=deepcopy(next(e for e in fixture()['entities'] if e['kind']=='case'));case['mode']='steady'
        self.store.apply('trusted',{'changes.apply'},self.policy.project_id,0,'steady',dict(upsert=[node,case],delete=[]))
        client=Client(self.config())
        try:
            job=client.call('solve_submit',self.base|dict(expected_revision=1,case_id=CASE,idempotency_key='steady',options=review.DEFAULT_SETTINGS))
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                job=client.call('jobs_get',dict(project_id=self.policy.project_id,job_id=job['job_id']))
                if job['state'] in {'succeeded','failed','interrupted'}:break
                time.sleep(.05)
            self.assertEqual(job['state'],'succeeded')
            values=client.call('results_query',dict(project_id=self.policy.project_id,job_id=job['job_id'],quantity='temperature',entity_ids=[review.uid(4),review.uid(5)]))
            self.assertEqual(values['values'],[[290,290]])
        finally:client.close()

    def test_live_job_cancel_is_independent_of_stdio_and_cannot_publish_partial(self):
        from fcst_mcp.gateway import Gateway
        from fcst_app.jobs import JobStore, Scheduler
        from test_jobs import execution, PEER
        identity=execution('hang')
        gateway=Gateway(self.store,self.policy,backend=dict(execution=identity))
        job=gateway.call('solve_submit',self.base|dict(case_id=CASE,idempotency_key='running-cancel',options=review.DEFAULT_SETTINGS))
        registry=dict(execution=gateway.job(job['job_id'])['execution'],command=[sys.executable,str(PEER),'hang'],
                      identity_file=str(PEER),resume_supported=False)
        failures=[]
        # The lifecycle peer tests cancellation only; it contributes no physics evidence.
        def run():
            try:
                with ProjectStore(self.store.path) as store:
                    with Scheduler(JobStore(store),self.root/'cancel-runs',{'fixture':registry}) as scheduler:scheduler.run_next()
            except Exception:failures.append('scheduler_failed')
        thread=threading.Thread(target=run);thread.start()
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            value=gateway.job(job['job_id'])
            if value['sequence']>=2:break
            time.sleep(.02)
        cancelled=gateway.call('jobs_cancel',dict(project_id=self.policy.project_id,job_id=job['job_id']))
        self.assertIn(cancelled['state'],{'cancelling','cancelled'})
        thread.join(timeout=10);self.assertFalse(thread.is_alive())
        self.assertFalse(failures);self.assertGreaterEqual(value['sequence'],2)
        result=gateway.call('jobs_get',dict(project_id=self.policy.project_id,job_id=job['job_id']))
        self.assertEqual(result['state'],'cancelled');self.assertIsNone(result['result_id'])
        with self.assertRaises(ValueError):gateway.result(job['job_id'])


def main():
    global WORKER
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',type=Path,required=True)
    parser.add_argument('--report',type=Path,default=ROOT/'.local/mcp.json')
    args=parser.parse_args();WORKER=args.worker.resolve()
    records=[];logs=ROOT/'.local/mcp-logs';logs.mkdir(parents=True,exist_ok=True)
    policy=json.loads((ROOT/'ci/mcp-acceptance.json').read_bytes())
    names=policy['required_cases']
    for name in names:
        stream=io.StringIO();result=unittest.TextTestRunner(stream=stream).run(unittest.TestSuite([MCPAcceptance(name)]))
        (logs/(name+'.log')).write_text(stream.getvalue(),encoding='utf-8')
        records.append(dict(id=name,status='passed' if result.wasSuccessful() and not result.skipped else 'failed'))
        print(name+': '+records[-1]['status'],flush=True)
    report=dict(work_package='WP-14',protocols=[PROTOCOL,'2025-11-25'],sdk='mcp==1.26.0',
        candidate=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        scope='Local typed automation and native thermal CLI parity; no vendor or integrated P0 qualification',
        native_worker_sha256=sha256(WORKER.read_bytes()).hexdigest(),
        input_sha256=input_hashes(),
        gate=evaluate(names,records),cases=records)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_bytes(encode(report)+b'\n')
    print(json.dumps(report['gate']));return 0 if report['gate']['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
