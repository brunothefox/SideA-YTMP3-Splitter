"""End-to-end offline cleanup with synthetic speech; cleans its imported source."""
import json
import sys
import shutil
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import ROOT, DATA
from playwright.sync_api import sync_playwright

OUTPUT=ROOT/'test-results'
speech=OUTPUT/'speech.wav'
sid=None
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:8000')
        page.locator('#split-file').set_input_files(str(speech))
        page.locator('#workspace').wait_for(state='visible',timeout=120000)
        sid=page.evaluate('state.source.id')
        page.locator('#cleanup-engine-status').filter(has_text='Offline engine ready').wait_for(timeout=10000)
        page.locator('#cleanup-quality').select_option('accurate' if page.locator('#cleanup-quality option[value=accurate]').is_enabled() else 'balanced')
        page.locator('#cleanup-language').select_option('en')
        for box in page.locator('#cleanup-packs input').all():box.uncheck()
        page.locator('#cleanup-custom').fill('door')
        page.locator('#cleanup-scan').click()
        page.wait_for_function('cleanup.matches.length === 2 && !cleanup.busy',timeout=120000)
        assert page.locator('.cleanup-match').count()==2
        page.locator('.cleanup-listen').first.click()
        page.wait_for_timeout(250)
        page.evaluate('audio.pause()')
        page.locator('#cleanup-mode').select_option('bleep')
        page.locator('#cleanup-preview').click()
        page.locator('.cleanup-ab').wait_for(state='visible',timeout=120000)
        assert page.locator('#cleanup-cleaned').get_attribute('src').startswith('/api/sources/')
        page.locator('#cleanup-reviewed').check()
        page.locator('#cleanup-apply').click()
        assert page.evaluate('exportOptions().redactions.length')==2
        assert page.evaluate('exportOptions().strip_metadata')
        page.locator('#export-button').click()
        page.locator('#downloads').wait_for(state='visible',timeout=120000)
        with page.expect_download() as event:page.locator('#zip-download').click()
        bundle=OUTPUT/'cleanup-test.zip';event.value.save_as(str(bundle))
        with zipfile.ZipFile(bundle) as z:
            report=json.loads(z.read('content-cleanup-report.json'))
            assert len(report['edits'])==2 and report['mode']=='bleep'
        page.locator('#cleanup-panel').scroll_into_view_if_needed()
        page.screenshot(path=str(OUTPUT/'cleanup-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        page.screenshot(path=str(OUTPUT/'cleanup-mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.locator('.cleanup-match input[type=checkbox]').first.uncheck()
        assert not page.evaluate('cleanup.applied')
        assert not page.evaluate('exportOptions().redactions.length')
        assert not errors,errors
        browser.close()
        print('Cleanup browser checks passed: real transcription, review, preview, apply, bleep export, report, metadata option, edit invalidation, mobile.')
finally:
    if sid and (DATA/sid).resolve().is_relative_to(DATA.resolve()):shutil.rmtree(DATA/sid,ignore_errors=True)
