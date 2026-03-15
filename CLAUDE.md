# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run the tool
python -m nba_watchability <basketball-reference-boxscore-url>
nba-score <url>

# Run all tests
python -m pytest

# Run a single test file
python -m pytest tests/test_scorer.py

# Run a single test
python -m pytest tests/test_scorer.py::test_closeness_score_tie
```

## Architecture

The tool scrapes basketball-reference.com box score and play-by-play pages, then computes a 0–100 watchability score across five factors — all without revealing the final score.

**Data flow:**

```
URL → scraper/http.py (BbrefSession) → boxscore.py + pbp.py parsers
    → models.py (GameData: BoxScoreData + PlayByPlayData)
    → scorer.py → WatchabilityResult
    → cli.py (Rich table or JSON output)
```

**Scoring engine (`scorer.py`):** Five independent functions each return `[0.0, 1.0]`, then get combined via weighted sum (weights defined in config). The five factors are: closeness (final margin), lead changes (back-and-forth play), anomalies (statistical achievements), team quality (win%), and clutch (tight plays in final 5 min).

**Configuration (`config.py` + `config.default.toml`):** All weights and thresholds are TOML-configurable. `config.load()` deep-merges a user-supplied partial config over the built-in defaults. The dataclass hierarchy in `config.py` mirrors the TOML sections.

**Scraper anti-detection (`scraper/http.py`):** Uses `curl_cffi` with Chrome 120 TLS fingerprinting plus a configurable inter-request delay. Basketball-reference embeds data tables inside HTML comments; `_unwrap_comments()` strips those before parsing.

**Models (`models.py`):** All dataclasses are frozen (immutable). `GameData` aggregates `BoxScoreData` (teams, records, quarter scores, player lines) and `PlayByPlayData` (score snapshots, lead change/tie counts).

**Tests (`tests/`):** Fixtures in `tests/fixtures/` are real HTML samples used by the scraper tests. The `responses` library mocks HTTP in test. No linter/formatter is configured in `pyproject.toml`.
