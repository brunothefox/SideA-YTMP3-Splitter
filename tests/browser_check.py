"""Run with the local server active; Chrome is used without installing a browser."""
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import run_ffmpeg, inspect_audio
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'test-results'
OUTPUT.mkdir(exist_ok=True)
tone = OUTPUT / 'browser-tone.wav'
run_ffmpeg(['-f', 'lavfi', '-i', 'sine=frequency=440:duration=8', '-ar', '48000', '-ac', '2', tone])

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1050}, accept_downloads=True)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8000')
    page.screenshot(path=str(OUTPUT / 'splitter-desktop.png'), full_page=True)
    page.locator('#split-file').set_input_files(str(tone))
    page.locator('#workspace').wait_for(state='visible', timeout=120000)
    page.locator('#toggle-paste').click()
    page.locator('#timestamp-text').fill('00:00 First song\n00:04 Second song')
    page.locator('#apply-timestamps').click()
    page.locator('.track-row').nth(1).wait_for()
    page.locator('#export-button').click()
    page.locator('#downloads').wait_for(state='visible', timeout=120000)
    assert page.locator('.download-row').count() == 2
    with page.expect_download() as info:
        page.locator('#zip-download').click()
    info.value.save_as(str(OUTPUT / 'browser-tracks.zip'))
    page.screenshot(path=str(OUTPUT / 'splitter-workspace.png'), full_page=True)
    page.locator('[data-view=neko]').click()
    requests = []
    page.on('request', lambda r: requests.append((r.method, r.url)))
    page.locator('#neko-files').set_input_files(str(tone))
    page.locator('.neko-card .shift-slider').wait_for(timeout=30000)
    page.locator('.shift-slider').fill('4')
    assert page.locator('.effect-value').inner_text() == '0.794'
    page.locator('.neko-play').click()
    page.wait_for_timeout(300)
    page.locator('.neko-play').click()
    for format in ['mp3', 'wav', 'ogg']:
        page.locator(f'.format-selector [data-format={format}]').click()
        page.locator('.neko-convert').click()
        page.locator('.neko-result').wait_for(state='visible', timeout=120000)
        with page.expect_download() as info:
            page.locator('.neko-result .primary').click()
        output = OUTPUT / ('browser-converted.' + format)
        info.value.save_as(str(output))
        metadata = inspect_audio(output)
        print(format, json.dumps(metadata))
        assert abs(metadata['duration'] - 8 / (2 ** (4 / 12))) < .15
        run_ffmpeg(['-i', output, '-f', 'null', '-'])
    page.locator('#neko-files').set_input_files(str(tone))
    page.wait_for_function('document.querySelectorAll(".neko-card").length === 2 && document.querySelectorAll(".shift-slider").length === 2')
    page.locator('#batch-shift').fill('7')
    page.locator('#batch-volume').fill('80')
    page.locator('#batch-apply').click()
    assert page.locator('.effect-value').all_inner_texts() == ['0.667', '0.667']
    page.locator('#batch-convert').click()
    page.wait_for_function('document.querySelector("#batch-status").textContent.startsWith("2 of 2 tracks converted")', timeout=120000)
    with page.expect_download() as info:
        page.locator('#batch-zip').click()
    batch_zip = OUTPUT / 'nekodj-batch.zip'
    info.value.save_as(str(batch_zip))
    with zipfile.ZipFile(batch_zip) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == 4
        config = json.loads(archive.read('nekodj-track-values.json'))
        assert len(config) == 2
        assert all(abs(t['effectSpeed'] - 1 / (2 ** (7 / 12))) < .000001 for t in config)
        assert all(t['file'] in archive.namelist() for t in config)
        assert b'assetId = 0' in archive.read('nekodj-config-template.lua')
    assert not [r for r in requests if r[0] == 'POST'], requests
    # Linked compensation follows each track's actual speed, including auto-fit.
    page.evaluate('nekoTracks[1].buffer = {duration: 600}')
    page.locator('#batch-shift').fill('0')
    page.locator('#batch-apply').click()
    values = page.evaluate('nekoTracks.map(t => ({shift:t.shift, duration:t.buffer.duration/getShift(t), effect:getEffect(t)}))')
    assert values[0]['shift'] == 0 and values[0]['effect'] == 1
    assert values[1]['shift'] > 0 and values[1]['duration'] < 420
    page.evaluate('nekoTracks[1].buffer = nekoTracks[0].buffer')
    page.locator('#batch-effect').select_option('manual')
    page.locator('#batch-manual').fill('0.75')
    page.locator('#batch-apply').click()
    assert page.locator('.manual-effect').evaluate_all('(nodes) => nodes.every(n => +n.value === .75)')
    page.locator('#batch-effect').select_option('linked')
    page.locator('#batch-shift').fill('4')
    page.locator('#batch-apply').click()
    page.locator('.neko-selected').nth(1).uncheck()
    page.locator('#batch-shift').fill('5')
    page.locator('#batch-apply').click()
    assert page.evaluate('nekoTracks[0].shift === 5 && nekoTracks[1].shift === 4')
    page.screenshot(path=str(OUTPUT / 'nekodj-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(OUTPUT / 'nekodj-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.locator('[data-view=split]').click()
    page.locator('#prep-selected').click()
    page.wait_for_function('document.querySelectorAll(".neko-card").length === 4', timeout=120000)
    assert page.locator('#neko-view').is_visible()
    page.locator('[data-view=split]').click()
    page.screenshot(path=str(OUTPUT / 'splitter-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    assert not errors, errors
    browser.close()
    print('Browser checks passed: import, tracklist, ZIP, previews, three codecs, browser privacy, mobile layout.')
