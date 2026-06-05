# Contributing & developer guide

DeutschX is three layers that share one brain:

```
deutschx/            Python core — the tutor, memory, spaced-repetition, word study, audio
  service.py         UI-agnostic logic every frontend calls
  api/server.py      local FastAPI server the apps talk to (http://127.0.0.1:8756)
  cli.py             terminal frontend
desktop/             Tauri (Rust) + React/TypeScript desktop app
  src/               the React UI
  src-tauri/         the Rust shell (launches the engine, bundles everything)
installer/           builds the Python engine into a standalone "sidecar" binary
.github/workflows/   CI that builds the installers
```

The desktop app never runs Python directly — it launches a **bundled engine** (the FastAPI
server compiled into a single executable) and talks to it over HTTP. The same API will back a
future web/mobile app.

## Prerequisites

- **Python 3.11+**
- **Node 20+** and **pnpm 9+** (`npm i -g pnpm`)
- **Rust 1.88+** (`rustup`) — for the desktop shell
- Platform Tauri prerequisites: see <https://tauri.app/start/prerequisites/>
  - Linux also needs: `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf`

## Run in development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd desktop && pnpm install && cd ..
./run-dev.sh
```

`run-dev.sh` starts the Python engine (`python -m deutschx.api`) and opens the Tauri dev window.
In dev, the Rust shell does **not** launch its own engine (it detects `tauri dev` and skips it),
so there's no port clash. Dev data lives in `./data` (set via `DEUTSCHX_DATA_DIR` in the script);
a packaged build uses the per-OS app-data folder instead.

Terminal version: `python -m deutschx`.

## How packaging works

1. **`installer/build_sidecar.py`** runs PyInstaller on `installer/deutschx_server.py` and copies
   the result to `desktop/src-tauri/binaries/deutschx-server-<rust-target-triple>[.exe]`.
2. **`tauri.conf.json`** lists it under `bundle.externalBin`, so Tauri bundles the matching binary.
3. **`src-tauri/src/lib.rs`** spawns it on startup (release builds only) and kills it on exit.
4. The React app polls `/api/health` and shows a splash until the engine is up.

### Build an installer locally

```bash
source .venv/bin/activate
pip install pyinstaller
python installer/build_sidecar.py        # builds the engine for THIS OS
cd desktop && pnpm install && pnpm tauri build
# installers land in desktop/src-tauri/target/release/bundle/
```

The bundled binaries are git-ignored — CI (or you) rebuilds them per platform.

## Releasing

Push a version tag and GitHub Actions does the rest:

```bash
git tag v1.0.0 && git push origin v1.0.0
```

`.github/workflows/release.yml` builds the engine + the Tauri installers on macOS (Apple Silicon
+ Intel), Windows and Linux, and attaches them to a **draft** Release. Review the assets, then
publish.

### Adding macOS notarization later (optional)

The builds are currently **unsigned** (users right-click → Open once). To remove that step you
need an Apple Developer account ($99/yr). Add these secrets to the repo and they'll be picked up
by `tauri-action`:

- `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PASSWORD` (your Developer ID cert, base64)
- `APPLE_SIGNING_IDENTITY`
- `APPLE_ID`, `APPLE_PASSWORD` (app-specific password), `APPLE_TEAM_ID`

Then set `ENABLE_CODE_SIGNING` / the matching `env` in the workflow per the Tauri docs:
<https://tauri.app/distribute/sign/macos/>. The same pattern applies for Windows signing.

## Optional: microphone pronunciation

The mic feature needs heavier, separate dependencies (kept out of the base install):

```bash
pip install -r requirements-pron.txt    # sounddevice, numpy, faster-whisper
```

Then enable it in **Settings → Enable microphone pronunciation** (a speech model downloads once).
Bundling this into the prebuilt installers (PyInstaller + faster-whisper/ctranslate2) is a known
hard problem and is not done yet; for now it's a source-build / power-user feature.

## Code style

Match the surrounding code: the Python core favours small, well-named functions with short
docstrings; the React views are self-contained and use the shared `api.ts` client. No lesson
logic in the API or UI — it all lives in `deutschx/service.py`.
