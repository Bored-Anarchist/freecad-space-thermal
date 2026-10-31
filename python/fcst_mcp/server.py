# SPDX-License-Identifier: MIT OR Apache-2.0
"""Bounded UTF-8 JSON-RPC stdio, modern metadata and a separate legacy profile."""
from copy import deepcopy
import json
import re
import sqlite3

from fcst_contracts import loads, ContractError
from fcst_app.persistence import encode, PersistenceError, reject
from fcst_exchange import ExchangeError
from . import PROTOCOL, LEGACY, VERSION
from .schemas import TOOLS

PREFIX='io.modelcontextprotocol/'
INFO=dict(name='fcst',version=VERSION)
CAPS=dict(tools={},resources={})
MAX_FRAME=1048576


class RPCError(Exception):
    def __init__(self,code,message,data=None):
        self.code,self.message,self.data=code,message,data


class Server:
    def __init__(self,gateway):
        self.gateway=gateway
        self.legacy=False
        self.initialized=False

    def handle(self,message):
        request_id=None
        try:
            if (not isinstance(message,dict) or message.get('jsonrpc')!='2.0'
                    or not isinstance(message.get('method'),str)
                    or set(message)-{'jsonrpc','id','method','params'}):
                raise RPCError(-32600,'Invalid request')
            request_id=message.get('id')
            if 'id' in message and (type(request_id) not in (str,int,float) or isinstance(request_id,float) and not request_id.is_integer()):
                request_id=None;raise RPCError(-32600,'Invalid request')
            if isinstance(request_id,float):request_id=int(request_id)
            params=message.get('params',{})
            if not isinstance(params,dict):raise RPCError(-32602,'Invalid params')
            method=message['method']
            if 'id' not in message:
                if method=='notifications/initialized' and self.legacy:self.initialized=True
                # Transport cancellation never cancels an application job. All
                # synchronous RPCs finish before the next input frame is read.
                return None
            meta=params.get('_meta',{})
            modern=isinstance(meta,dict) and PREFIX+'protocolVersion' in meta
            if method=='initialize' and not modern:
                if self.legacy:raise RPCError(-32600,'Already initialized')
                if (params.get('protocolVersion')!=LEGACY or not isinstance(params.get('capabilities'),dict)
                        or not isinstance(params.get('clientInfo'),dict)):
                    raise RPCError(-32602,'Supported legacy revision: '+LEGACY)
                self.legacy=True
                result=dict(protocolVersion=LEGACY,capabilities=CAPS,serverInfo=INFO)
            else:
                if modern:
                    version=meta[PREFIX+'protocolVersion']
                    if version!=PROTOCOL:raise RPCError(-32022,'Unsupported protocol version',dict(supported=[PROTOCOL,LEGACY],requested=version))
                    if not isinstance(meta.get(PREFIX+'clientCapabilities'),dict):raise RPCError(-32602,'Invalid params')
                elif not (self.legacy and self.initialized):
                    raise RPCError(-32602,'Per-request metadata required; supported '+PROTOCOL+' and '+LEGACY)
                result=self.dispatch(method,{k:v for k,v in params.items() if k!='_meta'},modern)
                if modern:
                    result=dict(resultType='complete',**result)
                    result['_meta']={PREFIX+'serverInfo':INFO}
                    if method in {'server/discover','tools/list','resources/list','resources/read','resources/templates/list'}:
                        result.update(cacheScope='private',ttlMs=0)
            response=dict(jsonrpc='2.0',id=request_id,result=result)
            if len(encode(response))>self.gateway.policy.max_response_bytes:raise RPCError(-32603,'Response limit')
            return response
        except RPCError as error:
            item=dict(code=error.code,message=error.message)
            if error.data is not None:item['data']=error.data
            return dict(jsonrpc='2.0',id=request_id,error=item)
        except (ValueError,OSError,KeyError,TypeError,sqlite3.Error):
            return dict(jsonrpc='2.0',id=request_id,error=dict(code=-32602,message='Invalid params'))

    def dispatch(self,method,params,modern):
        g=self.gateway
        if method=='ping':return {}
        if method=='server/discover':return dict(supportedVersions=[PROTOCOL,LEGACY],capabilities=CAPS)
        if method=='tools/list':
            if set(params)-{'cursor'}:raise RPCError(-32602,'Invalid params')
            cursor=params.get('cursor','0')
            if not isinstance(cursor,str) or not re.fullmatch(r'[0-9]{1,4}',cursor):raise RPCError(-32602,'Invalid cursor')
            start=int(cursor);names=sorted(TOOLS);items=[];end=start
            for name in names[start:]:
                tool=deepcopy(TOOLS[name])
                if len(encode(items+[tool]))>g.policy.max_response_bytes-1024:
                    if not items:raise RPCError(-32603,'Response limit')
                    break
                items.append(tool);end+=1
            result=dict(tools=items)
            if end<len(names):result['nextCursor']=str(end)
            return result
        if method=='tools/call':
            if set(params)-{'name','arguments'} or params.get('name') not in TOOLS:
                raise RPCError(-32602,'Unknown tool or invalid params')
            try:
                value=g.call(params['name'],params.get('arguments',{}))
                return dict(content=[dict(type='text',text=encode(value).decode())],structuredContent=value,isError=False)
            except (PersistenceError,ContractError,ExchangeError) as error:
                code=error.diagnostic.code if isinstance(error,ContractError) else error.code
                return dict(content=[dict(type='text',text=encode(dict(code=code)).decode())],isError=True)
        if method=='resources/templates/list':
            return dict(resourceTemplates=[dict(name='Versioned entities',uriTemplate='fcst://projects/{project_id}/revisions/{revision}/entities/{entity_id}',mimeType='application/json')])
        if method=='resources/list':
            if params:raise RPCError(-32602,'Invalid params')
            m=g.store.snapshot();base=f"fcst://projects/{g.policy.project_id}/revisions/{int(m['revision'])}"
            return dict(resources=[dict(uri=base+'/summary',name='Project summary',mimeType='application/json'),
                                   dict(uri=base+'/diagnostics',name='Diagnostics',mimeType='application/json'),
                                   dict(uri=base+'/audit',name='Redacted audit',mimeType='application/json')])
        if method=='resources/read':
            if set(params)!={'uri'} or not isinstance(params['uri'],str):raise RPCError(-32602,'Invalid params')
            uri=params['uri']
            match=re.fullmatch(r'fcst://projects/([a-f0-9-]{36})/revisions/([0-9]{1,12})/(summary|diagnostics|audit|entities/[a-f0-9-]{36}|artifacts/[a-f0-9-]{36})(?:\?offset=([0-9]{1,9})&limit=([0-9]{1,2}))?',uri)
            if not match:raise RPCError(-32602,'Invalid resource')
            project,revision,part,offset,limit=match.groups();revision=int(revision)
            if project!=g.policy.project_id:raise RPCError(-32002,'Resource unavailable')
            m=g.store.snapshot();base=dict(project_id=project,expected_revision=revision)
            if revision!=m['revision'] and not part.startswith('artifacts/'):raise RPCError(-32002,'Resource revision unavailable')
            try:
                if part=='summary':value=g.call('project_inspect',base)
                elif part=='diagnostics':value=g.call('model_validate',base)
                elif part=='audit':
                    start,count=int(offset or 0),int(limit or 16)
                    if not 1<=count<=64:raise RPCError(-32602,'Invalid page')
                    rows=g.db.execute('SELECT sequence,data FROM mcp_audit WHERE sequence>? ORDER BY sequence LIMIT ?',(start,count)).fetchall()
                    value=dict(events=[loads(r[1]) for r in rows],next_offset=rows[-1][0] if rows else None)
                elif part.startswith('entities/'):
                    value=g.call('object_get',base|dict(entity_id=part.split('/')[1]))
                else:
                    row=g.db.execute('SELECT revision,actor,cases,data FROM mcp_resources WHERE id=?',(part.split('/')[1],)).fetchone()
                    if (row is None or row[0]!=revision or row[1]!=g.policy.actor
                            or not set(loads(row[2]))<=g.policy.case_ids):raise RPCError(-32002,'Resource unavailable')
                    raw=row[3];start,count=int(offset or 0),int(limit or 64)
                    if not 1<=count<=64:raise RPCError(-32602,'Invalid page')
                    # Byte pages are explicit JSON envelopes; no implicit screenshots.
                    chunk=raw[start:start+count*512]
                    import base64
                    value=dict(encoding='base64',offset=start,data=base64.b64encode(chunk).decode(),
                               next_offset=start+len(chunk) if start+len(chunk)<len(raw) else None)
                return dict(contents=[dict(uri=uri,mimeType='application/json',text=encode(value).decode())])
            except (PersistenceError,ContractError):raise RPCError(-32002,'Resource unavailable')
        raise RPCError(-32601,'Method not found')


def serve(gateway,input_stream,output_stream):
    server=Server(gateway)
    while True:
        raw=input_stream.readline(MAX_FRAME+1)
        if not raw:return
        if len(raw)>MAX_FRAME:
            # Fail closed and exit; do not parse a suffix as another request.
            output_stream.write(encode(dict(jsonrpc='2.0',id=None,error=dict(code=-32600,message='Frame limit')))+b'\n')
            output_stream.flush();return
        try:message=loads(raw)
        except (ValueError,UnicodeError):
            response=dict(jsonrpc='2.0',id=None,error=dict(code=-32700,message='Parse error'))
        else:response=server.handle(message)
        if response is not None:
            output_stream.write(encode(response)+b'\n');output_stream.flush()
