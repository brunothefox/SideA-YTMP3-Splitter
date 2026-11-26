"""A persistent multi-project export queue using the single-project audio renderer."""
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import threading
import uuid
import zipfile
from pathlib import Path
from typing import Literal
from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,ValidationError
from jobs import JOBS,RUNNERS,Cancelled,checkpoint,new_job


class PlaylistProject(BaseModel):
    source_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    edits:dict=Field(default_factory=dict,max_length=8)


class PlaylistExportRequest(BaseModel):
    title:str=Field(default='Playlist',min_length=1,max_length=200)
    projects:list[PlaylistProject]=Field(min_length=1,max_length=200)
    mode:Literal['whole','cuts','interval']='whole'
    interval:float=Field(default=180,ge=1,le=86400,allow_inf_nan=False)
    layout:Literal['folders','flat']='folders'
    options:dict=Field(default_factory=dict,max_length=20)
    retry_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')


def register_playlist_exports(app,data,root,get_source,session_path,prepare_export,ExportRequest,safe_name):
    storage=data/'.playlist-exports';storage.mkdir(exist_ok=True)
    lock=threading.Lock()

    def path_for(eid):
        if not re.fullmatch(r'[a-f0-9]{32}',eid):raise HTTPException(404,'Playlist export not found.')
        return storage/eid

    def save(folder,manifest):
        temp=folder/'manifest.tmp';temp.write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8');temp.replace(folder/'manifest.json')

    def load(eid):
        folder=path_for(eid)
        if not (folder/'manifest.json').is_file():raise HTTPException(404,'Playlist export not found. Start a new export.')
        return folder,json.loads((folder/'manifest.json').read_text(encoding='utf-8'))

    def summary(manifest):
        items=manifest['items'];done=sum(i['status']=='done' for i in items)
        return {'export_id':manifest['id'],'items':items,'completed':done,
                'failed':sum(i['status']=='error' for i in items),'title':manifest['title'],
                'file_count':sum(len(i.get('result',{}).get('files',[])) for i in items if i['status']=='done'),
                'zip':f'/api/playlist-exports/{manifest["id"]}/download' if manifest.get('ready') else None,
                'zip_name':safe_name(manifest['title'])+'.zip'}

    @app.post('/api/playlist-exports')
    def export_playlist(body:PlaylistExportRequest):
        ids=[p.source_id for p in body.projects]
        if len(set(ids))!=len(ids):raise HTTPException(400,'Choose each video only once.')
        options=dict(body.options)
        forbidden={'tracks','artist','album','redactions','cleanup_mode','vocal_only'}&options.keys()
        if forbidden:raise HTTPException(400,'Per-video edits must be provided with their video.')
        specs=[]
        for project in body.projects:
            source=get_source(project.source_id);edits=project.edits
            if set(edits)-{'tracks','artist','album','redactions','cleanup_mode','vocal_only'}:
                raise HTTPException(400,'Unsupported per-video edits.')
            draft=source.get('draft',{})
            tracks=([{'start':0,'title':source['title'][:200]}] if body.mode=='whole' else edits.get('tracks') or draft.get('tracks') or source['tracks'])
            if body.mode=='interval':
                count=math.ceil(source['duration']/body.interval)
                if count>500:raise HTTPException(400,f'{source["title"]}: choose a longer interval to stay under 500 cuts per video.')
                tracks=[{'start':n*body.interval,'title':f'{source["title"][:180]} - Part {n+1:02}'} for n in range(count)]
            try:
                request=ExportRequest(**{**options,**edits,'tracks':tracks,
                    'artist':edits.get('artist',draft.get('artist',source.get('artist',''))),
                    'album':edits.get('album',body.title)})
            except ValidationError as error:raise HTTPException(400,'Invalid export settings: '+str(error))
            specs.append({'source_id':source['id'],'title':source['title'],'body':request.model_dump()})
        signature=hashlib.sha256(json.dumps({'specs':specs,'layout':body.layout,'title':body.title},sort_keys=True).encode()).hexdigest()
        if body.retry_id:
            folder,manifest=load(body.retry_id)
            if signature!=manifest['signature']:raise HTTPException(409,'Settings or tracks changed. Start a new playlist export.')
        else:
            eid=uuid.uuid4().hex;folder=path_for(eid);folder.mkdir()
            manifest={'id':eid,'title':body.title,'signature':signature,'ready':False,
                      'items':[{'source_id':s['source_id'],'title':s['title'],'status':'queued'} for s in specs]}
            save(folder,manifest)
        payload=body.model_dump();payload['retry_id']=manifest['id']

        def work(job):
            manifest['ready']=False;save(folder,manifest)
            for index,(spec,item) in enumerate(zip(specs,manifest['items'])):
                checkpoint()
                previous=item.get('result')
                if item['status']=='done' and previous and all((session_path(spec['source_id'])/previous['export_id']/f['name']).is_file() for f in previous['files']):continue
                item.update(status='working',error=None);save(folder,manifest)
                class Progress:
                    def update(self,**values):
                        job.update(progress=90*(index+values.get('progress',0)/100)/len(specs),
                                   message=f'Video {index+1} of {len(specs)} · '+values.get('message',spec['title']))
                try:
                    request=ExportRequest(**spec['body'])
                    item['result']=prepare_export(spec['source_id'],request)(Progress())
                    item['status']='done'
                except Cancelled:
                    item['status']='queued';save(folder,manifest);raise
                except Exception as error:
                    item.update(status='error',error=str(getattr(error,'detail',error))[-1000:])
                save(folder,manifest)
            checkpoint();job.update(progress=92,message='Packing your playlist ZIP…')
            rows=[]
            temporary=folder/'playlist.tmp'
            try:
                with zipfile.ZipFile(temporary,'w',zipfile.ZIP_STORED,allowZip64=True) as archive:
                    for index,item in enumerate(manifest['items']):
                        checkpoint()
                        if item['status']!='done':continue
                        result=item['result'];directory=session_path(item['source_id'])/result['export_id']
                        prefix=f'{index+1:03} - {safe_name(item["title"])[:70]}'
                        for audio in result['files']:
                            filename=Path(audio['name']).name
                            relative=f'{prefix}/{filename}' if body.layout=='folders' else f'{index+1:03} - {filename}'
                            with (directory/filename).open('rb') as incoming,archive.open(relative,'w',force_zip64=True) as outgoing:
                                while chunk:=incoming.read(1024*1024):checkpoint();outgoing.write(chunk)
                            rows.append({'video':item['title'],'file':relative,'duration':audio['duration'],
                                         'source_id':item['source_id']})
                        for sidecar in directory.iterdir():
                            if sidecar.suffix in {'.json','.csv','.lua'} and sidecar.name!='export.json':
                                archive.write(sidecar,f'Reports/{prefix}/{sidecar.name}')
                    archive.writestr('playlist-manifest.json',json.dumps({'title':body.title,'files':rows,
                        'failed':[{'title':i['title'],'error':i.get('error')} for i in manifest['items'] if i['status']=='error']},indent=2,ensure_ascii=False))
                    table=io.StringIO(newline='');writer=csv.DictWriter(table,fieldnames=['video','file','duration','source_id']);writer.writeheader();writer.writerows(rows)
                    archive.writestr('playlist-manifest.csv',table.getvalue().encode('utf-8-sig'))
                checkpoint();temporary.replace(folder/'playlist.zip')
            finally:
                temporary.unlink(missing_ok=True)
            manifest['ready']=bool(rows);save(folder,manifest)
            return summary(manifest)
        with lock:
            if any(j.get('kind')=='playlist_export' and j.get('payload',{}).get('retry_id')==manifest['id'] and j.get('status') in {'queued','working','paused'} for j in JOBS.values()):
                raise HTTPException(409,'This playlist export is already running.')
            job=new_job(work,kind='playlist_export',payload=payload)
        return {**job,'export_id':manifest['id']}

    @app.get('/api/playlist-exports/{eid}')
    def status(eid:str):return summary(load(eid)[1])

    @app.get('/api/playlist-exports/{eid}/download')
    def download(eid:str):
        folder,manifest=load(eid)
        if not manifest.get('ready') or not (folder/'playlist.zip').is_file():raise HTTPException(404,'Finish a playlist export before downloading.')
        return FileResponse(folder/'playlist.zip',filename=safe_name(manifest['title'])+'.zip')

    @app.post('/api/playlist-exports/{eid}/organize')
    def organize(eid:str):
        folder,manifest=load(eid)
        if not manifest.get('ready'):raise HTTPException(400,'Finish a playlist export first.')
        target=root/'exports'/(safe_name(manifest['title'])[:70]+' - '+eid[:8]);target.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(folder/'playlist.zip') as archive:
            for entry in archive.infolist():
                destination=(target/entry.filename).resolve()
                if not destination.is_relative_to(target.resolve()):raise HTTPException(400,'Invalid archive path.')
            archive.extractall(target)
        opened=False
        if os.name=='nt':
            try:os.startfile(str(target));opened=True
            except OSError:pass
        return {'folder':str(target),'opened':opened}

    RUNNERS['playlist_export']=lambda payload:export_playlist(PlaylistExportRequest(**payload))
