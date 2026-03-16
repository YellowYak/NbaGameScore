"""Configuration loading and validation for nba-watchability."""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import ConfigError

# Path to the default config shipped with the package (lives inside the package dir)
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.default.toml"


@dataclass
class ClosenessBreakpoint:
    margin: int
    score: float


@dataclass
class ClosenessConfig:
    breakpoints: list[ClosenessBreakpoint] = field(default_factory=list)


@dataclass
class LeadChangesConfig:
    max_for_full_score: int = 20
    ties_max: int = 10
    ties_weight: float = 0.3
    ot_bonus_per_period: float = 0.20  # added to B&F raw score per OT period (capped at 1.0)


@dataclass
class AnomalyAchievements:
    points_50: int = 30
    points_40_to_49: int = 20
    triple_double: int = 25
    rebounds_20: int = 20
    assists_15: int = 15
    steals_5: int = 15
    blocks_5: int = 10


@dataclass
class AnomaliesConfig:
    cap_points: int = 40
    achievements: AnomalyAchievements = field(default_factory=AnomalyAchievements)


@dataclass
class TeamQualityConfig:
    elite_threshold: float = 0.600
    floor_threshold: float = 0.300


@dataclass
class ClutchConfig:
    score_differential: int = 5   # max point gap to qualify as clutch
    max_plays_for_full_score: int = 10  # excitement points needed for score of 1.0
    play_weight: float = 1.0       # weight for a regular clutch scoring play
    tie_weight: float = 2.0        # weight when the play ties the game
    lead_change_weight: float = 3.0  # weight when the play changes the lead


@dataclass
class WeightsConfig:
    closeness: float = 30.0
    lead_changes: float = 25.0
    anomalies: float = 20.0
    team_quality: float = 15.0
    clutch: float = 20.0


@dataclass
class HttpConfig:
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    request_delay: float = 2.0
    timeout: int = 15


@dataclass
class ScoringConfig:
    closeness: ClosenessConfig = field(default_factory=ClosenessConfig)
    lead_changes: LeadChangesConfig = field(default_factory=LeadChangesConfig)
    anomalies: AnomaliesConfig = field(default_factory=AnomaliesConfig)
    team_quality: TeamQualityConfig = field(default_factory=TeamQualityConfig)
    clutch: ClutchConfig = field(default_factory=ClutchConfig)


@dataclass
class Config:
    weights: WeightsConfig = field(default_factory=WeightsConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    http: HttpConfig = field(default_factory=HttpConfig)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base, returning a new dict."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _parse_config(raw: dict[str, Any], source: str) -> Config:
    """Convert a raw TOML dict into a Config object, with validation."""
    try:
        weights_raw = raw.get("weights", {})
        weights = WeightsConfig(
            closeness=float(weights_raw.get("closeness", 30)),
            lead_changes=float(weights_raw.get("lead_changes", 25)),
            anomalies=float(weights_raw.get("anomalies", 20)),
            team_quality=float(weights_raw.get("team_quality", 15)),
            clutch=float(weights_raw.get("clutch", 20)),
        )

        scoring_raw = raw.get("scoring", {})

        # Closeness breakpoints
        closeness_raw = scoring_raw.get("closeness", {})
        bp_list = closeness_raw.get("breakpoints", [])
        breakpoints = [
            ClosenessBreakpoint(margin=int(bp["margin"]), score=float(bp["score"]))
            for bp in bp_list
        ]
        breakpoints.sort(key=lambda b: b.margin)
        closeness_cfg = ClosenessConfig(breakpoints=breakpoints)

        lc_raw = scoring_raw.get("lead_changes", {})
        lead_changes_cfg = LeadChangesConfig(
            max_for_full_score=int(lc_raw.get("max_for_full_score", 20)),
            ties_max=int(lc_raw.get("ties_max", 10)),
            ties_weight=float(lc_raw.get("ties_weight", 0.3)),
            ot_bonus_per_period=float(lc_raw.get("ot_bonus_per_period", 0.20)),
        )

        an_raw = scoring_raw.get("anomalies", {})
        ach_raw = an_raw.get("achievements", {})
        achievements = AnomalyAchievements(
            points_50=int(ach_raw.get("points_50", 30)),
            points_40_to_49=int(ach_raw.get("points_40_to_49", 20)),
            triple_double=int(ach_raw.get("triple_double", 25)),
            rebounds_20=int(ach_raw.get("rebounds_20", 20)),
            assists_15=int(ach_raw.get("assists_15", 15)),
            steals_5=int(ach_raw.get("steals_5", 15)),
            blocks_5=int(ach_raw.get("blocks_5", 10)),
        )
        anomalies_cfg = AnomaliesConfig(
            cap_points=int(an_raw.get("cap_points", 40)),
            achievements=achievements,
        )

        tq_raw = scoring_raw.get("team_quality", {})
        team_quality_cfg = TeamQualityConfig(
            elite_threshold=float(tq_raw.get("elite_threshold", 0.600)),
            floor_threshold=float(tq_raw.get("floor_threshold", 0.300)),
        )

        cl_raw = scoring_raw.get("clutch", {})
        clutch_cfg = ClutchConfig(
            score_differential=int(cl_raw.get("score_differential", 5)),
            max_plays_for_full_score=int(cl_raw.get("max_plays_for_full_score", 10)),
            play_weight=float(cl_raw.get("play_weight", 1.0)),
            tie_weight=float(cl_raw.get("tie_weight", 2.0)),
            lead_change_weight=float(cl_raw.get("lead_change_weight", 3.0)),
        )

        scoring = ScoringConfig(
            closeness=closeness_cfg,
            lead_changes=lead_changes_cfg,
            anomalies=anomalies_cfg,
            team_quality=team_quality_cfg,
            clutch=clutch_cfg,
        )

        http_raw = raw.get("http", {})
        http = HttpConfig(
            user_agent=str(http_raw.get("user_agent", HttpConfig.user_agent)),
            request_delay=float(http_raw.get("request_delay", 2.0)),
            timeout=int(http_raw.get("timeout", 15)),
        )

        # Basic validation
        total_weight = (
            weights.closeness
            + weights.lead_changes
            + weights.anomalies
            + weights.team_quality
            + weights.clutch
        )
        if total_weight <= 0:
            raise ConfigError(source, "all weights are zero or negative")

        if not breakpoints:
            raise ConfigError(source, "scoring.closeness.breakpoints must not be empty")

        if team_quality_cfg.elite_threshold <= team_quality_cfg.floor_threshold:
            raise ConfigError(
                source,
                "scoring.team_quality.elite_threshold must be greater than floor_threshold",
            )

        return Config(weights=weights, scoring=scoring, http=http)

    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigError(source, str(exc)) from exc


def load(user_config_path: str | Path | None = None) -> Config:
    """Load configuration, merging user overrides on top of defaults.

    Args:
        user_config_path: Optional path to a user-supplied TOML config file.
                          Values in this file override the built-in defaults.

    Returns:
        A fully populated Config object.
    """
    with open(_DEFAULT_CONFIG_PATH, "rb") as f:
        default_raw = tomllib.load(f)

    if user_config_path is not None:
        path = Path(user_config_path)
        if not path.exists():
            raise ConfigError(str(path), "file not found")
        try:
            with open(path, "rb") as f:
                user_raw = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(str(path), f"invalid TOML: {exc}") from exc

        merged = _deep_merge(default_raw, user_raw)
        return _parse_config(merged, str(path))

    return _parse_config(default_raw, str(_DEFAULT_CONFIG_PATH))
