# Standards Reference

What the scorerift dimensions measure, and which external standards, frameworks, and research inform each one.

---

## Dimension → Standards Map

| Dimension | Standards & Frameworks | What we check |
|-----------|----------------------|---------------|
| **Testing** | pytest, GitHub Actions CI | Test pass rate, CI pipeline status |
| **Lint / Code Quality** | Ruff (PEP 8, pyflakes, isort), Clean Code | Zero lint errors, no bare `except:`, no raw DB access |
| **Type Coverage** | PEP 484, PEP 561 (py.typed), mypy | Annotation ratio, py.typed marker |
| **Security** | OWASP Top 10, CWE, semgrep SAST | Vulnerability scan, secret detection, path traversal, RBAC |
| **Documentation** | README-driven development | Key files exist, README has expected sections |
| **Packaging** | PyPA standards, PEP 621 | pyproject.toml completeness (name, version, license, classifiers, URLs) |
| **Architecture** | Clean Code (Martin), LOC thresholds | File size limits (~1500 LOC), modular decomposition |
| **Reliability** | Circuit Breaker (Nygard), SRE principles | Agent health, breaker state, dependency freshness |
| **Observability** | Google SRE Book, structured logging | Health endpoints, audit trail, SSE broadcasting |
| **Performance** | SLA/SLO practices | Endpoint latency (p95), availability ratio |
| **Usability/UX** | User feedback aggregation | Page load success, star ratings, NPS-style scoring |
| **Data/HITL** | Human-in-the-loop ML practices | Annotation queue health, ingest source availability |

---

## Standards Detail

### OWASP Top 10 (Security)

