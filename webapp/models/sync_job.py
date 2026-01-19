"""
Pydantic models for sync jobs and related data.
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a sync job."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class SyncDirection(str, Enum):
    """Direction of sync operation."""
    LOCAL_TO_FILESPACE = "local-to-filespace"
    FILESPACE_TO_LOCAL = "filespace-to-local"
    BIDIRECTIONAL = "bidirectional"


class SyncProgress(BaseModel):
    """Real-time progress information for a running sync job."""
    job_id: str
    status: JobStatus = JobStatus.IDLE
    current_file: Optional[str] = None
    files_total: int = 0
    files_transferred: int = 0
    bytes_total: int = 0
    bytes_transferred: int = 0
    transfer_rate: Optional[str] = None
    eta: Optional[str] = None
    percent_complete: float = 0.0
    started_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    error_message: Optional[str] = None


class SyncJobBase(BaseModel):
    """Base model for sync job properties."""
    name: str = Field(..., min_length=1, max_length=100, description="Job name")
    source_path: str = Field(..., description="Source directory path")
    dest_path: str = Field(..., description="Destination directory path")
    direction: SyncDirection = SyncDirection.LOCAL_TO_FILESPACE
    interval: int = Field(default=300, ge=0, description="Sync interval in seconds (0 for manual)")
    parallel_jobs: int = Field(default=4, ge=1, le=32, description="Number of parallel rsync jobs")
    rsync_options: str = Field(default="-avz --progress", description="Rsync command options")
    exclude_patterns: list[str] = Field(default_factory=list, description="Patterns to exclude")
    enabled: bool = Field(default=True, description="Whether the job is enabled")


class SyncJobCreate(SyncJobBase):
    """Model for creating a new sync job."""
    pass


class SyncJobUpdate(BaseModel):
    """Model for updating an existing sync job."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    source_path: Optional[str] = None
    dest_path: Optional[str] = None
    direction: Optional[SyncDirection] = None
    interval: Optional[int] = Field(None, ge=0)
    parallel_jobs: Optional[int] = Field(None, ge=1, le=32)
    rsync_options: Optional[str] = None
    exclude_patterns: Optional[list[str]] = None
    enabled: Optional[bool] = None


class JobStats(BaseModel):
    """Statistics for a sync job run."""
    duration_seconds: float = 0.0
    files_synced: int = 0
    bytes_transferred: int = 0
    files_per_second: float = 0.0
    bytes_per_second: float = 0.0
    errors: int = 0


class SyncJob(SyncJobBase):
    """Complete sync job model with metadata."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    status: JobStatus = JobStatus.IDLE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[JobStatus] = None
    last_run_message: Optional[str] = None
    last_run_duration: Optional[float] = None
    last_run_stats: Optional[JobStats] = None
    run_count: int = 0
    # Aggregate statistics
    total_files_synced: int = 0
    total_bytes_transferred: int = 0
    total_run_time: float = 0.0
    avg_files_per_second: float = 0.0
    avg_bytes_per_second: float = 0.0

    class Config:
        use_enum_values = True


class SystemStatus(BaseModel):
    """Overall system status."""
    lucidlink_connected: bool = False
    lucidlink_filespace: Optional[str] = None
    mount_point: Optional[str] = None
    local_path: Optional[str] = None
    jobs_total: int = 0
    jobs_running: int = 0
    jobs_enabled: int = 0
    uptime: Optional[str] = None


class FileInfo(BaseModel):
    """Information about a file or directory."""
    name: str
    path: str
    is_dir: bool
    size: int = 0
    modified: Optional[datetime] = None
    permissions: Optional[str] = None


class BrowseResponse(BaseModel):
    """Response for directory browse requests."""
    path: str
    parent: Optional[str] = None
    items: list[FileInfo] = []
    error: Optional[str] = None
