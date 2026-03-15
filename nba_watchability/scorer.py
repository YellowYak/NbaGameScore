"""Watchability scoring engine."""

from __future__ import annotations

from .config import Config
from .models import FactorScore, GameData, PlayerLine, WatchabilityResult


# ---------------------------------------------------------------------------
# Individual factor functions — each returns a float in [0.0, 1.0]
# ---------------------------------------------------------------------------


def _closeness_score(game: GameData, cfg: Config) -> float:
    """Score based on the final margin of victory."""
    margin = game.box.margin
    breakpoints = cfg.scoring.closeness.breakpoints

    if not breakpoints:
        return 0.0

    # Below or at the first breakpoint
    if margin <= breakpoints[0].margin:
        return breakpoints[0].score

    # Above the last breakpoint
    if margin >= breakpoints[-1].margin:
        return breakpoints[-1].score

    # Piecewise linear interpolation
    for i in range(len(breakpoints) - 1):
        lo = breakpoints[i]
        hi = breakpoints[i + 1]
        if lo.margin <= margin <= hi.margin:
            t = (margin - lo.margin) / (hi.margin - lo.margin)
            return lo.score + t * (hi.score - lo.score)

    return 0.0


def _lead_change_score(game: GameData, cfg: Config) -> float:
    """Score based on lead changes, tied moments, and overtime periods."""
    lc_cfg = cfg.scoring.lead_changes
    lc_score = min(game.pbp.lead_changes / lc_cfg.max_for_full_score, 1.0)
    ties_score = min(game.pbp.ties / lc_cfg.ties_max, 1.0) if lc_cfg.ties_max > 0 else 0.0
    w = lc_cfg.ties_weight
    base = lc_score * (1.0 - w) + ties_score * w
    # OT kicker: overtime means the game was too close to decide in regulation
    ot_periods = game.pbp.overtime_periods or game.box.overtime_periods
    return min(base + ot_periods * lc_cfg.ot_bonus_per_period, 1.0)


def _anomaly_score(game: GameData, cfg: Config) -> float:
    """Score based on individual statistical achievements."""
    ach = cfg.scoring.anomalies.achievements
    cap = cfg.scoring.anomalies.cap_points

    total_pts = 0

    for player in game.box.player_lines:
        # Points-based achievements — at most one per player (take the higher tier)
        if player.points >= 50:
            total_pts += ach.points_50
        elif player.points >= 40:
            total_pts += ach.points_40_to_49

        # Triple-double: 10+ in points, rebounds, AND assists
        if player.points >= 10 and player.rebounds >= 10 and player.assists >= 10:
            total_pts += ach.triple_double

        if player.rebounds >= 20:
            total_pts += ach.rebounds_20

        if player.assists >= 10:
            total_pts += ach.assists_10

        if player.steals >= 5:
            total_pts += ach.steals_5

        if player.blocks >= 5:
            total_pts += ach.blocks_5

    return min(total_pts / cap, 1.0) if cap > 0 else 0.0


def _team_quality_score(game: GameData, cfg: Config) -> float:
    """Score based on both teams' win percentage at game time."""
    tq = cfg.scoring.team_quality
    avg_win_pct = (game.box.away_team.win_pct + game.box.home_team.win_pct) / 2.0

    if avg_win_pct >= tq.elite_threshold:
        return 1.0
    if avg_win_pct <= tq.floor_threshold:
        return 0.0

    span = tq.elite_threshold - tq.floor_threshold
    return (avg_win_pct - tq.floor_threshold) / span


def _clutch_score(game: GameData, cfg: Config) -> float:
    """Score based on scoring plays during clutch time.

    Clutch time: the final 5 minutes of Q4 (seconds_elapsed >= 420 of 720),
    or any overtime period in its entirety, where the score differential
    is <= score_differential points.

    Each clutch scoring play adds excitement points:
    - lead-changing play: lead_change_weight (default 3.0)
    - tying play:         tie_weight         (default 2.0)
    - regular play:       play_weight        (default 1.0)
    """
    clutch_cfg = cfg.scoring.clutch
    if clutch_cfg.max_plays_for_full_score <= 0:
        return 0.0

    # Q4 last-5-minutes threshold: 12-min quarter = 720s; last 5 min = elapsed >= 420s
    Q4_CLUTCH_THRESHOLD = 420

    excitement = 0.0
    prev_away: int | None = None
    prev_home: int | None = None

    for snap in game.pbp.snapshots:
        in_window = (
            (snap.quarter == 4 and snap.seconds_elapsed >= Q4_CLUTCH_THRESHOLD)
            or snap.quarter >= 5  # any OT period
        )
        if in_window and abs(snap.away_score - snap.home_score) <= clutch_cfg.score_differential:
            # Count only scoring plays (score changed from previous snapshot)
            if snap.away_score != prev_away or snap.home_score != prev_home:
                diff = snap.away_score - snap.home_score
                if diff == 0:
                    excitement += clutch_cfg.tie_weight
                elif (
                    prev_away is not None
                    and prev_home is not None
                    and (prev_away - prev_home) != 0
                    and (diff > 0) != ((prev_away - prev_home) > 0)
                ):
                    excitement += clutch_cfg.lead_change_weight
                else:
                    excitement += clutch_cfg.play_weight

        prev_away = snap.away_score
        prev_home = snap.home_score

    return min(excitement / clutch_cfg.max_plays_for_full_score, 1.0)


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------


def score(game: GameData, cfg: Config) -> WatchabilityResult:
    """Compute the watchability score for a game.

    Args:
        game: Combined box score + play-by-play data.
        cfg: Configuration (weights, thresholds).

    Returns:
        WatchabilityResult with total score and per-factor breakdown.
    """
    raw_factors: list[tuple[str, float, float]] = [
        ("Closeness",      _closeness_score(game, cfg),     cfg.weights.closeness),
        ("Back-and-Forth", _lead_change_score(game, cfg),   cfg.weights.lead_changes),
        ("Star Moments",   _anomaly_score(game, cfg),       cfg.weights.anomalies),
        ("Team Quality",   _team_quality_score(game, cfg),  cfg.weights.team_quality),
        ("Clutch Time",    _clutch_score(game, cfg),        cfg.weights.clutch),
    ]

    # Normalize weights so they sum to 1.0 (user-proof)
    total_weight = sum(w for _, _, w in raw_factors)
    if total_weight <= 0:
        total_weight = 1.0

    factors: list[FactorScore] = []
    weighted_sum = 0.0
    for name, raw, weight in raw_factors:
        normalized_weight = weight / total_weight
        contribution = raw * normalized_weight * 100.0
        weighted_sum += contribution
        factors.append(
            FactorScore(
                name=name,
                raw_score=raw,
                weight=normalized_weight,
                contribution=contribution,
            )
        )

    ot_periods = game.pbp.overtime_periods or game.box.overtime_periods

    return WatchabilityResult(
        total=round(weighted_sum),
        factors=tuple(factors),
        game_date=game.box.game_date,
        away_team=game.box.away_team.name,
        home_team=game.box.home_team.name,
        overtime_periods=ot_periods,
    )
