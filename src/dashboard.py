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

FIELD_X_MIN = -68000
FIELD_X_MAX = 68000
FIELD_Y_MIN = -32500
FIELD_Y_MAX = 32500

HEATMAP_OFFSET_X = 0
HEATMAP_OFFSET_Y = -29000
  
def load_positions() -> dict[str, Any] | None:
    if not POSITIONS_PATH.exists(): return None
    try:
        with POSITIONS_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError: return None

def format_match_time(match_second: float | None) -> str:
    if match_second is None: return "-"
    m_sec_int = int(match_second)
    return f"{m_sec_int // 60:02d}:{m_sec_int % 60:02d}"

def short_name(name: str) -> str:
    parts = name.split()
    return name if len(parts) == 1 else f"{parts[0][0]}. {parts[-1]}"

def get_current_half(positions: list[dict[str, Any]]) -> int | None:
    halves = [int(pos["half"]) for pos in positions if pos.get("half") is not None]
    return max(halves) if halves else None

def average_positions(name: str, sensor_definition: dict[str, list[int]], positions_by_sid: dict[int, dict[str, Any]], object_type: str, team: str | None) -> dict[str, Any] | None:
    used_positions = [positions_by_sid[sid] for sid in sensor_definition["feet"] if sid in positions_by_sid]
    if not used_positions: used_positions = [positions_by_sid[sid] for sid in sensor_definition["extra"] if sid in positions_by_sid]
    if not used_positions: return None
    return {
        "name": name, "label": short_name(name), "type": object_type, "team": team,
        "x": sum(float(pos["x"]) for pos in used_positions) / len(used_positions),
        "y": sum(float(pos["y"]) for pos in used_positions) / len(used_positions),
        "ts": max(int(pos["ts"]) for pos in used_positions if pos.get("ts") is not None),
        "matchSecond": max([float(pos["matchSecond"]) for pos in used_positions if pos.get("matchSecond") is not None], default=None),
        "sids": [int(pos["sid"]) for pos in used_positions],
        "speed_kmh": sum(float(pos.get("speed_kmh", 0.0)) for pos in used_positions) / len(used_positions),
    }

def get_ball_objects(positions_by_sid: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "name": f"Ball {sid}", "label": f"Ball {sid}", "type": "ball", "team": None,
        "x": float(positions_by_sid[sid]["x"]), "y": float(positions_by_sid[sid]["y"]),
        "ts": int(positions_by_sid[sid]["ts"]),
        "matchSecond": float(positions_by_sid[sid]["matchSecond"]) if positions_by_sid[sid].get("matchSecond") is not None else None,
        "sids": [sid], "speed_kmh": float(positions_by_sid[sid].get("speed_kmh", 0.0)),
    } for sid in ALL_BALL_IDS if sid in positions_by_sid]

def build_display_objects(state: dict[str, Any]) -> list[dict[str, Any]]:
    positions_by_sid = {int(pos["sid"]): pos for pos in state.get("positions", []) if pos.get("sid") is not None}
    display_objects = get_ball_objects(positions_by_sid)
    for name, sd in TEAM_A_PLAYERS.items():
        if p := average_positions(name, sd, positions_by_sid, "player", "Team A"): display_objects.append(p)
    for name, sd in TEAM_B_PLAYERS.items():
        if p := average_positions(name, sd, positions_by_sid, "player", "Team B"): display_objects.append(p)
    for name, sd in REFEREE.items():
        if p := average_positions(name, sd, positions_by_sid, "referee", None): display_objects.append(p)
    return display_objects

def add_pitch_lines(fig: go.Figure) -> None:
    field_width, field_height = FIELD_X_MAX - FIELD_X_MIN, FIELD_Y_MAX - FIELD_Y_MIN
    pen_d, pen_w = field_width * 0.165, field_height * 0.60
    goal_d, goal_w = field_width * 0.055, field_height * 0.30
    c_rad = field_height * 0.135
    line = dict(color="white", width=3)
    fig.update_layout(shapes=[
        dict(type="rect", x0=FIELD_X_MIN, y0=FIELD_Y_MIN, x1=FIELD_X_MAX, y1=FIELD_Y_MAX, line=line),
        dict(type="line", x0=0, y0=FIELD_Y_MIN, x1=0, y1=FIELD_Y_MAX, line=line),
        dict(type="circle", x0=-c_rad, y0=-c_rad, x1=c_rad, y1=c_rad, line=line),
        dict(type="rect", x0=FIELD_X_MIN, y0=-pen_w/2, x1=FIELD_X_MIN+pen_d, y1=pen_w/2, line=line),
        dict(type="rect", x0=FIELD_X_MAX-pen_d, y0=-pen_w/2, x1=FIELD_X_MAX, y1=pen_w/2, line=line),
        dict(type="rect", x0=FIELD_X_MIN, y0=-goal_w/2, x1=FIELD_X_MIN+goal_d, y1=goal_w/2, line=line),
        dict(type="rect", x0=FIELD_X_MAX-goal_d, y0=-goal_w/2, x1=FIELD_X_MAX, y1=goal_w/2, line=line),
    ])

