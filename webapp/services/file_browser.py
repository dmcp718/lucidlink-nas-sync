"""
File browser service for directory listing.
"""
import os
import stat
from datetime import datetime
from pathlib import Path
from typing import Optional

from webapp.config import settings
from webapp.models.sync_job import FileInfo, BrowseResponse


class FileBrowser:
    """Service for browsing local and filespace directories."""

    def __init__(self):
        self.local_root = settings.local_data_path
        self.filespace_root = settings.lucidlink_mount_point

    def _validate_path(self, path: str, root: str) -> tuple[bool, str]:
        """
        Validate that the requested path is within the allowed root.
        Returns (is_valid, resolved_path).
        """
        try:
            # Resolve to absolute path
            resolved = os.path.realpath(os.path.join(root, path.lstrip("/")))
            root_resolved = os.path.realpath(root)

            # Check if resolved path is within root
            if not resolved.startswith(root_resolved):
                return False, ""

            return True, resolved
        except Exception:
            return False, ""

    def _get_file_info(self, path: str, name: str) -> Optional[FileInfo]:
        """Get file information for a single file/directory."""
        try:
            full_path = os.path.join(path, name)
            stat_info = os.stat(full_path)

            return FileInfo(
                name=name,
                path=full_path,
                is_dir=stat.S_ISDIR(stat_info.st_mode),
                size=stat_info.st_size if not stat.S_ISDIR(stat_info.st_mode) else 0,
                modified=datetime.fromtimestamp(stat_info.st_mtime),
                permissions=stat.filemode(stat_info.st_mode),
            )
        except (OSError, PermissionError):
            return None

    def browse_local(self, path: str = "") -> BrowseResponse:
        """Browse the local data directory."""
        return self._browse(path, self.local_root, "local")

    def browse_filespace(self, path: str = "") -> BrowseResponse:
        """Browse the LucidLink filespace directory."""
        return self._browse(path, self.filespace_root, "filespace")

    def _browse(self, path: str, root: str, location: str) -> BrowseResponse:
        """Internal browse implementation."""
        # Handle empty path
        if not path or path == "/":
            path = ""

        # Validate path
        is_valid, resolved_path = self._validate_path(path, root)

        if not is_valid:
            return BrowseResponse(
                path=path,
                error=f"Invalid path: path traversal not allowed"
            )

        if not resolved_path:
            resolved_path = root

        # Check if path exists
        if not os.path.exists(resolved_path):
            return BrowseResponse(
                path=path,
                error=f"Path does not exist: {path}"
            )

        # Check if it's a directory
        if not os.path.isdir(resolved_path):
            return BrowseResponse(
                path=path,
                error=f"Path is not a directory: {path}"
            )

        # Get parent path
        relative_path = os.path.relpath(resolved_path, root)
        if relative_path == ".":
            parent = None
        else:
            parent = os.path.dirname(relative_path)
            if not parent:
                parent = ""

        # List directory contents
        items = []
        try:
            for name in sorted(os.listdir(resolved_path)):
                # Skip hidden files starting with .lucid (internal)
                if name.startswith(".lucid"):
                    continue

                file_info = self._get_file_info(resolved_path, name)
                if file_info:
                    # Make path relative to root
                    file_info.path = os.path.relpath(file_info.path, root)
                    items.append(file_info)

            # Sort: directories first, then files, both alphabetically
            items.sort(key=lambda x: (not x.is_dir, x.name.lower()))

        except PermissionError:
            return BrowseResponse(
                path=relative_path if relative_path != "." else "",
                parent=parent,
                error="Permission denied"
            )

        return BrowseResponse(
            path=relative_path if relative_path != "." else "",
            parent=parent,
            items=items,
        )


# Singleton instance
file_browser = FileBrowser()
