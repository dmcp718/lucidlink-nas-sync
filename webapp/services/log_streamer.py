"""
Log streaming service for real-time log viewing.
"""
import asyncio
import os
from typing import AsyncGenerator, Optional

import aiofiles

from webapp.config import settings


class LogStreamer:
    """Service for streaming log files."""

    def __init__(self):
        self.log_files = {
            "container": os.path.join(settings.log_path, "container.log"),
            "sync": os.path.join(settings.log_path, "sync.log"),
            "errors": os.path.join(settings.log_path, "errors.log"),
        }

    async def get_logs(
        self,
        log_type: str = "container",
        lines: int = 100,
    ) -> list[str]:
        """Get the last N lines from a log file."""
        log_file = self.log_files.get(log_type)
        if not log_file or not os.path.exists(log_file):
            return []

        try:
            async with aiofiles.open(log_file, "r") as f:
                content = await f.read()
                all_lines = content.strip().split("\n")
                return all_lines[-lines:] if lines > 0 else all_lines
        except Exception as e:
            return [f"Error reading log: {e}"]

    async def stream_logs(
        self,
        log_type: str = "container",
    ) -> AsyncGenerator[str, None]:
        """Stream log file changes in real-time (tail -f style)."""
        log_file = self.log_files.get(log_type)
        if not log_file:
            yield f"Unknown log type: {log_type}"
            return

        # Wait for file to exist
        while not os.path.exists(log_file):
            await asyncio.sleep(1)

        try:
            async with aiofiles.open(log_file, "r") as f:
                # Seek to end
                await f.seek(0, 2)

                while True:
                    line = await f.readline()
                    if line:
                        yield line.rstrip()
                    else:
                        await asyncio.sleep(0.5)
        except Exception as e:
            yield f"Error streaming log: {e}"

    def get_available_logs(self) -> list[dict]:
        """Get list of available log files with metadata."""
        result = []
        for name, path in self.log_files.items():
            info = {
                "name": name,
                "path": path,
                "exists": os.path.exists(path),
                "size": 0,
            }
            if info["exists"]:
                try:
                    info["size"] = os.path.getsize(path)
                except OSError:
                    pass
            result.append(info)
        return result


# Singleton instance
log_streamer = LogStreamer()
