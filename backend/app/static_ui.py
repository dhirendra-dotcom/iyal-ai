"""Serve the optional, dependency-free browser UI without changing API routes."""
import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# python:3.12-slim has no /etc/mime.types and Python < 3.13 lacks a built-in
# WebP mapping, so hero images were served as application/octet-stream.
mimetypes.add_type("image/webp", ".webp")


def mount_local_ui(app: FastAPI, directory: Path | None = None) -> bool:
    ui_directory = directory or Path(__file__).resolve().parents[2] / "frontend-lite"
    if not (ui_directory / "index.html").is_file():
        return False
    app.mount("/app", StaticFiles(directory=str(ui_directory), html=True), name="local-ui")
    return True


def mount_landing_site(app: FastAPI, directory: Path | None = None) -> bool:
    """Serve the static landing page at "/".

    Must be called after every API route is registered: Starlette matches in
    registration order, so a root mount added last only handles paths that no
    API route, /health or /app claimed.
    """
    site_directory = directory or Path(__file__).resolve().parents[2] / "site"
    if not (site_directory / "index.html").is_file():
        return False
    app.mount("/", StaticFiles(directory=str(site_directory), html=True), name="landing-site")
    return True
