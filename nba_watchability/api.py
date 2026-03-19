"""Public library API for nba-watchability — no CLI/Rich dependencies."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from . import config as _config
from . import scorer as _scorer
from .exceptions import InvalidDateError
from .models import GameData, WatchabilityResult
from .scraper import boxscore as _boxscore
from .scraper import http as _http
from .scraper import pbp as _pbp
from .scraper import schedule as _schedule


def score_game(url: str, config_path: str | Path | None = None) -> WatchabilityResult:
    """Fetch, parse, and score one game from its boxscore URL."""
    cfg = _config.load(config_path)
    session = _http.BbrefSession(cfg.http)
    return _score_game_with_session(url, session, cfg)


def score_date(
    date_str: str, config_path: str | Path | None = None
) -> list[WatchabilityResult]:
    """Fetch and score all games on a date (YYYYMMDD), sorted highest first."""
    try:
        parsed = datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        raise InvalidDateError(date_str)
    if parsed >= date.today():
        raise InvalidDateError(
            date_str,
            f"Date must be in the past: scores are not available for {date_str}.",
        )
    cfg = _config.load(config_path)
    session = _http.BbrefSession(cfg.http)
    index_url = _schedule.date_index_url(date_str)
    urls = _schedule.parse_boxscore_urls(session.get_soup(index_url))
    results = [_score_game_with_session(u, session, cfg) for u in urls]
    return sorted(results, key=lambda r: r.total, reverse=True)


def _score_game_with_session(url, session, cfg) -> WatchabilityResult:
    """Internal: score one game reusing an existing session."""
    game_id = _http.extract_game_id(url)
    pbp_url = _http.pbp_url_from_boxscore_url(url)
    box_data = _boxscore.parse(session.get_soup(url), game_id)
    pbp_data = _pbp.parse(session.get_soup(pbp_url))
    return _scorer.score(GameData(box=box_data, pbp=pbp_data), cfg, url=url)
