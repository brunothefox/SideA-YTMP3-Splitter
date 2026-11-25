# Development and UI handoff

Run `start.bat` on Windows or `bash start.sh` on Linux/macOS with Python 3.11+. The standalone entry point is `launcher.py`; backend is FastAPI. Keep source modules and static assets separate from `runtime.HOME`, which owns private user data.

## UI changes

The user intends to refine the UI separately. Preserve existing DOM IDs and the endpoint contracts when changing layout. `static/index.html` is the shell; `app.js` handles import/split and browser audio; `batch.js` handles browser batches; `studio.js` handles drafts and exports; `cleanup.js` handles speech review; `features.js` handles setup/jobs/backups/optional tools; `timeline.js` handles precise edit windows; `browser_sessions.js` handles optional IndexedDB recovery. CSS files correspond to these modules. Scripts use shared global functions, so keep their load order until a deliberate module refactor.

Do not change claims to “moderation safe”, “copyright free”, or perfect recognition. Theme flags and model suggestions require review. Browser-only conversion must not upload audio. Keep privacy descriptions accurate for local-server workflows.

## Checks

Install `pytest httpx playwright pyinstaller` for development. Run `python -m pytest -q`; browser smoke scripts use installed Chrome and a running local server. Never commit `data`, `exports`, `workspace`, `tools`, model weights, test audio, or credentials.

Build: `python -m PyInstaller --noconfirm SideA.spec`, then `python scripts/package_release.py`. The allowlist excludes user state. CI publishes versioned ZIPs and checksums; test the portable launcher with a fresh workspace before releasing.

Optional GPU, Demucs and local-Ollama features need separate integration testing on actual supported hardware/models. Run `benchmarks/evaluate.py` with permissioned, held-out labeled recordings to measure detection errors. Synthetic tests alone do not establish real-song accuracy.
