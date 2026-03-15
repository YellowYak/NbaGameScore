"""Tests for the watchability scoring engine."""

from datetime import date

import pytest

from nba_watchability import config as config_module
from nba_watchability import scorer
from nba_watchability.models import (
    BoxScoreData,
    GameData,
    PlayerLine,
    PlayByPlayData,
    QuarterScore,
    ScoreSnapshot,
    TeamSnapshot,
)


# ---------------------------------------------------------------------------
# Helpers for building test GameData objects
# ---------------------------------------------------------------------------


def _team(abbr: str, wins: int, losses: int) -> TeamSnapshot:
    names = {"GSW": "Golden State Warriors", "PHI": "Philadelphia 76ers",
             "LAL": "Los Angeles Lakers", "DEN": "Denver Nuggets",
             "OKC": "Oklahoma City Thunder", "SAS": "San Antonio Spurs"}
    return TeamSnapshot(name=names.get(abbr, abbr), abbreviation=abbr, wins=wins, losses=losses)


def _player(name: str, pts: int, reb: int = 3, ast: int = 2,
            stl: int = 0, blk: int = 0) -> PlayerLine:
    return PlayerLine(
        name=name, team_abbr="TST", minutes=30,
        points=pts, rebounds=reb, assists=ast,
        steals=stl, blocks=blk, turnovers=1,
        fg_made=pts // 3, fg_attempted=pts // 2 + 2,
    )


def _make_game(
    margin: int = 5,
    lead_changes: int = 5,
    ties: int = 3,
    ot_periods: int = 0,
    away_wins: int = 40, away_losses: int = 20,
    home_wins: int = 40, home_losses: int = 20,
    players: list[PlayerLine] | None = None,
) -> GameData:
    away_total = 100
    home_total = 100 - margin
    qs = (
        QuarterScore("Q1", 25, 25),
        QuarterScore("Q2", 25, 25),
        QuarterScore("Q3", 25, 25),
        QuarterScore("Q4", away_total - 75, home_total - 75),
    )
    box = BoxScoreData(
        game_date=date(2024, 12, 25),
        away_team=_team("DEN", away_wins, away_losses),
        home_team=_team("LAL", home_wins, home_losses),
        quarter_scores=qs,
        player_lines=tuple(players or []),
    )
    snap = ScoreSnapshot(quarter=4, seconds_elapsed=700, away_score=100, home_score=100 - margin)
    pbp_data = PlayByPlayData(
        snapshots=(snap,),
        lead_changes=lead_changes,
        ties=ties,
        overtime_periods=ot_periods,
    )
    return GameData(box=box, pbp=pbp_data)


# ---------------------------------------------------------------------------
# Closeness factor
# ---------------------------------------------------------------------------


class TestClosenessScore:
    cfg = config_module.load()

    def test_blowout_scores_low(self):
        game = _make_game(margin=30)
        result = scorer.score(game, self.cfg)
        closeness = next(f for f in result.factors if f.name == "Closeness")
        assert closeness.raw_score == 0.0

    def test_buzzer_beater_scores_high(self):
        game = _make_game(margin=1)
        result = scorer.score(game, self.cfg)
        closeness = next(f for f in result.factors if f.name == "Closeness")
        assert closeness.raw_score == 1.0

    def test_three_point_game_max(self):
        game = _make_game(margin=3)
        result = scorer.score(game, self.cfg)
        closeness = next(f for f in result.factors if f.name == "Closeness")
        assert closeness.raw_score == 1.0

    def test_interpolation_between_breakpoints(self):
        # margin=7 should give 0.65 exactly
        game = _make_game(margin=7)
        result = scorer.score(game, self.cfg)
        closeness = next(f for f in result.factors if f.name == "Closeness")
        assert abs(closeness.raw_score - 0.65) < 0.01

    def test_moderate_margin_interpolated(self):
        # margin=11 is between 7 (0.65) and 15 (0.25)
        game = _make_game(margin=11)
        result = scorer.score(game, self.cfg)
        closeness = next(f for f in result.factors if f.name == "Closeness")
        assert 0.25 < closeness.raw_score < 0.65


