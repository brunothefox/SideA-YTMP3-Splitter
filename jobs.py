"""Persistent jobs with cooperative pause/cancel, retry payloads, and subprocess cleanup."""
from __future__ import annotations
import json
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from fastapi import HTTPException
from runtime import HOME

LOCAL=threading.local()
RUNNERS={}
POOL=ThreadPoolExecutor(max_workers=2,thread_name_prefix='side-a')
DIRECTORY=HOME/'data/.jobs'
DIRECTORY.mkdir(parents=True,exist_ok=True)


class Cancelled(Exception):pass


class Job(dict):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.lock=threading.RLock()

    def save(self):
        path=DIRECTORY/(self['id']+'.json')
        temp=path.with_name(path.stem+'-'+uuid.uuid4().hex+'.tmp')
        temp.write_text(json.dumps(self,ensure_ascii=False),encoding='utf-8')
        temp.replace(path)

    def update(self,*args,**kwargs):
        with self.lock:
            super().update(*args,**kwargs)
            self['updated']=time.time()
            elapsed=self['updated']-self.get('started',self['updated'])
            progress=self.get('progress',0)
            if 0<progress<100 and elapsed>2:
                self['eta_seconds']=round(elapsed*(100-progress)/progress)
            self.save()


JOBS={}
for path in DIRECTORY.glob('*.json'):
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('status') in {'working','queued','paused'}:
            data.update(status='interrupted',message='App closed during this job. Retry to reuse completed scan sections.')
        JOBS[data['id']]=Job(data)
    except (OSError,ValueError,KeyError):pass


def checkpoint():
    job=getattr(LOCAL,'job',None)
    if not job:return
    if job.get('cancel_requested'):raise Cancelled('Job cancelled.')
    while job.get('pause_requested'):
        if job.get('status')!='paused':job.update(status='paused',message='Paused. Resume when ready.')
        time.sleep(.15)
        if job.get('cancel_requested'):raise Cancelled('Job cancelled.')
    if job.get('status')=='paused':job.update(status='working',message='Resuming…')


def new_job(work,kind='task',payload=None):
    jid=uuid.uuid4().hex
    job=Job(id=jid,status='queued',progress=0,message='Queued…',kind=kind,payload=payload or {},started=time.time(),updated=time.time())
    JOBS[jid]=job;job.save()
    def run():
        LOCAL.job=job
        try:
            checkpoint();job.update(status='working')
            result=work(job)
            checkpoint();job.update(status='done',progress=100,result=result,message='Ready',eta_seconds=0)
        except Cancelled as error:job.update(status='cancelled',message=str(error),eta_seconds=None)
        except Exception as error:job.update(status='error',message=str(error)[-1400:],eta_seconds=None)
        finally:LOCAL.job=None
    POOL.submit(run)
    return {'job':jid}


def managed_run(args,timeout=600,**kwargs):
    checkpoint()
    kwargs.setdefault('creationflags',subprocess.CREATE_NO_WINDOW if hasattr(subprocess,'CREATE_NO_WINDOW') else 0)
    started=time.monotonic()
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kwargs)
    try:
        while True:
            checkpoint()
            if time.monotonic()-started>timeout:raise TimeoutError('Processing timed out. Try a shorter selection.')
            try:
                stdout,stderr=process.communicate(timeout=.2)
                return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
            except subprocess.TimeoutExpired:continue
    except BaseException:
        process.terminate()
        try:process.communicate(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.communicate()
        raise


def register_jobs(app):
    @app.get('/api/tasks')
    def tasks():
        return {'jobs':[{k:v for k,v in j.items() if k not in {'result','payload'}} for j in sorted(JOBS.values(),key=lambda j:j['started'],reverse=True)[:50]]}

    @app.post('/api/jobs/{jid}/{action}')
    def control(jid:str,action:str):
        job=JOBS.get(jid)
        if not job:raise HTTPException(404,'Job not found.')
        if action=='retry':
            if job['status'] not in {'error','cancelled','interrupted'}:raise HTTPException(409,'Only failed, cancelled, or interrupted jobs can be retried.')
            handler=RUNNERS.get(job['kind'])
            if not handler:raise HTTPException(400,'Import the source again to retry this job.')
            return handler(job['payload'])
        if job['status'] not in {'queued','working','paused'}:raise HTTPException(409,'This job has already finished.')
        if action=='pause':job.update(pause_requested=True,message='Pausing at the next processing checkpoint…')
        elif action=='resume':job.update(pause_requested=False,message='Resuming…')
        elif action=='cancel':job.update(cancel_requested=True,pause_requested=False,message='Cancelling…')
        else:raise HTTPException(400,'Choose pause, resume, cancel, or retry.')
        return {'ok':True}
