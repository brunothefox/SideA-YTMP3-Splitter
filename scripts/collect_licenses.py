import importlib.metadata
import subprocess
from pathlib import Path
import imageio_ffmpeg
ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'dist/SideA/licenses';TARGET.mkdir(parents=True,exist_ok=True)
result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-L'],capture_output=True)
(TARGET.parent/'FFMPEG-LICENSE.txt').write_bytes(result.stdout+result.stderr)
for package in importlib.metadata.distributions():
    name=package.metadata.get('Name','dependency')
    for item in package.files or []:
        if any(part.lower() in {'license','licenses','copying','notice','license.txt','license.md','copying.txt'} for part in item.parts):
            source=Path(package.locate_file(item))
            if source.is_file():
                target=TARGET/(name+'-'+source.name)
                if not target.exists():target.write_bytes(source.read_bytes())
print('Collected dependency notices.')
