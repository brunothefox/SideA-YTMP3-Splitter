# Build with: python -m PyInstaller --noconfirm SideA.spec
from pathlib import Path
import shutil
from PyInstaller.utils.hooks import collect_all
root=Path(SPECPATH)
datas=[(str(root/'static'),'static'),(str(root/'resources'),'resources')]
binaries=[];hiddenimports=['uvicorn.logging','uvicorn.loops.asyncio','uvicorn.protocols.http.h11_impl','uvicorn.protocols.websockets.websockets_impl','uvicorn.lifespan.on']
node=shutil.which('node')
if node:
    datas.append((node,'tools/node'))
    node_license=Path(node).parent/'LICENSE'
    if node_license.exists():datas.append((str(node_license),'tools/node'))
for package in ['yt_dlp','yt_dlp_ejs','imageio_ffmpeg']:
    data,binary,hidden=collect_all(package);datas+=data;binaries+=binary;hiddenimports+=hidden
engine=root/'tools/whisper/Release'
if engine.exists():
    for file in engine.iterdir():
        if file.suffix=='.dll' or file.name in {'whisper-cli.exe','whisper-server.exe','whisper-quantize.exe'}:
            datas.append((str(file),'tools/whisper/Release'))
a=Analysis([str(root/'launcher.py')],pathex=[str(root)],binaries=binaries,datas=datas,hiddenimports=hiddenimports,
    hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['pytest','playwright','tkinter','matplotlib','numpy','pandas'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='SideA',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='SideA')
