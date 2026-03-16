"""Immutable data models for nba-watchability."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TeamSnapshot:
    """A team's identity and record at the time of a specific game."""

    name: str          # e.g. "Los Angeles Lakers"
    abbreviation: str  # e.g. "LAL"
    wins: int
    losses: int

    @property
    def win_pct(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total > 0 else 0.0


@dataclass(frozen=True)
class PlayerLine:
    """A single player's box score line."""

    name: str
    team_abbr: str
    minutes: int        # integer minutes played; 0 for DNP
    points: int         # used internally for anomaly detection — not displayed
    rebounds: int
    assists: int
    steals: int
    blocks: int
    turnovers: int
    fg_made: int
    fg_attempted: int


@dataclass(frozen=True)
class QuarterScore:
    """Points scored by each team in one period."""

    period: str         # "Q1", "Q2", "Q3", "Q4", "OT1", "OT2", ...
    away_points: int
    home_points: int


@dataclass(frozen=True)
class BoxScoreData:
    """Everything scraped from the main box score page."""

    game_date: date
    away_team: TeamSnapshot
    home_team: TeamSnapshot
    quarter_scores: tuple[QuarterScore, ...]
    player_lines: tuple[PlayerLine, ...]

    @property
    def final_away(self) -> int:
        return sum(q.away_points for q in self.quarter_scores)

    @property
    def final_home(self) -> int:
        return sum(q.home_points for q in self.quarter_scores)

    @property
    def margin(self) -> int:
        return abs(self.final_away - self.final_home)

    @property
    def overtime_periods(self) -> int:
        return sum(1 for q in self.quarter_scores if q.period.startswith("OT"))


@dataclass(frozen=True)
class ScoreSnapshot:
    """The running score at a single moment captured from play-by-play."""

    quarter: int         # 1–4 for regulation; 5=OT1, 6=OT2, ...
    seconds_elapsed: int # seconds elapsed within the quarter
    away_score: int
    home_score: int


@dataclass(frozen=True)
class PlayByPlayData:
    """Everything scraped from the play-by-play page."""

    snapshots: tuple[ScoreSnapshot, ...]
    lead_changes: int
    ties: int
    overtime_periods: int


@dataclass(frozen=True)
class GameData:
    """Combined data from box score and play-by-play pages."""

    box: BoxScoreData
    pbp: PlayByPlayData


@dataclass(frozen=True)
class FactorScore:
    """Watchability contribution from a single scoring factor."""

    name: str
    raw_score: float    # 0.0 – 1.0 before weighting
    weight: float       # normalised weight (0.0 – 1.0)
    contribution: float # raw_score * weight * 100

    @property
    def display_score(self) -> int:
        """Factor score as a 0–100 integer for display."""
        return round(self.raw_score * 100)


@dataclass(frozen=True)
class WatchabilityResult:
    """The final watchability assessment for a game."""

    total: int                          # 0–100
    factors: tuple[FactorScore, ...]
    game_date: date
    away_team: str                      # team name (not abbreviation)
    away_score: int
    home_team: str
    home_score: int
    overtime_periods: int
    boxscore_url: str = ""              # basketball-reference.com URL
