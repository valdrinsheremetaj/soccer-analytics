"""Run the Spark Structured Streaming demo for live soccer positions.

This module consumes replayed Parquet chunks from ``STREAM_INPUT_PATH`` and writes
small JSON files that the Streamlit dashboard can read. It maintains two live
outputs:

* the latest position for each visible sensor
* rolling one-minute running statistics grouped by sensor and intensity zone
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pyspark.sql.functions as F
from pyspark.sql import DataFrame, Row, SparkSession, Window
from pyspark.sql.functions import col, row_number

from src.config import (
    BALL_SENSOR_IDS,
    CLEAN_SCHEMA,
    FIELD_X_MAX,
    FIELD_X_MIN,
    FIELD_Y_MAX,
    FIELD_Y_MIN,
)
from src.heatmap_analysis import HeatmapAnalyzer

LOGGER = logging.getLogger(__name__)

APP_NAME = "Live Soccer Positions Demo"

STREAM_INPUT_PATH = Path("data/stream_input")
POSITIONS_FILE = Path("data/output/live_positions/positions.json")
STATS_FILE = Path("data/output/live_positions/stats_1m.json")

POSITIONS_CHECKPOINT = Path("checkpoints/live_positions")
STATS_CHECKPOINT = Path("checkpoints/stats_1m")

MAX_FILES_PER_TRIGGER = 1
PROCESSING_TRIGGER = "1 second"
SHUFFLE_PARTITIONS = "4"
WATERMARK_DELAY = "5 seconds"
ROLLING_WINDOW_DURATION = "1 minute"

HEATMAP_COLUMNS = 13
HEATMAP_ROWS = 8

BALL_SAMPLE_INTERVAL_SECONDS = 0.0005
PLAYER_SAMPLE_INTERVAL_SECONDS = 0.005

SPRINT_THRESHOLD_KMH = 24.0
HIGH_SPEED_THRESHOLD_KMH = 14.0
LOW_SPEED_THRESHOLD_KMH = 11.0
TROT_THRESHOLD_KMH = 1.0

JsonDict = dict[str, Any]
PositionBySensor = dict[int, JsonDict]
StatsBySensor = dict[int, dict[str, JsonDict]]


def configure_logging() -> None:
    """Configure a simple application logger."""
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )


def write_json_atomic(path: Path, payload: JsonDict) -> None:
    """Write JSON through a temporary file and then atomically replace the target.

    Atomic replacement prevents the dashboard from reading a partially written
    JSON file while Spark is updating the output.

    Args:
        path: Final JSON file path.
        payload: JSON-serializable data to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")

    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    os.replace(tmp_path, path)


def remove_path_if_exists(path: Path) -> None:
    """Remove a file or directory if it already exists.

    Args:
        path: File or directory to remove.
    """
    if not path.exists():
        return

    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def prepare_runtime_directories() -> None:
    """Reset output and checkpoint directories before starting the demo."""
    remove_path_if_exists(POSITIONS_FILE.parent)
    remove_path_if_exists(POSITIONS_CHECKPOINT)
    remove_path_if_exists(STATS_CHECKPOINT)

    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STREAM_INPUT_PATH.mkdir(parents=True, exist_ok=True)


def create_spark_session() -> SparkSession:
    """Create and configure the Spark session used by the streaming demo.

    Returns:
        Configured Spark session.
    """
    spark = SparkSession.builder.appName(APP_NAME).getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    spark.conf.set("spark.sql.shuffle.partitions", SHUFFLE_PARTITIONS)
    return spark


def read_position_stream(spark: SparkSession) -> DataFrame:
    """Read replayed Parquet chunks as a structured streaming source.

    Args:
        spark: Active Spark session.

    Returns:
        Streaming DataFrame with the configured clean schema.
    """
    return (
        spark.readStream.format("parquet")
        .schema(CLEAN_SCHEMA)
        .option("maxFilesPerTrigger", MAX_FILES_PER_TRIGGER)
        .load(str(STREAM_INPUT_PATH))
    )


def filter_valid_positions(position_stream: DataFrame) -> DataFrame:
    """Keep only rows that contain valid sensor positions inside the field.

    Args:
        position_stream: Raw streaming DataFrame.

    Returns:
        Filtered streaming DataFrame.
    """
    required_columns_present = (
        col("sid").isNotNull()
        & col("ts").isNotNull()
        & col("x").isNotNull()
        & col("y").isNotNull()
    )
    inside_field_bounds = (
        (col("x") >= FIELD_X_MIN)
        & (col("x") <= FIELD_X_MAX)
        & (col("y") >= FIELD_Y_MIN)
        & (col("y") <= FIELD_Y_MAX)
    )

    return position_stream.where(required_columns_present & inside_field_bounds)


