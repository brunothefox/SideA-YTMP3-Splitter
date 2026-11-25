"""Resource paths are read-only; user workspace paths stay outside bundled files."""
import os
import sys
from pathlib import Path

ASSETS = Path(__file__).resolve().parent
HOME = Path(os.environ.get('SIDEA_HOME') or (Path(sys.executable).parent / 'workspace' if getattr(sys,'frozen',False) else ASSETS)).resolve()
HOME.mkdir(parents=True,exist_ok=True)
node_directory=ASSETS/'tools/node'
if node_directory.exists():os.environ['PATH']=str(node_directory)+os.pathsep+os.environ.get('PATH','')
VERSION = '1.0.0'


def tool(name):
    suffix='.exe' if os.name=='nt' else ''
    candidates=[HOME/'tools/whisper/Release'/(name+suffix), HOME/'tools/whisper'/(name+suffix),
                ASSETS/'tools/whisper/Release'/(name+suffix),ASSETS/'tools/whisper'/(name+suffix)]
    import shutil
    return next((p for p in candidates if p.is_file()),Path(shutil.which(name) or candidates[0]))
