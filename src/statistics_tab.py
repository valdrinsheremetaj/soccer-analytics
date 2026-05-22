from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.config import (
    BALL_IDS_BY_HALF,
    FIELD_X_MAX,
    FIELD_X_MIN,
    TEAM_A_PLAYERS,
    TEAM_B_PLAYERS,
)

JsonDict = dict[str, Any]
DisplayObject = dict[str, Any]
PossessionData = dict[str, list[dict[str, float]]]

STREAM_METRICS_PATH = Path("data/output/live_positions/stream_metrics.json")

TEAM_A = "Team A"
TEAM_B = "Team B"
NEUTRAL = "Neutral"

POSSESSION_DISTANCE_THRESHOLD_M = 3.0
PRESSURE_DISTANCE_THRESHOLD_M = 5.0
PLAYER_SPEED_ANOMALY_KMH = 40.0
BALL_SPEED_ANOMALY_KMH = 180.0


def distance_m(first_object: DisplayObject, second_object: DisplayObject) -> float:
    """Returns distance in meters between two raw tracking objects."""
    return math.sqrt(
        (float(first_object["x"]) - float(second_object["x"])) ** 2
        + (float(first_object["y"]) - float(second_object["y"])) ** 2
    ) / 1_000.0


def intensity_label(speed_kmh: float) -> str:
    """Returns a readable intensity label."""
    if speed_kmh > 24:
        return "Sprint"
    if speed_kmh > 14:
        return "High-Speed Run"
    if speed_kmh > 11:
        return "Low-Speed Run"
    if speed_kmh > 1:
        return "Trot"
    return "Standing"


def load_stream_metrics() -> JsonDict | None:
    """Loads optional streaming-system metrics."""
    if not STREAM_METRICS_PATH.exists():
        return None

    try:
        return pd.read_json(STREAM_METRICS_PATH, typ="series").to_dict()
    except ValueError:
        return None


def select_active_ball(
    display_objects: list[DisplayObject],
    raw_positions: list[JsonDict],
) -> DisplayObject | None:
    """Selects the currently active ball.

    If the current half is known, the ball ids configured for that half are
    preferred. Otherwise the newest visible ball is used.
    """
    balls = [obj for obj in display_objects if obj["type"] == "ball"]

    if not balls:
        return None

    halves = [
        int(position["half"])
        for position in raw_positions
        if position.get("half") is not None
    ]
    current_half = max(halves) if halves else None

    if current_half in BALL_IDS_BY_HALF:
        allowed_sids = BALL_IDS_BY_HALF[current_half]
        half_balls = [
            ball
            for ball in balls
            if ball["sids"] and ball["sids"][0] in allowed_sids
        ]

        if half_balls:
            balls = half_balls

    return max(
        balls,
        key=lambda ball: (
            int(ball.get("ts") or 0),
            float(ball.get("speed_kmh", 0.0) or 0.0),
        ),
    )


def get_closest_player_to_ball(
    players: list[DisplayObject],
    ball: DisplayObject | None,
) -> tuple[DisplayObject | None, float | None]:
    """Returns the closest player to the active ball."""
    if ball is None or not players:
        return None, None

    closest_player = min(players, key=lambda player: distance_m(player, ball))
    return closest_player, distance_m(closest_player, ball)


def compute_live_possession(
    players: list[DisplayObject],
    ball: DisplayObject | None,
) -> JsonDict:
    """Estimates live possession from nearest player to ball."""
    closest_player, closest_distance = get_closest_player_to_ball(players, ball)

    if closest_player is None or closest_distance is None:
        return {"player": None, "team": NEUTRAL, "distance_m": None}

    if closest_distance <= POSSESSION_DISTANCE_THRESHOLD_M:
        return {
            "player": closest_player["name"],
            "team": closest_player["team"],
            "distance_m": closest_distance,
        }

    return {
        "player": closest_player["name"],
        "team": NEUTRAL,
        "distance_m": closest_distance,
    }


