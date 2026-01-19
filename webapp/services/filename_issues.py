"""
Service for managing filename issues - files with problematic characters.
"""
import json
import os
import re
import shutil
from datetime import datetime
from typing import Optional

import aiofiles

from webapp.config import settings
from webapp.models.sync_job import FilenameIssue, FilenameIssuesSummary


class FilenameIssuesManager:
    """Manages filename issues storage and remediation."""

    def __init__(self):
        self.issues_file = os.path.join(settings.config_path, "filename_issues.json")
        self.issues: dict[str, FilenameIssue] = {}

    async def load(self):
        """Load issues from persistence file."""
        if os.path.exists(self.issues_file):
            try:
                async with aiofiles.open(self.issues_file, "r") as f:
                    data = json.loads(await f.read())
                    for issue_data in data.get("issues", []):
                        issue = FilenameIssue(**issue_data)
                        self.issues[issue.id] = issue
            except Exception as e:
                print(f"Error loading filename issues: {e}")

    async def save(self):
        """Persist issues to file."""
        os.makedirs(os.path.dirname(self.issues_file), exist_ok=True)
        try:
            data = {
                "issues": [issue.model_dump() for issue in self.issues.values()]
            }
            async with aiofiles.open(self.issues_file, "w") as f:
                await f.write(json.dumps(data, indent=2, default=str))
        except Exception as e:
            print(f"Error saving filename issues: {e}")

    # Character replacement map for normalization
    CHAR_REPLACEMENTS = {
        '\\': '-',
        ':': '-',
        '*': '_',
        '?': '_',
        '"': "'",
        '<': '(',
        '>': ')',
        '|': '-',
        '\x00': '',
    }

    def normalize_filename(self, name: str) -> str:
        """Generate a normalized filename by replacing problematic characters."""
        result = name

        # Replace known problematic characters
        for char, replacement in self.CHAR_REPLACEMENTS.items():
            result = result.replace(char, replacement)

        # Remove control characters
        result = ''.join(c for c in result if ord(c) >= 32)

        # Remove leading and trailing spaces, and trailing dots
        result = result.strip(' ')  # Remove leading/trailing spaces
        result = result.rstrip('.')  # Remove trailing dots

        # If empty after normalization, use a placeholder
        if not result:
            result = "_renamed_"

        # Truncate if too long (preserve extension)
        if len(result.encode('utf-8')) > 255:
            base, ext = os.path.splitext(result)
            max_base = 255 - len(ext.encode('utf-8')) - 1
            while len(base.encode('utf-8')) > max_base:
                base = base[:-1]
            result = base + ext

        return result

    async def add_issue(
        self,
        job_id: str,
        job_name: str,
        source_base: str,
        relative_path: str,
        filename: str,
        is_dir: bool,
        issue_type: str,
        issue_char: Optional[str] = None,
    ) -> FilenameIssue:
        """Add a new filename issue."""
        source_path = os.path.join(source_base, relative_path)
        suggested_name = self.normalize_filename(filename)

        issue = FilenameIssue(
            job_id=job_id,
            job_name=job_name,
            source_path=source_path,
            relative_path=relative_path,
            filename=filename,
            is_dir=is_dir,
            issue_type=issue_type,
            issue_char=issue_char,
            suggested_name=suggested_name if suggested_name != filename else None,
        )

        self.issues[issue.id] = issue
        return issue

    async def clear_job_issues(self, job_id: str):
        """Clear all issues for a specific job (before re-scan)."""
        to_remove = [id for id, issue in self.issues.items() if issue.job_id == job_id]
        for id in to_remove:
            del self.issues[id]

    def get_issues_for_job(self, job_id: str) -> list[FilenameIssue]:
        """Get all issues for a specific job."""
        return [issue for issue in self.issues.values() if issue.job_id == job_id]

    def get_summary_for_job(self, job_id: str) -> FilenameIssuesSummary:
        """Get summary of issues for a job."""
        issues = self.get_issues_for_job(job_id)
        return FilenameIssuesSummary(
            job_id=job_id,
            total_issues=len(issues),
            pending=sum(1 for i in issues if i.status == "pending"),
            renamed=sum(1 for i in issues if i.status == "renamed"),
            skipped=sum(1 for i in issues if i.status == "skipped"),
            failed=sum(1 for i in issues if i.status == "failed"),
            issues=issues,
        )

    def get_all_pending(self) -> list[FilenameIssue]:
        """Get all pending issues across all jobs."""
        return [issue for issue in self.issues.values() if issue.status == "pending"]

    async def rename_file(self, issue_id: str, new_name: Optional[str] = None) -> tuple[bool, str]:
        """Rename a file to fix the issue."""
        issue = self.issues.get(issue_id)
        if not issue:
            return False, "Issue not found"

        if issue.status != "pending":
            return False, f"Issue already resolved: {issue.status}"

        # Use provided name or suggested name
        target_name = new_name or issue.suggested_name
        if not target_name:
            return False, "No target name provided or suggested"

        if target_name == issue.filename:
            return False, "New name is same as original"

        # Build paths
        parent_dir = os.path.dirname(issue.source_path)
        new_path = os.path.join(parent_dir, target_name)

        # Check if target already exists
        if os.path.exists(new_path):
            return False, f"Target already exists: {new_path}"

        try:
            # Rename the file/directory
            shutil.move(issue.source_path, new_path)

            # Update issue status
            issue.status = "renamed"
            issue.resolved_at = datetime.utcnow()
            await self.save()

            return True, f"Renamed to: {target_name}"

        except Exception as e:
            issue.status = "failed"
            await self.save()
            return False, f"Rename failed: {e}"

    async def skip_issue(self, issue_id: str) -> tuple[bool, str]:
        """Mark an issue as skipped (won't be renamed)."""
        issue = self.issues.get(issue_id)
        if not issue:
            return False, "Issue not found"

        issue.status = "skipped"
        issue.resolved_at = datetime.utcnow()
        await self.save()
        return True, "Issue marked as skipped"

    async def rename_all_pending(self, job_id: Optional[str] = None) -> dict:
        """Rename all pending issues (optionally for a specific job)."""
        if job_id:
            pending = [i for i in self.get_issues_for_job(job_id) if i.status == "pending"]
        else:
            pending = self.get_all_pending()

        results = {
            "total": len(pending),
            "renamed": 0,
            "failed": 0,
            "errors": [],
        }

        for issue in pending:
            success, message = await self.rename_file(issue.id)
            if success:
                results["renamed"] += 1
            else:
                results["failed"] += 1
                results["errors"].append(f"{issue.relative_path}: {message}")

        return results


# Singleton instance
filename_issues_manager = FilenameIssuesManager()
