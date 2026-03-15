"""Shared pytest fixtures."""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def boxscore_soup() -> BeautifulSoup:
    html = (FIXTURES / "boxscore_sample.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


@pytest.fixture()
def pbp_soup() -> BeautifulSoup:
    html = (FIXTURES / "pbp_sample.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


@pytest.fixture()
def schedule_soup() -> BeautifulSoup:
    html = (FIXTURES / "schedule_sample.html").read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")
