""""
This script reads the raw CSV data, keeps only records inside the official
match intervals, adds match-time metadata, converts raw coordinates and
movement values to standard units, and writes the result as CSV.
"""

import logging
import shutil
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, lit, when

from src.config import (
    CLEAN_FULL_GAME_PATH,
    FIRST_HALF_END_TS,
    FIRST_HALF_START_TS,
    RAW_FULL_GAME_PATH,
    RAW_SCHEMA,
    SECOND_HALF_END_TS,
    SECOND_HALF_START_TS,
    TS_PER_SECOND,
)


APP_NAME = "Cleaned Soccer Game Data"
SECOND_HALF_OFFSET_SECONDS = 1800.0
MICRO_TO_BASE_UNIT = 1e-6
METERS_PER_SECOND_TO_KMH = 3.6
SPEED_SAMPLE_THRESHOLD_KMH = 5.0

LOGGER = logging.getLogger(__name__)


def create_spark_session() -> SparkSession:
    """Create the Spark session used by the cleaning job."""
    return SparkSession.builder.appName(APP_NAME).getOrCreate()


def read_raw_game_data(spark_session: SparkSession) -> DataFrame:
    """Read the raw full-game CSV file using the configured schema."""
    return (
        spark_session.read.format("csv")
        .schema(RAW_SCHEMA)
        .option("header", False)
        .load(RAW_FULL_GAME_PATH)
    )


def build_cleaned_dataframe(raw_df: DataFrame) -> DataFrame:
    """Filter valid match records and add normalized columns.

    Args:
        raw_df: Raw full-game tracking data.

    Returns:
        A cleaned DataFrame containing only official match records, with
        additional columns for half, continuous match time, coordinates in
        meters, speed in m/s and km/h, and acceleration in m/s².
    """
    first_half_filter = (
        (col("ts") >= FIRST_HALF_START_TS) & (col("ts") <= FIRST_HALF_END_TS)
    )
    second_half_filter = (
        (col("ts") >= SECOND_HALF_START_TS) & (col("ts") <= SECOND_HALF_END_TS)
    )

    first_half_match_second = (
        (col("ts") - lit(FIRST_HALF_START_TS)) / lit(TS_PER_SECOND)
    ).cast("double")
    second_half_match_second = (
        lit(SECOND_HALF_OFFSET_SECONDS)
        + ((col("ts") - lit(SECOND_HALF_START_TS)) / lit(TS_PER_SECOND))
    ).cast("double")

    return (
        raw_df.where(first_half_filter | second_half_filter)
        .withColumn("half", when(first_half_filter, lit(1)).otherwise(lit(2)))
        .withColumn(
            "matchSecond",
            when(col("half") == 1, first_half_match_second).otherwise(
                second_half_match_second
            ),
        )
        # Raw coordinates are stored in millimeters.
        .withColumn("x_m", col("x") / lit(1000.0))
        .withColumn("y_m", col("y") / lit(1000.0))
        .withColumn("z_m", col("z") / lit(1000.0))
        # Raw movement values are stored in micro-units.
        .withColumn("speed_m_s", col("v_abs") * lit(MICRO_TO_BASE_UNIT))
        .withColumn(
            "speed_kmh",
            col("v_abs") * lit(MICRO_TO_BASE_UNIT) * lit(METERS_PER_SECOND_TO_KMH),
        )
        .withColumn(
            "acceleration_m_s2",
            col("a_abs") * lit(MICRO_TO_BASE_UNIT),
        )
    )


def remove_existing_output(output_path: str) -> None:
    """Remove the previous Spark output directory, if it exists."""
    path = Path(output_path)

    if path.exists():
        LOGGER.info("Removing existing output directory: %s", path)
        shutil.rmtree(path)


def write_cleaned_data(cleaned_df: DataFrame, output_path: str) -> None:
    """Write the cleaned DataFrame as CSV with a header row."""
    remove_existing_output(output_path)

    (
        cleaned_df.write.mode("overwrite")
        .option("header", "true")
        .csv(output_path)
    )


def clean_full_game(show_validation_sample: bool = True) -> None:
    """Run the complete full-game cleaning pipeline."""
    spark_session = create_spark_session()

    try:
        raw_df = read_raw_game_data(spark_session)
        cleaned_df = build_cleaned_dataframe(raw_df)

        if show_validation_sample:
            show_speed_sample(cleaned_df)

        write_cleaned_data(cleaned_df, CLEAN_FULL_GAME_PATH)
        LOGGER.info("Cleaned data written to: %s", CLEAN_FULL_GAME_PATH)
    finally:
        spark_session.stop()


def main() -> None:
    """Entry point for running this module as a script."""
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        level=logging.INFO,
    )
    clean_full_game()


if __name__ == "__main__":
    main()