def classify_intensity(speed_column: F.Column) -> F.Column:
    """Classify speed into simple running-intensity zones.

    Args:
        speed_column: Column containing speed in km/h.

    Returns:
        Spark column with the intensity label.
    """
    return (
        F.when(speed_column > SPRINT_THRESHOLD_KMH, "Sprint")
        .when(speed_column > HIGH_SPEED_THRESHOLD_KMH, "High-Speed Run")
        .when(speed_column > LOW_SPEED_THRESHOLD_KMH, "Low-Speed Run")
        .when(speed_column > TROT_THRESHOLD_KMH, "Trot")
        .otherwise("Standing")
    )


def build_running_stats_stream(valid_positions: DataFrame) -> DataFrame:
    """Build the rolling one-minute running-statistics stream.

    The statistics are computed for player sensors only. Ball sensors are
    excluded because ball movement would dominate the running-speed categories.

    Args:
        valid_positions: Filtered position stream.

    Returns:
        Aggregated streaming DataFrame grouped by sensor, intensity, and window.
    """
    player_positions = valid_positions.where(~F.col("sid").isin(BALL_SENSOR_IDS))

    enriched_stream = (
        player_positions.withColumn("event_time", F.expr("timestamp_seconds(matchSecond)"))
        .withColumn("intensity", classify_intensity(F.col("speed_kmh")))
        # Sensor samples represent short time intervals. Multiplying speed by
        # this interval gives an approximate distance increment per row.
        .withColumn("dt_seconds", F.lit(PLAYER_SAMPLE_INTERVAL_SECONDS))
        .withColumn("distance_covered", (F.col("speed_kmh") / 3.6) * F.col("dt_seconds"))
        .withWatermark("event_time", WATERMARK_DELAY)
    )

    return (
        enriched_stream.groupBy(
            F.col("sid"),
            F.col("intensity"),
            F.window(F.col("event_time"), ROLLING_WINDOW_DURATION),
        )
        .agg(
            F.sum("distance_covered").alias("distance_1m"),
            F.count("sid").alias("ping_count"),
        )
    )


def row_to_position(row: Row) -> JsonDict:
    """Convert a Spark row into a dashboard-friendly position dictionary.

    Args:
        row: Spark row from the newest-position micro-batch result.

    Returns:
        JSON-serializable position dictionary.
    """
    row_data = row.asDict()

    return {
        "sid": int(row_data["sid"]),
        "ts": int(row_data["ts"]),
        "x": float(row_data["x"]),
        "y": float(row_data["y"]),
        "z": float(row_data["z"]) if row_data.get("z") is not None else None,
        "half": int(row_data["half"]) if row_data.get("half") is not None else None,
        "matchSecond": (
            float(row_data["matchSecond"])
            if row_data.get("matchSecond") is not None
            else None
        ),
        "speed_kmh": (
            float(row_data["speed_kmh"])
            if row_data.get("speed_kmh") is not None
            else 0.0
        ),
    }


def get_current_match_second(latest_positions: PositionBySensor) -> float | None:
    """Return the latest visible match second across all sensors.

    Args:
        latest_positions: Latest known position for each sensor.

    Returns:
        Current match second, or ``None`` if no position has a match timestamp.
    """
    return max(
        (
            position["matchSecond"]
            for position in latest_positions.values()
            if position.get("matchSecond") is not None
        ),
        default=None,
    )


def build_positions_payload(
    batch_id: int,
    latest_positions: PositionBySensor,
    analyzer: HeatmapAnalyzer,
) -> JsonDict:
    """Create the JSON payload consumed by the Streamlit dashboard.

    Args:
        batch_id: Spark micro-batch identifier.
        latest_positions: Latest known position for each sensor.
        analyzer: Heatmap analyzer containing accumulated zone counts.

    Returns:
        JSON-serializable dashboard state.
    """
    return {
        "batchId": int(batch_id),
        "generatedAtUnix": time.time(),
        "currentMatchSecond": get_current_match_second(latest_positions),
        "field": {
            "xMin": FIELD_X_MIN,
            "xMax": FIELD_X_MAX,
            "yMin": FIELD_Y_MIN,
            "yMax": FIELD_Y_MAX,
        },
        "positions": list(latest_positions.values()),
        "heatmap_by_sid": analyzer.get_grids(),
    }


