from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config import (
    BALL_IDS_BY_HALF,
    BALL_SENSOR_IDS,
    FIELD_X_MAX,
    FIELD_X_MIN,
    FIELD_Y_MAX,
    FIELD_Y_MIN,
    TEAM_A_PLAYERS,
    TEAM_B_PLAYERS,
    REFEREE,
)

POSITIONS_PATH = Path("data/output/live_positions/positions.json")
STATS_PATH = Path("data/output/live_positions/stats_1m.json")
STREAM_METRICS_PATH = Path("data/output/live_positions/stream_metrics.json")
REFEREE_EVENTS_BASE = Path("data/raw/referee-events")


ALL_BALL_IDS = set(BALL_SENSOR_IDS)
REFRESH_SECONDS = 0.5
POSSESSION_DISTANCE_THRESHOLD_M = 3.0
PRESSURE_DISTANCE_THRESHOLD_M = 5.0
PLAYER_SPEED_ANOMALY_KMH = 40.0
BALL_SPEED_ANOMALY_KMH = 180.0


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def format_match_time(match_second: float | None) -> str:
    if match_second is None:
        return "-"
    second = int(match_second)
    return f"{second // 60:02d}:{second % 60:02d}"


def short_name(name: str) -> str:
    parts = name.split()
    return name if len(parts) == 1 else f"{parts[0][0]}. {parts[-1]}"


def distance_m(a: dict[str, Any], b: dict[str, Any]) -> float:
    # x/y are stored in millimetres in the live JSON, therefore divide by 1000.
    return math.sqrt((float(a["x"]) - float(b["x"])) ** 2 + (float(a["y"]) - float(b["y"])) ** 2) / 1000.0


def get_current_half(raw_positions: list[dict[str, Any]]) -> int | None:
    halves = [int(pos["half"]) for pos in raw_positions if pos.get("half") is not None]
    return max(halves) if halves else None


def intensity_label(speed_kmh: float) -> str:
    if speed_kmh > 24:
        return "Sprint"
    if speed_kmh > 14:
        return "High-Speed Run"
    if speed_kmh > 11:
        return "Low-Speed Run"
    if speed_kmh > 1:
        return "Trot"
    return "Standing"


def average_positions(
    name: str,
    sensor_definition: dict[str, list[int]],
    positions_by_sid: dict[int, dict[str, Any]],
    object_type: str,
    team: str | None,
    role: str | None,
) -> dict[str, Any] | None:
    used_positions = [positions_by_sid[sid] for sid in sensor_definition["feet"] if sid in positions_by_sid]
    if not used_positions:
        used_positions = [positions_by_sid[sid] for sid in sensor_definition.get("extra", []) if sid in positions_by_sid]
    if not used_positions:
        return None

    speeds = [float(pos.get("speed_kmh", 0.0) or 0.0) for pos in used_positions]
    accelerations = [float(pos.get("acceleration_m_s2", 0.0) or 0.0) for pos in used_positions]

    return {
        "name": name,
        "label": short_name(name),
        "type": object_type,
        "team": team,
        "role": role,
        "x": sum(float(pos["x"]) for pos in used_positions) / len(used_positions),
        "y": sum(float(pos["y"]) for pos in used_positions) / len(used_positions),
        "ts": max(int(pos["ts"]) for pos in used_positions if pos.get("ts") is not None),
        "matchSecond": max(
            [float(pos["matchSecond"]) for pos in used_positions if pos.get("matchSecond") is not None],
            default=None,
        ),
        "sids": [int(pos["sid"]) for pos in used_positions],
        "speed_kmh": sum(speeds) / len(speeds),
        "acceleration_m_s2": sum(accelerations) / len(accelerations) if accelerations else 0.0,
    }


