"""Local speech review and destructive explicit-language removal.

This is a word-list editing tool, not a platform moderation classifier.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import unicodedata
import uuid
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from runtime import ASSETS, HOME, tool
from jobs import RUNNERS, checkpoint
from speech_engine import ENGINE

POLICY_URL = 'https://about.roblox.com/community-standards'
PACKS = {
    'English — strong': ['fuck', 'fucking', 'fucked', 'fucker', 'fuckers', 'motherfucker', 'motherfuckers', 'motherfucking', 'shit', 'shits', 'shitty', 'bullshit', 'bitch', 'bitches', 'bitching', 'asshole', 'assholes', 'bastard', 'bastards', 'dick', 'dicks', 'cock', 'cocks', 'pussy', 'pussies', 'cunt', 'cunts'],
    'English — mild / context review': ['damn', 'damned', 'hell', 'ass', 'crap', 'piss', 'pissed', 'slut', 'whore'],
    'Spanish — starter': ['mierda', 'puta', 'putas', 'puto', 'putos', 'joder', 'jodido', 'cabron', 'cabrones', 'coño', 'cojones', 'pendejo', 'pendeja', 'chingar', 'chingada', 'chingado', 'verga', 'carajo', 'culero', 'hijo de puta'],
    'Malay / Indonesian — starter': ['babi', 'bangsat', 'bajingan', 'anjing', 'sial', 'sialan', 'celaka', 'bodoh', 'kontol', 'memek', 'pukimak', 'kimak', 'cibai', 'lancau', 'pantat', 'jancuk'],
}
THEMES = {
    'Sexual content — context review': ['have sex', 'sexual intercourse', 'pornography', 'pornographic', 'naked body', 'oral sex', 'strip club', 'tener sexo', 'sexo oral'],
    'Threats & graphic violence — context review': ['kill you', 'shoot you', 'stab you', 'blow your head', 'cut your throat', 'murder', 'rape', 'te voy a matar'],
    'Drugs & intoxication — context review': ['cocaine', 'heroin', 'methamphetamine', 'crack cocaine', 'smoke weed', 'get drunk', 'drug dealer', 'cocaina', 'marihuana'],
    'Self-harm — context review': ['kill myself', 'kill yourself', 'take my own life', 'end my life', 'commit suicide', 'cut myself'],
    'Personal information — context review': ['my phone number', 'my home address', 'my password', 'credit card number', 'social security number'],
    'Harassment & discrimination — context review': ['racial slur', 'go back to your country', 'inferior race', 'hate your race', 'you are worthless'],
}
EXTENDED = ASSETS / 'resources' / 'extended-english.txt'
if EXTENDED.exists():
    PACKS['English — extended dictionary (review context)'] = [w.strip() for w in EXTENDED.read_text(encoding='utf-8').splitlines() if w.strip()]


class Redaction(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)
    word: str = Field(default='Manual edit', max_length=200)

    @model_validator(mode='after')
    def ordered(self):
        if self.end <= self.start:
            raise ValueError('End must follow start.')
        return self


class ScanRequest(BaseModel):
    language: Literal['auto', 'en', 'es', 'ms', 'id', 'fr', 'de', 'pt', 'ja', 'ko', 'zh', 'ar', 'hi'] = 'auto'
    terms: list[str] = Field(min_length=1, max_length=3000)
    ranges: list[Redaction] = Field(default_factory=list, max_length=500)
    margin: float = Field(default=.15, ge=0, le=1, allow_inf_nan=False)
    themes: bool = True
    quality: Literal['balanced','accurate','accurate_fast'] = 'balanced'
    device: Literal['auto','cpu','gpu'] = 'auto'


class CleanupRequest(BaseModel):
    edits: list[Redaction] = Field(min_length=1, max_length=1000)
    mode: Literal['mute', 'bleep'] = 'mute'
    vocal_only: bool = False


def normal(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return ''.join(c for c in value if not unicodedata.combining(c))


def word_parts(value):
    return re.findall(r"[^\W_]+(?:['’][^\W_]+)?", normal(value), re.UNICODE)


def extract_words(document, offset=0):
    """Rejoin BPE tokens before whole-word matching, preserving timestamp spans."""
    words = []
    for segment in document.get('transcription', []):
        tokens = [t for t in segment.get('tokens', []) if t.get('offsets') and not t.get('text', '').startswith('[_') and not t.get('text', '').startswith('<|')]
        if any('\ufffd' in t.get('text','') for t in tokens):
            # Older CLI builds can split multibyte characters across BPE tokens.
            # Preserve the intact segment text and explicitly mark approximate timing.
            tokens = []
        if tokens:
            text, spans = '', []
            for token in tokens:
                start = len(text)
                text += token.get('text', '')
                spans.append((start, len(text), token))
            for match in re.finditer(r"[^\W_]+(?:['’][^\W_]+)?", text, re.UNICODE):
                overlapping = [t for a, b, t in spans if a < match.end() and b > match.start()]
                starts = [t['offsets']['from'] for t in overlapping if t['offsets']['from'] >= 0]
                ends = [t['offsets']['to'] for t in overlapping if t['offsets']['to'] >= 0]
                if starts and ends:
                    start, end = min(starts) / 1000 + offset, max(ends) / 1000 + offset
                    if end <= start:
                        end = start + .08
                    words.append({'text': match.group(), 'start': start, 'end': end,
                                  'confidence': round(sum(t.get('p', 0) for t in overlapping) / len(overlapping), 3)})
        else:
            text = segment.get('text', '').strip()
            offsets = segment.get('offsets', {})
            parts = re.findall(r"[^\W_]+(?:['’][^\W_]+)?", text)
            if not parts:
                continue
            start, end = offsets.get('from', 0) / 1000 + offset, offsets.get('to', 0) / 1000 + offset
            for i, part in enumerate(parts):
                words.append({'text': part, 'start': start+(end-start)*i/len(parts),
                              'end': start+(end-start)*(i+1)/len(parts), 'confidence': 0,
                              'approximate': True})
    return words


def find_matches(words, terms, duration, margin=.15):
    normalized = [normal(w['text']).replace('’', "'") for w in words]
    patterns = {tuple(word_parts(term)): term.strip() for term in terms if word_parts(term)}
    by_first = {}
    for parts,term in patterns.items():
        by_first.setdefault(parts[0],[]).append((parts,term))
    matches = []
    for i in range(len(words)):
        for parts, term in by_first.get(normalized[i], []):
            count = len(parts)
            if tuple(normalized[i:i+count]) != parts:
                continue
            chosen = words[i:i+count]
            if any(b['start']-a['end'] > 1.5 for a, b in zip(chosen, chosen[1:])):
                continue
            start, end = max(0, chosen[0]['start']-margin), min(duration, chosen[-1]['end']+margin)
            if end <= start:
                continue
            if any(m['term'] == term and abs(m['start']-start) < .25 for m in matches):
                continue
            matches.append({'start': round(start, 3), 'end': round(end, 3), 'word': ' '.join(w['text'] for w in chosen),
                            'term': term, 'confidence': round(min(w['confidence'] for w in chosen), 3),
                            'approximate': any(w.get('approximate') for w in chosen),
                            'context': ' '.join(w['text'] for w in words[max(0,i-5):i+count+5])})
    return sorted(matches, key=lambda m: (m['start'], m['end']))


def merged_intervals(edits, start, end):
    spans = sorted((max(0, e.start-start), min(end, e.end)-start) for e in edits if e.end > start and e.start < end)
    merged = []
    for a, b in spans:
        if b <= a:
            continue
        if merged and a <= merged[-1][1] + .005:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return merged


def redaction_filter(edits, start, end, mode):
    spans = merged_intervals(edits, start, end)
    if not spans:
        return ''
    # Six-millisecond transitions inside the marked intervals reduce clicks.
    envelopes = [f'min(1,max(0,(t-{a:.6f})/0.006))*min(1,max(0,({b:.6f}-t)/0.006))' for a,b in spans]
    gate = 'min(1,' + '+'.join(envelopes) + ')'
    signal = f'val(ch)*(1-({gate}))'
    if mode == 'bleep':
        signal += f'+0.12*sin(2*PI*1000*t)*({gate})'
    return "aeval=exprs='" + signal + "':c=same"


def register_cleanup(app, root, get_source, session_path, run_ffmpeg, new_job):
    engine = tool('whisper-server')
    model = root / 'tools' / 'models' / 'ggml-base.bin'

    @app.get('/api/cleanup/status')
    def status():
        return {'ready': engine.is_file() and model.is_file(), 'engine': 'whisper.cpp',
                'compact_ready':(root/'tools/models/ggml-small-q5_0.bin').is_file(), 'gpu_ready':(root/'tools/whisper-cuda/Release/whisper-server.exe').exists(), 'model': 'Whisper base multilingual', 'accurate_ready': (root/'tools/models/ggml-small.bin').is_file(),
                'packs': PACKS, 'themes':list(THEMES), 'policy_url': POLICY_URL}

    @app.get('/api/sources/{sid}/cleanup/analysis')
    def saved_analysis(sid: str):
        path = session_path(sid) / 'cleanup-analysis.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

    @app.post('/api/sources/{sid}/cleanup/scan')
    def scan(sid: str, body: ScanRequest):
        source, directory = get_source(sid), session_path(sid)
        selected_model = root/'tools/models'/({'balanced':'ggml-base.bin','accurate':'ggml-small.bin','accurate_fast':'ggml-small-q5_0.bin'}[body.quality])
        if not engine.is_file() or not selected_model.is_file():
            raise HTTPException(503, 'The local speech engine is missing. Run setup-cleanup.ps1, then try again.')
        if any(len(t) > 150 or not word_parts(t) for t in body.terms):
            raise HTTPException(400, 'Use words or short phrases, one per line, up to 150 characters each.')
        ranges = merged_intervals(body.ranges, 0, source['duration']) if body.ranges else [[0, source['duration']]]
        if not ranges:
            raise HTTPException(400, 'Select a range inside the audio.')
        cache_key = hashlib.sha256(json.dumps([body.language, ranges, body.quality, 'v1']).encode()).hexdigest()
        cache_path = directory / 'cleanup-transcript.json'
        def work(job):
            words = []
            languages = set()
            chunks=[]
            for start,end in ranges:
                position=math.floor(start/60)*60
                while position<end:
                    span=(position,min(source['duration'],position+61.5))
                    if span not in chunks:chunks.append(span)
                    position+=60
            chunks.sort()
            sections=directory/'transcript-sections'
            sections.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='speech-',dir=directory) as temp:
                temp=Path(temp)
                for index,(start,end) in enumerate(chunks):
                    checkpoint()
                    section_key=hashlib.sha256(json.dumps([start,end,body.language,body.quality,'warm-v2']).encode()).hexdigest()
                    cached=sections/(section_key+'.json')
                    job.update(progress=5+80*index/len(chunks),message=f'Section {index+1} of {len(chunks)}: '+('using saved transcript' if cached.exists() else 'transcribing locally'))
                    if cached.exists():
                        document=json.loads(cached.read_text(encoding='utf-8'))
                    else:
                        audio=temp/'scan.wav'
                        run_ffmpeg(['-ss',start,'-i',directory/source['filename'],'-t',end-start,'-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le',audio])
                        document=ENGINE.transcribe(audio,selected_model,body.language,body.device)
                        pending=cached.with_suffix('.tmp')
                        pending.write_text(json.dumps(document,ensure_ascii=False),encoding='utf-8');pending.replace(cached)
                    languages.add(document.get('result',{}).get('language',body.language))
                    for word in extract_words(document,start):
                        center=(word['start']+word['end'])/2
                        if not any(a<=center<b for a,b in ranges):continue
                        if any(normal(w['text'])==normal(word['text']) and abs(w['start']-word['start'])<.4 for w in words[-30:]):continue
                        words.append(word)
            words.sort(key=lambda w:w['start'])
            cache_path.write_text(json.dumps({'key':cache_key,'words':words,'languages':sorted(languages)},ensure_ascii=False),encoding='utf-8')
            matches = find_matches(words,body.terms,source['duration'],body.margin)
            for match in matches:
                match['kind'] = 'word'
                match['category'] = 'Word-list match'
            signals = []
            if body.themes:
                for category, terms in THEMES.items():
                    for match in find_matches(words,terms,source['duration'],body.margin):
                        signals.append({**match,'kind':'theme','category':category})
            result = {'matches':matches,'words':words,'languages':sorted(languages),'ranges':ranges,
                      'themes':sorted(signals,key=lambda m:m['start']),
                      'terms':body.terms,'margin':body.margin,'model':selected_model.stem,
                      'notice':'Not a moderation verdict. Recognition can miss or invent lyrics; review the full audio.'}
            (directory / 'cleanup-analysis.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
            return result
        return new_job(work,kind='scan',payload={'sid':sid,'body':body.model_dump()})

    RUNNERS['scan']=lambda payload:scan(payload['sid'],ScanRequest(**payload['body']))

    @app.post('/api/sources/{sid}/cleanup/preview')
    def cleaned_preview(sid: str, body: CleanupRequest):
        source,directory=get_source(sid),session_path(sid)
        from advanced import stems_for
        if body.vocal_only and not all(p.exists() for p in stems_for(source,directory)):
            raise HTTPException(400,'Separate vocals first.')
        if any(e.end > source['duration']+.05 for e in body.edits):
            raise HTTPException(400,'Keep all edits within the source duration.')
        key=hashlib.sha256(body.model_dump_json().encode()).hexdigest()[:24]
        path=directory / ('cleanup-'+key+'.mp3')
        def work(job):
            job.update(progress=15,message='Rendering your cleaned preview locally…')
            if not path.exists():
                script=directory / ('cleanup-'+key+'.filter')
                try:
                    effect=redaction_filter(body.edits,0,source['duration'],body.mode)
                    if body.vocal_only:
                        vocals,instrumental=stems_for(source,directory)
                        script.write_text(f'[0:a]{effect}[v];[v][1:a]amix=inputs=2:normalize=0[cleaned]',encoding='utf-8')
                        inputs=['-i',vocals,'-i',instrumental];mapping='[cleaned]';option='-/filter_complex'
                    else:
                        script.write_text(effect,encoding='utf-8');inputs=['-i',directory/source['filename']];mapping='0:a:0';option='-/af'
                    run_ffmpeg([*inputs,'-map',mapping,'-vn',option,script,
                                '-c:a','libmp3lame','-b:a','192k',path],timeout=1800)
                finally:
                    script.unlink(missing_ok=True)
            return {'url':f'/api/sources/{sid}/cleanup/audio/{key}','edit_count':len(body.edits),'mode':body.mode}
        return new_job(work)

    @app.get('/api/sources/{sid}/cleanup/audio/{key}')
    def preview_audio(sid:str,key:str):
        if not re.fullmatch(r'[a-f0-9]{24}',key):
            raise HTTPException(404,'Preview not found.')
        path=session_path(sid)/('cleanup-'+key+'.mp3')
        if not path.exists():
            raise HTTPException(404,'Generate a cleaned preview first.')
        return FileResponse(path,media_type='audio/mpeg')
