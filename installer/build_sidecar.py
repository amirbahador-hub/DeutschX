"""Build the DeutschX API server into a standalone sidecar binary for Tauri.

Runs PyInstaller, then copies the result to
  desktop/src-tauri/binaries/deutschx-server-<rust-target-triple>[.exe]
which Tauri bundles as an `externalBin`. Run it on each OS (locally or in CI):

    python packaging/build_sidecar.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "installer" / "deutschx_server.py"
BIN_DIR = ROOT / "desktop" / "src-tauri" / "binaries"
NAME = "deutschx-server"

# uvicorn loads protocol/loop implementations dynamically; name them so PyInstaller bundles them.
HIDDEN = [
    "uvicorn.logging",
    "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http", "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan", "uvicorn.lifespan.on",
]
COLLECT_ALL = ["anthropic", "fastapi", "starlette", "uvicorn", "pydantic", "pydantic_core"]


def target_triple() -> str:
    out = subprocess.run(["rustc", "-Vv"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split("host:", 1)[1].strip()
    raise SystemExit("could not determine the Rust target triple (is rustc installed?)")


def main() -> None:
    args = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile",
        "--name", NAME,
        "--distpath", str(ROOT / "installer" / "dist"),
        "--workpath", str(ROOT / "installer" / "build"),
        "--specpath", str(ROOT / "installer"),
    ]
    for h in HIDDEN:
        args += ["--hidden-import", h]
    for pkg in COLLECT_ALL:
        args += ["--collect-all", pkg]
    args.append(str(ENTRY))
    subprocess.run(args, check=True)

    triple = target_triple()
    ext = ".exe" if os.name == "nt" else ""
    src = ROOT / "installer" / "dist" / (NAME + ext)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    dst = BIN_DIR / f"{NAME}-{triple}{ext}"
    shutil.copy2(src, dst)
    if os.name != "nt":
        dst.chmod(0o755)
    print(f"\n✓ sidecar built: {dst}")


if __name__ == "__main__":
    main()
