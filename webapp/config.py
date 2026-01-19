"""
Application configuration from environment variables.
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LucidLink settings
    lucidlink_filespace: str = os.getenv("LUCIDLINK_FILESPACE", "")
    lucidlink_user: str = os.getenv("LUCIDLINK_USER", "")
    lucidlink_mount_point: str = os.getenv("LUCIDLINK_MOUNT_POINT", "/data/filespace")
    local_data_path: str = os.getenv("LOCAL_DATA_PATH", "/data/local")

    # Sync settings
    sync_direction: str = os.getenv("SYNC_DIRECTION", "local-to-filespace")
    sync_interval: int = int(os.getenv("SYNC_INTERVAL", "300"))
    parallel_jobs: int = int(os.getenv("PARALLEL_JOBS", "4"))
    rsync_options: str = os.getenv("RSYNC_OPTIONS", "-avz --progress")
    sync_exclude: str = os.getenv("SYNC_EXCLUDE", ".DS_Store,Thumbs.db,*.tmp")

    # Web UI settings
    webui_enabled: bool = os.getenv("WEBUI_ENABLED", "true").lower() == "true"
    webui_port: int = int(os.getenv("WEBUI_PORT", "8080"))

    # Paths
    config_path: str = "/config"
    jobs_file: str = "/config/jobs.json"
    log_path: str = "/var/log/sync"

    class Config:
        env_file = ".env"


settings = Settings()
