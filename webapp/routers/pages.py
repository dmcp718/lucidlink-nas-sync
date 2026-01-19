"""
HTML page routes for the web UI.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webapp.services.sync_manager import sync_manager
from webapp.services.file_browser import file_browser

router = APIRouter()
templates = Jinja2Templates(directory="/webapp/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main dashboard page."""
    status = await sync_manager.get_system_status()
    jobs = await sync_manager.list_jobs()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "status": status,
            "jobs": jobs,
        }
    )


@router.get("/jobs/new", response_class=HTMLResponse)
async def new_job(request: Request):
    """New job creation page."""
    return templates.TemplateResponse(
        "partials/job_form.html",
        {
            "request": request,
            "job": None,
            "is_new": True,
        }
    )


@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
async def edit_job(request: Request, job_id: str):
    """Job edit form."""
    job = await sync_manager.get_job(job_id)
    if not job:
        return HTMLResponse(content="Job not found", status_code=404)

    return templates.TemplateResponse(
        "partials/job_form.html",
        {
            "request": request,
            "job": job,
            "is_new": False,
        }
    )


@router.get("/partials/jobs-list", response_class=HTMLResponse)
async def jobs_list_partial(request: Request):
    """HTMX partial for jobs list."""
    jobs = await sync_manager.list_jobs()
    # Get progress for each job
    progress_map = {}
    for job in jobs:
        progress = sync_manager.get_progress(job.id)
        if progress:
            progress_map[job.id] = progress
    return templates.TemplateResponse(
        "partials/jobs_list.html",
        {
            "request": request,
            "jobs": jobs,
            "progress_map": progress_map,
        }
    )


@router.get("/partials/job-row/{job_id}", response_class=HTMLResponse)
async def job_row_partial(request: Request, job_id: str):
    """HTMX partial for a single job row."""
    job = await sync_manager.get_job(job_id)
    if not job:
        return HTMLResponse(content="", status_code=404)

    progress = sync_manager.get_progress(job_id)
    return templates.TemplateResponse(
        "partials/job_row.html",
        {
            "request": request,
            "job": job,
            "progress": progress,
        }
    )


@router.get("/partials/status", response_class=HTMLResponse)
async def status_partial(request: Request):
    """HTMX partial for system status."""
    status = await sync_manager.get_system_status()
    return templates.TemplateResponse(
        "partials/status.html",
        {
            "request": request,
            "status": status,
        }
    )


@router.get("/partials/browser/{location}", response_class=HTMLResponse)
async def browser_partial(request: Request, location: str, path: str = ""):
    """HTMX partial for file browser."""
    if location == "local":
        result = file_browser.browse_local(path)
    elif location == "filespace":
        result = file_browser.browse_filespace(path)
    else:
        return HTMLResponse(content="Invalid location", status_code=400)

    return templates.TemplateResponse(
        "partials/browser.html",
        {
            "request": request,
            "location": location,
            "result": result,
        }
    )


@router.get("/partials/path-picker/{location}", response_class=HTMLResponse)
async def path_picker_partial(request: Request, location: str, path: str = ""):
    """HTMX partial for path picker (folders only)."""
    if location == "local":
        result = file_browser.browse_local(path)
    elif location == "filespace":
        result = file_browser.browse_filespace(path)
    else:
        return HTMLResponse(content="Invalid location", status_code=400)

    # Filter to directories only
    result.items = [item for item in result.items if item.is_dir]

    return templates.TemplateResponse(
        "partials/path_picker.html",
        {
            "request": request,
            "location": location,
            "result": result,
        }
    )


@router.get("/partials/logs", response_class=HTMLResponse)
async def logs_partial(request: Request, log_type: str = "container", lines: int = 100):
    """HTMX partial for log viewer."""
    from webapp.services.log_streamer import log_streamer
    logs = await log_streamer.get_logs(log_type, lines)
    return templates.TemplateResponse(
        "partials/logs.html",
        {
            "request": request,
            "log_type": log_type,
            "logs": logs,
        }
    )


@router.get("/partials/filename-issues", response_class=HTMLResponse)
async def filename_issues_partial(request: Request):
    """HTMX partial for filename issues list."""
    from webapp.services.filename_issues import filename_issues_manager
    issues = list(filename_issues_manager.issues.values())
    # Sort: pending first, then by detected_at descending
    issues.sort(key=lambda x: (x.status != 'pending', x.detected_at), reverse=True)
    return templates.TemplateResponse(
        "partials/filename_issues.html",
        {
            "request": request,
            "issues": issues,
        }
    )
