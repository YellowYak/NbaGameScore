"""HTTP layer: fetching and pre-processing basketball-reference pages."""

from __future__ import annotations

import re
import time

from curl_cffi import requests
from bs4 import BeautifulSoup, Comment

from ..config import HttpConfig
from ..exceptions import HttpError, InvalidUrlError, NetworkError, RateLimitError

# Regex to validate and extract the game ID from a BBRef boxscore URL.
_BOXSCORE_RE = re.compile(
    r"basketball-reference\.com/boxscores/(?P<game_id>[0-9]{8}0[A-Z]{2,3})\.html"
)


def extract_game_id(url: str) -> str:
    """Return the game ID from a basketball-reference boxscore URL.

    Raises InvalidUrlError if the URL doesn't match the expected pattern.
    """
    match = _BOXSCORE_RE.search(url)
    if not match:
        raise InvalidUrlError(url)
    return match.group("game_id")


def pbp_url_from_boxscore_url(boxscore_url: str) -> str:
    """Derive the play-by-play URL from a boxscore URL."""
    game_id = extract_game_id(boxscore_url)
    return f"https://www.basketball-reference.com/boxscores/pbp/{game_id}.html"


def _unwrap_comments(soup: BeautifulSoup) -> BeautifulSoup:
    """Parse HTML comment nodes and graft their inner content back into the tree.

    Basketball-reference wraps most stat tables inside HTML comments to make
    scraping harder. This function makes those tables visible to BeautifulSoup.
    """
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        inner = BeautifulSoup(str(comment), "lxml")
        comment.replace_with(inner)
    return soup


class BbrefSession:
    """A requests session configured for polite basketball-reference scraping."""

    # curl_cffi impersonation target — Chrome 120 TLS fingerprint
    _IMPERSONATE = "chrome120"

    def __init__(self, cfg: HttpConfig) -> None:
        self._cfg = cfg
        self._session = requests.Session(impersonate=self._IMPERSONATE)
        self._last_request_time: float = 0.0

    def _wait(self) -> None:
        """Enforce the configured delay between consecutive requests."""
        elapsed = time.monotonic() - self._last_request_time
        remaining = self._cfg.request_delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def get_soup(self, url: str, *, verbose: bool = False) -> BeautifulSoup:
        """Fetch a URL, unwrap BBRef comment tables, and return a BeautifulSoup tree.

        Raises:
            NetworkError: on connection / timeout failures
            RateLimitError: on HTTP 429
            HttpError: on other non-2xx responses
        """
        self._wait()
        if verbose:
            print(f"  Fetching: {url}")
        try:
            response = self._session.get(url, timeout=self._cfg.timeout)
        except requests.errors.RequestsError as exc:
            raise NetworkError(url, exc) from exc
        finally:
            self._last_request_time = time.monotonic()

        if response.status_code == 429:
            raise RateLimitError(url)
        if response.status_code == 404:
            raise HttpError(url, 404)
        if not response.ok:
            raise HttpError(url, response.status_code)

        soup = BeautifulSoup(response.text, "lxml")
        return _unwrap_comments(soup)
