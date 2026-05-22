"""
This script reads the cleaned full-game soccer dataset, assigns each row to a
match-time chunk, and writes the result as a partitioned Parquet dataset.
"""

import logging
import shutil
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from src.config import (
    CHUNK_SECONDS,
    CHUNKED_FULL_GAME_PATH,
    CLEAN_FULL_GAME_PATH,
    CLEAN_SCHEMA,
)

APP_NAME = "Chunked Soccer Game Data"

LOGGER = logging.getLogger(__name__)


def create_spark_session(app_name: str = APP_NAME) -> SparkSession:
    """Create and return a Spark session.

    Args:
        app_name: Name shown in the Spark UI.

    Returns:
        Configured Spark session.
    """
    return SparkSession.builder.appName(app_name).getOrCreate()


def read_clean_data(spark_session: SparkSession) -> DataFrame:
    """Read the cleaned soccer tracking dataset.

    Args:
        spark_session: Active Spark session.

    Returns:
        DataFrame containing the cleaned full-game data.
    """
    return (
        spark_session.read.format("csv")
        .schema(CLEAN_SCHEMA)
        .option("header", True)
        .load(CLEAN_FULL_GAME_PATH)
    )


def add_chunk_id(dataframe: DataFrame) -> DataFrame:
    """Add a chunk identifier based on the match second.

    The first chunk starts at match second 0. For example, with a chunk size of
    10 seconds, rows from [0, 10) are assigned to chunk 0, rows from [10, 20)
    are assigned to chunk 1, and so on.

    Args:
        dataframe: Cleaned soccer tracking DataFrame.

    Returns:
        DataFrame with an additional ``chunkId`` column.
    """
    return dataframe.withColumn(
        "chunkId",
        F.floor(F.col("matchSecond") / F.lit(CHUNK_SECONDS)).cast("int"),
    )


def remove_existing_output(output_path: str) -> None:
    """Delete the output directory if it already exists.

    Args:
        output_path: Directory where the chunked dataset will be written.
    """
    path = Path(output_path)

    if path.exists():
        LOGGER.info("Removing existing output directory: %s", path)
        shutil.rmtree(path)


def write_chunked_data(dataframe: DataFrame, output_path: str) -> None:
    """Write the chunked dataset as partitioned Parquet files.

    Args:
        dataframe: DataFrame containing a ``chunkId`` column.
        output_path: Directory where the partitioned Parquet files are written.
    """
    dataframe.write.mode("overwrite").partitionBy("chunkId").parquet(output_path)


def split_clean_data_into_chunks() -> None:
    """Split the cleaned full-game dataset into match-time chunks."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    spark_session = create_spark_session()

    try:
        clean_data = read_clean_data(spark_session)
        chunked_data = add_chunk_id(clean_data)

        LOGGER.info("Rows to split: %s", chunked_data.count())
        LOGGER.info("Chunk size in match seconds: %s", CHUNK_SECONDS)

        remove_existing_output(CHUNKED_FULL_GAME_PATH)
        write_chunked_data(chunked_data, CHUNKED_FULL_GAME_PATH)

        LOGGER.info("Chunked dataset written to: %s", CHUNKED_FULL_GAME_PATH)
    finally:
        spark_session.stop()


if __name__ == "__main__":
    split_clean_data_into_chunks()
