import io
import json
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app, DATA, inspect_audio, parse_tracklist, prepare_source, run_ffmpeg

client = TestClient(app)


def wait_job(jid):
    for _ in range(300):
        result = client.get('/api/jobs/' + jid).json()
        if result['status'] == 'error':
            pytest.fail(result['message'])
        if result['status'] == 'done':
            return result['result']
        time.sleep(.05)
    pytest.fail('Job timed out')


@pytest.fixture
def tone(tmp_path):
    path = tmp_path / 'tone.wav'
    run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=6', '-ar', '48000', '-ac', '2', '-metadata', 'title=Test Mix', '-metadata', 'artist=Side A Tests', path])
    return path


def test_metadata_webm_regression(tone, tmp_path):
    webm = tmp_path / 'source.webm'
    run_ffmpeg(['-i', tone, '-c:a', 'libopus', webm])
    data = inspect_audio(webm)
    assert data['codec'] == 'opus'
    assert 5.9 < data['duration'] < 6.1
    assert data['sample_rate'] == 48000


def test_embedded_chapters(tone, tmp_path):
    metadata = tmp_path / 'chapters.txt'
    metadata.write_text(';FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=3000\ntitle=First\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=3000\nEND=6000\ntitle=Second\n')
    path = tmp_path / 'chaptered.mka'
    run_ffmpeg(['-i', tone, '-i', metadata, '-map_metadata', '1', '-map_chapters', '1', '-c:a', 'flac', path])
    data = inspect_audio(path)
    assert [c['title'] for c in data['chapters']] == ['First', 'Second']
    assert data['chapters'][1]['start'] == 3


@pytest.mark.parametrize('format', ['mp3', 'flac', 'wav', 'original'])
def test_upload_split_export_zip(tone, tmp_path, format):
    response = client.post('/api/upload', files={'file': ('mix.wav', tone.read_bytes(), 'audio/wav')})
    assert response.status_code == 200
    source = wait_job(response.json()['job'])
    try:
        assert source['title'] == 'Test Mix'
        assert source['artist'] == 'Side A Tests'
        assert source['peaks']
        preview = client.get(f'/api/sources/{source["id"]}/preview', headers={'Range': 'bytes=0-99'})
        assert preview.status_code == 206 and len(preview.content) == 100
        response = client.post(f'/api/sources/{source["id"]}/export', json={'format': format, 'artist':'Test Artist', 'album':'Test Album', 'tracks':[{'start':0,'title':'First # & song'}, {'start':2,'title':'Skipped','selected':False}, {'start':4,'title':'Last'}]})
        assert response.status_code == 200
        result = wait_job(response.json()['job'])
        assert len(result['files']) == 2
        archive = zipfile.ZipFile(io.BytesIO(client.get(result['zip']).content))
        assert len(archive.namelist()) == 2
        for item in result['files']:
            downloaded = client.get(item['url'])
            assert downloaded.status_code == 200
            output = tmp_path / item['name']
            output.write_bytes(downloaded.content)
            info = inspect_audio(output)
            assert 1.8 < info['duration'] < 2.2
            if format == 'mp3':
                assert info['tags']['artist'] == 'Test Artist'
        bad = client.post(f'/api/sources/{source["id"]}/export', json={'tracks':[{'start':4,'title':'A'}, {'start':2,'title':'B'}]})
        assert bad.status_code == 400
    finally:
        shutil.rmtree(DATA / source['id'])


def test_tracklist_and_local_access():
    tracks = parse_tracklist('00:02 A\n00:04 B\n00:04 Better title\n99:00 Out of bounds', 6)
    assert [t['start'] for t in tracks] == [0, 2, 4]
    assert tracks[-1]['title'] == 'Better title'
    assert client.post('/api/youtube', json={'url':'https://example.com/watch?v=x'}).status_code == 400
    assert client.post('/api/youtube', json={'url':'https://youtube.com/playlist?list=123'}).status_code == 400
    assert client.get('/api/health', headers={'origin':'https://example.com'}).status_code == 403
    assert client.get('/api/health', headers={'host':'evil.example'}).status_code == 403


@pytest.mark.parametrize('format', ['mp3', 'ogg', 'wav'])
def test_neko_shift_padding_config_and_folder(tone, tmp_path, format):
    response = client.post('/api/upload', files={'file': ('mix.wav', tone.read_bytes(), 'audio/wav')})
    source = wait_job(response.json()['job'])
    folder = None
    try:
        sid = source['id']
        tracks = [{'start':0, 'title':'01. Test Song [Official Video] 🎵 https://example.com'}]
        draft = {'tracks':tracks,'artist':'Draft Artist','album':'Draft Album','settings':{'export-target':'neko','padding-start':'0.5'}}
        assert client.put(f'/api/sources/{sid}/draft', json=draft).status_code == 200
        assert client.get(f'/api/sources/{sid}').json()['draft']['artist'] == 'Draft Artist'
        assert client.get(f'/api/sources/{sid}').json()['draft']['settings']['export-target'] == 'neko'
        assert sid in [s['id'] for s in client.get('/api/library').json()['sources']]
        payload = {'tracks':tracks,'format':format,'neko':True,'shift':12,'padding_start':.5,'padding_end':.75,'clean_titles':True,'fade':.02}
        result = wait_job(client.post(f'/api/sources/{sid}/export', json=payload).json()['job'])
        assert result['config'][0]['effectSpeed'] == .5
        assert result['config'][0]['title'] == 'Test Song'
        assert result['files'][0]['name'] == '01 - Test Song.' + format
        output = tmp_path / result['files'][0]['name']
        output.write_bytes(client.get(result['files'][0]['url']).content)
        assert abs(inspect_audio(output)['duration'] - 4.25) < .1
        raw = run_ffmpeg(['-i',output,'-ac','1','-ar','8000','-f','s16le','-']).stdout
        import array
        pcm = array.array('h')
        pcm.frombytes(raw)
        assert max(abs(n) for n in pcm[:3000]) < 100
        assert max(abs(n) for n in pcm[-4000:]) < 100
        bundle = zipfile.ZipFile(io.BytesIO(client.get(result['zip']).content))
        assert {'nekodj-track-values.csv','nekodj-track-values.json','nekodj-config-template.lua'} <= set(bundle.namelist())
        response = client.post(f'/api/sources/{sid}/exports/{result["export_id"]}/organize',json={'name':'Test Organized Mix','open_folder':False})
        assert response.status_code == 200
        folder = Path(response.json()['folder'])
        assert (folder / 'Audio' / result['files'][0]['name']).exists()
        assert (folder / 'Config' / 'nekodj-track-values.json').exists()
        assert client.post(f'/api/sources/{sid}/export',json={'tracks':tracks,'format':'original','padding_end':1}).status_code == 400
    finally:
        shutil.rmtree(DATA / source['id'])
        if folder and folder.resolve().is_relative_to((DATA.parent / 'exports').resolve()):
            shutil.rmtree(folder)