def add_object_trace(fig: go.Figure, objects: list[dict], name: str, color: str, marker_size: int, symbol: str = "circle", opacity: float = 1.0, is_trail: bool = False) -> None:
    if not objects: return
    stretch_x, stretch_y, offset_y, offset_x = 2.0, 1.0, -31000, -6000
    fig.add_trace(go.Scatter(
        x=[obj["y"] * stretch_x + offset_x for obj in objects], y=[obj["x"] * stretch_y + offset_y for obj in objects],
        mode="markers+text" if not is_trail else "markers", text=[obj["label"] for obj in objects] if not is_trail else None,
        textposition="bottom center", opacity=opacity,
        marker=dict(size=marker_size, color=color, symbol=symbol, line=dict(width=2 if not is_trail else 0, color="white")),
        name=name, showlegend=not is_trail, hoverinfo="none" if is_trail else None,
        customdata=[[obj["name"], ", ".join(map(str, obj["sids"])), obj["matchSecond"], obj.get("speed_kmh", 0.0)] for obj in objects] if not is_trail else None,
        hovertemplate="<b>%{customdata[0]}</b><br>sensor ids: %{customdata[1]}<br>match second: %{customdata[2]}<br>speed: %{customdata[3]:.1f} km/h<br>x: %{x:.0f}<br>y: %{y:.0f}<extra></extra>" if not is_trail else None,
    ))

def create_field_figure(state: dict[str, Any], show_trails: bool = True, show_heatmap: bool = False, heatmap_selection: str = "All") -> go.Figure:
    display_objects = build_display_objects(state)
    batch_id = state.get("batchId", 0)

    if "trail_history" not in st.session_state: st.session_state.trail_history = {}
    st.session_state.trail_history[batch_id] = display_objects
    
    recent_batches = sorted(st.session_state.trail_history.keys())[-5:]
    st.session_state.trail_history = {b: st.session_state.trail_history[b] for b in recent_batches}

    fig = go.Figure()

    # --- NEW: Dynamic Filtered Heatmap Layer ---
    heatmap_by_sid = state.get("heatmap_by_sid")
    if show_heatmap and heatmap_by_sid:
        stretch_x, stretch_y, offset_y, offset_x = 2.0, 1.0, -31000, 0
        x_bins, y_bins = 13, 8
        
        # 1. Figure out which sensor IDs belong to the dropdown selection
        target_sids = set()
        if heatmap_selection != "All":
            if heatmap_selection == "Team A":
                for p in TEAM_A_PLAYERS.values(): target_sids.update(p["feet"] + p["extra"])
            elif heatmap_selection == "Team B":
                for p in TEAM_B_PLAYERS.values(): target_sids.update(p["feet"] + p["extra"])
            elif heatmap_selection in TEAM_A_PLAYERS:
                target_sids.update(TEAM_A_PLAYERS[heatmap_selection]["feet"] + TEAM_A_PLAYERS[heatmap_selection]["extra"])
            elif heatmap_selection in TEAM_B_PLAYERS:
                target_sids.update(TEAM_B_PLAYERS[heatmap_selection]["feet"] + TEAM_B_PLAYERS[heatmap_selection]["extra"])

        # 2. Combine only the grids that match the selected SIDs
        combined_grid = [[0 for _ in range(x_bins)] for _ in range(y_bins)]
        for sid_str, grid in heatmap_by_sid.items():
            sid = int(sid_str)
            if heatmap_selection == "All" or sid in target_sids:
                for r in range(y_bins):
                    for c in range(x_bins):
                        combined_grid[r][c] += grid[r][c]

        # 3. Draw the combined grid
        DATA_X_MIN, DATA_X_MAX = -65000, 65000
        DATA_Y_MIN, DATA_Y_MAX = -34000, 34000

        raw_x_width = (DATA_X_MAX - DATA_X_MIN) / x_bins
        raw_y_height = (DATA_Y_MAX - DATA_Y_MIN) / y_bins
        
        # Calculate exactly 14 boundary edges for X, and 9 boundary edges for Y
        raw_x_edges = [DATA_X_MIN + i * raw_x_width for i in range(x_bins + 1)]
        raw_y_edges = [DATA_Y_MIN + i * raw_y_height for i in range(y_bins + 1)]

        # Apply the EXACT SAME math transformation applied to the player dots
        ui_x_edges = [y * stretch_x + offset_x for y in raw_y_edges]
        ui_y_edges = [x * stretch_y + offset_y for x in raw_x_edges]

        transposed_grid = [[combined_grid[r][c] for r in range(y_bins)] for c in range(x_bins)]

        fig.add_trace(go.Heatmap(
            z=transposed_grid, x=ui_x_edges, y=ui_y_edges,
            colorscale="Inferno", opacity=0.6, showscale=False,
            name=f"Heat Map ({heatmap_selection})", hoverinfo="none"
        ))

    add_pitch_lines(fig)

    if show_trails:
        for i, b_id in enumerate(recent_batches[:-1]):
            hist = st.session_state.trail_history[b_id]
            fade = (i + 1) / len(recent_batches) * 0.7 
            add_object_trace(fig, [o for o in hist if o["team"] == "Team A"], "Team A", "royalblue", 10, opacity=fade, is_trail=True)
            add_object_trace(fig, [o for o in hist if o["team"] == "Team B"], "Team B", "tomato", 10, opacity=fade, is_trail=True)
            add_object_trace(fig, [o for o in hist if o["type"] == "ball"], "Ball", "yellow", 10, "circle", opacity=fade, is_trail=True)

    add_object_trace(fig, [o for o in display_objects if o["team"] == "Team A"], "Team A", "royalblue", 17)
    add_object_trace(fig, [o for o in display_objects if o["team"] == "Team B"], "Team B", "tomato", 17)
    add_object_trace(fig, [o for o in display_objects if o["type"] == "ball"], "Ball", "yellow", 20)
    add_object_trace(fig, [o for o in display_objects if o["type"] == "referee"], "Referee", "black", 16, "square")

    fig.update_layout(
        height=800, margin=dict(l=20, r=20, t=20, b=20),
        plot_bgcolor="rgb(30, 150, 45)", paper_bgcolor="white",
        showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=14, color="black"), bgcolor="rgba(255, 255, 255, 0.9)", bordercolor="black", borderwidth=1),
        xaxis=dict(range=[FIELD_X_MIN, FIELD_X_MAX], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        yaxis=dict(range=[FIELD_Y_MIN * 1.2, FIELD_Y_MAX * 1.2], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True, scaleanchor="x", scaleratio=1),
    )
    return fig

