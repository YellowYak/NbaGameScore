"""Tests for the box score and play-by-play scrapers."""

from datetime import date

import pytest
from bs4 import BeautifulSoup, Comment

from nba_watchability.scraper import boxscore, pbp
from nba_watchability.scraper.http import _unwrap_comments, extract_game_id, pbp_url_from_boxscore_url
from nba_watchability.exceptions import InvalidUrlError, ParseError


# ---------------------------------------------------------------------------
# URL utilities
# ---------------------------------------------------------------------------


def test_extract_game_id_valid():
    url = "https://www.basketball-reference.com/boxscores/202412250LAL.html"
    assert extract_game_id(url) == "202412250LAL"


def test_extract_game_id_invalid():
    with pytest.raises(InvalidUrlError):
        extract_game_id("https://www.espn.com/nba/game/_/gameId/401705512")


def test_pbp_url_from_boxscore_url():
    url = "https://www.basketball-reference.com/boxscores/202412250LAL.html"
    pbp = pbp_url_from_boxscore_url(url)
    assert pbp == "https://www.basketball-reference.com/boxscores/pbp/202412250LAL.html"


# ---------------------------------------------------------------------------
# Comment unwrapping
# ---------------------------------------------------------------------------


def test_unwrap_comments_makes_tables_findable():
    html = "<html><body><!-- <table id='hidden'><tr><td>data</td></tr></table> --></body></html>"
    soup = BeautifulSoup(html, "lxml")
    # Before unwrapping — table not findable
    assert soup.find("table", id="hidden") is None
    # After unwrapping — table is findable
    unwrapped = _unwrap_comments(soup)
    assert unwrapped.find("table", id="hidden") is not None


# ---------------------------------------------------------------------------
# Box score parsing
# ---------------------------------------------------------------------------


class TestBoxScoreParse:
    def test_game_date(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.game_date == date(2024, 12, 25)

    def test_team_names(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.away_team.name == "Denver Nuggets"
        assert data.home_team.name == "Los Angeles Lakers"

    def test_team_abbreviations(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.away_team.abbreviation == "DEN"
        assert data.home_team.abbreviation == "LAL"

    def test_team_records(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.away_team.wins == 18
        assert data.away_team.losses == 14
        assert data.home_team.wins == 19
        assert data.home_team.losses == 13

    def test_win_pct(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert abs(data.away_team.win_pct - 18 / 32) < 0.001
        assert abs(data.home_team.win_pct - 19 / 32) < 0.001

    def test_quarter_scores(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert len(data.quarter_scores) == 4
        assert data.quarter_scores[0].period == "Q1"
        assert data.quarter_scores[0].away_points == 28
        assert data.quarter_scores[0].home_points == 25

    def test_final_scores(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.final_away == 112
        assert data.final_home == 109

    def test_margin(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.margin == 3

    def test_no_overtime(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.overtime_periods == 0

    def test_player_lines_parsed(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        names = [p.name for p in data.player_lines]
        assert "Nikola Jokic" in names
        assert "LeBron James" in names

    def test_dnp_players_excluded(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        names = [p.name for p in data.player_lines]
        # Aaron Gordon has "Did Not Play"
        assert "Aaron Gordon" not in names

    def test_team_totals_excluded(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        names = [p.name for p in data.player_lines]
        assert "Team Totals" not in names

    def test_jokic_stats(self, boxscore_soup):
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        jokic = next(p for p in data.player_lines if p.name == "Nikola Jokic")
        assert jokic.points == 32
        assert jokic.rebounds == 14
        assert jokic.assists == 11
        assert jokic.team_abbr == "DEN"

    def test_date_fallback_from_game_id(self, boxscore_soup):
        # Remove the h1 to force fallback to game ID
        for tag in boxscore_soup.find_all("h1"):
            tag.decompose()
        data = boxscore.parse(boxscore_soup, "202412250LAL")
        assert data.game_date == date(2024, 12, 25)


# ---------------------------------------------------------------------------
# Play-by-play parsing
# ---------------------------------------------------------------------------


class TestPbpParse:
    def test_snapshots_populated(self, pbp_soup):
        data = pbp.parse(pbp_soup)
        assert len(data.snapshots) > 0

    def test_final_score_in_snapshots(self, pbp_soup):
        data = pbp.parse(pbp_soup)
        last = data.snapshots[-1]
        assert last.away_score == 112
        assert last.home_score == 109

    def test_lead_changes_detected(self, pbp_soup):
        data = pbp.parse(pbp_soup)
        # The fixture has lead changes in Q1 (LAL→DEN), Q2 (DEN→LAL, LAL→DEN),
        # Q3 (DEN→LAL, LAL→DEN). Ties reset the state, so tied→lead is not counted.
        assert data.lead_changes >= 3

    def test_ties_detected(self, pbp_soup):
        data = pbp.parse(pbp_soup)
        # The fixture has ties at 2-2, 8-8, 30-30, 60-60, 86-86, 88-88, 91-91
        assert data.ties >= 5

    def test_no_overtime(self, pbp_soup):
        data = pbp.parse(pbp_soup)
        assert data.overtime_periods == 0

    def test_quarters_tracked(self, pbp_soup):
        data = pbp.parse(pbp_soup)
        quarters_seen = {s.quarter for s in data.snapshots}
        assert 1 in quarters_seen
        assert 4 in quarters_seen

    def test_missing_pbp_table_raises_parse_error(self):
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        with pytest.raises(ParseError) as exc_info:
            pbp.parse(soup)
        assert "pbp" in str(exc_info.value)
