"""Parse the basketball-reference play-by-play page."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..exceptions import ParseError
from ..models import PlayByPlayData, ScoreSnapshot

# Matches a score like "102-98" in the score column
_SCORE_RE = re.compile(r"^(\d+)-(\d+)$")

# Matches a time like "11:47.0" or "0:00.1"
_TIME_RE = re.compile(r"^(\d+):(\d+(?:\.\d+)?)$")


def _parse_time_to_seconds(time_str: str) -> int:
    """Convert 'MM:SS.d' (time remaining in quarter) to integer seconds elapsed.

    BBRef shows time remaining, so we subtract from 12 minutes (720 s)
    for regulation quarters, or 5 minutes (300 s) for OT quarters.
    """
    m = _TIME_RE.match(time_str.strip())
    if not m:
        return 0
    minutes = int(m.group(1))
    seconds = float(m.group(2))
    total_remaining = int(minutes * 60 + seconds)
    return total_remaining  # caller converts to elapsed by subtracting from period length


def _quarter_length(quarter: int) -> int:
    """Return the length of a quarter in seconds."""
    return 720 if quarter <= 4 else 300


def _parse_quarter_from_header(text: str) -> int | None:
    """Return the quarter number (1-based) from a section header row, or None."""
    text = text.strip().lower()
    # Match "1st Q", "1st Quarter", "2nd Q", "3rd Q", "4th Q", etc.
    m = re.match(r"^(\d+)(?:st|nd|rd|th)\s+q(?:uarter)?", text)
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 4 else None
    # OT periods: "1st OT", "1st Overtime", "2nd OT", etc.
    m = re.match(r"^(\d+)(?:st|nd|rd|th)\s+o(?:t|vertime)", text)
    if m:
        return 4 + int(m.group(1))
    if "overtime" in text or re.search(r"\bot\b", text):
        return 5
    return None


def parse(soup: BeautifulSoup) -> PlayByPlayData:
    """Parse a pre-fetched (comment-unwrapped) play-by-play page soup.

    Returns:
        PlayByPlayData with snapshots, lead_changes, ties, and overtime_periods.
    """
    table = soup.find("table", id="pbp")
    if not table:
        raise ParseError("pbp", "table#pbp")

    snapshots: list[ScoreSnapshot] = []
    current_quarter = 1
    last_away = 0
    last_home = 0

    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        cell_texts = [c.get_text(strip=True) for c in cells]

        # Detect quarter header rows: check text first (robust against HTML structure
        # changes), then fall back to colspan/single-cell structural detection.
        q = _parse_quarter_from_header(cell_texts[0])
        if q is not None:
            current_quarter = q
            continue
        if len(cells) == 1 or (cells[0].get("colspan") and int(cells[0].get("colspan", 1)) > 1):
            continue  # some other header/divider row — skip but don't reset quarter

        # A play row typically has 6 cells:
        # [0] time | [1] away action | [2] score | [3] home action | [4+] extra
        # Sometimes there are only 5 cells (combined score+detail columns).
        # We look for the score column by scanning for "X-Y" patterns.
        if len(cell_texts) < 3:
            continue

        time_str = cell_texts[0]
        if not _TIME_RE.match(time_str):
            # Not a play row
            continue

        # Find the score cell — scan all cells for "X-Y" format
        score_text = None
        for ct in cell_texts[1:]:
            if _SCORE_RE.match(ct):
                score_text = ct
                break

        if score_text:
            m = _SCORE_RE.match(score_text)
            if m:
                last_away = int(m.group(1))
                last_home = int(m.group(2))

        remaining = _parse_time_to_seconds(time_str)
        period_len = _quarter_length(current_quarter)
        elapsed = period_len - remaining

        snapshots.append(
            ScoreSnapshot(
                quarter=current_quarter,
                seconds_elapsed=max(elapsed, 0),
                away_score=last_away,
                home_score=last_home,
            )
        )

    if not snapshots:
        raise ParseError("pbp", "play-by-play rows (table#pbp appears empty)")

    # Count lead changes and ties in a single pass
    lead_changes = 0
    ties = 0
    prev_diff: int | None = None

    for snap in snapshots:
        diff = snap.away_score - snap.home_score
        if diff == 0:
            ties += 1
            prev_diff = 0
        else:
            if prev_diff is not None and prev_diff != 0:
                if (diff > 0) != (prev_diff > 0):
                    lead_changes += 1
            prev_diff = diff

    overtime_periods = max((s.quarter - 4 for s in snapshots if s.quarter > 4), default=0)

    return PlayByPlayData(
        snapshots=tuple(snapshots),
        lead_changes=lead_changes,
        ties=ties,
        overtime_periods=overtime_periods,
    )
