from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from src.config import FIELD_X_MIN, FIELD_X_MAX, FIELD_Y_MIN, FIELD_Y_MAX, BALL_IDS_BY_HALF, TEAM_A_PLAYERS, TEAM_B_PLAYERS, REFEREE


POSITIONS_PATH = Path("data/output/live_positions/positions.json")

REFRESH_SECONDS = 1

ALL_BALL_IDS = {4, 8, 10, 12}


FIELD_X_MIN = -52489
FIELD_X_MAX = 52489
FIELD_Y_MIN = -33965
FIELD_Y_MAX = 33965


def load_positions() -> dict[str, Any] | None:
    if not POSITIONS_PATH.exists():
        return None

    try:
        with POSITIONS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def format_match_time(match_second: int | None) -> str:
    if match_second is None:
        return "-"

    minutes = match_second // 60
    seconds = match_second % 60

    return f"{minutes:02d}:{seconds:02d}"


def short_name(name: str) -> str:
    parts = name.split()

    if len(parts) == 1:
        return name

    return f"{parts[0][0]}. {parts[-1]}"


def get_current_half(positions: list[dict[str, Any]]) -> int | None:
    halves = [
        int(pos["half"])
        for pos in positions
        if pos.get("half") is not None
    ]

    if not halves:
        return None

    return max(halves)


def average_positions(
    name: str,
    sensor_definition: dict[str, list[int]],
    positions_by_sid: dict[int, dict[str, Any]],
    object_type: str,
    team: str | None,
) -> dict[str, Any] | None:
    feet_ids = sensor_definition["feet"]
    extra_ids = sensor_definition["extra"]

    foot_positions = [
        positions_by_sid[sid]
        for sid in feet_ids
        if sid in positions_by_sid
    ]

    extra_positions = [
        positions_by_sid[sid]
        for sid in extra_ids
        if sid in positions_by_sid
    ]

    # For the player dot, prefer the foot sensors.
    # If foot sensors are missing, fall back to extra sensors such as arms.
    used_positions = foot_positions if foot_positions else extra_positions

    if not used_positions:
        return None

    x = sum(float(pos["x"]) for pos in used_positions) / len(used_positions)
    y = sum(float(pos["y"]) for pos in used_positions) / len(used_positions)

    all_used_sids = [
        int(pos["sid"])
        for pos in used_positions
    ]

    latest_ts = max(
        int(pos["ts"])
        for pos in used_positions
        if pos.get("ts") is not None
    )

    match_second_values = [
        int(pos["matchSecond"])
        for pos in used_positions
        if pos.get("matchSecond") is not None
    ]

    match_second = max(match_second_values) if match_second_values else None

    return {
        "name": name,
        "label": short_name(name),
        "type": object_type,
        "team": team,
        "x": x,
        "y": y,
        "ts": latest_ts,
        "matchSecond": match_second,
        "sids": all_used_sids,
    }


def get_ball_objects(
    positions_by_sid: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
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
                "x": float(pos["x"]),
                "y": float(pos["y"]),
                "ts": int(pos["ts"]),
                "matchSecond": (
                    int(pos["matchSecond"])
                    if pos.get("matchSecond") is not None
                    else None
                ),
                "sids": [sid],
            }
        )

    return balls


def build_display_objects(state: dict[str, Any]) -> list[dict[str, Any]]:
    positions = state.get("positions", [])

    positions_by_sid = {
        int(pos["sid"]): pos
        for pos in positions
        if pos.get("sid") is not None
    }

    display_objects = []

    balls = get_ball_objects(positions_by_sid)
    display_objects.extend(balls)

    for name, sensor_definition in TEAM_A_PLAYERS.items():
        player = average_positions(
            name=name,
            sensor_definition=sensor_definition,
            positions_by_sid=positions_by_sid,
            object_type="player",
            team="Team A",
        )

        if player is not None:
            display_objects.append(player)

    for name, sensor_definition in TEAM_B_PLAYERS.items():
        player = average_positions(
            name=name,
            sensor_definition=sensor_definition,
            positions_by_sid=positions_by_sid,
            object_type="player",
            team="Team B",
        )

        if player is not None:
            display_objects.append(player)

    for name, sensor_definition in REFEREE.items():
        referee = average_positions(
            name=name,
            sensor_definition=sensor_definition,
            positions_by_sid=positions_by_sid,
            object_type="referee",
            team=None,
        )

        if referee is not None:
            display_objects.append(referee)

    return display_objects


