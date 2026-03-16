# NBA Watchability Scorer

Scores NBA games for watchability — without spoiling the result. Give it a basketball-reference.com box score URL **or a date** and it returns a 0–100 score (per game) based on how exciting each game was.

## Installation

```bash
pip install -e .
```

## Usage

**Score a single game** — pass a basketball-reference.com box score URL:

```bash
python -m nba_watchability https://www.basketball-reference.com/boxscores/202503140DEN.html
```

**Score all games on a date** — pass a date in `YYYYMMDD` format. All games are fetched, scored, and printed ranked highest to lowest:

```bash
python -m nba_watchability 20260312
```

### Finding a URL

1. Go to [basketball-reference.com](https://www.basketball-reference.com)
2. Navigate to a team's schedule page (e.g. `basketball-reference.com/teams/LAL/2025_games.html`)
3. Click the **Box Score** link for any game
4. Copy the URL from your browser — it will look like `.../boxscores/YYYYMMDD0HOMETEAM.html`

### Options

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to a custom TOML config file (see below) |
| `--output json` | Output as JSON instead of the default table |
| `--verbose` / `-v` | Show HTTP fetch progress and PBP parsing diagnostics |

## Output

### Text (default)

The default text output is spoiler-free — no final score, no winner, no individual point totals:

```
──────────────── NBA Watchability Score ────────────────
  March 14, 2025  |  Denver Nuggets vs. Los Angeles Lakers

  WATCHABILITY SCORE:  87 / 100   ████████████████████░░░

   Factor              Score
   Closeness              95   ████████████████████
   Back-and-Forth         80   ████████████████░░░░
   Star Moments           75   ███████████████░░░░░
   Team Quality           90   ██████████████████░░
   Clutch Time            85   █████████████████░░░

  *** Spoiler-free: no scores or game outcomes shown ***
```

### JSON (`--output json`)

JSON output **does include the final score and winner** — useful for piping to other tools. Pass `--output json` to enable it:

```json
{
  "total": 87,
  "game_date": "2025-03-14",
  "boxscore_url": "https://www.basketball-reference.com/boxscores/202503140DEN.html",
  "away_team": "Denver Nuggets",
  "away_score": 115,
  "home_team": "Los Angeles Lakers",
  "home_score": 112,
  "winner": "Denver Nuggets",
  "overtime_periods": 0,
  "factors": [
    { "name": "Closeness",      "score": 95, "weight": 0.2353, "contribution": 22.35 },
    { "name": "Back-and-Forth", "score": 80, "weight": 0.1961, "contribution": 15.69 },
    { "name": "Star Moments",   "score": 75, "weight": 0.1569, "contribution": 11.76 },
    { "name": "Team Quality",   "score": 90, "weight": 0.1176, "contribution": 10.59 },
    { "name": "Clutch Time",    "score": 85, "weight": 0.1569, "contribution": 13.34 }
  ]
}
```

## Adjusting the Scoring Weights

Copy the built-in defaults and edit to taste:

```bash
cp nba_watchability/config.default.toml my_weights.toml
python -m nba_watchability --config my_weights.toml <url>
```

Your config file only needs to contain the values you want to override — everything else falls back to the defaults.

### Weights

```toml
[weights]
closeness    = 30   # final margin of victory
lead_changes = 25   # back-and-forth play (includes overtime kicker)
anomalies    = 20   # individual statistical achievements
team_quality = 15   # both teams' win % at game time
clutch       = 20   # scoring intensity in the final 5 minutes
```

Weights are relative — they're automatically normalized, so the scale doesn't matter. Setting everything to equal values (`20, 20, 20, 20, 20`) weights all factors the same.

### Closeness curve

Controls how quickly the score drops as the winning margin grows. The curve is piecewise linear between breakpoints:

```toml
[scoring.closeness]
[[scoring.closeness.breakpoints]]
margin = 0
score  = 1.0   # tie game

[[scoring.closeness.breakpoints]]
margin = 3
score  = 1.0   # 1–3 point game, still maximum

[[scoring.closeness.breakpoints]]
margin = 7
score  = 0.65

[[scoring.closeness.breakpoints]]
margin = 15
score  = 0.25

[[scoring.closeness.breakpoints]]
margin = 21
score  = 0.0   # 21+ point blowout → zero
```

Add or remove breakpoints, or shift the curve, to match your taste. Must be sorted by `margin` ascending.

### Back-and-forth thresholds

```toml
[scoring.lead_changes]
max_for_full_score  = 20    # lead changes needed for a perfect sub-score
ties_max            = 10    # tied moments needed for a perfect sub-score
ties_weight         = 0.3   # how much ties count vs. lead changes within this factor
ot_bonus_per_period = 0.20  # raw score bonus per overtime period (capped at 1.0)
```

The overtime kicker is folded into this factor: going to overtime means the game was too close to decide in regulation, which is the ultimate expression of back-and-forth play. With the default `0.20`, a single-OT game gets +20 points added to Back-and-Forth's raw score before capping at 1.0; a double-OT game gets +40.

### Statistical achievements

Each achievement earns "anomaly points." The sub-score is `min(total / cap_points, 1.0)`.

```toml
[scoring.anomalies]
cap_points = 40   # points needed to reach a score of 1.0

[scoring.anomalies.achievements]
points_50       = 30   # a player scores 50+
points_40_to_49 = 20   # a player scores 40–49
triple_double   = 25   # 10+ pts, reb, AND ast
rebounds_20     = 20   # a player grabs 20+ rebounds
assists_15      = 15   # a player dishes 15+ assists
steals_5        = 15   # a player records 5+ steals
blocks_5        = 10   # a player records 5+ blocks
```

Note: individual point totals are used only for these internal threshold checks and are never displayed.

### Team quality

```toml
[scoring.team_quality]
elite_threshold = 0.600   # avg win% → full score (both teams are contenders)
floor_threshold = 0.300   # avg win% → zero score (both teams are lottery teams)
```

### Clutch time

Clutch time is defined as the final 5 minutes of the 4th quarter (or any overtime period) when the score is within `score_differential` points. Each scoring play in that window adds weighted excitement points:

```toml
[scoring.clutch]
score_differential       = 5    # max point gap to qualify as clutch
max_plays_for_full_score = 10   # excitement points needed for a score of 1.0
play_weight              = 1.0  # weight for a regular clutch scoring play
tie_weight               = 2.0  # weight when the play ties the game
lead_change_weight       = 3.0  # weight when the play changes the lead
```

Tying and lead-changing plays are worth more than routine scoring plays, so a game with a dramatic late comeback scores higher than one where the same team keeps extending its lead.

## Running the tests

```bash
pip install -e ".[dev]"
python -m pytest
```
