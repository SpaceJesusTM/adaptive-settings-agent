"""FastAPI application factory.

Run (from the project root):  python -m uvicorn app.main:app --app-dir backend --port 8765
or simply:                    python scripts/dev.py
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api.routes import router
from .config import PROJECT_ROOT, get_settings
from .domain.errors import DomainError
from .services import Services, build_services


def create_app(services: Optional[Services] = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if getattr(app.state, "services", None) is None:
            app.state.services = build_services()
        yield

    app = FastAPI(title="CSC2524 Adaptive Settings Prototype", version=__version__, lifespan=lifespan)
    app.state.services = services
    settings = services.settings if services else get_settings()
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(DomainError)
    async def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    app.include_router(router)

    dist = PROJECT_ROOT / "frontend" / "dist"
    if dist.is_dir() and (dist / "index.html").is_file():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            candidate = (dist / full_path).resolve()
            if full_path and candidate.is_file() and Path(dist.resolve()) in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
