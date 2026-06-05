"""Run the API server: python -m deutschx.api [--host H] [--port P]."""
from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    ap = argparse.ArgumentParser(description="DeutschX local API server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8756)
    ap.add_argument("--reload", action="store_true")
    args = ap.parse_args()
    uvicorn.run("deutschx.api.server:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
