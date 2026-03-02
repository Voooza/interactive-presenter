"""FastAPI application entry point for the Interactive Presenter backend."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routes import router

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


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
