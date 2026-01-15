"""Main FastAPI application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import api_router, pages_router
from .websocket import websocket_router

# Get the directory containing this file
API_DIR = Path(__file__).parent
STATIC_DIR = API_DIR / "static"


def create_app(
    title: str = "PRDForge",
    debug: bool = False,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        title: Application title.
        debug: Enable debug mode.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(
        title=title,
        description="PRD-driven AI code generation platform",
        version="0.1.0",
        debug=debug,
    )

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Include routers
    app.include_router(api_router, prefix="/api")
    app.include_router(pages_router)
    app.include_router(websocket_router)

    return app
