"""Project backup/restore and disk cleanup with checked workspace boundaries."""
import json
import shutil
import uuid
import zipfile
from pathlib import Path,PurePosixPath
from fastapi import File,UploadFile,HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from jobs import JOBS,new_job
from runtime import HOME


def register_projects(app,get_source,session_path,prepare_source,DraftRequest):
    @app.get('/api/sources/{sid}/backup')
    def backup(sid:str):
        directory=session_path(sid)
        target=HOME/'data/.backups';target.mkdir(exist_ok=True)
        archive=target/(sid+'.sidea.zip')
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as bundle:
            source=get_source(sid)
            for path in directory.rglob('*'):
                if not path.is_file() or path.is_symlink():continue
                relative=path.relative_to(directory)
                if len(relative.parts)>1 and relative.parts[0]!='transcript-sections':continue
                if path.name==source['filename'] or path.suffix=='.json' or path.name=='preview.mp3':bundle.write(path,str(relative).replace('\\','/'))
        return FileResponse(archive,filename=source['title'][:60]+'.sidea.zip')

    @app.post('/api/projects/restore')
    async def restore(file:UploadFile=File(...)):
        sid=uuid.uuid4().hex;directory=HOME/'data'/sid;directory.mkdir(parents=True)
        archive=directory/'restore.zip'
        try:
            with archive.open('wb') as output:
                total=0
                while chunk:=await file.read(1024*1024):
                    total+=len(chunk)
                    if total>2*1024**3:raise HTTPException(413,'Project backup exceeds 2 GB.')
                    output.write(chunk)
            with zipfile.ZipFile(archive) as bundle:
                if len(bundle.infolist())>20000 or sum(m.file_size for m in bundle.infolist())>3*1024**3:raise HTTPException(400,'Backup is too large.')
                for member in bundle.infolist():
                    path=PurePosixPath(member.filename.replace('\\','/'))
                    target=directory.joinpath(*path.parts)
                    if path.is_absolute() or '..' in path.parts or not target.resolve().is_relative_to(directory.resolve()) or (member.external_attr>>16)&0o170000==0o120000:
                        raise HTTPException(400,'Backup contains an unsafe path.')
                    if member.filename=='restore.zip':raise HTTPException(400,'Invalid backup.')
                    if member.is_dir():target.mkdir(parents=True,exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True,exist_ok=True)
                        with bundle.open(member) as incoming,target.open('wb') as outgoing:shutil.copyfileobj(incoming,outgoing)
            archive.unlink()
            metadata=directory/'source.json'
            if not metadata.exists() or metadata.stat().st_size>5*1024**2:raise HTTPException(400,'Not a Side A project backup.')
            source=json.loads(metadata.read_text(encoding='utf-8'));filename=source.get('filename','')
            if Path(filename).name!=filename or not filename.startswith('source.') or not (directory/filename).is_file():raise HTTPException(400,'Backup audio is missing.')
            def work(job):
                try:
                    job.update(progress=20,message='Checking project audio and rebuilding its preview…')
                    draft_path=directory/'draft.json'
                    draft=DraftRequest(**json.loads(draft_path.read_text(encoding='utf-8'))) if draft_path.exists() else None
                    result=prepare_source(directory,directory/filename)
                    for field in ('title','artist','album'):
                        if isinstance(source.get(field),str):result[field]=source[field][:300]
                    (directory/'source.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
                    if draft:
                        starts=[t.start for t in draft.tracks]
                        if starts!=sorted(set(starts)) or starts[-1]>=result['duration']:raise ValueError('Backup tracklist is outside the audio.')
                        result['draft']=draft.model_dump()
                    return result
                except Exception:
                    shutil.rmtree(directory,ignore_errors=True);raise
            return new_job(work,kind='restore')
        except Exception:
            shutil.rmtree(directory,ignore_errors=True);raise
        finally:await file.close()

    @app.delete('/api/sources/{sid}')
    def delete(sid:str):
        directory=session_path(sid)
        if any(j.get('status') in {'working','queued','paused'} and j.get('payload',{}).get('sid')==sid for j in JOBS.values()):raise HTTPException(409,'Finish or cancel this project’s jobs first.')
        if not directory.resolve().is_relative_to((HOME/'data').resolve()):raise HTTPException(400,'Invalid project path.')
        shutil.rmtree(directory)
        return {'deleted':True}

    @app.get('/api/storage')
    def storage():
        return {'bytes':sum(p.stat().st_size for p in (HOME/'data').rglob('*') if p.is_file()),'workspace':str(HOME)}
