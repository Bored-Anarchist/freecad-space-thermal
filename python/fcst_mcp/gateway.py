# SPDX-License-Identifier: MIT OR Apache-2.0
"""Typed facade over shared persistence/jobs; all caller text remains inert."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import uuid

from jsonschema import Draft202012Validator, FormatChecker
from fcst_contracts import BUNDLE, loads, read, normalize
from fcst_app.persistence import Package, encode, reject, semantic_hash, atomic_file, read_bounded
from fcst_app.store import references
from fcst_app.jobs import JobStore, reference
from . import VERSION, PROTOCOL, LEGACY
from .schemas import TOOLS

SCOPES=frozenset({'changes.apply','entity.create','changes.undo','job.submit','job.query','job.cancel','result.query'})
UNAVAILABLE=['mesh_submit','radiation_submit','viewport_capture','arbitrary_code','network_transport']


def checked(schema,value):
    if not Draft202012Validator(schema,format_checker=FormatChecker()).is_valid(value): reject('invalid_arguments')


class Gateway:
    def __init__(self,store,policy,*,backend=None,wake=None):
        if store.snapshot()['project_id']!=policy.project_id: reject('wrong_project')
        self.store,self.policy,self.backend,self.wake=store,policy,backend,wake
        self.jobs=JobStore(store)
        self.db=store.db
        self.db.execute('CREATE TABLE IF NOT EXISTS mcp_audit (sequence INTEGER PRIMARY KEY, data BLOB NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS mcp_exchange (id TEXT PRIMARY KEY, data BLOB NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS mcp_resources (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, actor TEXT NOT NULL, cases BLOB NOT NULL, data BLOB NOT NULL)')

    def summary(self):
        m=self.store.snapshot()
        return dict(project_id=m['project_id'],revision=m['revision'],semantic_hash=semantic_hash(m),entity_count=len(m['entities']))

    def audit(self,name,args,before,outcome):
        after=self.store.snapshot()['revision']
        event=dict(actor=self.policy.actor,provider=self.policy.provider,tool=name,version=VERSION,
            argument_sha256=sha256(encode(args)).hexdigest(),before_revision=before,after_revision=after,
            changes=[h['after_hash'] for h in self.store.state()['history'] if before<h['revision']<=after],outcome=outcome)
        self.db.execute('INSERT INTO mcp_audit(data) VALUES(?)',(encode(event),))

    def call(self,name,args):
        before=self.store.snapshot()['revision']
        # Reserve audit capacity before any consequential operation.
        if self.db.execute('SELECT count(*) FROM mcp_audit').fetchone()[0]>=10000: reject('audit_capacity')
        try:
            if name not in TOOLS: reject('unsupported_operation')
            checked(TOOLS[name]['inputSchema'],args)
            if 'project_id' in args and args['project_id']!=self.policy.project_id: reject('wrong_project')
            if 'expected_revision' in args and name not in {'changes_apply','changes_undo','solve_submit'}:
                if args['expected_revision']!=before: reject('stale_revision')
            if TOOLS[name]['annotations']['destructiveHint'] and not self.policy.allow_edits: reject('authorization_required')
            result=self.execute(name,deepcopy(args))
            checked(TOOLS[name]['outputSchema'],result)
            if len(encode(result))>self.policy.max_response_bytes//2: reject('response_limit')
            self.audit(name,args,before,'succeeded')
            return result
        except Exception as error:
            from fcst_app.persistence import PersistenceError
            from fcst_contracts import ContractError
            from fcst_exchange import ExchangeError
            code=error.code if isinstance(error,(PersistenceError,ExchangeError)) else (
                error.diagnostic.code if isinstance(error,ContractError) else 'operation_failed')
            self.audit(name,args,before,code)
            if isinstance(error,(PersistenceError,ContractError,ExchangeError)): raise
            reject(code)

    def resource(self,data,revision=None):
        raw=encode(data)
        if len(raw)>self.policy.max_artifact_bytes: reject('resource_budget')
        count,total=self.db.execute('SELECT count(*),coalesce(sum(length(data)),0) FROM mcp_resources').fetchone()
        if count>=128 or total+len(raw)>67108864:reject('resource_budget')
        key=str(uuid.uuid4()); revision=int(self.store.snapshot()['revision'] if revision is None else revision)
        self.db.execute('INSERT INTO mcp_resources VALUES(?,?,?,?,?)',(key,revision,self.policy.actor,encode(sorted(self.policy.case_ids)),raw))
        return dict(uri=f'fcst://projects/{self.policy.project_id}/revisions/{revision}/artifacts/{key}',
                    sha256=sha256(raw).hexdigest(),byte_length=len(raw))

    def job(self,key):
        value=self.jobs._get(key)
        self.jobs._authority(self.policy.actor,SCOPES,'job.query',value)
        self.policy.case(value['case_id'])
        return value

    @staticmethod
    def job_summary(value):
        return dict(job_id=value['id'],case_id=value['case_id'],revision=value['revision'],semantic_hash=value['semantic_hash'],
            state=value['state'],execution_mode=value['execution']['mode'],result_id=value['result']['id'] if value['result'] else None,
            reason=value['reason'])

    def result(self,key,historical=False):
        self.job(key)
        return self.jobs.result(self.policy.actor,SCOPES,key,historical=historical)

    def execute(self,name,a):
        m=self.store.snapshot(); p=self.policy; actor=p.actor
        if name=='system_capabilities':
            return dict(protocols=[PROTOCOL,LEGACY],transport='stdio',tools=sorted(TOOLS),unavailable=UNAVAILABLE,
                        execution_mode='fcst_native',network_listener=False)
        if name=='schemas_get':
            if a['name'] not in TOOLS: reject('unsupported_operation')
            return dict(schema=TOOLS[a['name']])
        if name=='projects_list': return dict(projects=[self.summary()])
        if name=='project_inspect': return self.summary()
        if name=='objects_query':
            items=sorted((e for e in m['entities'] if 'kind' not in a or e['kind']==a['kind']),key=lambda e:e['id'])
            offset,limit=int(a.get('offset',0)),int(a.get('limit',64))
            page=[]
            for item in items[offset:offset+limit]:
                if len(encode(page+[item]))>p.max_response_bytes//3:
                    if not page: reject('response_limit')
                    break
                page.append(item)
            end=offset+len(page)
            return dict(items=page,offset=offset,next_offset=end if end<len(items) else None,revision=m['revision'])
        if name in {'object_get','dependencies_inspect'}:
            entity=next((e for e in m['entities'] if e['id']==a['entity_id']),None)
            if entity is None: reject('unknown_entity')
            if name=='object_get': return dict(entity=entity,revision=m['revision'])
            return dict(entity_id=entity['id'],references=sorted(references(entity)-{entity['id']}))
        if name=='compatibility_inspect':
            from fcst_exchange.core import ReferenceAdapter
            return dict(profiles=[ReferenceAdapter().probe()])
        if name.startswith(('changes_','nodes_','conductors_','materials_','optics_','loads_','cases_')):
            operation='changes.undo' if name=='changes_undo' else 'changes.apply' if name.startswith('changes_') else 'entity.create'
            payload={'revision':a['revision']} if operation=='changes.undo' else a.get('changes',dict(upsert=[a.get('entity')],delete=[]))
            # A case-scoped client may edit shared entities, but may not create/edit/delete other cases.
            candidates=payload.get('upsert',[])+[e for e in m['entities'] if e['id'] in payload.get('delete',[])]
            candidates += [e for e in m['entities'] if e['id'] in {v['id'] for v in payload.get('upsert',[])}]
            if operation=='changes.undo':
                history=next((h for h in self.store.state()['history'] if h['revision']==a['revision']),None)
                if history: candidates += [e for e in history['inverse']['restore'].values() if e]+[
                    e for e in m['entities'] if e['id'] in history['inverse']['restore']]
            for e in candidates:
                if e['kind']=='case': p.case(e['id'])
            if name=='changes_preview':
                plan=self.store.preview(actor,SCOPES,p.project_id,a['expected_revision'],payload)
                return dict(plan_id=plan['id'],plan_hash=plan['hash'],base_revision=plan['base_revision'])
            return self.store.apply(actor,SCOPES,p.project_id,a['expected_revision'],a['idempotency_key'],payload,
                operation=operation,plan_id=a.get('plan_id'),plan_hash=a.get('plan_hash'))
        if name=='model_validate':
            read('model',m)
            return dict(valid=True,semantic_hash=semantic_hash(m))
        if name=='solve_submit':
            p.case(a['case_id'])
            if self.backend is None: reject('backend_unavailable')
            budget=p.budget(a.get('budget'))
            execution=deepcopy(self.backend['execution']); execution['settings']=a['options']
            value=self.jobs.submit(actor,SCOPES,a['idempotency_key'],a['case_id'],expected_revision=a['expected_revision'],
                                   execution=execution,budget=budget,max_active_jobs=p.max_active_jobs)
            if self.wake: self.wake()
            return self.job_summary(value)
        if name in {'jobs_get','jobs_cancel'}:
            value=self.job(a['job_id'])
            if name=='jobs_cancel': value=self.jobs.cancel(actor,SCOPES,value['id'])
            return self.job_summary(value)
        if name=='results_query':
            info=self.result(a['job_id'],a.get('historical',False))
            from fcst_app.arrays import read_arrays
            arrays=read_arrays(self.jobs.bytes(a['job_id'],'result/data'))['arrays']
            ids=info['manifest']['node_ids']; quantity=a['quantity']; selected=a['entity_ids']
            if quantity not in arrays or any(i not in ids for i in selected): reject('result_query')
            indices=[ids.index(i) for i in selected]
            start,count=int(a.get('offset',0)),int(a.get('limit',64)); end=min(start+count,len(arrays['time']))
            return dict(node_ids=selected,time=arrays['time'][start:end].tolist(),
                values=arrays[quantity][start:end][:,indices].tolist(),next_offset=end if end<len(arrays['time']) else None,
                historical=info['snapshot']!=m)
        if name=='balances_get':
            info=self.result(a['job_id'],a.get('historical',False))
            from fcst_app.arrays import read_arrays
            arrays=read_arrays(self.jobs.bytes(a['job_id'],'result/data'))['arrays']
            value=dict(job_id=a['job_id'],semantic_hash=info['job']['semantic_hash'],
                time_s=arrays['time'].tolist(),quantities=info['manifest']['quantities'])
            if 'power' in arrays:value['boundary_power_sum_W']=arrays['power'].sum(axis=1).tolist()
            if 'residual' in arrays:value['max_absolute_equation_residual_W']=abs(arrays['residual']).max(axis=1).tolist()
            return self.resource(value,info['job']['revision'])
        if name=='results_compare':
            left,right=(self.result(a[k],True) for k in ('left_job_id','right_job_id'))
            from fcst_app.arrays import read_arrays
            x,y=(read_arrays(self.jobs.bytes(a[k],'result/data'))['arrays'] for k in ('left_job_id','right_job_id'))
            if (left['manifest']['node_ids']!=right['manifest']['node_ids'] or x['temperature'].shape!=y['temperature'].shape
                    or not (x['time']==y['time']).all()): reject('comparison_identity')
            return dict(max_temperature_difference_K=float(abs(x['temperature']-y['temperature']).max()),
                        same_snapshot=left['job']['semantic_hash']==right['job']['semantic_hash'])
        if name in {'snapshot_create','reports_generate'}:
            if not p.allow_export: reject('authorization_required')
            target=p.path(a['destination'],new=True)
            if name=='snapshot_create':
                if any(x[1].startswith('source_') for x in self.store._artifacts()) and not p.allow_source_export:
                    reject('source_export_authorization')
                self.store.save(target)
            else:
                atomic_file(target,encode(dict(summary=self.summary(),qualification='unqualified',
                    jobs=[self.job_summary(loads(r[0])) for r in self.db.execute('SELECT record FROM jobs WHERE actor=?',(actor,))
                          if loads(r[0])['case_id'] in p.case_ids])))
            return self.resource(dict(destination=a['destination'],**reference(a['destination'],target.read_bytes())))
        if name in {'import_preview','export_preview'}:
            if name=='import_preview':
                package=Package.open(p.path(a['path']))
                if package.model['project_id']!=p.project_id: reject('wrong_project')
                for e in package.model['entities']:
                    if e['kind']=='case': p.case(e['id'])
                raw=read_bounded(p.path(a['path']),p.max_artifact_bytes)
                plan=dict(operation=name,source=a['path'],source_hash=sha256(raw).hexdigest(),revision=m['revision'],
                          model_hash=semantic_hash(m),actor=actor)
                count=len(package.manifest['artifacts'])
            else:
                p.path(a['path'],new=True)
                plan=dict(operation=name,destination=a['path'],revision=m['revision'],model_hash=semantic_hash(m),actor=actor)
                count=len(self.store.export_package().manifest['artifacts'])
            key=str(uuid.uuid4()); digest=sha256(encode(plan)).hexdigest()
            self.db.execute('INSERT INTO mcp_exchange VALUES(?,?)',(key,encode(plan)))
            return dict(plan_id=key,plan_hash=digest,artifact_count=count)
        if name in {'import_submit','export_submit'}:
            if not p.allow_export: reject('authorization_required')
            row=self.db.execute('SELECT data FROM mcp_exchange WHERE id=?',(a['plan_id'],)).fetchone()
            if not row or sha256(row[0]).hexdigest()!=a['plan_hash']: reject('invalid_plan')
            plan=loads(row[0])
            if (plan['actor']!=actor or plan['operation']!=name.replace('submit','preview')
                    or plan['revision']!=m['revision'] or plan['model_hash']!=semantic_hash(m)): reject('invalid_plan')
            target=p.path(a['destination'],new=True)
            if name=='import_submit':
                source=p.path(plan['source']); raw=read_bounded(source,p.max_artifact_bytes)
                if sha256(raw).hexdigest()!=plan['source_hash']: reject('stale_source')
                package=Package.open(source)
            else:
                if a['destination']!=plan['destination']: reject('invalid_plan')
                package=self.store.export_package()
            if any(item['role'].startswith('source_') for item in package.manifest['artifacts']) and not p.allow_source_export:
                reject('source_export_authorization')
            from fcst_app.persistence import save_package
            save_package(package,target)
            return self.resource(dict(destination=a['destination'],**reference(a['destination'],target.read_bytes())))
        reject('unsupported_operation')
