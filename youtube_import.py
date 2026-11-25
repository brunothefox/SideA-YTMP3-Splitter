"""Normalize supported YouTube links and import bounded, reviewable collections."""
from __future__ import annotations
import json
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urljoin, urlparse
import yt_dlp
from fastapi import HTTPException
from pydantic import BaseModel,Field
from jobs import JOBS,RUNNERS,Cancelled,checkpoint

HOSTS={'youtube.com','www.youtube.com','m.youtube.com','music.youtube.com','youtu.be','www.youtu.be','youtube-nocookie.com','www.youtube-nocookie.com'}
VIDEO_ID=re.compile(r'[A-Za-z0-9_-]{11}\Z')


class YouTubeRequest(BaseModel):
    url:str=Field(min_length=1,max_length=2048)
    prefer_playlist:bool=False
    playlist_start:int=Field(default=1,ge=1,le=100000)
    playlist_limit:int=Field(default=50,ge=1,le=200)
    video_ids:list[str]|None=Field(default=None,max_length=200)
    batch_id:str|None=Field(default=None,pattern=r'^[a-f0-9]{32}$')


def normalize_youtube_url(value,prefer_playlist=False,depth=0):
    value=value.strip()
    if '://' not in value:value='https://'+value
    try:
        parsed=urlparse(value)
        if parsed.scheme not in {'http','https'} or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in {None,80,443}:
            raise ValueError()
    except ValueError:raise HTTPException(400,'Paste a YouTube video, Short, playlist, or channel link.')
    query=parse_qs(parsed.query)
    if depth<2 and parsed.path in {'/attribution_link','/redirect'}:
        nested=(query.get('u') or query.get('q') or [''])[0]
        if nested:return normalize_youtube_url(urljoin('https://www.youtube.com',nested),prefer_playlist,depth+1)
    parts=parsed.path.strip('/').split('/')
    video=(parts[0] if parsed.hostname.endswith('youtu.be') and len(parts)==1 else
           query.get('v',[''])[0] if parts==['watch'] else
           parts[1] if len(parts)==2 and parts[0] in {'shorts','live','embed','v','e'} else '')
    playlist=query.get('list',[''])[0]
    playlist_ok=bool(re.fullmatch(r'[A-Za-z0-9_-]{10,128}',playlist) or playlist=='RDMM')
    if playlist and (prefer_playlist or not VIDEO_ID.fullmatch(video)):
        if not playlist_ok:raise HTTPException(400,'The playlist ID in this link is invalid.')
        return {'kind':'collection','url':'https://www.youtube.com/playlist?list='+playlist,'collection_type':'playlist'}
    if VIDEO_ID.fullmatch(video):
        return {'kind':'video','url':'https://www.youtube.com/watch?v='+video,'video_id':video}
    channel=(len(parts) in {1,2} and parts[0].startswith('@') and len(parts[0])>1 and (len(parts)==1 or parts[1] in {'videos','shorts','streams'}))
    channel=channel or (len(parts) in {2,3} and parts[0] in {'channel','c','user'} and bool(parts[1]) and (len(parts)==2 or parts[2] in {'videos','shorts','streams'}))
    if channel:
        path=parsed.path.rstrip('/')
        if parts[-1] not in {'videos','shorts','streams'}:path+='/videos'
        return {'kind':'collection','url':'https://www.youtube.com'+path,'collection_type':'channel'}
    raise HTTPException(400,'Use a video, Short, recorded-live, embed, playlist, or channel uploads link.')