def build_rolling_player_stats(
    players: list[DisplayObject],
    stats_data: JsonDict | None,
) -> tuple[list[JsonDict], dict[str, dict[str, float]]]:
    """Builds player and team rolling physical stats from Spark output."""
    stats_dict = (stats_data or {}).get("stats", {})
    rows: list[JsonDict] = []
    team_totals = {
        TEAM_A: {
            "distance": 0.0,
            "sprint_distance": 0.0,
            "high_speed_distance": 0.0,
            "active_time": 0.0,
        },
        TEAM_B: {
            "distance": 0.0,
            "sprint_distance": 0.0,
            "high_speed_distance": 0.0,
            "active_time": 0.0,
        },
    }

    for player in players:
        distance_by_intensity = {
            "Standing": 0.0,
            "Trot": 0.0,
            "Low-Speed Run": 0.0,
            "High-Speed Run": 0.0,
            "Sprint": 0.0,
        }
        time_by_intensity = {key: 0.0 for key in distance_by_intensity}

        for sid in player["sids"]:
            sid_stats = stats_dict.get(str(sid), {})

            for intensity, values in sid_stats.items():
                distance_by_intensity[intensity] = (
                    distance_by_intensity.get(intensity, 0.0)
                    + float(values.get("distance_1m", 0.0) or 0.0)
                )
                time_by_intensity[intensity] = (
                    time_by_intensity.get(intensity, 0.0)
                    + float(values.get("time_1m", 0.0) or 0.0)
                )

        total_distance = sum(distance_by_intensity.values())
        active_time = sum(time_by_intensity.values())

        rows.append(
            {
                "Player": player["name"],
                "Team": player["team"],
                "Role": player.get("role", "Player"),
                "Current speed (km/h)": round(
                    float(player.get("speed_kmh", 0.0) or 0.0),
                    2,
                ),
                "Current intensity": intensity_label(
                    float(player.get("speed_kmh", 0.0) or 0.0)
                ),
                "Distance last 60s (m)": round(total_distance, 2),
                "Sprint distance last 60s (m)": round(
                    distance_by_intensity.get("Sprint", 0.0),
                    2,
                ),
                "High-speed distance last 60s (m)": round(
                    distance_by_intensity.get("High-Speed Run", 0.0),
                    2,
                ),
                "Active time last 60s (s)": round(active_time, 2),
            }
        )

        team = player["team"]

        if team in team_totals:
            team_totals[team]["distance"] += total_distance
            team_totals[team]["sprint_distance"] += distance_by_intensity.get(
                "Sprint",
                0.0,
            )
            team_totals[team]["high_speed_distance"] += distance_by_intensity.get(
                "High-Speed Run",
                0.0,
            )
            team_totals[team]["active_time"] += active_time

    return rows, team_totals


def compute_team_shape(players: list[DisplayObject]) -> dict[str, dict[str, float]]:
    """Computes tactical team-shape indicators."""
    result: dict[str, dict[str, float]] = {}

    for team in [TEAM_A, TEAM_B]:
        team_players = [player for player in players if player.get("team") == team]

        if not team_players:
            result[team] = {
                "visible_players": 0,
                "avg_speed": 0.0,
                "max_speed": 0.0,
                "width_m": 0.0,
                "depth_m": 0.0,
                "compactness_m": 0.0,
                "high_speed_players": 0,
            }
            continue

        centroid_x = sum(float(player["x"]) for player in team_players) / len(
            team_players
        )
        centroid_y = sum(float(player["y"]) for player in team_players) / len(
            team_players
        )
        compactness = sum(
            math.sqrt(
                (float(player["x"]) - centroid_x) ** 2
                + (float(player["y"]) - centroid_y) ** 2
            )
            / 1_000.0
            for player in team_players
        ) / len(team_players)

        result[team] = {
            "visible_players": len(team_players),
            "avg_speed": sum(
                float(player.get("speed_kmh", 0.0) or 0.0)
                for player in team_players
            )
            / len(team_players),
            "max_speed": max(
                float(player.get("speed_kmh", 0.0) or 0.0)
                for player in team_players
            ),
            "width_m": (
                max(float(player["y"]) for player in team_players)
                - min(float(player["y"]) for player in team_players)
            )
            / 1_000.0,
            "depth_m": (
                max(float(player["x"]) for player in team_players)
                - min(float(player["x"]) for player in team_players)
            )
            / 1_000.0,
            "compactness_m": compactness,
            "high_speed_players": sum(
                1
                for player in team_players
                if float(player.get("speed_kmh", 0.0) or 0.0) > 14.0
            ),
        }

    return result