# ---------------------------------------------------------------------------
# Lead change / back-and-forth factor
# ---------------------------------------------------------------------------


class TestLeadChangeScore:
    cfg = config_module.load()

    def test_many_lead_changes_scores_high(self):
        game = _make_game(lead_changes=20, ties=10)
        result = scorer.score(game, self.cfg)
        btf = next(f for f in result.factors if f.name == "Back-and-Forth")
        assert btf.raw_score == 1.0

    def test_no_lead_changes_scores_low(self):
        game = _make_game(lead_changes=0, ties=0)
        result = scorer.score(game, self.cfg)
        btf = next(f for f in result.factors if f.name == "Back-and-Forth")
        assert btf.raw_score == 0.0

    def test_partial_lead_changes(self):
        # 10 lead changes out of max 20 → 0.5 for lead changes component
        game = _make_game(lead_changes=10, ties=0)
        result = scorer.score(game, self.cfg)
        btf = next(f for f in result.factors if f.name == "Back-and-Forth")
        # ties_weight=0.3, so factor = 0.5*0.7 + 0.0*0.3 = 0.35; ot_periods=0 → no kicker
        assert abs(btf.raw_score - 0.35) < 0.01

    def test_ot_kicker_boosts_score(self):
        # 0 lead changes, 0 ties, 2 OT periods → kicker = 2 * 0.20 = 0.40
        game = _make_game(lead_changes=0, ties=0, ot_periods=2)
        result = scorer.score(game, self.cfg)
        btf = next(f for f in result.factors if f.name == "Back-and-Forth")
        assert abs(btf.raw_score - 0.40) < 0.01

    def test_ot_kicker_capped_at_one(self):
        # High base score plus large kicker still caps at 1.0
        game = _make_game(lead_changes=20, ties=10, ot_periods=3)
        result = scorer.score(game, self.cfg)
        btf = next(f for f in result.factors if f.name == "Back-and-Forth")
        assert btf.raw_score == 1.0


# ---------------------------------------------------------------------------
# Statistical anomalies factor
# ---------------------------------------------------------------------------


class TestAnomalyScore:
    cfg = config_module.load()

    def test_no_achievements_scores_zero(self):
        players = [_player("Player A", 15), _player("Player B", 12)]
        game = _make_game(players=players)
        result = scorer.score(game, self.cfg)
        star = next(f for f in result.factors if f.name == "Star Moments")
        assert star.raw_score == 0.0

    def test_50pt_game(self):
        players = [_player("Star Player", 52)]
        game = _make_game(players=players)
        result = scorer.score(game, self.cfg)
        star = next(f for f in result.factors if f.name == "Star Moments")
        # 50+ pts = 30 points; cap = 40 → raw_score = 30/40 = 0.75
        assert abs(star.raw_score - 0.75) < 0.01

    def test_40pt_game(self):
        players = [_player("Star Player", 45)]
        game = _make_game(players=players)
        result = scorer.score(game, self.cfg)
        star = next(f for f in result.factors if f.name == "Star Moments")
        # 40-49 pts = 20 points; 20/40 = 0.5
        assert abs(star.raw_score - 0.50) < 0.01

    def test_triple_double(self):
        players = [_player("TD Player", pts=10, reb=10, ast=10)]
        game = _make_game(players=players)
        result = scorer.score(game, self.cfg)
        star = next(f for f in result.factors if f.name == "Star Moments")
        # TD = 25 pts + assists_10 = 15 pts = 40 → capped at 1.0
        assert star.raw_score == 1.0

    def test_combined_achievements_capped_at_1(self):
        players = [_player("Beast", pts=55, reb=22, ast=11, stl=5, blk=5)]
        game = _make_game(players=players)
        result = scorer.score(game, self.cfg)
        star = next(f for f in result.factors if f.name == "Star Moments")
        assert star.raw_score == 1.0


