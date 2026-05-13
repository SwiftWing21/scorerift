# Architecture

## Design Philosophy

The ScoreRift system is built on one core insight: **neither automated scoring nor manual review alone is sufficient**. Automated checks catch drift, regressions, and known-bad patterns with high reliability but can't assess "feel" or strategic fit. Manual reviews catch what code can't express, but are subject to optimism bias, staleness, and inconsistency.

The dual-brain pattern combines both and adds **reconciliation with teeth**: when the brains disagree, the system surfaces that disagreement rather than silently choosing a winner.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                     AuditEngine                          │
│                                                          │
│  ┌─────────────┐  ┌───────────┐  ┌──────────────────┐   │
│  │ Dimension    │  │ Sidecar   │  │ Reconciler       │   │
│  │ Registry     │  │ (.json)   │  │                  │   │
│  │              │  │           │  │ divergence       │   │
│  │ check()→     │  │ manual    │  │ detection        │   │
│  │ (score,      │  │ grades    │  │ ratchet check    │   │
│  │  detail)     │  │ ratchets  │  │ weekly merge     │   │
│  │              │  │ feedback  │  │ status classify   │   │
│  └──────┬───────┘  └─────┬─────┘  └────────┬─────────┘   │
│         │                │                  │             │
│         └────────┬───────┘──────────────────┘             │
│                  │                                        │
│         ┌────────▼────────┐                               │
│         │   AuditDB       │                               │
│         │   (SQLite)      │                               │
│         │                 │                               │
│         │ audit_scores    │                               │
│         │ user_feedback   │                               │
│         └─────────────────┘                               │
└──────────────────────────────────────────────────────────┘
         │              │              │
    ┌────▼────┐   ┌─────▼─────┐  ┌────▼────┐
    │  CLI    │   │ Dashboard │  │ Export  │
    │         │   │ (Flask)   │  │ JSON/   │
    │ init    │   │           │  │ CSV/    │
    │ run     │   │ REST API  │  │ Markdown│
    │ status  │   │           │  │         │
    └─────────┘   └───────────┘  └─────────┘
```

## Key Design Decisions

### 1. Dimensions are callables, not configs

A dimension's `check` is a plain `Callable[[], tuple[float, dict]]`. No YAML schemas, no special DSL. This means:
- Any Python function can be a check
- Checks can call subprocess, HTTP, DB, or pure logic
- Testing is trivial (mock the callable)
- No serialization/deserialization overhead

### 2. Sidecar over DB for manual grades

Manual grades live in `audit_baseline.json`, not the database. Why:
- **Git-trackable** — diffs show grade changes in code review
- **Human-editable** — no special tooling needed to update
- **Atomic** — read the whole file, write the whole file (no partial states)
- **Portable** — copy between environments without DB migration

The DB stores the time-series of auto scores and reconciliation results. The sidecar stores the current truth of manual assessment.

### 3. Tier hierarchy is inclusive

Each tier includes all checks from lower tiers:
```
weekly ⊃ daily ⊃ medium ⊃ light
```

This means running `daily` also runs all `light` and `medium` checks. There's no way to run "only daily checks" because the lower tiers provide the foundation that daily reconciliation needs.

### 4. Divergence requires confidence

A divergence is only flagged when:
```
abs(auto_score - manual_score) > 0.15 AND auto_confidence >= 0.5
```

Low-confidence dimensions (like `usability_ux` at 0.30) can't trigger divergence because we don't trust the auto score enough to contradict a human reviewer. The confidence floor prevents noisy alerts.

### 5. Three resolution paths (not just two)

Most audit systems offer "fix it" or "ignore it". We add a third:
1. **Update manual grade** — acknowledge the auto score is right
2. **Acknowledge** — dismiss without changing (visible but dimmed)
3. **LLM review** — get a second opinion from an external model

The LLM review path is valuable because it resolves the "who's right?" question without requiring a full human re-audit. It's a structured single-call prompt, not a conversation.

### 6. Ratchets are advisory by default

Ratchets prevent silent regression: once you declare "testing should be at least A", a drop below that floor is flagged. But in v0.1, ratchets produce WARN, not FAIL.

This is deliberate — new users shouldn't have their CI broken by a feature they just set up. Promote to FAIL per-dimension after tuning the system for your codebase.

### 7. Presets are starting points, not constraints

Presets provide dimension definitions with stub check functions. The expectation is:
- Use a preset to get started fast
- Replace stub checks with real implementations for your project
- Add/remove dimensions as needed

A preset is a Python list of `Dimension` objects, not a locked configuration.

### 8. Integrations are optional and pluggable

Each integration (GitHub, semgrep, PyPI, Ollama) is:
- A separate module with its own dependencies
- Configured via `configure(**kwargs)` (no global config file)
- Provides `checks()` that return callables wire-able to dimensions

If you don't install `scorerift[github]`, the GitHub integration simply isn't available. No broken imports, no missing-dep errors at runtime.

## Data Flow

### Scoring Run

```
1. Engine.run_tier("daily")
2. For each dimension where tier ≤ requested tier:
   a. Call dimension.check() → (score, detail)
   b. Clamp score to [0.0, 1.0]
   c. Load manual grade from sidecar
   d. Compare: divergent if gap > 0.15 AND confidence ≥ 0.5
   e. Write DimensionResult to audit_scores table