def get_ball_objects(positions_by_sid: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    balls = []
    for sid in ALL_BALL_IDS:
        if sid not in positions_by_sid:
            continue
        pos = positions_by_sid[sid]
        balls.append(
            {
                "name": f"Ball {sid}",
                "label": f"Ball {sid}",
                "type": "ball",
                "team": None,
                "role": "Ball",
                "x": float(pos["x"]),
                "y": float(pos["y"]),
                "ts": int(pos["ts"]),
                "matchSecond": float(pos["matchSecond"]) if pos.get("matchSecond") is not None else None,
                "sids": [sid],
                "speed_kmh": float(pos.get("speed_kmh", 0.0) or 0.0),
                "acceleration_m_s2": float(pos.get("acceleration_m_s2", 0.0) or 0.0),
            }
        )
    return balls


def build_display_objects(state: dict[str, Any]) -> list[dict[str, Any]]:
    positions_by_sid = {
        int(pos["sid"]): pos
        for pos in state.get("positions", [])
        if pos.get("sid") is not None
    }
    display_objects = get_ball_objects(positions_by_sid)

    for name, sd in TEAM_A_PLAYERS.items():
        role = sd.get("role", "Player")
        player = average_positions(name, sd, positions_by_sid, "player", "Team A", role)
        if player:
            display_objects.append(player)

    for name, sd in TEAM_B_PLAYERS.items():
        role = sd.get("role", "Player")
        player = average_positions(name, sd, positions_by_sid, "player", "Team B", role)
        if player:
            display_objects.append(player)

    for name, sd in REFEREE.items():
        ref = average_positions(name, sd, positions_by_sid, "referee", None, "Referee")
        if ref:
            display_objects.append(ref)

    return display_objects


def select_active_ball(display_objects: list[dict[str, Any]], raw_positions: list[dict[str, Any]]) -> dict[str, Any] | None:
    balls = [obj for obj in display_objects if obj["type"] == "ball"]
    if not balls:
        return None

    current_half = get_current_half(raw_positions)
    if current_half in BALL_IDS_BY_HALF:
        allowed_sids = BALL_IDS_BY_HALF[current_half]
        half_balls = [ball for ball in balls if ball["sids"] and ball["sids"][0] in allowed_sids]
        if half_balls:
            balls = half_balls

    return max(balls, key=lambda ball: (ball.get("ts", 0), ball.get("speed_kmh", 0.0)))


def get_closest_player_to_ball(players: list[dict[str, Any]], ball: dict[str, Any] | None) -> tuple[dict[str, Any] | None, float | None]:
    if not ball or not players:
        return None, None
    closest = min(players, key=lambda p: distance_m(p, ball))
    return closest, distance_m(closest, ball)


def load_possession_data() -> dict[str, list[dict[str, float]]]:
    possession_data: dict[str, list[dict[str, float]]] = {}
    base_dir = Path("data/raw/referee-events/Ball Possession")

    def parse_time(t_str: str) -> float:
        try:
            h, m, s = str(t_str).split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            return -1

    if not base_dir.exists():
        return possession_data

    def process_file(filepath: Path, half_offset: float = 0.0) -> None:
        player_name = filepath.stem
        possession_data.setdefault(player_name, [])
        current_begin = None
        last_time = -1.0
        current_offset = half_offset

        with filepath.open("r", encoding="latin-1") as f:
            for line in f:
                parts = line.strip().split(";")
                if len(parts) < 3 or not parts[0].isdigit():
                    continue

                event_name = parts[1]
                raw_time = parse_time(parts[2])
                if raw_time == -1:
                    continue

                if raw_time < last_time and current_offset == 0.0:
                    current_offset = 1800.0
                last_time = raw_time
                timestamp = raw_time + current_offset

                if "Begin" in event_name:
                    current_begin = timestamp
                elif "End" in event_name and current_begin is not None:
                    possession_data[player_name].append({"start": current_begin, "end": timestamp})
                    current_begin = None

    if (base_dir / "1st Half").exists():
        for file in (base_dir / "1st Half").glob("*.csv"):
            process_file(file, 0.0)
        for file in (base_dir / "2nd Half").glob("*.csv"):
            process_file(file, 1800.0)
    else:
        for file in base_dir.glob("*.csv"):
            process_file(file, 0.0)

    return possession_data

def load_game_interruption_data() -> list[dict[str, Any]]:
    game_interruption_data: list[dict[str, Any]] = []
    base_dir = Path("data/raw/referee-events/Game Interruption")

    def parse_time(t_str: str) -> float:
        try:
            h, m, s = str(t_str).split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            return -1

    if not base_dir.exists():
        return game_interruption_data

    def process_file(filepath: Path, half_offset: float = 0.0) -> None:
        last_time = -1.0
        current_offset = half_offset

        with filepath.open("r", encoding="latin-1") as f:
            for line in f:
                parts = line.strip().split(";")
                if len(parts) < 3 or not parts[0].isdigit():
                    continue

                event_name = parts[1]
                raw_time = parse_time(parts[2])
                if raw_time == -1:
                    continue

                if raw_time < last_time and current_offset == 0.0:
                    current_offset = 1800.0
                last_time = raw_time

                timestamp = raw_time + current_offset

                game_interruption_data.append(
                    {
                        "time": timestamp,
                        "event": event_name,
                    }
                )

    if (base_dir / "1st Half").exists():
        for file in (base_dir / "1st Half").glob("*.csv"):
            process_file(file, 0.0)
        for file in (base_dir / "2nd Half").glob("*.csv"):
            process_file(file, 1800.0)
    else:
        for file in base_dir.glob("*.csv"):
            process_file(file, 0.0)

    return game_interruption_data

def load_shot_on_goal_data() -> list[dict[str, Any]]:
    shot_on_goal_data: list[dict[str, Any]] = []
    base_dir = Path("data/raw/referee-events/Shot on Goal")

    def parse_time(t_str: str) -> float:
        try:
            h, m, s = str(t_str).split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
        except Exception:
            return -1

    if not base_dir.exists():
        return shot_on_goal_data

    def process_file(filepath: Path, half_offset: float = 0.0) -> None:
        last_time = -1.0
        current_offset = half_offset

        with filepath.open("r", encoding="latin-1") as f:
            for line in f:
                parts = line.strip().split(";")
                if len(parts) < 3 or not parts[0].isdigit():
                    continue

                player_name = parts[1]
                raw_time = parse_time(parts[2])
                if raw_time == -1:
                    continue

                if raw_time < last_time and current_offset == 0.0:
                    current_offset = 1800.0
                last_time = raw_time

                timestamp = raw_time + current_offset

                if player_name in TEAM_A_PLAYERS:
                    team = "Team A"
                elif player_name in TEAM_B_PLAYERS:
                    team = "Team B"
                else:
                    team = None

                shot_on_goal_data.append(
                    {
                        "time": timestamp,
                        "player": player_name,
                        "team": team,
                    }
                )

    if (base_dir / "1st Half").exists():
        for file in (base_dir / "1st Half").glob("*.csv"):
            process_file(file, 0.0)
        for file in (base_dir / "2nd Half").glob("*.csv"):
            process_file(file, 1800.0)
    else:
        for file in base_dir.glob("*.csv"):
            process_file(file, 0.0)

    return shot_on_goal_data


def compute_metadata_possession(
    current_time: float | None,
    possession_data: dict[str, list[dict[str, float]]],
) -> tuple[str | None, dict[str, float], dict[str, float]]:
    current_possessor = None
    player_totals: dict[str, float] = {}
    team_totals = {"Team A": 0.0, "Team B": 0.0}

    if current_time is None:
        return current_possessor, player_totals, team_totals

    for player, intervals in possession_data.items():
        total = 0.0
        for interval in intervals:
            start, end = interval["start"], interval["end"]
            if start <= current_time <= end:
                current_possessor = player
            if start < current_time:
                total += max(0.0, min(end, current_time) - start)

        if total > 0:
            player_totals[player] = total
            if player in TEAM_A_PLAYERS:
                team_totals["Team A"] += total
            elif player in TEAM_B_PLAYERS:
                team_totals["Team B"] += total

    return current_possessor, player_totals, team_totals


def build_rolling_player_stats(
    players: list[dict[str, Any]],
    stats_data: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    stats_dict = (stats_data or {}).get("stats", {})
    rows: list[dict[str, Any]] = []
    team_totals = {
        "Team A": {"distance": 0.0, "sprint_distance": 0.0, "high_speed_distance": 0.0, "active_time": 0.0},
        "Team B": {"distance": 0.0, "sprint_distance": 0.0, "high_speed_distance": 0.0, "active_time": 0.0},
    }

    for player in players:
        distance_by_intensity = {"Standing": 0.0, "Trot": 0.0, "Low-Speed Run": 0.0, "High-Speed Run": 0.0, "Sprint": 0.0}
        time_by_intensity = {key: 0.0 for key in distance_by_intensity}

        for sid in player["sids"]:
            sid_stats = stats_dict.get(str(sid), {})
            for intensity, values in sid_stats.items():
                distance_by_intensity[intensity] = distance_by_intensity.get(intensity, 0.0) + float(values.get("distance_1m", 0.0) or 0.0)
                time_by_intensity[intensity] = time_by_intensity.get(intensity, 0.0) + float(values.get("time_1m", 0.0) or 0.0)

        total_distance = sum(distance_by_intensity.values())
        active_time = sum(time_by_intensity.values())
        row = {
            "Player": player["name"],
            "Team": player["team"],
            "Role": player.get("role", "Player"),
            "Current speed (km/h)": round(player.get("speed_kmh", 0.0), 2),
            "Current intensity": intensity_label(float(player.get("speed_kmh", 0.0) or 0.0)),
            "Distance last 60s (m)": round(total_distance, 2),
            "Sprint distance last 60s (m)": round(distance_by_intensity.get("Sprint", 0.0), 2),
            "High-speed distance last 60s (m)": round(distance_by_intensity.get("High-Speed Run", 0.0), 2),
            "Active time last 60s (s)": round(active_time, 2),
            **{f"{key} dist (m)": round(value, 2) for key, value in distance_by_intensity.items()},
        }
        rows.append(row)

        team = player["team"]
        if team in team_totals:
            team_totals[team]["distance"] += total_distance
            team_totals[team]["sprint_distance"] += distance_by_intensity.get("Sprint", 0.0)
            team_totals[team]["high_speed_distance"] += distance_by_intensity.get("High-Speed Run", 0.0)
            team_totals[team]["active_time"] += active_time

    return rows, team_totals


def compute_team_shape(players: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for team in ["Team A", "Team B"]:
        team_players = [player for player in players if player.get("team") == team]
        if not team_players:
            result[team] = {
                "visible_players": 0,
                "avg_speed": 0.0,
                "max_speed": 0.0,
                "width_m": 0.0,
                "depth_m": 0.0,
                "compactness_m": 0.0,
                "centroid_x_m": 0.0,
                "centroid_y_m": 0.0,
                "high_speed_players": 0,
            }
            continue

        centroid_x = sum(float(player["x"]) for player in team_players) / len(team_players)
        centroid_y = sum(float(player["y"]) for player in team_players) / len(team_players)
        compactness = sum(
            math.sqrt((float(player["x"]) - centroid_x) ** 2 + (float(player["y"]) - centroid_y) ** 2) / 1000.0
            for player in team_players
        ) / len(team_players)

        result[team] = {
            "visible_players": len(team_players),
            "avg_speed": sum(float(player.get("speed_kmh", 0.0) or 0.0) for player in team_players) / len(team_players),
            "max_speed": max(float(player.get("speed_kmh", 0.0) or 0.0) for player in team_players),
            "width_m": (max(float(player["y"]) for player in team_players) - min(float(player["y"]) for player in team_players)) / 1000.0,
            "depth_m": (max(float(player["x"]) for player in team_players) - min(float(player["x"]) for player in team_players)) / 1000.0,
            "compactness_m": compactness,
            "centroid_x_m": centroid_x / 1000.0,
            "centroid_y_m": centroid_y / 1000.0,
            "high_speed_players": sum(1 for player in team_players if float(player.get("speed_kmh", 0.0) or 0.0) > 14.0),
        }
    return result


def compute_pressure(players: list[dict[str, Any]], ball: dict[str, Any] | None) -> dict[str, int]:
    if ball is None:
        return {"Team A": 0, "Team B": 0}
    return {
        "Team A": sum(1 for player in players if player.get("team") == "Team A" and distance_m(player, ball) <= PRESSURE_DISTANCE_THRESHOLD_M),
        "Team B": sum(1 for player in players if player.get("team") == "Team B" and distance_m(player, ball) <= PRESSURE_DISTANCE_THRESHOLD_M),
    }


def compute_live_possession(players: list[dict[str, Any]], ball: dict[str, Any] | None) -> dict[str, Any]:
    closest, closest_distance = get_closest_player_to_ball(players, ball)
    if closest is None or closest_distance is None:
        return {"player": None, "team": "Neutral", "distance_m": None}
    if closest_distance <= POSSESSION_DISTANCE_THRESHOLD_M:
        return {"player": closest["name"], "team": closest["team"], "distance_m": closest_distance}
    return {"player": closest["name"], "team": "Neutral", "distance_m": closest_distance}


def compute_momentum(
    ball: dict[str, Any] | None,
    live_possession: dict[str, Any],
    pressure: dict[str, int],
    shape: dict[str, dict[str, float]],
) -> dict[str, float]:
    scores = {"Team A": 0.0, "Team B": 0.0}

    if live_possession.get("team") in scores:
        scores[live_possession["team"]] += 35.0
    
    

    if ball is not None:
        ball_x = float(ball["x"])
        norm_x = max(0.0, min(1.0, (ball_x - FIELD_X_MIN) / (FIELD_X_MAX - FIELD_X_MIN)))
        scores["Team A"] += norm_x * 25.0
        scores["Team B"] += (1.0 - norm_x) * 25.0

    scores["Team A"] += min(20.0, pressure["Team A"] * 5.0)
    scores["Team B"] += min(20.0, pressure["Team B"] * 5.0)

    scores["Team A"] += min(20.0, shape["Team A"]["high_speed_players"] * 4.0)
    scores["Team B"] += min(20.0, shape["Team B"]["high_speed_players"] * 4.0)

    total = scores["Team A"] + scores["Team B"]
    if total > 0:
        return {team: round(score / total * 100.0, 1) for team, score in scores.items()}
    return {"Team A": 50.0, "Team B": 50.0}

def momentum_over_time(
        raw_momentum: dict[str, float],
        previous_momentum: dict[str, float] | None,
        alpha: float = 0.15,
) -> dict[str, float]:
    if previous_momentum is None:
        return raw_momentum
    
    smoothed = {
        team: previous_momentum[team] * (1.0 - alpha) + raw_momentum[team] * alpha
        for team in raw_momentum
    }

    total = smoothed["Team A"] + smoothed["Team B"]

    if total > 0:
        return {
            team: round(score / total * 100.0, 1)
            for team, score in smoothed.items()
        }

    return previous_momentum


def detect_anomalies(
    players: list[dict[str, Any]],
    balls: list[dict[str, Any]],
    live_possession: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []

    for player in players:
        if float(player.get("speed_kmh", 0.0) or 0.0) > PLAYER_SPEED_ANOMALY_KMH:
            warnings.append(f"{player['name']} has an unrealistic player speed: {player['speed_kmh']:.1f} km/h")

    for ball in balls:
        if float(ball.get("speed_kmh", 0.0) or 0.0) > BALL_SPEED_ANOMALY_KMH:
            warnings.append(f"{ball['name']} has a very high ball speed: {ball['speed_kmh']:.1f} km/h")

    visible_team_players = sum(1 for player in players if player.get("team") in {"Team A", "Team B"})
    if visible_team_players < 12:
        warnings.append(f"Only {visible_team_players} team players are currently visible. Some sensors may be missing.")

    if live_possession.get("team") == "Neutral" and live_possession.get("distance_m") is not None:
        warnings.append(f"Loose ball: closest player is {live_possession['distance_m']:.1f} m away.")

    return warnings


def update_history(
    current_time: float | None,
    pressure: dict[str, int],
    momentum: dict[str, float],
    team_shape: dict[str, dict[str, float]],
) -> None:
    if current_time is None:
        return
    if "statistics_history" not in st.session_state:
        st.session_state.statistics_history = []

    previous = st.session_state.statistics_history[-1] if st.session_state.statistics_history else None
    if previous and previous["match_second"] == current_time:
        return

    st.session_state.statistics_history.append(
        {
            "match_second": current_time,
            "time": format_match_time(current_time),
            "Team A pressure": pressure["Team A"],
            "Team B pressure": pressure["Team B"],
            "Team A momentum": momentum["Team A"],
            "Team B momentum": momentum["Team B"],
            "Team A compactness": round(team_shape["Team A"]["compactness_m"], 2),
            "Team B compactness": round(team_shape["Team B"]["compactness_m"], 2),
        }
    )
    st.session_state.statistics_history = st.session_state.statistics_history[-300:]


def plot_history(metric_columns: list[str], title: str, y_label: str) -> go.Figure | None:
    history = st.session_state.get("statistics_history", [])
    if len(history) < 2:
        return None
    df = pd.DataFrame(history)
    fig = px.line(df, x="time", y=metric_columns, title=title, markers=False)
    fig.update_layout(
        height=320,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis_title="Match time",
        yaxis_title=y_label,
        legend_title="",
    )
    return fig


def main() -> None:
    st.set_page_config(page_title="Soccer Statistics Dashboard", layout="wide")
    st.title("Soccer Statistics Dashboard")

    if "possession_data" not in st.session_state:
        st.session_state.possession_data = load_possession_data()
    if "game_interruption_data" not in st.session_state:
        st.session_state.game_interruption_data = load_game_interruption_data()
    if "shot_on_goal_data" not in st.session_state:
        st.session_state.shot_on_goal_data = load_shot_on_goal_data()

    state = load_json(POSITIONS_PATH)
    stats_data = load_json(STATS_PATH)
    stream_metrics = load_json(STREAM_METRICS_PATH)

    if state is None:
        st.warning("No live position file found yet. Start the streaming job first.")
        time.sleep(REFRESH_SECONDS)
        st.rerun()
        return

    raw_positions = state.get("positions", [])
    display_objects = build_display_objects(state)
    players = [obj for obj in display_objects if obj.get("type") == "player"]
    balls = [obj for obj in display_objects if obj.get("type") == "ball"]
    ball = select_active_ball(display_objects, raw_positions)
    current_time = state.get("currentMatchSecond")

    metadata_possessor, player_possession, team_possession = compute_metadata_possession(
        current_time,
        st.session_state.possession_data,
    )
    live_possession = compute_live_possession(players, ball)
    closest_player, closest_distance = get_closest_player_to_ball(players, ball)
    team_shape = compute_team_shape(players)
    pressure = compute_pressure(players, ball)
    
    raw_momentum = compute_momentum(
        ball,
        live_possession,
        pressure,
        team_shape,
    )

    if st.session_state.get("momentum_match_second") == current_time:
        momentum = st.session_state.get("momentum", raw_momentum)
    else:
        momentum = momentum_over_time(
            raw_momentum=raw_momentum,
            previous_momentum=st.session_state.get("momentum"),
            alpha=0.15,
        )

        st.session_state.momentum = momentum
        st.session_state.raw_momentum = raw_momentum
        st.session_state.momentum_match_second = current_time

    anomalies = detect_anomalies(players, balls, live_possession)
    rolling_rows, rolling_team_totals = build_rolling_player_stats(players, stats_data)
    update_history(current_time, pressure, momentum, team_shape)

    st.sidebar.header("Live files")
    st.sidebar.write(f"Positions: `{POSITIONS_PATH}`")
    st.sidebar.write(f"Rolling stats: `{STATS_PATH}`")
    st.sidebar.write(f"Stream metrics: `{STREAM_METRICS_PATH}`")
    auto_refresh = st.sidebar.toggle("Auto refresh", value=True)
    st.sidebar.caption(f"Refresh interval: {REFRESH_SECONDS}s")

    top_cols = st.columns(6)
    top_cols[0].metric("Match time", format_match_time(current_time))
    top_cols[1].metric("Half", get_current_half(raw_positions) or "-")
    top_cols[2].metric("Spark batch", state.get("batchId", "-"))
    top_cols[3].metric("Raw sensors", len(raw_positions))
    top_cols[4].metric("Visible players", len(players))
    top_cols[5].metric("Ball speed", f"{ball.get('speed_kmh', 0.0):.1f} km/h" if ball else "-")

    st.divider()

    possession_cols = st.columns([1.1, 1.1, 1.4])
    with possession_cols[0]:
        st.subheader("Ball possession")
        if metadata_possessor:
            meta_team = "Team A" if metadata_possessor in TEAM_A_PLAYERS else "Team B" if metadata_possessor in TEAM_B_PLAYERS else "-"
            st.success(f"Metadata possession: **{metadata_possessor}** ({meta_team})")
        else:
            st.info("Metadata possession: no current possession")

        if live_possession.get("team") != "Neutral":
            st.success(
                f"Live nearest-player estimate: **{live_possession['player']}** "
                f"({live_possession['team']}, {live_possession['distance_m']:.1f} m)"
            )
        elif live_possession.get("player"):
            st.warning(
                f"Nearest player: **{live_possession['player']}**, "
                f"but ball is {live_possession['distance_m']:.1f} m away"
            )
        else:
            st.write("No ball/player estimate available.")

        if closest_player and closest_distance is not None:
            st.metric("Closest player to ball", closest_player["name"], f"{closest_distance:.1f} m")

    with possession_cols[1]:
        st.subheader("Team possession %")
        total_possession = team_possession["Team A"] + team_possession["Team B"]
        if total_possession > 0:
            fig = px.pie(
                values=[team_possession["Team A"], team_possession["Team B"]],
                names=["Team A", "Team B"],
                hole=0.35,
            )
            fig.update_layout(height=260, margin=dict(t=10, b=10, l=10, r=10), legend_title="")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.write("Waiting for possession metadata...")

    with possession_cols[2]:
        st.subheader("Time on ball leaderboard")
        possession_rows = []
        for player, seconds in sorted(player_possession.items(), key=lambda item: item[1], reverse=True)[:8]:
            possession_rows.append(
                {
                    "Player": player,
                    "Team": "Team A" if player in TEAM_A_PLAYERS else "Team B" if player in TEAM_B_PLAYERS else "-",
                    "Time on ball (s)": round(seconds, 1),
                }
            )
        if possession_rows:
            st.dataframe(pd.DataFrame(possession_rows), hide_index=True, use_container_width=True)
        else:
            st.write("No possession intervals yet.")

    st.divider()

    tactical_cols = st.columns(3)
    with tactical_cols[0]:
        st.subheader("Pressure index")
        pressure_df = pd.DataFrame(
            [
                {"Team": "Team A", "Players within 5m of ball": pressure["Team A"]},
                {"Team": "Team B", "Players within 5m of ball": pressure["Team B"]},
            ]
        )
        pressure_fig = px.bar(pressure_df, x="Team", y="Players within 5m of ball", text="Players within 5m of ball")
        pressure_fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), yaxis_range=[0, max(5, pressure_df["Players within 5m of ball"].max() + 1)])
        st.plotly_chart(pressure_fig, use_container_width=True, config={"displayModeBar": False})

    with tactical_cols[1]:
        st.subheader("Momentum proxy")
        momentum_df = pd.DataFrame(
            [
                {"Team": "Team A", "Momentum": momentum["Team A"]},
                {"Team": "Team B", "Momentum": momentum["Team B"]},
            ]
        )
        momentum_fig = px.bar(momentum_df, x="Team", y="Momentum", text="Momentum")
        momentum_fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), yaxis_range=[0, 100])
        st.plotly_chart(momentum_fig, use_container_width=True, config={"displayModeBar": False})
        st.caption("Heuristic proxy: possession + ball position + pressure + high-speed activity.")

    with tactical_cols[2]:
        st.subheader("Team shape")
        shape_rows = []
        for team, values in team_shape.items():
            shape_rows.append(
                {
                    "Team": team,
                    "Visible": int(values["visible_players"]),
                    "Width (m)": round(values["width_m"], 1),
                    "Depth (m)": round(values["depth_m"], 1),
                    "Compactness (m)": round(values["compactness_m"], 1),
                    "Avg speed": round(values["avg_speed"], 1),
                }
            )
        st.dataframe(pd.DataFrame(shape_rows), hide_index=True, use_container_width=True)

    history_cols = st.columns(2)
    with history_cols[0]:
        fig = plot_history(["Team A pressure", "Team B pressure"], "Pressure over dashboard time", "Players")
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    with history_cols[1]:
        fig = plot_history(["Team A momentum", "Team B momentum"], "Momentum over dashboard time", "Momentum score")
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.divider()

    physical_cols = st.columns([1.2, 1.2, 1.6])
    with physical_cols[0]:
        st.subheader("Fastest players now")
        fastest_rows = []
        for player in sorted(players, key=lambda p: p.get("speed_kmh", 0.0), reverse=True)[:8]:
            fastest_rows.append(
                {
                    "Player": player["name"],
                    "Team": player["team"],
                    "Speed (km/h)": round(float(player.get("speed_kmh", 0.0) or 0.0), 1),
                    "Intensity": intensity_label(float(player.get("speed_kmh", 0.0) or 0.0)),
                }
            )
        st.dataframe(pd.DataFrame(fastest_rows), hide_index=True, use_container_width=True)

    with physical_cols[1]:
        st.subheader("Top sprinters last 60s")
        sprint_df = pd.DataFrame(rolling_rows).sort_values("Sprint distance last 60s (m)", ascending=False).head(8)
        if not sprint_df.empty and sprint_df["Sprint distance last 60s (m)"].sum() > 0:
            st.dataframe(
                sprint_df[["Player", "Team", "Sprint distance last 60s (m)", "High-speed distance last 60s (m)"]],
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.write("No sprints detected in the last minute.")

    with physical_cols[2]:
        st.subheader("Team distance last 60s")
        team_distance_df = pd.DataFrame(
            [
                {
                    "Team": team,
                    "Total distance (m)": round(values["distance"], 2),
                    "Sprint distance (m)": round(values["sprint_distance"], 2),
                    "High-speed distance (m)": round(values["high_speed_distance"], 2),
                }
                for team, values in rolling_team_totals.items()
            ]
        )
        if team_distance_df["Total distance (m)"].sum() > 0:
            fig = px.bar(
                team_distance_df,
                x="Team",
                y=["Total distance (m)", "Sprint distance (m)", "High-speed distance (m)"],
                barmode="group",
            )
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10), legend_title="")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.write("Waiting for rolling distance stats...")

    with st.expander("Full player rolling statistics", expanded=False):
        if rolling_rows:
            st.dataframe(pd.DataFrame(rolling_rows), hide_index=True, use_container_width=True)
        else:
            st.write("Waiting for rolling statistics...")

    st.divider()

    systems_cols = st.columns(2)
    with systems_cols[0]:
        st.subheader("Streaming system metrics")
        if stream_metrics:
            metric_cols = st.columns(4)
            metric_cols[0].metric("Last input rows", stream_metrics.get("inputRows", "-"))
            metric_cols[1].metric("Newest sensors", stream_metrics.get("newestSensorRows", "-"))
            metric_cols[2].metric("Batch time", f"{stream_metrics.get('processingMs', 0):.1f} ms")
            metric_cols[3].metric("Rows/s", f"{stream_metrics.get('rowsPerSecond', 0):.1f}")
            st.json(stream_metrics, expanded=False)
        else:
            st.info("No stream_metrics.json yet. Use the patched streaming job below to enable this panel.")

    with systems_cols[1]:
        st.subheader("Events and anomalies")
        recent_events = []

        if current_time is not None:
            for event in st.session_state.game_interruption_data:
                if event["time"] <= current_time:
                    recent_events.append(
                        {
                            "time": event["time"],
                            "label": f"🛑 Game Interruption: {event['event']}",
                        }
                    )

            for event in st.session_state.shot_on_goal_data:
                if event["time"] <= current_time:
                    recent_events.append(
                        {
                            "time": event["time"],
                            "label": f"⚽ Shot on Goal: {event['player']}",
                        }
                    )

        recent_events = sorted(recent_events, key=lambda event: event["time"])

        for event in recent_events[-5:]:
            st.write(f"{format_match_time(event['time'])} — {event['label']}")

        if not recent_events:
            st.write("No metadata events reached yet.")

        if anomalies:
            st.warning("\n".join(f"- {warning}" for warning in anomalies))
        else:
            st.success("No obvious anomalies in the current state.")

    if auto_refresh:
        time.sleep(REFRESH_SECONDS)
        st.rerun()


if __name__ == "__main__":
    main()
