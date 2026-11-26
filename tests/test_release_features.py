import io
import json
import shutil
import threading
import time
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import app,DATA,ROOT,run_ffmpeg
from jobs import JOBS,RUNNERS,checkpoint,new_job
from benchmarks.evaluate import interval_metrics,wer

client=TestClient(app)

def wait(jid):
    for _ in range(600):
        job=client.get('/api/jobs/'+jid).json()
        if job['status']=='error':pytest.fail(job['message'])
        if job['status']=='done':return job['result']
        time.sleep(.03)
    pytest.fail('Job timed out')

@pytest.fixture
def source(tmp_path):
    path=tmp_path/'test.wav';run_ffmpeg(['-f','lavfi','-i','sine=frequency=400:duration=4','-ar','48000','-ac','2',path])
    result=wait(client.post('/api/upload',files={'file':('test.wav',path.read_bytes(),'audio/wav')}).json()['job'])
    yield result
    shutil.rmtree(DATA/result['id'],ignore_errors=True)

def test_pause_resume_cancel_and_persisted_history():
    gate=threading.Event()
    def work(job):
        while not gate.is_set():checkpoint();time.sleep(.01)
        return {'ok':True}
    jid=new_job(work,kind='test')['job']
    assert client.post(f'/api/jobs/{jid}/pause').status_code==200
    for _ in range(100):
        if JOBS[jid]['status']=='paused':break
        time.sleep(.02)
    assert JOBS[jid]['status']=='paused'
    assert client.post(f'/api/jobs/{jid}/resume').status_code==200
    gate.set();assert wait(jid)['ok']
    gate.clear();jid=new_job(work,kind='test')['job']
    client.post(f'/api/jobs/{jid}/cancel')
    for _ in range(100):
        if JOBS[jid]['status']=='cancelled':break
        time.sleep(.02)
    gate.set();assert JOBS[jid]['status']=='cancelled'
    assert (DATA/'.jobs'/(jid+'.json')).exists()

def test_retry_job():
    def failure(job):raise ValueError('Retry me')
    jid=new_job(failure,kind='test_retry',payload={'value':3})['job']
    for _ in range(100):
        if JOBS[jid]['status']=='error':break
        time.sleep(.01)
    RUNNERS['test_retry']=lambda p:new_job(lambda job:p)
    result=client.post(f'/api/jobs/{jid}/retry')
    assert result.status_code==200
    assert wait(result.json()['job'])=={'value':3}

def test_project_backup_restore_and_review(source):
    sid=source['id'];restored=None
    try:
        assert client.put(f'/api/sources/{sid}/review',json={'marks':[{'start':1,'end':2,'word':'Review','selected':True}],'mode':'mute'}).status_code==200
        assert client.put(f'/api/sources/{sid}/draft',json={'tracks':[{'start':0,'title':'Recovered title'}],'artist':'Artist','album':'Album','settings':{'export-target':'neko'}}).status_code==200
        response=client.get(f'/api/sources/{sid}/backup')
        assert response.status_code==200
        result=client.post('/api/projects/restore',files={'file':('project.sidea.zip',response.content,'application/zip')})
        restored=wait(result.json()['job'])
        assert restored['id']!=sid
        assert restored['draft']['tracks'][0]['title']=='Recovered title'
        assert client.get(f'/api/sources/{restored["id"]}/review').json()['marks'][0]['word']=='Review'
    finally:
        if restored:shutil.rmtree(DATA/restored['id'],ignore_errors=True)
        (DATA/'.backups'/(sid+'.sidea.zip')).unlink(missing_ok=True)

def test_backup_rejects_zip_traversal():
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:z.writestr('../escaped.txt','bad')
    response=client.post('/api/projects/restore',files={'file':('bad.zip',buffer.getvalue(),'application/zip')})
    assert response.status_code==400
    assert not (DATA/'escaped.txt').exists()

def test_detailed_waveform_and_removed_asset_mapping(source):
    sid=source['id']
    result=client.get(f'/api/sources/{sid}/waveform?start=1&end=2')
    assert result.status_code==200 and result.json()['peaks']
    assert client.get(f'/api/sources/{sid}/waveform?start=-1&end=2').status_code==400
    exported=wait(client.post(f'/api/sources/{sid}/export',json={'tracks':[{'start':0,'title':'Test'}],'format':'mp3','neko':True,'shift':0}).json()['job'])
    response=client.post(f'/api/sources/{sid}/exports/{exported["export_id"]}/asset-map',json={'entries':[]})
    assert response.status_code==410
    assert exported['config']==[]
    bundle=zipfile.ZipFile(io.BytesIO(client.get(exported['zip']).content))
    assert not any('nekodj' in name for name in bundle.namelist())


def test_vocal_only_cleanup_preserves_instrumental(source,tmp_path):
    sid=source['id'];folder=DATA/sid/'stems/htdemucs/source';folder.mkdir(parents=True)
    for filename,frequency in [('vocals.wav',1000),('no_vocals.wav',250)]:
        run_ffmpeg(['-f','lavfi','-i',f'sine=frequency={frequency}:duration=4','-ar','44100','-ac','2',folder/filename])
    payload={'tracks':[{'start':0,'title':'Stems'}],'format':'wav','vocal_only':True,'redactions':[{'start':1,'end':2}],'cleanup_mode':'mute'}
    exported=wait(client.post(f'/api/sources/{sid}/export',json=payload).json()['job'])
    output=tmp_path/'stems.wav';output.write_bytes(client.get(exported['files'][0]['url']).content)
    import array,math
    samples=array.array('h');samples.frombytes(run_ffmpeg(['-i',output,'-ac','1','-ar','8000','-f','s16le','-']).stdout)
    segment=samples[9600:14400]
    def amplitude(freq):return abs(sum(v*complex(math.cos(2*math.pi*freq*i/8000),-math.sin(2*math.pi*freq*i/8000)) for i,v in enumerate(segment)))/len(segment)
    assert amplitude(250)>500 and amplitude(1000)<5

def test_accuracy_metrics():
    assert wer('a b c','a wrong c')==pytest.approx(1/3)
    assert interval_metrics([{'start':1,'end':2}],[{'start':1.1,'end':1.9}])['recall']==1

def test_source_archive_allowlist_has_no_private_data():
    from scripts.package_release import allowed
    assert all(not {'data','exports','tools','.venv','workspace'} & set(p.relative_to(ROOT).parts) for p in allowed())
    assert any(p.name=='launcher.py' for p in allowed())

def test_verified_downloader_uses_partial_file(tmp_path,monkeypatch):
    import hashlib
    import setup_components
    class Response:
        status_code=200;headers={'Content-Length':'4'}
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def iter_content(self,size):yield b'test'
    monkeypatch.setattr(setup_components.requests,'get',lambda *args,**kwargs:Response())
    job=type('Job',(),{'update':lambda self,**kw:None})()
    target=tmp_path/'model.bin'
    setup_components.download('https://example.com/model',target,hashlib.sha256(b'test').hexdigest(),job)
    assert target.read_bytes()==b'test' and not target.with_suffix('.bin.part').exists()
    target.unlink()
    with pytest.raises(ValueError):setup_components.download('https://example.com/model',target,'0'*64,job)
    assert not target.exists() and not target.with_suffix('.bin.part').exists()
