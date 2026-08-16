"""Tests for preset dimension configurations."""

import subprocess

import pytest

from scorerift import Dimension
from scorerift.presets import PRESETS, python_project


class TestPresetsStructure:
    def test_all_presets_exist(self):
        expected = {"python", "api", "database", "infrastructure", "ml_pipeline"}
        assert set(PRESETS.keys()) == expected

    def test_all_presets_return_dimension_lists(self):
        for name, dims in PRESETS.items():
            assert isinstance(dims, list), f"{name} is not a list"
            for d in dims:
                assert isinstance(d, Dimension), f"{name} contains non-Dimension: {type(d)}"

    def test_python_has_8_dimensions(self):
        assert len(PRESETS["python"]) == 8

    def test_dimension_names_unique_per_preset(self):
        for preset_name, dims in PRESETS.items():
            names = [d.name for d in dims]
            assert len(names) == len(set(names)), f"Duplicate names in {preset_name}"

    def test_all_dimensions_have_check(self):
        for preset_name, dims in PRESETS.items():
            for d in dims:
                assert callable(d.check), f"{preset_name}.{d.name} check is not callable"

    def test_all_dimensions_have_tier(self):
        from scorerift.tiers import Tier
        for preset_name, dims in PRESETS.items():
            for d in dims:
                assert isinstance(d.tier, Tier), f"{preset_name}.{d.name} tier is not Tier"

    def test_confidence_in_range(self):
        for preset_name, dims in PRESETS.items():
            for d in dims:
                assert 0.0 <= d.confidence <= 1.0, f"{preset_name}.{d.name} confidence out of range"


class _FakePytestResult:
    stdout = "5 passed in 1.23s"
    stderr = ""
    returncode = 0


