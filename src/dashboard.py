"""

The dashboard reads JSON output produced by the streaming job and renders:
- live player, referee, and ball positions;
- optional movement trails;
- optional heat map overlays;
- live sprint and possession summaries;
- match event notifications.

The module is intentionally UI-focused. Data cleaning, chunking, and streaming
logic are handled by the separate pipeline scripts.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import time
import unicodedata
from pathlib import Path
from typing import Any

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config import (
    FIELD_X_MAX,
    FIELD_X_MIN,
    FIELD_Y_MAX,
    FIELD_Y_MIN,
    REFEREE,
    TEAM_A_PLAYERS,
    TEAM_B_PLAYERS,
)

from src.statistics_tab import render_statistics_tab

JsonDict = dict[str, Any]
Position = dict[str, Any]
DisplayObject = dict[str, Any]
PossessionInterval = dict[str, float]
PossessionData = dict[str, list[PossessionInterval]]

POSITIONS_PATH = Path("data/output/live_positions/positions.json")
STATS_PATH = Path("data/output/live_positions/stats_1m.json")
METADATA_PATH = Path("data/metadata")
RAW_REFEREE_EVENTS_PATH = Path("data/raw/referee-events")

POSSESSION_PATHS = [
    METADATA_PATH / "Ball Possession",
    RAW_REFEREE_EVENTS_PATH / "Ball Possession",
]

ALL_BALL_IDS = {4, 8, 10, 12}

REFRESH_SECONDS = 0.15
SECOND_HALF_OFFSET_SECONDS = 1800.0
TRAIL_BATCH_LIMIT = 5

HEATMAP_X_BINS = 13
HEATMAP_Y_BINS = 8
HEATMAP_DATA_X_MIN = -65000
HEATMAP_DATA_X_MAX = 65000
HEATMAP_DATA_Y_MIN = -34000
HEATMAP_DATA_Y_MAX = 34000

# The raw tracking coordinates are transformed to match the pitch drawing in the
# dashboard. Keep the same transform for dots and heat-map cells.
POSITION_SCALE_X = 2.0
POSITION_SCALE_Y = 1.0
POSITION_OFFSET_X = -6000.0
POSITION_OFFSET_Y = -31000.0
HEATMAP_OFFSET_X = 0.0
HEATMAP_OFFSET_Y = POSITION_OFFSET_Y

TEAM_A = "Team A"
TEAM_B = "Team B"

TEAM_A_COLORS = {
    "Goalkeeper": "#00FFFF",
    "Defender": "#4169E1",
    "Midfielder": "#0000CD",
    "Forward": "#000080",
    "Player": "royalblue",
}
TEAM_B_COLORS = {
    "Goalkeeper": "#FFD700",
    "Defender": "#FF6347",
    "Midfielder": "#DC143C",
    "Forward": "#8B0000",
    "Player": "tomato",
}

SPRINT_SPEED_KMH = 24.0
HIGH_SPEED_RUN_KMH = 14.0
LOW_SPEED_RUN_KMH = 11.0
TROT_SPEED_KMH = 1.0

LOOSE_BALL = "Loose Ball"
ROLLING_POSSESSION_WINDOW_SECONDS = 60.0

POSSESSION_HIGH_CONFIDENCE_MM = 1500.0
POSSESSION_MEDIUM_CONFIDENCE_MM = 3000.0
POSSESSION_LOW_CONFIDENCE_MM = 5000.0

LOGGER = logging.getLogger(__name__)


def load_json_file(path: Path) -> JsonDict | None:
    """Loads a JSON dictionary from disk.

    Args:
        path: JSON file path.

    Returns:
        Parsed JSON data, or ``None`` when the file does not exist or cannot be
        decoded.
    """
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as json_file:
            data = json.load(json_file)
    except json.JSONDecodeError:
        LOGGER.warning("Could not decode JSON file: %s", path)
        return None

    return data if isinstance(data, dict) else None


def load_positions() -> JsonDict | None:
    """Loads the latest live position state."""
    return load_json_file(POSITIONS_PATH)


def load_stats() -> JsonDict | None:
    """Loads the latest rolling speed statistics."""
    return load_json_file(STATS_PATH)


def parse_event_time(time_text: str, half_offset: float) -> float | None:
    """Converts a metadata event timestamp to match seconds.

    Args:
        time_text: Timestamp string in ``HH:MM:SS.s`` format.
        half_offset: Offset to add for the current half.

    Returns:
        Match time in seconds, or ``None`` when parsing fails.
    """
    if str(time_text) == "0":
        return half_offset

    try:
        hours, minutes, seconds = str(time_text).split(":")
        return (
            int(hours) * 3_600
            + int(minutes) * 60
            + float(seconds)
            + half_offset
        )
    except ValueError:
        return None

def read_possession_rows(file_path: Path) -> list[list[str]]:
    """Reads semicolon-separated possession metadata rows."""
    rows: list[list[str]] = []

    with file_path.open("r", encoding="latin-1", newline="") as possession_file:
        reader = csv.reader(possession_file, delimiter=";")

        for row in reader:
            cleaned_row = [value.strip() for value in row if value.strip()]
            if cleaned_row:
                rows.append(cleaned_row)

    return rows

def extract_times_from_row(row: list[str]) -> list[float]:
    """Extracts parseable timestamps from one metadata row."""
    candidate_fields = row[2:] if len(row) >= 3 and row[0].isdigit() else row
    time_values: list[float] = []

    for value in candidate_fields:
        if ":" not in value and value != "0":
            continue

        parsed_time = parse_possession_time(value)
        if parsed_time is not None:
            time_values.append(parsed_time)

    return time_values

def extract_times_from_files(file_paths: list[Path]) -> list[float]:
    """Extracts all timestamps from multiple files."""
    times: list[float] = []

    for file_path in file_paths:
        for row in read_possession_rows(file_path):
            times.extend(extract_times_from_row(row))

    return times


def read_match_event_file(
    folder: str,
    filename: str,
    half_offset: float,
    event_prefix: str,
    icon: str,
    events: list[JsonDict],
) -> None:
    """Reads one semicolon-separated match-event metadata file.

    The DEBS metadata files contain summary rows at the bottom. Those rows are
    ignored by requiring a numeric event id and a parseable timestamp.
    """
    file_path = METADATA_PATH / folder / filename
    if not file_path.exists():
        return

    with file_path.open("r", encoding="latin-1") as event_file:
        for line in event_file:
            parts = line.strip().split(";")
            if len(parts) < 3 or not parts[0].isdigit():
                continue

            event_time = parse_event_time(parts[2], half_offset)
            if event_time is None:
                continue

            events.append(
                {
                    "second": event_time,
                    "msg": f"{icon} **{event_prefix}**: {parts[1]}",
                }
            )


def load_match_events() -> list[JsonDict]:
    """Loads shot and interruption events from the metadata folder."""
    events: list[JsonDict] = []

    read_match_event_file(
        "Game Interruption",
        "1st Half.csv",
        0.0,
        "Match Control",
        "🛑",
        events,
    )
    read_match_event_file(
        "Game Interruption",
        "2nd Half.csv",
        SECOND_HALF_OFFSET_SECONDS,
        "Match Control",
        "🛑",
        events,
    )
    read_match_event_file(
        "Shot on Goal",
        "1st Half.csv",
        0.0,
        "Shot by",
        "⚽",
        events,
    )
    read_match_event_file(
        "Shot on Goal",
        "2nd Half.csv",
        SECOND_HALF_OFFSET_SECONDS,
        "Shot by",
        "⚽",
        events,
    )

    return sorted(events, key=lambda event: event["second"])


def parse_possession_time(time_text: str) -> float | None:
    """Parses possession timestamps from metadata files."""
    text = str(time_text).strip().replace(",", ".")

    if not text:
        return None

    if text == "0":
        return 0.0

    try:
        parts = text.split(":")

        if len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3_600 + int(minutes) * 60 + float(seconds)

        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)

    except ValueError:
        return None

    return None

def infer_second_half_offset(second_half_files: list[Path]) -> float:
    """Infers whether second-half files are relative or already absolute."""
    times = extract_times_from_files(second_half_files)

    if not times:
        return SECOND_HALF_OFFSET_SECONDS

    earliest_time = min(times)

    if earliest_time >= SECOND_HALF_OFFSET_SECONDS - 60.0:
        return 0.0

    return SECOND_HALF_OFFSET_SECONDS


def is_begin_event(event_text: str) -> bool:
    """Returns True if a row starts a possession interval."""
    text = event_text.casefold()
    return "begin" in text or "start" in text


def is_end_event(event_text: str) -> bool:
    """Returns True if a row ends a possession interval."""
    text = event_text.casefold()
    return "end" in text or "stop" in text


def add_possession_interval(
    possession_data: PossessionData,
    player_name: str,
    start_time: float,
    end_time: float,
) -> None:
    """Adds one valid possession interval."""
    if end_time <= start_time:
        LOGGER.warning(
            "Skipping invalid possession interval for %s: %.3f -> %.3f",
            player_name,
            start_time,
            end_time,
        )
        return

    possession_data.setdefault(player_name, []).append(
        {"start": start_time, "end": end_time}
    )


def process_possession_file(
    file_path: Path,
    possession_data: PossessionData,
    half_offset: float = 0.0,
) -> None:
    """Adds possession intervals from one player metadata file."""
    player_name = resolve_player_name(file_path.stem)

    current_begin: float | None = None
    current_offset = half_offset
    last_raw_time = -1.0

    for row in read_possession_rows(file_path):
        if len(row) < 3:
            continue

        event_text = row[1] if row[0].isdigit() else " ".join(row)
        time_values = extract_times_from_row(row)

        if not time_values:
            continue

        raw_time = time_values[0]

        # Handles single files where the second half starts again at 00:00.
        if raw_time < last_raw_time and half_offset == 0.0:
            current_offset = SECOND_HALF_OFFSET_SECONDS

        last_raw_time = raw_time
        event_time = raw_time + current_offset

        if is_begin_event(event_text):
            current_begin = event_time
            continue

        if is_end_event(event_text):
            if current_begin is not None:
                add_possession_interval(
                    possession_data,
                    player_name,
                    current_begin,
                    event_time,
                )
                current_begin = None
            continue

        # Fallback for interval-style rows: id;event;start;end
        if len(time_values) >= 2:
            add_possession_interval(
                possession_data,
                player_name,
                time_values[0] + current_offset,
                time_values[1] + current_offset,
            )

    if current_begin is not None:
        LOGGER.warning(
            "Unclosed possession interval in %s starting at %.3f",
            file_path,
            current_begin,
        )


def merge_possession_intervals(possession_data: PossessionData) -> PossessionData:
    """Sorts and merges overlapping intervals per player."""
    merged_data: PossessionData = {}

    for player_name, intervals in possession_data.items():
        sorted_intervals = sorted(
            [
                interval
                for interval in intervals
                if interval["end"] > interval["start"]
            ],
            key=lambda interval: interval["start"],
        )

        merged_intervals: list[PossessionInterval] = []

        for interval in sorted_intervals:
            if not merged_intervals:
                merged_intervals.append(interval)
                continue

            previous = merged_intervals[-1]

            if interval["start"] <= previous["end"]:
                previous["end"] = max(previous["end"], interval["end"])
            else:
                merged_intervals.append(interval)

        merged_data[player_name] = merged_intervals

    return merged_data


def load_possession_data() -> PossessionData:
    """Loads all player ball-possession intervals."""
    possession_path = find_possession_path()

    if possession_path is None:
        LOGGER.warning("No possession metadata path found.")
        return {}

    possession_data: PossessionData = {}

    first_half_dir = possession_path / "1st Half"
    second_half_dir = possession_path / "2nd Half"

    if first_half_dir.exists() or second_half_dir.exists():
        first_half_files = (
            sorted(first_half_dir.glob("*.csv")) if first_half_dir.exists() else []
        )
        second_half_files = (
            sorted(second_half_dir.glob("*.csv")) if second_half_dir.exists() else []
        )

        for file_path in first_half_files:
            process_possession_file(file_path, possession_data, 0.0)

        second_half_offset = infer_second_half_offset(second_half_files)
        LOGGER.info(
            "Using %.1f seconds as second-half possession offset.",
            second_half_offset,
        )

        for file_path in second_half_files:
            process_possession_file(
                file_path,
                possession_data,
                second_half_offset,
            )
    else:
        for file_path in sorted(possession_path.glob("*.csv")):
            process_possession_file(file_path, possession_data, 0.0)

    possession_data = merge_possession_intervals(possession_data)

    interval_count = sum(len(intervals) for intervals in possession_data.values())
    LOGGER.info(
        "Loaded %d possession intervals for %d players from %s.",
        interval_count,
        len(possession_data),
        possession_path,
    )

    return possession_data

def format_match_time(match_second: float | None) -> str:
    """Formats a match timestamp as ``MM:SS``."""
    if match_second is None:
        return "-"

    match_second_int = int(match_second)
    return f"{match_second_int // 60:02d}:{match_second_int % 60:02d}"


def short_name(name: str) -> str:
    """Converts a full player name into a compact display label."""
    parts = name.split()
    return name if len(parts) == 1 else f"{parts[0][0]}. {parts[-1]}"


def get_current_half(positions: list[Position]) -> int | None:
    """Returns the highest visible half value from the current raw positions."""
    halves = [int(pos["half"]) for pos in positions if pos.get("half") is not None]
    return max(halves) if halves else None

def find_possession_path() -> Path | None:
    """Returns the first existing possession metadata path."""
    for path in POSSESSION_PATHS:
        if path.exists():
            return path

    return None

def average_positions(
    name: str,
    sensor_definition: dict[str, Any],
    positions_by_sid: dict[int, Position],
    object_type: str,
    team: str | None,
    role: str | None,
) -> DisplayObject | None:
    """Builds one display object by averaging its available sensors.

    For players and the referee, foot sensors are preferred. Extra sensors are
    only used as fallback when foot sensors are missing.
    """
    used_positions = [
        positions_by_sid[sid]
        for sid in sensor_definition.get("feet", [])
        if sid in positions_by_sid
    ]

    if not used_positions:
        used_positions = [
            positions_by_sid[sid]
            for sid in sensor_definition.get("extra", [])
            if sid in positions_by_sid
        ]

    if not used_positions:
        return None

    match_seconds = [
        float(position["matchSecond"])
        for position in used_positions
        if position.get("matchSecond") is not None
    ]

    return {
        "name": name,
        "label": short_name(name),
        "type": object_type,
        "team": team,
        "role": role,
        "x": sum(float(position["x"]) for position in used_positions)
        / len(used_positions),
        "y": sum(float(position["y"]) for position in used_positions)
        / len(used_positions),
        "ts": max(
            int(position["ts"])
            for position in used_positions
            if position.get("ts") is not None
        ),
        "matchSecond": max(match_seconds) if match_seconds else None,
        "sids": [int(position["sid"]) for position in used_positions],
        "speed_kmh": sum(
            float(position.get("speed_kmh", 0.0)) for position in used_positions
        )
        / len(used_positions),
    }


def get_ball_objects(positions_by_sid: dict[int, Position]) -> list[DisplayObject]:
    """Returns display objects for all currently visible ball sensors."""
    ball_objects: list[DisplayObject] = []

    for sid in ALL_BALL_IDS:
        if sid not in positions_by_sid:
            continue

        position = positions_by_sid[sid]
        ball_objects.append(
            {
                "name": f"Ball {sid}",
                "label": f"Ball {sid}",
                "type": "ball",
                "team": None,
                "role": None,
                "x": float(position["x"]),
                "y": float(position["y"]),
                "ts": int(position["ts"]),
                "matchSecond": (
                    float(position["matchSecond"])
                    if position.get("matchSecond") is not None
                    else None
                ),
                "sids": [sid],
                "speed_kmh": float(position.get("speed_kmh", 0.0)),
            }
        )

    return ball_objects


def append_team_objects(
    display_objects: list[DisplayObject],
    team_players: dict[str, dict[str, Any]],
    positions_by_sid: dict[int, Position],
    team_name: str,
) -> None:
    """Adds all visible player objects for one team."""
    for name, sensor_definition in team_players.items():
        role = sensor_definition.get("role", "Player")
        player = average_positions(
            name,
            sensor_definition,
            positions_by_sid,
            "player",
            team_name,
            role,
        )
        if player is not None:
            display_objects.append(player)


def build_display_objects(state: JsonDict) -> list[DisplayObject]:
    """Builds all dashboard objects from the latest streaming state."""
    positions_by_sid = {
        int(position["sid"]): position
        for position in state.get("positions", [])
        if position.get("sid") is not None
    }

    display_objects = get_ball_objects(positions_by_sid)
    append_team_objects(display_objects, TEAM_A_PLAYERS, positions_by_sid, TEAM_A)
    append_team_objects(display_objects, TEAM_B_PLAYERS, positions_by_sid, TEAM_B)

    for name, sensor_definition in REFEREE.items():
        referee = average_positions(
            name,
            sensor_definition,
            positions_by_sid,
            "referee",
            None,
            "Referee",
        )
        if referee is not None:
            display_objects.append(referee)

    return display_objects


def add_pitch_lines(fig: go.Figure) -> None:
    """Adds pitch markings to the Plotly figure."""
    field_width = FIELD_X_MAX - FIELD_X_MIN
    field_height = FIELD_Y_MAX - FIELD_Y_MIN

    penalty_area_depth = field_width * 0.165
    penalty_area_width = field_height * 0.60
    goal_area_depth = field_width * 0.055
    goal_area_width = field_height * 0.30
    center_circle_radius = field_height * 0.135

    line_style = {"color": "white", "width": 3}

    fig.update_layout(
        shapes=[
            {
                "type": "rect",
                "x0": FIELD_X_MIN,
                "y0": FIELD_Y_MIN,
                "x1": FIELD_X_MAX,
                "y1": FIELD_Y_MAX,
                "line": line_style,
            },
            {
                "type": "line",
                "x0": 0,
                "y0": FIELD_Y_MIN,
                "x1": 0,
                "y1": FIELD_Y_MAX,
                "line": line_style,
            },
            {
                "type": "circle",
                "x0": -center_circle_radius,
                "y0": -center_circle_radius,
                "x1": center_circle_radius,
                "y1": center_circle_radius,
                "line": line_style,
            },
            {
                "type": "rect",
                "x0": FIELD_X_MIN,
                "y0": -penalty_area_width / 2,
                "x1": FIELD_X_MIN + penalty_area_depth,
                "y1": penalty_area_width / 2,
                "line": line_style,
            },
            {
                "type": "rect",
                "x0": FIELD_X_MAX - penalty_area_depth,
                "y0": -penalty_area_width / 2,
                "x1": FIELD_X_MAX,
                "y1": penalty_area_width / 2,
                "line": line_style,
            },
            {
                "type": "rect",
                "x0": FIELD_X_MIN,
                "y0": -goal_area_width / 2,
                "x1": FIELD_X_MIN + goal_area_depth,
                "y1": goal_area_width / 2,
                "line": line_style,
            },
            {
                "type": "rect",
                "x0": FIELD_X_MAX - goal_area_depth,
                "y0": -goal_area_width / 2,
                "x1": FIELD_X_MAX,
                "y1": goal_area_width / 2,
                "line": line_style,
            },
        ]
    )


def transform_position(
    obj: DisplayObject,
    offset_x: float = POSITION_OFFSET_X,
    offset_y: float = POSITION_OFFSET_Y,
) -> tuple[float, float]:
    """Transforms raw tracking coordinates into dashboard plot coordinates."""
    return (
        obj["y"] * POSITION_SCALE_X + offset_x,
        obj["x"] * POSITION_SCALE_Y + offset_y,
    )


def add_object_trace(
    fig: go.Figure,
    objects: list[DisplayObject],
    name: str,
    color: str,
    marker_size: int,
    symbol: str = "circle",
    opacity: float = 1.0,
    is_trail: bool = False,
) -> None:
    """Adds a group of objects to the pitch figure."""
    if not objects:
        return

    coordinates = [transform_position(obj) for obj in objects]

    fig.add_trace(
        go.Scatter(
            x=[point[0] for point in coordinates],
            y=[point[1] for point in coordinates],
            mode="markers" if is_trail else "markers+text",
            text=None if is_trail else [obj["label"] for obj in objects],
            textposition="bottom center",
            opacity=opacity,
            marker={
                "size": marker_size,
                "color": color,
                "symbol": symbol,
                "line": {
                    "width": 0 if is_trail else 2,
                    "color": "white",
                },
            },
            name=name,
            showlegend=not is_trail,
            hoverinfo="none" if is_trail else None,
            customdata=None
            if is_trail
            else [
                [
                    obj["name"],
                    ", ".join(map(str, obj["sids"])),
                    obj["matchSecond"],
                    obj.get("speed_kmh", 0.0),
                ]
                for obj in objects
            ],
            hovertemplate=None
            if is_trail
            else (
                "<b>%{customdata[0]}</b><br>"
                "sensor ids: %{customdata[1]}<br>"
                "match second: %{customdata[2]}<br>"
                "speed: %{customdata[3]:.1f} km/h<br>"
                "x: %{x:.0f}<br>"
                "y: %{y:.0f}<extra></extra>"
            ),
        )
    )


def get_heatmap_target_sids(selection: str) -> set[int] | None:
    """Returns sensor ids for the selected heat-map filter.

    ``None`` means that all available sensor ids should be included.
    """
    if selection == "All":
        return None

    if selection == TEAM_A:
        return {
            sid
            for player in TEAM_A_PLAYERS.values()
            for sid in player["feet"] + player["extra"]
        }

    if selection == TEAM_B:
        return {
            sid
            for player in TEAM_B_PLAYERS.values()
            for sid in player["feet"] + player["extra"]
        }

    if selection in TEAM_A_PLAYERS:
        player = TEAM_A_PLAYERS[selection]
        return set(player["feet"] + player["extra"])

    if selection in TEAM_B_PLAYERS:
        player = TEAM_B_PLAYERS[selection]
        return set(player["feet"] + player["extra"])

    return set()


def combine_heatmap_grids(
    heatmap_by_sid: JsonDict,
    selection: str,
) -> list[list[int]]:
    """Combines per-sensor heat-map grids for the selected focus."""
    target_sids = get_heatmap_target_sids(selection)
    combined_grid = [
        [0 for _ in range(HEATMAP_X_BINS)] for _ in range(HEATMAP_Y_BINS)
    ]

    for sid_text, grid in heatmap_by_sid.items():
        try:
            sid = int(sid_text)
        except ValueError:
            continue

        if target_sids is not None and sid not in target_sids:
            continue

        for row_index in range(min(HEATMAP_Y_BINS, len(grid))):
            row = grid[row_index]
            for col_index in range(min(HEATMAP_X_BINS, len(row))):
                combined_grid[row_index][col_index] += row[col_index]

    return combined_grid


def add_heatmap_trace(
    fig: go.Figure,
    state: JsonDict,
    heatmap_selection: str,
) -> None:
    """Adds the optional heat-map overlay to the pitch figure."""
    heatmap_by_sid = state.get("heatmap_by_sid")
    if not heatmap_by_sid:
        return

    combined_grid = combine_heatmap_grids(heatmap_by_sid, heatmap_selection)

    raw_x_width = (HEATMAP_DATA_X_MAX - HEATMAP_DATA_X_MIN) / HEATMAP_X_BINS
    raw_y_height = (HEATMAP_DATA_Y_MAX - HEATMAP_DATA_Y_MIN) / HEATMAP_Y_BINS

    raw_x_edges = [
        HEATMAP_DATA_X_MIN + index * raw_x_width
        for index in range(HEATMAP_X_BINS + 1)
    ]
    raw_y_edges = [
        HEATMAP_DATA_Y_MIN + index * raw_y_height
        for index in range(HEATMAP_Y_BINS + 1)
    ]

    ui_x_edges = [
        y_edge * POSITION_SCALE_X + HEATMAP_OFFSET_X for y_edge in raw_y_edges
    ]
    ui_y_edges = [
        x_edge * POSITION_SCALE_Y + HEATMAP_OFFSET_Y for x_edge in raw_x_edges
    ]

    # Plotly expects the heat-map matrix orientation to match the generated
    # boundary vectors, so the grid is transposed before rendering.
    transposed_grid = [
        [combined_grid[row][col] for row in range(HEATMAP_Y_BINS)]
        for col in range(HEATMAP_X_BINS)
    ]

    fig.add_trace(
        go.Heatmap(
            z=transposed_grid,
            x=ui_x_edges,
            y=ui_y_edges,
            colorscale="Inferno",
            opacity=0.6,
            showscale=False,
            name=f"Heat Map ({heatmap_selection})",
            hoverinfo="none",
        )
    )


def update_trail_history(
    batch_id: int,
    display_objects: list[DisplayObject],
) -> list[int]:
    """Stores recent batches and returns their ids in chronological order."""
    if "trail_history" not in st.session_state:
        st.session_state.trail_history = {}

    st.session_state.trail_history[batch_id] = display_objects

    recent_batches = sorted(st.session_state.trail_history.keys())[
        -TRAIL_BATCH_LIMIT:
    ]
    st.session_state.trail_history = {
        batch: st.session_state.trail_history[batch] for batch in recent_batches
    }

    return recent_batches


def add_trail_traces(fig: go.Figure, recent_batches: list[int]) -> None:
    """Adds fading object trails from previous batches."""
    if len(recent_batches) <= 1:
        return

    for index, batch_id in enumerate(recent_batches[:-1]):
        history = st.session_state.trail_history[batch_id]
        fade = (index + 1) / len(recent_batches) * 0.7

        add_object_trace(
            fig,
            [obj for obj in history if obj["team"] == TEAM_A],
            TEAM_A,
            "royalblue",
            10,
            opacity=fade,
            is_trail=True,
        )
        add_object_trace(
            fig,
            [obj for obj in history if obj["team"] == TEAM_B],
            TEAM_B,
            "tomato",
            10,
            opacity=fade,
            is_trail=True,
        )
        add_object_trace(
            fig,
            [obj for obj in history if obj["type"] == "ball"],
            "Ball",
            "yellow",
            10,
            opacity=fade,
            is_trail=True,
        )


def add_current_object_traces(
    fig: go.Figure,
    display_objects: list[DisplayObject],
) -> None:
    """Adds the currently visible players, balls, and referee."""
    for role, color in TEAM_A_COLORS.items():
        objects = [
            obj
            for obj in display_objects
            if obj["team"] == TEAM_A and obj["role"] == role
        ]
        add_object_trace(fig, objects, f"{TEAM_A} - {role}", color, 17)

    for role, color in TEAM_B_COLORS.items():
        objects = [
            obj
            for obj in display_objects
            if obj["team"] == TEAM_B and obj["role"] == role
        ]
        add_object_trace(fig, objects, f"{TEAM_B} - {role}", color, 17)

    add_object_trace(
        fig,
        [obj for obj in display_objects if obj["type"] == "ball"],
        "Ball",
        "yellow",
        20,
    )
    add_object_trace(
        fig,
        [obj for obj in display_objects if obj["type"] == "referee"],
        "Referee",
        "black",
        16,
        "square",
    )


def create_field_figure(
    state: JsonDict,
    show_trails: bool = True,
    show_heatmap: bool = False,
    heatmap_selection: str = "All",
) -> go.Figure:
    """Creates the live soccer pitch figure."""
    display_objects = build_display_objects(state)
    batch_id = int(state.get("batchId", 0))
    recent_batches = update_trail_history(batch_id, display_objects)

    fig = go.Figure()

    if show_heatmap:
        add_heatmap_trace(fig, state, heatmap_selection)

    add_pitch_lines(fig)

    if show_trails:
        add_trail_traces(fig, recent_batches)

    add_current_object_traces(fig, display_objects)

    fig.update_layout(
        height=800,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        plot_bgcolor="rgb(30, 150, 45)",
        paper_bgcolor="white",
        showlegend=True,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "center",
            "x": 0.5,
            "font": {"size": 14, "color": "black"},
            "bgcolor": "rgba(255, 255, 255, 0.9)",
            "bordercolor": "black",
            "borderwidth": 1,
        },
        xaxis={
            "range": [FIELD_X_MIN, FIELD_X_MAX],
            "showgrid": False,
            "zeroline": False,
            "showticklabels": False,
            "fixedrange": True,
        },
        yaxis={
            "range": [FIELD_Y_MIN * 1.2, FIELD_Y_MAX * 1.2],
            "showgrid": False,
            "zeroline": False,
            "showticklabels": False,
            "fixedrange": True,
            "scaleanchor": "x",
            "scaleratio": 1,
        },
    )

    return fig


def describe_running_intensity(speed_kmh: float) -> str:
    """Returns a readable speed intensity label."""
    if speed_kmh > SPRINT_SPEED_KMH:
        return "🔴 Sprint"
    if speed_kmh > HIGH_SPEED_RUN_KMH:
        return "🟡 High-Speed Run"
    if speed_kmh > LOW_SPEED_RUN_KMH:
        return "🟢 Low-Speed Run"
    if speed_kmh > TROT_SPEED_KMH:
        return "🚶 Trot"
    return "🧍 Standing"


def render_fastest_players(display_objects: list[DisplayObject]) -> None:
    """Renders the current-speed leaderboard in the sidebar."""
    st.sidebar.subheader("Fastest Players (Current)")

    players_only = [obj for obj in display_objects if obj["type"] == "player"]
    fastest_players = sorted(
        players_only,
        key=lambda player: player.get("speed_kmh", 0.0),
        reverse=True,
    )[:5]

    for index, player in enumerate(fastest_players, start=1):
        speed = float(player.get("speed_kmh", 0.0))
        intensity = describe_running_intensity(speed)
        st.sidebar.markdown(
            f"**{index}. {player['name']}** ({player['team']})  \n"
            f"{speed:.1f} km/h - {intensity}"
        )


def render_sprint_leaderboard(
    stats_data: JsonDict | None,
    display_objects: list[DisplayObject],
) -> None:
    """Renders the rolling sprint-distance leaderboard."""
    st.sidebar.divider()
    st.sidebar.subheader("🔥 Top Sprinters (Last 60s)")

    if not stats_data or "stats" not in stats_data:
        st.sidebar.write("Waiting for rolling stats data...")
        return

    stats_dict = stats_data["stats"]
    sprint_leaderboard: list[JsonDict] = []

    for player in [obj for obj in display_objects if obj["type"] == "player"]:
        total_sprint_distance = 0.0

        # Spark writes rolling statistics per sensor id. Player sprint distance
        # is approximated by summing the visible sensors that belong to them.
        for sid in player["sids"]:
            sid_stats = stats_dict.get(str(sid), {})
            total_sprint_distance += sid_stats.get("Sprint", {}).get(
                "distance_1m",
                0.0,
            )

        if total_sprint_distance > 0:
            sprint_leaderboard.append(
                {
                    "name": player["name"],
                    "team": player["team"],
                    "distance": total_sprint_distance,
                }
            )

    sprint_leaderboard.sort(key=lambda item: item["distance"], reverse=True)

    if not sprint_leaderboard:
        st.sidebar.write("No sprints detected in the last minute.")
        return

    for index, leader in enumerate(sprint_leaderboard[:5], start=1):
        st.sidebar.markdown(
            f"**{index}. {leader['name']}** ({leader['team']})  \n"
            f"**{leader['distance']:.1f} meters** sprinted"
        )

def get_player_name_variants(player_name: str) -> set[str]:
    """Returns robust variants for matching player names."""
    raw_name = " ".join(player_name.strip().split()).casefold()

    german_name = (
        raw_name.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )

    ascii_name = unicodedata.normalize("NFKD", raw_name)
    ascii_name = "".join(
        char for char in ascii_name if not unicodedata.combining(char)
    )

    ascii_german_name = unicodedata.normalize("NFKD", german_name)
    ascii_german_name = "".join(
        char for char in ascii_german_name
        if not unicodedata.combining(char)
    )

    return {raw_name, german_name, ascii_name, ascii_german_name}


def get_player_team(player_name: str) -> str:
    """Returns the team name for a player, or an empty string if unknown."""
    if player_name in TEAM_A_PLAYERS:
        return TEAM_A
    if player_name in TEAM_B_PLAYERS:
        return TEAM_B
    return ""


def get_team_possession_template() -> dict[str, float]:
    """Returns an empty team-possession dictionary."""
    return {TEAM_A: 0.0, TEAM_B: 0.0, LOOSE_BALL: 0.0}


def calculate_interval_overlap(
    interval_start: float,
    interval_end: float,
    window_start: float,
    window_end: float,
) -> float:
    """Returns the overlap duration between one interval and one time window."""
    overlap_start = max(interval_start, window_start)
    overlap_end = min(interval_end, window_end)
    return max(0.0, overlap_end - overlap_start)


def calculate_possession_state(
    current_time: float | None,
    possession_data: PossessionData,
    window_seconds: float | None = None,
) -> tuple[list[str], dict[str, float], dict[str, float]]:
    """Calculates current, player, and team possession from metadata."""
    current_possessors: list[str] = []
    player_possession: dict[str, float] = {}
    team_possession = get_team_possession_template()

    if current_time is None:
        return current_possessors, player_possession, team_possession

    window_end = current_time
    window_start = (
        0.0
        if window_seconds is None
        else max(0.0, current_time - window_seconds)
    )
    active_duration = max(0.0, window_end - window_start)

    clipped_intervals: list[tuple[str, float, float, float]] = []
    current_candidates: list[tuple[str, float]] = []

    for player_name, intervals in possession_data.items():
        for interval in intervals:
            start = interval["start"]
            end = interval["end"]

            # Half-open interval prevents double possession at boundaries.
            if start <= current_time < end:
                current_candidates.append((player_name, start))

            overlap_start = max(start, window_start)
            overlap_end = min(end, window_end)

            if overlap_end > overlap_start:
                clipped_intervals.append(
                    (player_name, overlap_start, overlap_end, start)
                )

    if current_candidates:
        latest_start = max(start for _, start in current_candidates)
        current_possessors = [
            player
            for player, start in current_candidates
            if start == latest_start
        ]

    boundaries = {window_start, window_end}

    for _, start, end, _ in clipped_intervals:
        boundaries.add(start)
        boundaries.add(end)

    sorted_boundaries = sorted(boundaries)

    for left, right in zip(sorted_boundaries, sorted_boundaries[1:], strict=False):
        if right <= left:
            continue

        probe_time = (left + right) / 2.0
        active_players = [
            (player_name, original_start)
            for player_name, start, end, original_start in clipped_intervals
            if start <= probe_time < end
        ]

        if not active_players:
            continue

        # If metadata overlaps, the interval that started last wins.
        player_name = max(active_players, key=lambda item: item[1])[0]
        player_possession[player_name] = (
            player_possession.get(player_name, 0.0) + right - left
        )

    for player_name, possession_seconds in player_possession.items():
        player_team = get_player_team(player_name)

        if player_team in team_possession:
            team_possession[player_team] += possession_seconds

    known_possession_time = team_possession[TEAM_A] + team_possession[TEAM_B]
    team_possession[LOOSE_BALL] = max(
        0.0,
        active_duration - known_possession_time,
    )

    return current_possessors, player_possession, team_possession


def calculate_object_distance(
    first_object: DisplayObject,
    second_object: DisplayObject,
) -> float:
    """Returns the raw tracking distance between two display objects."""
    return math.hypot(
        float(first_object["x"]) - float(second_object["x"]),
        float(first_object["y"]) - float(second_object["y"]),
    )

def resolve_player_name(raw_player_name: str) -> str:
    """Maps a metadata filename to the player name used in config.py."""
    player_lookup: dict[str, str] = {}

    for player_name in list(TEAM_A_PLAYERS) + list(TEAM_B_PLAYERS):
        for variant in get_player_name_variants(player_name):
            player_lookup[variant] = player_name

    for variant in get_player_name_variants(raw_player_name):
        if variant in player_lookup:
            return player_lookup[variant]

    return " ".join(raw_player_name.strip().split())


def get_latest_ball(display_objects: list[DisplayObject]) -> DisplayObject | None:
    """Returns the latest visible ball object."""
    ball_objects = [obj for obj in display_objects if obj["type"] == "ball"]

    if not ball_objects:
        return None

    return max(ball_objects, key=lambda ball: int(ball.get("ts") or 0))


def describe_possession_confidence(distance_mm: float) -> str:
    """Returns a possession confidence label based on distance to the ball."""
    if distance_mm <= POSSESSION_HIGH_CONFIDENCE_MM:
        return "High"
    if distance_mm <= POSSESSION_MEDIUM_CONFIDENCE_MM:
        return "Medium"
    if distance_mm <= POSSESSION_LOW_CONFIDENCE_MM:
        return "Low"
    return "Loose Ball"


def estimate_tracking_possession(
    display_objects: list[DisplayObject],
) -> JsonDict:
    """Estimates possession from live positions.

    The estimate uses a simple nearest-player-to-ball rule. It is intentionally
    lightweight so it can run inside the Streamlit refresh loop.
    """
    ball = get_latest_ball(display_objects)
    players = [obj for obj in display_objects if obj["type"] == "player"]

    if ball is None or not players:
        return {
            "possessor": None,
            "team": "",
            "distance_m": None,
            "confidence": "Unavailable",
        }

    closest_player = min(
        players,
        key=lambda player: calculate_object_distance(player, ball),
    )
    distance_mm = calculate_object_distance(closest_player, ball)
    confidence = describe_possession_confidence(distance_mm)

    if confidence == "Loose Ball":
        return {
            "possessor": None,
            "team": "",
            "distance_m": distance_mm / 1_000,
            "confidence": confidence,
        }

    return {
        "possessor": closest_player["name"],
        "team": closest_player["team"],
        "distance_m": distance_mm / 1_000,
        "confidence": confidence,
    }


def format_possession_duration(seconds: float) -> str:
    """Formats a possession duration for compact sidebar display."""
    if seconds >= 60:
        minutes = int(seconds // 60)
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds:.0f}s"

    return f"{seconds:.1f} seconds"


def render_current_possession(current_possessors: list[str]) -> None:
    """Renders the official metadata-based current possession."""
    if len(current_possessors) == 1:
        possessor = current_possessors[0]
        st.sidebar.success(
            f"⚽ **Official Possession:** {possessor} "
            f"({get_player_team(possessor)})"
        )
        return

    if len(current_possessors) > 1:
        st.sidebar.warning(
            "⚽ **Official Possession Conflict:** "
            + ", ".join(current_possessors)
        )
        return

    st.sidebar.info(f"⚽ **Official Possession:** None ({LOOSE_BALL})")


def render_tracking_possession_estimate(
    display_objects: list[DisplayObject],
    official_possessors: list[str],
) -> None:
    """Renders the live tracking-based possession estimate."""
    estimate = estimate_tracking_possession(display_objects)
    possessor = estimate["possessor"]
    distance_m = estimate["distance_m"]
    confidence = estimate["confidence"]

    st.sidebar.caption("Tracking estimate")

    if possessor:
        st.sidebar.info(
            f"Estimated: **{possessor}** ({estimate['team']})  \n"
            f"Distance to ball: {distance_m:.2f}m  \n"
            f"Confidence: {confidence}"
        )
    elif distance_m is not None:
        st.sidebar.info(
            f"Estimated: **None** ({LOOSE_BALL})  \n"
            f"Nearest distance: {distance_m:.2f}m"
        )
    else:
        st.sidebar.info("Estimated: unavailable")

    if len(official_possessors) != 1:
        return

    official_possessor = official_possessors[0]

    if possessor == official_possessor:
        st.sidebar.success("Metadata and tracking estimate agree.")
    elif possessor:
        st.sidebar.warning(
            f"Metadata/tracking differ: official is {official_possessor}, "
            f"estimate is {possessor}."
        )


def render_team_possession_chart(
    team_possession: dict[str, float],
    title: str,
    chart_key: str,
) -> None:
    """Renders a team-possession pie chart including loose-ball time."""
    st.sidebar.subheader(title)

    names = [TEAM_A, TEAM_B, LOOSE_BALL]
    values = [team_possession.get(name, 0.0) for name in names]
    visible_items = [
        (name, value)
        for name, value in zip(names, values, strict=True)
        if value > 0
    ]

    if not visible_items:
        st.sidebar.write("Waiting for first possession...")
        return

    visible_names = [item[0] for item in visible_items]
    visible_values = [item[1] for item in visible_items]

    pie_fig = px.pie(
        values=visible_values,
        names=visible_names,
        color=visible_names,
        color_discrete_map={
            TEAM_A: "royalblue",
            TEAM_B: "tomato",
            LOOSE_BALL: "lightgray",
        },
        height=200,
    )
    pie_fig.update_layout(
        margin={"t": 0, "b": 0, "l": 0, "r": 0},
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    pie_fig.update_traces(textposition="inside", textinfo="percent+label")

    st.sidebar.plotly_chart(
        pie_fig,
        use_container_width=True,
        key=chart_key,
    )


def render_time_on_ball(cumulative_possession: dict[str, float]) -> None:
    """Renders the player time-on-ball leaderboard."""
    st.sidebar.subheader("⏱️ Time on Ball")

    sorted_possession = sorted(
        cumulative_possession.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    if not sorted_possession:
        st.sidebar.write("No possessions yet.")
        return

    for index, (player, possession_seconds) in enumerate(
        sorted_possession[:5],
        start=1,
    ):
        st.sidebar.markdown(
            f"**{index}. {player}** ({get_player_team(player)})  \n"
            f"{format_possession_duration(possession_seconds)}"
        )


def render_possession_sidebar(
    current_time: float | None,
    possession_data: PossessionData,
    display_objects: list[DisplayObject],
) -> None:
    """Renders all possession-related sidebar elements."""
    current_possessors, cumulative_possession, match_team_possession = (
        calculate_possession_state(current_time, possession_data)
    )
    _, _, rolling_team_possession = calculate_possession_state(
        current_time,
        possession_data,
        ROLLING_POSSESSION_WINDOW_SECONDS,
    )

    st.sidebar.divider()

    render_current_possession(current_possessors)
    render_tracking_possession_estimate(display_objects, current_possessors)

    render_team_possession_chart(
    match_team_possession,
    "📊 Match Possession %",
    "match_possession_chart",
        )
    render_team_possession_chart(
    rolling_team_possession,
    f"📊 Possession Last {int(ROLLING_POSSESSION_WINDOW_SECONDS)}s",
    "rolling_possession_chart",
    )
    render_time_on_ball(cumulative_possession)


def build_heatmap_options() -> list[str]:
    """Builds the heat-map filter dropdown options."""
    return [("All"), TEAM_A, TEAM_B] + list(TEAM_A_PLAYERS) + list(TEAM_B_PLAYERS)


def render_sidebar(
    display_objects: list[DisplayObject],
    stats_data: JsonDict | None,
    current_time: float | None,
) -> tuple[bool, bool, str]:
    """Renders only display controls in the sidebar.

    The analysis elements are rendered in the separate Analysis tab.
    """
    st.sidebar.title("Display Controls")

    show_trails = st.sidebar.toggle("Show Velocity Trails", value=True)
    show_heatmap = st.sidebar.toggle("Show Live Heat Map", value=False)
    heatmap_selection = st.sidebar.selectbox(
        "Heat Map Focus",
        build_heatmap_options(),
        disabled=not show_heatmap,
    )
    
    if st.sidebar.button("Reload possession metadata"):
        st.session_state.possession_data = load_possession_data()
        st.sidebar.success("Possession metadata reloaded.")

    return show_trails, show_heatmap, heatmap_selection

def emit_due_match_events(current_time: float | None) -> None:
    """Shows toast notifications for metadata events already reached."""
    if current_time is None:
        return

    event_index = st.session_state.last_event_idx

    while event_index < len(st.session_state.match_events):
        event = st.session_state.match_events[event_index]

        if current_time < event["second"]:
            break

        st.toast(f"**Live Event:** {event['msg']}", icon="🏟️")
        event_index += 1

    st.session_state.last_event_idx = event_index


def initialize_session_state() -> None:
    """Initializes cached metadata in Streamlit session state."""
    if "match_events" not in st.session_state:
        st.session_state.match_events = load_match_events()
        st.session_state.last_event_idx = 0

    if "possession_data" not in st.session_state:
        st.session_state.possession_data = load_possession_data()
        
    st.session_state.calculate_possession_state = calculate_possession_state

def render_fastest_players_page(display_objects: list[DisplayObject]) -> None:
    """Renders the current-speed leaderboard in the analysis page."""
    st.subheader("Fastest Players Current")

    players_only = [obj for obj in display_objects if obj["type"] == "player"]
    fastest_players = sorted(
        players_only,
        key=lambda player: player.get("speed_kmh", 0.0),
        reverse=True,
    )[:5]

    if not fastest_players:
        st.write("No player data available yet.")
        return

    for index, player in enumerate(fastest_players, start=1):
        speed = float(player.get("speed_kmh", 0.0))
        intensity = describe_running_intensity(speed)
        st.markdown(
            f"**{index}. {player['name']}** ({player['team']})  \n"
            f"{speed:.1f} km/h - {intensity}"
        )


def render_sprint_leaderboard_page(
    stats_data: JsonDict | None,
    display_objects: list[DisplayObject],
) -> None:
    """Renders the rolling sprint-distance leaderboard in the analysis page."""
    st.subheader("🔥 Top Sprinters Last 60s")

    if not stats_data or "stats" not in stats_data:
        st.write("Waiting for rolling stats data...")
        return

    stats_dict = stats_data["stats"]
    sprint_leaderboard: list[JsonDict] = []

    for player in [obj for obj in display_objects if obj["type"] == "player"]:
        total_sprint_distance = 0.0

        for sid in player["sids"]:
            sid_stats = stats_dict.get(str(sid), {})
            total_sprint_distance += sid_stats.get("Sprint", {}).get(
                "distance_1m",
                0.0,
            )

        if total_sprint_distance > 0:
            sprint_leaderboard.append(
                {
                    "name": player["name"],
                    "team": player["team"],
                    "distance": total_sprint_distance,
                }
            )

    sprint_leaderboard.sort(key=lambda item: item["distance"], reverse=True)

    if not sprint_leaderboard:
        st.write("No sprints detected in the last minute.")
        return

    for index, leader in enumerate(sprint_leaderboard[:5], start=1):
        st.markdown(
            f"**{index}. {leader['name']}** ({leader['team']})  \n"
            f"**{leader['distance']:.1f} meters** sprinted"
        )


def render_possession_chart_page(
    team_possession: dict[str, float],
    title: str,
    chart_key: str,
) -> None:
    """Renders a possession pie chart in the analysis page."""
    st.subheader(title)

    names = [TEAM_A, TEAM_B, LOOSE_BALL]
    values = [team_possession.get(name, 0.0) for name in names]
    visible_items = [
        (name, value)
        for name, value in zip(names, values, strict=True)
        if value > 0
    ]

    if not visible_items:
        st.write("Waiting for first possession...")
        return

    visible_names = [item[0] for item in visible_items]
    visible_values = [item[1] for item in visible_items]

    pie_fig = px.pie(
        values=visible_values,
        names=visible_names,
        color=visible_names,
        color_discrete_map={
            TEAM_A: "royalblue",
            TEAM_B: "tomato",
            LOOSE_BALL: "lightgray",
        },
        height=300,
    )
    pie_fig.update_layout(
        margin={"t": 0, "b": 0, "l": 0, "r": 0},
        showlegend=True,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    pie_fig.update_traces(textposition="inside", textinfo="percent+label")

    st.plotly_chart(
        pie_fig,
        use_container_width=True,
        key=chart_key,
    )


def render_time_on_ball_page(cumulative_possession: dict[str, float]) -> None:
    """Renders the player time-on-ball leaderboard in the analysis page."""
    st.subheader("⏱️ Time on Ball")

    sorted_possession = sorted(
        cumulative_possession.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    if not sorted_possession:
        st.write("No possessions yet.")
        return

    for index, (player, possession_seconds) in enumerate(
        sorted_possession[:10],
        start=1,
    ):
        st.markdown(
            f"**{index}. {player}** ({get_player_team(player)})  \n"
            f"{format_possession_duration(possession_seconds)}"
        )


def render_possession_analysis_page(
    current_time: float | None,
    possession_data: PossessionData,
    display_objects: list[DisplayObject],
) -> None:
    """Renders possession analysis in the analysis page."""
    current_possessors, cumulative_possession, match_team_possession = (
        calculate_possession_state(current_time, possession_data)
    )
    _, _, rolling_team_possession = calculate_possession_state(
        current_time,
        possession_data,
        ROLLING_POSSESSION_WINDOW_SECONDS,
    )

    st.header("Possession Analysis")

    current_column, estimate_column = st.columns(2)

    with current_column:
        st.subheader("Official Possession")

        if len(current_possessors) == 1:
            possessor = current_possessors[0]
            st.success(
                f"⚽ {possessor} ({get_player_team(possessor)})"
            )
        elif len(current_possessors) > 1:
            st.warning(
                "Possession conflict: " + ", ".join(current_possessors)
            )
        else:
            st.info(f"None ({LOOSE_BALL})")

    with estimate_column:
        st.subheader("Tracking Estimate")

        estimate = estimate_tracking_possession(display_objects)
        possessor = estimate["possessor"]
        distance_m = estimate["distance_m"]
        confidence = estimate["confidence"]

        if possessor:
            st.info(
                f"Estimated: **{possessor}** ({estimate['team']})  \n"
                f"Distance to ball: {distance_m:.2f}m  \n"
                f"Confidence: {confidence}"
            )
        elif distance_m is not None:
            st.info(
                f"Estimated: **None** ({LOOSE_BALL})  \n"
                f"Nearest distance: {distance_m:.2f}m"
            )
        else:
            st.info("Estimated: unavailable")

        if len(current_possessors) == 1:
            official_possessor = current_possessors[0]

            if possessor == official_possessor:
                st.success("Metadata and tracking estimate agree.")
            elif possessor:
                st.warning(
                    f"Metadata/tracking differ: official is "
                    f"{official_possessor}, estimate is {possessor}."
                )

    chart_column, rolling_column = st.columns(2)

    with chart_column:
        render_possession_chart_page(
            match_team_possession,
            "📊 Match Possession %",
            "analysis_match_possession_chart",
        )

    with rolling_column:
        render_possession_chart_page(
            rolling_team_possession,
            f"📊 Possession Last {int(ROLLING_POSSESSION_WINDOW_SECONDS)}s",
            "analysis_rolling_possession_chart",
        )

    render_time_on_ball_page(cumulative_possession)

def render_analysis_page(
    state: JsonDict,
    display_objects: list[DisplayObject],
    stats_data: JsonDict | None,
    current_time: float | None,
) -> None:
    """Renders the dedicated match-analysis page."""
    raw_positions = state.get("positions", [])
    players_only = [obj for obj in display_objects if obj["type"] == "player"]

    st.header("Match Analysis")

    metric_columns = st.columns(5)
    metric_columns[0].metric("Visible objects", len(display_objects))
    metric_columns[1].metric("Raw sensors", len(raw_positions))
    metric_columns[2].metric("Match time", format_match_time(current_time))
    metric_columns[3].metric("Half", get_current_half(raw_positions) or "-")
    metric_columns[4].metric("Spark batch", state.get("batchId", "-"))

    if players_only:
        fastest_player = max(
            players_only,
            key=lambda player: player.get("speed_kmh", 0.0),
        )
        st.metric(
            "Current fastest player",
            fastest_player["name"],
            f"{float(fastest_player.get('speed_kmh', 0.0)):.1f} km/h",
        )

    st.divider()

    speed_column, sprint_column = st.columns(2)

    with speed_column:
        render_fastest_players_page(display_objects)

    with sprint_column:
        render_sprint_leaderboard_page(stats_data, display_objects)

    st.divider()

    render_possession_analysis_page(
        current_time,
        st.session_state.possession_data,
        display_objects,
    )

def render_main_dashboard(
    state: JsonDict,
    display_objects: list[DisplayObject],
    show_trails: bool,
    show_heatmap: bool,
    heatmap_selection: str,
) -> None:
    """Renders metrics and the main pitch chart."""
    raw_positions = state.get("positions", [])
    current_time = state.get("currentMatchSecond")

    with st.empty().container():
        columns = st.columns(5)
        columns[0].metric("Visible objects", len(display_objects))
        columns[1].metric("Raw sensors", len(raw_positions))
        columns[2].metric("Match time", format_match_time(current_time))
        columns[3].metric("Half", get_current_half(raw_positions) or "-")
        columns[4].metric("Spark batch", state.get("batchId", "-"))

        emit_due_match_events(current_time)

        fig = create_field_figure(
            state,
            show_trails=show_trails,
            show_heatmap=show_heatmap,
            heatmap_selection=heatmap_selection,
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
        )


def main() -> None:
    """Runs the Streamlit dashboard."""
    logging.basicConfig(level=logging.INFO)

    st.set_page_config(page_title="Live Soccer Positions", layout="wide")
    st.title("Live Soccer Tracking Demo")

    initialize_session_state()

    state = load_positions()
    if state is None:
        st.warning("No live position file found yet.")
        time.sleep(REFRESH_SECONDS)
        st.rerun()
        return

    display_objects = build_display_objects(state)
    stats_data = load_stats()
    current_time = state.get("currentMatchSecond")

    show_trails, show_heatmap, heatmap_selection = render_sidebar(
        display_objects,
        stats_data,
        current_time,
    )

    live_tab, statistics_tab = st.tabs(["Live Tracking", "Statistics"])

    with live_tab:
        render_main_dashboard(
        state,
        display_objects,
        show_trails,
        show_heatmap,
        heatmap_selection,
        )

    with statistics_tab:
        render_statistics_tab(
        state=state,
        display_objects=display_objects,
        stats_data=stats_data,
        possession_data=st.session_state.possession_data,
        )

    time.sleep(REFRESH_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()
