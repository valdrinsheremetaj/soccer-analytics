from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when
from pathlib import Path
import shutil
from src.config import (
    RAW_SCHEMA,
    RAW_FULL_GAME_PATH,
    CLEAN_FULL_GAME_PATH,
    FIRST_HALF_START_TS,
    FIRST_HALF_END_TS,
    SECOND_HALF_START_TS,
    SECOND_HALF_END_TS,
    GAME_START_TS,
    GAME_END_TS,
    TS_PER_SECOND,
)

def clean_full_game() -> None:
    spark_session = SparkSession.builder.appName("Cleaned Soccer Game Data").getOrCreate()

    df = spark_session.read.format(
        "csv").schema(RAW_SCHEMA).option(
        "header", False).load(RAW_FULL_GAME_PATH)
    
    print(f"Raw rows: {df.count()}")

    first_half_true = (
        (col("ts") >= FIRST_HALF_START_TS) &
        (col("ts") <= FIRST_HALF_END_TS)
    )
    second_half_true = (
        (col("ts") >= SECOND_HALF_START_TS) &
        (col("ts") <= SECOND_HALF_END_TS)
    )

    cleaned_ts_df = df.where(
        first_half_true | second_half_true
    ).withColumn(
        "half", when(first_half_true, 1).otherwise(2)
    ).withColumn(
        "matchSecond", ((col("ts") - GAME_START_TS) / TS_PER_SECOND).cast("int")
    )


    print(f"Cleaned ts rows: {cleaned_ts_df.count()}")

    output_path = Path(CLEAN_FULL_GAME_PATH)

    if output_path.exists():
        shutil.rmtree(output_path)

    cleaned_ts_df.write.mode("overwrite").option("header","true").csv(CLEAN_FULL_GAME_PATH)

    # cleaned_ts_df.write.mode("overwrite").parquet(CLEAN_FULL_GAME_PATH) --> parquet is not human readable, but much faster for analysis : makes sense if queries take a lot of time

    spark_session.stop()


if __name__ == "__main__":
    clean_full_game()