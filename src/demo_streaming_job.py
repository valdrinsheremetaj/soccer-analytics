from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql.functions import col, row_number

from src.config import CLEAN_SCHEMA, FIELD_X_MIN, FIELD_X_MAX, FIELD_Y_MIN, FIELD_Y_MAX
# --- NEW: Import the Heatmap Engine ---
from src.heatmap_analysis import HeatmapAnalyzer

STREAM_INPUT_PATH = Path("data/stream_input")
OUTPUT_FILE = Path("data/output/live_positions/positions.json")
CHECKPOINT_PATH = Path("checkpoints/live_positions")

def write_json_atomic(path: Path, payload: dict) -> None:
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)

def main() -> None:
    if OUTPUT_FILE.parent.exists():
        shutil.rmtree(OUTPUT_FILE.parent)
    if CHECKPOINT_PATH.exists():
        shutil.rmtree(CHECKPOINT_PATH)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    STREAM_INPUT_PATH.mkdir(parents=True, exist_ok=True)

    latest_positions: dict[int, dict] = {}
    
    # --- NEW: Initialize the 8x13 Grid Global State ---
    analyzer = HeatmapAnalyzer(FIELD_X_MIN, FIELD_X_MAX, FIELD_Y_MIN, FIELD_Y_MAX, cols=13, rows=8)

    spark = SparkSession.builder.appName("Live Soccer Positions Demo").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    
    spark.conf.set("spark.sql.shuffle.partitions", "4")

    print("Starting live positions streaming demo...")

    df = spark.readStream.format("parquet").schema(CLEAN_SCHEMA).option("header", "true").load(str(STREAM_INPUT_PATH))

    valid_positions = df.where(
        col("sid").isNotNull() & col("ts").isNotNull() & col("x").isNotNull() & col("y").isNotNull()
        & (col("x") >= FIELD_X_MIN) & (col("x") <= FIELD_X_MAX) & (col("y") >= FIELD_Y_MIN) & (col("y") <= FIELD_Y_MAX)
    )

    def process_batch(batch_df: DataFrame, batch_id: int) -> None:
        nonlocal latest_positions
        nonlocal analyzer

        if batch_df.isEmpty():
            return

        window = Window.partitionBy("sid").orderBy(col("ts").desc())
        newest_per_sid = batch_df.withColumn("row_number", row_number().over(window)).where(col("row_number") == 1).drop("row_number")
        rows = newest_per_sid.collect()

        for row in rows:
            sid = int(row["sid"])
            latest_positions[sid] = {
                "sid": sid,
                "ts": int(row["ts"]),
                "x": float(row["x"]),
                "y": float(row["y"]),
                "z": float(row["z"]) if row["z"] is not None else None,
                "half": int(row["half"]) if row["half"] is not None else None,
                "matchSecond": float(row["matchSecond"]) if row["matchSecond"] is not None else None,
                "speed_kmh": float(row["speed_kmh"]) if "speed_kmh" in row.asDict() and row["speed_kmh"] is not None else 0.0,
            }

        # --- NEW: Update Heatmap with Time Spent in Zones ---
        analyzer.update_from_positions(list(latest_positions.values()))

        current_match_second = max((position["matchSecond"] for position in latest_positions.values() if position["matchSecond"] is not None), default=None)

        payload = {
            "batchId": int(batch_id),
            "generatedAtUnix": time.time(),
            "currentMatchSecond": current_match_second,
            "field": {"xMin": FIELD_X_MIN, "xMax": FIELD_X_MAX, "yMin": FIELD_Y_MIN, "yMax": FIELD_Y_MAX},
            "positions": list(latest_positions.values()),
            "heatmap_by_sid": analyzer.get_grids(), # --- NEW: Export the Matrix ---
        }
        write_json_atomic(OUTPUT_FILE, payload)

    query = valid_positions.writeStream.foreachBatch(process_batch).outputMode("append").option("checkpointLocation", CHECKPOINT_PATH).trigger(processingTime="1 second").start()
    query.awaitTermination()

if __name__ == "__main__":
    main()