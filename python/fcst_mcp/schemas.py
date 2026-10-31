# SPDX-License-Identifier: MIT OR Apache-2.0
"""Closed operation schemas; references resolve only inside the owned bundle."""
from copy import deepcopy
from fcst_contracts import BUNDLE


def obj(properties, required=None):
    return dict(type='object', properties=properties,
                required=list(properties) if required is None else required, additionalProperties=False)


TEXT = dict(type='string', minLength=1, maxLength=128)
UUID = dict(type='string', format='uuid')
REV = dict(type='integer', minimum=0)
PAGE = dict(offset=REV, limit=dict(type='integer', minimum=1, maximum=64))
BOUND = dict(project_id=UUID, expected_revision=REV)
KEY = dict(idempotency_key=TEXT)
DEFS = BUNDLE['schemas']['model']['$defs']
ENTITY = BUNDLE['schemas']['model']['properties']['entities']['items']
CHANGES = obj(dict(upsert=dict(type='array', items=ENTITY, maxItems=256),
                   delete=dict(type='array', items=UUID, maxItems=256)))
PATH = dict(type='string', minLength=1, maxLength=256)


def spec(name, args, result, required=None, *, edit=False):
    def bundle(schema):
        needed=set()
        def collect(value):
            if isinstance(value,dict):
                ref=value.get('$ref','')
                if ref.startswith('#/$defs/'):
                    key=ref.split('/')[-1]
                    if key not in needed:
                        needed.add(key);collect(DEFS[key])
                for key,child in value.items():
                    if key!='$defs':collect(child)
            elif isinstance(value,list):
                for child in value:collect(child)
        collect(schema)
        return deepcopy(schema)|({'$defs':{k:deepcopy(DEFS[k]) for k in sorted(needed)}} if needed else {})
    return dict(name=name, description='FCST '+name.replace('_',' '),
        inputSchema=bundle(obj(args, required)),outputSchema=bundle(result),
        annotations=dict(readOnlyHint=not edit, destructiveHint=edit,
                         idempotentHint=not edit or name in {'changes_apply','changes_undo','solve_submit','jobs_cancel',
                             'nodes_create','conductors_create','materials_assign','optics_assign','loads_assign','cases_create'},
                         openWorldHint=False))


SUMMARY = obj(dict(project_id=UUID, revision=REV, semantic_hash=TEXT, entity_count=REV))
CHANGE_RESULT = obj(dict(revision=REV, semantic_hash=TEXT, invalidated=dict(type='array', items=UUID)))
REF = obj(dict(uri=PATH, sha256=TEXT, byte_length=REV))
PAGE_RESULT = obj(dict(items=dict(type='array', maxItems=64), offset=REV,
                       next_offset=dict(anyOf=[REV, dict(type='null')]), revision=REV))
JOB = obj(dict(job_id=UUID, case_id=UUID, revision=REV, semantic_hash=TEXT,
               state=dict(enum=['queued','running','cancelling','succeeded','failed','cancelled','interrupted']),
               execution_mode=dict(const='fcst_native'), result_id=dict(anyOf=[UUID,dict(type='null')]),
               reason=dict(anyOf=[TEXT,dict(type='null')])))
TOOLS = {}


def add(name, args, result, required=None, **kw):
    TOOLS[name] = spec(name,args,result,required,**kw)


add('system_capabilities', {}, obj(dict(protocols=dict(type='array',items=TEXT), transport=dict(const='stdio'),
    tools=dict(type='array',items=TEXT), unavailable=dict(type='array',items=TEXT),
    execution_mode=dict(const='fcst_native'), network_listener=dict(const=False))))
