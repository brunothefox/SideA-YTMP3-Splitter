# Side A

**Download:** [Windows portable ZIP and source ZIP](https://github.com/brunothefox/SideA-YTMP3-Splitter/releases/latest) · [Repository](https://github.com/brunothefox/SideA-YTMP3-Splitter)

## Download and launch

Windows: download `SideA-1.0.0-windows-x64.zip`, extract the entire folder, then double-click `SideA.exe`. Keep the terminal open while using the app; Ctrl+C stops it. Python, FFmpeg, the CPU speech worker, and Node.js are bundled. No administrator installation is required. The app opens localhost automatically and picks another local port if 8000 is occupied. The first release is unsigned.

Open **Setup & jobs** to download speech models (148 MB or 488 MB). An optional NVIDIA engine enables GPU processing; **Create compact accuracy model** generates a quantized version. These downloads are separate so the public package stays smaller. Audio is processed locally. Downloads need internet; YouTube imports also contact YouTube. Browser-only NekoDJ conversion works without uploading audio to the local server.

User audio, settings and job history live in the portable folder's `workspace` directory. Move that directory with the app to preserve projects, or use per-project backups. The source ZIP/repository never contains imported audio, local transcripts, credentials, model weights, or generated exports.

Linux/macOS: download the source ZIP, install Python 3.11+ and Node.js, and run `bash start.sh`. Linux x64 can install the speech worker in Setup; macOS needs a compatible `whisper-cpp` installation on PATH (for example through Homebrew). The prebuilt desktop ZIP is Windows x64; other platforms run from source.

## Release features

- Warm, serialized local speech worker; optional NVIDIA acceleration; compact models and per-minute transcript caching. Retry interrupted scans to reuse completed sections.
- Job history and pause/resume/cancel/retry. Pause and cancellation take effect at processing checkpoints; an active speech request may finish its current section first.
- Zoomed waveform editor with draggable censor boundaries, original/cleaned listening, and passage looping.
- Private project ZIP backups/restores, saved cleanup decisions, disk usage and individual project deletion.
- Opt-in browser-session saving restores browser-only NekoDJ source files and settings through IndexedDB. Use Clear saved session to remove them; converted files can be regenerated.
- NekoDJ audio-ID mapping: enter IDs after uploading to Roblox, then regenerate the JSON/CSV/Lua config in your ZIP. The Lua file remains a template for your actual NekoDJ schema.
- Optional Demucs vocal separation and vocal-only cleanup, preserving the instrumental as far as separation quality allows. This add-on needs Python 3.11 and its separate dependencies; full-signal muting remains available.
- Optional contextual transcript review through **local Ollama**, alongside basic phrase flags. Install/start Ollama and a model separately; choose it in the cleanup panel. Suggestions remain unselected for human review. Nothing is sent to a hosted AI API.
- Setup/diagnostics, user-triggered update checks, and evaluation tools under `benchmarks/` for measuring misses, false alarms, and transcription errors on permissioned test recordings.

The interface is intentionally kept close to the existing design for a separate UI refinement. See [CONTRIBUTING.md](CONTRIBUTING.md) for the DOM/API handoff map.

A local audio splitter and browser-only NekoDJ preparation tool.

## Run on Windows

For the source version, install Python 3.11 or newer and Node.js (Node is used for YouTube extraction). Double-click `start.bat`, or run `./start.ps1`. First run installs the Python dependencies, including a bundled FFmpeg. The launcher opens localhost; press Ctrl+C in the terminal to stop.

Manual setup:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe app.py
```

## Split a mix

Upload an audio file (up to 2 GB) or enter a single YouTube video URL. Side A reads title/artist tags, embedded chapters, YouTube chapters, and description timestamps. It does not recognize songs by listening. Without chapters, paste a timestamped tracklist or add cuts yourself.

Preview each track; edit start times and names. Export MP3 at 320 kbps, FLAC, 24-bit WAV, or copy the original codec without re-encoding. Download individual tracks or a ZIP. Original-codec cuts have audio-frame precision; MP3/FLAC/WAV use accurate seeking. Lossless output cannot improve a compressed source.

YouTube imports download the best available audio. Restricted, age-gated, private, live, or bot-blocked videos may fail. No account cookies are accessed. Update yt-dlp if extraction breaks: `./.venv/Scripts/python.exe -m pip install -U "yt-dlp[default]"`. The extractor may fetch its official JavaScript challenge component from GitHub when required.

## Prepare for NekoDJ

For large YouTube mixes, use **Prepare for → NekoDJ + config** in the splitter's export panel. This processes tracks sequentially on your local server instead of decoding the entire mix into browser memory. **Auto** keeps short tracks at their source speed and increases linked pitch/tempo only enough to fit longer tracks (including padding) below 7:00. **Bright** starts at +4 semitones; **Custom** lets you choose the shift. Each output gets its own calculated effectSpeed.

Expand **Padding & finishing** to add up to 10 seconds of silence before and after each track, choose an edge fade, and clean titles. **Clean titles** in the tracklist previews the cleanup before export: it strips URLs, emoji/symbol clutter, leading numbering, and common release tags while preserving letters from other languages. Review/edit titles yourself; cleanup does not guarantee Roblox approval.

The ZIP includes audio plus a JSON table, CSV table, and Lua config template. **Organize & open folder** saves copies under `exports/<mix>/Audio` and `Config` and opens the folder on Windows. No Roblox account access or automatic uploads are involved.

The project rail lists imported mixes. Edits and export settings auto-save to local disk and browser storage; undo/redo, title search, select/deselect, tracklist text download, original/shifted preview, and per-file output players are built in. Keyboard shortcuts outside text fields: Space to play/pause, M to cut, Left/Right to seek 5 seconds, Ctrl+Z to undo, Ctrl+Shift+Z to redo.

The NekoDJ tab decodes and converts files entirely inside your browser, with no audio upload. Drop multiple songs or send the splitter's exported tracks into it. Each track has a waveform, preview, shift in semitones, volume, linked/manual compensation, and OGG/MP3/WAV export. Batch settings include padding, fades, title cleanup, and minimum-shift auto-fitting. **Save to folder** uses Chrome/Edge's folder picker and writes audio and config directly to your chosen directory. Browser format support varies; MP3 and WAV are the fallback for unsupported input formats. Per-file input limit: 250 MB, with a 512 MiB estimated decoded-audio budget. For larger lists, use direct NekoDJ export in the splitter.

Speed = `2 ** (semitones / 12)`. Linked `effectSpeed = 1 / speed`. For example, +4 st → 1.259921× → effectSpeed 0.793701, matching the supplied reference. Manual mode lets you override compensation. Copy the number into your own NekoDJ config; the downloaded config note is a field snippet, not a complete game config.

For a whole mix, use **Split & prep for NekoDJ** on the splitter's selected tracks. It transfers losslessly encoded FLAC cuts to the browser workspace. In NekoDJ, select the tracks, apply a shared shift, volume, format, and linked/manual compensation, then choose **Convert selected**. The optional fit setting raises each long track's shift individually. Download the batch ZIP for the audio files, a JSON table of matching effectSpeed values, and a Lua template with placeholder Roblox asset IDs. No Roblox uploads happen automatically.

Long tracks default to fit within 6:59. Output is checked against Roblox's duration and 20 MB limits. Exports are 48 kHz, up to stereo: MP3 192 kbps, OGG/Opus 192 kbps (requires WebCodecs in a modern browser), or WAV 16-bit PCM. WAV may exceed 20 MB; use MP3/OGG. This does not guarantee Roblox moderation acceptance.

Use audio you own or have permission to use. Speed and pitch changes do not remove copyright. Roblox requirements: https://create.roblox.com/docs/audio/assets

## Explicit-language cleanup and theme review

The splitter includes **Explicit language & theme review**. This is an offline audio-editing aid, not a Roblox moderation predictor. It does not remove copyright or guarantee approval. Roblox's current standards are linked inside the tool: https://about.roblox.com/community-standards

1. Choose the selected tracks or the whole source. Choose a language or automatic detection.
2. Select starter dictionaries or the extended English dictionary (835 entries), and add custom words/phrases. Matching uses whole words, Unicode normalization, and rejoined transcription tokens; it does not match `ass` inside `assistant`.
3. Scan. Word matches and theme phrase signals include context, confidence, and editable timestamps. Theme flags start deselected. Themes use curated phrases covering sexual content, threats/violence, drugs, self-harm, harassment, and personal information. They are limited phrase signals, not semantic classification or exhaustive policy coverage. Non-English theme coverage is limited; supply your own phrases.
4. Listen, adjust timing, and add manual marks for missed words. Transcription can mishear sung lyrics, homophones, background vocals, and mixed languages. No-match results are not a clean bill of health.
5. Choose silence or bleep and generate an original/cleaned preview. Both options remove the marked original signal. Bleep replaces it with a 1 kHz tone; short edge ramps reduce clicks. The entire audio in a marked span is affected, including instruments; vocal-only separation is not implemented.
6. Review the marks and click **Apply cleanup to export**. Edits are applied before NekoDJ speed shifts and padding, so source timestamps remain aligned. The ZIP includes `content-cleanup-report.json`. Changing a mark disables application until reviewed again.

**Remove embedded metadata** is on by default in the UI, under Padding & finishing. It strips descriptive tags and attachments from the audio, including title, artist, album, comments, and track number. Filenames, ZIP config/report names, and unavoidable technical/container information remain. Duration, bitrate, sample rate, and channel count are properties of the audio and cannot be hidden by tag removal.

Whisper runs locally through whisper.cpp. Installed models live under `tools/models`, and transcript caches and preview files stay beside each source in `data/`. Balanced mode uses multilingual Whisper base (148 MB). Higher-accuracy mode uses multilingual Whisper small (488 MB); it can still make mistakes and runs more slowly. One-minute overlapping sections keep long-source processing bounded, and transcripts are cached for fast word-list rechecks. Only software/model downloads need internet access; audio is not sent to a transcription service.

On a new checkout, run `./setup-cleanup.ps1` for balanced scanning, or `./setup-cleanup.ps1 -HighAccuracy` for both models. The installer verifies published SHA-256 hashes. Whisper.cpp source/license: https://github.com/ggml-org/whisper.cpp . Extended dictionary: https://github.com/snguyenthanh/better_profanity (MIT; notice at `resources/wordlist-LICENSE.txt`). These dictionaries are not Roblox's own filter data.

`tests/test_cleanup.py` checks token/phrase matching, real synthetic-speech recognition when the fixture is present, signal replacement, metadata stripping, and edit alignment after shift/padding. `tests/cleanup_browser_check.py` exercises scan → review → preview → apply → ZIP on desktop and mobile.

## Privacy and storage details

The server binds only to `127.0.0.1`. Splitter imports and exports stay under `data/` on your disk. YouTube contacts YouTube and its delivery services. NekoDJ uploads no audio; all encoder scripts are served locally. No telemetry, external fonts, API keys, or cloud storage. Files persist across restarts; stop the app and delete `data/` to clear them. Your last source is remembered in this browser. Avoid multiple instances sharing the same port.

## Development

```powershell
./.venv/Scripts/python.exe -m pip install pytest httpx playwright
./.venv/Scripts/python.exe -m pytest -q
```

Browser tests use installed Chrome and the running server. `tests/browser_check.py` exercises import, editing, ZIP export, NekoDJ preview and all three encoders. The synthetic tone fixture is generated locally; no copyrighted samples are included.

`tests/studio_check.py` additionally exercises title cleanup, undo/redo, search, shifted preview, padding, NekoDJ config ZIPs, saved drafts/settings, mobile layout, and browser-only padding. Backend tests check actual decoded padding and durations in MP3, Vorbis OGG, and WAV, and verify folder organization without opening Explorer.

The locally vendored lamejs MP3 encoder uses LAME under the LGPL; see the upstream notice in `static/vendor/lamejs-LICENSE.txt`. It is served as a separate, unmodified script. Upstream source: https://github.com/zhuker/lamejs · LAME project: https://lame.sourceforge.net
