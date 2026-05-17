from pyspark.sql import SparkSession
from pyspark.sql.functions import col, floor
from pyspark.sql.types import StructType, StructField, IntegerType
from pathlib import Path
import shutil

from src.config import (
    CLEAN_SCHEMA,
    CLEAN_FULL_GAME_PATH,
    CHUNKED_FULL_GAME_PATH,
    CHUNK_SECONDS,
)

def split_clean_data_into_chunks() -> None:
    spark_session = SparkSession.builder.appName("Chunked Soccer Game Data").getOrCreate()

    df = spark_session.read.format(
        "csv").schema(CLEAN_SCHEMA).option(
        "header", True).load(CLEAN_FULL_GAME_PATH)
    
    chunked_df = df.withColumn(
        "chunkId", floor(col("matchSecond") / CHUNK_SECONDS).cast("int")
    )

    print(f"Rows to split: {chunked_df.count()}")
    print(f"Chunk size in match seconds: {CHUNK_SECONDS}")

    output_path = Path(CHUNKED_FULL_GAME_PATH)

    if output_path.exists():
        shutil.rmtree(output_path)

    chunked_df.write.mode("overwrite").partitionBy("chunkId").option("header", "true").csv(CHUNKED_FULL_GAME_PATH)

    spark_session.stop()

if __name__ == "__main__":
    split_clean_data_into_chunks()