# ---------------------------------------------------------------------------
# Team quality factor
# ---------------------------------------------------------------------------


class TestTeamQualityScore:
    cfg = config_module.load()

    def test_two_elite_teams(self):
        # Both at 0.700 win% → score = 1.0
        game = _make_game(away_wins=70, away_losses=30, home_wins=70, home_losses=30)
        result = scorer.score(game, self.cfg)
        tq = next(f for f in result.factors if f.name == "Team Quality")
        assert tq.raw_score == 1.0

    def test_two_bad_teams(self):
        # Both at 0.200 win% → score = 0.0
        game = _make_game(away_wins=20, away_losses=80, home_wins=20, home_losses=80)
        result = scorer.score(game, self.cfg)
        tq = next(f for f in result.factors if f.name == "Team Quality")
        assert tq.raw_score == 0.0

    def test_average_teams(self):
        # Both at 0.500 → between 0 and 1
        game = _make_game(away_wins=50, away_losses=50, home_wins=50, home_losses=50)
        result = scorer.score(game, self.cfg)
        tq = next(f for f in result.factors if f.name == "Team Quality")
        assert 0.0 < tq.raw_score < 1.0

    def test_exactly_at_elite_threshold(self):
        # avg win% = 0.600 → score = 1.0
        game = _make_game(away_wins=60, away_losses=40, home_wins=60, home_losses=40)
        result = scorer.score(game, self.cfg)
        tq = next(f for f in result.factors if f.name == "Team Quality")
        assert tq.raw_score == 1.0


# ---------------------------------------------------------------------------
# Overall score and weight normalization
# ---------------------------------------------------------------------------


class TestOverallScore:
    cfg = config_module.load()

    def test_total_in_range(self):
        game = _make_game(margin=5, lead_changes=10, ties=5)
        result = scorer.score(game, self.cfg)
        assert 0 <= result.total <= 100

    def test_high_excitement_scores_high(self):
        players = [_player("Star", pts=52)]
        game = _make_game(
            margin=1, lead_changes=25, ties=10, ot_periods=2,
            away_wins=65, away_losses=15, home_wins=65, home_losses=15,
            players=players,
        )
        result = scorer.score(game, self.cfg)
        assert result.total >= 75

    def test_boring_game_scores_low(self):
        game = _make_game(
            margin=30, lead_changes=0, ties=0, ot_periods=0,
            away_wins=15, away_losses=55, home_wins=15, home_losses=55,
        )
        result = scorer.score(game, self.cfg)
        assert result.total <= 20

    def test_weights_normalized(self):
        # Custom weights that don't sum to 1 should still produce valid results
        import copy
        cfg2 = copy.deepcopy(self.cfg)
        cfg2.weights.closeness = 1000
        cfg2.weights.lead_changes = 1000
        cfg2.weights.anomalies = 1000
        cfg2.weights.team_quality = 1000
        game = _make_game()
        result = scorer.score(game, cfg2)
        assert 0 <= result.total <= 100

    def test_factor_contributions_sum_to_total(self):
        game = _make_game(margin=5, lead_changes=10, ties=5)
        result = scorer.score(game, self.cfg)
        total_contributions = sum(f.contribution for f in result.factors)
        assert abs(total_contributions - result.total) <= 1  # allow rounding

    def test_clutch_factor_present(self):
        game = _make_game()
        result = scorer.score(game, self.cfg)
        names = [f.name for f in result.factors]
        assert "Clutch Time" in names


# ---------------------------------------------------------------------------
# Clutch time factor
# ---------------------------------------------------------------------------


