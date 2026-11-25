# Third-party software

Side A's application code is MIT licensed. Dependencies retain their own licenses; this license does not grant rights to audio imported by users.

- **whisper.cpp**: MIT. Source and corresponding release: https://github.com/ggml-org/whisper.cpp/tree/v1.9.2 . Notice: `resources/whisper-LICENSE.txt`. Optional official CPU/CUDA binaries are downloaded unchanged. Whisper models: https://github.com/openai/whisper (MIT); model distribution https://huggingface.co/ggerganov/whisper.cpp . Model downloads are not included in the source archive.
- **FFmpeg**: bundled through imageio-ffmpeg, whose builds have separate FFmpeg licensing (including GPL-enabled builds). FFmpeg remains a separate executable. See the exact binary's `-L` output and build configuration. FFmpeg source: https://ffmpeg.org/download.html ; imageio build/source instructions: https://github.com/imageio/imageio-ffmpeg . The portable archive includes `FFMPEG-LICENSE.txt`, generated from the shipped binary, and dependency license files collected during packaging. Preserve these notices when redistributing.
- **lamejs / LAME**: LGPL. Served as a separate, unmodified script at `static/vendor/lame.min.js`. Notice: `static/vendor/lamejs-LICENSE.txt`. Corresponding lamejs source (v1.2.1): https://github.com/zhuker/lamejs ; LAME: https://lame.sourceforge.net . You can replace this local script with your modified compatible version.
- **Extended word dictionary / better_profanity**: MIT. https://github.com/snguyenthanh/better_profanity . Notice: `resources/wordlist-LICENSE.txt`.
- **yt-dlp**: Unlicense for its own source, with separately licensed dependencies. https://github.com/yt-dlp/yt-dlp . No YouTube cookies or account credentials are bundled.
- **FastAPI**, **Requests**, **Pydantic**, **Mutagen**, **Uvicorn**, **PyInstaller** and Python: their respective upstream licenses are retained in dependency metadata. Mutagen is GPL licensed; PyInstaller's bootloader has its distribution exception. Preserve all dependency notices and consult upstream sources for redistribution requirements.
- **Optional Demucs/PyTorch**: installed separately on demand. https://github.com/facebookresearch/demucs ; https://pytorch.org . Models may have their own terms. Separation does not create music rights.
- **Optional Ollama**: an independent localhost service, not bundled. Each installed model has its own license. https://github.com/ollama/ollama .

No private audio, transcripts, local settings, credentials, or downloaded models are included in the public source archive. A source ZIP is generated from an explicit allowlist.
