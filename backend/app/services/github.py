"""
GitHub Issue Service

Creates GitHub issues for job failures to track and resolve problems.
"""

import hashlib
from datetime import datetime
from typing import Any

import httpx
from loguru import logger

from app.config import get_settings


class GitHubIssueCreator:
    """Creates GitHub issues for job failures."""
    
    def __init__(self):
        self.settings = get_settings()
        self.token = self.settings.github_token
        self.repo = self.settings.github_repo
        self.enabled = bool(self.token and self.repo)
        
        if not self.enabled:
            logger.warning("[GitHub] Not configured - issue creation disabled")
    
    @property
    def api_url(self) -> str:
        return f"https://api.github.com/repos/{self.repo}/issues"
    
    @property
    def search_url(self) -> str:
        return "https://api.github.com/search/issues"
    
    def _generate_issue_hash(self, task_name: str, error: str) -> str:
        """Generate a unique hash for deduplication."""
        # Use first 100 chars of error to group similar errors
        error_prefix = error[:100] if error else ""
        content = f"{task_name}:{error_prefix}"
        return hashlib.md5(content.encode()).hexdigest()[:8]
    
    async def _find_existing_issue(self, task_name: str, issue_hash: str) -> dict | None:
        """
        Search for an existing open issue with the same hash.
        
        Returns the issue if found, None otherwise.
        """
        if not self.enabled:
            return None
        
        try:
            # Search for open issues with our hash in the title
            query = f"repo:{self.repo} is:issue is:open [JOB-{issue_hash}] in:title"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    self.search_url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    params={"q": query},
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("total_count", 0) > 0:
                        return data["items"][0]
                
                return None
                
        except Exception as e:
            logger.error(f"[GitHub] Error searching for existing issue: {e}")
            return None
    
    async def _add_comment(self, issue_number: int, comment: str) -> bool:
        """Add a comment to an existing issue."""
        if not self.enabled:
            return False
        
        try:
            url = f"https://api.github.com/repos/{self.repo}/issues/{issue_number}/comments"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={"body": comment},
                )
                
                if response.status_code == 201:
                    logger.debug(f"[GitHub] ✅ Added comment to issue #{issue_number}")
                    return True
                else:
                    logger.error(f"[GitHub] ❌ Failed to add comment: {response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"[GitHub] ❌ Error adding comment: {e}")
            return False
    
    async def create_issue(
        self,
        task_name: str,
        error: str,
        details: dict[str, Any] | None = None,
    ) -> dict | None:
        """
        Create a GitHub issue for a job failure.
        
        If an issue with the same hash already exists, adds a comment instead.
        
        Args:
            task_name: Name of the failed task
            error: Error message
            details: Optional extra details
            
        Returns:
            Created/updated issue data or None on failure
        """
        if not self.enabled:
            logger.debug(f"[GitHub] Skipping (not configured): {task_name}")
            return None
        
        issue_hash = self._generate_issue_hash(task_name, error)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Check for existing issue
        existing = await self._find_existing_issue(task_name, issue_hash)
        
        if existing:
            # Add comment to existing issue
            comment = f"### ⚠️ Failure Recurrence\n\n"
            comment += f"**Time:** {timestamp}\n\n"
            comment += f"**Error:**\n```\n{error[:500]}\n```\n\n"
            
            if details:
                comment += "**Details:**\n"
                for key, value in details.items():
                    comment += f"- `{key}`: {value}\n"
            
            await self._add_comment(existing["number"], comment)
            logger.info(f"[GitHub] Updated existing issue #{existing['number']}")
            return existing
        
        # Create new issue
        title = f"[JOB-{issue_hash}] {task_name} failure: {error[:80]}"
        
        body = f"## 🚨 Job Failure Report\n\n"
        body += f"**Task:** `{task_name}`\n"
        body += f"**First Occurrence:** {timestamp}\n"
        body += f"**Issue Hash:** `{issue_hash}`\n\n"
        body += f"### Error\n\n```\n{error[:1000]}\n```\n\n"
        
        if details:
            body += "### Details\n\n"
            for key, value in details.items():
                body += f"- **{key}:** `{value}`\n"
            body += "\n"
        
        body += "---\n"
        body += "_This issue was automatically created by the pipeline failure handler._\n"
        body += "_Subsequent failures with the same signature will be added as comments._"
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github+json",
                        "X-GitHub-Api-Version": "2022-11-28",
                    },
                    json={
                        "title": title,
                        "body": body,
                        "labels": ["bug", "pipeline-failure", f"task:{task_name}"],
                    },
                )
                
                if response.status_code == 201:
                    issue_data = response.json()
                    logger.info(f"[GitHub] ✅ Created issue #{issue_data['number']}: {title}")
                    return issue_data
                else:
                    logger.error(f"[GitHub] ❌ Failed to create issue: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"[GitHub] ❌ Error creating issue: {e}")
            return None


# Singleton instance
_creator: GitHubIssueCreator | None = None


def get_github_creator() -> GitHubIssueCreator:
    """Get the singleton GitHubIssueCreator instance."""
    global _creator
    if _creator is None:
        _creator = GitHubIssueCreator()
    return _creator


async def create_failure_issue(
    task_name: str,
    error: str,
    details: dict[str, Any] | None = None,
) -> dict | None:
    """
    Create a GitHub issue for a job failure.
    
    Convenience function that uses the singleton creator.
    """
    creator = get_github_creator()
    return await creator.create_issue(task_name, error, details)