class TestCheckFailureNeutrality:
    """A tool failure is absence of evidence, not evidence of failure.

    Checks must return a neutral 0.5 (matching AuditEngine's own exception
    fallback), never 0.0, when the tool itself times out or crashes.
    """

    def test_pytest_timeout_returns_neutral_score(self, monkeypatch):
        def fake_run_tool(cmd, timeout=60, cwd=None):
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)
        monkeypatch.setattr(python_project, "run_tool", fake_run_tool)
        score, detail = python_project._check_test_coverage()
        assert score == 0.5
        assert detail["timeout"] is True
        assert "error" in detail
        assert detail["tool_failure"] is True

    def test_pytest_error_returns_neutral_score(self, monkeypatch):
        def fake_run_tool(cmd, timeout=60, cwd=None):
            raise OSError("python not found")
        monkeypatch.setattr(python_project, "run_tool", fake_run_tool)
        score, detail = python_project._check_test_coverage()
        assert score == 0.5
        assert "error" in detail
        assert "timeout" not in detail
        assert detail["tool_failure"] is True

    @pytest.mark.parametrize("check_name", [
        "_check_lint_score",
        "_check_type_coverage",
        "_check_import_hygiene",
    ])
    def test_tool_crash_returns_neutral_score(self, monkeypatch, check_name):
        monkeypatch.setattr(python_project, "tool_available", lambda name: True)

        def fake_run_tool(cmd, timeout=60, cwd=None):
            raise OSError("tool crashed")
        monkeypatch.setattr(python_project, "run_tool", fake_run_tool)
        score, detail = getattr(python_project, check_name)()
        assert score == 0.5, f"{check_name} scored a tool crash as {score}"
        assert "error" in detail
        assert detail["tool_failure"] is True

    def test_doc_coverage_error_returns_neutral_score(self, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("filesystem unavailable")
        monkeypatch.setattr(python_project, "Path", boom)
        score, detail = python_project._check_doc_coverage()
        assert score == 0.5
        assert "error" in detail
        assert detail["tool_failure"] is True


class TestPytestCollectionFailure:
    """pytest exiting without a parseable pass/fail count.

    Exit codes 2/3/4 (interrupted / internal error / usage error, e.g. a
    broken conftest) mean pytest produced no evidence — neutral tool
    failure. Exit code 5 (no tests collected) IS evidence: the project
    has no tests, which legitimately scores 0.0.
    """

    @staticmethod
    def _fake(returncode, stdout=""):
        def fake_run_tool(cmd, timeout=60, cwd=None):
            r = _FakePytestResult()
            r.returncode = returncode
            r.stdout = stdout
            return r
        return fake_run_tool

    @pytest.mark.parametrize("code", [2, 3, 4])
    def test_collection_error_is_tool_failure(self, monkeypatch, code):
        monkeypatch.setattr(python_project, "run_tool",
                            self._fake(code, "ERROR conftest.py ImportError"))
        score, detail = python_project._check_test_coverage()
        assert score == 0.5
        assert detail["tool_failure"] is True
        assert "error" in detail

    def test_no_tests_collected_scores_zero(self, monkeypatch):
        monkeypatch.setattr(python_project, "run_tool",
                            self._fake(5, "no tests ran in 0.01s"))
        score, detail = python_project._check_test_coverage()
        assert score == 0.0
        assert "tool_failure" not in detail
        assert detail["total"] == 0

    def test_no_tests_collected_records_active_marker_filter(self, monkeypatch):
        """Exit 5 with a markers filter active may mean a typo'd expression
        deselected everything — record the expression so the 0.0 is auditable."""
        monkeypatch.setenv("SCORERIFT_PYTEST_MARKERS", "not slwo")
        monkeypatch.setattr(python_project, "run_tool",
                            self._fake(5, "no tests ran in 0.01s"))
        score, detail = python_project._check_test_coverage()
        assert score == 0.0
        assert detail["markers"] == "not slwo"

    def test_exit_zero_but_unparseable_is_tool_failure(self, monkeypatch):
        monkeypatch.setattr(python_project, "run_tool", self._fake(0, "garbage"))
        score, detail = python_project._check_test_coverage()
        assert score == 0.5
        assert detail["tool_failure"] is True


class TestMissingToolNeutrality:
    """A tool that is not installed cannot produce evidence.

    Its neutral 0.5 must carry the tool_failure sentinel so the engine
    zeroes confidence instead of hard-failing health on a bare machine.
    """

    @pytest.mark.parametrize("check_name", [
        "_check_lint_score",
        "_check_type_coverage",
        "_check_security",
        "_check_import_hygiene",
    ])
    def test_missing_tool_is_tool_failure(self, monkeypatch, check_name):
        monkeypatch.setattr(python_project, "tool_available", lambda name: False)
        score, detail = getattr(python_project, check_name)()
        assert score == 0.5
        assert detail["tool_failure"] is True
        assert "note" in detail

    def test_pip_list_failure_is_tool_failure(self, monkeypatch):
        def fake_run_tool(cmd, timeout=60, cwd=None):
            r = _FakePytestResult()
            r.returncode = 1
            r.stderr = "pip exploded"
            return r
        monkeypatch.setattr(python_project, "run_tool", fake_run_tool)
        score, detail = python_project._check_dep_freshness()
        assert score == 0.5
        assert detail["tool_failure"] is True


class TestPytestTimeoutConfig:
    """The pytest timeout must be configurable; 120s is too short for real suites."""

    @pytest.fixture
    def captured(self, monkeypatch):
        calls = {}

        def fake_run_tool(cmd, timeout=60, cwd=None):
            calls["cmd"] = cmd
            calls["timeout"] = timeout
            return _FakePytestResult()
        monkeypatch.setattr(python_project, "run_tool", fake_run_tool)
        monkeypatch.delenv("SCORERIFT_PYTEST_TIMEOUT", raising=False)
        monkeypatch.delenv("SCORERIFT_PYTEST_MARKERS", raising=False)
        return calls

    def test_default_timeout_is_600(self, captured):
        python_project._check_test_coverage()
        assert captured["timeout"] == 600

    def test_env_var_overrides_timeout(self, captured, monkeypatch):
        monkeypatch.setenv("SCORERIFT_PYTEST_TIMEOUT", "333")
        python_project._check_test_coverage()
        assert captured["timeout"] == 333

    def test_invalid_env_var_falls_back_to_default(self, captured, monkeypatch):
        monkeypatch.setenv("SCORERIFT_PYTEST_TIMEOUT", "not-a-number")
        python_project._check_test_coverage()
        assert captured["timeout"] == 600

    @pytest.mark.parametrize("raw", ["0", "-5"])
    def test_nonpositive_env_var_falls_back_to_default(self, captured, monkeypatch, raw):
        monkeypatch.setenv("SCORERIFT_PYTEST_TIMEOUT", raw)
        python_project._check_test_coverage()
        assert captured["timeout"] == 600

    @pytest.mark.parametrize("raw", ["not-a-number", "0"])
    def test_invalid_env_var_logs_warning(self, captured, monkeypatch, caplog, raw):
        monkeypatch.setenv("SCORERIFT_PYTEST_TIMEOUT", raw)
        with caplog.at_level("WARNING", logger="scorerift"):
            python_project._check_test_coverage()
        assert any("SCORERIFT_PYTEST_TIMEOUT" in r.message for r in caplog.records)

    def test_marker_filter_from_env(self, captured, monkeypatch):
        monkeypatch.setenv("SCORERIFT_PYTEST_MARKERS", "not slow")
        python_project._check_test_coverage()
        # Look only past "pytest" — the base cmd is `python -m pytest`.
        args = captured["cmd"][captured["cmd"].index("pytest") + 1:]
        assert "-m" in args
        assert args[args.index("-m") + 1] == "not slow"

    def test_no_marker_filter_by_default(self, captured):
        python_project._check_test_coverage()
        args = captured["cmd"][captured["cmd"].index("pytest") + 1:]
        assert "-m" not in args
