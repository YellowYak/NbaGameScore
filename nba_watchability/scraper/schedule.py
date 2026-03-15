"""Scraper for the basketball-reference dates-index page."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..exceptions import InvalidDateError, ParseError

_DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_BOXSCORE_HREF_RE = re.compile(r"/boxscores/(\d{8}0[A-Z]{2,3})\.html")
_BASE = "https://www.basketball-reference.com"


def date_index_url(date_str: str) -> str:
    """Build the BBRef dates-page URL from an 8-digit YYYYMMDD string.

    Raises InvalidDateError if *date_str* doesn't match the expected format.
    """
    m = _DATE_RE.match(date_str)
    if not m:
        raise InvalidDateError(date_str)
    year, month, day = m.group(1), m.group(2), m.group(3)
    return f"{_BASE}/boxscores/?month={month}&day={day}&year={year}"


def parse_boxscore_urls(soup: BeautifulSoup) -> list[str]:
    """Extract all boxscore URLs from a BBRef dates-index page.

    Returns a list of full URLs like:
        ["https://www.basketball-reference.com/boxscores/20260312BOS.html", ...]

    Raises ParseError if no game links are found.
    """
    seen: dict[str, None] = {}  # ordered set via dict keys
    for tag in soup.find_all("a", href=True):
        href: str = tag["href"]
        if _BOXSCORE_HREF_RE.search(href):
            full_url = _BASE + href
            seen[full_url] = None

    if not seen:
        raise ParseError("schedule", "boxscore links")

    return list(seen)
