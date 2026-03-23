"""FastAPI application entry point for the Interactive Presenter backend."""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from backend.routes import router
from backend.ws.connection_manager import ConnectionManager
from backend.ws.handlers import ws_router


class SinglePageAppFiles(StaticFiles):
    """Serve built frontend assets and fall back to ``index.html`` for SPA routes."""

    _NO_FALLBACK_PREFIXES = ("api", "ws")

    async def get_response(self, path: str, scope: Scope) -> Response:
        """Return the matching static file or the SPA entrypoint.

        Args:
            path: Requested path relative to the static mount.
            scope: ASGI request scope.

        Returns:
            A static file response, or ``index.html`` for client-side routes.

        Raises:
            StarletteHTTPException: If the requested path should remain a 404.
        """
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not self._should_serve_index(path, scope):
                raise

        return await super().get_response("index.html", scope)

    def _should_serve_index(self, path: str, scope: Scope) -> bool:
        """Return whether a missing path should fall back to the SPA entrypoint."""
        method = scope.get("method")
        if method not in {"GET", "HEAD"}:
            return False

        normalized_path = path.strip("/")
        if not normalized_path:
            return True

        first_segment = normalized_path.split("/", maxsplit=1)[0]
        if first_segment in self._NO_FALLBACK_PREFIXES or normalized_path == "healthz":
            return False

        return "." not in Path(normalized_path).name


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Interactive Presenter",
        description="Backend API for the Interactive Presenter web application.",
        version="0.1.0",
    )

    # Allow all origins during development so the Vite dev server (port 5173)
    # can reach the API without CORS errors. Restrict in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(ws_router)

    # Create a single ConnectionManager instance shared across the application.
    app.state.connection_manager = ConnectionManager()

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        """Health check endpoint for Docker and load balancer probes."""
        return JSONResponse({"status": "ok"})

    # -----------------------------------------------------------------------
    # Serve pre-built frontend static files when available.
    # In production the Docker image copies the Vite build output into
    # ``/app/frontend/dist``. When running locally with ``dev.sh`` the Vite dev
    # server handles the frontend instead.
    # -----------------------------------------------------------------------
    static_dir = Path(os.environ.get("STATIC_DIR", "frontend/dist"))

    if static_dir.is_dir():
        app.mount(
            "/", SinglePageAppFiles(directory=str(static_dir), html=True), name="static"
        )

    return app


app = create_app()


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
