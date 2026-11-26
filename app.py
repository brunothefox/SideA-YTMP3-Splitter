from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
import csv
import io
import os
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import imageio_ffmpeg
import mutagen
import yt_dlp
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from content_cleanup import Redaction, redaction_filter, register_cleanup
from runtime import ASSETS, HOME, VERSION
from jobs import JOBS, RUNNERS, checkpoint, managed_run, new_job, register_jobs
from setup_components import register_setup
from project_io import register_projects
from advanced import register_advanced,stems_for
from youtube_import import YouTubeRequest,register_youtube

ROOT = HOME
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
POOL = ThreadPoolExecutor(max_workers=2)
MAX_UPLOAD = 2 * 1024**3
app = FastAPI(title='Side A — local audio splitter')


@app.middleware('http')
async def local_only(request: Request, call_next):
    # Reject browser requests from other sites, even when they target localhost.
    origin = request.headers.get('origin')
    if origin and origin != f'{request.url.scheme}://{request.headers.get("host")}':
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Open Side A directly on localhost.'}, status_code=403)
    if request.url.hostname not in {'localhost', '127.0.0.1', 'testserver'}:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail': 'Local access only.'}, status_code=403)
    return await call_next(request)


def run_ffmpeg(args, timeout=600):
    result = managed_run([FFMPEG, '-hide_banner', '-nostdin', '-y', *map(str, args)],timeout=timeout)
    if result.returncode:
        message = result.stderr.decode('utf-8', errors='replace')
        raise ValueError('FFmpeg could not process this audio. ' + message[-900:])
    return result


def session_path(sid):
    if not re.fullmatch(r'[a-f0-9]{32}', sid):
        raise HTTPException(404, 'Source not found.')
    path = DATA / sid
    if not (path / 'source.json').exists():
        raise HTTPException(404, 'Source expired or was deleted. Import it again.')
    return path


def get_source(sid):
    directory = session_path(sid)
    source = json.loads((directory / 'source.json').read_text(encoding='utf-8'))
    draft = directory / 'draft.json'
    if draft.exists():
        source['draft'] = json.loads(draft.read_text(encoding='utf-8'))
    return source


def parse_time(value):
    parts = str(value).strip().split(':')
    if not 1 <= len(parts) <= 3:
        raise ValueError('Use seconds, mm:ss, or hh:mm:ss.')
    values = [float(p) for p in parts]
    if any(not math.isfinite(n) or n < 0 for n in values):
        raise ValueError('Timestamps must be positive finite numbers.')
    if len(values) > 1 and any(n >= 60 for n in values[1:]):
        raise ValueError('Minutes and seconds after a colon must be below 60.')
    return sum(n * 60**i for i, n in enumerate(reversed(values)))


def parse_tracklist(text, duration):
    tracks = []
    for line in text.splitlines():
        match = re.match(r'^\s*(?:\d+[.)]\s+)?[\[(]?(\d{1,3}:\d{2}(?::\d{2})?(?:\.\d+)?)[\])]?\s*(?:[-–—|]\s*)?(.*?)\s*$', line)
        if match:
            start = parse_time(match[1])
            if start < duration:
                tracks.append({'start': start, 'title': match[2] or f'Track {len(tracks) + 1:02}'})
    unique = {t['start']: t for t in tracks}
    tracks = sorted(unique.values(), key=lambda t: t['start'])
    if tracks and tracks[0]['start'] > 0:
        tracks.insert(0, {'start': 0, 'title': 'Intro'})
    return tracks


