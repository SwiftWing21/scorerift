"""PyPI integration — dependency version drift detection.

Score per package: major behind = 0.0, minor = 0.5, patch = 1.0.
Overall score: average across tracked packages.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("scorerift.integrations.pypi")


class PyPIIntegration:
    """Check installed Python packages against PyPI latest versions.

    Feeds into: reliability dimension.
    """

    name = "pypi"

    def __init__(self) -> None:
        self.packages: list[str] = []
        self.timeout: int = 10

    def configure(self, packages: list[str] | None = None, timeout: int = 10, **kwargs: Any) -> None:
        self.packages = packages or []
        self.timeout = timeout

    def checks(self) -> dict[str, Any]:
        return {"dep_freshness": self.check_freshness}

    def check_freshness(self) -> tuple[float, dict[str, Any]]:
        """Compare installed versions against PyPI latest."""
        if not self.packages:
            return 0.5, {"note": "No packages configured for freshness check"}

        try:
            import importlib.metadata

            import httpx

            scores: list[float] = []
            details: list[dict[str, Any]] = []

            for pkg in self.packages:
                try:
                    installed = importlib.metadata.version(pkg)
                except importlib.metadata.PackageNotFoundError:
                    details.append({"package": pkg, "status": "not_installed"})
                    scores.append(0.0)
                    continue

                try:
                    resp = httpx.get(
                        f"https://pypi.org/pypi/{pkg}/json",
                        timeout=self.timeout,
                    )
                    resp.raise_for_status()
                    latest = resp.json()["info"]["version"]
                except Exception:
                    details.append({"package": pkg, "installed": installed, "status": "unknown"})
                    continue

                pkg_score = self._version_score(installed, latest)
                scores.append(pkg_score)
                details.append({
                    "package": pkg,
                    "installed": installed,
                    "latest": latest,
                    "score": pkg_score,
                })

            avg = sum(scores) / len(scores) if scores else 0.5
            return avg, {"packages": details}

        except Exception as e:
            log.warning("PyPI freshness check failed: %s", e)
            return 0.5, {"error": str(e), "tool_failure": True}

    @staticmethod
    def _version_score(installed: str, latest: str) -> float:
        """Score based on version distance: major=0.0, minor=0.5, patch=1.0, same=1.0."""
        try:
            i_parts = [int(x) for x in installed.split(".")[:3]]
            l_parts = [int(x) for x in latest.split(".")[:3]]
            while len(i_parts) < 3:
                i_parts.append(0)
            while len(l_parts) < 3:
                l_parts.append(0)

            if i_parts[0] < l_parts[0]:
                return 0.0  # major behind
            if i_parts[1] < l_parts[1]:
                return 0.5  # minor behind
            if i_parts[2] < l_parts[2]:
                return 1.0  # patch behind (still fine)
            return 1.0  # up to date
        except Exception:
            return 0.5
