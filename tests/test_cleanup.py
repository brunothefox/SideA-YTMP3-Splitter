import array
import io
import json
import math
import shutil
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import app, DATA, ROOT, run_ffmpeg
from content_cleanup import Redaction, THEMES, extract_words, find_matches, redaction_filter

client=TestClient(app)


def wait(jid):
    for _ in range(1200):
        job=client.get('/api/jobs/'+jid).json()
        if job['status']=='error':
            pytest.fail(job['message'])
        if job['status']=='done':
            return job['result']
        time.sleep(.05)
    pytest.fail('Job timed out')


def pcm(path):
    raw=run_ffmpeg(['-i',path,'-ac','1','-ar','8000','-f','s16le','-']).stdout
    result=array.array('h');result.frombytes(raw)
    return result


def test_whole_words_phrases_and_accents():
    words=[{'text':text,'start':i,'end':i+.5,'confidence':.8} for i,text in enumerate(['assistant','ass','Cabrón','hijo','de','puta'])]
    matches=find_matches(words,['ass','cabron','hijo de puta'],10,.1)
    assert [m['word'] for m in matches]==['ass','Cabrón','hijo de puta']
    assert matches[0]['start']==.9
    assert matches[-1]['end']==5.6


def test_subword_reassembly():
    document={'transcription':[{'text':' a bullshit phrase','tokens':[
        {'text':' a','offsets':{'from':0,'to':100},'p':.9},
        {'text':' bull','offsets':{'from':100,'to':300},'p':.8},
        {'text':'shit','offsets':{'from':300,'to':500},'p':.7},
        {'text':' phrase','offsets':{'from':500,'to':800},'p':.9}]}]}
    words=extract_words(document)
    assert [w['text'] for w in words]==['a','bullshit','phrase']
    assert find_matches(words,['bullshit'],1,0)[0]['end']==.5


def test_theme_phrase_signals_are_separate_from_word_matching():
    words=[{'text':t,'start':i*.3,'end':(i+1)*.3,'confidence':.9} for i,t in enumerate('the phrase my phone number appears in this recording'.split())]
    assert not find_matches(words,['phonebook','numbered'],10,0)
    signals=find_matches(words,THEMES['Personal information — context review'],10,0)
    assert len(signals)==1 and signals[0]['word']=='my phone number'


@pytest.mark.parametrize('mode',['mute','bleep'])
def test_audio_is_removed_not_overlaid(tmp_path,mode):
    source=tmp_path/'tone.wav';output=tmp_path/'clean.wav'
    run_ffmpeg(['-f','lavfi','-i','sine=frequency=250:duration=3','-ar','48000','-ac','2',source])
    run_ffmpeg(['-i',source,'-af',redaction_filter([Redaction(start=1,end=2)],0,3,mode),output])
    data=pcm(output)
    before=data[1600:6400];during=data[9600:14400]
    assert max(abs(n) for n in before)>1000
    if mode=='mute':
        assert max(abs(n) for n in during)==0
    else:
        crossings=sum(a<=0<b for a,b in zip(during,during[1:]))
        assert 590<crossings<610  # 1 kHz bleep for 0.6 seconds, not the source's 250 Hz.


def test_cleanup_export_shift_and_padding(tmp_path):
    tone=tmp_path/'tone.wav'
    run_ffmpeg(['-f','lavfi','-i','sine=frequency=250:duration=6','-ar','48000','-ac','2',tone])
    source=wait(client.post('/api/upload',files={'file':('tone.wav',tone.read_bytes(),'audio/wav')}).json()['job'])
    sid=source['id']
    try:
        payload={'tracks':[{'start':0,'title':'First'},{'start':3,'title':'Second'}],'format':'wav','neko':True,'shift':12,'padding_start':.5,
                 'redactions':[{'start':4.2,'end':4.8,'word':'Test edit'}],'cleanup_mode':'mute'}
        result=wait(client.post(f'/api/sources/{sid}/export',json=payload).json()['job'])
        output=tmp_path/'second.wav';output.write_bytes(client.get(result['files'][1]['url']).content)
        data=pcm(output)
        assert max(abs(n) for n in data[9200:10800])==0  # 1.15–1.35 seconds after shift/padding.
        assert max(abs(n) for n in data[5000:7000])>500
        bundle=zipfile.ZipFile(io.BytesIO(client.get(result['zip']).content))
        assert 'content-cleanup-report.json' in bundle.namelist()
        assert result['cleanup_count']==1
        preview=wait(client.post(f'/api/sources/{sid}/cleanup/preview',json={'edits':payload['redactions'],'mode':'mute'}).json()['job'])
        assert client.get(preview['url']).status_code==200
        payload['format']='original';payload['neko']=False
        assert client.post(f'/api/sources/{sid}/export',json=payload).status_code==400
    finally:
        shutil.rmtree(DATA/sid)


@pytest.mark.parametrize('format',['mp3','ogg','wav','flac'])
def test_descriptive_metadata_is_stripped(tmp_path,format):
    tone=tmp_path/'tagged.wav'
    run_ffmpeg(['-f','lavfi','-i','sine=duration=1','-metadata','title=Private Title','-metadata','artist=Private Artist',
                '-metadata','album=Private Album','-metadata','comment=Private Comment','-metadata','track=17',tone])
    source=wait(client.post('/api/upload',files={'file':('tagged.wav',tone.read_bytes(),'audio/wav')}).json()['job'])
    sid=source['id']
    try:
        result=wait(client.post(f'/api/sources/{sid}/export',json={'tracks':[{'start':0,'title':'Filename only'}],
                    'format':format,'strip_metadata':True,'artist':'Do not embed this','album':'Do not embed album'}).json()['job'])
        output=tmp_path/('export.'+format);output.write_bytes(client.get(result['files'][0]['url']).content)
        tags=run_ffmpeg(['-i',output,'-f','ffmetadata','-']).stdout.decode()
        assert not any(value in tags for value in ['Private','Do not embed','Filename only'])
        if format=='mp3':
            import mutagen
            assert not mutagen.File(output).tags
    finally:
        shutil.rmtree(DATA/sid)


@pytest.mark.skipif(not (ROOT/'tools/models/ggml-base.bin').exists() or not (ROOT/'test-results/speech.wav').exists(),reason='Offline engine/synthetic speech fixture not installed')
def test_real_local_speech_scan():
    speech=ROOT/'test-results/speech.wav'
    source=wait(client.post('/api/upload',files={'file':('speech.wav',speech.read_bytes(),'audio/wav')}).json()['job'])
    sid=source['id']
    try:
        request={'terms':['door'],'language':'en','themes':True,'margin':.15}
        result=wait(client.post(f'/api/sources/{sid}/cleanup/scan',json=request).json()['job'])
        assert len(result['matches'])==2
        assert all(m['word'].lower()=='door' for m in result['matches'])
        assert result['words'] and result['languages']==['en']
        request['terms']=['recording']
        result=wait(client.post(f'/api/sources/{sid}/cleanup/scan',json=request).json()['job'])
        assert len(result['matches'])==1
        assert client.get(f'/api/sources/{sid}/cleanup/analysis').json()['matches'][0]['word'].lower()=='recording'
    finally:
        shutil.rmtree(DATA/sid)
