"""Parse the basketball-reference box score page."""

from __future__ import annotations

import re
from datetime import date

from bs4 import BeautifulSoup

from ..exceptions import ParseError
from ..models import BoxScoreData, PlayerLine, QuarterScore, TeamSnapshot

# Matches a W-L record like "(15-20)" or "(15-20)*"
_RECORD_RE = re.compile(r"\(?(\d+)-(\d+)")

# Extracts a game date from an 8-digit game ID prefix (YYYYMMDD)
_DATE_FROM_ID_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})")


def _parse_int(value: str | None, default: int = 0) -> int:
    """Return int from a cell string, falling back to default."""
    if not value or not value.strip() or value.strip() in ("", "Did Not Play", "Did Not Dress", "Not With Team", "Inactive"):
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


def _parse_minutes(mp: str | None) -> int:
    """Convert a 'MM:SS' string to integer minutes."""
    if not mp or not mp.strip() or ":" not in mp:
        return 0
    parts = mp.strip().split(":")
    try:
        return int(parts[0])
    except ValueError:
        return 0


def _extract_game_date(soup: BeautifulSoup, game_id: str) -> date:
    """Extract the game date from the page title or game ID."""
    # Try page title first: "Team A at Team B Box Score, Month DD, YYYY"
    title_tag = soup.find("h1")
    if title_tag:
        text = title_tag.get_text()
        # look for a pattern like "January 15, 2025"
        m = re.search(r"([A-Z][a-z]+ \d{1,2}, \d{4})", text)
        if m:
            try:
                from datetime import datetime
                return datetime.strptime(m.group(1), "%B %d, %Y").date()
            except ValueError:
                pass

    # Fall back to game ID (first 8 chars = YYYYMMDD)
    m = _DATE_FROM_ID_RE.match(game_id)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    raise ParseError("boxscore", "game date")


def _extract_team_snapshots(
    soup: BeautifulSoup,
) -> tuple[TeamSnapshot, TeamSnapshot]:
    """Extract both teams' names, abbreviations, and W-L records.

    Returns (away_team, home_team).
    """
    # The scorebox div contains team names and records
    scorebox = soup.find("div", class_="scorebox")
    if not scorebox:
        raise ParseError("boxscore", "div.scorebox")

    team_divs = scorebox.find_all("div", recursive=False)
    # The scorebox has two main child divs — one per team — then a meta div
    team_sections = [d for d in team_divs if d.find("strong")]
    if len(team_sections) < 2:
        raise ParseError("boxscore", "team sections in div.scorebox")

    teams: list[TeamSnapshot] = []
    for section in team_sections[:2]:
        # Team name is inside <strong><a href="/teams/LAL/...">Los Angeles Lakers</a></strong>
        name_tag = section.find("strong")
        if not name_tag:
            raise ParseError("boxscore", "team name tag")
        name = name_tag.get_text(strip=True)

        # Abbreviation from the team link href
        team_link = name_tag.find("a")
        abbr = "UNK"
        if team_link and team_link.get("href"):
            href = team_link["href"]
            m = re.search(r"/teams/([A-Z]{2,3})/", href)
            if m:
                abbr = m.group(1)

        # W-L record: look for text matching "(W-L)" near the team div
        wins, losses = 0, 0
        section_text = section.get_text()
        m = _RECORD_RE.search(section_text)
        if m:
            wins = int(m.group(1))
            losses = int(m.group(2))

        teams.append(TeamSnapshot(name=name, abbreviation=abbr, wins=wins, losses=losses))

    return teams[0], teams[1]


