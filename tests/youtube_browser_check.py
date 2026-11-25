"""Isolated browser test of collection UI with local, synthetic downloader fixtures."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import run_ffmpeg

OUTPUT=ROOT/'test-results';OUTPUT.mkdir(exist_ok=True)
with socket.socket() as probe:
    probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
tone=OUTPUT/'youtube-test-tone.wav'
run_ffmpeg(['-f','lavfi','-i','sine=frequency=440:duration=4','-ar','48000','-ac','2',tone])
worker=r'''
import json,os
from pathlib import Path
import uvicorn
import youtube_import
from app import app
A='A2345678901';B='B2345678902';C='C2345678903'
class Fake:
    failures=0
    def __init__(self,options):self.options=options
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def prepare_filename(self,info):return self.options['outtmpl'].replace('%(ext)s','wav')
    def extract_info(self,url,download=True):
        if not download:return {'title':'Playlist <local> & test','playlist_count':100,'entries':[
            {'id':A,'title':'First song','duration':4},None,{'id':B,'title':'Temporary failure','duration':4},{'id':C,'title':'Last song','duration':4}]}
        assert self.options['noplaylist'] is True
        vid=url.split('v=')[1]
        if vid==B and Fake.failures==0:
            Fake.failures+=1
            raise ValueError('Synthetic unavailable video; retry succeeds')
        info={'id':vid,'title':'Imported '+vid,'uploader':'Local fixture','chapters':[{'start_time':0,'title':'Part A'},{'start_time':2,'title':'Part B'}]}
        Path(self.prepare_filename(info)).write_bytes(Path(os.environ['TEST_TONE']).read_bytes())
        return info
youtube_import.yt_dlp.YoutubeDL=Fake
uvicorn.run(app,host='127.0.0.1',port=int(os.environ['TEST_PORT']),log_level='error')
'''
with tempfile.TemporaryDirectory(prefix='youtube-ui-',dir=OUTPUT) as workspace:
    env=os.environ.copy();env['SIDEA_HOME']=workspace;env['TEST_TONE']=str(tone)
    env['TEST_PORT']=str(port)
    server=subprocess.Popen([sys.executable,'-B','-c',worker],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1):break
            except Exception:time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{port}')
            page.on('response',lambda response:print('HTTP',response.status,response.url) if response.status>=400 else None)
            page.locator('#youtube-url').fill('https://www.youtube.com/playlist?list=PL_test_collection_12345')
            page.locator('#youtube-form>button').click()
            page.locator('#youtube-import-selected').wait_for(state='visible',timeout=30000)
            assert page.locator('.youtube-video').count()==4
            assert page.locator('[data-youtube-index]:disabled').count()==1
            assert page.locator('#youtube-selection-count').inner_text()=='3 selected'
            page.locator('#youtube-import-selected').click()
            page.wait_for_function('youtubeState.batch?.imported === 2 && youtubeState.batch.failed === 1 && !state.importing',timeout=60000)
            assert page.locator('[data-youtube-source]').count()==2
            page.locator('#youtube-retry-failed').click()
            print('Retry requested')
            page.wait_for_function('youtubeState.batch?.imported === 3 && youtubeState.batch.failed === 0 && !state.importing',timeout=60000)
            assert len(list((Path(workspace)/'data').glob('*/source.json')))==3
            page.locator('[data-youtube-source]').last.click()
            page.wait_for_function('state.source.title === "Imported C2345678903"')
            page.locator('#change-source').click()
            page.locator('#youtube-url').fill('https://youtube.com/shorts/A2345678901?feature=share')
            page.locator('#youtube-form>button').click()
            page.wait_for_function('state.source.title === "Imported A2345678901" && !state.importing',timeout=60000)
            assert len(list((Path(workspace)/'data').glob('*/source.json')))==4
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(OUTPUT/'youtube-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            page.screenshot(path=str(OUTPUT/'youtube-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            assert not errors,errors
            browser.close()
            print('YouTube browser checks passed: playlist selection, unavailable item, partial failure, retry without duplicate projects, source opening, Shorts, mobile layout.')
    finally:
        server.terminate()
        try:server.wait(timeout=10)
        except subprocess.TimeoutExpired:server.kill();server.wait()