3. Return list of DimensionResult
```

### Reconciliation

```
1. Dr. Ders / scheduler triggers daily run at 3:00 AM
2. Run all dimensions up to daily tier
3. For each dimension with divergence=1 AND acknowledged=0:
   a. Push SSE alert (if dashboard is running)
   b. Flag in smoke test output
4. Check ratchet targets — flag any below floor
5. Aggregate user feedback into sidecar
```

### Feedback Loop

```
1. User submits feedback (stars/slider + text)
2. Score stored in user_feedback table
3. (Optional) Text classified by LLM into dimensions
4. Daily reconciliation aggregates into sidecar per-dimension
5. UX confidence adjusts: min(0.75, 0.30 + feedback_count/100 * 0.45)
```

## File Layout

```
scorerift/
├── src/scorerift/
│   ├── __init__.py          # Public API exports
│   ├── engine.py            # AuditEngine, Dimension, DimensionResult
│   ├── db.py                # SQLite storage (audit_scores, user_feedback)
│   ├── sidecar.py           # JSON sidecar read/write
│   ├── grades.py            # Grade ↔ score conversion
│   ├── tiers.py             # Tier enum + scheduling
│   ├── reconciler.py        # Weekly merge, ratchet check, status classify
│   ├── feedback.py          # LLMClassifier protocol, conversion helpers
│   ├── cli.py               # CLI entry point
│   ├── dashboard/           # Optional Flask blueprint
│   ├── exporters/           # JSON, CSV, Markdown report generators
│   ├── presets/             # Dimension configs per project type
│   │   ├── python_project.py # 8 dimensions for Python repos
│   │   ├── api_service.py   # 8 dimensions for REST APIs
│   │   ├── database.py      # 7 dimensions for database health
│   │   ├── infrastructure.py # 8 dimensions for DevOps/infra
│   │   └── ml_pipeline.py   # 7 dimensions for ML workflows
│   ├── integrations/        # Pluggable external data sources
│   │   ├── github.py        # CI status, open bugs, stale PRs
│   │   ├── semgrep.py       # SAST security scanning
│   │   ├── pypi.py          # Dependency version drift
│   │   └── ollama.py        # Local model health
│   └── reviewers/           # LLM-powered review system
│       ├── providers.py     # Claude, Gemini, OpenAI clients
│       ├── oss_review.py    # OSS swarm lenses + cross-validation
│       ├── consensus.py     # Multi-provider consensus
│       └── cache.py         # Local review result cache
├── examples/biged/           # Reference implementation (12 dimensions)
├── tests/                    # pytest test suite
├── docs/                     # This file + future guides
├── pyproject.toml            # Build config, deps, tool settings
└── README.md                 # User-facing documentation
```

## Origin

Extracted from BigEd CC (`github.com/mbachaud/Education`) after production use on a 125-skill AI fleet. The BigEd implementation lives in `fleet/audit_scorer.py` (1,088 lines) and uses all 12 dimensions across 4 tiers with Dr. Ders scheduling daily/weekly runs.

The extraction preserves the battle-tested core while making it configurable for any project type.
