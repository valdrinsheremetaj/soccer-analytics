from pyspark.sql import SparkSession 
from pyspark.sql.types import *
from pyspark.sql.functions import col, floor, lit, min as spark_min


GAME_START_TS = 10753295594424116
GAME_END_TS = 14879639146403495
TS_PER_SECOND = 1_000_000_000_000

RAW_FULL_GAME_PATH = "data/raw/full-game"
CLEAN_FULL_GAME_PATH = "data/processed/full-game-clean"


SCHEMA = StructType([
    StructField("sid", IntegerType(), True),
    StructField("ts", LongType(), True),
    StructField("x", IntegerType(), True),
    StructField("y", IntegerType(), True),
    StructField("z", IntegerType(), True),
    StructField("v_abs", LongType(), True),
    StructField("a_abs", LongType(), True),
    StructField("vx", IntegerType(), True),
    StructField("vy", IntegerType(), True),
    StructField("vz", IntegerType(), True),
    StructField("ax", IntegerType(), True),
    StructField("ay", IntegerType(), True),
    StructField("az", IntegerType(), True),
])


# start_ts = df.agg({"ts": "min"}).collect()[0][0]
# end_ts = df.agg({"ts": "max"}).collect()[0][0]
