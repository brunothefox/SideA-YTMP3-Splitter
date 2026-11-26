# Changes

## 1.2.0

- Unified playlist and multi-file batch workspace with audio previews, search, selection, and return from cut editing.
- One ZIP for whole sources, saved selected cuts, or equal-duration parts; folders per source or collision-safe flat names.
- Shared format, metadata removal, clean filenames, padding, fades, and linked pitch/speed controls.
- Persistent export queue with pause/cancel, refresh recovery, and retries that retain completed audio.
- Individual output previews/downloads, CSV/JSON file lists, and an organize/open-folder action.
- Removed NekoDJ config generation and asset-ID mapping; new exports focus on audio.
- Fixed a late import refresh interrupting preview playback.

## 1.1.0

- YouTube Shorts, share, embed, recorded-live, Music, and channel-upload links normalize consistently.
- Playlist/channel links show a selectable video list, with start position, batch size, and pagination.
- Selected videos import as separate projects; per-video errors do not discard successful sources.
- Failed/cancelled playlist batches retry unfinished items while reusing completed projects.
- Release packaging and CI read the app version instead of overwriting the original 1.0.0 release.

## 1.0.0

- Local audio/YouTube splitting with editable chapters, individual downloads and ZIPs.
- NekoDJ batch preparation, automatic duration fitting, speed compensation, padding, fades and metadata stripping.
- Offline word detection, phrase flags, manual review, whole-signal mute/bleep, and optional vocal-only cleanup.
- Persistent job history with pause/resume/cancel/retry; section caches survive interrupted scans.
- A warm speech worker, optional NVIDIA acceleration and compact model generation.
- Zoomed waveform editing, looping, project backup/restore, cleanup review persistence and audio-ID mapping.
- Setup/diagnostics, optional local contextual review through Ollama, update links, source/portable packaging, CI and checksums.

Limitations: no guaranteed moderation approval; contextual models and vocal separation are optional and imperfect; source builds on other operating systems need compatible speech engines; signed installers and automatic in-place updates are not provided.
