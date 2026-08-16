"""Preset dimensions for generic Python projects.

8 dimensions: 3 existing (pytest, ruff, mypy) + 5 newly implemented
(dep freshness, doc coverage, security, complexity, import hygiene).
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from pathlib import Path

from scorerift import Dimension, Tier
from scorerift.presets._check_utils import run_tool, tool_available

# Full-suite runs on real projects routinely take several minutes; 120s
# produced false timeouts. Override via SCORERIFT_PYTEST_TIMEOUT.
DEFAULT_PYTEST_TIMEOUT = 600


def _pytest_timeout() -> int:
    raw = os.environ.get("SCORERIFT_PYTEST_TIMEOUT", "")
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_PYTEST_TIMEOUT
    return value if value > 0 else DEFAULT_PYTEST_TIMEOUT


# ── Check functions ──────────────────────────────────────────────────

def _check_test_coverage() -> tuple[float, dict]:
    """Run pytest and return pass rate.

    SCORERIFT_PYTEST_TIMEOUT overrides the suite timeout (seconds);
    SCORERIFT_PYTEST_MARKERS passes a `-m` marker expression (e.g. "not slow").
    """
    cmd = ["python", "-m", "pytest", "--tb=no", "-q"]
    markers = os.environ.get("SCORERIFT_PYTEST_MARKERS")
    if markers:
        cmd += ["-m", markers]
    try:
        result = run_tool(cmd, timeout=_pytest_timeout())  # noqa: S607
        passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", result.stdout)) else 0
        failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", result.stdout)) else 0
        total = passed + failed
        return (passed / total if total else 0.0), {"passed": passed, "failed": failed, "total": total}
    except subprocess.TimeoutExpired as e:
        return 0.5, {"error": str(e), "timeout": True, "tool_failure": True}
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


def _check_lint_score() -> tuple[float, dict]:
    """Run ruff and score based on error count."""
    if not tool_available("ruff"):
        return 0.5, {"note": "ruff not installed", "tool_failure": True}
    try:
        result = run_tool(["ruff", "check", ".", "--statistics", "-q"], timeout=60)  # noqa: S607
        if result.returncode == 0:
            return 1.0, {"errors": 0}
        errors = len([ln for ln in result.stdout.strip().splitlines() if ln.strip()])
        score = max(0.0, 1.0 - errors * 0.02)
        return score, {"errors": errors}
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


def _check_type_coverage() -> tuple[float, dict]:
    """Run mypy and score based on error count."""
    if not tool_available("mypy"):
        return 0.5, {"note": "mypy not installed", "tool_failure": True}
    try:
        result = run_tool(["mypy", ".", "--no-error-summary"], timeout=120)  # noqa: S607
        if result.returncode == 0:
            return 1.0, {"errors": 0}
        errors = len(result.stdout.strip().splitlines())
        score = max(0.0, 1.0 - errors * 0.01)
        return score, {"errors": errors}
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


def _check_dep_freshness() -> tuple[float, dict]:
    """Check for outdated dependencies via pip."""
    try:
        result = run_tool(["pip", "list", "--outdated", "--format=json"], timeout=30)  # noqa: S607
        if result.returncode != 0:
            return 0.5, {"note": "pip list failed", "stderr": result.stderr[:200], "tool_failure": True}
        outdated = json.loads(result.stdout) if result.stdout.strip() else []
        total_pkgs = len(json.loads(
            run_tool(["pip", "list", "--format=json"], timeout=15).stdout  # noqa: S607
        )) if result.stdout else 1
        if not outdated:
            return 1.0, {"outdated": 0, "total": total_pkgs}
        # Score: 1.0 when none outdated, drops with each outdated package
        score = max(0.0, 1.0 - len(outdated) * 0.05)
        top5 = [{"name": p["name"], "current": p.get("version", "?"),
                 "latest": p.get("latest_version", "?")} for p in outdated[:5]]
        return score, {"outdated": len(outdated), "total": total_pkgs, "top5": top5}
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


def _check_doc_coverage() -> tuple[float, dict]:
    """Check docstring coverage using AST analysis + README existence."""
    try:
        cwd = Path(".")
        py_files = list(cwd.rglob("*.py"))
        # Filter out tests, venv, hidden dirs
        py_files = [f for f in py_files if not any(
            p in f.parts for p in ("venv", ".venv", "env", "__pycache__", ".git", "node_modules")
        )]

        total_items = 0
        documented = 0
        for fpath in py_files:
            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    # Skip private/dunder methods
                    if node.name.startswith("_") and not node.name.startswith("__"):
                        continue
                    total_items += 1
                    if ast.get_docstring(node):
                        documented += 1

        doc_ratio = documented / total_items if total_items else 0.0

        # Check README exists and has content
        readme_exists = any((cwd / name).exists() for name in ("README.md", "README.rst", "README.txt", "README"))
        readme_score = 1.0 if readme_exists else 0.0

        # 70% docstring ratio + 30% README
        score = 0.7 * doc_ratio + 0.3 * readme_score
        return score, {
            "documented": documented,
            "total": total_items,
            "ratio": round(doc_ratio, 3),
            "readme_exists": readme_exists,
            "files_scanned": len(py_files),
        }
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


def _check_security() -> tuple[float, dict]:
    """Run security checks — semgrep if available, else ruff S rules."""
    try:
        # Try semgrep first (more thorough)
        if tool_available("semgrep"):
            result = run_tool(
                ["semgrep", "--json", "--quiet", "--config", "p/python", "--config", "p/owasp-top-ten", "."],  # noqa: S607
                timeout=120,
            )
            if result.stdout.strip():
                data = json.loads(result.stdout)
                findings = data.get("results", [])
                errors = sum(1 for r in findings if r.get("extra", {}).get("severity") == "ERROR")
                warnings = sum(1 for r in findings if r.get("extra", {}).get("severity") == "WARNING")
                score = max(0.0, min(1.0, 1.0 - (errors * 0.15 + warnings * 0.05)))
                return score, {"tool": "semgrep", "errors": errors, "warnings": warnings, "total": len(findings)}

        # Fallback: ruff security rules
        if tool_available("ruff"):
            result = run_tool(["ruff", "check", ".", "--select", "S", "--statistics", "-q"], timeout=60)  # noqa: S607
            if result.returncode == 0:
                return 1.0, {"tool": "ruff-S", "findings": 0}
            findings = len([ln for ln in result.stdout.strip().splitlines() if ln.strip()])
            score = max(0.0, 1.0 - findings * 0.05)
            return score, {"tool": "ruff-S", "findings": findings}

        return 0.5, {"note": "Neither semgrep nor ruff available for security scanning", "tool_failure": True}
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


def _check_complexity() -> tuple[float, dict]:
    """Check code complexity — radon if available, else AST-based."""
    try:
        # Try radon first
        if tool_available("radon"):
            result = run_tool(["radon", "cc", ".", "-a", "-j"], timeout=60)  # noqa: S607
            if result.stdout.strip():
                data = json.loads(result.stdout)
                # Radon JSON: {filename: [{complexity: int, rank: str}, ...]}
                all_ranks = []
                for blocks in data.values():
                    if isinstance(blocks, list):
                        for block in blocks:
                            if isinstance(block, dict) and "rank" in block:
                                all_ranks.append(block["rank"])
                if all_ranks:
                    rank_scores = {"A": 1.0, "B": 0.85, "C": 0.65, "D": 0.45, "E": 0.25, "F": 0.1}
                    avg = sum(rank_scores.get(r, 0.5) for r in all_ranks) / len(all_ranks)
                    rank_counts = {}
                    for r in all_ranks:
                        rank_counts[r] = rank_counts.get(r, 0) + 1
                    return avg, {"tool": "radon", "functions": len(all_ranks), "ranks": rank_counts}

        # Fallback: AST-based McCabe counting (simplified)
        cwd = Path(".")
        py_files = [f for f in cwd.rglob("*.py") if not any(
            p in f.parts for p in ("venv", ".venv", "__pycache__", ".git")
        )]
        complexities = []
        for fpath in py_files:
            try:
                tree = ast.parse(fpath.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Count decision points (if, for, while, and, or, except, with)
                    cc = 1
                    for child in ast.walk(node):
                        if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With)):
                            cc += 1
                        elif isinstance(child, ast.BoolOp):
                            cc += len(child.values) - 1
                    complexities.append(cc)

        if not complexities:
            return 0.5, {"note": "No functions found to analyze"}

        avg_cc = sum(complexities) / len(complexities)
        # Score: avg CC of 1-5 = great (1.0), 5-10 = good (0.8), 10-20 = ok (0.6), 20+ = bad
        if avg_cc <= 5:
            score = 1.0
        elif avg_cc <= 10:
            score = 0.85
        elif avg_cc <= 20:
            score = 0.65
        else:
            score = max(0.3, 1.0 - avg_cc * 0.02)

        return score, {
            "tool": "ast",
            "functions": len(complexities),
            "avg_complexity": round(avg_cc, 2),
            "max_complexity": max(complexities),
        }
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


def _check_import_hygiene() -> tuple[float, dict]:
    """Check for import order violations and unused imports via ruff."""
    if not tool_available("ruff"):
        return 0.5, {"note": "ruff not installed", "tool_failure": True}
    try:
        result = run_tool(
            ["ruff", "check", ".", "--select", "I,F401", "--statistics", "-q"],  # noqa: S607
            timeout=60,
        )
        if result.returncode == 0:
            return 1.0, {"violations": 0}
        violations = len([ln for ln in result.stdout.strip().splitlines() if ln.strip()])
        score = max(0.0, 1.0 - violations * 0.03)
        return score, {"violations": violations}
    except Exception as e:
        return 0.5, {"error": str(e), "tool_failure": True}


# ── Dimension Definitions ────────────────────────────────────────────

PYTHON_DIMENSIONS: list[Dimension] = [
    Dimension(
        name="test_coverage",
        check=_check_test_coverage,
        confidence=0.95,
        tier=Tier.LIGHT,
        description="Test pass rate from pytest",
    ),
    Dimension(
        name="lint_score",
        check=_check_lint_score,
        confidence=0.90,
        tier=Tier.LIGHT,
        description="Code lint quality via ruff",
    ),
    Dimension(
        name="type_coverage",
        check=_check_type_coverage,
        confidence=0.85,
        tier=Tier.MEDIUM,
        description="Type annotation coverage via mypy",
    ),
    Dimension(
        name="dep_freshness",
        check=_check_dep_freshness,
        confidence=0.85,
        tier=Tier.WEEKLY,
        description="Dependency version freshness via pip",
    ),
    Dimension(
        name="doc_coverage",
        check=_check_doc_coverage,
        confidence=0.80,
        tier=Tier.MEDIUM,
        description="Docstring coverage + README existence",
    ),
    Dimension(
        name="security",
        check=_check_security,
        confidence=0.60,
        tier=Tier.WEEKLY,
        description="Security scanning via semgrep or ruff S rules",
    ),
    Dimension(
        name="complexity",
        check=_check_complexity,
        confidence=0.80,
        tier=Tier.MEDIUM,
        description="Code complexity via radon or AST analysis",
    ),
    Dimension(
        name="import_hygiene",
        check=_check_import_hygiene,
        confidence=0.85,
        tier=Tier.LIGHT,
        description="Import ordering and unused import violations",
    ),
]
