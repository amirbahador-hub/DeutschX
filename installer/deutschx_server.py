"""Standalone entry point for the bundled DeutschX API server.

This is what PyInstaller turns into the `deutschx-server` sidecar binary that the desktop
app ships and launches. Importing the FastAPI `app` object directly (rather than by string)
keeps PyInstaller's dependency analysis happy.
"""
from __future__ import annotations

import os

import uvicorn

from deutschx import config
from deutschx.api.server import app


def main() -> None:
    config.ensure_dirs()
    config.ensure_api_key()
    port = int(os.environ.get("DEUTSCHX_PORT", "8756"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