def register_youtube(app,data,ffmpeg,maximum_size,prepare_source,new_job):
    batches=data/'.youtube-batches';batches.mkdir(exist_ok=True)
    lock=threading.Lock()

    def options():
        return {'quiet':True,'no_warnings':True,'socket_timeout':30,'retries':2,
                'ffmpeg_location':ffmpeg,'js_runtimes':{'node':{}},'remote_components':['ejs:github']}

    def download_one(video_id,progress):
        checkpoint()
        directory=data/uuid.uuid4().hex;directory.mkdir()
        def hook(event):
            checkpoint()
            if event['status']=='downloading':
                total=event.get('total_bytes') or event.get('total_bytes_estimate') or 0
                downloaded=event.get('downloaded_bytes',0)
                if downloaded>maximum_size:raise ValueError('This video exceeds the 2 GB import limit.')
                progress(min(.75,.75*downloaded/total) if total else .1,'Downloading the best available audio…')
        def match(info,**kwargs):
            checkpoint()
            if info.get('is_live') or info.get('live_status') in {'is_live','is_upcoming'}:
                return 'Ongoing or upcoming live streams cannot be imported. Use a completed recording.'
        settings={**options(),'format':'bestaudio/best','noplaylist':True,'outtmpl':str(directory/'source.%(ext)s'),
                  'progress_hooks':[hook],'max_filesize':maximum_size,'match_filter':match}
        try:
            progress(.02,'Reading video information…')
            with yt_dlp.YoutubeDL(settings) as downloader:
                info=downloader.extract_info('https://www.youtube.com/watch?v='+video_id,download=True)
                if not info or info.get('_type') in {'playlist','multi_video'}:raise ValueError('No single-video audio was returned.')
                path=Path(downloader.prepare_filename(info))
            if not path.is_file():raise ValueError('No audio file was downloaded. The video may be unavailable or over the size limit.')
            progress(.8,'Reading chapters and preparing the preview…')
            source=prepare_source(directory,path,info)
            source['youtube_url']='https://www.youtube.com/watch?v='+video_id
            (directory/'source.json').write_text(json.dumps(source,ensure_ascii=False),encoding='utf-8')
            return source
        except BaseException:
            shutil.rmtree(directory,ignore_errors=True)
            raise

    def write_batch(batch):
        path=batches/(batch['id']+'.json');temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(batch,ensure_ascii=False),encoding='utf-8');temp.replace(path)

    def summarize(batch):
        return {'kind':'youtube_batch','batch_id':batch['id'],'title':batch['title'],'items':batch['items'],
                'imported':sum(item['status']=='imported' for item in batch['items']),
                'failed':sum(item['status']=='error' for item in batch['items'])}

    @app.post('/api/youtube')
    def youtube(body:YouTubeRequest):
        link=normalize_youtube_url(body.url,body.prefer_playlist)
        if body.video_ids is not None:
            if not body.video_ids or any(not VIDEO_ID.fullmatch(v) for v in body.video_ids):
                raise HTTPException(400,'Select at least one valid YouTube video (up to 200).')
            ids=list(dict.fromkeys(body.video_ids))
            if body.batch_id:
                path=batches/(body.batch_id+'.json')
                if not path.exists():raise HTTPException(404,'Batch not found. Read the playlist again.')
                batch=json.loads(path.read_text(encoding='utf-8'))
                if batch['url']!=link['url'] or [i['video_id'] for i in batch['items']]!=ids:
                    raise HTTPException(400,'Retry the original batch without changing its videos.')
            else:
                batch={'id':uuid.uuid4().hex,'url':link['url'],'title':'YouTube collection',
                       'items':[{'video_id':v,'title':v,'status':'queued'} for v in ids]}
                write_batch(batch)
            payload=body.model_dump();payload['batch_id']=batch['id']
            def work(job):
                try:
                    for index,item in enumerate(batch['items']):
                        checkpoint()
                        if item.get('source_id') and (data/item['source_id']/'source.json').exists():
                            item['status']='imported';continue
                        item.update(status='working',error=None);write_batch(batch)
                        def progress(fraction,message):
                            job.update(progress=100*(index+fraction)/len(batch['items']),
                                       message=f'Video {index+1} of {len(batch["items"])}: {message}')
                        try:
                            source=download_one(item['video_id'],progress)
                            item.update(status='imported',source_id=source['id'],title=source['title'],
                                        duration=source['duration'],track_count=len(source['tracks']))
                        except Cancelled:
                            item['status']='queued';write_batch(batch);raise
                        except Exception as error:
                            item.update(status='error',error=str(error)[-1000:])
                        write_batch(batch)
                    return summarize(batch)
                finally:pass
            with lock:
                if any(j.get('kind')=='youtube_batch' and j.get('payload',{}).get('batch_id')==batch['id'] and j.get('status') in {'queued','working','paused'} for j in JOBS.values()):
                    raise HTTPException(409,'This playlist batch is already importing.')
                result=new_job(work,kind='youtube_batch',payload=payload)
            return {**result,'batch_id':batch['id']}
        if link['kind']=='video':
            def work(job):
                try:return download_one(link['video_id'],lambda fraction,message:job.update(progress=100*fraction,message=message))
                except Cancelled:raise
                except Exception as error:raise ValueError('YouTube import failed: '+str(error)) from error
            return new_job(work,kind='youtube',payload=body.model_dump())
        def inspect(job):
            checkpoint();job.update(progress=10,message='Reading videos from this YouTube collection…')
            settings={**options(),'extract_flat':'in_playlist','skip_download':True,'ignoreerrors':True,
                      'noplaylist':False,'playliststart':body.playlist_start,'playlistend':body.playlist_start+body.playlist_limit-1}
            with yt_dlp.YoutubeDL(settings) as downloader:info=downloader.extract_info(link['url'],download=False)
            if not info:raise ValueError('This collection is unavailable or requires sign-in.')
            entries=[]
            for index,entry in enumerate(info.get('entries') or []):
                checkpoint()
                if index>=body.playlist_limit:break
                position=body.playlist_start+index
                if not entry:
                    entries.append({'position':position,'title':'Unavailable video','available':False});continue
                vid=entry.get('id') or ''
                available=bool(VIDEO_ID.fullmatch(vid)) and entry.get('availability') not in {'private','premium_only','subscriber_only','needs_auth'}
                entries.append({'position':entry.get('playlist_index') or position,'video_id':vid,
                                'title':entry.get('title') or vid or 'Unavailable video',
                                'duration':entry.get('duration'),'channel':entry.get('channel') or entry.get('uploader') or '',
                                'available':available})
            if not entries:raise ValueError('No videos were found in this range. Try a different starting position.')
            return {'kind':'youtube_collection','url':link['url'],'title':info.get('title') or 'YouTube collection',
                    'items':entries,'total':info.get('playlist_count') or info.get('n_entries'),
                    'start':body.playlist_start,'limit':body.playlist_limit}
        return new_job(inspect,kind='youtube',payload=body.model_dump())

    @app.get('/api/youtube/batches/{bid}')
    def batch_status(bid:str):
        if not re.fullmatch(r'[a-f0-9]{32}',bid):raise HTTPException(404,'Batch not found.')
        path=batches/(bid+'.json')
        if not path.exists():raise HTTPException(404,'Batch not found.')
        return summarize(json.loads(path.read_text(encoding='utf-8')))

    RUNNERS['youtube']=lambda payload:youtube(YouTubeRequest(**payload))
    RUNNERS['youtube_batch']=RUNNERS['youtube']
    return youtube