def create_positions_batch_processor(
    latest_positions: PositionBySensor,
    analyzer: HeatmapAnalyzer,
) -> Callable[[DataFrame, int], None]:
    """Create the foreachBatch callback for the live position output.

    Args:
        latest_positions: Mutable state containing the latest row per sensor.
        analyzer: Heatmap analyzer updated after every micro-batch.

    Returns:
        Function compatible with Spark ``foreachBatch``.
    """

    def process_batch(batch_df: DataFrame, batch_id: int) -> None:
        """Process one Spark micro-batch of position data."""
        if batch_df.isEmpty():
            return

        latest_row_window = Window.partitionBy("sid").orderBy(col("ts").desc())
        newest_per_sensor = (
            batch_df.withColumn("row_number", row_number().over(latest_row_window))
            .where(col("row_number") == 1)
            .drop("row_number")
        )

        for row in newest_per_sensor.collect():
            position = row_to_position(row)
            latest_positions[int(position["sid"])] = position

        # The heatmap uses the currently visible sensor positions as a simple
        # approximation of time spent in each zone.
        analyzer.update_from_positions(list(latest_positions.values()))

        payload = build_positions_payload(batch_id, latest_positions, analyzer)
        write_json_atomic(POSITIONS_FILE, payload)

    return process_batch


def get_sensor_sample_interval_seconds(sensor_id: int) -> float:
    """Return the sampling interval used for a sensor.

    Args:
        sensor_id: Sensor identifier.

    Returns:
        Sampling interval in seconds.
    """
    if sensor_id in BALL_SENSOR_IDS:
        return BALL_SAMPLE_INTERVAL_SECONDS
    return PLAYER_SAMPLE_INTERVAL_SECONDS


def create_stats_batch_processor(
    latest_stats: StatsBySensor,
) -> Callable[[DataFrame, int], None]:
    """Create the foreachBatch callback for rolling running statistics.

    Args:
        latest_stats: Mutable state containing the latest stats by sensor.

    Returns:
        Function compatible with Spark ``foreachBatch``.
    """

    def process_stats_batch(batch_df: DataFrame, batch_id: int) -> None:
        """Process one Spark micro-batch of aggregated running statistics."""
        if batch_df.isEmpty():
            return

        for row in batch_df.collect():
            sensor_id = int(row["sid"])
            intensity = str(row["intensity"])

            latest_stats.setdefault(sensor_id, {})
            sample_interval = get_sensor_sample_interval_seconds(sensor_id)

            latest_stats[sensor_id][intensity] = {
                "distance_1m": float(row["distance_1m"]),
                "time_1m": int(row["ping_count"]) * sample_interval,
            }

        write_json_atomic(STATS_FILE, {"batchId": int(batch_id), "stats": latest_stats})

    return process_stats_batch


def start_streaming_queries(
    valid_positions: DataFrame,
    running_stats_1m: DataFrame,
    process_positions_batch: Callable[[DataFrame, int], None],
    process_stats_batch: Callable[[DataFrame, int], None],
) -> None:
    """Start both streaming queries and block until one terminates.

    Args:
        valid_positions: Filtered live position stream.
        running_stats_1m: Aggregated rolling statistics stream.
        process_positions_batch: Callback writing latest positions to JSON.
        process_stats_batch: Callback writing rolling stats to JSON.
    """
    stats_query = (
        running_stats_1m.writeStream.foreachBatch(process_stats_batch)
        .outputMode("update")
        .option("checkpointLocation", str(STATS_CHECKPOINT))
        .trigger(processingTime=PROCESSING_TRIGGER)
        .start()
    )

    positions_query = (
        valid_positions.writeStream.foreachBatch(process_positions_batch)
        .outputMode("append")
        .option("checkpointLocation", str(POSITIONS_CHECKPOINT))
        .trigger(processingTime=PROCESSING_TRIGGER)
        .start()
    )

    LOGGER.info("Started positions query: %s", positions_query.id)
    LOGGER.info("Started rolling stats query: %s", stats_query.id)

    while positions_query.isActive and stats_query.isActive:
        time.sleep(1)

    positions_exception = positions_query.exception()
    stats_exception = stats_query.exception()

    if positions_exception is not None:
        raise RuntimeError(f"Positions query failed: {positions_exception}")

    if stats_exception is not None:
        raise RuntimeError(f"Stats query failed: {stats_exception}")


def main() -> None:
    """Run the live positions streaming demo."""
    configure_logging()
    prepare_runtime_directories()

    latest_positions: PositionBySensor = {}
    latest_stats: StatsBySensor = {}

    analyzer = HeatmapAnalyzer(
        FIELD_X_MIN,
        FIELD_X_MAX,
        FIELD_Y_MIN,
        FIELD_Y_MAX,
        cols=HEATMAP_COLUMNS,
        rows=HEATMAP_ROWS,
    )

    spark = create_spark_session()

    try:
        position_stream = read_position_stream(spark)
        valid_positions = filter_valid_positions(position_stream)
        running_stats_1m = build_running_stats_stream(valid_positions)

        process_positions_batch = create_positions_batch_processor(
            latest_positions,
            analyzer,
        )
        process_stats_batch = create_stats_batch_processor(latest_stats)

        LOGGER.info("Starting live positions streaming demo.")
        start_streaming_queries(
            valid_positions,
            running_stats_1m,
            process_positions_batch,
            process_stats_batch,
        )
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
