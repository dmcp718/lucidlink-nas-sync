"""
LucidLink Sync Web UI - FastAPI Application
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from webapp.config import settings
from webapp.routers import api, pages, websocket
from webapp.services.sync_manager import sync_manager
from webapp.services.filename_issues import filename_issues_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup: Load existing jobs and filename issues from persistence
    await sync_manager.load_jobs()
    await filename_issues_manager.load()
    yield
    # Shutdown: Stop all running jobs gracefully
    await sync_manager.shutdown()


app = FastAPI(
    title="LucidLink Sync",
    description="Web UI for managing LucidLink sync jobs",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(api.router, prefix="/api/v1", tags=["api"])
app.include_router(websocket.router, tags=["websocket"])
app.include_router(pages.router, tags=["pages"])

# Templates
templates = Jinja2Templates(directory="/webapp/templates")


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "webui_enabled": settings.webui_enabled,
        "lucidlink_mount": settings.lucidlink_mount_point,
        "local_path": settings.local_data_path,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "webapp.main:app",
        host="0.0.0.0",
        port=settings.webui_port,
        reload=False,
    )
