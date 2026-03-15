"""Custom exception hierarchy for nba-watchability."""


class NbaWatchabilityError(Exception):
    """Base exception for all nba-watchability errors."""


class InvalidUrlError(NbaWatchabilityError):
    """URL doesn't match the expected basketball-reference boxscore pattern."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(
            f"Not a valid basketball-reference boxscore URL: {url!r}\n"
            "Expected format: https://www.basketball-reference.com/boxscores/YYYYMMDD0TEAM.html"
        )


class ConfigError(NbaWatchabilityError):
    """Config file is missing a required field or contains an invalid value."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        super().__init__(f"Config error in {path!r}: {message}")


class NetworkError(NbaWatchabilityError):
    """An HTTP request failed."""

    def __init__(self, url: str, cause: Exception) -> None:
        self.url = url
        self.cause = cause
        super().__init__(f"Network error fetching {url!r}: {cause}")


class HttpError(NetworkError):
    """A non-2xx HTTP response was received."""

    def __init__(self, url: str, status_code: int) -> None:
        self.status_code = status_code
        # Bypass NetworkError.__init__ — no cause exception to wrap
        NbaWatchabilityError.__init__(
            self, f"HTTP {status_code} fetching {url!r}"
        )
        self.url = url
        self.cause = None  # type: ignore[assignment]


class RateLimitError(HttpError):
    """Basketball-reference returned 429 Too Many Requests."""

    def __init__(self, url: str) -> None:
        super().__init__(url, 429)
        NbaWatchabilityError.__init__(
            self,
            f"Rate limited (HTTP 429) fetching {url!r}. Wait a moment and try again.",
        )


class ParseError(NbaWatchabilityError):
    """An expected HTML element was not found; the page layout may have changed."""

    def __init__(self, page: str, element: str) -> None:
        self.page = page
        self.element = element
        super().__init__(
            f"Could not parse the {page!r} page — expected element not found: {element!r}.\n"
            "Basketball-reference may have changed its layout."
        )
