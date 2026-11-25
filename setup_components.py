"""Verified, resumable downloads. No audio is sent to these download servers."""
import hashlib
import os
import platform
import shutil
import tarfile
import zipfile
from pathlib import Path
import requests
from fastapi import HTTPException
from pydantic import BaseModel
from typing import Literal
from jobs import RUNNERS,checkpoint,managed_run,new_job
from runtime import HOME,tool

MODELS={
 'base':('ggml-base.bin','60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe'),
 'small':('ggml-small.bin','1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b')}
RELEASE='https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/'


def download(url,path,checksum,job):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==checksum:return
    part=path.with_suffix(path.suffix+'.part')
    offset=part.stat().st_size if part.exists() else 0
    response=requests.get(url,headers={'Range':f'bytes={offset}-'} if offset else {},stream=True,timeout=(30,60))
    if response.status_code==416:
        response.close();offset=0;response=requests.get(url,stream=True,timeout=(30,60))
    response.raise_for_status()
    append=offset>0 and response.status_code==206
    if not append:offset=0
    total=int(response.headers.get('Content-Length',0))+offset
    received=offset
    with response,part.open('ab' if append else 'wb') as output:
        for chunk in response.iter_content(1024*1024):
            checkpoint();output.write(chunk);received+=len(chunk)
            job.update(progress=min(96,96*received/total) if total else 10,message=f'Downloading {path.name}: {received//1024**2} MB'+(f' / {total//1024**2} MB' if total else ''))
    job.update(message='Verifying download checksum…',progress=97)
    digest=hashlib.sha256()
    with part.open('rb') as source:
        for chunk in iter(lambda:source.read(1024*1024),b''):checkpoint();digest.update(chunk)
    if digest.hexdigest()!=checksum:
        part.unlink();raise ValueError('Checksum mismatch. The download was discarded; retry setup.')
    part.replace(path)


def install_component(component,job):
    if component in MODELS:
        filename,checksum=MODELS[component]
        target=HOME/'tools/models'/filename
        download('https://huggingface.co/ggerganov/whisper.cpp/resolve/main/'+filename,target,checksum,job)
        return {'component':component,'ready':True}
    if component=='compact':
        original=HOME/'tools/models/ggml-small.bin'
        if not original.exists():raise ValueError('Install the higher-accuracy model first.')
        target=HOME/'tools/models/ggml-small-q5_0.bin'
        result=managed_run([str(tool('whisper-quantize')),str(original),str(target),'q5_0'],timeout=600)
        if result.returncode:raise ValueError(result.stderr.decode(errors='replace')[-700:])
        return {'component':component,'ready':True}
    if component=='gpu' and os.name!='nt':raise ValueError('On Linux/macOS, install a compatible GPU-enabled whisper.cpp build and put it on PATH.')
    if component=='engine' and os.name!='nt' and platform.system()!='Linux':raise ValueError('On macOS install whisper-cpp with Homebrew, then restart Side A.')
    if component=='gpu':
        name='whisper-cublas-12.4.0-bin-x64.zip';checksum='443110ddaad70d4290ab2e77179e31cf712035bbc4fad56bb4519a90c917b39c';folder='whisper-cuda'
    elif os.name=='nt':
        name='whisper-bin-x64.zip';checksum='49dcc16de826f20bd53d44f947a1ae49dfa81f86cad67a64d80820cb192d674a';folder='whisper'
    else:
        if platform.machine() not in {'x86_64','AMD64'}:raise ValueError('Install whisper.cpp for your CPU architecture and put it on PATH.')
        name='whisper-bin-ubuntu-x64.tar.gz';checksum='46811a3ecf584307480a220b9ef5ff81b7b22dc41577cbc274ce3afc61f753b1';folder='whisper'
    archive=HOME/'tools/downloads'/name
    download(RELEASE+name,archive,checksum,job)
    target=HOME/'tools'/folder;target.mkdir(parents=True,exist_ok=True)
    if name.endswith('.zip'):
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                checkpoint()
                if not (target/member.filename).resolve().is_relative_to(target.resolve()):raise ValueError('Invalid archive path.')
                bundle.extract(member,target)
    else:
        with tarfile.open(archive) as bundle:bundle.extractall(target,filter='data')
        for file in target.rglob('whisper-*'):
            if file.is_file() and '.' not in file.name:file.chmod(file.stat().st_mode|0o111)
    archive.unlink()
    return {'component':component,'ready':True}


class ComponentRequest(BaseModel):
    component:Literal['engine','gpu','base','small','compact']


def register_setup(app):
    @app.post('/api/setup')
    def setup(body:ComponentRequest):
        return new_job(lambda job:install_component(body.component,job),kind='setup',payload=body.model_dump())
    RUNNERS['setup']=lambda payload:setup(ComponentRequest(**payload))
