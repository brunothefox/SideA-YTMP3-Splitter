# Changes

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