def inspect_audio(path):
    result = run_ffmpeg(['-i', path, '-f', 'ffmetadata', '-'], timeout=120)
    log = result.stderr.decode('utf-8', errors='replace')
    match = re.search(r'Duration: (\d+:\d+:\d+(?:\.\d+)?)', log)
    if not match:
        raise ValueError('Could not read the audio duration. Try a standard audio file.')
    duration = parse_time(match[1])
    stream = re.search(r'Audio: ([^,]+), (\d+) Hz, ([^,\r\n]+)', log)
    bitrate = re.search(r'bitrate: (\d+) kb/s', log)
    tags = {}
    try:
        audio = mutagen.File(path, easy=True)
        if audio:
            tags = {key: str(value[0]) for key, value in (audio.tags or {}).items() if value}
            duration = float(audio.info.length)
    except Exception:
        pass
    metadata = result.stdout.decode('utf-8', errors='replace')
    # WAV/RIFF tags are often invisible to mutagen's easy interface.
    global_fields = dict(re.findall(r'^([^=\n]+)=(.*)$', metadata.split('[CHAPTER]')[0], re.M))
    for key in ('title', 'artist', 'album'):
        if key not in tags and key in global_fields:
            tags[key] = global_fields[key]
    chapters = []
    for block in metadata.split('[CHAPTER]')[1:]:
        fields = dict(re.findall(r'^([^=\n]+)=(.*)$', block, re.M))
        if 'START' in fields:
            numerator, denominator = map(int, fields.get('TIMEBASE', '1/1000').split('/'))
            chapters.append({'start': int(fields['START']) * numerator / denominator,
                             'title': fields.get('title', f'Track {len(chapters) + 1:02}')})
    return {'duration': duration, 'codec': stream[1].split(' ')[0] if stream else 'audio',
            'sample_rate': int(stream[2]) if stream else None,
            'channels': stream[3] if stream else None,
            'bitrate': int(bitrate[1]) if bitrate else None, 'tags': tags, 'chapters': chapters}


def prepare_source(directory, path, info=None):
    audio = inspect_audio(path)
    if audio['duration'] <= 0:
        raise ValueError('This file has no playable audio.')
    tags = audio['tags']
    info = info or {}
    chapters = info.get('chapters') or audio.pop('chapters')
    tracks = [{'start': float(c.get('start_time', c.get('start', 0))),
               'title': c.get('title') or f'Track {i + 1:02}'} for i, c in enumerate(chapters)]
    method = 'Embedded chapters' if tracks else 'Manual markers'
    if not tracks and info.get('description'):
        tracks = parse_tracklist(info['description'], audio['duration'])
        if tracks:
            method = 'Description timestamps'
    if not tracks:
        tracks = [{'start': 0, 'title': tags.get('title') or info.get('title') or path.stem}]
    tracks = sorted({t['start']: t for t in tracks if 0 <= t['start'] < audio['duration']}.values(), key=lambda t: t['start'])
    if not tracks or tracks[0]['start'] > 0:
        tracks.insert(0, {'start': 0, 'title': 'Intro'})
    # A browser-compatible preview also gives a compact real waveform.
    run_ffmpeg(['-i', path, '-map', '0:a:0', '-vn', '-c:a', 'libmp3lame', '-b:a', '128k', directory / 'preview.mp3'])
    raw = run_ffmpeg(['-i', path, '-map', '0:a:0', '-vn', '-ac', '1', '-ar', '100', '-f', 's16le', '-']).stdout
    import array
    samples = array.array('h')
    samples.frombytes(raw)
    step = max(1, len(samples) // 900)
    peaks = [max((abs(n) for n in samples[i:i + step]), default=0) / 32768 for i in range(0, len(samples), step)]
    source = {**audio, 'id': directory.name, 'filename': path.name,
              'title': tags.get('title') or info.get('title') or path.stem,
              'artist': tags.get('artist') or info.get('artist') or info.get('uploader') or '',
              'album': tags.get('album') or info.get('album') or '',
              'tracks': tracks, 'detection': method, 'peaks': peaks,
              'original_extension': path.suffix.lower(), 'created': time.time()}
    (directory / 'source.json').write_text(json.dumps(source), encoding='utf-8')
    return source



@app.get('/api/health')
def health():
    return {'ok': True, 'app':'Side A', 'version':VERSION, 'ffmpeg': Path(FFMPEG).name}


@app.post('/api/upload')
async def upload(file: UploadFile = File(...)):
    sid = uuid.uuid4().hex
    directory = DATA / sid
    directory.mkdir()
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.aiff', '.aif', '.wma', '.mp4', '.webm', '.mka', '.mkv', '.oga', '.alac', '.caf', '.amr'}:
        directory.rmdir()
        raise HTTPException(400, 'Choose an audio file such as MP3, WAV, FLAC, M4A, OGG, or OPUS.')
    path = directory / ('source' + suffix)
    size = 0
    try:
        with path.open('wb') as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, 'The upload limit is 2 GB.')
                output.write(chunk)
    except Exception:
        shutil.rmtree(directory)
        raise
    finally:
        await file.close()
    def work(job):
        job.update(message='Reading metadata and preparing your preview…', progress=20)
        try:
            source = prepare_source(directory, path)
            if source['title'] == 'source':
                source['title'] = Path(file.filename).stem
                source['tracks'][0]['title'] = source['title']
                (directory / 'source.json').write_text(json.dumps(source), encoding='utf-8')
            return source
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
    return new_job(work)


