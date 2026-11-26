# Side A

**Download:** [Windows portable ZIP and source ZIP](https://github.com/brunothefox/SideA-YTMP3-Splitter/releases/latest) · [Repository](https://github.com/brunothefox/SideA-YTMP3-Splitter)

## Download and launch

Windows: download the latest `SideA-…-windows-x64.zip`, extract the entire folder, then double-click `SideA.exe`. Keep the terminal open while using the app; Ctrl+C stops it. Python, FFmpeg, the CPU speech worker, and Node.js are bundled. No administrator installation is required. The app opens localhost automatically and picks another local port if 8000 is occupied. Releases are unsigned.

Open **Setup & jobs** to download speech models (148 MB or 488 MB). An optional NVIDIA engine enables GPU processing; **Create compact accuracy model** generates a quantized version. These downloads are separate so the public package stays smaller. Audio is processed locally. Downloads need internet; YouTube imports also contact YouTube.

User audio, settings and job history live in the portable folder's `workspace` directory. Move that directory with the app to preserve projects, or use per-project backups. The source ZIP/repository never contains imported audio, local transcripts, credentials, model weights, or generated exports.

Linux/macOS: download the source ZIP, install Python 3.11+ and Node.js, and run `bash start.sh`. Linux x64 can install the speech worker in Setup; macOS needs a compatible `whisper-cpp` installation on PATH (for example through Homebrew). The prebuilt desktop ZIP is Windows x64; other platforms run from source.

## Release features

- Warm, serialized local speech worker; optional NVIDIA acceleration; compact models and per-minute transcript caching. Retry interrupted scans to reuse completed sections.
- Job history and pause/resume/cancel/retry. Pause and cancellation take effect at processing checkpoints; an active speech request may finish its current section first.
- Zoomed waveform editor with draggable censor boundaries, original/cleaned listening, and passage looping.
- Private project ZIP backups/restores, saved cleanup decisions, disk usage and individual project deletion.
- Optional Demucs vocal separation and vocal-only cleanup, preserving the instrumental as far as separation quality allows. This add-on needs Python 3.11 and its separate dependencies; full-signal muting remains available.
- Optional contextual transcript review through **local Ollama**, alongside basic phrase flags. Install/start Ollama and a model separately; choose it in the cleanup panel. Suggestions remain unselected for human review. Nothing is sent to a hosted AI API.
- Setup/diagnostics, user-triggered update checks, and evaluation tools under `benchmarks/` for measuring misses, false alarms, and transcription errors on permissioned test recordings.

The interface is intentionally kept close to the existing design for a separate UI refinement. See [CONTRIBUTING.md](CONTRIBUTING.md) for the DOM/API handoff map.

A local audio splitter and batch exporter for files, mixes, and YouTube playlists.

## Run on Windows

For the source version, install Python 3.11 or newer and Node.js (Node is used for YouTube extraction). Double-click `start.bat`, or run `./start.ps1`. First run installs the Python dependencies, including a bundled FFmpeg. The launcher opens localhost; press Ctrl+C in the terminal to stop.

Manual setup:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe app.py
```

## Split a mix

Upload an audio file (up to 2 GB), or paste a YouTube link. Standard videos, Shorts, youtu.be shares, embeds, YouTube Music, and completed livestream recordings import individually. Playlists and channel uploads open a selectable list. Side A reads title/artist tags, embedded chapters, YouTube chapters, and description timestamps. It does not recognize songs by listening. Without chapters, paste a timestamped tracklist or add cuts yourself.

### YouTube playlists, Shorts, and channels

Paste the link into **YouTube video or playlist**, then click **Read YouTube link**. For a collection, select the videos and choose **Import selected videos**. Each video gets a separate project with chapters when available. Progress and failures are shown per video; failed videos do not discard successful imports. Use **Retry unfinished imports** or retry a cancelled job to retain completed sources. The most recent batch can be recovered after refreshing the browser.

Playlist options let you choose a starting position and list up to 200 videos per batch (50 by default). **Next videos** reads the next range. A watch URL containing both a video and a playlist opens the playlist by default; uncheck **Open the playlist** to import only that video. Collection imports run sequentially and support job pause/cancel/retry controls.

Private, deleted, region-restricted, age-gated, DRM-protected, bot-blocked, or sign-in-required content may be unavailable. Ongoing/upcoming livestreams are not imported; completed recordings can be. No account cookies are read, and link support is not a promise that every YouTube item can be downloaded.

Preview each track; edit start times and names. Export MP3 at 320 kbps, FLAC, 24-bit WAV, or copy the original codec without re-encoding. Download individual tracks or a ZIP. Original-codec cuts have audio-frame precision; MP3/FLAC/WAV use accurate seeking. Lossless output cannot improve a compressed source.

YouTube imports download the best available audio. Restricted, age-gated, private, live, or bot-blocked videos may fail. No account cookies are accessed. Update yt-dlp if extraction breaks: `./.venv/Scripts/python.exe -m pip install -U "yt-dlp[default]"`. The extractor may fetch its official JavaScript challenge component from GitHub when required.

## Playlist and local batch exports

1. Paste a playlist link, click **Read YouTube link**, choose videos, and click **Import selected videos**. Or select/drop multiple local files (up to 200 files, 2 GB each).
2. Preview any imported source in the list. Use **Edit cuts** for custom boundaries or cleanup, then **Back to playlist & batch export**.
3. Select the sources to export. Choose **One audio file per video**, **Saved cuts from each video**, or **Split every fixed duration**. Saved-cut mode respects deselected tracks; equal-duration mode creates new cuts and can end with a shorter final part.
4. Choose MP3 (320 kbps), high-quality Vorbis OGG, FLAC, WAV (24-bit PCM), or original codec. Select one folder per source or a flat audio folder. Numbered names prevent collisions when titles repeat.
5. Optional finishing includes clean filenames, descriptive metadata removal, padding, edge fades, and linked pitch/speed changes. Original-codec export cannot apply audio filters. FLAC/WAV do not restore quality lost in the original source.
6. Click **Export playlist ZIP**. Pause, resume, or cancel as needed. **Retry unfinished exports** reuses successful files when settings are unchanged. Changing the settings starts a new export.
7. Download the ZIP, preview/download individual outputs, or **Organize & open folder**. The ZIP contains audio, CSV/JSON file lists, and cleanup reports when applicable. No NekoDJ config, asset-ID mapping, or Lua templates are generated.

The batch queue and completed export download can be restored after refreshing the browser. If the app closes mid-export, retry the unfinished queue; completed sources are retained. Local file-import retries need the original files still selected in the same session; after restarting, reselect failed local files. Imported projects remain on disk.

## Single-source editing and audio effects

A single file or video opens in the waveform editor. Add cuts at the playhead, paste timestamps, or use **Split this audio by duration**. Search, select/deselect, rename, and undo/redo cuts before exporting.

Use **Prepare for → Pitch & speed effects** for linked pitch/tempo shifts. Automatic fitting under seven minutes is optional. Padding, fades, metadata removal, and clean filenames also work without shifting. Exported ZIPs contain audio and any requested cleanup report.

## Explicit-language cleanup and theme review

The splitter includes **Explicit language & theme review**. This is an offline audio-editing aid, not a Roblox moderation predictor. It does not remove copyright or guarantee approval. Roblox's current standards are linked inside the tool: https://about.roblox.com/community-standards

1. Choose the selected tracks or the whole source. Choose a language or automatic detection.
2. Select starter dictionaries or the extended English dictionary (835 entries), and add custom words/phrases. Matching uses whole words, Unicode normalization, and rejoined transcription tokens; it does not match `ass` inside `assistant`.
3. Scan. Word matches and theme phrase signals include context, confidence, and editable timestamps. Theme flags start deselected. Themes use curated phrases covering sexual content, threats/violence, drugs, self-harm, harassment, and personal information. They are limited phrase signals, not semantic classification or exhaustive policy coverage. Non-English theme coverage is limited; supply your own phrases.
4. Listen, adjust timing, and add manual marks for missed words. Transcription can mishear sung lyrics, homophones, background vocals, and mixed languages. No-match results are not a clean bill of health.
5. Choose silence or bleep and generate an original/cleaned preview. Both options remove the marked original signal. Bleep replaces it with a 1 kHz tone; short edge ramps reduce clicks. The entire audio in a marked span is affected, including instruments; optional vocal-only separation is available through Setup.
6. Review the marks and click **Apply cleanup to export**. Edits are applied before speed shifts and padding, so source timestamps remain aligned. The ZIP includes `content-cleanup-report.json`. Changing a mark disables application until reviewed again.

**Remove embedded metadata** is on by default in the UI, under Padding & finishing. It strips descriptive tags and attachments from the audio, including title, artist, album, comments, and track number. Filenames, ZIP file-list/report names, and unavoidable technical/container information remain. Duration, bitrate, sample rate, and channel count are properties of the audio and cannot be hidden by tag removal.

Whisper runs locally through whisper.cpp. Installed models live under `tools/models`, and transcript caches and preview files stay beside each source in `data/`. Balanced mode uses multilingual Whisper base (148 MB). Higher-accuracy mode uses multilingual Whisper small (488 MB); it can still make mistakes and runs more slowly. One-minute overlapping sections keep long-source processing bounded, and transcripts are cached for fast word-list rechecks. Only software/model downloads need internet access; audio is not sent to a transcription service.

On a new checkout, run `./setup-cleanup.ps1` for balanced scanning, or `./setup-cleanup.ps1 -HighAccuracy` for both models. The installer verifies published SHA-256 hashes. Whisper.cpp source/license: https://github.com/ggml-org/whisper.cpp . Extended dictionary: https://github.com/snguyenthanh/better_profanity (MIT; notice at `resources/wordlist-LICENSE.txt`). These dictionaries are not Roblox's own filter data.

`tests/test_cleanup.py` checks token/phrase matching, real synthetic-speech recognition when the fixture is present, signal replacement, metadata stripping, and edit alignment after shift/padding. `tests/cleanup_browser_check.py` exercises scan → review → preview → apply → ZIP on desktop and mobile.

## Privacy and storage details

The server binds only to `127.0.0.1`. Splitter imports and exports stay under `data/` on your disk. YouTube contacts YouTube and its delivery services. All audio conversion runs on the local server. No telemetry, external fonts, API keys, or cloud storage. Files persist across restarts; stop the app and delete `data/` to clear them. Your last source is remembered in this browser. Avoid multiple instances sharing the same port.

## Development

```powershell
./.venv/Scripts/python.exe -m pip install pytest httpx playwright
./.venv/Scripts/python.exe -m pytest -q
```

Browser checks use installed Chrome. Run `python tests/youtube_browser_check.py` for an isolated synthetic playlist/local-file flow: unavailable items, retries, playback, editor return, whole/cut/interval exports, refresh recovery, and desktop/mobile layouts. `python -m pytest -q` checks actual decoded audio, padding, cleanup, metadata, cancellation, retries, and archive layouts. No copyrighted test recordings are included.
