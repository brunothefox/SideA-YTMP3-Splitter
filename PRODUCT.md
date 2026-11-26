# Side A

<!-- impeccable:product-schema 1 -->

## Platform
web

## Product Purpose
A localhost audio splitter and batch exporter. Import local audio or YouTube videos/Shorts/playlists/channel uploads; preview sources, edit chapter or timestamp cuts, and export named audio files individually or in organized ZIPs.

## Operating Context
Runs on the user's own computer, bound to localhost. Imported projects and exports persist on disk; software downloads and YouTube imports need internet. No cloud audio processing or automatic external uploads.

## Capabilities and Constraints
Single-source waveform editing supports manual cuts, pasted timestamps, equal-duration splitting, selection, title editing, undo/redo, and saved drafts. Metadata is not song recognition. Sources without chapters require supplied timestamps, manual cuts, or fixed-duration splitting.

The batch workspace accepts selected YouTube playlist videos or multiple local files (up to 200 per batch, 2 GB per source). Inline source previews, search, selection, and a return action from the editor keep batch work in one place. Export whole sources, saved selected cuts, or fixed-duration parts. Shared formats/finishing settings apply to the entire selection. Numbered flat or per-source folder layouts prevent duplicate-title collisions. ZIPs contain audio, CSV/JSON file lists, and optional cleanup reports; no game config files are generated.

Exports run sequentially with progress, pause/resume/cancel, persistent retry payloads, and successful-result reuse on unchanged retries. A browser refresh can restore the last batch and active or completed export. Local file upload retries require original files in the same browser session; imported projects remain on disk. Individual output previews/downloads are capped at the first 100 UI entries; all files are included in the ZIP.

Formats: MP3 320 kbps, Vorbis OGG, FLAC, 24-bit WAV, or stream copy of the source codec. Optional linked pitch/speed, volume, fit below seven minutes, padding, and fades. Stream copy cannot apply filters; FLAC/WAV cannot restore source quality. Private/restricted videos and ongoing livestreams may not import.

Local multilingual speech recognition, user-reviewed word/theme marks, silence/bleep replacement, optional Demucs vocal separation, and optional local Ollama transcript review assist content editing. Only applied edits are passed into batch exports. Metadata stripping removes descriptive tags while technical audio properties remain. Content processing cannot guarantee platform approval or clear copyright.

## Stack
Python FastAPI, FFmpeg, yt-dlp, whisper.cpp, and buildless HTML/CSS/JavaScript. Windows portable release, with source launchers for other platforms.
