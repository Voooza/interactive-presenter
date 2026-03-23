"""FastAPI application entry point for the Interactive Presenter backend."""

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.routes import router
from backend.ws.connection_manager import ConnectionManager
from backend.ws.handlers import ws_router

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


# ---------------------------------------------------------------------------
# Serve pre-built frontend static files when available.
# In production the Docker image copies the Vite build output into
# ``/app/frontend/dist``.  When running locally with ``dev.sh`` the Vite dev
# server handles the frontend instead.
# ---------------------------------------------------------------------------
_STATIC_DIR = Path(os.environ.get("STATIC_DIR", "frontend/dist"))

if _STATIC_DIR.is_dir():
    # ``html=True`` enables SPA fallback — any path that doesn't match a
    # real file returns ``index.html`` so React Router can handle it.
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