def _extract_line_score(
    soup: BeautifulSoup, away_abbr: str, home_abbr: str
) -> tuple[tuple[QuarterScore, ...], int]:
    """Parse the quarter-by-quarter line score table.

    Returns (quarter_scores, overtime_periods).
    """
    table = soup.find("table", id="line_score")
    if not table:
        raise ParseError("boxscore", "table#line_score")

    thead = table.find("thead")
    if not thead:
        raise ParseError("boxscore", "line_score thead")

    # Build period labels from header row
    header_cells = thead.find_all("th")
    period_labels: list[str] = []
    for cell in header_cells:
        text = cell.get_text(strip=True)
        if text in ("", "Team"):
            continue
        if text == "T":
            break  # stop before the total column
        period_labels.append(text)

    # Map numeric "1","2","3","4" to "Q1"–"Q4"; "OT","2OT",... to "OT1","OT2",...
    def _label(raw: str) -> str:
        if raw.isdigit():
            return f"Q{raw}"
        # BBRef uses "OT", "2OT", "3OT" etc.
        if raw == "OT":
            return "OT1"
        m = re.match(r"^(\d+)OT$", raw)
        if m:
            return f"OT{m.group(1)}"
        return raw

    period_labels = [_label(p) for p in period_labels]

    # Extract the two data rows (away, home)
    tbody = table.find("tbody")
    if not tbody:
        raise ParseError("boxscore", "line_score tbody")

    rows = tbody.find_all("tr")
    if len(rows) < 2:
        raise ParseError("boxscore", "line_score data rows")

    def _row_scores(row) -> list[int]:
        cells = row.find_all("td")
        scores: list[int] = []
        for cell in cells:
            stat = cell.get("data-stat", "")
            if stat == "team_id":
                continue
            text = cell.get_text(strip=True)
            if text == "T":
                continue
            try:
                scores.append(int(text))
            except ValueError:
                scores.append(0)
        return scores

    away_scores = _row_scores(rows[0])
    home_scores = _row_scores(rows[1])

    # Trim to the number of labelled periods (excludes the total column)
    n = min(len(period_labels), len(away_scores), len(home_scores))
    quarter_scores = tuple(
        QuarterScore(
            period=period_labels[i],
            away_points=away_scores[i],
            home_points=home_scores[i],
        )
        for i in range(n)
    )

    overtime_periods = sum(1 for q in quarter_scores if q.period.startswith("OT"))
    return quarter_scores, overtime_periods


def _extract_player_lines(
    soup: BeautifulSoup, away_abbr: str, home_abbr: str
) -> tuple[PlayerLine, ...]:
    """Parse both teams' player stat tables."""
    lines: list[PlayerLine] = []

    for team_abbr in (away_abbr, home_abbr):
        table_id = f"box-{team_abbr}-game-basic"
        table = soup.find("table", id=table_id)
        if not table:
            # Try case-insensitive fallback
            table = soup.find(
                "table",
                id=lambda x: x and x.lower() == table_id.lower(),
            )
        if not table:
            raise ParseError("boxscore", f"table#{table_id}")

        tbody = table.find("tbody")
        if not tbody:
            continue

        for row in tbody.find_all("tr"):
            # Skip section headers (e.g., "Starters", "Reserves")
            if row.get("class") and "thead" in row.get("class", []):
                continue

            name_cell = row.find(["td", "th"], attrs={"data-stat": "player"})
            if not name_cell:
                continue

            name = name_cell.get_text(strip=True)
            if not name or name in ("Team Totals",):
                continue

            # Check for DNP rows
            mp_cell = row.find("td", attrs={"data-stat": "mp"})
            mp_text = mp_cell.get_text(strip=True) if mp_cell else ""
            if mp_text in ("Did Not Play", "Did Not Dress", "Not With Team", "Inactive", ""):
                continue

            def _get(stat: str) -> int:
                cell = row.find("td", attrs={"data-stat": stat})
                return _parse_int(cell.get_text(strip=True) if cell else None)

            lines.append(
                PlayerLine(
                    name=name,
                    team_abbr=team_abbr,
                    minutes=_parse_minutes(mp_text),
                    points=_get("pts"),
                    rebounds=_get("trb"),
                    assists=_get("ast"),
                    steals=_get("stl"),
                    blocks=_get("blk"),
                    turnovers=_get("tov"),
                    fg_made=_get("fg"),
                    fg_attempted=_get("fga"),
                )
            )

    return tuple(lines)


def parse(soup: BeautifulSoup, game_id: str) -> BoxScoreData:
    """Parse a pre-fetched (comment-unwrapped) box score page soup.

    Args:
        soup: BeautifulSoup tree from the box score page (with comments unwrapped).
        game_id: The BBRef game ID (e.g. "202412250LAL"), used as fallback for date.

    Returns:
        BoxScoreData with all fields populated.
    """
    game_date = _extract_game_date(soup, game_id)
    away_team, home_team = _extract_team_snapshots(soup)
    quarter_scores, _ot = _extract_line_score(soup, away_team.abbreviation, home_team.abbreviation)
    player_lines = _extract_player_lines(soup, away_team.abbreviation, home_team.abbreviation)

    return BoxScoreData(
        game_date=game_date,
        away_team=away_team,
        home_team=home_team,
        quarter_scores=quarter_scores,
        player_lines=player_lines,
    )
