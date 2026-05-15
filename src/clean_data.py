from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from src.config import (
    SCHEMA,
    RAW_FULL_GAME_PATH,
    CLEAN_FULL_GAME_PATH,
    GAME_START_TS,
    GAME_END_TS,
    TS_PER_SECOND,
)

def clean_full_game() -> None:
    spark_session = SparkSession.builder.appName("Cleaned Soccer Game Data").getOrCreate()

    df = spark_session.read.format(
        "csv").schema(SCHEMA).option(
        "header", False).load(RAW_FULL_GAME_PATH)
    
    print(f"Raw rows: {df.count()}")

    cleaned_ts_df = df.where(
        (col("ts") >= GAME_START_TS) & 
        (col("ts") <= GAME_END_TS)
    ).withColumn(
        "matchSecond", ((col("ts") - GAME_START_TS) / TS_PER_SECOND).cast("int")
    )


    print(f"Cleaned ts rows: {cleaned_ts_df.count()}")

    cleaned_ts_df.write.mode("overwrite").option("header","true").csv(CLEAN_FULL_GAME_PATH)

    # cleaned_ts_df.write.mode("overwrite").parquet(CLEAN_FULL_GAME_PATH) --> parquet is not human readable, but much faster for analysis : makes sense if queries take a lot of time

    spark_session.stop()


if __name__ == "__main__":
    clean_full_game()