youtube=register_youtube(app,DATA,FFMPEG,MAX_UPLOAD,prepare_source,new_job)


@app.get('/api/jobs/{jid}')
def job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, 'Job not found. Import your source again.')
    return JOBS[jid]


@app.get('/api/sources/{sid}')
def source(sid: str):
    return get_source(sid)


@app.get('/api/sources/{sid}/preview')
def preview(sid: str):
    return FileResponse(session_path(sid) / 'preview.mp3', media_type='audio/mpeg')


@app.get('/api/sources/{sid}/waveform')
def detailed_waveform(sid:str,start:float=0,end:float=10):
    source=get_source(sid)
    if not math.isfinite(start) or not math.isfinite(end) or start<0 or end<=start or end-start>120 or end>source['duration']+.05:
        raise HTTPException(400,'Choose a waveform window within the audio, up to 120 seconds.')
    raw=run_ffmpeg(['-ss',start,'-i',session_path(sid)/source['filename'],'-t',end-start,'-map','0:a:0','-ac','1','-ar','4000','-f','s16le','-']).stdout
    import array
    samples=array.array('h');samples.frombytes(raw);step=max(1,len(samples)//1000)
    return {'start':start,'end':end,'peaks':[max((abs(v) for v in samples[i:i+step]),default=0)/32768 for i in range(0,len(samples),step)]}


class TracklistRequest(BaseModel):
    text: str = Field(max_length=100000)


@app.post('/api/sources/{sid}/tracklist')
def tracklist(sid: str, body: TracklistRequest):
    tracks = parse_tracklist(body.text, get_source(sid)['duration'])
    if not tracks:
        raise HTTPException(400, 'No valid timestamps found. Try: 00:00 First song, with one song per line.')
    return {'tracks': tracks}


class Track(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    title: str = Field(min_length=1, max_length=200)
    selected: bool = True


class ExportRequest(BaseModel):
    tracks: list[Track] = Field(min_length=1, max_length=500)
    format: str = 'mp3'
    artist: str = Field(default='', max_length=200)
    album: str = Field(default='', max_length=200)
    neko: bool = False
    shift: float = Field(default=4, ge=-12, le=96, allow_inf_nan=False)
    volume: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    fit: bool = True
    fade: float = Field(default=0, ge=0, le=3, allow_inf_nan=False)
    padding_start: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    padding_end: float = Field(default=0, ge=0, le=10, allow_inf_nan=False)
    clean_titles: bool = False
    redactions: list[Redaction] = Field(default_factory=list, max_length=1000)
    cleanup_mode: str = 'mute'
    strip_metadata: bool = False
    vocal_only: bool = False


@app.get('/api/library')
def library():
    items = []
    for path in DATA.glob('*/source.json'):
        try:
            source = json.loads(path.read_text(encoding='utf-8'))
            draft_path = path.parent / 'draft.json'
            draft = json.loads(draft_path.read_text(encoding='utf-8')) if draft_path.exists() else {}
            items.append({k: source.get(k) for k in ('id', 'title', 'artist', 'duration', 'codec', 'created')}
                         | {'track_count': len(draft.get('tracks', source['tracks']))})
        except (OSError, ValueError, KeyError):
            continue
    return {'sources': sorted(items, key=lambda s: s.get('created') or 0, reverse=True)[:100]}


class DraftRequest(BaseModel):
    tracks: list[Track] = Field(min_length=1, max_length=500)
    artist: str = Field(default='', max_length=200)
    album: str = Field(default='', max_length=200)
    settings: dict[str, str | float | bool] = Field(default_factory=dict, max_length=20)


@app.put('/api/sources/{sid}/draft')
def save_draft(sid: str, body: DraftRequest):
    source = get_source(sid)
    starts = [t.start for t in body.tracks]
    if starts != sorted(set(starts)) or starts[-1] >= source['duration']:
        raise HTTPException(400, 'Track starts must be unique, in order, and within the audio.')
    directory = session_path(sid)
    temp = directory / f'draft-{uuid.uuid4().hex}.tmp'
    temp.write_text(body.model_dump_json(), encoding='utf-8')
    temp.replace(directory / 'draft.json')
    return {'saved': True}


def safe_name(name):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:100]
    if not cleaned or cleaned.upper().split('.')[0] in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        return 'Track'
    return cleaned


def clean_title(title):
    title = unicodedata.normalize('NFKC', title)
    title = re.sub(r'https?://\S+', '', title)
    title = re.sub(r'[\[(](?:official\s*(?:music\s*)?(?:video|audio|visualizer)?|lyrics?|\d{3,4}p|4k|hd|hq)[\])]', '', title, flags=re.I)
    title = re.sub(r'^\s*\d{1,3}\s*[.)-]\s*', '', title)
    title = ''.join(c for c in title if c.isalnum() or c in " -'()")
    return re.sub(r'\s+', ' ', title).strip(' -')[:100] or 'Untitled Track'


def prepare_export(sid: str, body: ExportRequest):
    source = get_source(sid)
    if body.format not in {'mp3', 'flac', 'wav', 'original', 'ogg'}:
        raise HTTPException(400, 'Choose MP3, FLAC, WAV, or original audio.')
    if body.neko and body.format not in {'mp3', 'ogg', 'wav', 'flac'}:
        raise HTTPException(400, 'Pitch and speed processing supports MP3, OGG, FLAC, and WAV.')
    if body.format == 'original' and (body.padding_start or body.padding_end or body.fade):
        raise HTTPException(400, 'Padding and fades require re-encoding. Choose MP3, OGG, FLAC, or WAV.')
    if body.cleanup_mode not in {'mute', 'bleep'}:
        raise HTTPException(400, 'Choose mute or bleep for content cleanup.')
    if body.redactions and body.format == 'original':
        raise HTTPException(400, 'Content cleanup requires re-encoding. Choose MP3, OGG, FLAC, or WAV.')
    if any(edit.end > source['duration']+.05 for edit in body.redactions):
        raise HTTPException(400, 'Keep content-cleanup marks within the source duration.')
    if body.vocal_only and body.redactions and not all(p.exists() for p in stems_for(source,session_path(sid))):
        raise HTTPException(400,'Separate vocals in the cleanup panel before choosing vocal-only cleanup.')
    starts = [t.start for t in body.tracks]
    if starts != sorted(set(starts)) or any(t >= source['duration'] for t in starts):
        raise HTTPException(400, 'Track starts must be unique, in order, and before the end of the audio.')
    if not any(t.selected for t in body.tracks):
        raise HTTPException(400, 'Select at least one track.')
    directory = session_path(sid)
    eid = uuid.uuid4().hex
    target = directory / eid
    target.mkdir()
    def work(job):
        chosen = [t for t in body.tracks if t.selected]
        codec = source['codec']
        copy_ext = {'aac': '.m4a', 'alac': '.m4a', 'opus': '.ogg', 'vorbis': '.ogg',
                    'mp3': '.mp3', 'flac': '.flac'}.get(codec, '.mka')
        extension = copy_ext if body.format == 'original' else '.' + body.format
        settings = {'mp3': ['-c:a', 'libmp3lame', '-b:a', '320k'],
                    'ogg': ['-c:a', 'libvorbis', '-q:a', '6'],
                    'flac': ['-c:a', 'flac'], 'wav': ['-c:a', 'pcm_s24le'],
                    'original': ['-c:a', 'copy']}[body.format]
        files = []
        try:
            for index, track in enumerate(body.tracks):
                if not track.selected:
                    continue
                end = body.tracks[index + 1].start if index + 1 < len(body.tracks) else source['duration']
                shift = body.shift
                padding = body.padding_start + body.padding_end
                if body.neko and body.fit:
                    shift = max(shift, math.ceil(12 * math.log2((end - track.start) / (419 - padding)) * 10) / 10)
                speed = 2 ** (shift / 12) if body.neko else 1
                content_duration = (end - track.start) / speed
                output_duration = content_duration + padding
                title = clean_title(track.title) if body.clean_titles else track.title
                name = f'{index + 1:02} - {safe_name(title)}{extension}'
                job.update(message=f'Exporting {len(files) + 1} of {len(chosen)}: {track.title}', progress=100 * len(files) / len(chosen))
                filters = []
                if body.neko:
                    # Trim before changing sample rate: output duration is source duration / speed.
                    sample_rate = source.get('sample_rate') or 48000
                    filters = ['-af', f'atrim=duration={end-track.start},asetpts=PTS-STARTPTS,asetrate={sample_rate}*{speed},aresample=48000,volume={body.volume}']
                    if body.fade:
                        fade = min(body.fade, content_duration / 2)
                        filters[-1] += f',afade=t=in:d={fade},afade=t=out:st={max(0,content_duration-fade)}:d={fade}'
                    if padding:
                        filters[-1] += f',adelay={body.padding_start*1000}:all=1,apad=pad_dur={body.padding_end}'
                    filters += ['-ar', '48000', '-ac', '2']
                elif padding or body.fade:
                    chain = f'atrim=duration={end-track.start},asetpts=PTS-STARTPTS'
                    if body.fade:
                        fade = min(body.fade, content_duration/2)
                        chain += f',afade=t=in:d={fade},afade=t=out:st={content_duration-fade}:d={fade}'
                    if padding:
                        chain += f',adelay={body.padding_start*1000}:all=1,apad=pad_dur={body.padding_end}'
                    filters = ['-af', chain]
                cleanup = redaction_filter(body.redactions, track.start, end, body.cleanup_mode)
                script = None
                input_args = ['-ss',track.start,'-i',directory/source['filename']]
                mapping = '0:a:0'
                if cleanup and body.vocal_only:
                    vocals,instrumental=stems_for(source,directory)
                    input_args=['-ss',track.start,'-i',vocals,'-ss',track.start,'-i',instrumental]
                    tail='anull'
                    if '-af' in filters:
                        af_index=filters.index('-af');tail=filters[af_index+1];filters[af_index:af_index+2]=[]
                    graph=f'[0:a]asetpts=PTS-STARTPTS,{cleanup}[v];[1:a]asetpts=PTS-STARTPTS[i];[v][i]amix=inputs=2:normalize=0,aresample={source.get("sample_rate") or 48000},{tail}[cleaned]'
                    script=target/f'.{index}.filter';script.write_text(graph,encoding='utf-8')
                    filters=['-/filter_complex',script,*filters];mapping='[cleaned]'
                elif cleanup:
                    if '-af' in filters:
                        af_index = filters.index('-af')
                        filters[af_index+1] = 'asetpts=PTS-STARTPTS,' + cleanup + ',' + filters[af_index+1]
                    else:
                        filters = ['-af', 'asetpts=PTS-STARTPTS,'+cleanup, *filters]
                if '-af' in filters:
                    af_index = filters.index('-af')
                    script = target / f'.{index}.filter'
                    script.write_text(filters[af_index+1], encoding='utf-8')
                    filters[af_index:af_index+2] = ['-/af', script]
                args = [*input_args, '-t', output_duration,
                        '-map', mapping, '-vn', '-map_chapters', '-1', *settings, *filters,
                        '-map_metadata', '-1']
                if body.strip_metadata:
                    args += ['-metadata','encoder=']
                    if extension == '.mp3':
                        args += ['-id3v2_version','0','-write_id3v1','0']
                else:
                    args += ['-metadata', f'title={title}', '-metadata', f'artist={body.artist}',
                             '-metadata', f'album={body.album}', '-metadata', f'track={index + 1}']
                args += [target / name]
                try:
                    run_ffmpeg(args, timeout=1800)
                finally:
                    if script:
                        script.unlink(missing_ok=True)
                files.append({'name': name, 'size': (target / name).stat().st_size,
                              'url': f'/api/sources/{sid}/downloads/{eid}/{quote(name, safe="")}',
                              'duration': output_duration, 'effectSpeed': None,
                              'shift': round(shift,2) if body.neko else 0})
            extra_files = []
            if body.redactions:
                report = {'mode':body.cleanup_mode, 'edits':[e.model_dump() for e in body.redactions],
                          'notice':'User-reviewed content edits. Not a moderation verdict or copyright clearance.'}
                (target / 'content-cleanup-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
                extra_files.append('content-cleanup-report.json')
            archive = target / 'tracks.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as bundle:
                for item in files:
                    bundle.write(target / item['name'], item['name'])
                for name in extra_files:
                    bundle.write(target / name, name)
            result = {'files': files, 'zip': f'/api/sources/{sid}/downloads/{eid}/tracks.zip',
                    'zip_name': safe_name(source['title']) + '.zip',
                    'config': [], 'export_id': eid, 'cleanup_count':len(body.redactions)}
            (target / 'export.json').write_text(json.dumps(result), encoding='utf-8')
            return result
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
    return work


@app.post('/api/sources/{sid}/export')
def export(sid: str, body: ExportRequest):
    return new_job(prepare_export(sid,body),kind='export',payload={'sid':sid,'body':body.model_dump()})


class OrganizeRequest(BaseModel):
    name: str = Field(default='', max_length=100)
    open_folder: bool = True


@app.post('/api/sources/{sid}/exports/{eid}/organize')
def organize(sid: str, eid: str, body: OrganizeRequest):
    if not re.fullmatch(r'[a-f0-9]{32}', eid):
        raise HTTPException(404, 'Export not found.')
    source = get_source(sid)
    export_dir = session_path(sid) / eid
    if not (export_dir / 'export.json').is_file():
        raise HTTPException(404, 'Finish an export first.')
    result = json.loads((export_dir / 'export.json').read_text(encoding='utf-8'))
    folder = ROOT / 'exports' / (safe_name(body.name or source['title'])[:70] + ' - ' + eid[:8])
    (folder / 'Audio').mkdir(parents=True, exist_ok=True)
    for item in result['files']:
        filename = Path(item['name']).name
        shutil.copy2(export_dir / filename, folder / 'Audio' / filename)
    if result.get('config'):
        (folder / 'Config').mkdir(exist_ok=True)
        for filename in ('nekodj-track-values.json', 'nekodj-track-values.csv', 'nekodj-config-template.lua'):
            shutil.copy2(export_dir / filename, folder / 'Config' / filename)
    if (export_dir / 'content-cleanup-report.json').exists():
        (folder / 'Config').mkdir(exist_ok=True)
        shutil.copy2(export_dir / 'content-cleanup-report.json', folder / 'Config' / 'content-cleanup-report.json')
    opened = False
    if body.open_folder and os.name == 'nt':
        try:
            os.startfile(str(folder))
            opened = True
        except OSError:
            pass
    return {'folder': str(folder), 'opened': opened}


@app.get('/api/sources/{sid}/downloads/{eid}/{filename}')
def download(sid: str, eid: str, filename: str):
    if not re.fullmatch(r'[a-f0-9]{32}', eid) or Path(filename).name != filename:
        raise HTTPException(404, 'File not found.')
    base = session_path(sid)
    path = base / eid / filename
    if not path.is_file() or not path.resolve().is_relative_to(base.resolve()):
        raise HTTPException(404, 'File not found.')
    return FileResponse(path, filename=filename)


RUNNERS['export']=lambda payload:export(payload['sid'],ExportRequest(**payload['body']))
RUNNERS['youtube']=lambda payload:youtube(YouTubeRequest(**payload))
register_jobs(app)
register_setup(app)
register_projects(app,get_source,session_path,prepare_source,DraftRequest)
register_advanced(app,get_source,session_path,run_ffmpeg)
register_cleanup(app, ROOT, get_source, session_path, run_ffmpeg, new_job)
from playlist_exports import register_playlist_exports
register_playlist_exports(app,DATA,ROOT,get_source,session_path,prepare_export,ExportRequest,safe_name)
app.mount('/', StaticFiles(directory=ASSETS / 'static', html=True), name='static')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
