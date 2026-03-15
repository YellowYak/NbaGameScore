"""CLI entry point and rich output rendering for nba-watchability."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box as rich_box

from . import config as config_module
from . import scorer as scorer_module
from .exceptions import NbaWatchabilityError
from .models import WatchabilityResult
from .scraper import http as http_module
from .scraper import boxscore as boxscore_module
from .scraper import pbp as pbp_module
from .models import GameData


console = Console()
err_console = Console(stderr=True)


def _render_bar(score: float, width: int = 20) -> str:
    """Render a simple block bar for a 0.0–1.0 score."""
    filled = round(score * width)
    empty = width - filled
    return "█" * filled + "░" * empty


def _render_result_text(result: WatchabilityResult) -> None:
    """Print a rich, spoiler-free watchability report to the terminal."""
    # Header
    date_str = result.game_date.strftime("%B %-d, %Y") if sys.platform != "win32" else result.game_date.strftime("%B %d, %Y").replace(" 0", " ")
    game_line = f"{date_str}  |  {result.away_team} vs. {result.home_team}"

    # Score colour: green ≥ 70, yellow 40–69, red < 40
    total = result.total
    if total >= 70:
        score_colour = "bold green"
    elif total >= 40:
        score_colour = "bold yellow"
    else:
        score_colour = "bold red"

    console.print()
    console.rule("[bold cyan]NBA Watchability Score[/bold cyan]")
    console.print(f"  [dim]{game_line}[/dim]")
    console.print()
    console.print(f"  WATCHABILITY SCORE:  [{score_colour}]{total} / 100[/{score_colour}]  {_render_bar(total / 100, 24)}")
    console.print()

    # Factor table
    table = Table(box=rich_box.SIMPLE_HEAD, show_header=True, header_style="bold")
    table.add_column("Factor", style="", min_width=18)
    table.add_column("Score", justify="right", min_width=6)
    table.add_column("", min_width=22)

    for factor in result.factors:
        ds = factor.display_score
        if ds >= 70:
            colour = "green"
        elif ds >= 40:
            colour = "yellow"
        else:
            colour = "red"
        bar = _render_bar(factor.raw_score, 20)
        table.add_row(
            factor.name,
            f"[{colour}]{ds}[/{colour}]",
            f"[{colour}]{bar}[/{colour}]",
        )

    console.print(table)
    console.print(f"  [dim italic]*** Spoiler-free: no scores or game outcomes shown ***[/dim italic]")
    console.print()


def _render_result_json(result: WatchabilityResult) -> None:
    """Print the result as JSON to stdout."""
    data = {
        "total": result.total,
        "game_date": result.game_date.isoformat(),
        "away_team": result.away_team,
        "home_team": result.home_team,
        "overtime_periods": result.overtime_periods,
        "factors": [
            {
                "name": f.name,
                "score": f.display_score,
                "weight": round(f.weight, 4),
                "contribution": round(f.contribution, 2),
            }
            for f in result.factors
        ],
    }
    click.echo(json.dumps(data, indent=2))


@click.command()
@click.argument("url")
@click.option(
    "--config",
    "config_path",
    default=None,
    type=click.Path(exists=False, dir_okay=False),
    help="Path to a custom TOML config file (overrides built-in defaults).",
)
@click.option(
    "--output",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Show HTTP fetch progress and parse warnings.",
)
def main(url: str, config_path: str | None, output: str, verbose: bool) -> None:
    """Score the watchability of an NBA game without spoiling the result.

    URL should be a basketball-reference.com boxscore URL, e.g.:

      https://www.basketball-reference.com/boxscores/202412250LAL.html
    """
    try:
        # Load config
        cfg = config_module.load(config_path)

        # Derive game ID and PBP URL
        game_id = http_module.extract_game_id(url)
        pbp_url = http_module.pbp_url_from_boxscore_url(url)

        # Fetch and parse
        session = http_module.BbrefSession(cfg.http)

        if verbose:
            err_console.print(f"[dim]Fetching box score…[/dim]")
        box_soup = session.get_soup(url, verbose=verbose)
        box_data = boxscore_module.parse(box_soup, game_id)

        if verbose:
            err_console.print(f"[dim]Fetching play-by-play…[/dim]")
        pbp_soup = session.get_soup(pbp_url, verbose=verbose)
        pbp_data = pbp_module.parse(pbp_soup)

        if verbose:
            q4_snaps = [s for s in pbp_data.snapshots if s.quarter == 4]
            clutch_snaps = [s for s in q4_snaps if s.seconds_elapsed >= 420]
            ot_snaps = [s for s in pbp_data.snapshots if s.quarter >= 5]
            quarters_seen = sorted({s.quarter for s in pbp_data.snapshots})
            err_console.print(
                f"[dim]PBP: {len(pbp_data.snapshots)} total snaps | "
                f"quarters seen: {quarters_seen} | "
                f"Q4 snaps: {len(q4_snaps)} | "
                f"clutch-window snaps (Q4 last 5 min): {len(clutch_snaps)} | "
                f"OT snaps: {len(ot_snaps)} | "
                f"lead changes: {pbp_data.lead_changes} | ties: {pbp_data.ties}[/dim]"
            )

        game = GameData(box=box_data, pbp=pbp_data)

        # Score
        result = scorer_module.score(game, cfg)

        # Output
        if output == "json":
            _render_result_json(result)
        else:
            _render_result_text(result)

    except NbaWatchabilityError as exc:
        err_console.print(
            Panel(
                str(exc),
                title="[bold red]Error[/bold red]",
                border_style="red",
            )
        )
        sys.exit(1)
