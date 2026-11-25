"""Functional checks for the studio workflow. Requires the running local site."""
import json
import sys
import zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import inspect_audio, run_ffmpeg
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results'
OUTPUT.mkdir(exist_ok=True)
fixture = OUTPUT / 'studio-tone.wav'
run_ffmpeg(['-f','lavfi','-i','sine=frequency=330:duration=10','-ar','48000','-ac','2',fixture])

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome',headless=True)
    page = browser.new_page(viewport={'width':1600,'height':1100},accept_downloads=True)
    errors=[]
    page.on('pageerror',lambda e: errors.append(str(e)))
    page.goto('http://127.0.0.1:8000')
    page.locator('#split-file').set_input_files(str(fixture))
    page.locator('#workspace').wait_for(state='visible',timeout=120000)
    page.locator('#toggle-paste').click()
    page.locator('#timestamp-text').fill('00:00 First Song [Official Video] 🎵\n00:05 Second Song [Lyrics]')
    page.locator('#apply-timestamps').click()
    page.wait_for_function('document.querySelectorAll(".track-row").length === 2')
    page.locator('#clean-track-names').click()
    assert page.locator('.title-input').nth(0).input_value()=='First Song'
    page.locator('#undo-edit').click()
    assert '[Official Video]' in page.locator('.title-input').nth(0).input_value()
    page.locator('#redo-edit').click()
    assert page.locator('.title-input').nth(0).input_value()=='First Song'
    page.locator('#track-search').fill('second')
    assert page.locator('.track-row:visible').count()==1
    page.locator('#track-search').fill('')
    page.locator('#export-target').select_option('neko')
    page.locator('#auto-shift').select_option('bright')
    page.locator('.finishing-options summary').click()
    page.locator('#padding-start').fill('0.5')
    page.locator('#padding-end').fill('0.75')
    page.locator('#padding-end').press('Tab')
    page.locator('#export-fade').select_option('0.02')
    assert '0.793701' in page.locator('.track-prediction').first.inner_text()
    page.locator('#preview-rate').select_option('shift')
    assert abs(page.evaluate('audio.playbackRate') - 2**(4/12)) < .00001
    page.locator('#notice button').click()
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(OUTPUT / 'studio-editor-desktop.png'),full_page=True)
    page.locator('#export-button').click()
    page.locator('#downloads').wait_for(state='visible',timeout=120000)
    with page.expect_download() as event:
        page.locator('#zip-download').click()
    bundle=OUTPUT/'studio-nekodj.zip'
    event.value.save_as(str(bundle))
    with zipfile.ZipFile(bundle) as z:
        assert len(z.namelist())==5
        config=json.loads(z.read('nekodj-track-values.json'))
        assert all(c['effectSpeed']==.793701 for c in config)
        assert all(abs(c['durationSeconds']-(5/2**(4/12)+1.25)) < .002 for c in config)
    # Draft survives a full page reload.
    page.wait_for_function('document.querySelector("#draft-status").textContent.includes("All edits saved")')
    page.reload()
    page.locator('#workspace').wait_for(state='visible',timeout=30000)
    assert page.locator('.track-row').count()==2
    assert page.locator('.title-input').first.input_value()=='First Song'
    assert page.locator('#export-target').input_value()=='neko'
    assert page.locator('#padding-start').input_value()=='0.5'
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(OUTPUT/'studio-editor-mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('[data-view=neko]').click()
    page.locator('#neko-files').set_input_files(str(fixture))
    page.locator('.shift-slider').wait_for(timeout=30000)
    page.locator('#batch-shift').fill('12')
    page.locator('#browser-pad-start').fill('0.5')
    page.locator('#browser-pad-end').fill('0.75')
    page.locator('#batch-format').select_option('wav')
    page.locator('#batch-apply').click()
    page.locator('#batch-convert').click()
    page.wait_for_function('document.querySelector("#batch-status").textContent.startsWith("1 of 1 tracks converted")',timeout=120000)
    with page.expect_download() as event:
        page.locator('.neko-result .primary').click()
    output=OUTPUT/'studio-browser-padded.wav'
    event.value.save_as(str(output))
    assert abs(inspect_audio(output)['duration']-6.25)<.05
    assert not errors,errors
    browser.close()
    print('Studio checks passed: undo/redo, search, titles, shift preview, padding, config ZIP, draft recovery, mobile, browser padding.')
