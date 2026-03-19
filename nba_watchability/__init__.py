"""nba-watchability: score NBA games for watchability without spoilers."""

__version__ = "0.1.0"

from .api import score_game, score_date
from .models import WatchabilityResult, GameData, BoxScoreData, PlayByPlayData, FactorScore
from .config import Config, load as load_config
from .exceptions import NbaWatchabilityError, InvalidUrlError, NetworkError

__all__ = [
    "score_game", "score_date",
    "WatchabilityResult", "GameData", "BoxScoreData", "PlayByPlayData", "FactorScore",
    "Config", "load_config",
    "NbaWatchabilityError", "InvalidUrlError", "NetworkError",
]