def compute_pressure(
    players: list[DisplayObject],
    ball: DisplayObject | None,
) -> dict[str, int]:
    """Counts players within the pressure radius around the ball."""
    if ball is None:
        return {TEAM_A: 0, TEAM_B: 0}

    return {
        TEAM_A: sum(
            1
            for player in players
            if player.get("team") == TEAM_A
            and distance_m(player, ball) <= PRESSURE_DISTANCE_THRESHOLD_M
        ),
        TEAM_B: sum(
            1
            for player in players
            if player.get("team") == TEAM_B
            and distance_m(player, ball) <= PRESSURE_DISTANCE_THRESHOLD_M
        ),
    }


def compute_momentum(
    ball: DisplayObject | None,
    live_possession: JsonDict,
    pressure: dict[str, int],
    team_shape: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Computes a simple heuristic momentum score."""
    scores = {TEAM_A: 0.0, TEAM_B: 0.0}

    if live_possession.get("team") in scores:
        scores[live_possession["team"]] += 35.0

    if ball is not None:
        ball_x = float(ball["x"])
        norm_x = max(
            0.0,
            min(1.0, (ball_x - FIELD_X_MIN) / (FIELD_X_MAX - FIELD_X_MIN)),
        )
        scores[TEAM_A] += norm_x * 25.0
        scores[TEAM_B] += (1.0 - norm_x) * 25.0

    scores[TEAM_A] += min(20.0, pressure[TEAM_A] * 5.0)
    scores[TEAM_B] += min(20.0, pressure[TEAM_B] * 5.0)

    scores[TEAM_A] += min(20.0, team_shape[TEAM_A]["high_speed_players"] * 4.0)
    scores[TEAM_B] += min(20.0, team_shape[TEAM_B]["high_speed_players"] * 4.0)

    total = scores[TEAM_A] + scores[TEAM_B]

    if total <= 0:
        return {TEAM_A: 50.0, TEAM_B: 50.0}

    return {team: round(score / total * 100.0, 1) for team, score in scores.items()}


def momentum_over_time(
    raw_momentum: dict[str, float],
    previous_momentum: dict[str, float] | None,
    alpha: float = 0.15,
) -> dict[str, float]:
    """Smooths the momentum score over dashboard refreshes."""
    if previous_momentum is None:
        return raw_momentum

    smoothed = {
        team: previous_momentum[team] * (1.0 - alpha)
        + raw_momentum[team] * alpha
        for team in raw_momentum
    }
    total = smoothed[TEAM_A] + smoothed[TEAM_B]

    if total <= 0:
        return previous_momentum

    return {team: round(score / total * 100.0, 1) for team, score in smoothed.items()}


def detect_anomalies(
    players: list[DisplayObject],
    balls: list[DisplayObject],
    live_possession: JsonDict,
) -> list[str]:
    """Detects simple speed, visibility, and loose-ball anomalies."""
    warnings: list[str] = []

    for player in players:
        if float(player.get("speed_kmh", 0.0) or 0.0) > PLAYER_SPEED_ANOMALY_KMH:
            warnings.append(
                f"{player['name']} has an unrealistic player speed: "
                f"{player['speed_kmh']:.1f} km/h"
            )

    for ball in balls:
        if float(ball.get("speed_kmh", 0.0) or 0.0) > BALL_SPEED_ANOMALY_KMH:
            warnings.append(
                f"{ball['name']} has a very high ball speed: "
                f"{ball['speed_kmh']:.1f} km/h"
            )

    visible_team_players = sum(
        1 for player in players if player.get("team") in {TEAM_A, TEAM_B}
    )

    if visible_team_players < 12:
        warnings.append(
            f"Only {visible_team_players} team players are currently visible. "
            "Some sensors may be missing."
        )

    if (
        live_possession.get("team") == NEUTRAL
        and live_possession.get("distance_m") is not None
    ):
        warnings.append(
            f"Loose ball: closest player is "
            f"{live_possession['distance_m']:.1f} m away."
        )

    return warnings


def update_statistics_history(
    current_time: float | None,
    pressure: dict[str, int],
    momentum: dict[str, float],
    team_shape: dict[str, dict[str, float]],
) -> None:
    """Stores recent tactical values for line charts."""
    if current_time is None:
        return

    if "statistics_history" not in st.session_state:
        st.session_state.statistics_history = []

    previous = (
        st.session_state.statistics_history[-1]
        if st.session_state.statistics_history
        else None
    )

    if previous and previous["match_second"] == current_time:
        return

    st.session_state.statistics_history.append(
        {
            "match_second": current_time,
            "time": format_match_time(current_time),
            f"{TEAM_A} pressure": pressure[TEAM_A],
            f"{TEAM_B} pressure": pressure[TEAM_B],
            f"{TEAM_A} momentum": momentum[TEAM_A],
            f"{TEAM_B} momentum": momentum[TEAM_B],
            f"{TEAM_A} compactness": round(team_shape[TEAM_A]["compactness_m"], 2),
            f"{TEAM_B} compactness": round(team_shape[TEAM_B]["compactness_m"], 2),
        }
    )
    st.session_state.statistics_history = st.session_state.statistics_history[-300:]


def plot_history(metric_columns: list[str], title: str, y_label: str) -> go.Figure | None:
    """Creates a line chart from the stored statistics history."""
    history = st.session_state.get("statistics_history", [])

    if len(history) < 2:
        return None

    history_df = pd.DataFrame(history)
    fig = px.line(history_df, x="time", y=metric_columns, title=title)
    fig.update_layout(
        height=320,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        xaxis_title="Match time",
        yaxis_title=y_label,
        legend_title="",
    )

    return fig


def format_match_time(match_second: float | None) -> str:
    """Formats match time as MM:SS."""
    if match_second is None:
        return "-"

    second = int(match_second)
    return f"{second // 60:02d}:{second % 60:02d}"


def get_player_team(player_name: str) -> str:
    """Returns player team from config."""
    if player_name in TEAM_A_PLAYERS:
        return TEAM_A
    if player_name in TEAM_B_PLAYERS:
        return TEAM_B
    return "-"


def render_possession_statistics(
    current_time: float | None,
    possession_data: PossessionData,
    players: list[DisplayObject],
    ball: DisplayObject | None,
) -> None:
    """Renders possession analysis using your existing possession data."""
    live_possession = compute_live_possession(players, ball)
    closest_player, closest_distance = get_closest_player_to_ball(players, ball)

    # Use your existing function from dashboard.py through session state output.
    # This keeps your improved possession parser and avoids duplicating the
    # fragile metadata logic from the separate statistics dashboard.
    current_possessors, player_possession, team_possession = (
        st.session_state.calculate_possession_state(current_time, possession_data)
    )

    possession_cols = st.columns([1.1, 1.1, 1.4])

    with possession_cols[0]:
        st.subheader("Ball possession")

        if len(current_possessors) == 1:
            possessor = current_possessors[0]
            st.success(f"Metadata possession: **{possessor}** ({get_player_team(possessor)})")
        elif len(current_possessors) > 1:
            st.warning("Metadata possession conflict: " + ", ".join(current_possessors))
        else:
            st.info("Metadata possession: no current possession")

        if live_possession.get("team") != NEUTRAL:
            st.success(
                f"Live nearest-player estimate: **{live_possession['player']}** "
                f"({live_possession['team']}, {live_possession['distance_m']:.1f} m)"
            )
        elif live_possession.get("player"):
            st.warning(
                f"Nearest player: **{live_possession['player']}**, "
                f"but ball is {live_possession['distance_m']:.1f} m away"
            )

        if closest_player and closest_distance is not None:
            st.metric(
                "Closest player to ball",
                closest_player["name"],
                f"{closest_distance:.1f} m",
            )

    with possession_cols[1]:
        st.subheader("Team possession %")

        names = [TEAM_A, TEAM_B, "Loose Ball"]
        values = [team_possession.get(name, 0.0) for name in names]
        visible_items = [(name, value) for name, value in zip(names, values) if value > 0]

        if visible_items:
            fig = px.pie(
                values=[item[1] for item in visible_items],
                names=[item[0] for item in visible_items],
                hole=0.35,
            )
            fig.update_layout(
                height=260,
                margin={"t": 10, "b": 10, "l": 10, "r": 10},
                legend_title="",
            )
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False},
                key="statistics_team_possession",
            )
        else:
            st.write("Waiting for possession metadata...")

    with possession_cols[2]:
        st.subheader("Time on ball leaderboard")

        possession_rows = [
            {
                "Player": player,
                "Team": get_player_team(player),
                "Time on ball (s)": round(seconds, 1),
            }
            for player, seconds in sorted(
                player_possession.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:8]
        ]

        if possession_rows:
            st.dataframe(
                pd.DataFrame(possession_rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.write("No possession intervals yet.")


def render_statistics_tab(
    state: JsonDict,
    display_objects: list[DisplayObject],
    stats_data: JsonDict | None,
    possession_data: PossessionData,
) -> None:
    """Renders the statistics tab inside the main dashboard."""
    raw_positions = state.get("positions", [])
    current_time = state.get("currentMatchSecond")

    players = [obj for obj in display_objects if obj.get("type") == "player"]
    balls = [obj for obj in display_objects if obj.get("type") == "ball"]
    ball = select_active_ball(display_objects, raw_positions)

    live_possession = compute_live_possession(players, ball)
    team_shape = compute_team_shape(players)
    pressure = compute_pressure(players, ball)
    raw_momentum = compute_momentum(ball, live_possession, pressure, team_shape)

    if st.session_state.get("momentum_match_second") == current_time:
        momentum = st.session_state.get("momentum", raw_momentum)
    else:
        momentum = momentum_over_time(
            raw_momentum,
            st.session_state.get("momentum"),
            alpha=0.15,
        )
        st.session_state.momentum = momentum
        st.session_state.momentum_match_second = current_time

    anomalies = detect_anomalies(players, balls, live_possession)
    rolling_rows, rolling_team_totals = build_rolling_player_stats(players, stats_data)
    update_statistics_history(current_time, pressure, momentum, team_shape)

    st.header("Match Statistics")

    top_cols = st.columns(6)
    top_cols[0].metric("Match time", format_match_time(current_time))
    top_cols[1].metric("Spark batch", state.get("batchId", "-"))
    top_cols[2].metric("Raw sensors", len(raw_positions))
    top_cols[3].metric("Visible players", len(players))
    top_cols[4].metric(
        "Ball speed",
        f"{ball.get('speed_kmh', 0.0):.1f} km/h" if ball else "-",
    )
    top_cols[5].metric(
        "Live possession",
        live_possession.get("team", NEUTRAL),
    )

    st.divider()
    render_possession_statistics(current_time, possession_data, players, ball)

    st.divider()

    tactical_cols = st.columns(3)

    with tactical_cols[0]:
        st.subheader("Pressure index")
        pressure_df = pd.DataFrame(
            [
                {"Team": TEAM_A, "Players within 5m": pressure[TEAM_A]},
                {"Team": TEAM_B, "Players within 5m": pressure[TEAM_B]},
            ]
        )
        fig = px.bar(
            pressure_df,
            x="Team",
            y="Players within 5m",
            text="Players within 5m",
        )
        fig.update_layout(
            height=280,
            margin={"l": 10, "r": 10, "t": 10, "b": 10},
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
            key="statistics_pressure",
        )

    with tactical_cols[1]:
        st.subheader("Momentum proxy")
        momentum_df = pd.DataFrame(
            [
                {"Team": TEAM_A, "Momentum": momentum[TEAM_A]},
                {"Team": TEAM_B, "Momentum": momentum[TEAM_B]},
            ]
        )
        fig = px.bar(momentum_df, x="Team", y="Momentum", text="Momentum")
        fig.update_layout(
            height=280,
            margin={"l": 10, "r": 10, "t": 10, "b": 10},
            yaxis_range=[0, 100],
        )
        st.plotly_chart(
            fig,
            use_container_width=True,
            config={"displayModeBar": False},
            key="statistics_momentum",
        )
        st.caption("Heuristic proxy: possession + ball position + pressure + high-speed activity.")

    with tactical_cols[2]:
        st.subheader("Team shape")
        shape_rows = [
            {
                "Team": team,
                "Visible": int(values["visible_players"]),
                "Width (m)": round(values["width_m"], 1),
                "Depth (m)": round(values["depth_m"], 1),
                "Compactness (m)": round(values["compactness_m"], 1),
                "Avg speed": round(values["avg_speed"], 1),
            }
            for team, values in team_shape.items()
        ]
        st.dataframe(
            pd.DataFrame(shape_rows),
            hide_index=True,
            use_container_width=True,
        )

    history_cols = st.columns(2)

    with history_cols[0]:
        fig = plot_history(
            [f"{TEAM_A} pressure", f"{TEAM_B} pressure"],
            "Pressure over dashboard time",
            "Players",
        )
        if fig:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False},
                key="statistics_pressure_history",
            )

    with history_cols[1]:
        fig = plot_history(
            [f"{TEAM_A} momentum", f"{TEAM_B} momentum"],
            "Momentum over dashboard time",
            "Momentum score",
        )
        if fig:
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False},
                key="statistics_momentum_history",
            )

    st.divider()

    physical_cols = st.columns([1.2, 1.2, 1.6])

    with physical_cols[0]:
        st.subheader("Fastest players now")
        fastest_rows = [
            {
                "Player": player["name"],
                "Team": player["team"],
                "Speed (km/h)": round(float(player.get("speed_kmh", 0.0) or 0.0), 1),
                "Intensity": intensity_label(float(player.get("speed_kmh", 0.0) or 0.0)),
            }
            for player in sorted(
                players,
                key=lambda player: player.get("speed_kmh", 0.0),
                reverse=True,
            )[:8]
        ]
        st.dataframe(
            pd.DataFrame(fastest_rows),
            hide_index=True,
            use_container_width=True,
        )

    with physical_cols[1]:
        st.subheader("Top sprinters last 60s")
        sprint_df = pd.DataFrame(rolling_rows)

        if not sprint_df.empty:
            sprint_df = sprint_df.sort_values(
                "Sprint distance last 60s (m)",
                ascending=False,
            ).head(8)

        if not sprint_df.empty and sprint_df["Sprint distance last 60s (m)"].sum() > 0:
            st.dataframe(
                sprint_df[
                    [
                        "Player",
                        "Team",
                        "Sprint distance last 60s (m)",
                        "High-speed distance last 60s (m)",
                    ]
                ],
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

        if not team_distance_df.empty and team_distance_df["Total distance (m)"].sum() > 0:
            fig = px.bar(
                team_distance_df,
                x="Team",
                y=[
                    "Total distance (m)",
                    "Sprint distance (m)",
                    "High-speed distance (m)",
                ],
                barmode="group",
            )
            fig.update_layout(
                height=300,
                margin={"l": 10, "r": 10, "t": 10, "b": 10},
                legend_title="",
            )
            st.plotly_chart(
                fig,
                use_container_width=True,
                config={"displayModeBar": False},
                key="statistics_team_distance",
            )
        else:
            st.write("Waiting for rolling distance stats...")

    with st.expander("Full player rolling statistics", expanded=False):
        if rolling_rows:
            st.dataframe(
                pd.DataFrame(rolling_rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.write("Waiting for rolling statistics...")

    st.divider()

    systems_cols = st.columns(2)

    with systems_cols[0]:
        st.subheader("Streaming system metrics")
        stream_metrics = load_stream_metrics()

        if stream_metrics:
            metric_cols = st.columns(4)
            metric_cols[0].metric("Last input rows", stream_metrics.get("inputRows", "-"))
            metric_cols[1].metric("Newest sensors", stream_metrics.get("newestSensorRows", "-"))
            metric_cols[2].metric(
                "Batch time",
                f"{float(stream_metrics.get('processingMs', 0.0)):.1f} ms",
            )
            metric_cols[3].metric(
                "Rows/s",
                f"{float(stream_metrics.get('rowsPerSecond', 0.0)):.1f}",
            )
            st.json(stream_metrics, expanded=False)
        else:
            st.info("No stream_metrics.json yet.")

    with systems_cols[1]:
        st.subheader("Anomalies")

        if anomalies:
            st.warning("\n".join(f"- {warning}" for warning in anomalies))
        else:
            st.success("No obvious anomalies in the current state.")