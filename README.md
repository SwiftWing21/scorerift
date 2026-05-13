# ScoreRift

**The product isn't the scoring. It's watching the gap.**

Automated checks exist everywhere. Manual reviews exist everywhere. What doesn't exist is a system that runs both continuously, compares them over time, and alerts you the moment they disagree.

That disagreement — the divergence — is where the real information lives.

```
  LEFT BRAIN (Auto)              RIGHT BRAIN (Manual)
  ─────────────────              ────────────────────
  pytest pass rate    ──┐    ┌── Human grade (A)
  ruff lint score     ──┤    ├── LLM review findings
  semgrep scan        ──┤    ├── User feedback (4.2/5)
  endpoint health     ──┘    └── Team notes
                        │    │
                        ▼    ▼
                   ┌───────────┐
                   │ THE GAP   │  <── this is the product
                   └─────┬─────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
           Aligned    DIVERGED    Failing
           (quiet)    (signal)     (alarm)
```

When both brains agree, everything's fine — move on. When they disagree, something interesting just happened: either reality changed and the reviewer hasn't caught up, or the reviewer sees something the automation can't. Either way, that gap is worth investigating.

## What Divergence Actually Catches

| What happened | Auto says | Manual says | Gap means |
|---------------|-----------|-------------|-----------|
| Tests pass but codebase rotted | A | C+ (stale) | Auto is right. Manual grade expired — reviewer hasn't looked since the refactor. |
| Reviewer bumped grade after "looks good" review | B+ | A | Manual is optimistic. Auto sees real issues the reviewer glossed over. |
| Security vuln in dependency | D | A | Auto caught it. Manual grade was set before the CVE dropped. |
| "Feels slow" but metrics are fine | A | B- | Manual is right. Users feel something automation can't measure. |
| Big refactor, nothing broke | A | B (cautious) | Auto is right. Reviewer is still nervous from the refactor but tests confirm it's solid. |
| Compliance review happened | B+ | A (with notes) | Manual is right. External auditor validated things auto can't check. |

**None of these are caught by running either brain alone.** The signal is in the disagreement.

## Quick Start

```bash
pip install scorerift

scorerift init                      # create DB + baseline sidecar
scorerift register --preset python  # 8 dimensions for Python projects
scorerift run light                 # first scan (~2s)
scorerift status                    # view scores + divergences
```

```
Dimension                  Auto   Grade  Manual  Status
-----------------------------------------------------------------
  test_coverage            0.930      A      —   ok
  lint_score               1.000      S      —   ok
  security                 0.850     A-     A+   DIVERGED
  type_coverage            0.720     B-      —   ok

Overall: A- (0.876)    Divergences: 1
```

That `DIVERGED` on security is the system working. Auto scored 0.85 (A-), but someone manually graded it A+. Who's wrong? That's the conversation worth having.

## How It Works

**Divergence detection** fires when `|auto_score - manual_score| > 0.15` AND auto-confidence is above 50%. Low-confidence dimensions (like UX at 30%) can't trigger divergence — the system doesn't argue with humans until it has enough data to form a real opinion.

**Three resolution paths:**
1. **Update manual grade** — you agree with auto, fix the sidecar
2. **Acknowledge** — you disagree with auto, dismiss the alert (visible but dimmed)
3. **Re-audit** — run a deeper tier or request an LLM review for a second opinion

**Ratchet rules** prevent silent regression: set a floor grade, and if the score drops below it, the system flags it. Ratchets are advisory — they warn, not block.

**Six defense layers** prevent the system from lying to you:

