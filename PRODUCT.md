# Side A

<!-- impeccable:product-schema 1 -->

## Platform
web

## Product Purpose
A locally hosted audio splitter. Import an audio file or YouTube video, detect embedded chapters or description timestamps, preview and edit boundaries, then download named tracks individually or as a ZIP.

The NekoDJ workspace prepares individual songs or selected batches with pitch/speed shifts, volume adjustment, linked or manual effectSpeed values, and browser-only MP3/OGG/WAV conversion. Long tracks default to fit below seven minutes. Splitter exports can be sent directly to this workspace. Batch downloads include audio and corresponding config values.

Large mixes can also be exported directly from the splitter to NekoDJ-ready audio and config on the local server. Auto shift uses the minimum linked pitch/tempo increase necessary to fit each track plus its padding under seven minutes. Optional +4-semitone and custom presets, volume reduction, start/end silence padding, and edge fades are available. Selected titles can be cleaned and edited before export. Title cleaning does not guarantee Roblox moderation approval.

Imported projects and edits persist locally. The editor offers undo/redo, track search, selection tools, an editable tracklist download, original/shifted audition, and per-file output players. Export settings are saved with the draft. Organized server exports are stored under `exports/<project>/Audio` and `Config`; browser-only batches can be saved through the browser's folder picker.

## Operating Context
Runs on the user's computer, bound to localhost. Files stay in the local data directory; YouTube imports require internet access.

## Capabilities and Constraints
Metadata is not song recognition. Sources without chapters need manual timestamps. Stream copying preserves the existing codec with frame-level cut precision. Re-encoding supports MP3, FLAC, and WAV; lossless export cannot restore missing source quality.

Explicit-language cleanup uses local multilingual speech recognition, word dictionaries/custom phrases, and limited theme phrase signals. Users review context and timing, add manual marks, and choose full-signal mute or bleep replacement. Approved edits are applied before shifts/padding and included in export reports. Embedded descriptive metadata can be stripped. Neither content cleanup nor tag removal guarantees Roblox approval or clears copyright. Vocal-only removal and exhaustive semantic theme classification are not implemented.

## Stack
Implementation choice: Python FastAPI, FFmpeg, yt-dlp, and buildless HTML/CSS/JavaScript.