def _make_game_with_snapshots(snapshots: list, margin: int = 5) -> GameData:
    """Build a GameData with custom PBP snapshots."""
    from nba_watchability.models import ScoreSnapshot
    qs = (
        QuarterScore("Q1", 25, 25),
        QuarterScore("Q2", 25, 25),
        QuarterScore("Q3", 25, 25),
        QuarterScore("Q4", 25 + margin, 25),
    )
    box = BoxScoreData(
        game_date=date(2024, 12, 25),
        away_team=_team("DEN", 40, 20),
        home_team=_team("LAL", 40, 20),
        quarter_scores=qs,
        player_lines=(),
    )
    pbp_data = PlayByPlayData(
        snapshots=tuple(snapshots),
        lead_changes=0,
        ties=0,
        overtime_periods=0,
    )
    return GameData(box=box, pbp=pbp_data)


class TestClutchScore:
    cfg = config_module.load()

    def _snap(self, quarter: int, elapsed: int, away: int, home: int) -> ScoreSnapshot:
        return ScoreSnapshot(quarter=quarter, seconds_elapsed=elapsed,
                             away_score=away, home_score=home)

    def test_no_clutch_plays_scores_zero(self):
        # All plays in Q1-Q3 — none in Q4 clutch window
        snaps = [self._snap(1, 100, 10, 8), self._snap(2, 200, 20, 18)]
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert clutch.raw_score == 0.0

    def test_clutch_plays_within_differential_counted(self):
        # 10 scoring plays in Q4 clutch window, all within 5 pts → score = 1.0
        snaps = []
        for i in range(10):
            snaps.append(self._snap(4, 430 + i * 10, 90 + i, 88 + i))
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert clutch.raw_score == 1.0

    def test_blowout_clutch_window_not_counted(self):
        # Plays in Q4 clutch window but score differential > 5
        snaps = [self._snap(4, 500, 110, 90), self._snap(4, 600, 115, 90)]
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert clutch.raw_score == 0.0

    def test_early_q4_not_counted(self):
        # Play at Q4 second 300 (10:00 remaining) — outside the last-5-min window
        snaps = [self._snap(4, 300, 60, 58)]
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert clutch.raw_score == 0.0

    def test_ot_plays_counted_as_clutch(self):
        # OT period with tight score — entire OT counts as clutch window
        snaps = [self._snap(5, 50, 100, 98), self._snap(5, 100, 102, 100),
                 self._snap(5, 150, 104, 102)]
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert clutch.raw_score > 0.0

    def test_partial_clutch_plays_partial_score(self):
        # 5 clutch plays out of max 10 → raw_score ≈ 0.5
        snaps = []
        for i in range(5):
            snaps.append(self._snap(4, 430 + i * 10, 90 + i, 88 + i))
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert abs(clutch.raw_score - 0.5) < 0.01

    def test_tying_play_weighted_higher_than_regular(self):
        # snap1: away leads 90-88 (regular, +1.0)
        # snap2: home ties 90-90 (tie, +2.0) → excitement=3.0 → 0.3
        snaps = [
            self._snap(4, 430, 90, 88),
            self._snap(4, 440, 90, 90),
        ]
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert abs(clutch.raw_score - 0.3) < 0.01

    def test_lead_change_play_weighted_highest(self):
        # snap1: away leads 90-88 (regular, +1.0)
        # snap2: home takes lead 90-92 (lead change, +3.0) → excitement=4.0 → 0.4
        snaps = [
            self._snap(4, 430, 90, 88),
            self._snap(4, 440, 90, 92),
        ]
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, self.cfg)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert abs(clutch.raw_score - 0.4) < 0.01

    def test_clutch_weight_zero_disables_factor(self):
        import copy
        cfg2 = copy.deepcopy(self.cfg)
        cfg2.weights.clutch = 0.0
        snaps = [self._snap(4, 500, 95, 93)]
        game = _make_game_with_snapshots(snaps)
        result = scorer.score(game, cfg2)
        clutch = next(f for f in result.factors if f.name == "Clutch Time")
        assert clutch.contribution == 0.0
