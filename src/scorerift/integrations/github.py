"""GitHub integration — CI status, open bugs, stale PRs.

Requires: pip install scorerift[github]
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("scorerift.integrations.github")


class GitHubIntegration:
    """Check GitHub repo health via the REST API.

    Feeds into: testing (CI), code_quality (bugs), architecture (stale PRs).
    """

    name = "github"

    def __init__(self) -> None:
        self.token: str | None = None
        self.repo: str | None = None  # "owner/repo"
        self._base_url = "https://api.github.com"

    def configure(self, token: str | None = None, repo: str | None = None, **kwargs: Any) -> None:
        self.token = token
        self.repo = repo

    def checks(self) -> dict[str, Any]:
        return {
            "ci_status": self.check_ci_status,
            "open_bugs": self.check_open_bugs,
            "stale_prs": self.check_stale_prs,
        }

    def check_ci_status(self) -> tuple[float, dict[str, Any]]:
        """Latest Actions workflow run: passed = 1.0, failed = 0.0."""
        if not self.repo or not self.token:
            return 0.5, {"note": "GitHub not configured"}
        try:
            data = self._get(f"/repos/{self.repo}/actions/runs?per_page=1")
            runs = data.get("workflow_runs", [])
            if not runs:
                return 0.5, {"note": "No workflow runs found"}
            latest = runs[0]
            passed = latest.get("conclusion") == "success"
            return (1.0 if passed else 0.0), {
                "run_id": latest.get("id"),
                "conclusion": latest.get("conclusion"),
                "url": latest.get("html_url"),
            }
        except Exception as e:
            log.warning("CI status check failed: %s", e)
            return 0.5, {"error": str(e), "tool_failure": True}

    def check_open_bugs(self) -> tuple[float, dict[str, Any]]:
        """Score: 1.0 - (open_bugs * 0.05), clamped to [0.0, 1.0]."""
        if not self.repo or not self.token:
            return 0.5, {"note": "GitHub not configured"}
        try:
            data = self._get(f"/repos/{self.repo}/issues?labels=bug&state=open&per_page=100")
            count = len(data) if isinstance(data, list) else 0
            score = max(0.0, 1.0 - count * 0.05)
            return score, {"open_bugs": count}
        except Exception as e:
            log.warning("Open bugs check failed: %s", e)
            return 0.5, {"error": str(e), "tool_failure": True}

    def check_stale_prs(self) -> tuple[float, dict[str, Any]]:
        """Score: 1.0 - (stale_prs * 0.1), clamped. Stale = >14 days old."""
        if not self.repo or not self.token:
            return 0.5, {"note": "GitHub not configured"}
        try:
            import datetime
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)).isoformat()
            data = self._get(f"/repos/{self.repo}/pulls?state=open&per_page=100")
            if not isinstance(data, list):
                return 0.5, {"note": "Unexpected response format"}
            stale = [pr for pr in data if pr.get("created_at", "") < cutoff]
            score = max(0.0, 1.0 - len(stale) * 0.1)
            return score, {"stale_prs": len(stale), "total_open": len(data)}
        except Exception as e:
            log.warning("Stale PRs check failed: %s", e)
            return 0.5, {"error": str(e), "tool_failure": True}

    def _get(self, path: str) -> Any:
        """Make an authenticated GET request to the GitHub API."""
        import httpx
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        resp = httpx.get(f"{self._base_url}{path}", headers=headers, timeout=15)
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining and int(remaining) < 20:
            log.warning("GitHub rate limit low: %s remaining", remaining)
        resp.raise_for_status()
        return resp.json()
