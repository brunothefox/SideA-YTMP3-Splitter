import shutil
import time
from pathlib import Path
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import app,DATA,run_ffmpeg
from jobs import JOBS,Cancelled
from youtube_import import normalize_youtube_url

client=TestClient(app)
A='A2345678901';B='B2345678902';PLAYLIST='PL_test_collection_12345'

def wait(jid):
    for _ in range(600):
        state=client.get('/api/jobs/'+jid).json()
        if state['status'] in {'done','error','cancelled'}:return state
        time.sleep(.02)
    pytest.fail('YouTube job timed out')

@pytest.mark.parametrize('url',[
    f'https://www.youtube.com/watch?v={A}',f'https://youtu.be/{A}?si=share&t=5',
    f'https://www.youtube.com/shorts/{A}',f'https://m.youtube.com/shorts/{A}/?feature=share',
    f'https://music.youtube.com/watch?v={A}',f'https://youtube.com/live/{A}',
    f'https://www.youtube.com/embed/{A}',f'https://www.youtube-nocookie.com/embed/{A}',
    f'https://youtube.com/v/{A}',f'youtu.be/{A}',
    f'https://youtube.com/attribution_link?u=%2Fwatch%3Fv%3D{A}',
    f'https://youtube.com/redirect?q=https%3A%2F%2Fyoutu.be%2F{A}',
])
def test_video_url_forms(url):
    assert normalize_youtube_url(url)=={'kind':'video','url':'https://www.youtube.com/watch?v='+A,'video_id':A}

@pytest.mark.parametrize('url',[
    'https://youtube.com.evil.example/watch?v='+A,'https://evil.example/youtube.com/watch?v='+A,
    'file:///etc/passwd','https://user:password@youtube.com/watch?v='+A,
    'https://youtube.com:garbage/watch?v='+A,'https://youtube.com:444/watch?v='+A,
    'https://youtube.com/redirect?q=https://example.com','https://youtube.com/watch?v=bad',
    'https://youtube.com/playlist?list=123',
])
def test_invalid_urls(url):
    with pytest.raises(HTTPException) as error:normalize_youtube_url(url)
    assert error.value.status_code==400

def test_playlist_choice_and_channels():
    url=f'https://youtube.com/watch?v={A}&list={PLAYLIST}'
    assert normalize_youtube_url(url)['kind']=='video'
    assert normalize_youtube_url(url,True)['kind']=='collection'
    assert normalize_youtube_url('https://music.youtube.com/playlist?list='+PLAYLIST)['kind']=='collection'
    assert normalize_youtube_url('https://youtube.com/@example/shorts')['url']=='https://www.youtube.com/@example/shorts'
    assert normalize_youtube_url('https://youtube.com/@example')['url'].endswith('/@example/videos')

@pytest.fixture
def fake_youtube(tmp_path,monkeypatch):
    fixture=tmp_path/'audio.wav'
    run_ffmpeg(['-f','lavfi','-i','sine=frequency=440:duration=4','-ar','48000','-ac','2',fixture])
    class Fake:
        calls=[];failed=set();cancelled=set();settings=[]
        def __init__(self,options):self.options=options;Fake.settings.append(options)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def prepare_filename(self,info):return self.options['outtmpl'].replace('%(ext)s','wav')
        def extract_info(self,url,download=True):
            Fake.calls.append((url,download))
            if not download:
                return {'title':'Test playlist','playlist_count':4,'entries':[
                    {'id':A,'title':'First video','duration':4,'playlist_index':3},
                    None,{'id':B,'title':'Private video','availability':'private'},
                    {'id':B,'title':'Second video','duration':4,'playlist_index':6}]}
            vid=url.split('v=')[1]
            if vid in Fake.failed:raise ValueError('This video is unavailable')
            if vid in Fake.cancelled:raise Cancelled('Test cancellation')
            info={'id':vid,'title':'Video '+vid,'uploader':'Test channel','chapters':[{'start_time':0,'title':'Part one'},{'start_time':2,'title':'Part two'}]}
            Path(self.prepare_filename(info)).write_bytes(fixture.read_bytes())
            for hook in self.options.get('progress_hooks',[]):hook({'status':'downloading','downloaded_bytes':100,'total_bytes':100})
            return info
    monkeypatch.setattr('youtube_import.yt_dlp.YoutubeDL',Fake)
    return Fake

