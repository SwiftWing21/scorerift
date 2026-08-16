"""Tests for integration modules with mocked HTTP/subprocess."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from scorerift.integrations.github import GitHubIntegration
from scorerift.integrations.ollama import OllamaIntegration
from scorerift.integrations.pypi import PyPIIntegration
from scorerift.integrations.semgrep import SemgrepIntegration

# ── GitHub ──────────────────────────────────────────────────────────


class TestGitHubIntegration:
    def _configured(self) -> GitHubIntegration:
        gh = GitHubIntegration()
        gh.configure(token="ghp_test123", repo="owner/repo")  # noqa: S106
        return gh

    def test_ci_status_success(self):
        gh = self._configured()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "workflow_runs": [
                {"id": 42, "conclusion": "success", "html_url": "https://github.com/runs/42"}
            ]
        }
        mock_resp.headers = {"X-RateLimit-Remaining": "100"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            score, detail = gh.check_ci_status()
        assert score == 1.0
        assert detail["conclusion"] == "success"
        assert detail["run_id"] == 42

    def test_ci_status_failure(self):
        gh = self._configured()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "workflow_runs": [
                {"id": 99, "conclusion": "failure", "html_url": "https://github.com/runs/99"}
            ]
        }
        mock_resp.headers = {"X-RateLimit-Remaining": "100"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            score, detail = gh.check_ci_status()
        assert score == 0.0
        assert detail["conclusion"] == "failure"

    def test_open_bugs_score(self):
        gh = self._configured()
        # 5 bugs -> score = 1.0 - 5*0.05 = 0.75
        bugs = [{"id": i, "title": f"bug {i}"} for i in range(5)]
        mock_resp = MagicMock()
        mock_resp.json.return_value = bugs
        mock_resp.headers = {"X-RateLimit-Remaining": "100"}
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_resp):
            score, detail = gh.check_open_bugs()
        assert score == 0.75
        assert detail["open_bugs"] == 5

    def test_missing_token_returns_half(self):
        gh = GitHubIntegration()
        # Not configured — no token, no repo
        score, detail = gh.check_ci_status()
        assert score == 0.5
        assert "not configured" in detail["note"].lower()

    def test_missing_repo_returns_half(self):
        gh = GitHubIntegration()
        gh.configure(token="ghp_test", repo=None)  # noqa: S106
        score, detail = gh.check_open_bugs()
        assert score == 0.5


# ── Ollama ──────────────────────────────────────────────────────────


class TestOllamaIntegration:
    def test_health_with_models(self):
        oll = OllamaIntegration()
        payload = json.dumps({"models": [{"name": "qwen3:8b"}, {"name": "llama3:8b"}]}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            score, detail = oll.check_health()
        assert score == 1.0
        assert detail["models"] == 2

    def test_health_no_models(self):
        oll = OllamaIntegration()
        payload = json.dumps({"models": []}).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = payload
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            score, detail = oll.check_health()
        assert score == 0.0
        assert "no models" in detail["note"].lower()

    def test_health_connection_error(self):
        oll = OllamaIntegration()
        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
            score, detail = oll.check_health()
        assert score == 0.0
        assert "error" in detail

    def test_connection_error_is_evidence_not_tool_failure(self):
        """Unreachable Ollama is the check's documented failing verdict (0.0),
        not a tool failure — it must never carry the tool_failure sentinel."""
        oll = OllamaIntegration()
        with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
            score, detail = oll.check_health()
        assert score == 0.0
        assert "tool_failure" not in detail


# ── PyPI ────────────────────────────────────────────────────────────


class TestPyPIVersionScore:
    def test_same_version(self):
        assert PyPIIntegration._version_score("1.2.3", "1.2.3") == 1.0

    def test_patch_behind(self):
        assert PyPIIntegration._version_score("1.2.3", "1.2.5") == 1.0

    def test_minor_behind(self):
        assert PyPIIntegration._version_score("1.2.3", "1.4.0") == 0.5

    def test_major_behind(self):
        assert PyPIIntegration._version_score("1.2.3", "2.0.0") == 0.0

    def test_malformed_returns_half(self):
        assert PyPIIntegration._version_score("bad", "1.0.0") == 0.5

    def test_short_versions(self):
        # "1.0" vs "1.1" -> minor behind
        assert PyPIIntegration._version_score("1.0", "1.1") == 0.5


# ── Semgrep ─────────────────────────────────────────────────────────


class TestSemgrepIntegration:
    def test_not_installed_returns_half(self):
        sg = SemgrepIntegration()
        with patch("subprocess.run", side_effect=FileNotFoundError("semgrep")):
            score, detail = sg.scan()
        assert score == 0.5
        assert "not installed" in detail["note"]

    def test_not_installed_is_tool_failure(self):
        """A missing semgrep binary is absence of evidence — the neutral 0.5
        must carry the tool_failure sentinel so it cannot fail health."""
        sg = SemgrepIntegration()
        with patch("subprocess.run", side_effect=FileNotFoundError("semgrep")):
            score, detail = sg.scan()
        assert detail["tool_failure"] is True

    def test_scan_with_findings(self):
        sg = SemgrepIntegration()
        findings = {
            "results": [
                {"extra": {"severity": "ERROR"}},
                {"extra": {"severity": "ERROR"}},
                {"extra": {"severity": "WARNING"}},
                {"extra": {"severity": "INFO"}},
            ]
        }
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = json.dumps(findings)
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            score, detail = sg.scan()
        # score = 1.0 - (2*0.15 + 1*0.05) = 1.0 - 0.35 = 0.65
        assert score == 0.65
        assert detail["errors"] == 2
        assert detail["warnings"] == 1
        assert detail["infos"] == 1
        assert detail["total_findings"] == 4

    def test_scan_clean(self):
        sg = SemgrepIntegration()
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = json.dumps({"results": []})
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result):
            score, detail = sg.scan()
        assert score == 1.0
        assert detail["total_findings"] == 0
