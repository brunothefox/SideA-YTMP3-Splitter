import io
import json
import shutil
import time
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import app,DATA,run_ffmpeg,inspect_audio
from jobs import JOBS,Cancelled

client=TestClient(app)

def wait(jid):
    for _ in range(600):
        result=client.get('/api/jobs/'+jid).json()
        if result['status'] in {'done','error','cancelled'}:return result
        time.sleep(.02)
    pytest.fail('Playlist export timed out')

@pytest.fixture
def projects(tmp_path):
    tone=tmp_path/'source.wav'
    run_ffmpeg(['-f','lavfi','-i','sine=frequency=440:duration=4','-ar','48000',tone])
    sources=[];before=set((DATA/'.playlist-exports').iterdir())
    for _ in range(2):
        response=client.post('/api/upload',files={'file':('same title.wav',tone.read_bytes(),'audio/wav')})
        source=wait(response.json()['job'])['result'];sources.append(source)
        client.put(f'/api/sources/{source["id"]}/draft',json={'tracks':[{'start':0,'title':'First'},{'start':2,'title':'Skipped','selected':False}],'artist':'Test','album':'Test'})
    yield sources
    for source in sources:shutil.rmtree(DATA/source['id'],ignore_errors=True)
    for directory in set((DATA/'.playlist-exports').iterdir())-before:shutil.rmtree(directory,ignore_errors=True)

def request(projects,**overrides):
    return {'title':'Test Playlist','projects':[{'source_id':s['id']} for s in projects],
            'options':{'format':'wav','strip_metadata':True},**overrides}

@pytest.mark.parametrize('mode,layout,seconds',[('whole','folders',4),('cuts','flat',2),('interval','flat',2)])
def test_batch_audio_layout_saved_cuts_and_no_game_configs(projects,tmp_path,mode,layout,seconds):
    response=client.post('/api/playlist-exports',json=request(projects,mode=mode,layout=layout,interval=2))
    assert response.status_code==200,response.text
    job=wait(response.json()['job']);assert job['status']=='done',job
    result=job['result'];expected=4 if mode=='interval' else 2;assert result['file_count']==expected and result['completed']==2
    bundle=zipfile.ZipFile(io.BytesIO(client.get(result['zip']).content));names=bundle.namelist()
    audio=[n for n in names if n.endswith('.wav')]
    assert len(audio)==expected and len(set(audio))==expected
    assert all(('/' in name)==(layout=='folders') for name in audio)
    assert not any('nekodj' in n or n.endswith('.lua') for n in names)
    assert len(json.loads(bundle.read('playlist-manifest.json'))['files'])==expected
    for index,name in enumerate(audio):
        output=tmp_path/f'{index}.wav';output.write_bytes(bundle.read(name))
        assert abs(inspect_audio(output)['duration']-seconds)<.1

def test_partial_failure_retry_preserves_completed_audio(projects,monkeypatch):
    import app as module
    original=module.run_ffmpeg;failed=False
    def flaky(args,**kwargs):
        nonlocal failed
        if not failed and any(str(DATA/projects[1]['id']) in str(arg) for arg in args):failed=True;raise ValueError('Temporary encoding failure')
        return original(args,**kwargs)
    monkeypatch.setattr(module,'run_ffmpeg',flaky)
    body=request(projects)
    response=client.post('/api/playlist-exports',json=body).json();first=wait(response['job'])['result']
    assert first['completed']==1 and first['failed']==1
    retained=first['items'][0]['result']['export_id']
    response=client.post('/api/playlist-exports',json={**body,'retry_id':first['export_id']}).json()
    final=wait(response['job'])['result'];assert final['completed']==2 and final['failed']==0
    assert final['items'][0]['result']['export_id']==retained
    changed={**body,'retry_id':first['export_id'],'layout':'flat'}
    assert client.post('/api/playlist-exports',json=changed).status_code==409

def test_cancellation_keeps_completed_projects_for_retry(projects,monkeypatch):
    import app as module
    original_run=module.run_ffmpeg;seen=0
    def cancel_run(args,**kwargs):
        nonlocal seen
        seen+=1
        if seen==2:raise Cancelled('Cancelled fixture')
        return original_run(args,**kwargs)
    monkeypatch.setattr(module,'run_ffmpeg',cancel_run)
    body=request(projects);response=client.post('/api/playlist-exports',json=body).json()
    assert wait(response['job'])['status']=='cancelled'
    saved=client.get('/api/playlist-exports/'+response['export_id']).json();assert saved['completed']==1
    resumed=client.post('/api/playlist-exports',json={**body,'retry_id':response['export_id']}).json()
    assert wait(resumed['job'])['result']['completed']==2

def test_validation_and_missing_download(projects):
    body=request(projects)
    assert client.post('/api/playlist-exports',json={**body,'projects':[body['projects'][0]]*2}).status_code==400
    assert client.post('/api/playlist-exports',json={**body,'projects':[{'source_id':'../outside'}]}).status_code==422
    assert client.post('/api/playlist-exports',json={**body,'options':{'tracks':[]}}).status_code==400
    assert client.get('/api/playlist-exports/'+'0'*32+'/download').status_code==404

def test_batch_applies_reviewed_edits_and_padding(projects,tmp_path):
    body=request(projects[:1],options={'format':'wav','strip_metadata':True,'padding_start':.5,'padding_end':.25})
    body['projects'][0]['edits']={'redactions':[{'start':1,'end':2}],'cleanup_mode':'mute'}
    job=wait(client.post('/api/playlist-exports',json=body).json()['job']);assert job['status']=='done',job
    result=job['result'];bundle=zipfile.ZipFile(io.BytesIO(client.get(result['zip']).content))
    name=next(n for n in bundle.namelist() if n.endswith('.wav'));output=tmp_path/'edited.wav';output.write_bytes(bundle.read(name))
    assert abs(inspect_audio(output)['duration']-4.75)<.05
    import array
    pcm=array.array('h');pcm.frombytes(run_ffmpeg(['-i',output,'-ar','8000','-ac','1','-f','s16le','-']).stdout)
    assert max(abs(v) for v in pcm[12800:15200])<10
    assert any('content-cleanup-report.json' in name for name in bundle.namelist())

def test_retry_packing_reuses_all_rendered_audio(projects,monkeypatch):
    import playlist_exports as module
    original=module.zipfile.ZipFile;cancelled=False
    def cancel_archive(file,*args,**kwargs):
        nonlocal cancelled
        if str(file).endswith('playlist.tmp') and not cancelled:
            cancelled=True;raise Cancelled('Cancel during archive packing')
        return original(file,*args,**kwargs)
    monkeypatch.setattr(module.zipfile,'ZipFile',cancel_archive)
    body=request(projects);response=client.post('/api/playlist-exports',json=body).json()
    assert wait(response['job'])['status']=='cancelled'
    saved=client.get('/api/playlist-exports/'+response['export_id']).json()
    assert saved['completed']==2 and saved['zip'] is None
    ids=[i['result']['export_id'] for i in saved['items']]
    response=client.post('/api/playlist-exports',json={**body,'retry_id':saved['export_id']}).json()
    final=wait(response['job'])['result'];assert final['zip']
    assert [i['result']['export_id'] for i in final['items']]==ids
