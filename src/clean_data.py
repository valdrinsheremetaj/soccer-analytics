from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, lit
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
    TS_PER_SECOND,
)

def clean_full_game() -> None:
    spark_session = SparkSession.builder.appName("Cleaned Soccer Game Data").getOrCreate()

    df = spark_session.read.format(
        "csv").schema(RAW_SCHEMA).option(
        "header", False).load(RAW_FULL_GAME_PATH)
    
    first_half_true = (col("ts") >= FIRST_HALF_START_TS) & (col("ts") <= FIRST_HALF_END_TS)
    second_half_true = (col("ts") >= SECOND_HALF_START_TS) & (col("ts") <= SECOND_HALF_END_TS)

    cleaned_ts_df = df.where(
        first_half_true | second_half_true
    ).withColumn(
        "half", when(first_half_true, 1).otherwise(2)
    ).withColumn(
        "matchSecond",
        when(
            col("half") == 1,
            ((col("ts") - lit(FIRST_HALF_START_TS)) / lit(TS_PER_SECOND)).cast("double")
        ).otherwise(
            (lit(1800) + ((col("ts") - lit(SECOND_HALF_START_TS)) / lit(TS_PER_SECOND))).cast("double")
        )
    ).withColumn(
        "x_m", col("x") / 1000.0
    ).withColumn(
        "y_m", col("y") / 1000.0
    ).withColumn(
        "z_m", col("z") / 1000.0
    ).withColumn(
        "speed_m_s", col("v_abs") * 1e-6      
    ).withColumn(
        "speed_kmh", (col("v_abs") * 1e-6) * 3.6 
    ).withColumn(
        "acceleration_m_s2", col("a_abs") * 1e-6
    )

    output_path = Path(CLEAN_FULL_GAME_PATH)
    if output_path.exists():
        shutil.rmtree(output_path)

    cleaned_ts_df.write.mode("overwrite").option("header","true").csv(CLEAN_FULL_GAME_PATH)
    spark_session.stop()

if __name__ == "__main__":
    clean_full_game()