add('schemas_get',dict(name=TEXT), obj(dict(schema=dict(type='object'))))
add('projects_list',{},obj(dict(projects=dict(type='array',items=SUMMARY,maxItems=1))))
add('project_inspect',BOUND,SUMMARY)
add('objects_query',BOUND|PAGE|dict(kind=TEXT),PAGE_RESULT,list(BOUND))
add('object_get',BOUND|dict(entity_id=UUID),obj(dict(entity=ENTITY,revision=REV)))
add('dependencies_inspect',BOUND|dict(entity_id=UUID),obj(dict(entity_id=UUID,references=dict(type='array',items=UUID))))
add('compatibility_inspect',BOUND,obj(dict(profiles=dict(type='array',items=dict(type='object')))))
add('changes_preview',BOUND|dict(changes=CHANGES),obj(dict(plan_id=UUID,plan_hash=TEXT,base_revision=REV)),edit=True)
add('changes_apply',BOUND|KEY|dict(changes=CHANGES,plan_id=UUID,plan_hash=TEXT),CHANGE_RESULT,
    list(BOUND)+list(KEY)+['changes'],edit=True)
add('changes_undo',BOUND|KEY|dict(revision=REV),CHANGE_RESULT,edit=True)
for name,kind in [('nodes_create','node'),('conductors_create','conductor'),('materials_assign','material'),
                  ('optics_assign','optics'),('loads_assign','load'),('cases_create','case')]:
    add(name,BOUND|KEY|dict(entity={'$ref':'#/$defs/'+kind}),CHANGE_RESULT,edit=True)
add('model_validate',BOUND,obj(dict(valid=dict(const=True),semantic_hash=TEXT)))
add('snapshot_create',BOUND|dict(destination=PATH|dict(description='New .fcst package inside the authorized root')),REF,edit=True)
OPTIONS = obj(dict(mode=dict(enum=['steady','transient']),start=dict(type='number',minimum=0),
    end=dict(type='number',exclusiveMinimum=0), samples=dict(type='integer',minimum=2,maximum=1001),
    absolute_temperature_tolerance=dict(type='number',exclusiveMinimum=0),
    relative_temperature_tolerance=dict(type='number',minimum=0)))
BUDGET = obj(dict(wall_s=dict(type='number',exclusiveMinimum=0),cancel_s=dict(type='number',exclusiveMinimum=0),
    memory_mb=dict(type='integer',minimum=32),artifact_bytes=dict(type='integer',minimum=1)))
add('solve_submit',BOUND|KEY|dict(case_id=UUID,options=OPTIONS,budget=BUDGET),JOB,
    list(BOUND)+list(KEY)+['case_id','options'],edit=True)
add('jobs_get',dict(project_id=UUID,job_id=UUID),JOB)
add('jobs_cancel',dict(project_id=UUID,job_id=UUID),JOB,edit=True)
add('results_query',dict(project_id=UUID,job_id=UUID,historical=dict(type='boolean'),quantity=dict(enum=['temperature','power','residual']),
    entity_ids=dict(type='array',items=UUID,minItems=1,maxItems=64),**PAGE),
    obj(dict(node_ids=dict(type='array',items=UUID),time=dict(type='array'),values=dict(type='array'),
        next_offset=dict(anyOf=[REV,dict(type='null')]),historical=dict(type='boolean'))),
    ['project_id','job_id','quantity','entity_ids'])
add('balances_get',dict(project_id=UUID,job_id=UUID,historical=dict(type='boolean')),REF,['project_id','job_id'])
add('results_compare',dict(project_id=UUID,left_job_id=UUID,right_job_id=UUID),
    obj(dict(max_temperature_difference_K=dict(type='number',minimum=0),same_snapshot=dict(type='boolean'))))
add('reports_generate',BOUND|dict(destination=PATH|dict(description='New .json report inside the authorized root')),REF,edit=True)
for name in ('import_preview','export_preview'):
    add(name,BOUND|dict(path=PATH),obj(dict(plan_id=UUID,plan_hash=TEXT,artifact_count=REV)),edit=True)
for name in ('import_submit','export_submit'):
    add(name,BOUND|dict(plan_id=UUID,plan_hash=TEXT,destination=PATH|dict(description='New .fcst package inside the authorized root')),REF,edit=True)
