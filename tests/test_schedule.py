"""Tests for the schedule (dates-index) scraper."""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from nba_watchability.scraper import schedule
from nba_watchability.exceptions import InvalidDateError, ParseError


def test_date_index_url_valid():
    url = schedule.date_index_url("20260312")
    assert url == "https://www.basketball-reference.com/boxscores/?month=03&day=12&year=2026"


def test_date_index_url_valid_different_date():
    url = schedule.date_index_url("20241225")
    assert url == "https://www.basketball-reference.com/boxscores/?month=12&day=25&year=2024"


def test_date_index_url_invalid_raises():
    with pytest.raises(InvalidDateError):
        schedule.date_index_url("notadate")


def test_date_index_url_too_short_raises():
    with pytest.raises(InvalidDateError):
        schedule.date_index_url("2026031")


def test_date_index_url_too_long_raises():
    with pytest.raises(InvalidDateError):
        schedule.date_index_url("202603120")


def test_parse_boxscore_urls(schedule_soup: BeautifulSoup):
    urls = schedule.parse_boxscore_urls(schedule_soup)
    assert len(urls) == 3
    assert "https://www.basketball-reference.com/boxscores/202603120BOS.html" in urls
    assert "https://www.basketball-reference.com/boxscores/202603120LAL.html" in urls
    assert "https://www.basketball-reference.com/boxscores/202603120GSW.html" in urls


def test_parse_boxscore_urls_no_duplicates(schedule_soup: BeautifulSoup):
    urls = schedule.parse_boxscore_urls(schedule_soup)
    assert len(urls) == len(set(urls))


def test_parse_boxscore_urls_are_full_urls(schedule_soup: BeautifulSoup):
    urls = schedule.parse_boxscore_urls(schedule_soup)
    assert all(u.startswith("https://www.basketball-reference.com/boxscores/") for u in urls)
    assert all(u.endswith(".html") for u in urls)


def test_parse_boxscore_urls_empty_page_raises():
    soup = BeautifulSoup("<html><body><p>No games today.</p></body></html>", "lxml")
    with pytest.raises(ParseError):
        schedule.parse_boxscore_urls(soup)