def add_pitch_lines(fig: go.Figure) -> None:
    x_min = FIELD_X_MIN
    x_max = FIELD_X_MAX
    y_min = FIELD_Y_MIN
    y_max = FIELD_Y_MAX

    field_width = x_max - x_min
    field_height = y_max - y_min

    penalty_depth = field_width * 0.165
    penalty_width = field_height * 0.60

    goal_depth = field_width * 0.055
    goal_width = field_height * 0.30

    center_circle_radius = field_height * 0.135

    line = dict(color="white", width=3)

    shapes = [
        dict(
            type="rect",
            x0=x_min,
            y0=y_min,
            x1=x_max,
            y1=y_max,
            line=line,
        ),
        dict(
            type="line",
            x0=0,
            y0=y_min,
            x1=0,
            y1=y_max,
            line=line,
        ),
        dict(
            type="circle",
            x0=-center_circle_radius,
            y0=-center_circle_radius,
            x1=center_circle_radius,
            y1=center_circle_radius,
            line=line,
        ),
        dict(
            type="rect",
            x0=x_min,
            y0=-penalty_width / 2,
            x1=x_min + penalty_depth,
            y1=penalty_width / 2,
            line=line,
        ),
        dict(
            type="rect",
            x0=x_max - penalty_depth,
            y0=-penalty_width / 2,
            x1=x_max,
            y1=penalty_width / 2,
            line=line,
        ),
        dict(
            type="rect",
            x0=x_min,
            y0=-goal_width / 2,
            x1=x_min + goal_depth,
            y1=goal_width / 2,
            line=line,
        ),
        dict(
            type="rect",
            x0=x_max - goal_depth,
            y0=-goal_width / 2,
            x1=x_max,
            y1=goal_width / 2,
            line=line,
        ),
    ]

    fig.update_layout(shapes=shapes)


def add_object_trace(
    fig: go.Figure,
    objects: list[dict[str, Any]],
    name: str,
    color: str,
    marker_size: int,
    symbol: str = "circle",
) -> None:
    if not objects:
        return

    fig.add_trace(
        go.Scatter(
            x=[obj["x"] for obj in objects],
            y=[obj["y"] for obj in objects],
            mode="markers+text",
            text=[obj["label"] for obj in objects],
            textposition="top center",
            marker=dict(
                size=marker_size,
                color=color,
                symbol=symbol,
                line=dict(width=2, color="white"),
            ),
            name=name,
            customdata=[
                [
                    obj["name"],
                    ", ".join(map(str, obj["sids"])),
                    obj["matchSecond"],
                ]
                for obj in objects
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "sensor ids: %{customdata[1]}<br>"
                "match second: %{customdata[2]}<br>"
                "x: %{x:.0f}<br>"
                "y: %{y:.0f}"
                "<extra></extra>"
            ),
        )
    )


def create_field_figure(state: dict[str, Any]) -> go.Figure:
    display_objects = build_display_objects(state)

    team_a = [
        obj for obj in display_objects
        if obj["team"] == "Team A"
    ]

    team_b = [
        obj for obj in display_objects
        if obj["team"] == "Team B"
    ]

    balls = [
        obj for obj in display_objects
        if obj["type"] == "ball"
    ]

    referees = [
        obj for obj in display_objects
        if obj["type"] == "referee"
    ]

    fig = go.Figure()

    add_object_trace(
        fig=fig,
        objects=team_a,
        name="Team A",
        color="royalblue",
        marker_size=17,
    )

    add_object_trace(
        fig=fig,
        objects=team_b,
        name="Team B",
        color="tomato",
        marker_size=17,
    )

    add_object_trace(
        fig=fig,
        objects=balls,
        name="Ball",
        color="yellow",
        marker_size=20,
        symbol="circle",
    )

    add_object_trace(
        fig=fig,
        objects=referees,
        name="Referee",
        color="black",
        marker_size=16,
        symbol="diamond",
    )

    add_pitch_lines(fig)

    fig.update_layout(
        height=720,
        margin=dict(l=20, r=20, t=20, b=20),
        plot_bgcolor="rgb(30, 150, 45)",
        paper_bgcolor="white",
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="center",
            x=0.5,
        ),
        xaxis=dict(
            range=[FIELD_X_MIN, FIELD_X_MAX],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            fixedrange=True,
        ),
        yaxis=dict(
            range=[FIELD_Y_MIN, FIELD_Y_MAX],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            fixedrange=True,
            scaleanchor="x",
            scaleratio=1,
        ),
    )

    return fig


def main() -> None:
    st.set_page_config(
        page_title="Live Soccer Positions",
        layout="wide",
    )

    st.title("Live Soccer Tracking Demo")

    state = load_positions()

    if state is None:
        st.warning("No live position file found yet.")

        st.code(
            """
python -m src.live_positions_streaming_job
python -m src.replay_full_game
            """.strip(),
            language="bash",
        )

        time.sleep(REFRESH_SECONDS)
        st.rerun()

        return

    raw_positions = state.get("positions", [])
    display_objects = build_display_objects(state)

    current_match_second = state.get("currentMatchSecond")
    batch_id = state.get("batchId", "-")
    current_half = get_current_half(raw_positions)

    cols = st.columns(5)

    cols[0].metric("Visible objects", len(display_objects))
    cols[1].metric("Raw sensors", len(raw_positions))
    cols[2].metric("Match time", format_match_time(current_match_second))
    cols[3].metric("Half", current_half if current_half is not None else "-")
    cols[4].metric("Spark batch", batch_id)

    fig = create_field_figure(state)

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={"displayModeBar": False},
    )

    st.caption(
        "Player dots are averaged from their foot sensors. "
        "If the foot sensors are missing, extra sensors such as arm sensors are used as fallback. "
        "Ball sensors are combined depending on the current half."
    )

    time.sleep(REFRESH_SECONDS)
    st.rerun()


if __name__ == "__main__":
    main()