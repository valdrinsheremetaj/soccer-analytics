from pyspark.sql import SparkSession
from pyspark.sql.functions import col, window, count
from pathlib import Path

from src.config import CLEAN_SCHEMA, STREAM_INPUT_PATH

OUTPUT_PATH = "data/output/events_per_sensor"
CHECKPOINT_PATH = "checkpoints/events_per_sensor"


def run_streaming_job() -> None:

    Path(STREAM_INPUT_PATH).mkdir(parents=True, exist_ok=True)

    spark = (
        SparkSession.builder
        .appName("Soccer Streaming Job")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")

    df = (
        spark.readStream
        .format("csv")
        .schema(CLEAN_SCHEMA)
        .option("header", "true")
        .load(STREAM_INPUT_PATH)
    )

    # matchSecond is only an integer for now, so we start simple:
    result = (
        df.groupBy("sid", "half")
        .agg(count("*").alias("event_count"))
        .orderBy(col("event_count").desc())
    )

    query = (
        result.writeStream
        .outputMode("complete")
        .format("console")
        .option("truncate", "false")
        .option("checkpointLocation", CHECKPOINT_PATH)
        .start()
    )

    query.awaitTermination()


if __name__ == "__main__":
    run_streaming_job()