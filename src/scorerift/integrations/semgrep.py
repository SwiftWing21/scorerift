"""Semgrep integration — SAST security scanning.

Requires: pip install semgrep
"""

from __future__ import annotations

import logging
import subprocess
from typing import Any

log = logging.getLogger("scorerift.integrations.semgrep")


class SemgrepIntegration:
    """Run semgrep security scans and score based on findings.

    Score: 1.0 - (errors * 0.15 + warnings * 0.05), clamped to [0.0, 1.0].
    Feeds into: security dimension.
    """

    name = "semgrep"

    def __init__(self) -> None:
        self.targets: list[str] = ["."]
        self.rules: list[str] = ["p/python", "p/owasp-top-ten"]
        self.timeout: int = 120

    def configure(
        self,
        targets: list[str] | None = None,
        rules: list[str] | None = None,
        timeout: int = 120,
        **kwargs: Any,
    ) -> None:
        if targets:
            self.targets = targets
        if rules:
            self.rules = rules
        self.timeout = timeout

    def checks(self) -> dict[str, Any]:
        return {"semgrep_scan": self.scan}

    def scan(self) -> tuple[float, dict[str, Any]]:
        """Run semgrep and return a score based on finding severity."""
        try:
            import json as _json

            cmd = ["semgrep", "--json", "--quiet"]
            for rule in self.rules:
                cmd.extend(["--config", rule])
            cmd.extend(self.targets)

            result = subprocess.run(  # noqa: S603
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            data = _json.loads(result.stdout) if result.stdout else {}
            results = data.get("results", [])

            errors = sum(1 for r in results if r.get("extra", {}).get("severity") == "ERROR")
            warnings = sum(1 for r in results if r.get("extra", {}).get("severity") == "WARNING")
            infos = sum(1 for r in results if r.get("extra", {}).get("severity") == "INFO")

            score = max(0.0, min(1.0, 1.0 - (errors * 0.15 + warnings * 0.05)))

            return score, {
                "errors": errors,
                "warnings": warnings,
                "infos": infos,
                "total_findings": len(results),
            }
        except FileNotFoundError:
            log.warning("semgrep not installed — skipping security scan")
            return 0.5, {"note": "semgrep not installed", "install": "pip install semgrep",
                         "tool_failure": True}
        except Exception as e:
            log.warning("Semgrep scan failed: %s", e)
            return 0.5, {"error": str(e), "tool_failure": True}
