"""Local single-instance supervisor: adopt existing workers, restart exits, catch up."""
import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from src.browser.profiles import PROJECT_ROOT, _pid_alive
from src.storage.file_lock import file_lock

RUNTIME = PROJECT_ROOT/'sessions/runtime'


def process_inventory():
    """Read only project Python processes; never log command lines or env values."""
    if os.name=='nt':
        script = "$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' -and $_.CommandLine -match 'engine.dashboard|engine.classification_worker' } | Select-Object ProcessId,CommandLine) | ConvertTo-Json -Compress"
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
            capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:raise RuntimeError('PROCESS_SCAN_FAILED')
        rows=json.loads(result.stdout or '[]')
        return rows if isinstance(rows,list) else [rows]
    result=subprocess.run(['ps','-eo','pid,args'],capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError('PROCESS_SCAN_FAILED')
    return [{'ProcessId':int(line.strip().split(None,1)[0]),'CommandLine':line.strip().split(None,1)[1]}
            for line in result.stdout.splitlines()[1:] if len(line.strip().split(None,1))==2]


class Supervisor:
    def __init__(self, port=8765, runtime=RUNTIME, root=PROJECT_ROOT, inventory=process_inventory, launch=None):
        self.port,self.runtime,self.root=port,Path(runtime),Path(root)
        self.inventory=inventory;self.launch=launch or self._launch
        self.workers={};self.attempts={};self.next_start={};self.children=[]
        self.next_recovery=0
        self.latest_recovery=None
        self.runtime.mkdir(parents=True,exist_ok=True)

    def _launch(self, module):
        logs=self.root/'reports';logs.mkdir(exist_ok=True)
        name=module.rsplit('.',1)[1]
        args=[sys.executable,'-X','utf8','-m',module]
        args+=['--port',str(self.port)] if module=='engine.dashboard' else ['--serve','--report',str(logs/'classifier-supervised-latest.json')]
        with open(logs/(name+'-supervised.out.log'),'ab') as out,open(logs/(name+'-supervised.err.log'),'ab') as err:
            child=subprocess.Popen(args,cwd=self.root,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                **({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
        self.children.append(child)
        return child.pid

    def ensure_workers(self, now):
        rows=self.inventory()  # On an inconclusive scan do not launch duplicates.
        for module in ('engine.dashboard','engine.classification_worker'):
            current=self.workers.get(module)
            if current and _pid_alive(current['pid']):
                if now-current['started']>60:self.attempts[module]=0
                continue
            matches=[r for r in rows if re.search(r'(?:^|\s)-m\s+'+re.escape(module)+r'(?:\s|$)',r.get('CommandLine') or '')
                     and str(self.root).casefold() in (r.get('CommandLine') or '').casefold()]
            if module=='engine.dashboard':
                matches=[r for r in matches if int((re.search(r'--port(?:=|\s+)(\d+)',r['CommandLine']) or [None,'8765'])[1])==self.port]
            if matches:
                # Prefer the actual interpreter over a venv launcher.
                real=next((r for r in matches if sys.executable.casefold() in r['CommandLine'].casefold()),matches[-1])
                self.workers[module]=dict(pid=real['ProcessId'],ownership='ADOPTED',started=now)
                continue
            if current:
                self.attempts[module]=self.attempts.get(module,0)+1
                self.next_start[module]=now+min(60,2**min(self.attempts[module],6))
                self.workers.pop(module,None)
            if now<self.next_start.get(module,0):
                continue
            pid=self.launch(module)
            self.workers[module]=dict(pid=pid,ownership='STARTED',started=now)

    def request(self, path, payload=None):
        base=f'http://127.0.0.1:{self.port}'
        request=urllib.request.Request(base+path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Origin':base,'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=15) as response:
            return json.load(response)

    def cycle(self, now=None):
        now=time.monotonic() if now is None else now
        for child in self.children:child.poll()
        self.children=[child for child in self.children if child.returncode is None]
        state=dict(schema_version='runtime-supervisor-v1',pid=os.getpid(),updated_at=datetime.now(timezone.utc).isoformat(),
                   root=str(self.root),port=self.port,status='RUNNING')
        try:
            self.ensure_workers(now)
            if now>=self.next_recovery:
                identity=self.request('/api/runtime/status')
                if Path(identity['root']).resolve()!=self.root.resolve():raise RuntimeError('DASHBOARD_ROOT_MISMATCH')
                if Path(identity['database']).resolve()!=(self.root/'sessions/acquisition/acquisition.sqlite3').resolve():
                    raise RuntimeError('DASHBOARD_DATABASE_MISMATCH')
                state['catchup']=self.request('/api/runtime/catchup',{})
                self.latest_recovery=state['catchup']
                self.next_recovery=now+60
        except Exception as error:
            state.update(status='DEGRADED',error_code=type(error).__name__)
        state['workers']={k:{field:v[field] for field in ('pid','ownership')} for k,v in self.workers.items()}
        if self.latest_recovery is not None:state['catchup']=self.latest_recovery
        path=self.runtime/'status.json';temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(temporary,path)
        return state


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--status',action='store_true')
    args=parser.parse_args(argv)
    if args.status:
        path=RUNTIME/'status.json'
        value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'status':'NOT_STARTED'}
        if value.get('pid') and not _pid_alive(value['pid']):value['status']='STOPPED'
        print(json.dumps(value,ensure_ascii=False,indent=2));return 0
    RUNTIME.mkdir(parents=True,exist_ok=True)
    try:
        with file_lock(RUNTIME/'supervisor.guard',timeout=0):
            supervisor=Supervisor(args.port)
            while True:
                supervisor.cycle()
                time.sleep(10)
    except ValueError:
        print('Supervisor đã chạy; không tạo tiến trình thứ hai.');return 0
    except KeyboardInterrupt:
        # Children stay up; this stops supervision, never kills a running crawl.
        return 0


if __name__=='__main__':sys.exit(main())
