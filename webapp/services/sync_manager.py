"""
Sync job manager service.
"""
import asyncio
import json
import os
import re
import subprocess
from datetime import datetime
from typing import Optional

import aiofiles

from webapp.config import settings
from webapp.models.sync_job import (
    SyncJob,
    SyncJobCreate,
    SyncJobUpdate,
    SyncProgress,
    JobStatus,
    SystemStatus,
)


class SyncManager:
    """Manages sync jobs including CRUD, execution, and progress tracking."""

    def __init__(self):
        self.jobs: dict[str, SyncJob] = {}
        self.running_processes: dict[str, asyncio.subprocess.Process] = {}
        self.progress: dict[str, SyncProgress] = {}
        self._progress_callbacks: list = []

    async def load_jobs(self):
        """Load jobs from persistence file."""
        if os.path.exists(settings.jobs_file):
            try:
                async with aiofiles.open(settings.jobs_file, "r") as f:
                    data = json.loads(await f.read())
                    for job_data in data.get("jobs", []):
                        job = SyncJob(**job_data)
                        # Reset status on load (container restart)
                        job.status = JobStatus.IDLE
                        self.jobs[job.id] = job
            except Exception as e:
                print(f"Error loading jobs: {e}")

    async def save_jobs(self):
        """Persist jobs to file."""
        # Ensure config directory exists
        os.makedirs(os.path.dirname(settings.jobs_file), exist_ok=True)

        try:
            data = {
                "jobs": [job.model_dump() for job in self.jobs.values()]
            }
            async with aiofiles.open(settings.jobs_file, "w") as f:
                await f.write(json.dumps(data, indent=2, default=str))
        except Exception as e:
            print(f"Error saving jobs: {e}")

    def register_progress_callback(self, callback):
        """Register a callback for progress updates."""
        self._progress_callbacks.append(callback)

    def unregister_progress_callback(self, callback):
        """Unregister a progress callback."""
        if callback in self._progress_callbacks:
            self._progress_callbacks.remove(callback)

    async def _notify_progress(self, job_id: str, progress: SyncProgress):
        """Notify all registered callbacks of progress update."""
        for callback in self._progress_callbacks:
            try:
                await callback(job_id, progress)
            except Exception as e:
                print(f"Error in progress callback: {e}")

    # CRUD Operations
    async def create_job(self, job_data: SyncJobCreate) -> SyncJob:
        """Create a new sync job."""
        job = SyncJob(**job_data.model_dump())
        self.jobs[job.id] = job
        await self.save_jobs()
        return job

    async def get_job(self, job_id: str) -> Optional[SyncJob]:
        """Get a job by ID."""
        return self.jobs.get(job_id)

    async def list_jobs(self) -> list[SyncJob]:
        """List all jobs."""
        return list(self.jobs.values())

    async def update_job(self, job_id: str, job_data: SyncJobUpdate) -> Optional[SyncJob]:
        """Update an existing job."""
        job = self.jobs.get(job_id)
        if not job:
            return None

        update_data = job_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(job, field, value)

        job.updated_at = datetime.utcnow()
        await self.save_jobs()
        return job

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        if job_id in self.jobs:
            # Stop if running
            if job_id in self.running_processes:
                await self.stop_job(job_id)

            del self.jobs[job_id]
            await self.save_jobs()
            return True
        return False

    # Job Execution
    async def start_job(self, job_id: str) -> tuple[bool, str]:
        """Start a sync job."""
        job = self.jobs.get(job_id)
        if not job:
            return False, "Job not found"

        if job_id in self.running_processes:
            return False, "Job is already running"

        # Initialize progress
        progress = SyncProgress(
            job_id=job_id,
            status=JobStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        self.progress[job_id] = progress

        # Update job status
        job.status = JobStatus.RUNNING
        job.last_run_at = datetime.utcnow()
        await self.save_jobs()

        # Start the sync process
        asyncio.create_task(self._run_sync(job))

        return True, "Job started"

    async def stop_job(self, job_id: str) -> tuple[bool, str]:
        """Stop a running sync job."""
        if job_id not in self.running_processes:
            return False, "Job is not running"

        try:
            process = self.running_processes[job_id]
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            process.kill()
        except Exception as e:
            return False, f"Error stopping job: {e}"
        finally:
            if job_id in self.running_processes:
                del self.running_processes[job_id]

        # Update status
        job = self.jobs.get(job_id)
        if job:
            job.status = JobStatus.STOPPED
            job.last_run_status = JobStatus.STOPPED
            job.last_run_message = "Stopped by user"
            await self.save_jobs()

        if job_id in self.progress:
            self.progress[job_id].status = JobStatus.STOPPED
            await self._notify_progress(job_id, self.progress[job_id])

        return True, "Job stopped"

    async def _run_sync(self, job: SyncJob):
        """Run the sync process for a job."""
        job_id = job.id

        try:
            # Build rsync command with progress
            source = job.source_path.rstrip("/") + "/"
            dest = job.dest_path.rstrip("/") + "/"

            # Base rsync options with machine-readable progress
            rsync_opts = job.rsync_options.split()
            if "--info=progress2" not in rsync_opts:
                rsync_opts.append("--info=progress2")

            # Add exclude patterns
            for pattern in job.exclude_patterns:
                rsync_opts.extend(["--exclude", pattern])

            cmd = ["rsync"] + rsync_opts + [source, dest]

            # Start process
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self.running_processes[job_id] = process

            # Parse progress output
            progress = self.progress.get(job_id)
            if not progress:
                progress = SyncProgress(job_id=job_id, status=JobStatus.RUNNING)
                self.progress[job_id] = progress

            # Read output line by line
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                line_text = line.decode().strip()
                self._parse_rsync_progress(line_text, progress)
                progress.updated_at = datetime.utcnow()
                await self._notify_progress(job_id, progress)

            # Wait for process to complete
            await process.wait()

            # Update final status
            if process.returncode == 0:
                job.status = JobStatus.COMPLETED
                job.last_run_status = JobStatus.COMPLETED
                job.last_run_message = "Completed successfully"
                progress.status = JobStatus.COMPLETED
                progress.percent_complete = 100.0
            else:
                job.status = JobStatus.FAILED
                job.last_run_status = JobStatus.FAILED
                job.last_run_message = f"Failed with exit code {process.returncode}"
                progress.status = JobStatus.FAILED
                progress.error_message = f"Exit code: {process.returncode}"

            job.run_count += 1

        except Exception as e:
            job.status = JobStatus.FAILED
            job.last_run_status = JobStatus.FAILED
            job.last_run_message = str(e)
            if job_id in self.progress:
                self.progress[job_id].status = JobStatus.FAILED
                self.progress[job_id].error_message = str(e)

        finally:
            if job_id in self.running_processes:
                del self.running_processes[job_id]
            await self.save_jobs()
            if job_id in self.progress:
                await self._notify_progress(job_id, self.progress[job_id])

    def _parse_rsync_progress(self, line: str, progress: SyncProgress):
        """Parse rsync --info=progress2 output."""
        # Example: "    1,234,567  45%   12.34MB/s    0:01:23"
        match = re.search(
            r'^\s*([\d,]+)\s+(\d+)%\s+([\d.]+\w+/s)\s+(\d+:\d+:\d+)',
            line
        )
        if match:
            bytes_str, percent, rate, eta = match.groups()
            progress.bytes_transferred = int(bytes_str.replace(",", ""))
            progress.percent_complete = float(percent)
            progress.transfer_rate = rate
            progress.eta = eta
            return

        # Also check for file being transferred
        if line and not line.startswith(" ") and "/" in line:
            progress.current_file = line
            progress.files_transferred += 1

    def get_progress(self, job_id: str) -> Optional[SyncProgress]:
        """Get current progress for a job."""
        return self.progress.get(job_id)

    async def get_system_status(self) -> SystemStatus:
        """Get overall system status."""
        # Check LucidLink connection by verifying FUSE mount in /proc/mounts
        lucidlink_connected = False
        try:
            with open("/proc/mounts", "r") as f:
                mounts = f.read()
                lucidlink_connected = f"{settings.lucidlink_mount_point} fuse" in mounts
        except Exception:
            pass

        return SystemStatus(
            lucidlink_connected=lucidlink_connected,
            lucidlink_filespace=settings.lucidlink_filespace if lucidlink_connected else None,
            mount_point=settings.lucidlink_mount_point,
            local_path=settings.local_data_path,
            jobs_total=len(self.jobs),
            jobs_running=len(self.running_processes),
            jobs_enabled=sum(1 for j in self.jobs.values() if j.enabled),
        )

    async def shutdown(self):
        """Gracefully shutdown all running jobs."""
        for job_id in list(self.running_processes.keys()):
            await self.stop_job(job_id)


# Singleton instance
sync_manager = SyncManager()
