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
    WorkerProgress,
    JobStatus,
    JobStats,
    SystemStatus,
    FilenameIssue,
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

    def _get_source_stats(self, source_path: str, exclude_patterns: list[str]) -> tuple[int, int]:
        """Calculate total files and bytes in source directory."""
        total_files = 0
        total_bytes = 0
        try:
            for root, dirs, files in os.walk(source_path):
                # Filter excluded patterns
                for pattern in exclude_patterns:
                    dirs[:] = [d for d in dirs if not self._matches_pattern(d, pattern)]

                for f in files:
                    # Skip excluded files
                    if any(self._matches_pattern(f, p) for p in exclude_patterns):
                        continue
                    try:
                        filepath = os.path.join(root, f)
                        total_bytes += os.path.getsize(filepath)
                        total_files += 1
                    except (OSError, PermissionError):
                        pass
        except (OSError, PermissionError):
            pass
        return total_files, total_bytes

    def _get_item_stats(self, source_path: str, item: str, exclude_patterns: list[str]) -> tuple[int, int]:
        """Calculate files and bytes for a single item (file or directory)."""
        item_path = os.path.join(source_path, item)
        if os.path.isfile(item_path):
            try:
                return 1, os.path.getsize(item_path)
            except (OSError, PermissionError):
                return 0, 0
        return self._get_source_stats(item_path, exclude_patterns)

    def _get_top_level_items(self, source_path: str, exclude_patterns: list[str]) -> list[tuple[str, int, int]]:
        """Get top-level items with their file counts and sizes."""
        items = []
        try:
            for item in os.listdir(source_path):
                if any(self._matches_pattern(item, p) for p in exclude_patterns):
                    continue
                files, bytes_size = self._get_item_stats(source_path, item, exclude_patterns)
                items.append((item, files, bytes_size))
        except (OSError, PermissionError):
            pass
        # Sort by size descending for better distribution
        items.sort(key=lambda x: x[2], reverse=True)
        return items

    def _distribute_items(self, items: list[tuple[str, int, int]], num_workers: int) -> list[list[tuple[str, int, int]]]:
        """Distribute items across workers using greedy load balancing."""
        if not items:
            return [[] for _ in range(num_workers)]

        # Use greedy algorithm: assign largest item to worker with least total size
        worker_loads = [0] * num_workers
        worker_items: list[list[tuple[str, int, int]]] = [[] for _ in range(num_workers)]

        for item in items:
            # Find worker with minimum load
            min_worker = min(range(num_workers), key=lambda w: worker_loads[w])
            worker_items[min_worker].append(item)
            worker_loads[min_worker] += item[2]  # Add bytes to load

        return worker_items

    def _matches_pattern(self, name: str, pattern: str) -> bool:
        """Simple pattern matching for exclude patterns."""
        import fnmatch
        return fnmatch.fnmatch(name, pattern)

    async def _log_errors(self, job_name: str, job_id: str, errors: list[str]):
        """Log errors to the errors.log file."""
        error_log_path = os.path.join(settings.log_path, "errors.log")
        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        try:
            async with aiofiles.open(error_log_path, "a") as f:
                await f.write(f"\n[{timestamp}] Job: {job_name} ({job_id})\n")
                for error in errors:
                    await f.write(f"  {error}\n")
        except Exception as e:
            print(f"Error writing to errors.log: {e}")

    # Characters that are problematic on various filesystems
    PROBLEMATIC_CHARS = {
        '\\': ('backslash', '\\'),
        ':': ('colon', ':'),
        '*': ('asterisk', '*'),
        '?': ('question_mark', '?'),
        '"': ('double_quote', '"'),
        '<': ('less_than', '<'),
        '>': ('greater_than', '>'),
        '|': ('pipe', '|'),
        '\x00': ('null_byte', '\x00'),
    }
    # Control characters (0x00-0x1F)
    CONTROL_CHARS = set(chr(i) for i in range(32))

    def _check_filename(self, name: str, rel_path: str) -> Optional[tuple[str, Optional[str]]]:
        """Check a filename for problematic characters. Returns (issue_type, issue_char) or None."""
        # Check for problematic characters
        for char, (issue_type, _) in self.PROBLEMATIC_CHARS.items():
            if char in name:
                return (issue_type, char)

        # Check for control characters
        for char in name:
            if char in self.CONTROL_CHARS:
                return ('control_char', char)

        # Check for leading/trailing spaces (cross-platform issues)
        if name.startswith(' '):
            return ('leading_space', ' ')
        if name.endswith(' '):
            return ('trailing_space', ' ')

        # Check for trailing dots (Windows issue)
        if name.endswith('.') and name != '.' and name != '..':
            return ('trailing_dot', '.')

        # Check for very long filenames (255 byte limit common)
        if len(name.encode('utf-8')) > 255:
            return ('too_long', None)

        return None

    async def _preflight_check_filenames(
        self,
        job_id: str,
        job_name: str,
        source: str,
        exclude_patterns: list[str]
    ) -> int:
        """Check all filenames for problematic characters. Saves issues to manager. Returns count."""
        from webapp.services.filename_issues import filename_issues_manager

        # Clear previous issues for this job
        await filename_issues_manager.clear_job_issues(job_id)

        issue_count = 0
        try:
            for root, dirs, files in os.walk(source):
                # Filter excluded directories
                dirs[:] = [d for d in dirs if not any(self._matches_pattern(d, p) for p in exclude_patterns)]

                rel_root = os.path.relpath(root, source)

                # Check directory names
                for d in dirs:
                    rel_path = os.path.join(rel_root, d) if rel_root != '.' else d
                    issue = self._check_filename(d, rel_path)
                    if issue:
                        issue_type, issue_char = issue
                        await filename_issues_manager.add_issue(
                            job_id=job_id,
                            job_name=job_name,
                            source_base=source,
                            relative_path=rel_path,
                            filename=d,
                            is_dir=True,
                            issue_type=issue_type,
                            issue_char=issue_char,
                        )
                        issue_count += 1

                # Check file names
                for f in files:
                    if any(self._matches_pattern(f, p) for p in exclude_patterns):
                        continue
                    rel_path = os.path.join(rel_root, f) if rel_root != '.' else f
                    issue = self._check_filename(f, rel_path)
                    if issue:
                        issue_type, issue_char = issue
                        await filename_issues_manager.add_issue(
                            job_id=job_id,
                            job_name=job_name,
                            source_base=source,
                            relative_path=rel_path,
                            filename=f,
                            is_dir=False,
                            issue_type=issue_type,
                            issue_char=issue_char,
                        )
                        issue_count += 1

        except (OSError, PermissionError) as e:
            print(f"Error scanning filenames: {e}")

        # Save all issues
        await filename_issues_manager.save()
        return issue_count

    def _preflight_create_dirs(self, source: str, dest: str, exclude_patterns: list[str]) -> int:
        """Create directory structure on destination before sync. Returns directory count."""
        dir_count = 0
        try:
            for root, dirs, files in os.walk(source):
                # Filter excluded directories
                dirs[:] = [d for d in dirs if not any(self._matches_pattern(d, p) for p in exclude_patterns)]

                # Create corresponding directory on destination
                rel_path = os.path.relpath(root, source)
                if rel_path == '.':
                    dest_dir = dest
                else:
                    dest_dir = os.path.join(dest, rel_path)

                os.makedirs(dest_dir, exist_ok=True)
                dir_count += 1
        except (OSError, PermissionError) as e:
            print(f"Error creating directory structure: {e}")
        return dir_count

    async def _run_worker(
        self,
        worker_id: int,
        items: list[tuple[str, int, int]],
        source: str,
        dest: str,
        rsync_opts: list[str],
        progress: SyncProgress,
        job_id: str,
    ) -> tuple[int, list[str]]:
        """Run rsync for a subset of items assigned to this worker."""
        worker = progress.workers[worker_id]
        worker.status = "running"
        error_lines = []
        files_done = 0

        for item_name, item_files, item_bytes in items:
            item_source = os.path.join(source, item_name)
            worker.current_file = item_name

            # Determine if item is file or directory
            if os.path.isfile(item_source):
                cmd = ["rsync"] + rsync_opts + [item_source, dest]
            else:
                cmd = ["rsync"] + rsync_opts + [item_source + "/", os.path.join(dest, item_name) + "/"]

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_text = line.decode().strip()
                    if line_text.startswith("rsync:") or line_text.startswith("rsync error:"):
                        error_lines.append(f"[Worker {worker_id}] {line_text}")

                await process.wait()

                if process.returncode == 0:
                    files_done += item_files
                    worker.files_transferred = files_done
                    # Update overall progress
                    progress.files_transferred = sum(w.files_transferred for w in progress.workers)
                    if progress.files_total > 0:
                        progress.percent_complete = (progress.files_transferred / progress.files_total) * 100
                    progress.updated_at = datetime.utcnow()
                    await self._notify_progress(job_id, progress)
                else:
                    error_lines.append(f"[Worker {worker_id}] Failed to sync {item_name}: exit code {process.returncode}")

            except Exception as e:
                error_lines.append(f"[Worker {worker_id}] Error syncing {item_name}: {e}")

        worker.status = "completed" if not error_lines else "failed"
        worker.current_file = None
        progress.active_workers = sum(1 for w in progress.workers if w.status == "running")
        return files_done, error_lines

    async def _run_sync(self, job: SyncJob):
        """Run the sync process for a job using parallel workers."""
        job_id = job.id

        try:
            source = job.source_path.rstrip("/")
            dest = job.dest_path.rstrip("/")

            # Get progress object
            progress = self.progress.get(job_id)
            if not progress:
                progress = SyncProgress(job_id=job_id, status=JobStatus.RUNNING, started_at=datetime.utcnow())
                self.progress[job_id] = progress

            # Calculate source stats and get top-level items (run in executor)
            loop = asyncio.get_event_loop()
            items = await loop.run_in_executor(
                None, self._get_top_level_items, source, job.exclude_patterns
            )

            # Calculate totals
            total_files = sum(item[1] for item in items)
            total_bytes = sum(item[2] for item in items)

            # Determine number of workers (at most as many as items)
            num_workers = min(job.parallel_jobs, len(items)) if items else 1

            # Distribute items across workers
            worker_items = self._distribute_items(items, num_workers)

            # Initialize worker progress objects
            progress.files_total = total_files
            progress.bytes_total = total_bytes
            progress.workers = []
            for i in range(num_workers):
                w_items = worker_items[i]
                wp = WorkerProgress(
                    worker_id=i,
                    items=[item[0] for item in w_items],
                    files_total=sum(item[1] for item in w_items),
                    bytes_total=sum(item[2] for item in w_items),
                    status="pending"
                )
                progress.workers.append(wp)

            progress.active_workers = num_workers
            progress.updated_at = datetime.utcnow()
            await self._notify_progress(job_id, progress)

            # Build rsync options
            rsync_opts = job.rsync_options.split()
            # Remove --info=progress2 for parallel mode (too noisy)
            rsync_opts = [opt for opt in rsync_opts if opt != "--info=progress2"]
            for pattern in job.exclude_patterns:
                rsync_opts.extend(["--exclude", pattern])

            # Pre-flight: Check filenames for problematic characters
            progress.current_file = "Pre-flight: Checking filenames..."
            progress.updated_at = datetime.utcnow()
            await self._notify_progress(job_id, progress)

            issue_count = await self._preflight_check_filenames(
                job_id, job.name, source, job.exclude_patterns
            )
            if issue_count > 0:
                progress.current_file = f"Pre-flight: {issue_count} filename issues found (see Filename Issues)"
                progress.updated_at = datetime.utcnow()
                await self._notify_progress(job_id, progress)

            # Pre-flight: Create directory structure on destination
            progress.current_file = "Pre-flight: Creating directories..."
            progress.updated_at = datetime.utcnow()
            await self._notify_progress(job_id, progress)

            dir_count = await loop.run_in_executor(
                None, self._preflight_create_dirs, source, dest, job.exclude_patterns
            )
            progress.current_file = f"Pre-flight: Created {dir_count} directories"
            progress.updated_at = datetime.utcnow()
            await self._notify_progress(job_id, progress)

            # Run workers in parallel
            self.running_processes[job_id] = True  # Mark as running (not a real process)
            tasks = [
                self._run_worker(i, worker_items[i], source, dest, rsync_opts, progress, job_id)
                for i in range(num_workers)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            total_files_done = 0
            all_errors = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    all_errors.append(f"[Worker {i}] Exception: {result}")
                else:
                    files_done, errors = result
                    total_files_done += files_done
                    all_errors.extend(errors)

            # Log errors
            if all_errors:
                await self._log_errors(job.name, job_id, all_errors)

            # Calculate duration and statistics
            end_time = datetime.utcnow()
            duration = (end_time - progress.started_at).total_seconds() if progress.started_at else 0.0

            stats = JobStats(
                duration_seconds=duration,
                files_synced=total_files_done if total_files_done > 0 else total_files,
                bytes_transferred=total_bytes,
                files_per_second=total_files_done / duration if duration > 0 else 0.0,
                bytes_per_second=total_bytes / duration if duration > 0 else 0.0,
                errors=len(all_errors),
            )

            # Update final status
            if not all_errors:
                job.status = JobStatus.COMPLETED
                job.last_run_status = JobStatus.COMPLETED
                job.last_run_message = f"Completed: {stats.files_synced} files in {duration:.1f}s ({num_workers} workers)"
                progress.status = JobStatus.COMPLETED
                progress.percent_complete = 100.0
            else:
                job.status = JobStatus.FAILED
                job.last_run_status = JobStatus.FAILED
                error_summary = all_errors[0] if all_errors else "Unknown error"
                job.last_run_message = f"Failed: {error_summary}"
                progress.status = JobStatus.FAILED
                progress.error_message = error_summary

            # Store stats
            job.last_run_duration = duration
            job.last_run_stats = stats
            job.run_count += 1

            # Update aggregate statistics
            job.total_files_synced += stats.files_synced
            job.total_bytes_transferred += stats.bytes_transferred
            job.total_run_time += duration
            if job.total_run_time > 0:
                job.avg_files_per_second = job.total_files_synced / job.total_run_time
                job.avg_bytes_per_second = job.total_bytes_transferred / job.total_run_time

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

    def _parse_rsync_progress(self, line: str, progress: SyncProgress) -> Optional[str]:
        """Parse rsync --info=progress2 output. Returns error message if line is an error."""
        # Check for rsync error messages first
        if line.startswith("rsync:") or line.startswith("rsync error:"):
            return line  # Return error for logging

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
            return None

        # Also check for file being transferred
        if line and not line.startswith(" ") and "/" in line:
            progress.current_file = line
            progress.files_transferred += 1

        return None

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
