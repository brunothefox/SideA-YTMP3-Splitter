"""Allowlisted source archive; user audio, keys, models and caches are never included."""
import hashlib
import json
import shutil
import zipfile
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from runtime import VERSION
OUT=ROOT/'releases';OUT.mkdir(exist_ok=True)
FILES=['app.py','runtime.py','jobs.py','launcher.py','content_cleanup.py','speech_engine.py','setup_components.py','project_io.py','advanced.py','youtube_import.py','playlist_exports.py',
       'requirements.txt','start.bat','start.ps1','start.sh','setup-cleanup.ps1','README.md','LICENSE','THIRD_PARTY.md','SideA.spec','PRODUCT.md','DESIGN.md','CONTRIBUTING.md','CHANGELOG.md','.gitignore']
FOLDERS=['static','resources','scripts','tests','benchmarks','.github']
def allowed():
    paths=[ROOT/name for name in FILES if (ROOT/name).is_file()]
    for folder in FOLDERS:
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.zip','.wav','.mp3','.bin','.exe','.dll'}:paths.append(p)
    return sorted(set(paths))
def package():
    source=OUT/f'SideA-{VERSION}-source.zip'
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in allowed():archive.write(path,'SideA/'+path.relative_to(ROOT).as_posix())
    outputs=[source]
    built=ROOT/'dist/SideA'
    if built.is_dir():
        portable=OUT/f'SideA-{VERSION}-windows-x64.zip'
        with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED) as archive:
            for path in built.rglob('*'):
                if path.is_file() and 'workspace' not in path.relative_to(built).parts:archive.write(path,'SideA/'+path.relative_to(built).as_posix())
            for name in ['README.md','LICENSE','THIRD_PARTY.md','CHANGELOG.md']:
                if (ROOT/name).exists():archive.write(ROOT/name,'SideA/'+name)
        outputs.append(portable)
    checksums=[]
    for path in outputs:
        digest=hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
        checksums.append(digest.hexdigest()+'  '+path.name)
        print(str(path),path.stat().st_size)
    (OUT/'SHA256SUMS.txt').write_text('\n'.join(checksums)+'\n',encoding='utf-8')
    manifest=[p.relative_to(ROOT).as_posix() for p in allowed()]
    (OUT/'source-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
if __name__=='__main__':package()