def test_shorts_import_metadata(fake_youtube):
    response=client.post('/api/youtube',json={'url':'https://youtube.com/shorts/'+A})
    state=wait(response.json()['job']);assert state['status']=='done',state
    source=state['result']
    try:
        assert source['title']=='Video '+A
        assert source['artist']=='Test channel'
        assert len(source['tracks'])==2
        assert fake_youtube.calls[-1][0]=='https://www.youtube.com/watch?v='+A
        assert fake_youtube.settings[-1]['noplaylist'] is True
    finally:shutil.rmtree(DATA/source['id'])

def test_playlist_is_inspected_before_download(fake_youtube):
    response=client.post('/api/youtube',json={'url':'https://youtube.com/playlist?list='+PLAYLIST,'playlist_start':3,'playlist_limit':4})
    state=wait(response.json()['job']);assert state['status']=='done',state
    result=state['result']
    assert result['kind']=='youtube_collection' and result['title']=='Test playlist'
    assert [i['available'] for i in result['items']]==[True,False,False,True]
    assert fake_youtube.calls==[('https://www.youtube.com/playlist?list='+PLAYLIST,False)]
    assert fake_youtube.settings[-1]['playliststart']==3 and fake_youtube.settings[-1]['playlistend']==6

def test_batch_partial_failure_and_retry_without_duplicates(fake_youtube):
    fake_youtube.failed.add(B)
    body={'url':'https://youtube.com/playlist?list='+PLAYLIST,'video_ids':[A,B,A]}
    response=client.post('/api/youtube',json=body)
    result=wait(response.json()['job'])['result'];bid=result['batch_id']
    try:
        assert result['imported']==1 and result['failed']==1
        first=result['items'][0]['source_id']
        fake_youtube.failed.clear();body['video_ids']=[A,B];body['batch_id']=bid
        before=len(fake_youtube.calls)
        response=client.post('/api/youtube',json=body)
        result=wait(response.json()['job'])['result']
        assert result['imported']==2 and result['failed']==0
        assert result['items'][0]['source_id']==first
        assert len(fake_youtube.calls)-before==1
        assert client.get('/api/youtube/batches/'+bid).json()['imported']==2
    finally:
        report=client.get('/api/youtube/batches/'+bid).json()
        for item in report['items']:
            if item.get('source_id'):shutil.rmtree(DATA/item['source_id'],ignore_errors=True)
        (DATA/'.youtube-batches'/(bid+'.json')).unlink(missing_ok=True)

def test_cancelled_batch_can_retry_and_keep_finished_sources(fake_youtube):
    fake_youtube.cancelled.add(B)
    body={'url':'https://youtube.com/playlist?list='+PLAYLIST,'video_ids':[A,B]}
    response=client.post('/api/youtube',json=body);bid=response.json()['batch_id'];jid=response.json()['job']
    state=wait(jid)
    try:
        assert state['status']=='cancelled'
        report=client.get('/api/youtube/batches/'+bid).json();first=report['items'][0]['source_id']
        assert report['imported']==1
        fake_youtube.cancelled.clear()
        retry=client.post(f'/api/jobs/{jid}/retry')
        assert retry.status_code==200
        result=wait(retry.json()['job'])['result']
        assert result['imported']==2 and result['items'][0]['source_id']==first
    finally:
        report=client.get('/api/youtube/batches/'+bid).json()
        for item in report['items']:
            if item.get('source_id'):shutil.rmtree(DATA/item['source_id'],ignore_errors=True)
        (DATA/'.youtube-batches'/(bid+'.json')).unlink(missing_ok=True)

def test_empty_and_invalid_selection():
    for ids in [[],['bad']]:assert client.post('/api/youtube',json={'url':'https://youtube.com/playlist?list='+PLAYLIST,'video_ids':ids}).status_code==400
