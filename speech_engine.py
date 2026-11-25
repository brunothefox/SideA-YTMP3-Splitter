"""Keep one localhost-only Whisper worker warm; serialize model use safely."""
from __future__ import annotations
import atexit
import os
import secrets
import socket
import subprocess
import threading
import time
from pathlib import Path
import requests
from jobs import checkpoint
from runtime import HOME,tool


class SpeechEngine:
    def __init__(self):
        self.lock=threading.Lock();self.process=None;self.key=None;self.url=None;self.log=None
        atexit.register(self.close)

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process=None;self.key=None
        if self.log:self.log.close();self.log=None

    def transcribe(self,path,model,language,device='auto'):
        while not self.lock.acquire(timeout=.2):checkpoint()
        try:
            checkpoint()
            server=tool('whisper-server')
            cuda=HOME/'tools/whisper-cuda/Release/whisper-server.exe'
            if device=='gpu' and not cuda.exists() and os.name=='nt':
                raise ValueError('Install the GPU engine in Setup first, or choose CPU/Auto.')
            if device!='cpu' and cuda.exists():server=cuda
            key=(str(server),str(model),device)
            if self.key!=key or not self.process or self.process.poll() is not None:
                self.close()
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                prefix='/'+secrets.token_hex(24)
                self.url=f'http://127.0.0.1:{port}{prefix}'
                directory=HOME/'data/.engine';directory.mkdir(parents=True,exist_ok=True)
                self.log=(directory/'worker.log').open('wb')
                args=[str(server),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--request-path',prefix,
                      '--public',str(directory),'-t',str(min(8,max(1,(os.cpu_count() or 2)-1))),'-ml','1','-sow','-nlp']
                if device=='cpu' or (os.name=='nt' and server!=cuda):args+=['-ng']
                self.process=subprocess.Popen(args,cwd=server.parent,stdout=self.log,stderr=self.log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                for _ in range(400):
                    checkpoint()
                    if self.process.poll() is not None:raise ValueError('Speech engine exited. Check Diagnostics; GPU builds need a compatible NVIDIA driver.')
                    try:
                        response=requests.get(self.url+'/health',timeout=1)
                        if response.ok:break
                    except requests.RequestException:pass
                    time.sleep(.15)
                else:raise TimeoutError('The speech model did not become ready.')
                self.key=key
            with Path(path).open('rb') as audio:
                response=requests.post(self.url+'/inference',files={'file':('audio.wav',audio,'audio/wav')},
                    data={'response_format':'verbose_json','language':language,'max_len':'1','split_on_word':'true',
                          'token_timestamps':'true','temperature':'0','no_language_probabilities':'true'},timeout=1800)
            checkpoint()
            if not response.ok:raise ValueError('Speech engine failed: '+response.text[:500])
            data=response.json()
            segments=[]
            for segment in data.get('segments',[]):
                tokens=[{'text':w['word'],'offsets':{'from':round(w.get('start',segment.get('start',0))*1000),
                        'to':round(w.get('end',segment.get('end',0))*1000)},'p':w.get('probability',0)} for w in segment.get('words',[])]
                segments.append({'text':segment['text'],'tokens':tokens,'offsets':{'from':round(segment.get('start',0)*1000),'to':round(segment.get('end',0)*1000)}})
            detected=data.get('language',language).lower()
            codes={'english':'en','spanish':'es','malay':'ms','indonesian':'id','french':'fr','german':'de','portuguese':'pt','japanese':'ja','korean':'ko','chinese':'zh','arabic':'ar','hindi':'hi'}
            return {'result':{'language':language if language!='auto' else codes.get(detected,detected)},'transcription':segments}
        finally:self.lock.release()


ENGINE=SpeechEngine()