The [OWASP Top 10](https://owasp.org/www-project-top-ten/) is the industry standard for web application security risks. We check for:

- **A01: Broken Access Control** — path traversal tests, RBAC role enforcement
- **A02: Cryptographic Failures** — no hardcoded secrets (API keys, tokens, passwords)
- **A03: Injection** — SQL injection via semgrep `p/sql-injection` ruleset
- **A07: Authentication Failures** — session token handling, secure cookie flags

Automated via semgrep with rulesets: `p/python`, `p/owasp-top-ten`, `p/sql-injection`.

### CWE (Common Weakness Enumeration)

Implicit in semgrep rules. Key CWEs covered:
- CWE-89: SQL Injection
- CWE-94/95: Code Injection
- CWE-798: Hardcoded Credentials
- CWE-22: Path Traversal

### Ruff Lint Rules (Code Quality)

[Ruff](https://docs.astral.sh/ruff/) enforces Python code quality via fast AST analysis:

| Rule set | What it catches |
|----------|----------------|
| E/W (pycodestyle) | Style violations, whitespace |
| F (pyflakes) | Unused imports, undefined names |
| I (isort) | Import ordering |
| UP (pyupgrade) | Python version modernization |
| S (bandit) | Security anti-patterns |
| B (bugbear) | Likely bugs, design problems |
| SIM (simplify) | Unnecessary complexity |
| TCH (type-checking) | Runtime vs type-checking imports |

### PEP 484 / PEP 561 (Type Coverage)

- **PEP 484**: Type hints for Python functions and variables
- **PEP 561**: `py.typed` marker file declaring a package supports type checking
- **mypy**: Static type checker that validates annotations

We score: 50% for `py.typed` presence + 50% for annotation ratio across all functions.

### PEP 621 / PyPA (Packaging)

[PEP 621](https://peps.python.org/pep-0621/) standardizes `pyproject.toml` metadata. We check 10 fields:

1. `name` — package identifier
2. `version` — semantic version
3. `description` — one-line summary
4. `license` — SPDX license identifier
5. `requires-python` — minimum Python version
6. `readme` — points to README.md
7. `[project.scripts]` — CLI entry points
8. `classifiers` — PyPI trove classifiers
9. `[project.urls]` — homepage, repo, issues
10. `[project.optional-dependencies]` — extras (dashboard, dev, etc.)

### Clean Code / LOC Thresholds (Architecture)

Inspired by Robert C. Martin's *Clean Code* and general industry practice:

- **File size limit**: ~1500 LOC per module. Beyond this, decomposition is warranted.
- **Single responsibility**: Each module should have one clear purpose.
- **No raw infrastructure access**: Database queries go through a DAL, not raw `sqlite3.connect()`.

### Circuit Breaker Pattern (Reliability)

From Michael Nygard's *Release It!* — the circuit breaker prevents cascading failures:

- **Closed**: Normal operation, requests pass through
- **Open**: Too many failures, requests short-circuit to fallback
- **Half-open**: Testing if the downstream has recovered

We score: `closed_breakers / total_breakers`.

### PyPI Dependency Drift (Reliability)

Version drift scoring per package:

| Distance | Score | Risk |
|----------|-------|------|
| Up to date | 1.0 | None |
| Patch behind | 1.0 | Negligible |
| Minor behind | 0.5 | Moderate — may miss features or fixes |
| Major behind | 0.0 | High — likely breaking changes, security patches missed |

### Google SRE Principles (Observability, Performance)

From the [Google SRE Book](https://sre.google/sre-book/table-of-contents/):

- **Health endpoints**: Kubernetes-style liveness/readiness probes (`/api/health`)
- **Structured logging**: Machine-parseable JSON log format
- **SLI/SLO tracking**: Latency measurement feeds performance scoring
- **Error budgets**: Ratchet rules act as informal error budgets (score can't drop below floor)

### DORA Metrics (Planned)

The [DORA](https://dora.dev/) four key metrics are not yet formally scored but are on the roadmap:

| Metric | Maps to | Status |
|--------|---------|--------|
| Deployment Frequency | CI dimension | Partially (CI pass/fail tracked) |
| Lead Time for Changes | — | Not yet measured |
| Change Failure Rate | Testing dimension | Partially (test pass rate) |
| Mean Time to Recovery | Reliability dimension | Not yet measured |

### User Feedback (Usability/UX)

The UX dimension is unique — it's the only one where auto-confidence *scales with feedback volume*:

```
confidence = min(0.75, 0.30 + (feedback_count / 100) * 0.45)
```

At 0 feedback entries, confidence is 0.30 (too low to trigger divergence). At 100+ entries, confidence reaches 0.75 — enough to meaningfully compare with a manual grade.

This prevents the system from overriding human UX judgment until it has enough data to form a real opinion.

---

## The Six-Layer Defense Stack

These layers work together to prevent both false positives (flagging something that's fine) and false negatives (missing real issues):

| Layer | What it does | What it catches |
|-------|-------------|-----------------|
| 1. Functional test scoring | Score from actual tests, not file existence | Grade inflation |
| 2. Grade expiry | Manual grades expire after N days if flagged | Stale optimism |
| 3. Divergence check | Manual exceeds auto by >0.15 (untuned default) | Optimistic reviewers |
| 4. Git diff detection | Flags unreviewed changes since last manual grade | Silent drift |
| 5. External scanners | Independent signals (semgrep, PyPI, GitHub) | Blind spots |
| 6. Ratchet rules | Score can't drop below floor without explicit edit | Backsliding |

**Residual risk**: All 6 layers agree on a wrong answer simultaneously. This requires: functional tests pass + manual reviewer agrees + git shows no changes + external scanner misses it. Near-zero probability.

---

## References

- [OWASP Top 10 (2021)](https://owasp.org/www-project-top-ten/)
- [CWE - Common Weakness Enumeration](https://cwe.mitre.org/)
- [Semgrep Rules Registry](https://semgrep.dev/r)
- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [PEP 484 — Type Hints](https://peps.python.org/pep-0484/)
- [PEP 561 — Distributing Type Information](https://peps.python.org/pep-0561/)
- [PEP 621 — Project Metadata](https://peps.python.org/pep-0621/)
- [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [DORA Metrics](https://dora.dev/)
- Martin, R.C. *Clean Code* (2008) — file size, single responsibility
- Nygard, M. *Release It!* (2007, 2nd ed. 2018) — circuit breaker pattern
- [pytest Documentation](https://docs.pytest.org/)
- [mypy Documentation](https://mypy.readthedocs.io/)

---

## API Key Safety

1. **Environment variables only** -- API keys are read from `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, and `OPENAI_API_KEY` environment variables. Never store keys in config files or source code.

2. **`__repr__` masks keys automatically** -- All provider classes (`ClaudeProvider`, `GeminiProvider`, `OpenAIProvider`) implement `__repr__` that shows only the first 8 and last 4 characters of the key. Short keys display as `***`. This prevents accidental key leakage in logs, tracebacks, and REPL output.

3. **Key format validation** -- Each provider logs a warning at initialization if the API key does not match the expected prefix (`sk-ant-` for Claude, `AI` for Gemini, `sk-` for OpenAI). This catches misconfigured environment variables early without blocking execution.

4. **`raw_response` disabled by default** -- Provider classes have `store_raw = False` by default. LLM response text is only stored in `ReviewResult.raw_response` when `store_raw` is explicitly set to `True`. This reduces the amount of potentially sensitive project code retained in memory and cache.

5. **`BudgetGuard` caps per-session spend** -- The `BudgetGuard` class enforces a configurable USD ceiling (default: $1.00) per session. Pass it to `consensus_review(budget=...)` to skip providers when the budget is exhausted. Call `budget.remaining` to check how much is left.

6. **Review cache is local only** -- The `review_cache` SQLite table stores findings that may reference project code snippets and file paths. This data is stored in a local SQLite database only and is never transmitted to external services.
