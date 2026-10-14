"""Versioned query scopes. No credentials and no implicit schedule enablement."""
from pathlib import Path
import copy
import os
import re
import tempfile
from urllib.parse import urlencode
import yaml
from src.acquisition.projects import load_projects
from src.storage.file_lock import file_lock


class ThreadsRegistry:
    def __init__(self,directory):
        self.directory=Path(directory);self.path=self.directory/'threads.yaml'
        self.data=yaml.safe_load(self.path.read_text(encoding='utf-8')) if self.path.exists() else None
        if self.data is not None:self.validate(self.data)

    def validate(self,data):
        if not isinstance(data,dict) or data.get('schema_version')!='threads-config-v1':raise ValueError('Invalid Threads config')
        if type(data.get('version')) is not int or data['version']<1 or type(data.get('enabled')) is not bool:raise ValueError('Invalid Threads version/enabled')
        if data.get('provider') not in {'THREADS_BROWSER','THREADS_API'}:raise ValueError('Invalid Threads provider')
        if any(k in data for k in ('token','cookie','password','api_key')):raise ValueError('Use env/profile credentials')
        projects=load_projects(self.directory);seen=set()
        for row in data.get('queries',[]):
            key=row.get('query_id')
            if not isinstance(key,str) or not re.fullmatch(r'threads_[a-z0-9_]+',key) or key in seen:raise ValueError('Invalid query ID')
            seen.add(key)
            if row.get('project_id') not in projects or not projects[row['project_id']]['enabled']:raise ValueError('Invalid query project')
            if row.get('type') not in {'KEYWORD','TAG_TEXT'} or not isinstance(row.get('value'),str) or not 1<=len(row['value'].strip())<=150:raise ValueError('Invalid query text/type')
            if type(row.get('version')) is not int or row['version']<1:raise ValueError('Invalid query version')
            for flag in ('enabled','ambiguous','archived'):
                if type(row.get(flag)) is not bool:raise ValueError('Invalid query flag')
        if not seen:raise ValueError('Query registry required')
        bounds={'candidates_per_query':(1,1000),'pages_per_query':(1,50),'replies_per_conversation':(1,100),
                'rescan_roots':(0,100),'seconds_per_query':(10,300),'seconds_per_run':(10,1200)}
        for key,(low,high) in bounds.items():
            value=data.get('limits',{}).get(key)
            if type(value) is not int or not low<=value<=high:raise ValueError('Invalid Threads budget')
        value=data.get('limits',{}).get('unverified_conversations_per_query',2)
        if type(value) is not int or not 0<=value<=20:raise ValueError('Invalid unverified conversation budget')

    def write(self,data,expected_version):
        with file_lock(self.directory/'.threads.lock'):self._write(data,expected_version)

    def _write(self,data,expected_version):
        current=ThreadsRegistry(self.directory)
        if current.data['version']!=expected_version:raise ValueError('QUERY_VERSION_CONFLICT')
        self.validate(data)
        fd,name=tempfile.mkstemp(dir=self.directory,prefix='.threads-',suffix='.tmp')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                yaml.safe_dump(data,stream,allow_unicode=True,sort_keys=False);stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.path)
        finally:Path(name).unlink(missing_ok=True)
        self.data=data

    def update_queries(self,rows,expected_version):
        data=copy.deepcopy(self.data);known={q['query_id']:q for q in data['queries']}
        if not isinstance(rows,list) or not 1<=len(rows)<=50:raise ValueError('Invalid query list')
        for row in rows:
            key=row.get('query_id');previous=known.get(key)
            if not set(row)<={'query_id','project_id','type','value','enabled','ambiguous','archived'}:raise ValueError('Invalid query edit fields')
            known[key]={**(previous or {'version':0,'ambiguous':False,'archived':False}),**row,'version':(previous or {}).get('version',0)+1}
        data.update(queries=list(known.values()),version=data['version']+1)
        self.write(data,expected_version);return self.data

    def sources(self):
        if not self.data:return {}
        checked=self.data.get('verification',{});ready=checked.get('search_recent')=='SUPPORTED'
        return {q['query_id']:dict(source_id=q['query_id'],name=q['value'],platform='threads',source_type='THREADS_SEARCH',
            url='https://www.threads.com/search?'+urlencode({'q':q['value']}),query=q['value'],query_version=q['version'],
            project_id=q['project_id'],enabled=bool(self.data['enabled'] and q['enabled'] and not q['archived']),
            access_verified=ready,verification_status='VERIFIED' if ready else 'PENDING_VERIFICATION',
            requires_login=self.data['provider']=='THREADS_BROWSER',access_type='PUBLIC') for q in self.data['queries']}
