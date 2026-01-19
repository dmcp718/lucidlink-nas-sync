"""
REST API endpoints for sync job management.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from webapp.models.sync_job import (
    SyncJob,
    SyncJobCreate,
    SyncJobUpdate,
    SyncProgress,
    SystemStatus,
    BrowseResponse,
)
from webapp.services.file_browser import file_browser
from webapp.services.sync_manager import sync_manager
from webapp.services.log_streamer import log_streamer

router = APIRouter()


# Browse endpoints
@router.get("/browse/local", response_model=BrowseResponse)
async def browse_local(path: str = Query(default="", description="Path relative to local data root")):
    """Browse the local data directory."""
    return file_browser.browse_local(path)


@router.get("/browse/filespace", response_model=BrowseResponse)
async def browse_filespace(path: str = Query(default="", description="Path relative to filespace root")):
    """Browse the LucidLink filespace directory."""
    return file_browser.browse_filespace(path)


# Job CRUD endpoints
@router.get("/jobs", response_model=list[SyncJob])
async def list_jobs():
    """List all sync jobs."""
    return await sync_manager.list_jobs()


@router.post("/jobs", response_model=SyncJob, status_code=201)
async def create_job(job: SyncJobCreate):
    """Create a new sync job."""
    return await sync_manager.create_job(job)


@router.get("/jobs/{job_id}", response_model=SyncJob)
async def get_job(job_id: str):
    """Get a specific sync job."""
    job = await sync_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.put("/jobs/{job_id}", response_model=SyncJob)
async def update_job(job_id: str, job_data: SyncJobUpdate):
    """Update an existing sync job."""
    job = await sync_manager.update_job(job_id, job_data)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str):
    """Delete a sync job."""
    if not await sync_manager.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")


# Job control endpoints
@router.post("/jobs/{job_id}/start")
async def start_job(job_id: str):
    """Start a sync job."""
    success, message = await sync_manager.start_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "started", "message": message}


@router.post("/jobs/{job_id}/stop")
async def stop_job(job_id: str):
    """Stop a running sync job."""
    success, message = await sync_manager.stop_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"status": "stopped", "message": message}


@router.get("/jobs/{job_id}/progress", response_model=Optional[SyncProgress])
async def get_job_progress(job_id: str):
    """Get current progress of a sync job."""
    progress = sync_manager.get_progress(job_id)
    if not progress:
        # Return empty progress if job exists but hasn't been run
        job = await sync_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return None
    return progress


# System status endpoints
@router.get("/status", response_model=SystemStatus)
async def get_status():
    """Get overall system status."""
    return await sync_manager.get_system_status()


# Log endpoints
@router.get("/logs")
async def get_logs(
    log_type: str = Query(default="container", description="Log type: container or sync"),
    lines: int = Query(default=100, ge=1, le=10000, description="Number of lines to return"),
):
    """Get log entries."""
    logs = await log_streamer.get_logs(log_type, lines)
    return {"log_type": log_type, "lines": logs}


@router.get("/logs/available")
async def get_available_logs():
    """Get list of available log files."""
    return log_streamer.get_available_logs()
