"""Portable app browser smoke; defaults to its clean-workspace test port."""
import os
import sys
import json
import zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
base=os.environ.get('SIDEA_TEST_URL','http://127.0.0.1:8098')
speech=ROOT/'test-results/speech.wav'
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base)
    page.locator('[data-view=manage]').click()
    page.locator('#diagnostics-output').filter(has_text='version').wait_for(timeout=30000)
    assert page.locator('[data-install=base]').count()==1
    page.locator('[data-view=split]').click()
    page.locator('#split-file').set_input_files(str(speech))
    page.locator('#workspace').wait_for(state='visible',timeout=120000)
    page.locator('#cleanup-quality').select_option('balanced')
    page.locator('#cleanup-device').select_option('cpu')
    page.locator('#cleanup-language').select_option('en')
    for box in page.locator('#cleanup-packs input').all():box.uncheck()
    page.locator('#cleanup-custom').fill('door')
    page.locator('#cleanup-scan').click()
    page.wait_for_function('cleanup.matches.length === 2 && !cleanup.busy',timeout=120000)
    page.wait_for_function('detailState.peaks.length > 0')
    assert page.locator('#detail-mark option').count()==2
    page.locator('#detail-zoom').select_option('2')
    page.locator('#detail-original').click()
    page.wait_for_timeout(200)
    page.evaluate('audio.pause()')
    page.locator('#cleanup-preview').click()
    page.locator('.cleanup-ab').wait_for(state='visible',timeout=120000)
    page.locator('#cleanup-reviewed').check()
    page.locator('#cleanup-apply').click()
    page.locator('#export-target').select_option('neko')
    page.locator('#auto-shift').select_option('auto')
    page.locator('#export-button').click()
    page.locator('#downloads').wait_for(state='visible',timeout=120000)
    page.locator('[data-asset-index]').first.fill('123456789')
    page.locator('#save-asset-map').click()
    page.wait_for_function('state.exports.config[0].assetId === 123456789')
    with page.expect_download() as event:page.locator('#zip-download').click()
    zipfile_path=ROOT/'test-results/portable-output.zip';event.value.save_as(str(zipfile_path))
    with zipfile.ZipFile(zipfile_path) as bundle:
        assert json.loads(bundle.read('nekodj-track-values.json'))[0]['assetId']==123456789
        assert 'content-cleanup-report.json' in bundle.namelist()
    with page.expect_download() as event:page.locator('#backup-project').click()
    backup=ROOT/'test-results/portable-project.sidea.zip';event.value.save_as(str(backup))
    page.locator('[data-view=manage]').click()
    page.locator('#restore-project').set_input_files(str(backup))
    page.wait_for_function('document.querySelector("#split-view").hidden === false',timeout=120000)
    page.locator('.cleanup-match').first.wait_for()
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(ROOT/'test-results/release-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
    print('Portable browser checks passed: setup, bundled engine, warm scan, detailed waveform, cleaned export, asset IDs, ZIP, backup/restore, mobile.')