def main() -> None:
    st.set_page_config(page_title="Live Soccer Positions", layout="wide")
    st.title("Live Soccer Tracking Demo")

    if (state := load_positions()) is None:
        st.warning("No live position file found yet.")
        time.sleep(REFRESH_SECONDS)
        st.rerun()
        return

    raw_positions = state.get("positions", [])
    display_objects = build_display_objects(state)
    
    st.sidebar.title("Display Controls")
    show_trails = st.sidebar.toggle("Show Velocity Trails", value=True)
    show_heatmap = st.sidebar.toggle("Show Live Heat Map", value=False)
    
    # --- NEW: Dropdown to filter Heatmap by Team or Player ---
    heatmap_options = ["All", "Team A", "Team B"] + list(TEAM_A_PLAYERS.keys()) + list(TEAM_B_PLAYERS.keys())
    heatmap_selection = st.sidebar.selectbox("Heat Map Focus", heatmap_options, disabled=not show_heatmap)
    
    st.sidebar.divider()
    
    st.sidebar.subheader("Fastest Players (Current)")
    players_only = [obj for obj in display_objects if obj["type"] == "player"]
    for i, p in enumerate(sorted(players_only, key=lambda p: p.get("speed_kmh", 0), reverse=True)[:5]):
        speed = p.get('speed_kmh', 0)
        intensity = "🔴 Sprint" if speed > 24 else "🟡 High-Speed Run" if speed > 14 else "🟢 Low-Speed Run" if speed > 11 else "🚶 Trot" if speed > 1 else "🧍 Standing"
        st.sidebar.markdown(f"**{i+1}. {p['name']}** ({p['team']})  \n{speed:.1f} km/h - {intensity}")

    st.sidebar.divider()

    cols = st.columns(5)
    cols[0].metric("Visible objects", len(display_objects))
    cols[1].metric("Raw sensors", len(raw_positions))
    cols[2].metric("Match time", format_match_time(state.get("currentMatchSecond")))
    cols[3].metric("Half", get_current_half(raw_positions) or "-")
    cols[4].metric("Spark batch", state.get("batchId", "-"))

    fig = create_field_figure(state, show_trails=show_trails, show_heatmap=show_heatmap, heatmap_selection=heatmap_selection)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    time.sleep(REFRESH_SECONDS)
    st.rerun()

if __name__ == "__main__":
    main()