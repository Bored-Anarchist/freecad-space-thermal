# SPDX-License-Identifier: MIT OR Apache-2.0
"""Vendor names map to safe package paths; exact original bytes stay unchanged."""
from hashlib import sha256
from pathlib import Path
from fcst_app.persistence import Package,encode
from .core import target_id,reject


def package_sinda(staged):
    model=staged.require_native()
    files={'model.json':encode(model),'exchange/fidelity.json':staged.report_bytes}
    aliases={source.path:'source/'+sha256(source.path.encode()).hexdigest()+'.original' for source in staged.sources}
    ids={name:target_id(('vendor-original',name)) for name in aliases}
    graph={row['path']:row['includes'] for row in staged.report['dependencies']}
    records=[]
    for source in staged.sources:
        name=aliases[source.path];files[name]=source.content
        records.append({'id':ids[source.path],'role':'source_original' if source.path==staged.entry else 'source_dependency',
                        'artifact':{'path':name,'sha256':sha256(source.content).hexdigest(),'byte_length':len(source.content)},
                        'dependencies':[ids[child] for child in graph[source.path]]})
    files['exchange/source-map.json']=encode({'source_paths':aliases,'source_revision':staged.report['source_revision']})
    model_id=target_id(('vendor-model',model['project_id']))
    for name in ('model.json','exchange/fidelity.json','exchange/source-map.json'):
        records.append({'id':model_id if name=='model.json' else target_id(('vendor-evidence',name)),
                        'role':'model' if name=='model.json' else 'evidence',
                        'artifact':{'path':name,'sha256':sha256(files[name]).hexdigest(),'byte_length':len(files[name])},
                        'dependencies':list(ids.values()) if name=='model.json' else []})
    return Package({'contract_version':'2.0.0','minimum_reader':'2.0.0','project_id':model['project_id'],'revision':model['revision'],
                    'model_artifact_id':model_id,'artifacts':records},files)