| Layer | What it catches |
|-------|----------------|
| Functional test scoring | Grade inflation (scores from tests, not file existence) |
| Grade expiry | Stale optimism (old manual grades display as expired) |
| Cross-validation | Optimistic reviewers (divergence when manual >> auto) |
| Git diff detection | Silent drift (code changed since last manual review) |
| External scanners | Blind spots (semgrep, PyPI drift — independent signals) |
| Ratchet rules | Backsliding (score can't drop below target without explicit edit) |

## The Python Preset (8 real checks, 0 stubs)

| Dimension | What it runs | Confidence |
|-----------|-------------|------------|
| test_coverage | `pytest` pass rate | 95% |
| lint_score | `ruff check` error count | 90% |
| type_coverage | `mypy` error count | 85% |
| dep_freshness | `pip list --outdated` | 85% |
| doc_coverage | AST docstring ratio + README existence | 80% |
| security | semgrep SAST or ruff S rules (fallback) | 60% |
| complexity | radon or AST McCabe analysis (fallback) | 80% |
| import_hygiene | `ruff check --select I,F401` | 85% |

Every check handles missing tools gracefully (returns 0.5 with a note, not a crash). Confidence determines how much weight divergence detection gives each dimension.

## Wrap Your Existing Tools

ScoreRift doesn't replace your tooling. It sits on top of it.

A dimension's `check` is just `Callable[[], tuple[float, dict]]`. That callable can hit any API, parse any CLI output, or query any system. The framework doesn't care where the score comes from — it just needs a number between 0 and 1, and a detail dict.

```python
# Wrap SonarQube's quality gate
def sonarqube_gate():
    resp = requests.get(f"{SONAR_URL}/api/qualitygates/project_status",
                        params={"projectKey": PROJECT}, timeout=10)
    data = resp.json()["projectStatus"]
    return (1.0 if data["status"] == "OK" else 0.4, data)

# Wrap Datadog SLO
def datadog_slo():
    resp = requests.get(f"{DD_URL}/api/v1/slo/{SLO_ID}",
                        headers={"DD-API-KEY": KEY}, timeout=10)
    sli = resp.json()["data"]["overall_status"][0]["sli_value"]
    return (sli / 100.0, {"sli": sli})

# Wrap any CLI tool
def pylint_score():
    result = subprocess.run(["pylint", "src/", "--output-format=json"],
                            capture_output=True, text=True, timeout=120)
    data = json.loads(result.stdout)
    score = max(0.0, (10 - len(data)) / 10)  # normalize to 0-1
    return (score, {"issues": len(data)})

engine.register(Dimension(name="sonarqube", check=sonarqube_gate, confidence=0.9, tier=Tier.DAILY))
engine.register(Dimension(name="slo_compliance", check=datadog_slo, confidence=0.95, tier=Tier.LIGHT))
engine.register(Dimension(name="pylint", check=pylint_score, confidence=0.85, tier=Tier.MEDIUM))
```

This reframes the entire project: not "alternative to SonarQube" but **"the layer that watches whether SonarQube and your team's manual assessment still agree."** Use the presets to get started, then wire in whatever tools your team already runs.

## LLM-Powered Reviews (The Right Brain On Demand)

The manual grade doesn't have to come from you. Point an LLM at any dimension and get a structured review with cross-validated findings.

**Three review modes:**

| Mode | What it does | API calls | Best for |
|------|-------------|-----------|----------|
| **Single** | One provider, one pass | 1 | Quick sanity check |
| **Swarm** | One provider, 4 specialized lenses (security auditor, performance engineer, architect, compliance auditor) — findings cross-validated | 4 | Deep single-dimension review |
| **Consensus** | Same prompt to Claude + Gemini + OpenAI, compare scores | 1 per provider | When you want multiple opinions |

**Cost scales with context size.** The system prompt is ~200 tokens. Your cost is driven by how much code/context you pass in:

| Context size | Sonnet (single) | Sonnet (swarm, 4 lenses) | Flash + 4o-mini (consensus) |
|-------------|-----------------|--------------------------|----------------------------|
| ~1K tokens (one file) | ~$0.005 | ~$0.02 | ~$0.002 |
| ~10K tokens (module) | ~$0.05 | ~$0.20 | ~$0.01 |
| ~50K tokens (small repo) | ~$0.20 | ~$0.80 | ~$0.05 |

Every review logs exact input/output tokens and cost in the DB. Use `cache.stats()` to see cumulative spend. Cached reviews (7-day TTL) cost nothing on repeat runs.

```python
# Trigger a swarm review — 4 lenses review independently, then cross-validate
result = engine.review_dimension("security", context=source_code, mode="swarm")
# result["cross_validated"] = findings 2+ lenses agree on (high confidence)
# result["single_source"] = findings from only 1 lens (investigate)

# Multi-provider consensus — do Claude and Gemini agree?
result = engine.review_dimension("architecture", context=source_code, mode="consensus")
# result["agreement"] = 0.92 (they mostly agree)
# result["provider_results"]["claude"]["grade"] = "A"
# result["provider_results"]["gemini"]["grade"] = "A-"
```

The review result automatically updates the sidecar with `source: "llm_review"`. Now you have **three layers of gap detection**:
1. Auto score vs manual grade (original divergence)
2. LLM review vs auto score (does the model see something automation missed?)
3. LLM review vs LLM review (do Claude and Gemini disagree? That's a signal too)

**Swarm lenses** are where the magic happens. Four specialized reviewers look at the same code from different angles — a security auditor catches different things than a performance engineer. Findings that appear in 2+ lenses are **cross-validated** (high confidence). Findings from only one lens are flagged as single-source (investigate, but lower confidence).

**Built-in cost safety:**
- Local result cache (7-day TTL) — same context + same provider = cached, no API call
- All costs tracked per review in the DB
- Providers that aren't configured (no API key) are silently skipped

```bash
# Configure providers via environment variables
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=AI...
export OPENAI_API_KEY=sk-...
# Any combination works — uses whichever keys are available
```

## Web Dashboard

```bash
pip install scorerift[dashboard]
scorerift dashboard                 # http://localhost:8484/audit/
scorerift dashboard --native        # PyWebView native window
```

Grade ring, score bars, divergence alerts, tier triggers, feedback widget, review tracking. Self-contained HTML, zero CDN dependencies.

**[Full walkthrough with examples &#8594; docs/QUICKSTART.md](docs/QUICKSTART.md)**

## Python API

```python
from scorerift import AuditEngine, Dimension, Tier

engine = AuditEngine(db_path="audit.db", baseline_path="audit_baseline.json")

engine.register(Dimension(
    name="test_coverage",
    check=lambda: (passed / total, {"passed": passed, "total": total}),
    confidence=0.95,
    tier=Tier.LIGHT,
))

results = engine.run_tier("daily")
health = engine.health_check()  # {"ok": True, "grade": "A", "divergences": 0, ...}

# The interesting part: what do the brains disagree on?
for d in engine.get_divergences():
    print(f"{d.name}: auto={d.auto_score:.2f} vs manual={d.manual_grade}")
```

## CI Integration

```yaml
- name: Audit health check
  run: |
    pip install scorerift
    scorerift health
```

Exit code 0 = aligned. Exit code 1 = divergences or failing dimensions. The JSON output tells you exactly what disagrees and by how much.

## More Presets

| Preset | Dimensions | Best for |
|--------|-----------|----------|
| `python` | 8 real checks | Python repos |
| `api` | 8 dimensions | REST APIs |
| `database` | 7 dimensions | Databases |
| `infrastructure` | 8 dimensions | DevOps |
| `ml_pipeline` | 7 dimensions | ML workflows |

## Dogfooding: TBR Auditing Itself

We ran scorerift on its own codebase. Here's what happened.

**Step 1: Auto-scorer says everything is perfect.**

```
Dimension              Auto  Grade   Status
  testing             1.000      S   ok
  lint                1.000      S   ok
  security            1.000      S   ok
  test_depth          1.000      S   ok
  packaging           1.000      S   ok
  ci                  1.000      S   ok
  documentation       0.920     A+   ok
  type_coverage       0.748      B   ok

Overall: A+ (0.959)
```

Seven S-tier scores. Auto says ship it.

**Step 2: Human reviewer finds real issues.**

A deep code review graded the same dimensions differently:

| Dimension | Auto | Human | Gap |
|-----------|------|-------|-----|
| testing | S (1.0) | A- | Auto counts pass rate. Human found missing DB roundtrip tests, untested reviewer modules. |
| security | S (1.0) | B+ | Auto's ruff S rules found 0 issues. Human found os.chdir thread safety hazard, sidecar path traversal weakness. |
| test_depth | S (1.0) | A- | Auto counts test files per module (8/8). Human noted reviewer modules have zero coverage. |
| lint | S (1.0) | A- | Auto: ruff clean. Human found orphaned functions, inconsistent fallback behavior. |

**Step 3: Divergence detector fires.**

```
Divergences: 4
  testing:    auto=1.000 vs manual=A- (gap=0.150)
  lint:       auto=1.000 vs manual=A- (gap=0.150)
  security:   auto=1.000 vs manual=B+ (gap=0.200)
  test_depth: auto=1.000 vs manual=A- (gap=0.150)
```

**Step 4: Fix the real issues.**

The divergences pointed to 10 concrete fixes: thread safety lock on CWD changes, atomic sidecar writes, consistent error fallbacks, missing test coverage, orphaned reconciler functions. All fixed in v0.4.0, tests went from 99 to 117.

**The auto-scorer was wrong.** Not because it's broken — it correctly measured what it measures (pass rate, lint errors, file counts). But those measurements missed real issues that only a reviewer could see. Without the divergence detection, we would have shipped with a thread-safety bug.

This is the entire product thesis in one example: **neither brain alone is sufficient.**

## Docs

- **[Quickstart Guide](docs/QUICKSTART.md)** — step-by-step with examples
- **[Standards Reference](docs/STANDARDS.md)** — what we measure and why (OWASP, SRE, DORA, Clean Code, etc.)
- **[Architecture](docs/ARCHITECTURE.md)** — design decisions and data flow
- **[examples/biged/](examples/biged/)** — 12-dimension reference implementation

## Desktop GUI

[ScoreRift Studio](https://github.com/mbachaud/scorerift-studio) — native desktop app for configuring, running, and reviewing audits without the CLI. Open any folder, pick a preset, run audits, edit manual grades, export reports.

## Origin

Extracted from [BigEd CC](https://github.com/mbachaud/Education) after production use on a 125-skill AI fleet with 12 audit dimensions, 4 tiers, and automated daily/weekly scheduling. The divergence detection pattern caught real issues that neither automated tests nor manual reviews caught alone.

## License

Apache-2.0 — see [LICENSE](LICENSE). Copyright 2025-2026 Michael Bachaud (mbachaud).
